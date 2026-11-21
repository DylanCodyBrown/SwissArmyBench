"""Projects (services/projects.py), for the Workbench window and the agent (the golden rule).

POST /projects          {"folder", "name", "app"?, "notebooks"?, "tables"?}: a new project
POST /projects/open     {"folder"}: the project's files, for the Workbench's tabs
POST /projects/export-data  {"folder"}: data.py written again from the project's data.ipynb
POST /projects/dictionary   {"tables": [{"name", "source"}], "descriptions"}: the data dictionary's tables
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely, with_body
from swissarmybench.services.projects import Projects


def routes(projects: Projects) -> list[BaseRoute]:
    async def open_project(request: Request) -> Response:
        return json_response(projects.open(await read_json(request), actor(request)))

    async def data_dictionary(request: Request) -> Response:
        return json_response(await projects.dictionary(await read_json(request)))

    return [
        Route("/projects/dictionary", safely(data_dictionary), methods=["POST"]),
        Route("/projects", with_body(projects.create), methods=["POST"]),
        Route("/projects/open", safely(open_project), methods=["POST"]),
        Route("/projects/export-data", with_body(projects.export_data), methods=["POST"]),
    ]
