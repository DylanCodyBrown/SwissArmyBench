"""The project's sandbox (services/sandbox.py).

GET   /sandbox?sort=&order=          its tables (sorted: name, rows, source, created, changed), sources,
                                     clients, designations, baseline, checkpoints, log          sandbox(list)
POST  /sandbox/tables                {"from", ...}: a table in                                sandbox_add
POST  /sandbox/tables/remove         {"table"}                                                sandbox_remove
POST  /sandbox/tables/open           {"table"}: in Grids, following every write               sandbox_open
POST  /sandbox/tables/variant        {"from": grid|structure, "table"|"structure", "name"?}: a sandbox
                                     variant, its own designation and origin                  sandbox(variant)
POST  /sandbox/tables/mock           {"table", "connection"|null}: Mocked as a connection       sandbox(mock)
POST  /sandbox/edit                  {"table", "op": update|insert|delete, ...}: its grid's edit sandbox(edit)
POST  /sandbox/reset                 every table back to the baseline (agent: on Allow)       sandbox_reset
POST  /sandbox/baseline              the sandbox as it is now made the baseline     sandbox_checkpoint
POST  /sandbox/checkpoints           {"name", "action": save | delete}                      sandbox_checkpoint
POST  /sandbox/checkpoints/restore   {"name"}                                                 sandbox_restore
POST  /sandbox/data                  a mock client's data call (the token)
POST  /sandbox/data/{key}            a running local sandbox API's data call: its own key in the path
                                     instead of the token (server/security.py's secret paths)
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import (
    error_as,
    error_response,
    json_response,
    read_json,
    with_body,
)
from swissarmybench.services.sandbox import Sandbox

DATA_PREFIX = "/sandbox/data/"


def routes(sandbox: Sandbox, keys: Callable[[], set[str]] = set) -> list[BaseRoute]:
    async def by_key(request: Request) -> Response:
        key = str(request.path_params["key"])
        if not any(secrets.compare_digest(key, k) for k in keys()):
            return error_as(PermissionError("That key is not a running local sandbox API's."), 403)
        try:
            return json_response(await sandbox.data(await read_json(request), "api"))
        except Exception as error:
            return error_response(error)

    async def listing(request: Request) -> Response:
        try:
            return json_response(await sandbox.listing(dict(request.query_params)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/sandbox", listing),
        Route("/sandbox/tables", with_body(sandbox.add), methods=["POST"]),
        Route("/sandbox/tables/remove", with_body(sandbox.remove), methods=["POST"]),
        Route("/sandbox/tables/open", with_body(sandbox.open_grid), methods=["POST"]),
        Route("/sandbox/tables/variant", with_body(sandbox.variant), methods=["POST"]),
        Route("/sandbox/tables/mock", with_body(sandbox.mock), methods=["POST"]),
        Route("/sandbox/edit", with_body(sandbox.edit), methods=["POST"]),
        Route("/sandbox/reset", with_body(sandbox.reset), methods=["POST"]),
        Route("/sandbox/baseline", with_body(sandbox.set_baseline), methods=["POST"]),
        Route("/sandbox/checkpoints", with_body(sandbox.checkpoint), methods=["POST"]),
        Route("/sandbox/checkpoints/restore", with_body(sandbox.restore), methods=["POST"]),
        Route("/sandbox/data", with_body(sandbox.data), methods=["POST"]),
        Route(DATA_PREFIX + "{key}", by_key, methods=["POST"]),
    ]
