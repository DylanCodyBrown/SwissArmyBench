""".sql files on the Scripts page (services/sql_files.py), for the page and the agent alike (workbench_sql):

POST /scripts/sql/run        {path?, text?, connection?, line?, selection?, table?}: the file's query (or the
                             statement at the line) built as the open table named after the file; a failure's
                             refusal carries the file's `line`
POST /scripts/sql/for-table  {table}: a table a query made as its .sql file (Edit in Scripts): {path, made};
                             a table a Power Query made answers with its .pq file

Power Query files (services/m_files.py, held by SqlFiles as `power_query`; workbench_m):

POST /scripts/pq/run         {path?, text?, line?, query?}: every table query of the file (or the one at the
                             line, or named) built as the open table of its name; a failure's refusal
                             carries the file's `line`, `column` and `name`
POST /scripts/pq/problems    {path?, text?}: what cannot run, before a run; nothing is read
POST /scripts/pq/sql         {path?, text?, line?, query?}: the DuckDB SQL composed for each query
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.domain.sql_files import SqlFileError
from swissarmybench.server.http import actor, json_response, read_json, refusal, with_body
from swissarmybench.services.m_files import PowerQueryError
from swissarmybench.services.sql_files import SqlFiles


def routes(sql_files: SqlFiles) -> list[BaseRoute]:
    async def run(request: Request) -> Response:
        try:
            return json_response(await sql_files.run(await read_json(request), actor(request)))
        except SqlFileError as error:
            where = f"line {error.line}" if error.line else None
            return refusal(str(error), 400, where=where, details=error.details, line=error.line)

    queries = sql_files.power_query

    def refused(error: PowerQueryError) -> Response:
        where = f"line {error.line}" if error.line else None
        return refusal(
            str(error), 400, where=where, details=error.details, line=error.line, column=error.column,
            name=error.name, query=error.query, add_connection=error.add_connection or None,
        )  # fmt: skip

    async def run_queries(request: Request) -> Response:
        try:
            return json_response(await queries.run(await read_json(request), actor(request)))
        except PowerQueryError as error:
            return refused(error)

    async def composed(request: Request) -> Response:
        try:
            return json_response(await queries.sql(await read_json(request)))
        except PowerQueryError as error:
            return refused(error)

    async def problems(request: Request) -> Response:
        return json_response(await queries.problems(await read_json(request)))

    return [
        Route("/scripts/pq/run", run_queries, methods=["POST"]),
        Route("/scripts/pq/sql", composed, methods=["POST"]),
        Route("/scripts/pq/problems", problems, methods=["POST"]),
        Route("/scripts/sql/run", run, methods=["POST"]),
        Route("/scripts/sql/for-table", with_body(sql_files.for_table), methods=["POST"]),
    ]
