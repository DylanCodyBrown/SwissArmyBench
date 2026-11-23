"""What the open project needs installed, found as it opens and installed at once (services/project_python.py
ProjectInstalls; the owner, 2026-11-23). The agent's tool is `project_installs`.

GET   /project/installs          the pass's state: checking, installing, done, failed or none; each package,
                                 why it is needed and its status; the words the bar says
POST  /project/installs/check    look again (installs nothing)
POST  /project/installs/run      install what the project lacks, in one install (Try again; agent: on Allow)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, with_body
from swissarmybench.services.project_python import ProjectInstalls


def routes(installs: ProjectInstalls) -> list[BaseRoute]:
    async def state(request: Request) -> Response:
        return json_response(installs.state())

    return [
        Route("/project/installs", state, methods=["GET"]),
        Route("/project/installs/check", with_body(installs.check), methods=["POST"]),
        Route("/project/installs/run", with_body(installs.run), methods=["POST"]),
    ]
