"""The checks every request goes through before routing (plan section 6, rules 1 and 2).

Think of LocalOnlyGuard as ASP.NET middleware registered ahead of routing: it sees the raw
request and either short-circuits with a status code or passes it on. Two checks, in order:

1. Host and Origin -> 403. A web page open in the user's browser can try to call
   http://127.0.0.1:<port>. Checking Host defeats DNS rebinding (an attacker's domain that
   resolves to 127.0.0.1 still sends its own name as Host). Checking Origin stops a page on
   another site from calling us. A request with NO Origin header is allowed: browsers send
   Origin on cross-site requests and on every WebSocket upgrade, while non-browser clients
   such as the push client never send it. Those still face the token check.
2. Token -> 401. `Authorization: Bearer <token>`, compared in constant time. A browser cannot
   set headers on a WebSocket, so the grid page sends the token as a WebSocket subprotocol
   instead (`new WebSocket(url, ["swissarmybench", token])`); that keeps it out of the URL and
   so out of the server's access log.
3. Or the page's cookie (the owner's call, 2026-11-16: the user never sees or handles the token, and
   a bookmark works). A page opened with the token posts it once to /session, which answers with a
   cookie `sab_<port>`: HttpOnly (the page's script cannot read it), SameSite=Strict (the browser
   sends it on no request another site starts), Path=/, no Secure (plain http on 127.0.0.1). Its
   value is not the token but a separate random secret made at each start and kept in memory only:
   a restart ends it, and the page then needs the token again, which `start`, `open` and the tray
   give. The cookie counts only with the Host and Origin checks above, and on an unsafe method
   (POST, PUT, PATCH, DELETE) only with our own Origin header present (defence in depth beside
   SameSite). The websocket takes it too. The agent, the push client and VS Code keep the Bearer
   token from the connection file.

A page asked for in the browser (GET, Accept: text/html) with no token and no valid cookie gets a
plain page that says how to open the app (its tray icon, `swissarmybench open`), not the 401 text.

A notebook's live Streamlit pages (/streamlit/live/<app>-<secret>/..., server/streamlit_proxy.py)
skip the token check too, for any method and for their websocket: a frame's address cannot carry a
header, so the path carries that app's own secret instead (random, made when the app is opened, never
the server's token), which the route checks. Those frames are sandboxed without this server's origin,
so their requests say `Origin: null`: allowed on these paths only. Host is still checked.

Deliberate exception: GET requests for the grid page shell (/g/...) and its static files
(/static/...) skip the token check. They hold no data, only the page and the vendored grid
library. The token reaches the page in the URL fragment (#token=...), which browsers never
send to the server, and the page's script attaches it to every data request. Host and Origin
are still checked on these paths.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

from starlette.datastructures import Headers
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket

from swissarmybench.domain.lifecycle import from_a_page

WEBSOCKET_SUBPROTOCOL: str = "swissarmybench"
# What a client from before the rename offers (SwissArmyGrid's): still answered, for one release.
OLD_WEBSOCKET_SUBPROTOCOL: str = "swissarmygrid"

# The page shell and its files: prefixes for /g/<id> and /static/..., and the exact paths of the
# workspace, catalog and workbench pages (a prefix would also let "/workspaceanything" skip the token check).
_PUBLIC_PREFIXES: tuple[str, ...] = ("/g/", "/static/")
_PUBLIC_PATHS: frozenset[str] = frozenset({"/", "/workspace", "/catalog", "/workbench"})

# The plain page for a browser that asks with no token and no valid cookie (a bookmark after a restart).
SIGNED_OUT_PAGE: str = (
    "<!doctype html><html><head><meta charset='utf-8'><title>Swiss Army Bench</title>"
    "<style>body{font:15px system-ui,sans-serif;margin:48px;color:#1c2228;background:#eef1f4}"
    "@media(prefers-color-scheme:dark){body{color:#e6e9ec;background:#1c2228}}code{font-size:14px}</style>"
    "</head><body><p>Open Swiss Army Bench from its tray icon, or run <code>swissarmybench open</code>.</p>"
    "</body></html>"
)
UNSAFE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _who(path: str) -> str:
    """Who a request with the token likely is, in words (the lifecycle's last client)."""
    if path.startswith("/processes"):
        return "a Python session"
    if path.startswith(("/workbench/kernels", "/connections/sql/")):
        return "a Workbench kernel"
    return "a client"


def cookie_name(port: int) -> str:
    """The page's cookie, named for the port: cookies are shared by every port of a host."""
    return f"sab_{port}"


_MESSAGES: dict[int, str] = {
    401: "Missing or wrong token. Clients read it from the server's connection file.",
    403: "Refused: only this computer's own grid pages and clients may call it.",
}


class LocalOnlyGuard:
    """ASGI middleware enforcing the Host, Origin and token checks."""

    def __init__(
        self,
        app: ASGIApp,
        port: int,
        token: str,
        session: str | None = None,
        secret_paths: tuple[str, ...] = (),
        activity: Callable[[str, str, bool, bool], None] | None = None,
    ) -> None:
        self._app = app
        # The server's life (services/lifecycle.py): each request let in, (path, who, by token, started).
        self._activity = activity
        # Live pages whose path carries their own secret (an extension's: Streamlit's, a dev server's).
        self._secret_paths: tuple[str, ...] = tuple(secret_paths)
        self._token: bytes = token.encode("ascii")
        # The page's cookie value: a secret of this start's own (None: no cookie is accepted).
        self._session: bytes | None = session.encode("ascii") if session else None
        self._cookie = cookie_name(port)
        self._allowed_hosts: frozenset[str] = frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})
        self._allowed_origins: frozenset[str] = frozenset(f"http://{host}" for host in self._allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Lifespan events (startup and shutdown) are not requests.
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        status: int | None = self._check(scope)
        if status is None and self._activity is not None and scope["type"] == "http":
            headers = Headers(scope=scope)
            # A page's own request is not a client's, though it carries the token too (domain/lifecycle.py).
            by_token = self._has_token(scope, headers) and not from_a_page(headers.get("sec-fetch-site"))
            path: str = scope["path"]
            who = "the agent" if headers.get("x-actor") == "agent" else _who(path)
            self._activity(path, who, by_token, True)
            try:
                await self._app(scope, receive, send)
            finally:
                self._activity(path, who, by_token, False)
        elif status is None:
            await self._app(scope, receive, send)
        elif scope["type"] == "websocket":
            # Closing before accepting makes the server answer the upgrade with HTTP 403.
            await WebSocket(scope, receive, send).close(code=1008)
        elif (
            status == 401
            and scope["method"] == "GET"
            and "text/html" in Headers(scope=scope).get("accept", "")
        ):
            await HTMLResponse(SIGNED_OUT_PAGE, status_code=401)(scope, receive, send)
        else:
            await PlainTextResponse(_MESSAGES[status], status_code=status)(scope, receive, send)

    def _check(self, scope: Scope) -> int | None:
        """Return the refusal status code, or None when the request may proceed."""
        headers: Headers = Headers(scope=scope)
        if headers.get("host") not in self._allowed_hosts:
            return 403
        origin: str | None = headers.get("origin")
        path: str = scope["path"]
        if any(path.startswith(p) and len(path) > len(p) for p in self._secret_paths):
            # A sandboxed frame has no origin of its own to name.
            return None if origin in (None, "null") or origin in self._allowed_origins else 403
        if origin is not None and origin not in self._allowed_origins:
            return 403
        public = path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES)
        if scope["type"] == "http" and scope["method"] == "GET" and public:
            return None
        if self._has_token(scope, headers):
            return None
        if self._has_cookie(headers):
            # The cookie on an unsafe method: only with our own Origin (a browser sends it on these).
            unsafe = scope["type"] == "http" and scope["method"] in UNSAFE_METHODS
            return 403 if unsafe and origin not in self._allowed_origins else None
        return 401

    def _has_cookie(self, headers: Headers) -> bool:
        if self._session is None:
            return False
        for part in headers.get("cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == self._cookie and secrets.compare_digest(value.encode("latin-1"), self._session):
                return True
        return False

    def _has_token(self, scope: Scope, headers: Headers) -> bool:
        # Header values arrive decoded as latin-1, so re-encoding them is lossless.
        presented: bytes = headers.get("authorization", "").encode("latin-1")
        if secrets.compare_digest(presented, b"Bearer " + self._token):
            return True
        if scope["type"] == "websocket":
            offered: list[str] = [
                part.strip() for part in headers.get("sec-websocket-protocol", "").split(",")
            ]
            return any(secrets.compare_digest(part.encode("latin-1"), self._token) for part in offered)
        return False
