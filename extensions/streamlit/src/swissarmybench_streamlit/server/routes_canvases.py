"""The Canvas (services/canvas.py), for the Canvas page and the agent.

GET    /streamlit/canvas                       the Canvas page (canvas.html)
GET    /streamlit/canvases?folder=             the project's canvases (and old .stapp.json files, said)
POST   /streamlit/canvases                     {"path"} or {"name", "folder"?}: open (a new one is made)
GET    /streamlit/canvases/{canvas}            its model, version, read-only, broken, missing, marks, notes
DELETE /streamlit/canvases/{canvas}            closed (its Play stopped)
POST   /streamlit/canvases/{canvas}/command    {"kind", "version"?, "window"?, ...}: one rule-checked change
POST   /streamlit/canvases/{canvas}/undo       and /redo
POST   /streamlit/canvases/{canvas}/play       {"page"?}: the pages built and run live: its address
POST   /streamlit/canvases/{canvas}/stop
POST   /streamlit/canvases/{canvas}/check      every page headless (AppTest): each widget's errors
POST   /streamlit/canvases/{canvas}/export     {"folder"}: the app that runs alone (the agent's on Allow)
POST   /streamlit/canvases/{canvas}/launch     a build in the project's builds/ and the app run from it
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench_streamlit.services.canvas import Canvases


def routes(canvases: Canvases, web_root: Path | None) -> list[BaseRoute]:
    async def body_of(request: Request) -> Any:
        return await read_json(request) if int(request.headers.get("content-length") or 0) else {}

    def name_of(request: Request) -> str:
        return str(request.path_params["canvas"])

    async def page(request: Request) -> Response:
        if web_root is None or not (web_root / "canvas.html").is_file():
            return Response("The Canvas page is not here.", 404)
        return FileResponse(web_root / "canvas.html", headers={"Cache-Control": "no-store"})

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
        return json_response(await canvases.stop(name_of(request)))

    async def check(request: Request) -> Response:
        return json_response(await canvases.check(name_of(request), await body_of(request), actor(request)))

    async def export(request: Request) -> Response:
        return json_response(await canvases.export(name_of(request), await body_of(request), actor(request)))

    async def launch(request: Request) -> Response:
        return json_response(await canvases.launch(name_of(request), await body_of(request), actor(request)))

    return [
        Route("/streamlit/canvas", page),
        Route("/streamlit/canvases", safely(listing), methods=["GET", "POST"]),
        Route("/streamlit/canvases/{canvas}", safely(one), methods=["GET", "DELETE"]),
        Route("/streamlit/canvases/{canvas}/command", safely(command), methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/undo", safely(undo), methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/redo", safely(redo), methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/play", safely(play), methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/stop", safely(stop), methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/check", safely(check), methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/export", safely(export), methods=["POST"]),
        Route("/streamlit/canvases/{canvas}/launch", safely(launch), methods=["POST"]),
    ]
