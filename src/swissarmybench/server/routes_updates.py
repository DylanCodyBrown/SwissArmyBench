"""Updates (services/updates.py), for the pages and the agent.

GET    /updates           the current version, the latest, whether one is available      app_update_check
PUT    /updates           {"check": false}: Settings' Check for updates (kept)            app_update_check on=
POST   /updates/check     check now (nothing is sent with the switch off)          app_update_check now=
POST   /updates/install   {"version"?, "confirmed"?}: Update to X (the agent's asks)   app_update
GET    /whats-new         ?all=1 | ?since=: What's New (WHATSNEW.md): opens after an update   app_whats_new
POST   /whats-new/seen    the window closed: the running version seen (the user's own; 403 for the agent)
POST   /whats-new/open    every main window opens What's New                       app_whats_new open=
"""

from __future__ import annotations

from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, with_body
from swissarmybench.services.updates import Updates

# The app's name in the status bar. The backend says it; the page shows what it is told, with the user's own
# folder extensions in its tooltip (every packaged extension is built in: the owner, 2026-11-27). The
# package, the uv tool and the commands keep their names (swissarmybench, sab).
APP_NAME = "Swiss Army Bench"


def routes(updates: Updates, extensions: Callable[[], list[str]] = list) -> list[BaseRoute]:
    """`extensions`: the folder extensions' names (the version mark's tooltip)."""

    def named() -> dict[str, object]:
        return {"name": APP_NAME, "extensions": extensions()}

    async def state(request: Request) -> Response:
        return json_response(updates.state() | named())

    async def check(request: Request) -> Response:
        # {"asked": true}: the user's button (or the agent's now) checks even with the switch off.
        body = await read_json(request) if await request.body() else {}
        asked = isinstance(body, dict) and body.get("asked") is True
        return json_response(await updates.check(asked=asked) | named())

    async def install(request: Request) -> Response:
        body = await read_json(request) if await request.body() else {}
        return json_response(await updates.install(body, actor(request)))

    async def whats_new(request: Request) -> Response:
        query = request.query_params
        found = news.state(query.get("since") or None, query.get("all") in ("1", "true")) if news else {}
        return json_response(found)

    news = updates.whats_new
    more: list[BaseRoute] = (
        [
            Route("/whats-new", whats_new),
            Route("/whats-new/seen", with_body(news.seen), methods=["POST"]),
            Route("/whats-new/open", with_body(news.show), methods=["POST"]),
        ]
        if news
        else []
    )
    return [
        *more,
        Route("/updates", state),
        Route("/updates", with_body(updates.set), methods=["PUT"]),
        Route("/updates/check", check, methods=["POST"]),
        Route("/updates/install", install, methods=["POST"]),
    ]
