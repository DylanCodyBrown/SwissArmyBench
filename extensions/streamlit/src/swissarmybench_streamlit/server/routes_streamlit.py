"""Streamlit in the Workbench (services/streamlit.py), for the Workbench window and the agent (the
golden rule: every action here has its command).

  GET    /streamlit/apps                        the open apps: a canvas for each open Streamlit app,
                                                one for each open notebook or script
  GET    /streamlit/cells?folder=               the Streamlit cells pane: every Python cell that calls
                                                Streamlit, by document (and the project's files)
  POST   /streamlit/apps   {"path"} | {"title", "cells", ...} | {"canvas": true, "pages", ...}: open one
  GET    /streamlit/apps/{app}                  a canvas: its pages, blocks and their state; a
                                                document's: its live cells
  PUT    /streamlit/apps/{app}                  the document as the window holds it now
  DELETE /streamlit/apps/{app}                  the document closed: the app goes
  POST   /streamlit/apps/{app}/run              Play: run or refresh the app
  POST   /streamlit/apps/{app}/stop             stop its process
  POST   /streamlit/apps/{app}/install          Streamlit, pandas and pyarrow into its Python
  POST   /streamlit/apps/{app}/export           {"folder"}: the pages as a folder that runs alone
  POST   /streamlit/apps/{app}/save-as          {"path"}: the project as one zip
  POST   /streamlit/apps/{app}/pages            {"name"?, "document"?, "cell"?}: a new page
  PATCH  /streamlit/apps/{app}/pages/{page}     {"name"} rename, {"index"} move among the pages
  DELETE /streamlit/apps/{app}/pages/{page}
  POST   /streamlit/apps/{app}/pages/{page}/blocks          {"document", "cell", "row"?, "column"?, "w"?}
  PATCH  /streamlit/apps/{app}/pages/{page}/blocks/{block}  {"row", "column", "insert"?}, {"w", "h"}, {"page"}
  DELETE /streamlit/apps/{app}/pages/{page}/blocks/{block}  take it off the page
  PUT    /streamlit/apps/{app}/settings         the page settings: {"title", "icon", "layout", "logo",
                                                "colours"}
  GET    /streamlit/apps/{app}/session          the live page's session state, each key with its block

The live pages themselves are passed through by server/streamlit_proxy.py (/streamlit/live/...).
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench_streamlit.services.streamlit import StreamlitApps


def routes(apps: StreamlitApps) -> list[BaseRoute]:
    async def body_of(request: Request) -> Any:
        return await read_json(request) if int(request.headers.get("content-length") or 0) else {}

    async def listing(request: Request) -> Response:
        return json_response(apps.listing())

    async def pane(request: Request) -> Response:
        return json_response(apps.pane(request.query_params.get("folder") or None))

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

    async def save_as(request: Request) -> Response:
        return json_response(
            await apps.save_as(request.path_params["app"], await body_of(request), actor(request))
        )

    async def place(request: Request) -> Response:
        params = request.path_params
        return json_response(
            await apps.place(params["app"], params["page"], await body_of(request), actor(request))
        )

    async def change_block(request: Request) -> Response:
        params = request.path_params
        return json_response(
            await apps.change_block(
                params["app"], params["page"], params["block"], await body_of(request), actor(request)
            )
        )

    async def remove_block(request: Request) -> Response:
        params = request.path_params
        return json_response(
            await apps.remove_block(params["app"], params["page"], params["block"], actor(request))
        )

    async def settings(request: Request) -> Response:
        return json_response(
            await apps.set_settings(request.path_params["app"], await body_of(request), actor(request))
        )

    async def session(request: Request) -> Response:
        return json_response(apps.session(request.path_params["app"]))

    block = "/streamlit/apps/{app}/pages/{page}/blocks/{block}"
    return [
        Route("/streamlit/apps", safely(listing)),
        Route("/streamlit/cells", safely(pane)),
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
        Route("/streamlit/apps/{app}/save-as", safely(save_as), methods=["POST"]),
        Route("/streamlit/apps/{app}/pages/{page}/blocks", safely(place), methods=["POST"]),
        Route(block, safely(change_block), methods=["PATCH"]),
        Route(block, safely(remove_block), methods=["DELETE"]),
        Route("/streamlit/apps/{app}/settings", safely(settings), methods=["PUT"]),
        Route("/streamlit/apps/{app}/session", safely(session)),
    ]
