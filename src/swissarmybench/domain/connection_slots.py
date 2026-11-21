"""How many queries run at once on one connection (the owner, 2026-11-21: "we should probably throttle how
many queries an agent can run in parallel per connection").

His answers: one limit per connection covers every query (the user's, notebooks' and scripts' in Workbench
kernels, background catalog loads, the agent's), and the agent has a smaller share, so it can never take all
of a connection's slots. Over the limit a query waits in line: it shows its place and a Cancel, and gives up
with a plain message after the wait limit. The defaults: 8 at once, at most 4 of them the agent's, a wait of
two minutes; each connection's own in its file's header (`[queries]`: total, agent, wait).

The line is first come, first served within a priority: the user's interactive work (a grid, a query, a
notebook) goes ahead of background catalog loads; an agent's query that waits for the agent's share lets
the user's behind it go first (it is not the user's share it waits for).

A Board holds every connection's line: pure, no clock (each call is given `now`), no I/O. The service
(services/connection_slots.py) wakes the waiters it grants and keeps the leases of kernels' slots.
Standard library only (the plain client reads a connection's [queries] through domain/blades.py).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

DEFAULT_TOTAL: int = 8
DEFAULT_AGENT: int = 4
DEFAULT_WAIT: int = 120  # seconds a query waits in line before it gives up
MOST_TOTAL: int = 64
MOST_WAIT: int = 3_600
LEASE_SECONDS: float = 15.0  # a kernel's slot expires unless renewed within this (the kernel died)
FINISHED_KEPT: int = 50

INTERACTIVE: int = 0
BACKGROUND: int = 5

USER, AGENT, BACKGROUND_CALLER = "user", "agent", "background"
CALLERS: tuple[str, ...] = (USER, AGENT, BACKGROUND_CALLER)

# What a query is, in the Queries window's words.
KINDS: dict[str, str] = {
    "read": "table read",
    "rows": "table read",
    "query": "query",
    "queries": "query",
    "catalog": "catalog listing",
    "datasets": "catalog listing",
    "test": "test",
    "blade": "blade run",
    "analyze": "Analyze",
    "probe": "access check",
}

OUTCOMES: tuple[str, ...] = ("ok", "cancelled", "failed", "timed out", "ended")


class LimitsError(ValueError):
    """A limit that cannot be: said in one plain sentence."""


@dataclass(frozen=True)
class Limits:
    total: int = DEFAULT_TOTAL
    agent: int = DEFAULT_AGENT
    wait: int = DEFAULT_WAIT

    def to_json(self) -> dict[str, int]:
        return {"total": self.total, "agent": self.agent, "wait": self.wait}

    def header(self) -> dict[str, int]:
        """What a connection's file keeps: only what differs from the defaults (a file with the defaults
        has no [queries] table, so no existing file changes)."""
        default = Limits()
        return {k: v for k, v in self.to_json().items() if v != getattr(default, k)}


def _whole(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str) or not str(value).strip().isdigit():
        raise LimitsError(f"{label} is a whole number.")
    return int(value)


def check_limits(raw: Mapping[str, Any] | None, base: Limits | None = None) -> Limits:
    """Limits from a form or a file's header: total 1 to 64, the agent's share at most the total (0: the
    agent runs nothing here), the wait 1 second to an hour. Missing keys keep `base`'s (the defaults)."""
    start = base or Limits()
    if raw is None:
        return start
    if not isinstance(raw, Mapping):
        raise LimitsError("The limits are {total, agent, wait}.")
    unknown = set(raw) - {"total", "agent", "wait"}
    if unknown:
        raise LimitsError(f"The limits are total, agent and wait, not {', '.join(sorted(unknown))}.")
    given = {k: v for k, v in raw.items() if v not in (None, "")}
    total = _whole(given["total"], "Queries at once") if "total" in given else start.total
    agent = _whole(given["agent"], "The agent's share") if "agent" in given else start.agent
    wait = _whole(given["wait"], "The wait limit") if "wait" in given else start.wait
    if not 1 <= total <= MOST_TOTAL:
        raise LimitsError(f"Queries at once is between 1 and {MOST_TOTAL}.")
    if "agent" not in given and agent > total:
        agent = total
    if agent > total:
        raise LimitsError(f"The agent's share is at most the {total} queries at once.")
    if not 1 <= wait <= MOST_WAIT:
        raise LimitsError("The wait limit is between 1 second and an hour (3600 seconds).")
    return Limits(total, agent, wait)


