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
POST /scripts/library-file    {path}: a library's source, read-only (go to definition outside the project)
POST /scripts/files/package   {name, parent?}: a new package (its __init__.py)
POST /scripts/files/move      {path, to, apply?}: rename a module or package, its imports following (the plan)
POST /scripts/files/duplicate {path}: a copy beside it
POST /scripts/files/delete    {path}: to the system's trash (the user's own: 403 for the agent)
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

    async def library_file(request: Request) -> Response:
        return json_response(await ide.library_file(await read_json(request)))

    async def new_package(request: Request) -> Response:
        return json_response(await ide.new_package(await read_json(request), actor(request)))

    async def move(request: Request) -> Response:
        return json_response(await ide.move(await read_json(request), actor(request)))

    async def duplicate(request: Request) -> Response:
        return json_response(await ide.duplicate(await read_json(request), actor(request)))

    async def delete(request: Request) -> Response:
        return json_response(await ide.delete(await read_json(request), actor(request)))

    return [
        Route("/scripts/tree", safely(tree), methods=["GET"]),
        Route("/scripts/fine-tune", safely(fine_tune), methods=["POST"]),
        Route("/scripts/definition", safely(definition), methods=["POST"]),
        Route("/scripts/references", safely(references), methods=["POST"]),
        Route("/scripts/rename", safely(rename), methods=["POST"]),
        Route("/scripts/search", safely(search), methods=["POST"]),
        Route("/scripts/replace", safely(replace), methods=["POST"]),
        Route("/scripts/format", safely(format_), methods=["POST"]),
        Route("/scripts/library-file", safely(library_file), methods=["POST"]),
        Route("/scripts/files/package", safely(new_package), methods=["POST"]),
        Route("/scripts/files/move", safely(move), methods=["POST"]),
        Route("/scripts/files/duplicate", safely(duplicate), methods=["POST"]),
        Route("/scripts/files/delete", safely(delete), methods=["POST"]),
    ]
