"""The library (services/library.py), for Settings and the agent.

GET   /library           where it is, what is in it, what stays here, what never goes in       library_info
PUT   /library           {"folder": a whole path, or null: the default}: Settings' Library folder
                         (the agent's waits for the user's Allow)                          library_set_folder
POST  /library/notices   what the page says once (the move into the library), then gone (the page's own)
GET   /library/setup     Set up from the meta store: vaults, values, connections, shared projects
                         (?check=1: each vault checked again)                                library_setup
POST  /library/setup/move-to-vault  {"connection", "secret", "vault", "vault_secret"}: a keyring password
                         mapped to a vault's secret                              library_setup_move_to_vault
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.library import Library
from swissarmybench.services.library_setup import LibrarySetup


def routes(library: Library, setup: LibrarySetup) -> list[BaseRoute]:
    async def info(request: Request) -> Response:
        return json_response(library.info())

    async def set_folder(request: Request) -> Response:
        try:
            return json_response(await library.set_folder(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    async def notices(request: Request) -> Response:
        return json_response(library.take_notices())

    async def checklist(request: Request) -> Response:
        check = request.query_params.get("check") in ("1", "true")
        return json_response(await setup.checklist(check, actor(request)))

    async def move_to_vault(request: Request) -> Response:
        try:
            return json_response(await setup.move_to_vault(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/library/setup", checklist),
        Route("/library/setup/move-to-vault", move_to_vault, methods=["POST"]),
        Route("/library", info),
        Route("/library", set_folder, methods=["PUT"]),
        Route("/library/notices", notices, methods=["POST"]),
    ]
