"""The Extensions page (services/extensions.py), for the page and the agent.

GET    /extensions          every extension: preinstalled, available, installed, coming; folders too
POST   /extensions/install  {"id"}: Install (the app restarts; the agent waits for Allow); a folder's: its
                            packages, then Load again (no restart)
POST   /extensions/remove   {"id", "confirmed"?}: Remove (the user's asks first); a folder's to the trash
POST   /extensions/new      {"id", "name"?, "project_type"?}: New extension, a folder in the library
POST   /extensions/show     {"id"}: Show its folder (the user's click only: 403 for the agent)

The agent's: extensions_list, _install, _remove, _new (Show its folder has none).
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, with_body
from swissarmybench.services.extensions import Extensions


def routes(extensions: Extensions) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(extensions.state())

    async def show(body: Any, who: str) -> Any:
        return extensions.show(body, who)

    return [
        Route("/extensions", listing),
        Route("/extensions/install", with_body(extensions.install), methods=["POST"]),
        Route("/extensions/remove", with_body(extensions.remove), methods=["POST"]),
        Route("/extensions/new", with_body(extensions.new), methods=["POST"]),
        Route("/extensions/show", with_body(show), methods=["POST"]),
    ]
