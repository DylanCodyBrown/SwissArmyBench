"""The Project Explorer (services/project_explorer.py), the home page, for the page and the agent (the golden
rule); Show in folder and Delete are the user's own (403 for the agent).

GET  /projects/explorer     ?by=&descending=&type=&q=&where=: every project as a card (Local or Shared),
                            sorted and filtered; the types; both projects folders
GET  /projects/folder       the Local and Shared projects folders
GET  /projects/types        the project types, each explained for beginners
POST /projects/sort         {"by", "descending"?} | {"order": [folders]} | {"move": a folder, "by": -1 or 1}
POST /projects/explained    {"explained": true}: the types' explanations put away (remembered)
POST /projects/folder       {"which"?: "local" | "shared", "folder"} | {"default": true}: Settings' Local and
                            Shared projects folders (the agent's on Allow)
POST /projects/share        {"path", "name"?}: a local project copied into the shared folder (no rows), opened
                            (the agent's on Allow)
POST /projects/copy-local   {"path", "name"?}: Make a local copy of a shared project (no rows), opened
POST /projects/rename       {"path", "name"}: a project's folder renamed
POST /projects/remove       {"path"}: off the list (no file touched)
POST /projects/locate       {"path", "to"}: a moved project found again
POST /projects/show         {"path"}: its folder in the system's file manager (the user's click only)
POST /projects/delete       {"path", "confirm": its name}: its folder to the system's trash (the user's only)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, read_json, safely, with_body
from swissarmybench.services.project_explorer import ProjectExplorer


def routes(explorer: ProjectExplorer) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(await explorer.list(dict(request.query_params)))

    async def folders(request: Request) -> Response:
        return json_response(explorer.folders())

    async def types(request: Request) -> Response:
        return json_response(explorer.types())

    async def explained(request: Request) -> Response:
        return json_response(await explorer.explained(await read_json(request)))

    return [
        Route("/projects/explorer", safely(listing), methods=["GET"]),
        Route("/projects/types", safely(types), methods=["GET"]),
        Route("/projects/sort", with_body(explorer.sort), methods=["POST"]),
        Route("/projects/explained", safely(explained), methods=["POST"]),
        Route("/projects/folder", with_body(explorer.set_folder), methods=["POST"]),
        Route("/projects/folder", safely(folders), methods=["GET"]),
        Route("/projects/share", with_body(explorer.share), methods=["POST"]),
        Route("/projects/copy-local", with_body(explorer.copy_local), methods=["POST"]),
        Route("/projects/rename", with_body(explorer.rename), methods=["POST"]),
        Route("/projects/remove", with_body(explorer.remove), methods=["POST"]),
        Route("/projects/locate", with_body(explorer.locate), methods=["POST"]),
        Route("/projects/show", with_body(explorer.show), methods=["POST"]),
        Route("/projects/delete", with_body(explorer.delete), methods=["POST"]),
    ]
