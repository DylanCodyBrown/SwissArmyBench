"""Streamlit pieces and the page designer (services/streamlit.py), for the Workbench window, the page
designer's window and the agent (the golden rule: every action here has its command).

  GET    /designer                              the page designer (its own window)
  GET    /streamlit/apps                        the open apps: one for each document with Streamlit cells
  POST   /streamlit/apps   {"title", "pieces", "pages", "python", "window"} | {"path"}: open one
  GET    /streamlit/apps/{app}                  its pieces (name, what each makes and reads, state),
                                                its pages and their layouts, where it is shown
  PUT    /streamlit/apps/{app}                  {"pieces", ...}: the document as the window holds it now
  DELETE /streamlit/apps/{app}                  the document closed: the app goes
  POST   /streamlit/apps/{app}/run              run or refresh the app (start its Streamlit process)
  POST   /streamlit/apps/{app}/stop             stop its process
  POST   /streamlit/apps/{app}/install          Streamlit, pandas and pyarrow into the notebook's Python
  POST   /streamlit/apps/{app}/export           {"folder"}: the designed pages as a runnable folder
  POST   /streamlit/apps/{app}/pages            {"name"?, "cell"?}: a new page (with a first piece)
  PATCH  /streamlit/apps/{app}/pages/{page}     {"name"} rename, {"index"} move among the pages
  DELETE /streamlit/apps/{app}/pages/{page}
  POST   /streamlit/apps/{app}/pages/{page}/pieces          {"cell", "index"?, "w"?, "h"?}: push a piece
  PATCH  /streamlit/apps/{app}/pages/{page}/pieces/{piece}  {"index"} move, {"w", "h"} resize, {"page"}
  DELETE /streamlit/apps/{app}/pages/{page}/pieces/{piece}  take it off the page

The live pages themselves are passed through by server/streamlit_proxy.py (/streamlit/live/...).
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmygrid.server.http import actor, error_response, json_response, read_json
from swissarmygrid.services.streamlit import StreamlitApps


def routes(apps: StreamlitApps) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    async def body_of(request: Request) -> Any:
        return await read_json(request) if int(request.headers.get("content-length") or 0) else {}

    async def listing(request: Request) -> Response:
        return json_response(apps.listing())

    async def open_app(request: Request) -> Response:
        return json_response(await apps.open(await body_of(request), actor(request)))

    async def state(request: Request) -> Response:
        return json_response(apps.state(request.path_params["app"]))

    async def sync(request: Request) -> Response:
        return json_response(await apps.sync(request.path_params["app"], await body_of(request)))

    async def close(request: Request) -> Response:
        await apps.close(request.path_params["app"])
        return json_response({"ok": True})

    async def run(request: Request) -> Response:
        return json_response(
            await apps.run(request.path_params["app"], await body_of(request), actor(request))
        )

    async def stop(request: Request) -> Response:
        return json_response(await apps.stop(request.path_params["app"], actor(request)))

    async def install(request: Request) -> Response:
        return json_response(await apps.install(request.path_params["app"], actor(request)))

    async def export(request: Request) -> Response:
        return json_response(
            await apps.export(request.path_params["app"], await body_of(request), actor(request))
        )

    async def add_page(request: Request) -> Response:
        return json_response(
            await apps.add_page(request.path_params["app"], await body_of(request), actor(request))
        )

    async def change_page(request: Request) -> Response:
        params = request.path_params
        return json_response(
            await apps.change_page(params["app"], params["page"], await body_of(request), actor(request))
        )

    async def remove_page(request: Request) -> Response:
        params = request.path_params
        return json_response(await apps.remove_page(params["app"], params["page"], actor(request)))

    async def push(request: Request) -> Response:
        params = request.path_params
        return json_response(
            await apps.push(params["app"], params["page"], await body_of(request), actor(request))
        )

    async def change_piece(request: Request) -> Response:
        params = request.path_params
        return json_response(
            await apps.change_piece(
                params["app"], params["page"], params["piece"], await body_of(request), actor(request)
            )
        )

    async def remove_piece(request: Request) -> Response:
        params = request.path_params
        return json_response(
            await apps.remove_piece(params["app"], params["page"], params["piece"], actor(request))
        )

    piece = "/streamlit/apps/{app}/pages/{page}/pieces/{piece}"
    return [
        Route("/streamlit/apps", safely(listing)),
        Route("/streamlit/apps", safely(open_app), methods=["POST"]),
        Route("/streamlit/apps/{app}", safely(state)),
        Route("/streamlit/apps/{app}", safely(sync), methods=["PUT"]),
        Route("/streamlit/apps/{app}", safely(close), methods=["DELETE"]),
        Route("/streamlit/apps/{app}/run", safely(run), methods=["POST"]),
        Route("/streamlit/apps/{app}/stop", safely(stop), methods=["POST"]),
        Route("/streamlit/apps/{app}/install", safely(install), methods=["POST"]),
        Route("/streamlit/apps/{app}/export", safely(export), methods=["POST"]),
        Route("/streamlit/apps/{app}/pages", safely(add_page), methods=["POST"]),
        Route("/streamlit/apps/{app}/pages/{page}", safely(change_page), methods=["PATCH"]),
        Route("/streamlit/apps/{app}/pages/{page}", safely(remove_page), methods=["DELETE"]),
        Route("/streamlit/apps/{app}/pages/{page}/pieces", safely(push), methods=["POST"]),
        Route(piece, safely(change_piece), methods=["PATCH"]),
        Route(piece, safely(remove_piece), methods=["DELETE"]),
    ]
