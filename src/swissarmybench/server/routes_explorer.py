"""The Data Explorer's search and the Data page's browse (services/explorer.py), for the Workbench's pane,
the grid page's Find data dialog, the Data page and the agent (explorer_search, explorer_browse,
explorer_table).

GET  /explorer/search?q=cust&kinds=tables,columns&connection=Shop&column=customer_id&limit=25
     the results grouped by kind and counted, and the connections whose catalog could be loaded
GET  /explorer/browse?kinds=tables&connection=Shop
     the Data page with nothing typed: every connection (its status, its tables in groups), then the open
     tables, Structures, the APIs' tables and the blades whose result is a table. Names only
GET  /explorer/table?connection=Shop&database=&schema=main&table=orders
     a connection's table for the detail side: columns, where it comes from, its SQL name, its code
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, safely
from swissarmybench.services.explorer import Explorer


def routes(explorer: Explorer) -> list[BaseRoute]:
    async def search(request: Request) -> Response:
        return json_response(await explorer.search(dict(request.query_params)))

    async def browse(request: Request) -> Response:
        return json_response(await explorer.browse(dict(request.query_params)))

    async def table(request: Request) -> Response:
        return json_response(await explorer.table(dict(request.query_params)))

    return [
        Route("/explorer/search", safely(search)),
        Route("/explorer/browse", safely(browse)),
        Route("/explorer/table", safely(table)),
    ]
