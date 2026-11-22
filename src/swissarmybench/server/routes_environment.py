"""The Environment (services/environment.py): everything the project holds. The agent's one tool for all of
it is `environment` (its action names the route).

GET   /environment                      ?search=: every row, or the ones found (each tab's count)        list
GET   /environment/show                 ?kind=&name=: one row whole (every place that uses it)            show
GET   /environment/columns              ?name=: an open table's columns (type, range, blanks)             show
POST  /environment/open                 {"kind", "name"}: where it opens (a table: a grid, its view)  open
POST  /environment/insert               {"kind", "name"}: what it is inserted into code as  insert
POST  /environment/rename               {"kind", "name", "to"}  rename
POST  /environment/remove               {"kind", "name", "python"?} (a file's delete: agent on Allow)  remove
POST  /environment/keep                 {"name", "keep"}: its rows with the project (agent: on Allow)     keep
POST  /environment/clear                {"tables", "variables", "structures", "dry_run"?} (agent: Allow) clear
GET   /environment/libraries            ?check=1: the project's libraries (check: ask the index)  libraries
POST  /environment/libraries/install    {"name"} (agent: on Allow)  install
POST  /environment/libraries/update     {"name"} or {"all": true} (agent: on Allow)  update
POST  /environment/libraries/pin        {"name", "pinned"} (agent: on Allow)                              pin
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, read_json, with_body
from swissarmybench.services.environment import Environment


def routes(environment: Environment) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(await environment.listing(request.query_params.get("search")))

    async def show(request: Request) -> Response:
        query = request.query_params
        return json_response(await environment.show(query.get("kind"), query.get("name")))

    async def columns(request: Request) -> Response:
        return json_response(await environment.columns(request.query_params.get("name")))

    async def insert(request: Request) -> Response:
        return json_response(environment.insert(await read_json(request)))

    async def libraries(request: Request) -> Response:
        return json_response(await environment.libraries(request.query_params.get("check") in ("1", "true")))

    return [
        Route("/environment", listing, methods=["GET"]),
        Route("/environment/show", show, methods=["GET"]),
        Route("/environment/columns", columns, methods=["GET"]),
        Route("/environment/open", with_body(environment.open), methods=["POST"]),
        Route("/environment/insert", insert, methods=["POST"]),
        Route("/environment/rename", with_body(environment.rename), methods=["POST"]),
        Route("/environment/remove", with_body(environment.remove), methods=["POST"]),
        Route("/environment/keep", with_body(environment.keep), methods=["POST"]),
        Route("/environment/clear", with_body(environment.clear), methods=["POST"]),
        Route("/environment/libraries", libraries, methods=["GET"]),
        Route("/environment/libraries/install", with_body(environment.install), methods=["POST"]),
        Route("/environment/libraries/update", with_body(environment.update), methods=["POST"]),
        Route("/environment/libraries/pin", with_body(environment.pin), methods=["POST"]),
    ]
