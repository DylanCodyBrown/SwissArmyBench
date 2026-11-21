"""A script's run settings, Run as scheduled and its run history (services/script_runs.py), for the
Workbench window's Script mode and the agent (workbench_script_settings, workbench_script_run,
workbench_script_history).

GET  /workbench/scripts/settings?path=   the arguments and the variables it needs, each with its source
PUT  /workbench/scripts/settings         {"path", "arguments", "variables": [{"name", "from", ...}]}
POST /workbench/scripts/run              {"path", "python"?}: Run as scheduled (no app); the run's record
GET  /workbench/scripts/history?path=    its runs, the newest first, each with its log (memory only)
POST /workbench/scripts/history          {"path", "seconds", "exit_code", "log"?}: a Run file the window ran
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely, with_body
from swissarmybench.services.script_runs import ScriptRuns


def routes(runs: ScriptRuns) -> list[BaseRoute]:
    async def settings(request: Request) -> Response:
        return json_response(runs.settings(request.query_params.get("path")))

    async def set_settings(request: Request) -> Response:
        return json_response(runs.set_settings(await read_json(request), actor(request)))

    async def history(request: Request) -> Response:
        return json_response(runs.history(request.query_params.get("path")))

    async def record(request: Request) -> Response:
        return json_response(runs.record(await read_json(request)))

    return [
        Route("/workbench/scripts/settings", safely(settings)),
        Route("/workbench/scripts/settings", safely(set_settings), methods=["PUT"]),
        Route("/workbench/scripts/run", with_body(runs.run), methods=["POST"]),
        Route("/workbench/scripts/history", safely(history)),
        Route("/workbench/scripts/history", safely(record), methods=["POST"]),
    ]
