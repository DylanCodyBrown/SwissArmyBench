"""The project scaffold's door (services/scaffold.py): its made files' state, a refresh, Take the new one.

GET   /project/scaffold          each made file: same, to write, to remove, edited by hand    project_scaffold
POST  /project/scaffold          every made file brought up to date {"take"?: [file]}         project_scaffold
POST  /project/scaffold/take     {"file"}: the app's text over a hand edit                   project_scaffold
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, with_body
from swissarmybench.services.scaffold import Scaffold


def routes(scaffold: Scaffold) -> list[BaseRoute]:
    async def status(request: Request) -> Response:
        return json_response(await scaffold.status())

    return [
        Route("/project/scaffold", status),
        Route("/project/scaffold", with_body(scaffold.refresh), methods=["POST"]),
        Route("/project/scaffold/take", with_body(scaffold.take), methods=["POST"]),
    ]
