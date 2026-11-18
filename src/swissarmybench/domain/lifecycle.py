"""The server's life follows the app (the owner, 2026-11-18: "I wanted the server to simply run while the app
is active and shutdown when it's not instead of all this crazy server background junk"; "Stay up while
they're busy"). Standard library only, no clock: the service gives it the times.

  windows    the app's pages connected (the desktop app's windows, a browser's tabs): the server stays
  grace      the last one closed: it stops GRACE seconds later (a reload, a slow tab, must not end it);
             at the start, before the first window arrives, START_GRACE seconds
  closed     the desktop app said it closed (its last window): no grace beyond CLOSE_GRACE
  clients    the agent, VS Code, a Python session's push, a Workbench kernel's report: each request with the
             token (not the pages' cookie) counts; the server then stops IDLE seconds after the last one with
             still no window
  busy       something at work right now (a VS Code window connected, a kernel running a cell, a scheduled
             script running): no stop while it is
  held       a reason not to stop at all yet (an open project with unsaved changes and Autosave off)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GRACE_SECONDS: float = 30.0
START_GRACE_SECONDS: float = 120.0
CLOSE_GRACE_SECONDS: float = 2.0
IDLE_SECONDS: float = 600.0
# Requests that are the pages' own even with the token (the page trades the token for its cookie here).
PAGE_PATHS: tuple[str, ...] = ("/session",)
# Asking whether the server is there, or when it stops, is not work: the desktop app's own /health checks
# (at its start and with each page it opens) kept the server up 10 minutes after the app closed.
NOT_WORK_PATHS: tuple[str, ...] = ("/health", "/lifecycle")
NOTICE_GONE = "The tray icon is gone: Swiss Army Bench now runs while it's open."


@dataclass
class Life:
    """What the stop is worked out from (times in seconds on one clock)."""

    started: float
    windows: int = 0
    windows_gone_at: float | None = None  # when the last window closed (None: one is open, or none yet)
    client_at: float | None = None  # the last request of a client that is not a page
    client: str = ""  # who that was (agent, vscode, a client)
    closed_at: float | None = None  # the desktop app said its last window closed
    busy: list[str] = field(default_factory=list)
    held: str = ""


def stop_at(
    life: Life,
    grace: float = GRACE_SECONDS,
    idle: float = IDLE_SECONDS,
    start_grace: float = START_GRACE_SECONDS,
) -> float | None:
    """When the server stops, or None while a window is open or something is busy."""
    if life.windows > 0 or life.busy:
        return None
    if life.windows_gone_at is None:
        at = life.started + start_grace  # no window yet: the first one may take a while to start
    else:
        at = life.windows_gone_at + grace
        if life.closed_at is not None and life.closed_at >= life.windows_gone_at - grace:
            at = min(at, max(life.closed_at, life.windows_gone_at) + CLOSE_GRACE_SECONDS)
    if life.client_at is not None:
        at = max(at, life.client_at + idle)
    return at


def from_a_page(sec_fetch_site: str | None) -> bool:
    """A request one of the app's own pages made: the browser (Qt WebEngine too) marks it Sec-Fetch-Site
    same-origin, which a page's script cannot change. The pages send the token as well (web/src/api.ts), so
    without this every click in a window counted as a client and held the server 10 minutes after it closed.
    The agent, VS Code and a Python push send no such header."""
    return (sec_fetch_site or "").strip().lower() == "same-origin"


def counts_as_client(path: str, by_token: bool) -> bool:
    """A request that keeps the server up for IDLE seconds: one with the token (the agent, VS Code, a push,
    a kernel), not the pages' cookie, and not the page trading its token for the cookie."""
    return by_token and not any(path == p or path.startswith(p + "/") for p in (*PAGE_PATHS, *NOT_WORK_PATHS))


def state(life: Life, now: float, at: float | None) -> dict[str, Any]:
    """The lifecycle as the agent reads it (app_lifecycle): windows, the last client, when it stops, why."""
    if life.held and at is not None and at <= now:
        why = life.held
    elif at is None:
        why = "a window is open" if life.windows else f"busy: {', '.join(life.busy)}"
    elif life.client_at is not None and at == life.client_at + IDLE_SECONDS:
        why = f"{life.client or 'a client'} was here {round(now - life.client_at)} s ago"
    else:
        why = "no window is open"
    return {
        "windows": life.windows,
        "last_client": None
        if life.client_at is None
        else {"who": life.client, "seconds_ago": round(now - life.client_at)},
        "busy": list(life.busy),
        "held": life.held or None,
        "stops_in": None if at is None else max(0, round(at - now)),
        "why": why,
    }
