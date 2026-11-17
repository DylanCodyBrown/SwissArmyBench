"""A connection's tables (services/connection_tables.py): what every kind of connection exposes, and DuckDB
SQL that names them by the connection. The agent may do all of it too (the golden rule):

  GET    /connections/{name}/tree           its tables as a tree (a Power BI workspace's datasets, a
                                            database's schemas), each with its name for SQL; ?load=0
                                            never loads the catalog (the state is said)
  POST   /connections/{name}/open-dataset   {dataset}: every table of one dataset (or schema), each a grid
  POST   /connections/sql/prepare           {sql}: the connections' tables a DuckDB query names, read (or
                                            this session's read of them), and the query pointed at them
                                            (what a Workbench kernel's %%sql runs; the tables themselves
                                            come from the next route)
  GET    /connections/sql/reads             this session's reads: each one's connection, table, rows, when
  GET    /connections/sql/reads/{id}        one read's rows as an Arrow IPC stream (a kernel's DuckDB)
  POST   /connections/sql/refresh           {connection?}: drop the session's reads, so the next query
                                            reads again
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.blade_runner import RefreshError
from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.blades import BladeService, NeedsValues
from swissarmybench.services.connection_tables import ConnectionTables


def routes(tables: ConnectionTables, blades: BladeService) -> list[BaseRoute]:
    def failed(error: Exception, name: str | None) -> Response:
        if isinstance(error, NeedsValues):
            return json_response({"needs": error.missing, "message": str(error)}, status_code=409)
        if isinstance(error, RefreshError):
            return json_response(blades.run_failure(str(error), error.missing_module, name), status_code=422)
        return error_response(error)

    async def tree(request: Request) -> Response:
        name = request.path_params["name"]
        try:
            return json_response(await tables.tree(name, request.query_params.get("load") != "0"))
        except Exception as error:
            return failed(error, name)

    async def open_dataset(request: Request) -> Response:
        name = request.path_params["name"]
        try:
            body = await read_json(request)
            dataset = str(body.get("dataset") or body.get("schema") or "") if isinstance(body, dict) else ""
            return json_response(await tables.open_dataset(name, dataset, actor(request)))
        except Exception as error:
            return failed(error, name)

    async def prepare(request: Request) -> Response:
        try:
            body = await read_json(request)
            text = body.get("sql") if isinstance(body, dict) else None
            if not isinstance(text, str) or not text.strip():
                raise ValueError('Send {"sql": "SELECT ... FROM [Connection].table"}.')
            prepared = await tables.prepare(text)
            return json_response({"sql": prepared.sql, "tables": prepared.reads})
        except Exception as error:
            return failed(error, None)

    async def reads(request: Request) -> Response:
        return json_response(tables.reads())

    async def read(request: Request) -> Response:
        try:
            data = await tables.arrow(request.path_params["id"])
            return Response(data, media_type="application/vnd.apache.arrow.stream")
        except Exception as error:
            return error_response(error)

    async def refresh(request: Request) -> Response:
        try:
            body = await read_json(request)
            name = body.get("connection") if isinstance(body, dict) else None
            return json_response(await tables.refresh(str(name) if name else None))
        except Exception as error:
            return error_response(error)

    return [
        Route("/connections/sql/prepare", prepare, methods=["POST"]),
        Route("/connections/sql/reads", reads),
        Route("/connections/sql/reads/{id}", read),
        Route("/connections/sql/refresh", refresh, methods=["POST"]),
        Route("/connections/{name}/tree", tree),
        Route("/connections/{name}/open-dataset", open_dataset, methods=["POST"]),
    ]
