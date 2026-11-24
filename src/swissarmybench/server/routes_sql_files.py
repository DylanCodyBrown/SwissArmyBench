""".sql files on the Scripts page (services/sql_files.py), for the page and the agent alike (workbench_sql):

POST /scripts/sql/run        {path?, text?, connection?, line?, selection?, table?}: the file's query (or the
                             statement at the line) built as the open table named after the file; a failure's
                             refusal carries the file's `line`
POST /scripts/sql/for-table  {table}: a table a query made as its .sql file (Edit in Scripts): {path, made}
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.domain.sql_files import SqlFileError
from swissarmybench.server.http import actor, json_response, read_json, refusal, with_body
from swissarmybench.services.sql_files import SqlFiles


def routes(sql_files: SqlFiles) -> list[BaseRoute]:
    async def run(request: Request) -> Response:
        try:
            return json_response(await sql_files.run(await read_json(request), actor(request)))
        except SqlFileError as error:
            where = f"line {error.line}" if error.line else None
            return refusal(str(error), 400, where=where, details=error.details, line=error.line)

    return [
        Route("/scripts/sql/run", run, methods=["POST"]),
        Route("/scripts/sql/for-table", with_body(sql_files.for_table), methods=["POST"]),
    ]
