"""The Scripts page's debugger (services/debugger.py), for the page and the agent alike (workbench_debug).

GET  /workbench/debug              ?kernel= or ?document=: the session (state, line, frames, output)
POST /workbench/debug/breakpoints  {kernel | document, breakpoints: [{line, condition?, log?}]}
POST /workbench/debug/start        {kernel | document, code, breakpoints?}: the script run under the debugger
POST /workbench/debug/step         {kernel | document, action: over | into | out | continue}
POST /workbench/debug/variables    {kernel | document, frame | reference}
POST /workbench/debug/evaluate     {kernel | document, expression, frame?}: the debug console, a watch
POST /workbench/debug/stop         {kernel | document}
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench.services.debugger import Debugger


def routes(debugger: Debugger) -> list[BaseRoute]:
    async def state(request: Request) -> Response:
        return json_response(debugger.state(dict(request.query_params)))

    async def breakpoints(request: Request) -> Response:
        return json_response(await debugger.breakpoints(await read_json(request), actor(request)))

    async def start(request: Request) -> Response:
        return json_response(await debugger.start(await read_json(request), actor(request)))

    async def step(request: Request) -> Response:
        return json_response(await debugger.step(await read_json(request), actor(request)))

    async def variables(request: Request) -> Response:
        return json_response(await debugger.variables(await read_json(request)))

    async def evaluate(request: Request) -> Response:
        return json_response(await debugger.evaluate(await read_json(request), actor(request)))

    async def stop(request: Request) -> Response:
        return json_response(await debugger.stop(await read_json(request), actor(request)))

    return [
        Route("/workbench/debug", safely(state), methods=["GET"]),
        Route("/workbench/debug/breakpoints", safely(breakpoints), methods=["POST"]),
        Route("/workbench/debug/start", safely(start), methods=["POST"]),
        Route("/workbench/debug/step", safely(step), methods=["POST"]),
        Route("/workbench/debug/variables", safely(variables), methods=["POST"]),
        Route("/workbench/debug/evaluate", safely(evaluate), methods=["POST"]),
        Route("/workbench/debug/stop", safely(stop), methods=["POST"]),
    ]
