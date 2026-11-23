"""The swap (the owner, 2026-11-23: "blazor has my approval, do the swap"): while the Blazor front end is
the one this computer opens, every classic page's address (/workspace, /g/<grid>, /notebooks, /scripts, the
Canvas, the Widgets window, the analyzer) answers with its Blazor page instead, its words kept. A bookmark,
the desktop app, a pushed grid's address and an agent's window all land on the Blazor pages. ?classic=1 shows
the classic page anyway (those pages stay one release, then go). The #token stays with the browser."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl

from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from swissarmybench.domain import navigation


class ClassicToBlazor:
    """ASGI middleware: a classic page's GET answers 302 to its Blazor page while `chosen()` is "blazor" and
    the Blazor front end is built here (`built`); anything else passes through untouched."""

    def __init__(self, app: ASGIApp, chosen: Callable[[], str], built: bool) -> None:
        self.app = app
        self.chosen = chosen
        self.built = built

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._moves(scope):
            query = dict(parse_qsl(scope.get("query_string", b"").decode("latin-1")))
            if "classic" not in query:
                address = navigation.blazor_address(scope["path"], query)
                await RedirectResponse(address, status_code=302)(scope, receive, send)
                return
        await self.app(scope, receive, send)

    def _moves(self, scope: Scope) -> bool:
        return (
            self.built
            and scope["type"] == "http"
            and scope.get("method") in ("GET", "HEAD")
            and navigation.is_classic_page(str(scope.get("path", "")))
            and self.chosen() == "blazor"
        )


def chosen_by(frontend: Callable[[], dict[str, Any]]) -> Callable[[], str]:
    """The front end the navigation service says this computer opens, read on each request (a switch in
    Settings takes effect on the next page)."""
    return lambda: str(frontend().get("frontend", ""))
