"""Projects as one .sab file (services/sab_projects.py), for the home page, the Workbench and the agent
(the golden rule).

GET  /project               the open project (its unsaved mark, tables that need a fix), the recent ones
POST /project/new           {"name"?, "discard"?}: a new project
POST /project/open          {"path", "discard"?, "ask"?} | {"cancel": true}: a .sab (or a project folder)
POST /project/save          {"keep_rows"?, "path"?, "folder"?}: Save (path: Save as; folder: a folder
                            project saved as one .sab)
POST /project/close         {"discard"?}
POST /project/fix           {"table", "path"?, "remove"?}: a table that did not come back
POST /project/layout        {"window", "layout", "unsaved"?}: a window's layout, for the next save
POST /project/recent/remove {"path"}: off the recent list
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.sab_projects import SabProjects


def routes(projects: SabProjects) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    async def state(request: Request) -> Response:
        return json_response(projects.state())

    async def new(request: Request) -> Response:
        return json_response(await projects.new(await read_json(request), actor(request)))

    async def open_project(request: Request) -> Response:
        return json_response(await projects.open(await read_json(request), actor(request)))

    async def save(request: Request) -> Response:
        return json_response(await projects.save(await read_json(request), actor(request)))

    async def close(request: Request) -> Response:
        return json_response(await projects.close(await read_json(request), actor(request)))

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
        Route("/project/fix", safely(fix), methods=["POST"]),
        Route("/project/layout", safely(layout), methods=["POST"]),
        Route("/project/recent/remove", safely(forget), methods=["POST"]),
    ]
