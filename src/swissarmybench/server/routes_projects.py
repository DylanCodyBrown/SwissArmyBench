"""Projects (services/projects.py), for the Workbench window and the agent (the golden rule).

POST /projects          {"folder", "name", "app"?, "notebooks"?, "tables"?}: a new project
POST /projects/open     {"folder"}: the project's files, for the Workbench's tabs
POST /projects/export-data  {"folder"}: data.py written again from the project's data.ipynb
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmygrid.server.http import actor, error_response, json_response, read_json
from swissarmygrid.services.projects import Projects


def routes(projects: Projects) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    async def create(request: Request) -> Response:
        return json_response(await projects.create(await read_json(request), actor(request)))

    async def open_project(request: Request) -> Response:
        return json_response(projects.open(await read_json(request), actor(request)))

    async def export_data(request: Request) -> Response:
        return json_response(await projects.export_data(await read_json(request), actor(request)))

    return [
        Route("/projects", safely(create), methods=["POST"]),
        Route("/projects/open", safely(open_project), methods=["POST"]),
        Route("/projects/export-data", safely(export_data), methods=["POST"]),
    ]
