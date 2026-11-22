"""Structures (services/structures.py), for the page and the agent alike (the golden rule).

GET    /structures                      the open structures and the project's structure files
POST   /structures                      New: {"kind": object | list, "name"?, "format"?, "value"?, "origin"?}
POST   /structures/open                 {"path"}: a .json, .yaml, .xml or .toml file
POST   /structures/paste                {"text", "format"?, "name"?}
GET    /structures/saved?name=&path=    a saved structure's value (sab.structure)
GET    /structures/references?name=     where code calls sab.structure(name)
GET    /structures/{id}?view=           its value (result: through its steps; file: the file's) and its
                                        own text as typed
GET    /structures/{id}/search?words=&view=  where words stand: each match's path and code
GET    /structures/{id}/describe?path=  its shape, record lists and a capped preview (the agent's read)
DELETE /structures/{id}                 closed
PUT    /structures/{id}                 {"text", "view"?} the text as typed (kept when it does not parse:
                                        text_error) | {"format"} | {"name"}
POST   /structures/{id}/edit            an edit in a tab's tree on the file itself (its text written again)
POST   /structures/{id}/format          Format: the text written again in its own format
POST   /structures/{id}/reload          Reload: the file read again; POST /keep-mine: Keep mine
POST   /structures/{id}/steps           a step; POST /structures/{id}/steps/remove {"index"?}
POST   /structures/{id}/undo, /redo
POST   /structures/{id}/grid            {"path"?, "name"?}: Open as grid
POST   /structures/{id}/run-again       an API call's structure: the call sent again, its steps kept
GET    /structures/{id}/lineage         the call (or file) -> it -> its steps -> the grids made from it
POST   /structures/{id}/save            to its file ({"text", "hash", "force"?}: a tab's Save, the text)
POST   /structures/{id}/save-as         {"name"?, "format"?, "folder"? | "path"?}
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, with_body
from swissarmybench.services.structures import Structures


def routes(structures: Structures) -> list[BaseRoute]:
    def sid(request: Request) -> str:
        return str(request.path_params["sid"])

    async def listing(request: Request) -> Response:
        return json_response(structures.listing())

    async def saved(request: Request) -> Response:
        q = request.query_params
        return json_response(await structures.saved(q.get("name", ""), q.get("path", "$")))

    async def references(request: Request) -> Response:
        return json_response(structures.references(request.query_params.get("name", "")))

    async def show(request: Request) -> Response:
        view = request.query_params.get("view", "result")
        return json_response(structures.show(sid(request), view="file" if view == "file" else "result"))

    async def search(request: Request) -> Response:
        q = request.query_params
        return json_response(structures.search(sid(request), q.get("words", ""), q.get("view", "file")))

    async def edit(request: Request) -> Response:
        return json_response(await structures.edit(sid(request), await read_json(request), actor(request)))

    async def format_text(request: Request) -> Response:
        body = await read_json(request)
        return json_response(await structures.format_text(sid(request), body, actor(request)))

    async def reload(request: Request) -> Response:
        return json_response(await structures.reload(sid(request), actor(request)))

    async def keep_mine(request: Request) -> Response:
        return json_response(await structures.keep_mine(sid(request), actor(request)))

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
        body = await read_json(request)
        return json_response(await structures.save(sid(request), body, actor(request)))

    async def save_as(request: Request) -> Response:
        return json_response(await structures.save_as(sid(request), await read_json(request), actor(request)))

    return [
        Route("/structures", listing, methods=["GET"]),
        Route("/structures", with_body(structures.new), methods=["POST"]),
        Route("/structures/open", with_body(structures.open_file), methods=["POST"]),
        Route("/structures/paste", with_body(structures.paste), methods=["POST"]),
        Route("/structures/saved", saved, methods=["GET"]),
        Route("/structures/references", references, methods=["GET"]),
        Route("/structures/{sid}", show, methods=["GET"]),
        Route("/structures/{sid}", close, methods=["DELETE"]),
        Route("/structures/{sid}", change, methods=["PUT"]),
        Route("/structures/{sid}/describe", describe, methods=["GET"]),
        Route("/structures/{sid}/search", search, methods=["GET"]),
        Route("/structures/{sid}/edit", edit, methods=["POST"]),
        Route("/structures/{sid}/format", format_text, methods=["POST"]),
        Route("/structures/{sid}/reload", reload, methods=["POST"]),
        Route("/structures/{sid}/keep-mine", keep_mine, methods=["POST"]),
        Route("/structures/{sid}/steps", step, methods=["POST"]),
        Route("/structures/{sid}/steps/remove", remove_step, methods=["POST"]),
        Route("/structures/{sid}/undo", undo, methods=["POST"]),
        Route("/structures/{sid}/redo", redo, methods=["POST"]),
        Route("/structures/{sid}/grid", grid, methods=["POST"]),
        Route("/structures/{sid}/save", save, methods=["POST"]),
        Route("/structures/{sid}/run-again", run_again, methods=["POST"]),
        Route("/structures/{sid}/lineage", lineage, methods=["GET"]),
        Route("/structures/{sid}/save-as", save_as, methods=["POST"]),
    ]
