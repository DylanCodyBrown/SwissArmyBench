"""Add API (services/apis.py), for the page and the agent alike (the golden rule). No answer holds a
secret's value: a keyring value sent with Add goes to the keyring.

GET  /apis/choices   the auth types with their settings, and the presets (Azure, AWS, Google)
POST /apis/preview   {"spec" | "spec_path" | "spec_url" | "form", "name"?, "base_url"?, "auth"?, "folder"?}:
                     what Add would write (the operations, tables, variables, and what changes)
POST /apis/try       the same and "try" (an operation's name), "values"? ({"NAME": "value"}, this run
                     only): its first rows, before Add (nothing written, no value answered)
POST /apis           the same, and "variables"?, "secrets"?, "row_limit"?: API_<name>.py written and
                     its connection saved
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.apis import Apis


def routes(apis: Apis) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    async def choices(request: Request) -> Response:
        return json_response(apis.choices())

    async def preview(request: Request) -> Response:
        return json_response(await apis.preview(await read_json(request)))

    async def try_it(request: Request) -> Response:
        return json_response(await apis.try_it(await read_json(request)))

    async def add(request: Request) -> Response:
        return json_response(await apis.add(await read_json(request), actor(request)))

    async def make_into_blades(request: Request) -> Response:
        body = await read_json(request)
        name = request.path_params["name"]
        return json_response(await apis.make_into_blades(name, body, actor(request)))

    return [
        Route("/apis/choices", safely(choices), methods=["GET"]),
        Route("/apis/preview", safely(preview), methods=["POST"]),
        Route("/apis/try", safely(try_it), methods=["POST"]),
        Route("/apis", safely(add), methods=["POST"]),
        Route("/apis/{name}/make-into-blades", safely(make_into_blades), methods=["POST"]),
    ]
