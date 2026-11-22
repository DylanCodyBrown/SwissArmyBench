"""The Desktop extension's HTTP door (services/desktop.py). Every route serves the agent too.

GET    /desktop          the shell: running, its windows (kind, title, page)   desktop_status
POST   /desktop/open     {page: home | workbench | blades}: opened in the shell                desktop_open
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, with_body
from swissarmybench.services.desktop import Desktop


def routes(desktop: Desktop) -> list[BaseRoute]:
    async def status(request: Request) -> Response:
        return json_response(await desktop.status())

    return [
        Route("/desktop", status),
        Route("/desktop/open", with_body(desktop.open), methods=["POST"]),
    ]
