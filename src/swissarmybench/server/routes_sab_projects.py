"""A project is a folder (services/sab_projects.py), for the home page, the Workbench and the agent (the
golden rule).

GET  /project               the open project (its unsaved mark, tables that need a fix), the recent ones
POST /project/new           {"name", "folder"?, "path"?, "type"?, "app"?, "notebooks"?, "autosave"?,
                            "discard"?}: a new project folder, scaffolded, opened, its .sab/ written
POST /project/autosave      {"on"}: autosave on or off (kept in .sab/project.json)
POST /project/private       {"on"}: nothing of the project sent out by an extension (the agent's on Allow)
POST /project/open          {"path", "make"?, "discard"?, "ask"?} | {"cancel": true}: a project's folder
POST /project/save          {"keep_rows"?}: .sab/ written (no project open: {"path"} makes the work one)
POST /project/copy          {"path", "data"?, "folder"?}: Copy project to (a new or empty folder)
POST /project/close         {"discard"?}
POST /project/fix           {"table", "path"?, "remove"?}: a table that did not come back
POST /project/layout        {"window", "layout", "unsaved"?}: a window's layout, for the next save
POST /project/recent/remove {"path"}: off the recent list
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench.services.sab_projects import SabProjects


def routes(projects: SabProjects) -> list[BaseRoute]:
    async def state(request: Request) -> Response:
        return json_response(projects.state())

    async def new(request: Request) -> Response:
        return json_response(await projects.new(await read_json(request), actor(request)))

    async def open_project(request: Request) -> Response:
        return json_response(await projects.open(await read_json(request), actor(request)))

    async def save(request: Request) -> Response:
        return json_response(await projects.save(await read_json(request), actor(request)))

    async def copy(request: Request) -> Response:
        return json_response(await projects.copy(await read_json(request), actor(request)))

    async def close(request: Request) -> Response:
        return json_response(await projects.close(await read_json(request), actor(request)))

    async def autosave(request: Request) -> Response:
        return json_response(await projects.set_autosave(await read_json(request), actor(request)))

    async def private(request: Request) -> Response:
        return json_response(await projects.set_private(await read_json(request), actor(request)))

    async def fix(request: Request) -> Response:
        return json_response(await projects.fix(await read_json(request), actor(request)))

    async def layout(request: Request) -> Response:
        return json_response(await projects.layout(await read_json(request)))

    async def forget(request: Request) -> Response:
        return json_response(await projects.forget(await read_json(request)))

    return [
        Route("/project", safely(state), methods=["GET"]),
        Route("/project/new", safely(new), methods=["POST"]),
        Route("/project/open", safely(open_project), methods=["POST"]),
        Route("/project/save", safely(save), methods=["POST"]),
        Route("/project/close", safely(close), methods=["POST"]),
        Route("/project/copy", safely(copy), methods=["POST"]),
        Route("/project/fix", safely(fix), methods=["POST"]),
        Route("/project/autosave", safely(autosave), methods=["POST"]),
        Route("/project/private", safely(private), methods=["POST"]),
        Route("/project/layout", safely(layout), methods=["POST"]),
        Route("/project/recent/remove", safely(forget), methods=["POST"]),
    ]
