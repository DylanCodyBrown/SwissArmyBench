"""The old pages' addresses (the classic front end's, gone 2026-11-23; the owner: "we can swap over to full
Blazer do not keep both in sync in parallel"): /workspace, /g/<grid>, /notebooks, /scripts, the Canvas, the
Widgets window and the analyzer each answer with their Blazor page, their words kept. A bookmark, the desktop
app, a pushed grid's address and an agent's window all land on the Blazor pages. The #token stays with the
browser."""

from __future__ import annotations

from urllib.parse import parse_qsl, quote

from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from swissarmybench.domain import navigation


class OldAddresses:
    """ASGI middleware: an old page's GET answers 302 to its Blazor page; anything else passes through."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope.get("method") in ("GET", "HEAD")
            and navigation.is_old_page(str(scope.get("path", "")))
        ):
            query = dict(parse_qsl(scope.get("query_string", b"").decode("latin-1")))
            address = blazor_address(scope["path"], query)
            await RedirectResponse(address, status_code=302)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def blazor_address(path: str, query: dict[str, str]) -> str:
    """The Blazor page's address for an old page's (navigation.blazor_page, its words encoded)."""
    page, words = navigation.blazor_page(path, query)
    text = "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in words.items())
    return f"/blazor/{page}" + (f"?{text}" if text else "")
