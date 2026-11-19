"""The canvas's property pane and designer (services/canvas_pane.py; the owner, 2026-11-19), for the Workbench
window and the agent (the golden rule: each has its canvas_* command).

  GET   /streamlit/toolbox                       the Toolbox: every element and container, with its properties
  POST  /streamlit/apps/{app}/toolbox            {"element"}: that element's cell (code, name), names free
  GET   /streamlit/apps/{app}/inspect?page=&block=   a block, a page or the app as the pane draws it:
                                                 properties, uses, used by, state, cache, the code it exports
  GET   /streamlit/tables/{name}                 a table a block uses: columns, steps in words, first rows
  POST  /streamlit/apps/{app}/pages/{page}/blocks/{block}/code
                                                 a change to its cell's code as a plan (before, after, the
                                                 characters that differ); {"apply": true}: the window makes it
  POST  /streamlit/apps/{app}/now                the RUNNING app only: {"key", "value"} sets session state,
                                                 {"key", "forget": true}, {"clear": a cached function or "*"}
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench_streamlit.services.canvas_pane import CanvasPane
from swissarmybench_streamlit.services.streamlit import StreamlitApps


def routes(pane: CanvasPane, apps: StreamlitApps) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    async def body_of(request: Request) -> Any:
        return await read_json(request) if int(request.headers.get("content-length") or 0) else {}

    async def toolbox(request: Request) -> Response:
        return json_response(pane.toolbox())

    async def new_cell(request: Request) -> Response:
        return json_response(pane.new_cell(request.path_params["app"], await body_of(request)))

    async def inspect(request: Request) -> Response:
        asked = request.query_params
        return json_response(
            await pane.inspect(
                request.path_params["app"], asked.get("page") or None, asked.get("block") or None
            )
        )

    async def table(request: Request) -> Response:
        return json_response(await pane.table(request.path_params["name"]))

    async def code(request: Request) -> Response:
        params = request.path_params
        return json_response(
            await pane.code(
                params["app"], params["page"], params["block"], await body_of(request), actor(request)
            )
        )

    async def now(request: Request) -> Response:
        return json_response(
            await apps.now(request.path_params["app"], await body_of(request), actor(request))
        )

    return [
        Route("/streamlit/toolbox", safely(toolbox)),
        Route("/streamlit/apps/{app}/toolbox", safely(new_cell), methods=["POST"]),
        Route("/streamlit/apps/{app}/inspect", safely(inspect)),
        Route("/streamlit/tables/{name}", safely(table)),
        Route("/streamlit/apps/{app}/pages/{page}/blocks/{block}/code", safely(code), methods=["POST"]),
        Route("/streamlit/apps/{app}/now", safely(now), methods=["POST"]),
    ]
