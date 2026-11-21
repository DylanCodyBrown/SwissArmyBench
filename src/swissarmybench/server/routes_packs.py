"""Packs: blades and relationship sets from a Claude Code plugin marketplace (services/packs.py).

  GET  /packs        the installed packs, the editable ones (clones in the blade folders), the commands
  POST /packs/new    {"folder", "marketplace", "owner", "pack", "description", "add_folder"}: a new
                     marketplace repository with one pack
  POST /packs/add    {"pack": <folder>, "blades": [names], "sets": [names], "replace"}: copy them in

Files on disk, and code that others will run; the agent may do all of it too (the golden rule).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench.services.packs import Packs


def routes(packs: Packs) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(packs.list())

    async def new(request: Request) -> Response:
        return json_response(packs.create(await read_json(request), actor(request)))

    async def add(request: Request) -> Response:
        return json_response(packs.add(await read_json(request), actor(request)))

    return [
        Route("/packs", safely(listing)),
        Route("/packs/new", safely(new), methods=["POST"]),
        Route("/packs/add", safely(add), methods=["POST"]),
    ]
