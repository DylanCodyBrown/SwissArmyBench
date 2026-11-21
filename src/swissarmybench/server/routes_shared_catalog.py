"""The shared catalog (services/shared_catalog.py): the library's catalog/, for the pages and the agent.

GET   /shared-catalog                 every connection's tables, state and used_by (?search=)   catalog_shared
GET   /shared-catalog/table           one table: columns, keys, relationships
                                      (?connection=&table=)                               catalog_shared_table
POST  /shared-catalog/refresh         look at the folder now (what a pull changed)      catalog_shared_refresh
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response
from swissarmybench.services.shared_catalog import SharedCatalog


def routes(shared: SharedCatalog) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(shared.listing(request.query_params.get("search")))

    async def table(request: Request) -> Response:
        q = request.query_params
        return json_response(shared.table(q.get("connection"), q.get("table")))

    async def refresh(request: Request) -> Response:
        return json_response(await shared.refresh(actor(request)))

    return [
        Route("/shared-catalog", listing),
        Route("/shared-catalog/table", table),
        Route("/shared-catalog/refresh", refresh, methods=["POST"]),
    ]
