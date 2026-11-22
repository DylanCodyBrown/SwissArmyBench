"""What belongs to the open project, and bringing things into it (services/project_scope.py), for the
Workbench's Notebooks, Scripts and Apps pages, the import dialog and the agent (the golden rule).

GET  /project/documents       ?kind=notebook|script|app: the open project's documents
GET  /project/tree            ?page=notebooks|scripts: the explorer's groups (a .py by module, its outline)
POST /project/module-outline  {"text"}: a module's outline as typed
POST /project/import/sources  {"from": a project's folder, a file, or "computer"}: what it offers
POST /project/import          {"from", "documents"?, "connections"?, "blades"?}: copies into the project
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, read_json, with_body
from swissarmybench.services.project_scope import ProjectScope


def routes(scope: ProjectScope) -> list[BaseRoute]:
    async def documents(request: Request) -> Response:
        return json_response(scope.documents(request.query_params.get("kind") or None))

    async def tree(request: Request) -> Response:
        return json_response(scope.tree(request.query_params.get("page")))

    async def outline(request: Request) -> Response:
        return json_response(scope.outline(await read_json(request)))

    async def sources(request: Request) -> Response:
        return json_response(await scope.sources(await read_json(request)))

    return [
        Route("/project/documents", documents, methods=["GET"]),
        Route("/project/tree", tree, methods=["GET"]),
        Route("/project/module-outline", outline, methods=["POST"]),
        Route("/project/import/sources", sources, methods=["POST"]),
        Route("/project/import", with_body(scope.import_), methods=["POST"]),
    ]
