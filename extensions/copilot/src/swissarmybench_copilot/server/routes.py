# ruff: noqa: E501 (the routes' table)
"""The GitHub Copilot extension's HTTP door (services/copilot.py). Every route serves the agent too but
signing in and out (the user's: 403), and each user action's command is named beside it.

GET    /copilot                   installed, on, signed-in login, private, ready        copilot_status
POST   /copilot/toggle            {on}: the On switch                                    copilot_toggle
POST   /copilot/install           npm install of the pinned server (the agent's: Allow)  copilot_install
GET    /copilot/panel             the Extensions card's and Settings' panel, as data     copilot_status
POST   /copilot/panel             {action} or {switch, on}: a click on it                 (by action: the above)
POST   /copilot/sign-in           the device flow's code (the user's)                    (the user's only)
POST   /copilot/sign-in/finish    wait for GitHub, once the page is open (the user's)    (the user's only)
POST   /copilot/sign-out          (the user's)                                           (the user's only)
GET    /copilot/inline            the editors' status bar item: name, on, its word       (the editor's)
POST   /copilot/complete          {request, document, position}: ghost text              (the editor's)
POST   /copilot/cancel            {request}: that completion cancelled                   (the editor's)
POST   /copilot/event             {id, kind: shown|accepted|partial, length?}            (the editor's)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench_copilot.services.copilot import Copilot

Handler = Callable[[Request], Awaitable[Response]]


def safely(handler: Handler) -> Handler:
    async def run(request: Request) -> Response:
        try:
            return await handler(request)
        except Exception as error:
            return error_response(error)

    return run


def routes(copilot: Copilot) -> list[BaseRoute]:
    async def status(request: Request) -> Response:
        return json_response(await copilot.state(actor(request)))

    async def toggle(request: Request) -> Response:
        return json_response(await copilot.toggle(await read_json(request), actor(request)))

    async def install(request: Request) -> Response:
        return json_response(await copilot.install(actor(request)))

    async def panel(request: Request) -> Response:
        if request.method == "GET":
            return json_response(await copilot.panel_now(actor(request)))
        return json_response(await copilot.act(await read_json(request), actor(request)))

    async def sign_in(request: Request) -> Response:
        return json_response(await copilot.sign_in(actor(request)))

    async def finish(request: Request) -> Response:
        return json_response(await copilot.finish(actor(request)))

    async def sign_out(request: Request) -> Response:
        return json_response(await copilot.sign_out(actor(request)))

    async def inline(request: Request) -> Response:
        return json_response(await copilot.inline_status())

    async def complete(request: Request) -> Response:
        return json_response(await copilot.complete(await read_json(request)))

    async def cancel(request: Request) -> Response:
        return json_response(await copilot.cancel(await read_json(request)))

    async def event(request: Request) -> Response:
        return json_response(await copilot.event(await read_json(request)))

    return [
        Route("/copilot", safely(status)),
        Route("/copilot/toggle", safely(toggle), methods=["POST"]),
        Route("/copilot/install", safely(install), methods=["POST"]),
        Route("/copilot/panel", safely(panel), methods=["GET", "POST"]),
        Route("/copilot/sign-in", safely(sign_in), methods=["POST"]),
        Route("/copilot/sign-in/finish", safely(finish), methods=["POST"]),
        Route("/copilot/sign-out", safely(sign_out), methods=["POST"]),
        Route("/copilot/inline", safely(inline)),
        Route("/copilot/complete", safely(complete), methods=["POST"]),
        Route("/copilot/cancel", safely(cancel), methods=["POST"]),
        Route("/copilot/event", safely(event), methods=["POST"]),
    ]
