"""Every table's read-only cell (services/table_cells.py), for the Workbench window and the agent.

GET    /workbench/tables              every open table as its cell's text (its transformations as one
                                      DuckDB query, its load when no code made it), its grid and steps
POST   /workbench/tables/arrange      {"kind": "notebook", "cells", "tables", "next_cell", "move"} or
                                      {"kind": "script", "text", "tables", "move"}: the document with
                                      its Tables group as it should be, and each cell's uses line
GET    /workbench/tables/{name}/arrow  an open table's grid view (its steps applied) as an Arrow IPC
                                      stream: a kernel's DuckDB SQL naming it (client/sql_cell.py)
POST   /workbench/tables/adapter/tables  the open tables as a source of the adapter: {"tables": [{name,
                                      columns: [{name, type}]}]} (adapter.Remote's tables)
POST   /workbench/tables/adapter/read  {"table", "plan"}: the plan over its grid view as an Arrow IPC stream,
                                      X-Sab-Folded the parts folded (a kernel's sab.table(name))
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, read_json
from swissarmybench.services.table_cells import TableCells


def routes(tables: TableCells) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(await tables.listing())

    async def arrange(request: Request) -> Response:
        return json_response(await tables.arrange(await read_json(request)))

    async def view(request: Request) -> Response:
        data = await tables.view(request.path_params["name"])
        return Response(data, media_type="application/vnd.apache.arrow.stream")

    async def adapter_tables(request: Request) -> Response:
        return json_response(await tables.adapter_tables())

    async def adapter_read(request: Request) -> Response:
        body = await read_json(request)
        given = body if isinstance(body, dict) else {}
        data, folded = await tables.adapter_read(str(given.get("table") or ""), given.get("plan"))
        headers = {"X-Sab-Folded": ",".join(folded)}
        return Response(data, media_type="application/vnd.apache.arrow.stream", headers=headers)

    return [
        Route("/workbench/tables", listing),
        Route("/workbench/tables/{name}/arrow", view),
        Route("/workbench/tables/arrange", arrange, methods=["POST"]),
        Route("/workbench/tables/adapter/tables", adapter_tables, methods=["POST"]),
        Route("/workbench/tables/adapter/read", adapter_read, methods=["POST"]),
    ]
