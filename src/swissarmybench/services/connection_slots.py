"""The one gate every connection call in the server passes through (domain/connection_slots.py: the rule).

Every run of a connection's code goes through bootstrap's `run_blade` (a table read, the "+" tab's query, a
catalog listing or load, a test, a blade run, the Analyze and agent reads), and that run asks here first:
`await slots.run(connection, work, kind=...)`. A Workbench kernel (its own process) asks the routes for a
leased slot instead (acquire, renew while it runs, release; a lease that is not renewed expires: the kernel
died), and its requests to the server (DuckDB SQL naming a connection's table) carry its id, so the slot the
server takes for it is counted as the kernel's caller.

Who is asking comes from the request (CURRENT, set at the door by server/app.py): the agent (X-Actor), the
page (its client id, X-Sab-Client, so its Cancel finds its query), a kernel (X-Kernel: the Workbench
knows who started the cell it runs, the user or the agent), or background work (a catalog that loads itself).

A slot is always given back when its work ends: an answer, an error, a timeout, a Cancel, a killed child
process (the work is its own task; cancelling it kills the child, server/blade_runner.py). Nothing here
blocks: the live notice (`connection_slots`, names and counts only, never SQL) is sent once per loop turn.
The SQL text stays in memory for the Queries window, shown to the user only (sql(): refused to the agent).
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
from collections.abc import Awaitable, Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, TypeVar

from swissarmybench.domain import connection_slots as rules
from swissarmybench.domain.connection_slots import Board, Limits, Ticket
from swissarmybench.domain.query_text import format_sql
from swissarmybench.domain.refusals import first_sentence, try_again
from swissarmybench.services.agent import NoOneToAsk
from swissarmybench.services.changes import raised
from swissarmybench.services.ports import Approvals, Audit, Notifier
from swissarmybench.services.workspace import NotFound, TimedOut

T = TypeVar("T")

AGENT_WAIT_LOGGED: float = 3.0  # an agent's wait longer than this is a Session entry
SWEEP_SECONDS: float = 1.0


@dataclass(frozen=True)
class Caller:
    """Who a connection call is for."""

    role: str = rules.USER
    who: str = "You"
    client: str = ""
    kernel: str = ""
    priority: int = rules.INTERACTIVE
    source: dict[str, Any] = field(default_factory=dict)


CURRENT: ContextVar[Caller | None] = ContextVar("sab_connection_caller", default=None)
BACKGROUND = Caller(rules.BACKGROUND_CALLER, "Background catalog", priority=rules.BACKGROUND)


@contextlib.contextmanager
def calling_as(caller: Caller) -> Iterator[None]:
    """Run what follows as `caller` (a background load, a request's own caller)."""
    token = CURRENT.set(caller)
    try:
        yield
    finally:
        CURRENT.reset(token)


class ConnectionSlots:
    def __init__(
        self,
        live: Notifier,
        audit: Audit,
        limits_of: Callable[[str], Limits],
        save_limits: Callable[[str, dict[str, int]], str] | None = None,
        approvals: Approvals | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._live = live
        self._audit = audit
        self.board = Board(limits_of)
        # A connection's limits written into its file's header (adapters/blades.py set_header): its name.
        self._save_limits = save_limits
        self._approvals: Approvals = approvals or NoOneToAsk()  # the user's Allow
        self._clock = clock
        self._waiters: dict[str, asyncio.Future[str]] = {}
        self._tasks: dict[str, asyncio.Future[Any]] = {}
        self._cancelled: set[str] = set()
        # A kernel's caller now (services/workbench.py: the user's or the agent's cell), its interrupt.
        self.kernel_caller: Callable[[str], Caller] = lambda kernel: Caller(kernel=kernel)
        self.interrupt_kernel: Callable[[str], Awaitable[None]] | None = None
        # Each finished call heard (the statistics: services/call_stats.py CallStats.finished).
        self.on_finished: Callable[[dict[str, Any], list[Any]], None] | None = None
        self._dirty = False
        self._sweeper: asyncio.Task[None] | None = None
        self.started = secrets.token_hex(
            4
        )  # this start's id: a page that sees another knows the app restarted

    # ===== the gate =====

    async def run(
        self,
        connection: str,
        work: Callable[[], Awaitable[T]],
        kind: str = "query",
        targets: tuple[str, ...] = (),
        sql: str = "",
        dialect: str = "",
    ) -> T:
        """`work` in one of the connection's slots: waiting in line first when they are all taken (TimedOut
        after its wait limit, or on a Cancel); the slot given back however the work ends."""
        caller = CURRENT.get() or Caller()
        ticket = self._ticket(connection, caller, kind, targets, sql, dialect)
        await self._wait(ticket)
        task: asyncio.Future[T] = asyncio.ensure_future(work())
        self._tasks[ticket.id] = task
        outcome, reason, rows, facts = "ok", "", None, []
        try:
            answer = await task
            table: Any = answer.get("table") if isinstance(answer, dict) else None
            rows = int(table.num_rows) if table is not None and hasattr(table, "num_rows") else None
            said = answer.pop("facts", None) if isinstance(answer, dict) else None  # the statistics' only
            facts = said if isinstance(said, list) else []
            return answer
        except asyncio.CancelledError:
            outcome = "cancelled"
            if ticket.id in self._cancelled:
                raise TimedOut(rules.cancelled_words(ticket.connection), where=ticket.connection) from None
            raise
        except TimedOut as error:
            outcome, reason = "failed", first_sentence(str(error), 200)
            raise
        except Exception as error:
            outcome, reason = "failed", first_sentence(str(error) or type(error).__name__, 200)
            raise
        finally:
            self._tasks.pop(ticket.id, None)
            self._cancelled.discard(ticket.id)
            self._leave(ticket.id, outcome, reason, rows, facts)

    def _ticket(
        self, connection: str, caller: Caller, kind: str, targets: tuple[str, ...], sql: str, dialect: str
    ) -> Ticket:
        if caller.kernel and caller.role == rules.USER and caller.who == "You":
            caller = self.kernel_caller(caller.kernel)
        return Ticket(
            id=secrets.token_hex(5),
            connection=connection,
            caller=caller.role,
            who=caller.who,
            kind=kind,
            targets=tuple(t for t in targets if t)[:10],
            sql=sql[:200_000],
            dialect=dialect,
            source=dict(caller.source) | ({"kernel": caller.kernel} if caller.kernel else {}),
            client=caller.client,
            priority=caller.priority,
        )

    async def _wait(self, ticket: Ticket) -> None:
        began = self._clock()
        self._wake(self.board.ask(ticket, began))
        self._changed()
        if ticket.running:
            return
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._waiters[ticket.id] = future
        limit = self.board.limits(ticket.connection).wait
        try:
            said = await asyncio.wait_for(future, limit)
        except TimeoutError:
            running = self.board.status(ticket.connection)["running"]
            self._leave(ticket.id, "timed out", "waited past its limit")
            raise TimedOut(
                rules.gave_up_words(ticket.connection, limit, running),
                where=ticket.connection,
                fixes=[try_again()],
            ) from None
        except asyncio.CancelledError:
            self._leave(ticket.id, "cancelled", "")
            raise
        finally:
            self._waiters.pop(ticket.id, None)
        if said == "cancelled":
            raise TimedOut(rules.cancelled_words(ticket.connection), where=ticket.connection)
        waited = self._clock() - began
        if ticket.caller == rules.AGENT and waited > AGENT_WAIT_LOGGED:
            self._audit.write("agent", "connection_slot_waited", ticket.connection, seconds=round(waited))

    def _wake(self, started: list[Ticket]) -> None:
        for ticket in started:
            future = self._waiters.get(ticket.id)
            if future is not None and not future.done():
                future.set_result("go")

    def _leave(
        self,
        ticket_id: str,
        outcome: str,
        reason: str,
        rows: int | None = None,
        facts: list[Any] | None = None,
    ) -> None:
        left, started = self.board.leave(ticket_id, self._clock(), outcome, reason, rows)
        self._wake(started)
        self._changed()
        if left is not None and self.board.finished and self.on_finished is not None:
            # The call statistics (services/call_stats.py): the finished entry and the adapter's facts its
            # child process sent back. A listener that fails never fails the call.
            with contextlib.suppress(Exception):
                self.on_finished(self.board.finished[0].to_json(), list(facts or []))

    # ===== cancel =====

    async def cancel(self, ticket_id: str, who: str = "user") -> dict[str, Any]:
        """A waiting query leaves the line; a running one is stopped (its child process killed, its kernel
        interrupted). The agent cancels its own freely, the user's on the user's Allow."""
        ticket = self.board.get(ticket_id)
        if ticket is None:
            raise NotFound("That query has finished.")
        if who == "agent" and ticket.caller != rules.AGENT:
            await self._approvals.allowed(
                who,
                subject=ticket.connection,
                action="cancel a query",
                detail=f"Cancel {ticket.who}'s {rules.KINDS.get(ticket.kind, ticket.kind)} "
                f"on {ticket.connection}",
                otherwise="their query was not cancelled",
            )
        state = "running" if ticket.running else "waiting"
        future = self._waiters.get(ticket_id)
        if future is not None and not future.done():
            future.set_result("cancelled")  # its _wait leaves the line
            self._leave(ticket_id, "cancelled", "")
        elif ticket.running and ticket_id in self._tasks:
            self._cancelled.add(ticket_id)
            self._tasks[ticket_id].cancel()  # run()'s finally gives the slot back
        elif ticket.kernel:
            if ticket.running and self.interrupt_kernel is not None:
                with contextlib.suppress(Exception):
                    await self.interrupt_kernel(ticket.kernel)
            self._leave(ticket_id, "cancelled", "")
        else:
            self._leave(ticket_id, "cancelled", "")
        self._audit.write(who, "connection_query_cancel", ticket.connection)
        return {"cancelled": ticket_id, "connection": ticket.connection, "was": state}

    async def cancel_client(self, client: str, who: str = "user") -> dict[str, Any]:
        """Every query a page asked for that still waits or runs (the loading state's Cancel)."""
        found = [t.id for t in self.board.tickets() if client and t.client == client]
        for ticket_id in found:
            with contextlib.suppress(NotFound):
                await self.cancel(ticket_id, who)
        return {"cancelled": found}

    # ===== a kernel's leased slot =====

    def acquire(self, body: Any, kernel: str) -> dict[str, Any]:
        """A Workbench kernel asks for a slot: running now, or waiting with its place (it renews to hear)."""
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("connection"), str)
            or not body["connection"]
        ):
            raise ValueError('Send {"connection": "...", "kind": "query"}.')
        if not kernel:
            raise ValueError("A slot is asked for by a Workbench kernel (X-Kernel).")
        caller = self.kernel_caller(kernel)
        targets = tuple(str(t) for t in body.get("targets") or [] if isinstance(t, str))
        kind = str(body.get("kind") or "query")
        sql = str(body.get("sql") or "")
        dialect = str(body.get("dialect") or "")
        ticket = self._ticket(body["connection"].strip()[:120], caller, kind, targets, sql, dialect)
        ticket.kernel = kernel
        if isinstance(body.get("cell"), int | str):
            ticket.source["cell"] = body["cell"]
        now = self._clock()
        ticket.lease_until = now + rules.LEASE_SECONDS
        self._wake(self.board.ask(ticket, now))
        self._changed()
        self._sweep_soon()
        return self._lease_state(ticket)

    def renew(self, ticket_id: str) -> dict[str, Any]:
        """A kernel's slot kept (its lease renewed), and how it stands: running, waiting (its place), or
        ended (cancelled, timed out, expired)."""
        ticket = self.board.renew(ticket_id, self._clock())
        if ticket is None:
            for done in self.board.finished:
                if done.ticket.id == ticket_id:
                    words = (
                        rules.gave_up_words(
                            done.ticket.connection, self.board.limits(done.ticket.connection).wait, 0
                        )
                        if done.outcome == "timed out"
                        else rules.cancelled_words(done.ticket.connection)
                    )
                    return {"ticket": ticket_id, "state": done.outcome, "words": words}
            return {"ticket": ticket_id, "state": "ended", "words": "The slot is no longer held."}
        now = self._clock()
        if not ticket.running and now - ticket.queued_at >= self.board.limits(ticket.connection).wait:
            running = self.board.status(ticket.connection)["running"]
            waited = self.board.limits(ticket.connection).wait
            self._leave(ticket_id, "timed out", "waited past its limit")
            return {
                "ticket": ticket_id,
                "state": "timed out",
                "words": rules.gave_up_words(ticket.connection, waited, running),
            }
        return self._lease_state(ticket)

    def release(self, ticket_id: str, body: Any) -> dict[str, Any]:
        body = body if isinstance(body, dict) else {}
        outcome = str(body.get("outcome") or "ok")
        reason = str(body.get("reason") or "")[:300]
        rows = body.get("rows") if isinstance(body.get("rows"), int) else None
        self._leave(ticket_id, outcome if outcome in rules.OUTCOMES else "ok", reason, rows)
        return {"released": ticket_id}

    def _lease_state(self, ticket: Ticket) -> dict[str, Any]:
        place = self.board.place(ticket)
        out: dict[str, Any] = {"ticket": ticket.id, "state": "running" if ticket.running else "waiting"}
        if place is not None:
            out |= {"place": place, "words": rules.kernel_words(ticket.connection, place)}
        return out

    def _sweep_soon(self) -> None:
        if self._sweeper is None or self._sweeper.done():
            self._sweeper = asyncio.get_running_loop().create_task(self._sweep())

    async def _sweep(self) -> None:
        """Kernels' slots whose lease ran out go back (the kernel died); it stops when none is leased."""
        while any(t.kernel for t in self.board.tickets()):
            await asyncio.sleep(SWEEP_SECONDS)
            self.expire()

    def expire(self) -> list[str]:
        now = self._clock()
        gone = [t.id for t in self.board.expired(now)]
        for ticket_id in gone:
            self._leave(ticket_id, "ended", "its kernel stopped answering")
        overdue = [t.id for t in self.board.overdue(now) if t.kernel]
        for ticket_id in overdue:
            self._leave(ticket_id, "timed out", "waited past its limit")
        return gone

    def kernel_stopped(self, kernel: str) -> None:
        """A kernel closed or died: its slots go back at once."""
        for ticket in self.board.tickets():
            if ticket.kernel == kernel:
                self._leave(ticket.id, "ended", "its kernel stopped")

    # ===== reading =====

    def status(self, names: list[str]) -> dict[str, Any]:
        """Each connection's counts and limits (the cards): names and counts only."""
        everyone = names + [
            n for n in self.board.names() if n.casefold() not in {x.casefold() for x in names}
        ]
        return {"connections": [self.board.status(n) for n in everyone], "started": self.started}

    def queries(self, connection: str | None = None, with_sql: bool = False) -> dict[str, Any]:
        """The running and waiting queries (one connection's, or every one's), and the finished ones. No SQL
        text in it (sql() gives one query's, to the user)."""
        now = self._clock()
        wanted = connection or None
        tickets = []
        for ticket in self.board.tickets(wanted):
            place = self.board.place(ticket)
            row = ticket.to_json(now, place)
            if place is not None:
                running = self.board.status(ticket.connection)["running"]
                row["words"] = rules.waiting_words(ticket.connection, place, running)
            tickets.append(row)
        finished = [
            f.to_json()
            for f in self.board.finished
            if wanted is None or f.ticket.connection.casefold() == wanted.casefold()
        ]
        names = [wanted] if wanted else self.board.names()
        return {
            "queries": tickets,
            "finished": finished,
            "connections": [self.board.status(n) for n in names],
            "started": self.started,
            "now": now,
        }

    def sql(self, ticket_id: str) -> dict[str, Any]:
        """One query's SQL as written (`${NAME}` unresolved) and formatted for reading: the user's only."""
        ticket = self.board.get(ticket_id)
        if ticket is None:
            ticket = next((f.ticket for f in self.board.finished if f.ticket.id == ticket_id), None)
        if ticket is None:
            raise NotFound("That query is no longer listed.")
        return {
            "id": ticket.id,
            "connection": ticket.connection,
            "dialect": ticket.dialect,
            "sql": ticket.sql,
            "formatted": format_sql(ticket.sql, ticket.dialect),
            "language": "dax" if ticket.dialect == "dax" else "sql",
        }

    def clear_finished(self) -> dict[str, Any]:
        cleared = self.board.clear_finished()
        self._changed()
        return {"cleared": cleared}

    # ===== the limits =====

    def limits(self, name: str) -> dict[str, Any]:
        return {"connection": name, **self.board.limits(name).to_json(), "defaults": Limits().to_json()}

    def set_limits(self, name: str, body: Any, who: str = "user") -> dict[str, Any]:
        """A connection's limits (its file's [queries]): total 1 to 64, the agent's at most the total."""
        if self._save_limits is None:
            raise ValueError("The limits cannot be saved here.")
        was = self.board.limits(name)
        limits = rules.check_limits(body if isinstance(body, dict) else None, was)
        saved = self._save_limits(name, limits.header())
        # The change log: a setting by name (the counts are settings, not data).
        change = raised(
            "setting", f"{saved} queries at once", {"limits": was.to_json()}, {"limits": limits.to_json()}
        )
        self._audit.write(who, "connection_limits", saved, total=limits.total, agent=limits.agent, **change)
        self._wake(self.board.regrant(saved, self._clock()))
        self._changed()
        return self.limits(saved)

    # ===== the live notice =====

    def _changed(self) -> None:
        """Tell the pages once this loop turn (never awaited by the work it describes)."""
        if self._dirty:
            return
        self._dirty = True
        try:
            asyncio.get_running_loop().call_soon(self._flush)
        except RuntimeError:
            self._dirty = False

    def _flush(self) -> None:
        self._dirty = False
        snapshot = self.queries()
        message = {"type": "connection_slots"} | {
            k: snapshot[k] for k in ("queries", "connections", "started")
        }
        message["finished"] = snapshot["finished"][:1]  # the newest, so a page knows the list moved
        asyncio.get_running_loop().create_task(self._send(message))

    async def _send(self, message: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await self._live.broadcast(message)
