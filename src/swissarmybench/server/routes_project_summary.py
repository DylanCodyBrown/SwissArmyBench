"""Home's summary of the open project (services/project_summary.py), for the Home page and the agent
(the golden rule: `project_summary`).

GET  /project/summary   {"project": None} with none open; else the project, its Python, tables, documents, the
                        connections it uses, the Session's last entries, its deliverable and the counts
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response
from swissarmybench.services.project_summary import ProjectSummary, Sources


def routes(sources: Sources) -> list[BaseRoute]:
    summary = ProjectSummary(sources)  # built from the services it reads, by their names (Services)

    async def read(request: Request) -> Response:
        return json_response(summary.summary())

    return [Route("/project/summary", read, methods=["GET"])]
