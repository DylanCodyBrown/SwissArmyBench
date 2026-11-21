"""Every table's read-only cell (services/table_cells.py), for the Workbench window and the agent.

GET    /workbench/tables              every open table as its cell's text (its transformations as one
                                      DuckDB query, its load when no code made it), its grid and steps
POST   /workbench/tables/arrange      {"kind": "notebook", "cells", "tables", "next_cell", "move"} or
                                      {"kind": "script", "text", "tables", "move"}: the document with
                                      its Tables group as it should be, and each cell's uses line
GET    /workbench/tables/{name}/arrow  an open table's grid view (its steps applied) as an Arrow IPC
                                      stream: a kernel's DuckDB SQL naming it (client/sql_cell.py)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, read_json, safely
from swissarmybench.services.table_cells import TableCells


def routes(tables: TableCells) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(await tables.listing())

    async def arrange(request: Request) -> Response:
        return json_response(await tables.arrange(await read_json(request)))

    async def view(request: Request) -> Response:
        data = await tables.view(request.path_params["name"])
        return Response(data, media_type="application/vnd.apache.arrow.stream")

    return [
        Route("/workbench/tables", safely(listing)),
        Route("/workbench/tables/{name}/arrow", safely(view)),
        Route("/workbench/tables/arrange", safely(arrange), methods=["POST"]),
    ]
