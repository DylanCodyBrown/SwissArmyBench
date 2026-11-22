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
  POST   /connections/{name}/sql-endpoint   a Dataverse connection saved for its Web API moved to its
                                            SQL endpoint (its tables listed and read there from now on)
  GET    /connections/sql/reads             this session's reads: each one's connection, table, rows, when
  GET    /connections/sql/reads/{id}        one read's rows as an Arrow IPC stream (a kernel's DuckDB)
  POST   /connections/sql/refresh           {connection?}: drop the session's reads, so the next query
                                            reads again
  GET    /connections/sql/alias?name=       the open project's dataset connection name ({name, alias,
                                            words, dialect: dax}) when it is not a saved connection (a
                                            kernel's %%dax cell asks before it fails)
  POST   /connections/sql/alias/dax         {name, dax}: DAX through what that name reads now, an Arrow
                                            IPC stream (its words in X-Sab-Source)
"""

from __future__ import annotations

from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.blade_runner import RefreshError
from swissarmybench.server.http import actor, error_response, json_response, read_json, safely
from swissarmybench.services.blades import BladeService, NeedsValues
from swissarmybench.services.connection_tables import ConnectionTables
from swissarmybench.services.connections import ConnectionService


def routes(tables: ConnectionTables, blades: BladeService, connections: ConnectionService) -> list[BaseRoute]:
    def failed(error: NeedsValues | RefreshError, name: str | None) -> Response:
        """The two errors these routes answer their own way (every other one: the app's guard)."""
        if isinstance(error, NeedsValues):
            return json_response({"needs": error.missing, "message": str(error)}, status_code=409)
        return json_response(blades.run_failure(str(error), error.missing_module, name), status_code=422)

    async def tree(request: Request) -> Response:
        name = request.path_params["name"]
        try:
            return json_response(await tables.tree(name, request.query_params.get("load") != "0"))
        except (NeedsValues, RefreshError) as error:
            return failed(error, name)

    async def open_dataset(request: Request) -> Response:
        name = request.path_params["name"]
        try:
            body = await read_json(request)
            dataset = str(body.get("dataset") or body.get("schema") or "") if isinstance(body, dict) else ""
            return json_response(await tables.open_dataset(name, dataset, actor(request)))
        except (NeedsValues, RefreshError) as error:
            return failed(error, name)

    async def sql_endpoint(request: Request) -> Response:
        return json_response(await connections.use_sql_endpoint(request.path_params["name"], actor(request)))

    async def prepare(request: Request) -> Response:
        try:
            body = await read_json(request)
            text = body.get("sql") if isinstance(body, dict) else None
            if not isinstance(text, str) or not text.strip():
                raise ValueError('Send {"sql": "SELECT ... FROM [Connection].table"}.')
            prepared = await tables.prepare(text)
            return json_response({"sql": prepared.sql, "tables": prepared.reads})
        except (NeedsValues, RefreshError) as error:
            return failed(error, None)

    async def reads(request: Request) -> Response:
        return json_response(tables.reads())

    async def read(request: Request) -> Response:
        data = await tables.arrow(request.path_params["id"])
        return Response(data, media_type="application/vnd.apache.arrow.stream")

    async def alias(request: Request) -> Response:
        name = request.query_params.get("name", "")
        found = tables.alias(name) if name else None
        if found is None:
            return error_response(
                LookupError(f"No dataset connection is named {name!r} in the open project.")
            )
        key, value = found
        return json_response(
            {"name": key, "alias": True, "words": value.words(), "dialect": "dax", "connection": "database"}
        )

    async def alias_dax(request: Request) -> Response:
        try:
            body = await read_json(request)
            body = body if isinstance(body, dict) else {}
            name, query = body.get("name"), body.get("dax")
            if not isinstance(name, str) or not isinstance(query, str) or not query.strip():
                raise ValueError('Send {"name": "<the dataset connection>", "dax": "EVALUATE ..."}.')
            table, words = await tables.alias_dax(name, query)
            data = await tables.to_arrow(table)
            return Response(
                data, media_type="application/vnd.apache.arrow.stream", headers={"X-Sab-Source": quote(words)}
            )
        except (NeedsValues, RefreshError) as error:
            return failed(error, None)

    async def refresh(request: Request) -> Response:
        body = await read_json(request)
        name = body.get("connection") if isinstance(body, dict) else None
        return json_response(await tables.refresh(str(name) if name else None))

    return [
        Route("/connections/sql/prepare", prepare, methods=["POST"]),
        Route("/connections/sql/reads", reads),
        Route("/connections/sql/reads/{id}", safely(read)),
        Route("/connections/sql/refresh", safely(refresh), methods=["POST"]),
        Route("/connections/sql/alias", alias),
        Route("/connections/sql/alias/dax", alias_dax, methods=["POST"]),
        Route("/connections/{name}/tree", tree),
        Route("/connections/{name}/open-dataset", open_dataset, methods=["POST"]),
        Route("/connections/{name}/sql-endpoint", safely(sql_endpoint), methods=["POST"]),
    ]
