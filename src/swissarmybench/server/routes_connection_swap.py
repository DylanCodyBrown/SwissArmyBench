"""A table's connection swapped for another, and the code pointed at the new one
(services/connection_swap.py). The agent may do all of it too (the golden rule):

  GET    /tables/{name}/connection         the table's connection, how it is read, the others, its undo
  POST   /tables/{name}/connection         {to, place?, sql?, all?, dataset?}: read it from `to`, its steps
                                           kept: {swapped}, or {review: its query}, or {pick: tables}
  POST   /tables/{name}/connection/undo    the table as it was before its last swap
  POST   /connections/{name}/move          {to, run_as_is?}: every table read from `name` (a deleted one
                                           too) moved to `to`: {moved, review, pick, failed}
  GET    /connections/{name}/references    the cells that name `name` (a deleted one too): the picks
  POST   /connections/{name}/repoint       {to, picks?}: those cells (the ticked ones) name `to`
  POST   /connections/rewrite              the Workbench window's helper: a cell's or a script's text
                                           pointed at another connection (nothing is kept)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.connection_swap import ConnectionSwap


def routes(swap: ConnectionSwap) -> list[BaseRoute]:
    async def state(request: Request) -> Response:
        try:
            return json_response(swap.state(request.path_params["name"]))
        except Exception as error:
            return error_response(error)

    async def change(request: Request) -> Response:
        try:
            body = await read_json(request)
            return json_response(await swap.swap(request.path_params["name"], body, actor(request)))
        except Exception as error:
            return error_response(error)

    async def undo(request: Request) -> Response:
        try:
            return json_response(await swap.undo(request.path_params["name"], actor(request)))
        except Exception as error:
            return error_response(error)

    async def move(request: Request) -> Response:
        try:
            body = await read_json(request)
            return json_response(await swap.move(request.path_params["name"], body, actor(request)))
        except Exception as error:
            return error_response(error)

    async def references(request: Request) -> Response:
        try:
            return json_response(swap.references(request.path_params["name"]))
        except Exception as error:
            return error_response(error)

    async def repoint(request: Request) -> Response:
        try:
            body = await read_json(request)
            return json_response(await swap.repoint(request.path_params["name"], body, actor(request)))
        except Exception as error:
            return error_response(error)

    async def new_query(request: Request) -> Response:
        try:
            body = await read_json(request)
            return json_response(await swap.new_query(request.path_params["name"], body, actor(request)))
        except Exception as error:
            return error_response(error)

    async def rewrite(request: Request) -> Response:
        try:
            return json_response(swap.rewrite(await read_json(request)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/tables/{name}/connection", state),
        Route("/tables/{name}/connection", change, methods=["POST"]),
        Route("/tables/{name}/connection/undo", undo, methods=["POST"]),
        Route("/connections/rewrite", rewrite, methods=["POST"]),
        Route("/datasets/{name}/connection-query", new_query, methods=["POST"]),
        Route("/connections/{name}/move", move, methods=["POST"]),
        Route("/connections/{name}/references", references),
        Route("/connections/{name}/repoint", repoint, methods=["POST"]),
    ]
