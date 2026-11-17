"""Structures (services/structures.py), for the page and the agent alike (the golden rule).

GET    /structures                      the open structures and the project's structure files
POST   /structures                      New: {"kind": object | list, "name"?, "format"?, "value"?, "origin"?}
POST   /structures/open                 {"path"}: a .json, .yaml, .xml or .toml file
POST   /structures/paste                {"text", "format"?, "name"?}
GET    /structures/saved?name=&path=    a saved structure's value (sab.structure)
GET    /structures/references?name=     where code calls sab.structure(name)
GET    /structures/{id}                 its result, written in its format too (text)
GET    /structures/{id}/describe?path=  its shape, record lists and a capped preview (the agent's read)
DELETE /structures/{id}                 closed
PUT    /structures/{id}                 {"text"} the text view's edit | {"format"} | {"name"}
POST   /structures/{id}/steps           a step; POST /structures/{id}/steps/remove {"index"?}
POST   /structures/{id}/undo, /redo
POST   /structures/{id}/grid            {"path"?, "name"?}: Open as grid
POST   /structures/{id}/run-again       an API call's structure: the call sent again, its steps kept
GET    /structures/{id}/lineage         the call (or file) -> it -> its steps -> the grids made from it
POST   /structures/{id}/save            to its file
POST   /structures/{id}/save-as         {"name"?, "format"?, "folder"? | "path"?}
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.structures import Structures


def routes(structures: Structures) -> list[BaseRoute]:
    def safely(handler: Any) -> Any:
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)  # type: ignore[no-any-return]
            except Exception as error:
                return error_response(error)

        return guarded

    def sid(request: Request) -> str:
        return str(request.path_params["sid"])

    async def listing(request: Request) -> Response:
        return json_response(structures.listing())

    async def new(request: Request) -> Response:
        return json_response(await structures.new(await read_json(request), actor(request)))

    async def open_file(request: Request) -> Response:
        return json_response(await structures.open_file(await read_json(request), actor(request)))

    async def paste(request: Request) -> Response:
        return json_response(await structures.paste(await read_json(request), actor(request)))

    async def saved(request: Request) -> Response:
        q = request.query_params
        return json_response(await structures.saved(q.get("name", ""), q.get("path", "$")))

    async def references(request: Request) -> Response:
        return json_response(structures.references(request.query_params.get("name", "")))

    async def show(request: Request) -> Response:
        return json_response(structures.show(sid(request)))

    async def describe(request: Request) -> Response:
        return json_response(structures.describe(sid(request), request.query_params.get("path", "$")))

    async def close(request: Request) -> Response:
        return json_response(await structures.close(sid(request), actor(request)))

    async def change(request: Request) -> Response:
        body = await read_json(request)
        who = actor(request)
        if isinstance(body, dict) and "text" in body:
            return json_response(await structures.set_text(sid(request), body, who))
        if isinstance(body, dict) and "format" in body:
            return json_response(await structures.set_format(sid(request), body, who))
        return json_response(await structures.rename(sid(request), body, who))

    async def step(request: Request) -> Response:
        return json_response(
            await structures.add_step(sid(request), await read_json(request), actor(request))
        )

    async def remove_step(request: Request) -> Response:
        body = await read_json(request)
        return json_response(await structures.remove_step(sid(request), body, actor(request)))

    async def undo(request: Request) -> Response:
        return json_response(await structures.undo(sid(request), actor(request)))

    async def redo(request: Request) -> Response:
        return json_response(await structures.redo(sid(request), actor(request)))

    async def grid(request: Request) -> Response:
        body = await read_json(request)
        return json_response(await structures.open_as_grid(sid(request), body, actor(request)))

    async def run_again(request: Request) -> Response:
        return json_response(await structures.run_again(sid(request), actor(request)))

    async def lineage(request: Request) -> Response:
        return json_response(structures.lineage(sid(request)))

    async def save(request: Request) -> Response:
        return json_response(await structures.save(sid(request), actor(request)))

    async def save_as(request: Request) -> Response:
        return json_response(await structures.save_as(sid(request), await read_json(request), actor(request)))

    return [
        Route("/structures", safely(listing), methods=["GET"]),
        Route("/structures", safely(new), methods=["POST"]),
        Route("/structures/open", safely(open_file), methods=["POST"]),
        Route("/structures/paste", safely(paste), methods=["POST"]),
        Route("/structures/saved", safely(saved), methods=["GET"]),
        Route("/structures/references", safely(references), methods=["GET"]),
        Route("/structures/{sid}", safely(show), methods=["GET"]),
        Route("/structures/{sid}", safely(close), methods=["DELETE"]),
        Route("/structures/{sid}", safely(change), methods=["PUT"]),
        Route("/structures/{sid}/describe", safely(describe), methods=["GET"]),
        Route("/structures/{sid}/steps", safely(step), methods=["POST"]),
        Route("/structures/{sid}/steps/remove", safely(remove_step), methods=["POST"]),
        Route("/structures/{sid}/undo", safely(undo), methods=["POST"]),
        Route("/structures/{sid}/redo", safely(redo), methods=["POST"]),
        Route("/structures/{sid}/grid", safely(grid), methods=["POST"]),
        Route("/structures/{sid}/save", safely(save), methods=["POST"]),
        Route("/structures/{sid}/run-again", safely(run_again), methods=["POST"]),
        Route("/structures/{sid}/lineage", safely(lineage), methods=["GET"]),
        Route("/structures/{sid}/save-as", safely(save_as), methods=["POST"]),
    ]
