"""The Variables page (services/variables.py): this computer's variables, where each comes from, its uses.

GET    /variables              ?search=&source=: every variable; plain values only            variables_list
PUT    /variables              {"name", "value", "from", "local"}: add or change           variables_set
POST   /variables/rename       {"name", "to"}: renamed, connections and Run settings with it  variables_rename
DELETE /variables/{name}       a variable of this computer, or a key vault's entry       variables_remove
POST   /variables/reveal       {"name"}: Show (the user's only: 403 for the agent)
POST   /variables/resolve      {"text"}: what a box's ${NAME} reads here (a secret masked)  variables_resolve
GET    /variables/uses         ?name=: what reads each variable (fields by setting, code)    variables_uses
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, with_body
from swissarmybench.services.variables import Variables


def routes(variables: Variables) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        if request.method == "PUT":
            return json_response(await variables.put(await read_json(request), actor(request)))
        query = request.query_params
        return json_response(variables.listing(query.get("search"), query.get("source")))

    async def remove(request: Request) -> Response:
        name = request.path_params["name"]
        return json_response(await variables.remove({"name": name}, actor(request)))

    async def reveal(request: Request) -> Response:
        return json_response(variables.reveal(await read_json(request), actor(request)))

    async def resolve(request: Request) -> Response:
        return json_response(variables.preview(await read_json(request)))

    async def uses(request: Request) -> Response:
        return json_response(variables.uses(request.query_params.get("name")))

    return [
        Route("/variables", listing, methods=["GET", "PUT"]),
        Route("/variables/resolve", resolve, methods=["POST"]),
        Route("/variables/uses", uses, methods=["GET"]),
        Route("/variables/rename", with_body(variables.rename), methods=["POST"]),
        Route("/variables/reveal", reveal, methods=["POST"]),
        Route("/variables/{name}", remove, methods=["DELETE"]),
    ]
