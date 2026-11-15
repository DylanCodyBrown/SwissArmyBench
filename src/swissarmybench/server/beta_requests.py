"""The beta log at the HTTP door (services/beta_log.py): how long each request took to answer, and the
errors routes answer with.

A pure ASGI middleware: it times each request to its first byte (a streamed answer counts until it
starts) and, past the slow mark, logs the route's PATTERN (`/grids/{grid_id}/rows`), never the URL, which
names tables. It keeps the request's beta log in a context variable, so `report()` (called by
http.error_response) can log an error with its route. Beta mode off: one attribute read per request.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from swissarmybench.services.beta_log import BetaLog

# Routes that wait on purpose (for the user, a page or a child process to answer): never "slow".
WAITS: frozenset[str] = frozenset(
    {
        "/snapshots",
        "/workbench/window",
        "/workbench/kernels",
        "/workbench/environments",
        "/agent/export-approval/{grid_id}",
    }
)

_current: ContextVar[tuple[BetaLog, Scope] | None] = ContextVar("beta_request", default=None)


def route_of(scope: Scope) -> str | None:
    """The pattern of the route that took the request, or None before one did."""
    path = getattr(scope.get("route"), "path", None)
    return path if isinstance(path, str) else None


def report(error: BaseException, status: int) -> None:
    """A route answered with an error: 5xx as a server error (its stack), 4xx as a refusal (its words)."""
    found = _current.get()
    if found is None:
        return
    beta, scope = found
    route, method = route_of(scope), scope.get("method")
    if status >= 500:
        beta.server_error(error, route, method)
    else:
        beta.refused(error, route, method, status)


class BetaRequests:
    def __init__(self, app: ASGIApp, beta: BetaLog, slow_seconds: float) -> None:
        self.app = app
        self.beta = beta
        self.slow_seconds = slow_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.beta.on:
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        answered: dict[str, Any] = {}

        async def sending(message: Message) -> None:
            if message["type"] == "http.response.start" and not answered:
                answered["at"], answered["status"] = time.perf_counter(), int(message.get("status", 0))
            await send(message)

        token = _current.set((self.beta, scope))
        try:
            await self.app(scope, receive, sending)
        except Exception as error:
            self.beta.server_error(error, route_of(scope), scope.get("method"))
            raise
        finally:
            _current.reset(token)
            seconds = answered.get("at", time.perf_counter()) - started
            route = route_of(scope)
            if seconds >= self.slow_seconds and route is not None and route not in WAITS:
                self.beta.slow(
                    route, str(scope.get("method", "")), answered.get("status", 500), seconds * 1000
                )
