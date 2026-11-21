"""The project's sandbox (services/sandbox.py).

GET   /sandbox?sort=&order=          its tables (sorted: name, rows, source, created, changed), sources,
                                     clients, designations, baseline, checkpoints, log          sandbox(list)
POST  /sandbox/tables                {"from", ...}: a table in                                sandbox_add
POST  /sandbox/tables/remove         {"table"}                                                sandbox_remove
POST  /sandbox/tables/open           {"table"}: in Grids, following every write               sandbox_open
POST  /sandbox/tables/variant        {"from": grid|structure, "table"|"structure", "name"?}: a sandbox
                                     variant, its own designation and origin                  sandbox(variant)
POST  /sandbox/tables/mock           {"table", "connection"|null}: Mocked as a connection       sandbox(mock)
POST  /sandbox/edit                  {"table", "op": update|insert|delete, ...}: its grid's edit sandbox(edit)
POST  /sandbox/reset                 every table back to the baseline (agent: on Allow)       sandbox_reset
POST  /sandbox/baseline              the sandbox as it is now made the baseline     sandbox_checkpoint
POST  /sandbox/checkpoints           {"name", "action": save | delete}                      sandbox_checkpoint
POST  /sandbox/checkpoints/restore   {"name"}                                                 sandbox_restore
POST  /sandbox/data                  a mock client's data call (the token)
POST  /sandbox/data/{key}            a running local sandbox API's data call: its own key in the path
                                     instead of the token (server/security.py's secret paths)
POST  /sandbox/adapter/{tables|read|write}  the three below with the token (an in-app caller, a test)
POST  /sandbox/data/{key}/tables     sab_adapter.Remote's tables(source): {"connection"}
POST  /sandbox/data/{key}/read       its read: {"connection", "table", "plan"}; an Arrow IPC stream
                                     (X-Sab-Folded: the plan's parts folded)
POST  /sandbox/data/{key}/write      its write: an Arrow IPC stream; ?connection&table&key&mode; the counts
"""

from __future__ import annotations

import io
import secrets
from collections.abc import Callable, Iterator
from typing import Any

import pyarrow.ipc as ipc
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import (
    error_as,
    error_response,
    json_response,
    read_json,
    with_body,
)
from swissarmybench.services.sandbox import Sandbox

DATA_PREFIX = "/sandbox/data/"
ARROW_STREAM = "application/vnd.apache.arrow.stream"
ADAPTER = "/sandbox/adapter"  # the adapter's calls with the token (the key'd ones: DATA_PREFIX + key)


def routes(sandbox: Sandbox, keys: Callable[[], set[str]] = set) -> list[BaseRoute]:
    async def by_key(request: Request) -> Response:
        key = str(request.path_params["key"])
        if not any(secrets.compare_digest(key, k) for k in keys()):
            return error_as(PermissionError("That key is not a running local sandbox API's."), 403)
        try:
            return json_response(await sandbox.data(await read_json(request), "api"))
        except Exception as error:
            return error_response(error)

    def allowed(request: Request) -> bool:
        """A key'd path: a running local sandbox API's own key; the token's path: the guard checked it."""
        key = request.path_params.get("key")
        return key is None or any(secrets.compare_digest(str(key), k) for k in keys())

    async def adapter_tables(request: Request) -> Response:
        if not allowed(request):
            return error_as(PermissionError("That key is not a running local sandbox API's."), 403)
        try:
            return json_response(await sandbox.source_tables(await read_json(request)))
        except Exception as error:
            return error_response(error)

    async def adapter_read(request: Request) -> Response:
        """sab_adapter.Remote's read: the batches streamed as an Arrow IPC stream, as DuckDB makes them."""
        if not allowed(request):
            return error_as(PermissionError("That key is not a running local sandbox API's."), 403)
        try:
            reader, folded = await sandbox.read_arrow(await read_json(request))
        except Exception as error:
            return error_response(error)
        return StreamingResponse(
            _ipc(reader), media_type=ARROW_STREAM, headers={"X-Sab-Folded": ",".join(folded)}
        )

    async def adapter_write(request: Request) -> Response:
        """sab_adapter.Remote's write: an Arrow IPC stream's rows; the names in the query string."""
        if not allowed(request):
            return error_as(PermissionError("That key is not a running local sandbox API's."), 403)
        try:
            given = {k: str(v) for k, v in request.query_params.items()}
            return json_response(await sandbox.write_arrow(given, await request.body(), "api"))
        except Exception as error:
            return error_response(error)

    async def listing(request: Request) -> Response:
        try:
            return json_response(await sandbox.listing(dict(request.query_params)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/sandbox", listing),
        Route("/sandbox/tables", with_body(sandbox.add), methods=["POST"]),
        Route("/sandbox/tables/remove", with_body(sandbox.remove), methods=["POST"]),
        Route("/sandbox/tables/open", with_body(sandbox.open_grid), methods=["POST"]),
        Route("/sandbox/tables/variant", with_body(sandbox.variant), methods=["POST"]),
        Route("/sandbox/tables/mock", with_body(sandbox.mock), methods=["POST"]),
        Route("/sandbox/tables/key", with_body(sandbox.set_key), methods=["POST"]),
        Route("/sandbox/edit", with_body(sandbox.edit), methods=["POST"]),
        Route("/sandbox/reset", with_body(sandbox.reset), methods=["POST"]),
        Route("/sandbox/baseline", with_body(sandbox.set_baseline), methods=["POST"]),
        Route("/sandbox/checkpoints", with_body(sandbox.checkpoint), methods=["POST"]),
        Route("/sandbox/checkpoints/restore", with_body(sandbox.restore), methods=["POST"]),
        Route("/sandbox/data", with_body(sandbox.data), methods=["POST"]),
        Route(DATA_PREFIX + "{key}", by_key, methods=["POST"]),
        Route(ADAPTER + "/tables", adapter_tables, methods=["POST"]),
        Route(ADAPTER + "/read", adapter_read, methods=["POST"]),
        Route(ADAPTER + "/write", adapter_write, methods=["POST"]),
        Route(DATA_PREFIX + "{key}/tables", adapter_tables, methods=["POST"]),
        Route(DATA_PREFIX + "{key}/read", adapter_read, methods=["POST"]),
        Route(DATA_PREFIX + "{key}/write", adapter_write, methods=["POST"]),
    ]


def _ipc(reader: Any) -> Iterator[bytes]:
    """A reader's batches as one Arrow IPC stream, a piece a batch (Starlette reads it in its thread pool)."""
    sink = io.BytesIO()

    def taken() -> bytes:
        data = sink.getvalue()
        sink.seek(0)
        sink.truncate()
        return data

    writer = ipc.new_stream(sink, reader.schema)
    yield taken()
    try:
        for batch in reader:
            writer.write_batch(batch)
            yield taken()
    finally:
        writer.close()
        reader.close()
    yield taken()
