"""The project's outline (services/project_outline.py), for the home page, the Workbench and the agent
(the golden rule: `project_outline`).

GET  /project/outline   the open project's outline as markdown (text/markdown), written nowhere
POST /project/outline   ARCHITECTURE.md written at the project folder's top (only when its bytes change):
                        {"file", "path", "written", "text"}
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import with_body
from swissarmybench.services.project_outline import ProjectOutline


def routes(outline: ProjectOutline) -> list[BaseRoute]:
    async def read(request: Request) -> Response:
        text = await outline.build()
        return Response(text, media_type="text/markdown; charset=utf-8")

    return [
        Route("/project/outline", read, methods=["GET"]),
        Route("/project/outline", with_body(outline.write), methods=["POST"]),
    ]
