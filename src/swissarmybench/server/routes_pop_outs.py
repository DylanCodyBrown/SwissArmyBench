"""Pages and tables in windows of their own (services/pop_outs.py). Every route serves the agent too
(app_navigate's pop).

GET  /pop-outs            {popped: [{key, kind, name, address, connected, placeholder}], mains}
POST /pop-outs            {key, name, address, open: false} (a page's own), {page} or {table} (the agent's)
POST /pop-outs/reattach   {key} | {page} | {table}: back in its old place, its window closed (front, closed)
POST /pop-outs/show       {key} | {page} | {table}: its window to the front
POST /pop-outs/front      {address}: a popped-out window's link out, shown by the main window last in front
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, with_body
from swissarmybench.services.pop_outs import PopOuts


def routes(pop_outs: PopOuts) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(pop_outs.listing())

    return [
        Route("/pop-outs", listing),
        Route("/pop-outs", with_body(pop_outs.pop), methods=["POST"]),
        Route("/pop-outs/reattach", with_body(pop_outs.reattach), methods=["POST"]),
        Route("/pop-outs/show", with_body(pop_outs.show), methods=["POST"]),
        Route("/pop-outs/front", with_body(pop_outs.front), methods=["POST"]),
    ]
