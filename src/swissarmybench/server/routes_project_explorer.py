"""The Project Explorer (services/project_explorer.py), the home page, for the page and the agent (the golden
rule); Show in folder and Delete are the user's own (403 for the agent).

GET  /projects/explorer     ?by=&descending=&type=&q=: every project as a card, sorted and filtered; the types
GET  /projects/types        the project types, each explained for beginners
POST /projects/sort         {"by", "descending"?} | {"order": [folders]} | {"move": a folder, "by": -1 or 1}
POST /projects/explained    {"explained": true}: the types' explanations put away (remembered)
POST /projects/folder       {"folder"} | {"default": true}: Settings' Projects folder (the agent's on Allow)
POST /projects/rename       {"path", "name"}: a project's folder renamed
POST /projects/remove       {"path"}: off the list (no file touched)
POST /projects/locate       {"path", "to"}: a moved project found again
POST /projects/show         {"path"}: its folder in the system's file manager (the user's click only)
POST /projects/delete       {"path", "confirm": its name}: its folder to the system's trash (the user's only)
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.project_explorer import ProjectExplorer


def routes(explorer: ProjectExplorer) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    async def listing(request: Request) -> Response:
        return json_response(await explorer.list(dict(request.query_params)))

    async def types(request: Request) -> Response:
        return json_response(explorer.types())

    def posted(use: Any, with_actor: bool = True) -> Any:
        async def handler(request: Request) -> Response:
            body = await read_json(request)
            done = await (use(body, actor(request)) if with_actor else use(body))
            return json_response(done)

        return safely(handler)

    return [
        Route("/projects/explorer", safely(listing), methods=["GET"]),
        Route("/projects/types", safely(types), methods=["GET"]),
        Route("/projects/sort", posted(explorer.sort), methods=["POST"]),
        Route("/projects/explained", posted(explorer.explained, False), methods=["POST"]),
        Route("/projects/folder", posted(explorer.set_folder), methods=["POST"]),
        Route("/projects/rename", posted(explorer.rename), methods=["POST"]),
        Route("/projects/remove", posted(explorer.remove), methods=["POST"]),
        Route("/projects/locate", posted(explorer.locate), methods=["POST"]),
        Route("/projects/show", posted(explorer.show), methods=["POST"]),
        Route("/projects/delete", posted(explorer.delete), methods=["POST"]),
    ]
