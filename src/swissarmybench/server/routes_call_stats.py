"""Every call's statistics (services/call_stats.py; Plans/stats.plan.md): names, times, sizes, never a value.

GET  /stats           ?action=summary|slowest|errors|table|connection|endpoint|hints&name=&n=20   stats
GET  /stats/figures   ?kind=connection|endpoint|table&names=a,b: each one's figures (the Connections and
                      APIs pages)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response
from swissarmybench.services.call_stats import CallStats


def routes(stats: CallStats) -> list[BaseRoute]:
    async def view(request: Request) -> Response:
        q = request.query_params
        return json_response(stats.view(q.get("action") or "summary", q.get("name") or "", q.get("n")))

    async def figures(request: Request) -> Response:
        q = request.query_params
        names = [n for n in (q.get("names") or "").split(",") if n.strip()]
        return json_response({"figures": stats.figures_of(q.get("kind") or "connection", names)})

    return [Route("/stats", view), Route("/stats/figures", figures)]
