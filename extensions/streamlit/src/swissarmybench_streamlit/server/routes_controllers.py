"""A canvas page's controllers (services/controllers.py), for the Workbench window and the agent.

GET  /streamlit/apps/{app}/check?page=                            each page's check: defaults used,
                                                                  contract problems, names made twice,
                                                                  cycles; each block's controller
POST /streamlit/apps/{app}/pages/{page}/test                      Test this page (AppTest)
GET  /streamlit/apps/{app}/pages/{page}/blocks/{block}/move-to-data   a thin cell's move, for the
                                                                  window to make in its documents
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response
from swissarmybench_streamlit.services.controllers import Controllers


def routes(controllers: Controllers) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    async def check(request: Request) -> Response:
        page = request.query_params.get("page") or None
        return json_response(controllers.check(request.path_params["app"], page))

    async def test(request: Request) -> Response:
        params = request.path_params
        return json_response(await controllers.test(params["app"], params["page"], actor(request)))

    async def move(request: Request) -> Response:
        params = request.path_params
        return json_response(controllers.move_plan(params["app"], params["page"], params["block"]))

    return [
        Route("/streamlit/apps/{app}/check", safely(check)),
        Route("/streamlit/apps/{app}/pages/{page}/test", safely(test), methods=["POST"]),
        Route("/streamlit/apps/{app}/pages/{page}/blocks/{block}/move-to-data", safely(move)),
    ]
