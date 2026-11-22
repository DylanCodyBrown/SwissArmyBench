"""Blades (plan decisions 14-18). The golden rule (the owner, 2026-11-14): whatever the user can do,
the agent can too, so every route serves the agent but one: /blades/{name}/python, whose answer
carries the saved password values (they never reach the agent):

  GET    /blades, /blades/templates, /blades/{name}
  POST   /blades                     save a new one        PUT /blades/{name}   its code (the blade IDE's
                                     Save: {code, stamp, force?}; 409 when the file changed on disk since)
                                     and its header's name, description, tags, table name
  GET    /blades/{name}/code         the open editor's look at its file: the code and its stamp
  POST   /blades/{name}/run          the IDE's Run: {code?, env?, run?, stream?}; stream: NDJSON lines of
                                     {"output": {stream, text}}, then {"done": the answer}
  GET    /blades/{name}/run          its last run this session (output, result, problems)
  POST   /blades/runs/{run}/cancel   stop a run going now
  POST   /blades/{name}/result/open  the last run's table opened as a grid
  POST   /blades/{name}/problems     {code?}: the lint's problems in its code (the editor's)
  GET    /blades/name-check?name=    Save as's live check of a new blade's name
  GET    /blades/new  POST ...       New blade: the choices; a new .blade.py in the library's blades/ folder
  GET    /blades/table-name?name=&blade=   the live check of a table name ("available", or why not)
  POST   /blades/{name}/show         Show its file: the system's file manager (the user's click only)
  DELETE /blades/{name}
  POST   /blades/inspect             what code makes, asks for, imports and needs (nothing saved or run)
  POST   /blades/fill                write values into the code at its settings; the new code and settings
  PUT    /blades/{name}/secrets      save or forget its secrets (in the operating system's vault)
  POST   /blades/{name}/refresh      run it and its catalog command in a child process; load the catalog
  POST   /blades/{name}/test         run it in a child process: does it work?
  GET    /blades/{name}/python       everything sab.blade() needs to run it in the caller's Python
  POST   /blades/install             install packages into Swiss Army Bench's own Python
  GET    /blades/folders  PUT ...    the blade folders searched for blade files, and files that failed
  PUT    /blades/{name}/pin          a favourite, or not (kept on this computer)
  GET    /blades/{name}/export       the blade as a portable .blade.py file
  GET    /blades/export?names=       several (or all) as a zip of them
  POST   /blades/import              review what files hold (nothing saved or run), then apply choices
  GET    /blades/analyses            the analysis blades, for the Analyze menu
  GET    /blades/starters            the built-in starter pack, by family (read-only)
  POST   /blades/{name}/copy         {"name"}: a starter's (or a pack's) blade copied as the user's own
  GET    /blades/{name}/snippet      a snippet for its form: text, placeholders, options (?dataset=)
  POST   /blades/{name}/snippet      {"values"}: the snippet filled, ready to insert
  POST   /grids/{id}/blade-analysis  {"name", "columns", "env"}: run an analysis blade on the grid's rows

The use cases are services/blades.py.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import BaseRoute, Route

from swissarmybench.domain.blades import BladeCodeError, VaultUnavailableError
from swissarmybench.server.blade_runner import RefreshError
from swissarmybench.server.http import (
    actor,
    error_as,
    json_response,
    read_json,
    read_json_object,
    refusal,
)
from swissarmybench.services.blades import BladeService, ChangedOnDisk, IncompleteBlade, NeedsValues


def _agent_refused() -> Response:
    return refusal(
        "This answer holds the saved password values (for sab.blade in the user's Python): never the "
        "agent's. Run the blade in a Workbench kernel instead (workbench_run), where it reads them itself.",
        403,
    )


def routes(blades: BladeService) -> list[BaseRoute]:
    async def list_blades(request: Request) -> Response:
        return json_response(blades.listing())

    async def templates(request: Request) -> Response:
        return json_response(blades.templates())

    async def get_blade(request: Request) -> Response:
        return json_response(blades.details(request.path_params["name"]))

    async def save_blade(request: Request) -> Response:
        try:
            previous = request.path_params.get("name")
            if previous is not None:  # a saved blade: its code and its header (the blade IDE's Save)
                return json_response(await blades.update(previous, await read_json(request), actor(request)))
            return json_response(await blades.save(await read_json(request), None, actor(request)))
        except ChangedOnDisk as error:
            return json_response(
                {"error": str(error), "changed_on_disk": True, "stamp": error.stamp}, status_code=409
            )
        except IncompleteBlade as error:
            return _incomplete(error)
        except VaultUnavailableError as error:
            return error_as(error, 409)

    # ===== the blade IDE (the owner, 2026-11-21) =====

    def _incomplete(error: IncompleteBlade) -> Response:
        # The one refusal shape, with the line the code lacks its kind's part at (the editor marks it).
        return json_response(
            {"error": str(error), "where": f"line {error.line}", "line": error.line}, status_code=422
        )

    async def header(request: Request) -> Response:
        try:
            if request.method == "GET":
                return json_response(blades.header(request.path_params["name"]))
            body = await read_json(request)
            return json_response(await blades.header_set(request.path_params["name"], body, actor(request)))
        except IncompleteBlade as error:
            return _incomplete(error)

    async def code(request: Request) -> Response:
        return json_response(blades.code(request.path_params["name"]))

    async def run_blade(request: Request) -> Response:
        name = request.path_params["name"]
        try:
            if request.method == "GET":
                return json_response(blades.last_run(name))
            body = await read_json(request) if int(request.headers.get("content-length") or 0) else {}
            body = body if isinstance(body, dict) else {}
            who = actor(request)
            if not body.get("stream"):
                return json_response(await blades.run(name, body, who))
            blades.runnable_now(name)  # refused before the stream starts (a snippet, a secret blade)
        except NeedsValues as error:
            return _needs(error)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def work() -> None:
            try:
                done = await blades.run(
                    name,
                    body,
                    who,
                    lambda stream, text: queue.put_nowait({"output": {"stream": stream, "text": text}}),
                )
                queue.put_nowait({"done": done})
            except NeedsValues as error:
                queue.put_nowait({"done": {"ok": False, "needs": error.missing, "error": str(error)}})
            except Exception as error:
                queue.put_nowait({"done": {"ok": False, "error": str(error)}})

        async def lines() -> AsyncIterator[bytes]:
            task = asyncio.create_task(work())
            try:
                while True:
                    item = await queue.get()
                    yield (json.dumps(item, default=str) + "\n").encode()
                    if "done" in item:
                        break
            finally:
                if not task.done():
                    blades.cancel(str(body.get("run") or ""))
                await asyncio.gather(task, return_exceptions=True)

        return StreamingResponse(
            lines(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"}
        )

    async def cancel_run(request: Request) -> Response:
        return json_response(blades.cancel(request.path_params["run"]))

    async def open_result(request: Request) -> Response:
        return json_response(await blades.open_result(request.path_params["name"], actor(request)))

    async def problems(request: Request) -> Response:
        body = await read_json(request) if int(request.headers.get("content-length") or 0) else {}
        code_text = body.get("code") if isinstance(body, dict) else None
        return json_response(await blades.problems(request.path_params["name"], code_text))

    async def name_check(request: Request) -> Response:
        return json_response(blades.name_check(request.query_params.get("name", "")))

    async def new_blade(request: Request) -> Response:
        if request.method == "GET":
            return json_response(blades.new_blades())
        return json_response(await blades.new(await read_json(request), actor(request)))

    async def table_name(request: Request) -> Response:
        name = request.query_params.get("name", "")
        return json_response(blades.table_name_check(name, request.query_params.get("blade") or None))

    async def show_file(request: Request) -> Response:
        return json_response(await blades.show_file(request.path_params["name"], actor(request)))

    async def remove_blade(request: Request) -> Response:
        return json_response(await blades.remove(request.path_params["name"], actor(request)))

    async def inspect_code(request: Request) -> Response:
        body = await read_json_object(request, '{"code": "..."}')
        code = body.get("code")
        if not isinstance(code, str):
            raise ValueError('Send {"code": "..."}.')
        template, name = body.get("template"), body.get("name")
        try:
            return json_response(
                blades.inspect(
                    code,
                    template if isinstance(template, str) else None,
                    name if isinstance(name, str) else None,
                )
            )
        except BladeCodeError as error:
            return json_response({"error": str(error)})

    async def fill_settings(request: Request) -> Response:
        """Write new values into a blade's code at its settings (by the ids `settings` gave for this
        same code). Returns the new code and its settings, read again."""
        body = await read_json_object(request, '{"code": "...", "values": {"<id>": "..."}}')
        code, values = body.get("code"), body.get("values")
        if not isinstance(code, str) or not isinstance(values, dict):
            raise ValueError('Send {"code": "...", "values": {"<setting id>": "new value"}}.')
        return json_response(blades.fill(code, values, body.get("template"), body.get("name")))

    async def set_secrets(request: Request) -> Response:
        try:
            body = await read_json(request)
            return json_response(blades.set_secrets(request.path_params["name"], body))
        except VaultUnavailableError as error:
            return error_as(error, 409)

    async def typed_body(request: Request) -> Any:
        """The values the user typed for this run, when the request carries any."""
        return await read_json(request) if int(request.headers.get("content-length") or 0) else {}

    def _needs(error: NeedsValues) -> Response:
        return json_response({"needs": error.missing, "message": str(error)}, status_code=409)

    def _run_failed(error: RefreshError, name: str | None = None) -> Response:
        return json_response(blades.run_failure(str(error), error.missing_module, name), status_code=422)

    async def refresh(request: Request) -> Response:
        try:
            blade = blades.runnable(request.path_params["name"], "catalog")
            return json_response(await blades.refresh(blade, await typed_body(request)))
        except NeedsValues as error:
            return _needs(error)
        except RefreshError as error:
            return _run_failed(error, request.path_params["name"])

    async def test(request: Request) -> Response:
        try:
            blade = blades.runnable(request.path_params["name"], "test")
            return json_response(await blades.test(blade, await typed_body(request)))
        except NeedsValues as error:
            return _needs(error)
        except RefreshError as error:
            return _run_failed(error, request.path_params["name"])

    async def analyses(request: Request) -> Response:
        return json_response(blades.analysis_blades.analyses())

    async def analyze(request: Request) -> Response:
        """The user's own analysis on the grid's rows as shown, run in a child process like Test."""
        try:
            body = await read_json(request)
            if not isinstance(body, dict) or not isinstance(body.get("name"), str):
                raise ValueError('Send {"name": the analysis blade, "columns": [the selected columns]}.')
            grid, info = blades.ws.grid_and_info(request.path_params["grid_id"])
            return json_response(
                await blades.analysis_blades.analyze(body["name"], grid, info, body, actor(request))
            )
        except NeedsValues as error:
            return _needs(error)
        except RefreshError as error:
            return _run_failed(error, body.get("name") if isinstance(body, dict) else None)

    async def python(request: Request) -> Response:
        """What sab.blade() runs in the caller's Python. Secret values included: only the user's own
        Python asks (the token is the user's; the agent is refused)."""
        if actor(request) == "agent":
            return _agent_refused()
        return json_response(blades.for_python(request.path_params["name"]))

    # ===== favourites, blade folders, export and import (portable blades) =====

    async def pin(request: Request) -> Response:
        body = await read_json_object(request, '{"pinned": true}')
        return json_response(await blades.pin(request.path_params["name"], bool(body.get("pinned"))))

    async def folders(request: Request) -> Response:
        if request.method == "PUT":
            body = await read_json_object(request, '{"folders": ["..."]}')
            await blades.set_folders(body.get("folders"))
        return json_response(blades.folders())

    async def export_one(request: Request) -> Response:
        text, file_name = blades.export_one(request.path_params["name"])
        return Response(
            text,
            media_type="text/x-python; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
        )

    async def export_all(request: Request) -> Response:
        wanted = {n.strip().casefold() for n in request.query_params.get("names", "").split(",") if n.strip()}
        return Response(
            blades.export_zip(wanted),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="blades.zip"'},
        )

    async def import_blades(request: Request) -> Response:
        """Import portable blades in two steps: review what each file holds (nothing saved, nothing
        run), then apply the choice for each."""
        body = await read_json_object(request, '{"files": [{"name": "...", "data": "<base64>"}]}')
        return json_response(await blades.import_blades(body))

    # ===== the starter pack, copies, snippets =====

    async def starters(request: Request) -> Response:
        return json_response(blades.starters())

    async def copy(request: Request) -> Response:
        body = await read_json(request) if int(request.headers.get("content-length") or 0) else {}
        new_name = body.get("name") if isinstance(body, dict) else None
        code_text = body.get("code") if isinstance(body, dict) else None  # Save as: the editor's code
        return json_response(
            await blades.copy(request.path_params["name"], new_name, actor(request), code_text)
        )

    async def snippet(request: Request) -> Response:
        name = request.path_params["name"]
        if request.method == "POST":
            body = await read_json_object(request, '{"values": {"measure": "Total Sales"}}')
            return json_response(blades.fill_snippet(name, body.get("values", {})))
        return json_response(await blades.snippet(name, request.query_params.get("dataset")))

    async def install(request: Request) -> Response:
        """Install packages into Swiss Army Bench's own Python, where Refresh runs, on the user's click."""
        body = await read_json_object(request, '{"packages": ["pyodbc"]}')
        worked, shown = await blades.install(body.get("packages"))
        return json_response(shown, status_code=200 if worked else 422)

    return [
        Route("/blades", list_blades),
        Route("/blades", save_blade, methods=["POST"]),
        Route("/blades/templates", templates),
        Route("/blades/new", new_blade, methods=["GET", "POST"]),
        Route("/blades/table-name", table_name),
        Route("/blades/name-check", name_check),
        Route("/blades/runs/{run}/cancel", cancel_run, methods=["POST"]),
        Route("/blades/folders", folders, methods=["GET", "PUT"]),
        Route("/blades/export", export_all),
        Route("/blades/import", import_blades, methods=["POST"]),
        Route("/blades/inspect", inspect_code, methods=["POST"]),
        Route("/blades/fill", fill_settings, methods=["POST"]),
        Route("/blades/install", install, methods=["POST"]),
        Route("/blades/analyses", analyses),
        Route("/blades/starters", starters),
        Route("/grids/{grid_id}/blade-analysis", analyze, methods=["POST"]),
        Route("/blades/{name}", get_blade),
        Route("/blades/{name}", save_blade, methods=["PUT"]),
        Route("/blades/{name}", remove_blade, methods=["DELETE"]),
        Route("/blades/{name}/secrets", set_secrets, methods=["PUT"]),
        Route("/blades/{name}/code", code),
        Route("/blades/{name}/header", header, methods=["GET", "PUT"]),
        Route("/blades/{name}/run", run_blade, methods=["GET", "POST"]),
        Route("/blades/{name}/result/open", open_result, methods=["POST"]),
        Route("/blades/{name}/problems", problems, methods=["POST"]),
        Route("/blades/{name}/refresh", refresh, methods=["POST"]),
        Route("/blades/{name}/test", test, methods=["POST"]),
        Route("/blades/{name}/python", python),
        Route("/blades/{name}/pin", pin, methods=["PUT"]),
        Route("/blades/{name}/show", show_file, methods=["POST"]),
        Route("/blades/{name}/export", export_one),
        Route("/blades/{name}/copy", copy, methods=["POST"]),
        Route("/blades/{name}/snippet", snippet, methods=["GET", "POST"]),
    ]