def limits_of_header(header: Any) -> Limits:
    """A file's [queries] table read loosely: anything wrong reads as the defaults (a hand edit never
    stops a connection from running)."""
    try:
        return check_limits(header if isinstance(header, Mapping) else None)
    except LimitsError:
        return Limits()


@dataclass
class Ticket:
    """One query on one connection: waiting in line, or running in one of its slots."""

    id: str
    connection: str
    caller: str = USER  # user, agent or background
    who: str = "You"  # You, Notebook sales.ipynb, Script load.py, The agent, Background catalog
    kind: str = "query"  # KINDS' key
    targets: tuple[str, ...] = ()  # the table names it reads, where known
    sql: str = ""  # the text as written (${NAME} unresolved): the user's only, never the agent's or a log's
    dialect: str = ""
    source: dict[str, Any] = field(default_factory=dict)  # where it came from: a grid, a kernel's cell
    client: str = ""  # the page that asked (its cancel finds it)
    kernel: str = ""  # a Workbench kernel's slot (leased)
    priority: int = INTERACTIVE
    seq: int = 0
    queued_at: float = 0.0
    started_at: float | None = None
    lease_until: float | None = None
    rows: int | None = None

    @property
    def running(self) -> bool:
        return self.started_at is not None

    def to_json(self, now: float, place: int | None = None, with_sql: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "connection": self.connection,
            "caller": self.caller,
            "who": self.who,
            "kind": self.kind,
            "what": KINDS.get(self.kind, self.kind),
            "targets": list(self.targets),
            "state": "running" if self.running else "waiting",
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "elapsed": round(now - (self.started_at if self.started_at is not None else self.queued_at), 1),
            "source": dict(self.source),
            "has_sql": bool(self.sql),
        }
        if place is not None:
            out["place"] = place
        if self.rows is not None:
            out["rows"] = self.rows
        if self.kernel:
            out["kernel"] = self.kernel
        if self.client:
            out["client"] = self.client
        if with_sql and self.sql:
            out["sql"] = self.sql
            out["dialect"] = self.dialect
        return out


@dataclass(frozen=True)
class Finished:
    ticket: Ticket
    ended_at: float
    outcome: str
    reason: str = ""

    def to_json(self, with_sql: bool = False) -> dict[str, Any]:
        t = self.ticket
        began = t.started_at if t.started_at is not None else t.queued_at
        out = {
            "id": t.id,
            "connection": t.connection,
            "caller": t.caller,
            "who": t.who,
            "kind": t.kind,
            "what": KINDS.get(t.kind, t.kind),
            "targets": list(t.targets),
            "outcome": self.outcome,
            "reason": self.reason,
            "ended_at": self.ended_at,
            "seconds": round(self.ended_at - began, 2),
            "waited": round((t.started_at or self.ended_at) - t.queued_at, 2),
            "source": dict(t.source),
            "has_sql": bool(t.sql),
        }
        if t.rows is not None:
            out["rows"] = t.rows
        if with_sql and t.sql:
            out["sql"] = t.sql
            out["dialect"] = t.dialect
        return out


@dataclass
class Line:
    """One connection's slots: who runs, who waits."""

    name: str
    running: list[Ticket] = field(default_factory=list)
    waiting: list[Ticket] = field(default_factory=list)

    def agent_running(self) -> int:
        return sum(1 for t in self.running if t.caller == AGENT)

    def ordered(self) -> list[Ticket]:
        return sorted(self.waiting, key=lambda t: (t.priority, t.seq))


