"""The system's own file dialog (services/file_dialogs.py): the user's click only (403 for the agent, which
passes paths to every command directly).

GET    /dialogs           {"system": bool, "tool", "reason"?}: whether this computer's dialogs open
POST   /dialogs/choose    {mode, title, start?, suffixes?, name?, kind?}: {"path"} | {"cancelled": true} |
                          {"busy": true} (one is open) | {"unavailable": why} (the page's own picker then)
POST   /dialogs/recent    {kind, path, mode}: a pick in the page's own picker, its folder remembered
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely, with_body
from swissarmybench.services.file_dialogs import FileDialogs


def routes(dialogs: FileDialogs) -> list[BaseRoute]:
    async def status(request: Request) -> Response:
        return json_response(await dialogs.status())

    async def recent(request: Request) -> Response:
        return json_response(dialogs.remember(await read_json(request), actor(request)))

    return [
        Route("/dialogs", safely(status), methods=["GET"]),
        Route("/dialogs/choose", with_body(dialogs.choose), methods=["POST"]),
        Route("/dialogs/recent", safely(recent), methods=["POST"]),
    ]
