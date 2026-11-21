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

from swissarmybench.server.http import json_response, read_json, safely, with_body
from swissarmybench.services.sab_projects import SabProjects


def routes(projects: SabProjects) -> list[BaseRoute]:
    async def state(request: Request) -> Response:
        return json_response(projects.state())

    async def layout(request: Request) -> Response:
        return json_response(await projects.layout(await read_json(request)))

    async def forget(request: Request) -> Response:
        return json_response(await projects.forget(await read_json(request)))

    return [
        Route("/project", safely(state), methods=["GET"]),
        Route("/project/new", with_body(projects.new), methods=["POST"]),
        Route("/project/open", with_body(projects.open), methods=["POST"]),
        Route("/project/save", with_body(projects.save), methods=["POST"]),
        Route("/project/close", with_body(projects.close), methods=["POST"]),
        Route("/project/copy", with_body(projects.copy), methods=["POST"]),
        Route("/project/fix", with_body(projects.fix), methods=["POST"]),
        Route("/project/autosave", with_body(projects.set_autosave), methods=["POST"]),
        Route("/project/private", with_body(projects.set_private), methods=["POST"]),
        Route("/project/layout", safely(layout), methods=["POST"]),
        Route("/project/recent/remove", safely(forget), methods=["POST"]),
    ]
