"""Export as one Python script (services/script_export.py), for the Workbench window and the agent
(the golden rule: `workbench_export_script`).

POST /workbench/export-script  {"path", "cells"? | "text"?, "kind"?, "to"?, "stub"?, "check"?}: the
                               notebook or script as one .py that runs with plain `python <file>`
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench.services.script_export import ScriptExports


def routes(exports: ScriptExports) -> list[BaseRoute]:
    async def export(request: Request) -> Response:
        return json_response(await exports.export(await read_json(request), actor(request)))

    return [Route("/workbench/export-script", safely(export), methods=["POST"])]
