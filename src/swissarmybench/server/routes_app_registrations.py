"""App registrations (services/app_registrations.py): a library item, and its access report.

GET   /app-registrations                    the library's registrations, their users, the last check's line
POST  /app-registrations                    {"name", "tenant", "client", "secret"}: variable names only
POST  /app-registrations/remove             {"name"}
GET   /app-registrations/{name}             the registration and its last access report
POST  /app-registrations/{name}/check       Test / Check again: the access report made now (read-only calls)
GET   /connections/{name}/access            a connection's Access section (what it reaches, when, by which)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, with_body
from swissarmybench.services.app_registrations import AppRegistrations


def routes(registrations: AppRegistrations) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(registrations.listing())

    async def one(request: Request) -> Response:
        return json_response(registrations.report(request.path_params["name"]))

    async def check(request: Request) -> Response:
        return json_response(await registrations.check(request.path_params["name"], actor(request)))

    async def access(request: Request) -> Response:
        return json_response(registrations.access(request.path_params["name"]))

    return [
        Route("/app-registrations", listing),
        Route("/app-registrations", with_body(registrations.add), methods=["POST"]),
        Route("/app-registrations/remove", with_body(registrations.remove), methods=["POST"]),
        Route("/app-registrations/{name}", one),
        Route("/app-registrations/{name}/check", check, methods=["POST"]),
        Route("/connections/{name}/access", access),
    ]
