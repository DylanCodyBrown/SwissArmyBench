"""Each connection's slots and the Queries window (services/connection_slots.py), for the pages, the agent
(connections_slots, connections_queries, connections_cancel_query, connections_set_limits) and the Workbench
kernels' leased slots.

GET    /connections/slots                   each connection's counts and limits (the cards): names, counts
GET    /connections/queries?connection=     the running and waiting queries and the finished ones (no SQL)
GET    /connections/queries/{id}/sql        one query's SQL, as written and formatted: the user's only (403)
POST   /connections/queries/{id}/cancel     a waiting one leaves the line, a running one is stopped
POST   /connections/queries/cancel-mine     every query this page asked for (X-Sab-Client): its Cancel
POST   /connections/queries/clear           the finished list emptied
GET    /connections/{name}/limits           its limits and the defaults
PUT    /connections/{name}/limits           {"total", "agent", "wait"}: written into its file's [queries]
POST   /connections/slots/acquire           a kernel's slot (X-Kernel): {"connection", "kind", "sql"?}
POST   /connections/slots/{id}/renew        its lease renewed; how it stands (waiting: its place)
POST   /connections/slots/{id}/release      {"outcome", "rows"?, "reason"?}: given back

CallerAtTheDoor sets who each request's connection calls are for (services/connection_slots.py CURRENT):
the agent (X-Actor: agent), a page (X-Sab-Client, its Cancel's key), a Workbench kernel (X-Kernel).
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from swissarmybench.domain import connection_slots as rules
from swissarmybench.server.http import actor, error_response, json_response, read_json, refusal
from swissarmybench.services.connection_slots import CURRENT, Caller, ConnectionSlots


def _short(value: str | None, most: int = 64) -> str:
    text = (value or "").strip()
    return text if len(text) <= most and text.isprintable() else ""


class CallerAtTheDoor:
    """ASGI middleware: each request's caller for the connection slots, from its headers."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        kernel = _short(headers.get("x-kernel"), 32)
        if headers.get("x-actor") == "agent":
            caller = Caller(rules.AGENT, "The agent", kernel=kernel)
        else:
            caller = Caller(client=_short(headers.get("x-sab-client"), 40), kernel=kernel)
        token = CURRENT.set(caller)
        try:
            await self._app(scope, receive, send)
        finally:
            CURRENT.reset(token)


def routes(slots: ConnectionSlots, names: object) -> list[BaseRoute]:
    """`names()`: every saved connection's name (the cards' counts cover each)."""

    def connection_names() -> list[str]:
        found = names() if callable(names) else []
        return [str(n) for n in found] if isinstance(found, list) else []

    async def status(request: Request) -> Response:
        return json_response(slots.status(connection_names()))

    async def queries(request: Request) -> Response:
        return json_response(slots.queries(request.query_params.get("connection") or None))

    async def sql(request: Request) -> Response:
        if actor(request) == "agent":
            return refusal("A query's SQL is shown to the user only.", 403)
        try:
            return json_response(slots.sql(request.path_params["id"]))
        except Exception as error:
            return error_response(error)

    async def cancel(request: Request) -> Response:
        try:
            return json_response(await slots.cancel(request.path_params["id"], actor(request)))
        except Exception as error:
            return error_response(error)

    async def cancel_mine(request: Request) -> Response:
        client = _short(request.headers.get("x-sab-client"), 40)
        return json_response(await slots.cancel_client(client, actor(request)))

    async def clear(request: Request) -> Response:
        return json_response(slots.clear_finished())

    async def limits(request: Request) -> Response:
        name = request.path_params["name"]
        try:
            if request.method == "PUT":
                return json_response(slots.set_limits(name, await read_json(request), actor(request)))
            return json_response(slots.limits(name))
        except rules.LimitsError as error:
            return refusal(str(error), 400, where=name)
        except Exception as error:
            return error_response(error)

    async def acquire(request: Request) -> Response:
        try:
            kernel = _short(request.headers.get("x-kernel"), 32)
            return json_response(slots.acquire(await read_json(request), kernel))
        except Exception as error:
            return error_response(error)

    async def renew(request: Request) -> Response:
        return json_response(slots.renew(request.path_params["id"]))

    async def release(request: Request) -> Response:
        try:
            return json_response(slots.release(request.path_params["id"], await read_json(request)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/connections/slots", status),
        Route("/connections/slots/acquire", acquire, methods=["POST"]),
        Route("/connections/slots/{id}/renew", renew, methods=["POST"]),
        Route("/connections/slots/{id}/release", release, methods=["POST"]),
        Route("/connections/queries", queries),
        Route("/connections/queries/cancel-mine", cancel_mine, methods=["POST"]),
        Route("/connections/queries/clear", clear, methods=["POST"]),
        Route("/connections/queries/{id}/sql", sql),
        Route("/connections/queries/{id}/cancel", cancel, methods=["POST"]),
        Route("/connections/{name}/limits", limits, methods=["GET", "PUT"]),
    ]
