"""Share a running app with your organization (services/sharing.py; Microsoft Dev Tunnels, organization only).

GET   /sharing            ?kind=&app=: devtunnel installed, the sign-in, the shares (?fresh=1: read again)
                                                                                         sharing_status
POST  /sharing/install    devtunnel downloaded and checked (the agent's on Allow; sharing_start does it)
POST  /sharing/sign-in    {"device"?}: Sign in with your work account (the user's only: 403 for the agent)
POST  /sharing/start      {"kind", "app"} (the agent's on Allow)                              sharing_start
POST  /sharing/stop       {"kind", "app"} (the agent's on Allow)                              sharing_stop
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, with_actor, with_body
from swissarmybench.services.sharing import Sharing


def routes(sharing: Sharing) -> list[BaseRoute]:
    async def status(request: Request) -> Response:
        query = request.query_params
        body = {
            "kind": query.get("kind"),
            "app": query.get("app"),
            "fresh": query.get("fresh") in ("1", "true"),
        }
        try:
            return json_response(await sharing.status(body, actor(request)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/sharing", status),
        Route("/sharing/install", with_actor(lambda who: sharing.install(None, who)), methods=["POST"]),
        Route("/sharing/sign-in", with_body(sharing.sign_in), methods=["POST"]),
        Route("/sharing/start", with_body(sharing.start), methods=["POST"]),
        Route("/sharing/stop", with_body(sharing.stop), methods=["POST"]),
    ]
