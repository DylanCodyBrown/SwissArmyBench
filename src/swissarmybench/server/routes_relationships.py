"""Relationships: the current model and its library, the Key Finder, and comparing two grids
(services/relationships.py has the use cases).

  GET  /relationships                    the current model (keys + relationships), as model JSON
  POST /relationships                    {"model": {...}, "replace": false}: merge (or replace) a model
  GET  /relationships/library            the models found in the library folders
  POST /relationships/library/{name}     apply that library model (merge)
  GET  /relationships/erd?tables=a,b     the current model as Mermaid erDiagram text; without tables, of the
       &scope=project|all                tables the open project uses (the default), or all of them
  GET  /relationships/scope?scope=       which tables the project uses: drawn, hidden, counted by connection

  The joins in use, managed (each with one Undo):
  POST /relationships/delete             {"joins": [{"from", "from_columns", "to", "to_columns"}, ...]}
  POST /relationships/update             {"joins": [...], "kind", "active"}: their kind and/or Run
  POST /relationships/undo               the joins in use as they were before the last delete or edit

  Relationship sets (saved, shared sets of relationships; the .relationships.json file in
  domain/relationships.py; a "tang" until 2026-11-17, whose old routes answer for one release):
  POST   /relationships/sets             {"name", "description", "tags", "author", "folder"}: save the
                                         current relationships as a set (own sets, or a shared folder)
  GET    /relationships/set              the current relationships as a .relationships.json (a download)
  GET    /relationships/sets/{name}      a saved set as a .relationships.json (a download)
  PATCH  /relationships/sets/{name}      {"name": new}: rename a saved set (its file too)
  DELETE /relationships/sets/{name}      delete a saved set's file (the agent's waits for the user's Allow)
  POST   /relationships/import           {"text", "apply", "save", "folder"}: without apply, what the
                                         set holds and what applying it would change; with it, merge
  POST   /relationships/check            {"set": name}: run it (or the current) against the open tables
  POST /relationships/tangs, GET /relationships/tang: the old names of the first two, one release
  POST /relationships/find               {"tables": [...]}: the finder's suggestions, with evidence
  POST /relationships/reject             a suggestion not to offer again ({"undo": true} brings it back)
  GET  /relationships/path?from=a&to=b   the shortest chain of joins between two tables

  Every one of them is the agent's too (the golden rule); its delete of a saved set waits for Allow.

  GET  /grids/{id}/key-finder            the grids a Key Finder can compare against
  POST /grids/{id}/key-finder            {"target": grid id | "*", "options": {...}}
       -> pairs (column, target grid, column, shared values, % found each way, score), best first,
          and unique_key: the column combination that tells this grid's first rows apart
  POST /grids/{id}/key-finder/sample     {"target", "source_column", "target_column", "options"}
       -> a few shared values and a few this column has that the target lacks (page only)

  POST   /compares                 {"left", "right", "keys": [[l, r], ...], "mode", "anti_side"}
                                   ("show": true puts the two grids side by side on the grid page)
  GET    /compares                 the compares that are running (a page reloading takes its own up again)
  GET    /compares/{id}            the compare, with its counts (matched, left only, right only)
  PATCH  /compares/{id}            change keys, mode or anti_side
  DELETE /compares/{id}
  GET    /compares/{id}/rows?side=left|right&start=&end=
  GET    /compares/{id}/key-group?row=N
  POST   /compares/{id}/focus      {"side": picked side, "position": its view row}   (cross compare)
  DELETE /compares/{id}/focus

Key Finder pairs carry counts, never values. The value samples are for the page (the agent reads
values through its own query tool).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, query_int, read_json, safely
from swissarmybench.services.relationship_scope import ProjectTables
from swissarmybench.services.relationships import Compares, Finder, KeyFinder, Models


def routes(
    models: Models, finder: Finder, keys: KeyFinder, compares: Compares, tables: ProjectTables
) -> list[BaseRoute]:
    ws = keys.ws

    # ===== the model =====

    async def get_current(request: Request) -> Response:
        return json_response(models.current())

    async def set_current(request: Request) -> Response:
        return json_response(await models.set_current(await read_json(request), actor(request)))

    async def library(request: Request) -> Response:
        return json_response(models.library())

    async def apply_library(request: Request) -> Response:
        return json_response(await models.apply_library(request.path_params["name"], actor(request)))

    async def erd(request: Request) -> Response:
        wanted = {t for t in request.query_params.get("tables", "").split(",") if t}
        return json_response(tables.erd(wanted, request.query_params.get("scope")))

    async def scope(request: Request) -> Response:
        return json_response(tables.scope(request.query_params.get("scope")))

    # ===== the Key Finder =====

    async def candidates(request: Request) -> Response:
        """The grids a Key Finder can compare against (for the page's picker)."""
        source, _ = ws.grid_and_info(request.path_params["grid_id"])
        return json_response(keys.candidates(source))

    async def find(request: Request) -> Response:
        source, _ = ws.grid_and_info(request.path_params["grid_id"])
        return json_response(await keys.run(source, await read_json(request), actor(request)))

    async def sample(request: Request) -> Response:
        source, _ = ws.grid_and_info(request.path_params["grid_id"])
        return json_response(await keys.sample(source, await read_json(request)))

    # ===== compare =====

    async def create(request: Request) -> Response:
        return json_response(await compares.create(await read_json(request), actor(request)))

    async def running(request: Request) -> Response:
        return json_response(await compares.running())

    async def read(request: Request) -> Response:
        return json_response(await compares.read(compares.get(request.path_params["compare_id"])))

    async def change(request: Request) -> Response:
        cmp = compares.get(request.path_params["compare_id"])
        return json_response(await compares.change(cmp, await read_json(request)))

    async def remove(request: Request) -> Response:
        return json_response(await compares.remove(request.path_params["compare_id"]))

    async def rows(request: Request) -> Response:
        cmp = compares.get(request.path_params["compare_id"])
        which = request.query_params.get("side")
        if which not in ("left", "right"):
            raise ValueError("side must be left or right.")
        start = max(0, query_int(request, "start", 0) or 0)
        end = max(
            start, min(query_int(request, "end", start + 100) or 0, start + ws.settings.max_window_rows)
        )
        return json_response(
            await compares.rows(cmp, which, start, end), max_bytes=ws.settings.max_response_bytes
        )

    async def key_group(request: Request) -> Response:
        cmp = compares.get(request.path_params["compare_id"])
        return json_response(await compares.key_group(cmp, query_int(request, "row")))

    async def set_focus(request: Request) -> Response:
        cmp = compares.get(request.path_params["compare_id"])
        return json_response(await compares.set_focus(cmp, await read_json(request)))

    async def clear_focus(request: Request) -> Response:
        return json_response(compares.clear_focus(compares.get(request.path_params["compare_id"])))

    # ===== the joins in use =====

    async def delete_joins(request: Request) -> Response:
        return json_response(await models.delete_joins(await read_json(request), actor(request)))

    async def update_joins(request: Request) -> Response:
        return json_response(await models.update_joins(await read_json(request), actor(request)))

    async def undo(request: Request) -> Response:
        return json_response(await models.undo(actor(request)))

    # ===== relationship sets and the finder =====

    def download(text: str, name: str) -> Response:
        return Response(
            text,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    async def save_set(request: Request) -> Response:
        return json_response(await models.save_set(await read_json(request), actor(request)))

    async def export_set(request: Request) -> Response:
        return download(*models.export_set())

    async def export_saved(request: Request) -> Response:
        return download(*models.export_saved(request.path_params["name"]))

    async def rename_set(request: Request) -> Response:
        body = await read_json(request)
        return json_response(await models.rename_set(request.path_params["name"], body, actor(request)))

    async def delete_set(request: Request) -> Response:
        return json_response(await models.delete_set(request.path_params["name"], actor(request)))

    async def import_set(request: Request) -> Response:
        body = await read_json(request)
        if isinstance(body, dict) and body.get("apply"):
            return json_response(await models.import_set(body, actor(request)))
        return json_response(models.review(body.get("text") if isinstance(body, dict) else None))

    async def check(request: Request) -> Response:
        return json_response(await models.check(await read_json(request), actor(request)))

    async def find_relationships(request: Request) -> Response:
        return json_response(await finder.find(await read_json(request), actor(request)))

    async def reject(request: Request) -> Response:
        return json_response(finder.reject(await read_json(request)))

    async def path(request: Request) -> Response:
        start, end = request.query_params.get("from", ""), request.query_params.get("to", "")
        if not start or not end:
            return Response("Name two tables: /relationships/path?from=a&to=b", status_code=400)
        return json_response(models.path(start, end))

    return [
        Route("/relationships", get_current),
        Route("/relationships", safely(set_current), methods=["POST"]),
        Route("/relationships/library", library),
        Route("/relationships/library/{name}", safely(apply_library), methods=["POST"]),
        Route("/relationships/erd", safely(erd)),
        Route("/relationships/scope", safely(scope)),
        Route("/relationships/delete", safely(delete_joins), methods=["POST"]),
        Route("/relationships/update", safely(update_joins), methods=["POST"]),
        Route("/relationships/undo", safely(undo), methods=["POST"]),
        Route("/relationships/sets", safely(save_set), methods=["POST"]),
        Route("/relationships/set", safely(export_set)),
        Route("/relationships/sets/{name}", safely(export_saved)),
        Route("/relationships/sets/{name}", safely(rename_set), methods=["PATCH"]),
        Route("/relationships/sets/{name}", safely(delete_set), methods=["DELETE"]),
        # The old names (a tang, until 2026-11-17), one release.
        Route("/relationships/tangs", safely(save_set), methods=["POST"]),
        Route("/relationships/tang", safely(export_set)),
        Route("/relationships/import", safely(import_set), methods=["POST"]),
        Route("/relationships/check", safely(check), methods=["POST"]),
        Route("/relationships/find", safely(find_relationships), methods=["POST"]),
        Route("/relationships/reject", safely(reject), methods=["POST"]),
        Route("/relationships/path", path),
        Route("/grids/{grid_id}/key-finder", safely(candidates)),
        Route("/grids/{grid_id}/key-finder", safely(find), methods=["POST"]),
        Route("/grids/{grid_id}/key-finder/sample", safely(sample), methods=["POST"]),
        Route("/compares", safely(running)),
        Route("/compares", safely(create), methods=["POST"]),
        Route("/compares/{compare_id}", safely(read)),
        Route("/compares/{compare_id}", safely(change), methods=["PATCH"]),
        Route("/compares/{compare_id}", safely(remove), methods=["DELETE"]),
        Route("/compares/{compare_id}/rows", safely(rows)),
        Route("/compares/{compare_id}/key-group", safely(key_group)),
        Route("/compares/{compare_id}/focus", safely(set_focus), methods=["POST"]),
        Route("/compares/{compare_id}/focus", safely(clear_focus), methods=["DELETE"]),
    ]
