"""The Extensions page (services/extensions.py), for the page and the agent.

GET    /extensions          the library's folder extensions, and each built-in feature with a panel of its own
POST   /extensions/install  {"id"}: a folder's missing packages (the agent waits for Allow), then Load again
                            (no restart); a built-in feature's id: one sentence, it is built in
POST   /extensions/remove   {"id", "confirmed"?}: a folder's to the trash (the user's asks first); a built-in
                            feature's id: one sentence, it cannot be removed
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
