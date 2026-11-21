"""Widgets (services/widgets.py), for the Widgets window, the Canvas's Widgets pane and the agent.

GET    /streamlit/widget                         the Widgets window (widget.html: no rail)
GET    /streamlit/widgets?framework=&q=          every widget of the framework (the library's, the prebuilt)
POST   /streamlit/widgets                        {"name"?, "description"?, "code"?}: a new widget
GET    /streamlit/widgets/check-name?name=&own=  the live check: available, taken, not a valid name
POST   /streamlit/widgets/properties             {"code"} or {"name"}: the properties (types, masks)
POST   /streamlit/widgets/check-value            {"name" or "code", "property", "value", "values"?}
POST   /streamlit/widgets/stop                   {"window"?}: the widget run alone, stopped
GET    /streamlit/widgets/{name}                 one widget: header, code, properties
PUT    /streamlit/widgets/{name}                 {"code"}: saved below its header
PATCH  /streamlit/widgets/{name}                 {"name"?, "description"?, ...}: its header only
POST   /streamlit/widgets/{name}/property        {"property", "value", "code"?}: a default written back
POST   /streamlit/widgets/{name}/copy            {"name"?}: a prebuilt one as your own
DELETE /streamlit/widgets/{name}                 the agent's waits for the user's Allow
POST   /streamlit/widgets/{name}/run             {"values"?, "code"?, "window"?, "python"?}: Run in place
POST   /streamlit/widgets/{name}/check           the same headless (AppTest): its errors
GET    /streamlit/widgets/{name}/preview?theme=  the preview's state (asked for when it is not made)
GET    /streamlit/widgets/{name}/preview.png?key= the preview itself
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench_streamlit.services.widgets import Widgets


def routes(widgets: Widgets, previews: Any, web_root: Path | None) -> list[BaseRoute]:
    async def body_of(request: Request) -> Any:
        return await read_json(request) if int(request.headers.get("content-length") or 0) else {}

    def name_of(request: Request) -> str:
        return str(request.path_params["name"])

    async def window(request: Request) -> Response:
        if web_root is None or not (web_root / "widget.html").is_file():
            return Response("The Widgets window's page is not here.", 404)
        return FileResponse(web_root / "widget.html", headers={"Cache-Control": "no-store"})

    async def listing(request: Request) -> Response:
        if request.method == "POST":
            return json_response(await widgets.new(await body_of(request), actor(request)))
        q = request.query_params
        return json_response(widgets.listing(q.get("framework") or "streamlit", q.get("q") or ""))

    async def check_name(request: Request) -> Response:
        q = request.query_params
        return json_response(widgets.check_name(q.get("name") or "", q.get("own") or None))

    async def properties(request: Request) -> Response:
        return json_response(widgets.properties(await body_of(request)))

    async def check_value(request: Request) -> Response:
        return json_response(widgets.check_value(await body_of(request)))

    async def context(request: Request) -> Response:
        return json_response(widgets.context_info())

    async def stop(request: Request) -> Response:
        return json_response(await widgets.stop(await body_of(request)))

    async def one(request: Request) -> Response:
        name, who = name_of(request), actor(request)
        if request.method == "PUT":
            return json_response(await widgets.save(name, await body_of(request), who))
        if request.method == "PATCH":
            return json_response(await widgets.header(name, await body_of(request), who))
        if request.method == "DELETE":
            return json_response(await widgets.delete(name, who))
        return json_response(widgets.get(name))

    async def set_property(request: Request) -> Response:
        return json_response(
            await widgets.set_property(name_of(request), await body_of(request), actor(request))
        )

    async def copy(request: Request) -> Response:
        return json_response(await widgets.copy(name_of(request), await body_of(request), actor(request)))

    async def run(request: Request) -> Response:
        return json_response(await widgets.run(name_of(request), await body_of(request), actor(request)))

    async def check(request: Request) -> Response:
        return json_response(await widgets.check(name_of(request), await body_of(request), actor(request)))

    async def preview(request: Request) -> Response:
        name, theme = name_of(request), request.query_params.get("theme") or "light"
        said = widgets.preview(name, theme)
        if said["state"] == "coming" and previews is not None:
            previews.want(name, theme)
        return json_response(said)

    async def preview_png(request: Request) -> Response:
        data = widgets.preview_png(str(request.query_params.get("key") or ""))
        if data is None:
            return Response("No preview yet.", 404)
        return Response(data, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})

    return [
        Route("/streamlit/widget", window),
        Route("/streamlit/widgets", safely(listing), methods=["GET", "POST"]),
        Route("/streamlit/widgets/check-name", safely(check_name)),
        Route("/streamlit/widgets/properties", safely(properties), methods=["POST"]),
        Route("/streamlit/widgets/check-value", safely(check_value), methods=["POST"]),
        Route("/streamlit/widgets/stop", safely(stop), methods=["POST"]),
        Route("/streamlit/widgets/context", safely(context)),
        Route("/streamlit/widgets/{name}", safely(one), methods=["GET", "PUT", "PATCH", "DELETE"]),
        Route("/streamlit/widgets/{name}/property", safely(set_property), methods=["POST"]),
        Route("/streamlit/widgets/{name}/copy", safely(copy), methods=["POST"]),
        Route("/streamlit/widgets/{name}/run", safely(run), methods=["POST"]),
        Route("/streamlit/widgets/{name}/check", safely(check), methods=["POST"]),
        Route("/streamlit/widgets/{name}/preview", safely(preview)),
        Route("/streamlit/widgets/{name}/preview.png", safely(preview_png)),
    ]
