"""The Session page (services/session_log.py): this session's log, and Follow the agent.

GET  /session-log          ?who=agent|user|both&limit=200: the entries, newest first; the switch   app_session
PUT  /session-log/follow   {"on": true|false}: Follow the agent (the user's only: 403 for the agent)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench.services.session_log import SessionLog


def routes(log: SessionLog) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(log.listing(request.query_params.get("who"), request.query_params.get("limit")))

    async def follow(request: Request) -> Response:
        return json_response(await log.set_follow(await read_json(request), actor(request)))

    return [
        Route("/session-log", safely(listing)),
        Route("/session-log/follow", safely(follow), methods=["PUT"]),
    ]
