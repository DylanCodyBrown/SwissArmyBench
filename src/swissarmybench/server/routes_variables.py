"""The Variables page (services/variables.py): the project's variables, where each comes from, what uses it.

GET    /variables              ?search=&source=: every variable; plain values only            variables_list
PUT    /variables              {"name", "value", "from": "value"|"keyring"}: add or change    variables_set
POST   /variables/rename       {"name", "to"}: renamed, connections and Run settings with it  variables_rename
DELETE /variables/{name}       the project's variable, or a key vault's entry                 variables_remove
POST   /variables/reveal       {"name"}: Show (the user's only: 403 for the agent)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.variables import Variables


def routes(variables: Variables) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        try:
            if request.method == "PUT":
                return json_response(await variables.put(await read_json(request), actor(request)))
            query = request.query_params
            return json_response(variables.listing(query.get("search"), query.get("source")))
        except Exception as error:
            return error_response(error)

    async def rename(request: Request) -> Response:
        try:
            return json_response(await variables.rename(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    async def remove(request: Request) -> Response:
        try:
            name = request.path_params["name"]
            return json_response(await variables.remove({"name": name}, actor(request)))
        except Exception as error:
            return error_response(error)

    async def reveal(request: Request) -> Response:
        try:
            return json_response(variables.reveal(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/variables", listing, methods=["GET", "PUT"]),
        Route("/variables/rename", rename, methods=["POST"]),
        Route("/variables/reveal", reveal, methods=["POST"]),
        Route("/variables/{name}", remove, methods=["DELETE"]),
    ]
