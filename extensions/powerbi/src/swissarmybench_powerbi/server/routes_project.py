"""The Power BI project's door (services/project.py), for its page and the agent.

POST /powerbi/import                       {path, name?, folder?, dataset?, dry_run?}: a .pbix as a project
POST /powerbi/file-connection              {name, path}: a .pbix file connection (pbixray)
GET  /powerbi/file-connection/{name}       its card: path, tables, "as of", read-only and why, portability
POST /powerbi/file-connection/{name}/relationships   the file's relationships into the model and the ERD
GET  /powerbi/setup                        To finish setting up; POST: one row's fix
GET  /powerbi/source                       Read Power BI from; PUT {source}: switched, the grids read again
GET  /powerbi/page                         the Power BI page, as data
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench_powerbi.services.project import PowerBIProject


def door(work: Callable[[Request], Awaitable[Any]]) -> Callable[[Request], Awaitable[Response]]:
    async def answer(request: Request) -> Response:
        try:
            return json_response(await work(request))
        except Exception as error:
            return error_response(error)

    return answer


def routes(project: PowerBIProject) -> list[BaseRoute]:
    async def imported(r: Request) -> Any:
        return await project.import_project(await read_json(r), actor(r))

    async def add(r: Request) -> Any:
        return await project.add_file_connection(await read_json(r), actor(r))

    async def card(r: Request) -> Any:
        return await project.describe(r.path_params["name"])

    async def joins(r: Request) -> Any:
        return await project.file_relationships(r.path_params["name"], actor(r))

    async def setup(r: Request) -> Any:
        return {"to_finish": await project.to_finish()}

    async def fix(r: Request) -> Any:
        return await project.fix(await read_json(r), actor(r))

    async def source(r: Request) -> Any:
        return project.source()

    async def switch(r: Request) -> Any:
        return await project.set_source(await read_json(r), actor(r))

    async def page(r: Request) -> Any:
        return await project.page()

    return [
        Route("/powerbi/import", door(imported), methods=["POST"]),
        Route("/powerbi/file-connection", door(add), methods=["POST"]),
        Route("/powerbi/file-connection/{name}", door(card)),
        Route("/powerbi/file-connection/{name}/relationships", door(joins), methods=["POST"]),
        Route("/powerbi/setup", door(setup)),
        Route("/powerbi/setup", door(fix), methods=["POST"]),
        Route("/powerbi/source", door(source)),
        Route("/powerbi/source", door(switch), methods=["PUT"]),
        Route("/powerbi/page", door(page)),
    ]
