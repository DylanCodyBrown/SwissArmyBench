"""The page's own file picker (services/folders.py); the agent may list folders and make one too (the golden
rule):

GET    /folders?path=&suffixes=.csv,.xlsx&kind=&hidden=1   a folder's subfolders and files (names,
                       sizes, dates); with kind, the quick places and its recent folders
POST   /folders/new   {"path", "name"}: New folder, inside the folder shown
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_as, json_response, read_json
from swissarmybench.services.folders import Folders


def routes(folders: Folders) -> list[BaseRoute]:
    async def browse(request: Request) -> Response:
        query = request.query_params
        try:
            return json_response(
                folders.browse(
                    query.get("path"),
                    query.get("suffixes"),
                    query.get("kind"),
                    query.get("hidden") in ("1", "true"),
                )
            )
        except FileNotFoundError as error:
            return error_as(error, 404)
        except PermissionError as error:
            return error_as(error, 403)

    async def new_folder(request: Request) -> Response:
        try:
            return json_response(folders.new_folder(await read_json(request), actor(request)))
        except FileNotFoundError as error:
            return error_as(error, 404)
        except FileExistsError as error:
            return error_as(error, 409)
        except PermissionError as error:
            return error_as(error, 403)

    return [Route("/folders", browse), Route("/folders/new", new_folder, methods=["POST"])]
