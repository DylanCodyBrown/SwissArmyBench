"""Launch, builds and the Performance Analyzer (services/launch.py; the owner, 2026-11-19), for the canvas's
window and the agent (the golden rule: app_launch, app_stop, builds_list, builds_compare, build_relaunch,
build_restore, perf_attach, perf_session, perf_hints).

  POST  /streamlit/apps/{app}/launch              {"analyzer"?: true}: a new build, run in its own window
  GET   /streamlit/apps/{app}/launch              the running launch (its build, address) or none
  DELETE /streamlit/apps/{app}/launch             Stop
  GET   /streamlit/apps/{app}/builds              newest first: number, time, what changed, result
  GET   /streamlit/apps/{app}/builds/{n}          a build's files (Open, read-only)
  GET   /streamlit/apps/{app}/builds/compare?a=&b=  two builds file by file
  POST  /streamlit/apps/{app}/builds/{n}/launch   Relaunch an old build
  POST  /streamlit/apps/{app}/builds/{n}/restore  its cells' code back into the app (plans the window makes)
  POST  /streamlit/apps/{app}/perf                {"on"?: false, "clear"?: true}: attach, pause, a new session
  DELETE /streamlit/apps/{app}/perf               detach (it records nothing more)
  GET   /streamlit/apps/{app}/perf                the session: timeline, calls, caches, socket, hints
  GET   /streamlit/apps/{app}/perf/hints          the hints alone
  POST  /streamlit/apps/{app}/perf/save           the session into its build (perf-<time>.json)
  GET   /streamlit/apps/{app}/builds/{n}/perf/{name}  a saved session
  GET   /streamlit/perf                           the analyzer's window (perf.html)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench_streamlit.services.launch import Launches


def routes(launches: Launches, web_root: Path | None = None) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    async def body_of(request: Request) -> Any:
        return await read_json(request) if int(request.headers.get("content-length") or 0) else {}

    async def launch(request: Request) -> Response:
        app = request.path_params["app"]
        if request.method == "GET":
            return json_response(launches.status(app))
        if request.method == "DELETE":
            return json_response(await launches.stop(app, actor(request)))
        return json_response(await launches.launch(app, await body_of(request), actor(request)))

    async def listing(request: Request) -> Response:
        return json_response(await launches.listing(request.path_params["app"]))

    async def build(request: Request) -> Response:
        return json_response(await launches.files(request.path_params["app"], request.path_params["number"]))

    async def compare(request: Request) -> Response:
        asked = request.query_params
        return json_response(
            await launches.compare(request.path_params["app"], asked.get("a"), asked.get("b"))
        )

    async def relaunch(request: Request) -> Response:
        params = request.path_params
        return json_response(await launches.relaunch(params["app"], params["number"], actor(request)))

    async def restore(request: Request) -> Response:
        params = request.path_params
        return json_response(await launches.restore(params["app"], params["number"], actor(request)))

    async def analyzer(request: Request) -> Response:
        app = request.path_params["app"]
        if request.method == "GET":
            return json_response(launches.session(app))
        if request.method == "DELETE":
            return json_response(launches.detach(app))
        return json_response(launches.attach(app, await body_of(request), actor(request)))

    async def hints(request: Request) -> Response:
        return json_response(launches.hints(request.path_params["app"]))

    async def save(request: Request) -> Response:
        return json_response(await launches.save(request.path_params["app"], actor(request)))

    async def saved(request: Request) -> Response:
        params = request.path_params
        return json_response(await launches.saved(params["app"], params["number"], params["name"]))

    async def window(request: Request) -> Response:
        if web_root is None:
            return Response("The analyzer's page is not here.", 404)
        return FileResponse(web_root / "perf.html", headers={"Cache-Control": "no-store"})

    return [
        Route("/streamlit/apps/{app}/launch", safely(launch), methods=["GET", "POST", "DELETE"]),
        Route("/streamlit/apps/{app}/builds", safely(listing)),
        Route("/streamlit/apps/{app}/builds/compare", safely(compare)),
        Route("/streamlit/apps/{app}/builds/{number}", safely(build)),
        Route("/streamlit/apps/{app}/builds/{number}/launch", safely(relaunch), methods=["POST"]),
        Route("/streamlit/apps/{app}/builds/{number}/restore", safely(restore), methods=["POST"]),
        Route("/streamlit/apps/{app}/builds/{number}/perf/{name}", safely(saved)),
        Route("/streamlit/apps/{app}/perf", safely(analyzer), methods=["GET", "POST", "DELETE"]),
        Route("/streamlit/apps/{app}/perf/hints", safely(hints)),
        Route("/streamlit/apps/{app}/perf/save", safely(save), methods=["POST"]),
        Route("/streamlit/perf", window),
    ]
