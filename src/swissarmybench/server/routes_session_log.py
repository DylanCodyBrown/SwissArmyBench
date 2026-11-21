"""The Session page (services/session_log.py): this session's log, and Follow the agent.

GET  /session-log          ?who=agent|user|both&limit=200: the entries, newest first; the switch   app_session
PUT  /session-log/follow   {"on": true|false}: Follow the agent (the user's only: 403 for the agent)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, with_body
from swissarmybench.services.session_log import SessionLog


def routes(log: SessionLog) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(log.listing(request.query_params.get("who"), request.query_params.get("limit")))

    return [
        Route("/session-log", listing),
        Route("/session-log/follow", with_body(log.set_follow), methods=["PUT"]),
    ]