class Board:
    """Every connection's line. `limits_of(name)` gives a connection's limits (its file's header)."""

    def __init__(self, limits_of: Callable[[str], Limits] = lambda name: Limits()) -> None:
        self._limits_of = limits_of
        self._lines: dict[str, Line] = {}
        self._by_id: dict[str, Ticket] = {}
        self._seq = 0
        self.finished: deque[Finished] = deque(maxlen=FINISHED_KEPT)

    # ===== reading =====

    def limits(self, name: str) -> Limits:
        try:
            return self._limits_of(name)
        except (KeyError, LookupError, LimitsError):
            return Limits()

    def get(self, ticket_id: str) -> Ticket | None:
        return self._by_id.get(ticket_id)

    def tickets(self, connection: str | None = None) -> list[Ticket]:
        out: list[Ticket] = []
        for line in self._lines.values():
            if connection is None or line.name.casefold() == connection.casefold():
                out += line.running + line.ordered()
        return out

    def names(self) -> list[str]:
        return [line.name for line in self._lines.values() if line.running or line.waiting]

    def place(self, ticket: Ticket) -> int | None:
        """A waiting ticket's place in line (1 is next), or None when it runs (or is gone)."""
        line = self._lines.get(ticket.connection.casefold())
        if line is None or ticket.running:
            return None
        for number, waiting in enumerate(line.ordered(), start=1):
            if waiting.id == ticket.id:
                return number
        return None

    def status(self, name: str) -> dict[str, Any]:
        line = self._lines.get(name.casefold()) or Line(name)
        limits = self.limits(name)
        running, waiting, agent_running = len(line.running), len(line.waiting), line.agent_running()
        return {
            "connection": line.name if (line.running or line.waiting) else name,
            "running": running,
            "waiting": waiting,
            "agent_running": agent_running,
            "agent_waiting": sum(1 for t in line.waiting if t.caller == AGENT),
            "limits": limits.to_json(),
            "words": status_words(running, waiting, limits.total),
            "full_words": status_words(running, waiting, limits.total, agent_running, limits.agent),
        }

    # ===== changing =====

    def ask(self, ticket: Ticket, now: float) -> list[Ticket]:
        """A query asks for a slot: it joins its connection's line; the tickets that may start now (this one
        among them when there is room) come back, started."""
        self._seq += 1
        ticket.seq = self._seq
        ticket.queued_at = now
        key = ticket.connection.casefold()
        line = self._lines.setdefault(key, Line(ticket.connection))
        line.waiting.append(ticket)
        self._by_id[ticket.id] = ticket
        return self._pump(line, now)

    def leave(
        self, ticket_id: str, now: float, outcome: str = "ok", reason: str = "", rows: int | None = None
    ) -> tuple[Ticket | None, list[Ticket]]:
        """A query is done (ended, failed, cancelled, timed out, its lease expired): its place or slot is
        free. The ticket (None: already gone) and the ones that start now."""
        ticket = self._by_id.pop(ticket_id, None)
        if ticket is None:
            return None, []
        if rows is not None:
            ticket.rows = rows
        line = self._lines.get(ticket.connection.casefold())
        if line is not None:
            line.running = [t for t in line.running if t.id != ticket_id]
            line.waiting = [t for t in line.waiting if t.id != ticket_id]
        self.finished.appendleft(
            Finished(ticket, now, outcome if outcome in OUTCOMES else "ok", reason[:300])
        )
        started = self._pump(line, now) if line is not None else []
        if line is not None and not line.running and not line.waiting:
            self._lines.pop(ticket.connection.casefold(), None)
        return ticket, started

    def renew(self, ticket_id: str, now: float, seconds: float = LEASE_SECONDS) -> Ticket | None:
        ticket = self._by_id.get(ticket_id)
        if ticket is not None and ticket.kernel:
            ticket.lease_until = now + seconds
        return ticket

    def expired(self, now: float) -> list[Ticket]:
        """Kernels' tickets whose lease ran out (the kernel died or was stopped)."""
        return [
            t for t in self._by_id.values() if t.kernel and t.lease_until is not None and t.lease_until < now
        ]

    def overdue(self, now: float) -> list[Ticket]:
        """Waiting tickets past their connection's wait limit."""
        return [
            t
            for t in self._by_id.values()
            if not t.running and now - t.queued_at >= self.limits(t.connection).wait
        ]

    def regrant(self, name: str, now: float) -> list[Ticket]:
        """A connection's limits changed: the ones that may start now."""
        line = self._lines.get(name.casefold())
        return self._pump(line, now) if line is not None else []

    def clear_finished(self) -> int:
        count = len(self.finished)
        self.finished.clear()
        return count

    def _pump(self, line: Line, now: float) -> list[Ticket]:
        limits = self.limits(line.name)
        started: list[Ticket] = []
        for ticket in line.ordered():
            if len(line.running) >= limits.total:
                break
            if ticket.caller == AGENT and line.agent_running() >= limits.agent:
                continue  # the agent's share is full: the others behind it go first
            line.waiting.remove(ticket)
            ticket.started_at = now
            line.running.append(ticket)
            started.append(ticket)
        return started


