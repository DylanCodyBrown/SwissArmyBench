"""The Power BI project's door (services/project.py), for its page and the agent.

POST /powerbi/import                       {path, name?, folder?, dataset?, dry_run?}: a .pbix as a project
POST /powerbi/file-connection              {name, path}: a .pbix file connection (pbixray)
GET  /powerbi/file-connection/{name}       its card: path, tables, "as of", read-only and why, portability
POST /powerbi/file-connection/{name}/relationships   the file's relationships into the model and the ERD
GET  /powerbi/setup                        To finish setting up; POST: one row's fix
GET  /powerbi/source                       Read Power BI from; PUT {source}: switched, the grids read again
GET  /powerbi/registration                 the project's app registration; PUT {registration, dry_run?}
GET  /powerbi/live                         Edit in Power BI Desktop: the running Desktops, Live or Not open
GET  /powerbi/live/model                   the open model's metadata (names only)
POST /powerbi/live/plan                    {changes?}: the dry run (none sent: our relationships and measures)
POST /powerbi/live/apply                   the same, made (each change audited; the agent's on Allow)
POST /powerbi/opened                       {path}: a Power BI file opened with the app, offered on its page
GET  /powerbi/page                         the Power BI page, as data
GET  /powerbi/panel                        the same, drawn by the base's generic panel; POST {choice, value}
| {action}
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench_powerbi.services.live_link import LiveLink
from swissarmybench_powerbi.services.project import PowerBIProject


def door(work: Callable[[Request], Awaitable[Any]]) -> Callable[[Request], Awaitable[Response]]:
    async def answer(request: Request) -> Response:
        return json_response(await work(request))

    return safely(answer)


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

    async def registration(r: Request) -> Any:
        body = await read_json(r) if r.method == "PUT" else {}
        return await project.registration(body, actor(r))

    async def panel(r: Request) -> Any:
        body = await read_json(r) if r.method == "POST" else {}
        return await project.panel(body, actor(r))

    async def opened(r: Request) -> Any:
        return project.opened(await read_json(r))

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
        Route("/powerbi/registration", door(registration), methods=["GET", "PUT"]),
        Route("/powerbi/page", door(page)),
        Route("/powerbi/opened", door(opened), methods=["POST"]),
        Route("/powerbi/panel", door(panel), methods=["GET", "POST"]),
    ]


def live_routes(live: LiveLink) -> list[BaseRoute]:
    async def status(r: Request) -> Any:
        return await live.status(r.query_params.get("asked") in ("1", "true"))

    async def model(r: Request) -> Any:
        return await live.model()

    async def plan(r: Request) -> Any:
        return await live.plan(await read_json(r))

    async def apply(r: Request) -> Any:
        return await live.apply(await read_json(r), actor(r))

    return [
        Route("/powerbi/live", door(status)),
        Route("/powerbi/live/model", door(model)),
        Route("/powerbi/live/plan", door(plan), methods=["POST"]),
        Route("/powerbi/live/apply", door(apply), methods=["POST"]),
    ]
