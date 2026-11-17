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

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.file_dialogs import FileDialogs


def routes(dialogs: FileDialogs) -> list[BaseRoute]:
    async def status(request: Request) -> Response:
        try:
            return json_response(await dialogs.status())
        except Exception as error:
            return error_response(error)

    async def choose(request: Request) -> Response:
        try:
            return json_response(await dialogs.choose(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    async def recent(request: Request) -> Response:
        try:
            return json_response(dialogs.remember(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/dialogs", status, methods=["GET"]),
        Route("/dialogs/choose", choose, methods=["POST"]),
        Route("/dialogs/recent", recent, methods=["POST"]),
    ]
