"""A script's run settings (services/script_runs.py), for the Workbench window's Script mode and the agent
(workbench_script_settings).

GET  /workbench/scripts/settings?path=   the arguments and the variables it needs, each with its source
PUT  /workbench/scripts/settings         {"path", "arguments", "variables": [{"name", "from", ...}]}
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json
from swissarmybench.services.script_runs import ScriptRuns


def routes(runs: ScriptRuns) -> list[BaseRoute]:
    async def settings(request: Request) -> Response:
        return json_response(runs.settings(request.query_params.get("path")))

    async def set_settings(request: Request) -> Response:
        return json_response(runs.set_settings(await read_json(request), actor(request)))

    return [
        Route("/workbench/scripts/settings", settings),
        Route("/workbench/scripts/settings", set_settings, methods=["PUT"]),
    ]
