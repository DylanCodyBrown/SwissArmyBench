"""The Canvas (services/canvas.py), for the Canvas page and the agent.

(/streamlit/canvas, the old Canvas page's address, answers with its Blazor page: server/frontend_pages.py)
GET    /streamlit/canvases?folder=             the project's canvases (and old .stapp.json files, said)
POST   /streamlit/canvases                     {"path"} or {"name", "folder"?}: open (a new one is made)
GET    /streamlit/canvases/{canvas}            its model, version, read-only, broken, missing, marks, notes
DELETE /streamlit/canvases/{canvas}            closed (its Play stopped)
POST   /streamlit/canvases/{canvas}/command    {"kind", "version"?, "window"?, ...}: one rule-checked change
                                               (kind "wire": {id, port, wire}: an In's source, an Event's
                                               actions; null unwires)
POST   /streamlit/canvases/{canvas}/undo       and /redo
POST   /streamlit/canvases/{canvas}/play       {"page"?}: the pages built and run live: its address
POST   /streamlit/canvases/{canvas}/stop
POST   /streamlit/canvases/{canvas}/check      every page headless (AppTest): each widget's errors
POST   /streamlit/canvases/{canvas}/export     {"folder"}: the app that runs alone (the agent's on Allow)
POST   /streamlit/canvases/{canvas}/full-screen {"on"?}: its page full screen or back (none: toggled)
(Launch, Builds and the Performance Analyzer: routes_launch.py)
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json
from swissarmybench_streamlit.services.canvas import Canvases


def routes(canvases: Canvases) -> list[BaseRoute]:
    async def body_of(request: Request) -> Any:
        return await read_json(request) if int(request.headers.get("content-length") or 0) else {}

    def name_of(request: Request) -> str:
        return str(request.path_params["canvas"])

    async def listing(request: Request) -> Response:
        if request.method == "POST":
            return json_response(await canvases.open(await body_of(request), actor(request)))
        return json_response(canvases.listing(request.query_params.get("folder") or None))

    async def one(request: Request) -> Response:
        if request.method == "DELETE":
            return json_response(await canvases.close(name_of(request)))
        return json_response(canvases.state(name_of(request)))

    async def command(request: Request) -> Response:
        return json_response(await canvases.command(name_of(request), await body_of(request), actor(request)))

    async def undo(request: Request) -> Response:
        return json_response(await canvases.undo(name_of(request), await body_of(request), actor(request)))

    async def redo(request: Request) -> Response:
        return json_response(
            await canvases.undo(name_of(request), await body_of(request), actor(request), redo=True)
        )

    async def play(request: Request) -> Response:
        return json_response(await canvases.play(name_of(request), await body_of(request), actor(request)))

    async def stop(request: Request) -> Response:
        return json_response(await canvases.stop(name_of(request), await body_of(request)))

    async def check(request: Request) -> Response:
        return json_response(await canvases.check(name_of(request), await body_of(request), actor(request)))

    async def export(request: Request) -> Response:
        return json_response(await canvases.export(name_of(request), await body_of(request), actor(request)))

    async def full_screen(request: Request) -> Response:
        return json_response(
            await canvases.full_screen(name_of(request), await body_of(request), actor(request))
        )

    return [
        Route("/streamlit/canvases/{canvas}/full-screen", full_screen, methods=["POST"]),
        Route("/streamlit/canvases", listing, methods=["GET", "POST"]),
        Route("/streamlit/canvases/{canvas}", one, methods=["GET", "DELETE"]),
        Route("/streamlit/canvases/{canvas}/command", command, methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/undo", undo, methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/redo", redo, methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/play", play, methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/stop", stop, methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/check", check, methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/export", export, methods=["POST"]),
    ]
