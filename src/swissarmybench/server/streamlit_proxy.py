"""A notebook's Streamlit app, shown through this server (docs/ideas.md, "Streamlit cells").

The Streamlit process listens on 127.0.0.1 only, on a port of its own. The Workbench page may frame
nothing but this server (`frame-src 'self'`), and that policy stays as it is: the app's pages are
passed through here instead, under a path that carries the app's own secret:

    /streamlit/live/<app>-<secret>/...     Streamlit's pages, files and its websocket

Streamlit is started with that same path as its base path, so nothing in its pages is rewritten. The
secret is random, made when the app starts, and is not the server's token: a frame or a window's
address cannot carry a header, and the token never goes into an address. The guard still checks the
Host on every request, and lets these paths through without the token; the secret is checked here, in
constant time.

The frames are sandboxed without the app's origin (as an HTML cell's design is), so a Streamlit page
cannot read the Workbench's token or storage. A page in such a frame fetches its own files as another
origin would, so the answers carry `Access-Control-Allow-Origin: *`: only a caller that already holds
the secret gets an answer at all.
"""

from __future__ import annotations

import asyncio
import http.client
import secrets
from collections.abc import Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

PREFIX: str = "/streamlit/live/"
_TIMEOUT_SECONDS: float = 60.0
_MAX_BODY: int = 250_000_000  # an uploaded file (Streamlit's own limit is 200 MB)
_MAX_MESSAGE: int = 250_000_000
# Headers that describe one hop, not the answer (RFC 9110), and the ones set anew here.
_HOP: frozenset[str] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "host",
        "origin",
        "referer",
        "authorization",
    }
)
_ANSWER_DROP: frozenset[str] = _HOP | {"access-control-allow-origin", "server", "date"}

# (app id, secret) -> the port its Streamlit listens on, or None: no such app, or a wrong secret.
Lookup = Callable[[str], int | None]


def same(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode("utf-8", "replace"), b.encode("utf-8", "replace"))


def _fetch(
    port: int, method: str, target: str, headers: dict[str, str], body: bytes
) -> tuple[int, list[tuple[str, str]], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_TIMEOUT_SECONDS)
    try:
        connection.request(method, target, body=body or None, headers=headers)
        answer = connection.getresponse()
        return answer.status, answer.getheaders(), answer.read()
    finally:
        connection.close()


# A websocket message seen as it passes: (the key, "down" to the page or "up" from it, the message). The
# Performance Analyzer's (the Streamlit extension's): it keeps only a message's kind and size.
Tap = Callable[[str, str, bytes | str], None]


def routes(
    port_of: Lookup, prefix: str = PREFIX, what: str = "This Streamlit app", tap: Tap | None = None
) -> list[BaseRoute]:
    """`port_of("<app>-<secret>")` gives the Streamlit port to pass on to (None: refuse). Another live page
    served the same way (an extension's dev server, started with `prefix` as its base path) passes its own
    `prefix` and its words for `what` is not running. `tap`: told of each websocket message (its own work
    decides whether to keep anything)."""

    async def page(request: Request) -> Response:
        port = port_of(request.path_params["key"])
        if port is None:
            return Response(f"{what} is not running (run it again).", 404)
        if request.method == "OPTIONS":  # a sandboxed frame asks before an upload
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": request.headers.get(
                        "access-control-request-headers", "*"
                    ),
                    "Access-Control-Max-Age": "600",
                },
            )
        body = await request.body()
        if len(body) > _MAX_BODY:
            return Response("Too large.", 413)
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
        headers["Host"] = f"127.0.0.1:{port}"
        if "origin" in request.headers:
            headers["Origin"] = f"http://127.0.0.1:{port}"  # the live server's own check: its own address
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        try:
            status, got, data = await asyncio.to_thread(_fetch, port, request.method, target, headers, body)
        except OSError:
            return Response(f"{what} did not answer (it may still be starting).", 502)
        answer = Response(data, status_code=status)
        del answer.headers["content-length"]
        for name, value in got:
            if name.lower() not in _ANSWER_DROP:
                answer.headers.append(name, value)
        answer.headers["Content-Length"] = str(len(data))
        answer.headers["Access-Control-Allow-Origin"] = "*"
        answer.headers["Referrer-Policy"] = "no-referrer"  # the secret is in the address
        return answer

    async def socket(websocket: WebSocket) -> None:
        port = port_of(websocket.path_params["key"])
        if port is None:
            await websocket.close(code=1008)
            return
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed

        query = websocket.url.query
        target = f"ws://127.0.0.1:{port}{websocket.url.path}" + (f"?{query}" if query else "")
        offered: list[Any] = list(websocket.scope.get("subprotocols", []))
        try:
            upstream = await connect(
                target,
                subprotocols=offered or None,
                origin=f"http://127.0.0.1:{port}",  # type: ignore[arg-type]
                max_size=_MAX_MESSAGE,
                open_timeout=_TIMEOUT_SECONDS,
                proxy=None,
            )
        except Exception:
            await websocket.close(code=1011)
            return
        await websocket.accept(subprotocol=upstream.subprotocol)
        key = websocket.path_params["key"]

        def seen(direction: str, message: bytes | str) -> None:
            if tap is not None:
                try:
                    tap(key, direction, message)
                except Exception:  # noqa: S110 (the analyzer's trouble never stops the page)
                    pass

        async def down() -> None:
            try:
                async for message in upstream:
                    seen("down", message)
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)
            except ConnectionClosed:
                pass

        async def up() -> None:
            try:
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message.get("bytes") is not None:
                        seen("up", message["bytes"])
                        await upstream.send(message["bytes"])
                    elif message.get("text") is not None:
                        await upstream.send(message["text"])
            except (WebSocketDisconnect, ConnectionClosed, RuntimeError):
                pass

        tasks = [asyncio.create_task(down()), asyncio.create_task(up())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await upstream.close()
            try:
                await websocket.close()
            except (RuntimeError, WebSocketDisconnect):  # already closed by the page
                pass

    methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"]
    return [
        Route(prefix + "{key}", page, methods=methods),
        Route(prefix + "{key}/{rest:path}", page, methods=methods),
        WebSocketRoute(prefix + "{key}/{rest:path}", socket),
    ]
