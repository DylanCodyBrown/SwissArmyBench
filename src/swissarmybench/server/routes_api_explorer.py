"""The APIs page (services/api_explorer.py), for the page and the agent alike (the golden rule).

GET  /apis                               the library's APIs as cards, and older API connections
GET  /apis/search?q=                     every API's operations matching the words
GET  /apis/{name}?operation=             an API's operations (inputs, outputs, examples), its schemas
POST /apis/{name}/calls/{operation}      {"inputs", "body"?}: the call sent, its answer opened in Structures
PUT  /apis/{name}/calls/{operation}      the authored call saved as its web call blade (Return as table...)
POST /apis/{name}/calls/{operation}/write  Write rows with this call: the dry run (the default), or sent:
                                         the results as a grid and a structure; PUT saves it as a blade
POST /apis/{name}/refresh                its source read again: what changed (nothing written)
POST /apis/{name}/refresh/apply          what Refresh showed, written
PUT  /apis/{name}/check                  {"on"}: check for changes when the page opens
PUT  /apis/{name}/name                   {"name"}: renamed
POST /apis/{name}/delete                 {"confirm"?}: the code that uses it; with confirm, deleted (the
                                         agent's waits for the user's Allow)
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.api_explorer import Explorer


def routes(explorer: Explorer) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    def name(request: Request) -> str:
        return str(request.path_params["name"])

    async def listing(request: Request) -> Response:
        return json_response(explorer.listing())

    async def search(request: Request) -> Response:
        return json_response(explorer.search(request.query_params.get("q", "")))

    async def describe(request: Request) -> Response:
        return json_response(explorer.describe(name(request), request.query_params.get("operation")))

    async def send(request: Request) -> Response:
        body = await read_json(request)
        return json_response(
            await explorer.send(name(request), request.path_params["op"], body, actor(request))
        )

    async def save_call(request: Request) -> Response:
        body = await read_json(request)
        answer = await explorer.save_call(name(request), request.path_params["op"], body, actor(request))
        return json_response(answer)

    async def write(request: Request) -> Response:
        body = await read_json(request)
        return json_response(
            await explorer.write_rows(name(request), request.path_params["op"], body, actor(request))
        )

    async def save_write(request: Request) -> Response:
        body = await read_json(request)
        return json_response(
            await explorer.save_write(name(request), request.path_params["op"], body, actor(request))
        )

    async def refresh(request: Request) -> Response:
        return json_response(await explorer.refresh(name(request), actor(request)))

    async def apply(request: Request) -> Response:
        return json_response(await explorer.apply_refresh(name(request), actor(request)))

    async def check(request: Request) -> Response:
        body = await read_json(request)
        return json_response(await explorer.set_check(name(request), bool((body or {}).get("on"))))

    async def rename(request: Request) -> Response:
        body = await read_json(request)
        return json_response(
            await explorer.rename(name(request), str((body or {}).get("name") or ""), actor(request))
        )

    async def delete(request: Request) -> Response:
        return json_response(await explorer.delete(name(request), await read_json(request), actor(request)))

    return [
        Route("/apis", safely(listing), methods=["GET"]),
        Route("/apis/search", safely(search), methods=["GET"]),
        Route("/apis/{name}", safely(describe), methods=["GET"]),
        Route("/apis/{name}/calls/{op}", safely(send), methods=["POST"]),
        Route("/apis/{name}/calls/{op}", safely(save_call), methods=["PUT"]),
        Route("/apis/{name}/calls/{op}/write", safely(write), methods=["POST"]),
        Route("/apis/{name}/calls/{op}/write", safely(save_write), methods=["PUT"]),
        Route("/apis/{name}/refresh", safely(refresh), methods=["POST"]),
        Route("/apis/{name}/refresh/apply", safely(apply), methods=["POST"]),
        Route("/apis/{name}/check", safely(check), methods=["PUT"]),
        Route("/apis/{name}/name", safely(rename), methods=["PUT"]),
        Route("/apis/{name}/delete", safely(delete), methods=["POST"]),
    ]
