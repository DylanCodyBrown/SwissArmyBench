"""Beta mode, the beta log and the beta notes (services/beta_log.py), for every page and the agent.

GET    /beta               beta mode (on, what decided it) and what the log holds      app_beta_mode
PUT    /beta               {"on": false}: beta mode off (or on), now and at each start   app_beta_mode
GET    /beta/log           ?kind=error,page&since=2h&limit=200: the newest events          app_beta_log
GET    /beta/notes         every note (a picture is named, never sent)                     app_beta_notes
DELETE /beta/log           clear the log: every file and picture                          app_beta_log_clear
POST   /beta/export        {"path": "...zip"}: one zip (the agent's: no pictures)         app_beta_log_export
POST   /beta/notes         a note, from the page's "Leave a note…" (the user's own words)
POST   /beta/page-errors   a page's error, from the page itself
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, query_int, read_json, with_body
from swissarmybench.services.beta_log import BetaLog


def routes(beta: BetaLog) -> list[BaseRoute]:
    async def state(request: Request) -> Response:
        return json_response(await beta.state())

    async def events(request: Request) -> Response:
        q = request.query_params
        return json_response(
            await beta.events(q.get("kind"), q.get("since"), query_int(request, "limit", 200))
        )

    async def notes(request: Request) -> Response:
        return json_response(await beta.notes())

    async def page_error(request: Request) -> Response:
        return json_response(beta.page_error(await read_json(request)))

    async def clear(request: Request) -> Response:
        return json_response(await beta.clear(actor(request)))

    return [
        Route("/beta", state),
        Route("/beta", with_body(beta.set), methods=["PUT"]),
        Route("/beta/log", events),
        Route("/beta/log", clear, methods=["DELETE"]),
        Route("/beta/notes", notes),
        Route("/beta/notes", with_body(beta.note), methods=["POST"]),
        Route("/beta/page-errors", page_error, methods=["POST"]),
        Route("/beta/export", with_body(beta.export), methods=["POST"]),
    ]
