"""The Scripts IDE (services/script_ide.py), for the page and the agent alike (workbench_definition,
workbench_references, workbench_rename, workbench_search, workbench_replace, workbench_format).

GET  /scripts/tree         the explorer: the project's code, the library's, what the app generates
POST /scripts/fine-tune    {table}: its transformations as a new script in scripts/
POST /scripts/definition   {text, line, column, path}: where the name at the cursor is defined (F12)
POST /scripts/references   the same: every use across the project (Shift+F12)
POST /scripts/rename       {text, line, column, path, to, apply?}: the plan, or applied (F2)
POST /scripts/search       {query, regex?, case?, word?}: across the project's scripts
POST /scripts/replace      {query, to, ..., apply?}: the plan, or applied
POST /scripts/format       {text, python?}: Ruff's format in the script's Python
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench.services.script_ide import ScriptIde


def routes(ide: ScriptIde) -> list[BaseRoute]:
    async def tree(request: Request) -> Response:
        return json_response(await ide.tree())

    async def fine_tune(request: Request) -> Response:
        return json_response(await ide.fine_tune(await read_json(request), actor(request)))

    async def definition(request: Request) -> Response:
        return json_response(await ide.definition(await read_json(request)))

    async def references(request: Request) -> Response:
        return json_response(await ide.references(await read_json(request)))

    async def rename(request: Request) -> Response:
        return json_response(await ide.rename(await read_json(request), actor(request)))

    async def search(request: Request) -> Response:
        return json_response(ide.search(await read_json(request)))

    async def replace(request: Request) -> Response:
        return json_response(await ide.replace(await read_json(request), actor(request)))

    async def format_(request: Request) -> Response:
        return json_response(await ide.format(await read_json(request)))

    return [
        Route("/scripts/tree", safely(tree), methods=["GET"]),
        Route("/scripts/fine-tune", safely(fine_tune), methods=["POST"]),
        Route("/scripts/definition", safely(definition), methods=["POST"]),
        Route("/scripts/references", safely(references), methods=["POST"]),
        Route("/scripts/rename", safely(rename), methods=["POST"]),
        Route("/scripts/search", safely(search), methods=["POST"]),
        Route("/scripts/replace", safely(replace), methods=["POST"]),
        Route("/scripts/format", safely(format_), methods=["POST"]),
    ]
