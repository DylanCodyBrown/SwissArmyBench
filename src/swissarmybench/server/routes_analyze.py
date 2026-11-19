"""The Analyze page (services/analyze.py; the rules in domain/analyze.py, the contracts in
domain/analysis_contracts.py). The page's forms, the agent's analyze_* tools and `sab.analyze` use these.

  GET  /analyze?front=<grid>         the toolbar: the groups and each analysis (question, name, what you
                                     get); the open tables ("orders, with 2 steps") and the one a form
                                     starts on (the grid in front, else the last used in Analyze)
  GET  /analyze/contracts            every analysis's data contract, with its made-up sample
  GET  /analyze/contracts/{id}       one contract and its sample
  POST /analyze/plan     {"analysis", "table"?, "columns"?, "options"?}: the form, planned: each slot's
                         columns that fit (and the ones that do not, with why), the picks, the options,
                         what is missing in one sentence, the fixes, the sentence of what will run
  POST /analyze/check    {"table"?}: Check this table: every analysis ranked (fits now, after its fixes,
                         or not, and why), the three that suit it; with "analysis": that one's check
  POST /analyze/column   {"table"?, "column"?}: the analyses a column fits (with none: every column's)
  POST /analyze/fix      {"analysis", "table", "fixes": [ids], "columns"?}: add those fixes' steps to the
                         table (the user's Apply; undone in the steps strip), then the form again
  POST /analyze/sample   {"analysis"}: the contract's made-up sample opened as a table
  POST /analyze/run      {"analysis", "table"?, "columns"?, "options"?, "apply_fixes"?, "sample"?,
                         "token"?}: run it; its cards land at the top of the board (`cards`), `result` holds
                         the numbers. 409 with `plan` when the table does not fit as asked
  POST /analyze/cancel   {"token"}: stop the run started with that token; nothing of it lands
  POST /analyze/land     {"analysis", "dataset", "request", "result"}: a result Python computed itself
                         (sab.analyze.<analysis>(df)) put on the board: the cards are made here
  GET  /analyze/runs                 this session's runs, newest first
  GET  /analyze/runs/{run}           what a run ran with (Run again)
  GET  /analyze/runs/{run}/math      Show the math: {"title", "markdown"}
  POST /analyze/runs/{run}/grid      Open as grid: the result's table in a tab of its own
  GET  /analyze/runs/{run}/code      Copy code: {"code", "imports"}

Every refusal is in the one shape (9.5). The agent may use all of them (cell values come back in a
column's preview and a result, so its tools mark them as data).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.domain.refusals import try_again
from swissarmybench.server.http import actor, error_response, json_response, read_json, refusal
from swissarmybench.services.analyze import Analyze, DoesNotFit

Handler = Callable[[Request], Awaitable[Response]]


def routes(analyze: Analyze) -> list[BaseRoute]:
    def answered(work: Callable[[Request], Awaitable[object]]) -> Handler:
        async def handle(request: Request) -> Response:
            try:
                return json_response(await work(request))
            except DoesNotFit as error:
                return refusal(str(error), 409, where=error.where, fixes=[try_again()], plan=error.plan)
            except Exception as error:
                return error_response(error)

        return handle

    async def toolbar(request: Request) -> object:
        return analyze.catalog() | analyze.tables(request.query_params.get("front"))

    async def contracts(request: Request) -> object:
        return analyze.contracts(request.path_params.get("analysis"))

    async def plan(request: Request) -> object:
        return await analyze.plan(await read_json(request), actor(request))

    async def check(request: Request) -> object:
        return await analyze.check(await read_json(request), actor(request))

    async def column(request: Request) -> object:
        return await analyze.column(await read_json(request), actor(request))

    async def fix(request: Request) -> object:
        return await analyze.apply_fixes(await read_json(request), actor(request))

    async def sample(request: Request) -> object:
        body = await read_json(request)
        if not isinstance(body, dict):
            raise ValueError('Send {"analysis": "benford"}.')
        return await analyze.open_sample(body.get("analysis"), actor(request))

    async def run(request: Request) -> object:
        return await analyze.run(await read_json(request), actor(request))

    async def cancel(request: Request) -> object:
        body = await read_json(request)
        return analyze.cancel(body.get("token") if isinstance(body, dict) else None)

    async def land(request: Request) -> object:
        return await analyze.land(await read_json(request), actor(request))

    async def runs(request: Request) -> object:
        return analyze.runs()

    async def inputs(request: Request) -> object:
        return analyze.inputs(request.path_params["run"])

    async def math(request: Request) -> object:
        return analyze.math(request.path_params["run"])

    async def as_grid(request: Request) -> object:
        return await analyze.as_grid(request.path_params["run"], actor(request))

    async def code(request: Request) -> object:
        return await analyze.code(request.path_params["run"])

    return [
        Route("/analyze", answered(toolbar)),
        Route("/analyze/contracts", answered(contracts)),
        Route("/analyze/contracts/{analysis}", answered(contracts)),
        Route("/analyze/plan", answered(plan), methods=["POST"]),
        Route("/analyze/check", answered(check), methods=["POST"]),
        Route("/analyze/column", answered(column), methods=["POST"]),
        Route("/analyze/fix", answered(fix), methods=["POST"]),
        Route("/analyze/sample", answered(sample), methods=["POST"]),
        Route("/analyze/run", answered(run), methods=["POST"]),
        Route("/analyze/cancel", answered(cancel), methods=["POST"]),
        Route("/analyze/land", answered(land), methods=["POST"]),
        Route("/analyze/runs", answered(runs)),
        Route("/analyze/runs/{run}", answered(inputs)),
        Route("/analyze/runs/{run}/math", answered(math)),
        Route("/analyze/runs/{run}/grid", answered(as_grid), methods=["POST"]),
        Route("/analyze/runs/{run}/code", answered(code)),
    ]
