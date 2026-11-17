"""The Workbench editors' intelligence (services/intellisense.py), for the page and the agent alike
(workbench_complete, workbench_signature, workbench_problems).

POST /workbench/intel/complete   {text, offset | line+column, notebook, before, kernel, path, recent}
POST /workbench/intel/signature  the same: the call the cursor is inside (its parameter info)
POST /workbench/intel/hover      the same: the name at the cursor
POST /workbench/intel/lint       {text, language, notebook, before, after, kernel, connection, ...}
PUT  /workbench/intel/problems   {document, title, problems}: what an editor shows now (the page tells)
GET  /workbench/intel/problems   [?path=]: every open document's problems; a file's, checked now
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.intellisense import Intellisense


def routes(intel: Intellisense) -> list[BaseRoute]:
    async def ask(request: Request) -> Response:
        try:
            body = await read_json(request)
            who = actor(request)
            kind = request.path_params["kind"]
            if kind == "complete":
                return json_response(await intel.complete(body, who))
            if kind == "signature":
                return json_response(await intel.signature(body, who))
            if kind == "hover":
                return json_response(await intel.hover(body, who))
            if kind == "lint":
                return json_response(await intel.lint(body, who))
            return json_response({"error": "Ask complete, signature, hover or lint."}, status_code=404)
        except Exception as error:
            return error_response(error)

    async def report(request: Request) -> Response:
        try:
            return json_response(intel.report(await read_json(request)))
        except Exception as error:
            return error_response(error)

    async def problems(request: Request) -> Response:
        try:
            return json_response(
                await intel.problems(request.query_params.get("path") or None, actor(request))
            )
        except Exception as error:
            return error_response(error)

    return [
        Route("/workbench/intel/problems", problems),
        Route("/workbench/intel/problems", report, methods=["PUT"]),
        Route("/workbench/intel/{kind}", ask, methods=["POST"]),
    ]
