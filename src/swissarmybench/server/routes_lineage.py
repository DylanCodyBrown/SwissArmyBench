"""Lineage with values (services/lineage.py), for the Workbench window and the agent.

POST   /workbench/lineage    {"document", "cell", "cells"?|"text"?, "kernel"?, "errors"?, "values"?} or
                             {"app", "page", "block", "values"?}: from that cell or canvas block back
                             through every cell to the data: the nodes in flow order, the edges, the
                             Mermaid text, and each node's value, summarised
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench.services.lineage import Lineage


def routes(lineage: Lineage) -> list[BaseRoute]:
    async def trace(request: Request) -> Response:
        return json_response(await lineage.trace(await read_json(request), actor(request)))

    return [Route("/workbench/lineage", safely(trace), methods=["POST"])]
