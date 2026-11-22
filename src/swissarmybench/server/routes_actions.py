"""Every API's actions through api_adapter (services/actions.py), for the page and the agent alike.

GET  /actions?api=            every API's actions (the library's; `local`: the project's sandbox API)
GET  /actions/{api}/{action}  one action: its inputs, its learned contract, its kept shape, the last call
POST /actions/run             {"api", "action", "inputs"?, "required"?}: one call, its one envelope (a write
                              by the agent waits for the user's Allow)
POST /actions/discover        {"api"}: the read-only probe, on the user's Allow (asked once per API and
                              remembered with it)
POST /actions/allow           {"api", "allow": false}: Discover's Allow taken back
POST /actions/offer           {"api", "action", "from", "to", "take"}: a rename offered once, answered
POST /actions/build           {"api", "action", "as": cell | function | widget, "path"?, "insert"?, ...}: a
                              cell into the project's data.ipynb, a function into the script `path` names, a
                              widget on a canvas page
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json
from swissarmybench.services.actions import Actions


def routes(actions: Actions) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        api = request.query_params.get("api")
        return json_response(await actions.list({"api": api} if api else {}, actor(request)))

    async def describe(request: Request) -> Response:
        params = request.path_params
        return json_response(
            await actions.describe(str(params["api"]), str(params["action"]), actor(request))
        )

    async def run(request: Request) -> Response:
        return json_response(await actions.run(await read_json(request), actor(request)))

    async def discover(request: Request) -> Response:
        return json_response(await actions.discover(await read_json(request), actor(request)))

    async def allow(request: Request) -> Response:
        return json_response(await actions.allow(await read_json(request), actor(request)))

    async def offer(request: Request) -> Response:
        return json_response(await actions.answer_offer(await read_json(request), actor(request)))

    async def build(request: Request) -> Response:
        return json_response(await actions.build(await read_json(request), actor(request)))

    return [
        Route("/actions", listing, methods=["GET"]),
        Route("/actions/run", run, methods=["POST"]),
        Route("/actions/discover", discover, methods=["POST"]),
        Route("/actions/allow", allow, methods=["POST"]),
        Route("/actions/offer", offer, methods=["POST"]),
        Route("/actions/build", build, methods=["POST"]),
        Route("/actions/{api}/{action}", describe, methods=["GET"]),
    ]
