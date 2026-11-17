"""The Data Explorer's search (services/explorer.py), for the Workbench's pane, the grid page's Find data
dialog and the agent (explorer_search).

GET  /explorer/search?q=cust&kinds=tables,columns&connection=Shop&column=customer_id&limit=25
     the results grouped by kind and counted, and the connections whose catalog could be loaded
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import error_response, json_response
from swissarmybench.services.explorer import Explorer


def routes(explorer: Explorer) -> list[BaseRoute]:
    async def search(request: Request) -> Response:
        try:
            return json_response(await explorer.search(dict(request.query_params)))
        except Exception as error:
            return error_response(error)

    return [Route("/explorer/search", search)]
