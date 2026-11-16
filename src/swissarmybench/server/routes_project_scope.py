"""What belongs to the open project, and bringing things into it (services/project_scope.py), for the
Workbench's Notebooks, Scripts and Apps pages, the import dialog and the agent (the golden rule).

GET  /project/documents       ?kind=notebook|script|app: the open project's documents
POST /project/import/sources  {"from": a .sab, a project's folder, a file, or "computer"}: what it offers
POST /project/import          {"from", "documents"?, "connections"?, "blades"?}: copies into the project
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.project_scope import ProjectScope


def routes(scope: ProjectScope) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    async def documents(request: Request) -> Response:
        return json_response(scope.documents(request.query_params.get("kind") or None))

    async def sources(request: Request) -> Response:
        return json_response(await scope.sources(await read_json(request)))

    async def import_(request: Request) -> Response:
        return json_response(await scope.import_(await read_json(request), actor(request)))

    return [
        Route("/project/documents", safely(documents), methods=["GET"]),
        Route("/project/import/sources", safely(sources), methods=["POST"]),
        Route("/project/import", safely(import_), methods=["POST"]),
    ]
