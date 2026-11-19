"""The Desktop extension's HTTP door (services/desktop.py). Every route serves the agent too.

GET    /desktop          the shell: running, its windows (kind, title, page)   desktop_status
POST   /desktop/open     {page: home | workbench | blades}: opened in the shell                desktop_open
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench.services.desktop import Desktop


def routes(desktop: Desktop) -> list[BaseRoute]:
    async def status(request: Request) -> Response:
        return json_response(await desktop.status())

    async def open_page(request: Request) -> Response:
        return json_response(await desktop.open(await read_json(request), actor(request)))

    return [
        Route("/desktop", safely(status)),
        Route("/desktop/open", safely(open_page), methods=["POST"]),
    ]
