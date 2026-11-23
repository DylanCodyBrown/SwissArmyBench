"""Launch, Builds and the Performance Analyzer on the Canvas (services/launch.py), for the Canvas page, the
analyzer's window and the agent (app_launch, canvas_builds and canvas_perf, each by its action).

  POST   /streamlit/canvases/{canvas}/launch              {"analyzer"?: true}: a new build, run in a window
  GET    /streamlit/canvases/{canvas}/launch              the running launch (its build) or none
  DELETE /streamlit/canvases/{canvas}/launch              Stop
  GET    /streamlit/canvases/{canvas}/builds              newest first: number, time, what changed, result
  GET    /streamlit/canvases/{canvas}/builds/compare?a=&b=  two builds file by file (no b: the canvas now)
  GET    /streamlit/canvases/{canvas}/builds/{n}          a build's files (Open, read-only)
  POST   /streamlit/canvases/{canvas}/builds/{n}/launch   Relaunch an old build
  POST   /streamlit/canvases/{canvas}/builds/{n}/restore  its canvas back, one change (Undo takes it back)
  GET    /streamlit/canvases/{canvas}/builds/{n}/perf/{name}  a saved analyzer session
  POST   /streamlit/canvases/{canvas}/perf                {"on"?: false, "clear"?: true}: attach, pause, anew
  DELETE /streamlit/canvases/{canvas}/perf                detach
  GET    /streamlit/canvases/{canvas}/perf                the session: timeline, calls, caches, socket, hints
  GET    /streamlit/canvases/{canvas}/perf/hints          the hints alone
  POST   /streamlit/canvases/{canvas}/perf/save           the session into its build (perf-<time>.json)
  (/streamlit/perf, the analyzer's old address, answers with its Blazor page: server/frontend_pages.py)
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json
from swissarmybench_streamlit.services.launch import Launches


def routes(launches: Launches) -> list[BaseRoute]:
    async def body_of(request: Request) -> Any:
        return await read_json(request) if int(request.headers.get("content-length") or 0) else {}

    def canvas(request: Request) -> str:
        return str(request.path_params["canvas"])

    async def launch(request: Request) -> Response:
        if request.method == "GET":
            return json_response(launches.status(canvas(request)))
        if request.method == "DELETE":
            return json_response(await launches.stop(canvas(request), actor(request)))
        return json_response(await launches.launch(canvas(request), await body_of(request), actor(request)))

    async def listing(request: Request) -> Response:
        return json_response(await launches.listing(canvas(request)))

    async def build(request: Request) -> Response:
        return json_response(await launches.files(canvas(request), request.path_params["number"]))

    async def compare(request: Request) -> Response:
        asked = request.query_params
        return json_response(await launches.compare(canvas(request), asked.get("a"), asked.get("b")))

    async def relaunch(request: Request) -> Response:
        number = request.path_params["number"]
        return json_response(
            await launches.relaunch(canvas(request), number, await body_of(request), actor(request))
        )

    async def restore(request: Request) -> Response:
        number = request.path_params["number"]
        return json_response(
            await launches.restore(canvas(request), number, await body_of(request), actor(request))
        )

    async def analyzer(request: Request) -> Response:
        if request.method == "GET":
            return json_response(launches.session(canvas(request)))
        if request.method == "DELETE":
            return json_response(launches.detach(canvas(request)))
        return json_response(launches.attach(canvas(request), await body_of(request), actor(request)))

    async def hints(request: Request) -> Response:
        return json_response(launches.hints(canvas(request)))

    async def save(request: Request) -> Response:
        return json_response(await launches.save(canvas(request), actor(request)))

    async def saved(request: Request) -> Response:
        params = request.path_params
        return json_response(await launches.saved(canvas(request), params["number"], params["name"]))

    base = "/streamlit/canvases/{canvas}"
    return [
        Route(f"{base}/launch", launch, methods=["GET", "POST", "DELETE"]),
        Route(f"{base}/builds", listing),
        Route(f"{base}/builds/compare", compare),
        Route(f"{base}/builds/{{number}}", build),
        Route(f"{base}/builds/{{number}}/launch", relaunch, methods=["POST"]),
        Route(f"{base}/builds/{{number}}/restore", restore, methods=["POST"]),
        Route(f"{base}/builds/{{number}}/perf/{{name}}", saved),
        Route(f"{base}/perf", analyzer, methods=["GET", "POST", "DELETE"]),
        Route(f"{base}/perf/hints", hints),
        Route(f"{base}/perf/save", save, methods=["POST"]),
    ]