# ===== words =====


def ordinal(number: int) -> str:
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _queries(count: int) -> str:
    return f"{count} {'query' if count == 1 else 'queries'}"


def waiting_words(connection: str, place: int, running: int) -> str:
    """ "Waiting: 3rd in line for Warehouse (8 queries running)"."""
    return f"Waiting: {ordinal(place)} in line for {connection} ({_queries(running)} running)"


def kernel_words(connection: str, place: int) -> str:
    """A cell's line while it waits: "Waiting for a slot on Warehouse (2nd in line)"."""
    return f"Waiting for a slot on {connection} ({ordinal(place)} in line)"


def status_words(
    running: int, waiting: int, total: int, agent_running: int | None = None, agent: int | None = None
) -> str:
    """ "Running 3 of 8 · 1 waiting" (the card), with " · agent 2 of 4" (the Queries window)."""
    words = f"Running {running} of {total}"
    if waiting:
        words += f" · {waiting} waiting"
    if agent_running is not None and agent is not None:
        words += f" · agent {agent_running} of {agent}"
    return words


def duration_words(seconds: float) -> str:
    whole = round(seconds)
    if whole >= 60 and whole % 60 == 0:
        minutes = whole // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{whole} second{'s' if whole != 1 else ''}"


def gave_up_words(connection: str, waited: float, running: int) -> str:
    """The refusal after the wait limit."""
    return (
        f"Waited {duration_words(waited)} for a slot on {connection} ({_queries(running)} running) and gave "
        "up: try again, or raise its limit."
    )


def cancelled_words(connection: str) -> str:
    return f"Cancelled: the query on {connection} was stopped."


def summary(board: Board, names: Iterable[str]) -> list[dict[str, Any]]:
    """Each named connection's counts (the cards)."""
    return [board.status(n) for n in names]


# ===== a connection's file: its [queries] table =====


def header_lines(queries: Any) -> list[str]:
    """The [queries] table of a connection's file header (only what differs from the defaults)."""
    if not isinstance(queries, Mapping) or not queries:
        return []
    lines = ["", "[queries]  # at once on this connection, the agent's share, seconds one waits in line"]
    return lines + [f"{key} = {int(queries[key])}" for key in ("total", "agent", "wait") if key in queries]


def from_header(header: Mapping[str, Any]) -> dict[str, Any]:
    """A file header's [queries] as a blade's field (none when it holds only the defaults or is absent)."""
    found = limits_of_header(header.get("queries")).header() if isinstance(header, Mapping) else {}
    return {"queries": found} if found else {}


def queries_of(
    data: Mapping[str, Any], previous: Mapping[str, int] | None, error: type[Exception] = LimitsError
) -> dict[str, int]:
    """A save's limits: the ones sent (checked; `error` raised with the reason), else the connection's own
    kept (a form's save)."""
    if "queries" not in data:
        return dict(previous or {})
    raw = data["queries"]
    try:
        return check_limits(raw if raw else None).header()
    except LimitsError as said:
        raise error(str(said)) from None
