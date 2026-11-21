"""The Analyze menu's analyses on one grid's view (services/analysis.py; the math in domain/analysis.py).

  POST /grids/{id}/fit-test   {"columns": [...], "expected": even | benford | benford2 | grid |
                              shares | together, "reference": {"grid", "column"}, "shares": {...}}
                              -> per column: chi-square, degrees of freedom, p, effect size, the verdict
                              in words, each value's observed and expected count
  POST /grids/{id}/outliers   {"column", "look": amount | frequency, "method": robust | iqr | zscore,
                              "threshold", "by"} -> how many, the fences, the most extreme, and the
                              steps that show or exclude their rows (not added: the page or the agent
                              adds one)
  POST /grids/{id}/odds       {"column", "buckets", "outcome": {"column", "values"} or {"column", "op",
                              "value"}} -> each value's share, 1 in N and odds; with an outcome, each
                              value's rate against the rest and its odds ratio with a 95% range
  POST /grids/{id}/predictors {"target", "candidates", "buckets"} -> each candidate tested together with
                              the target, ranked by Cramér's V; correlations; pairs that say the same
  POST /analysis-proof        {"analysis", "result", "dataset"} -> {"title", "markdown"}: Show the math,
                              the result's own numbers worked through (domain/proofs.py)
  POST /grids/{id}/analysis-code {"analysis", "body"} -> {"code", "imports"}: the analysis as Python for
                              the notebook (the steps as checked SQL, then the swissarmybench.stats call)

Whether a table suits an analysis, and what a form starts on, are the Analyze page's (routes_analyze.py:
POST /analyze/check, POST /analyze/plan), from each analysis's contract.

All read; the agent may run them (cell values come back, so its tools mark them as data).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.domain.proofs import proof as show_the_math
from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench.services.analysis import Analysis
from swissarmybench.services.grids import GridService


def routes(grids: GridService, analysis: Analysis) -> list[BaseRoute]:
    async def fit_test(request: Request) -> Response:
        grid, info = grids.find(request.path_params["grid_id"])
        body = await read_json(request)
        if not isinstance(body, dict):
            raise ValueError('Send {"columns": [...], "expected": "even"}.')
        return json_response(await analysis.fit(grid, info, body, actor(request)))

    def one(name: str, example: str) -> Callable[[Request], Awaitable[Response]]:
        async def handle(request: Request) -> Response:
            grid, info = grids.find(request.path_params["grid_id"])
            body = await read_json(request)
            if not isinstance(body, dict):
                raise ValueError(f"Send {example}.")
            return json_response(await analysis.run(name, grid, info, body, actor(request)))

        return safely(handle)

    async def proof(request: Request) -> Response:
        """Show the math: {"analysis", "result": what the window showed, "dataset"} as a proof."""
        body = await read_json(request)
        if not isinstance(body, dict):
            raise ValueError('Send {"analysis": "odds", "result": {...the result shown...}}.')
        dataset = str(body.get("dataset") or "")
        return json_response(show_the_math(str(body.get("analysis")), body.get("result"), dataset))

    async def code(request: Request) -> Response:
        """The analysis as Python for a notebook (the result's Copy code)."""
        grid, info = grids.find(request.path_params["grid_id"])
        body = await read_json(request)
        if not isinstance(body, dict) or not isinstance(body.get("body"), dict):
            raise ValueError('Send {"analysis": "odds", "body": {...the analysis request...}}.')
        return json_response(await analysis.code(str(body.get("analysis")), grid, info, body["body"]))

    return [
        Route("/grids/{grid_id}/fit-test", safely(fit_test), methods=["POST"]),
        Route(
            "/grids/{grid_id}/outliers",
            one("outliers", '{"column": name, "look": "amount"}'),
            methods=["POST"],
        ),
        Route(
            "/grids/{grid_id}/odds",
            one("odds", '{"column": name}, with "outcome" for odds ratios'),
            methods=["POST"],
        ),
        Route("/grids/{grid_id}/predictors", one("predictors", '{"target": name}'), methods=["POST"]),
        Route("/grids/{grid_id}/analysis-code", safely(code), methods=["POST"]),
        Route("/analysis-proof", safely(proof), methods=["POST"]),
    ]
