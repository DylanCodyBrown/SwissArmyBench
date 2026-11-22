"""A project's local sandbox API, hosted (run as `python -I api_host.py`, a process of its own:
services/local_api.py).

What it reads from its environment, and nothing else: SAB_API_FILE (the project's API.py), SAB_API_KEY (every
request carries it: `Authorization: Bearer <key>`), SAB_API_BASE (the base path), SAB_SANDBOX_DATA (the app's
/sandbox/data/<key> address: the adapter's only door here, adapter.Remote). Its environment has no
connection's code, variable or secret (the server builds it from scratch), and the app's own client functions
are taken over before API.py is imported: `connection(name)` is the adapter's Connection over the sandbox's
tables read from that connection; `swissarmybench.blade`, `.read`, `.sql`, `.dax` and `.load` refuse, so
nothing here reaches a real connection.

On 127.0.0.1 only, on a port the system gives; its first line on stdout is JSON: {"port", "endpoints"} or
{"error", "line"} (API.py did not import). Starlette and uvicorn (the app's own); each request kept in memory
for
the request log (method, path, status, milliseconds, rows; never a value): GET /__sab/log.
"""

from __future__ import annotations

import collections
import importlib.util
import json
import os
import secrets
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from swissarmybench.adapters import adapter, api_adapter
from swissarmybench.server import api_runtime as sab_api

LOG_SIZE = 200
URL_VARIABLE = "SAB_SANDBOX_DATA"  # the app's /sandbox/data/<key> address, this process's only door
LINE_HEADER = (
    "X-Sab-Error-Line"  # a failed request's API.py line, for Try it (this host only, never an export)
)
REFUSED = (
    "A local sandbox API never reaches a real connection: use connection(name) from sab_api, which reads and "
    "writes the sandbox's tables from it through the adapter."
)


def _say(answer: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(answer) + "\n")
    sys.stdout.flush()


def _guard(connection: Any) -> None:
    """The app's client functions in this process: the adapter's connection over the sandbox, or a refusal."""
    import swissarmybench

    def refused(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(REFUSED)

    for name in ("blade", "read", "sql", "dax", "load", "blades"):
        setattr(swissarmybench, name, refused)
    swissarmybench.connection = connection
    try:
        from swissarmybench.client import blades_client, sql_cell

        blades_client.blade = refused
        blades_client.read = refused
        sql_cell.connection = refused
        sql_cell.open_connection = refused
    except ImportError:  # pragma: no cover (the plain wheel's own)
        pass


def _load(path: Path) -> None:
    sys.modules["sab_api"] = sab_api
    sys.modules["adapter"] = adapter  # `from adapter import read, Plan`: the sandbox, by name
    sys.modules["api_adapter"] = api_adapter  # `from api_adapter import run`: an export's same bytes
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("API", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{path} could not be read.")
    module = importlib.util.module_from_spec(spec)
    sys.modules["API"] = module
    spec.loader.exec_module(module)


def _error_line(error: BaseException, path: Path) -> int | None:
    if isinstance(error, SyntaxError) and error.lineno:
        return int(error.lineno)
    for frame in reversed(traceback.extract_tb(error.__traceback__)):
        if Path(frame.filename).name == path.name:
            return int(frame.lineno or 0) or None
    return None


def build(key: str, log: collections.deque[dict[str, Any]], api_file: Path | None = None) -> Any:
    from starlette.applications import Starlette
    from starlette.concurrency import run_in_threadpool
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    expected = f"Bearer {key}".encode()

    def allowed(request: Request) -> bool:
        given = request.headers.get("authorization", "").encode("latin-1")
        return secrets.compare_digest(given, expected)

    failed = threading.local()

    def note(error: BaseException) -> None:
        failed.line = _error_line(error, api_file) if api_file is not None else None

    sab_api.on_failure = note

    def handled(
        method: str, path: str, query: dict[str, str], body: bytes, accept: str = ""
    ) -> tuple[Any, ...]:
        failed.line = None
        return (*sab_api.handle(method, path, query, body, accept), failed.line)

    async def one(request: Request) -> Response:
        if not allowed(request):
            return JSONResponse(
                {"error": "This local sandbox API takes its key (Authorization: Bearer)."}, 401
            )
        started = time.perf_counter()
        body = await request.body()
        query = dict(request.query_params)
        status, headers, payload, line = await run_in_threadpool(
            handled, request.method, request.url.path, query, body, request.headers.get("accept", "")
        )
        rows = None
        said = None
        try:
            parsed = json.loads(payload) if payload else None
            rows = len(parsed) if isinstance(parsed, list) else None
            if status >= 400 and isinstance(parsed, dict):
                said = str(parsed.get("error") or "")[:300] or None
        except ValueError:
            pass
        entry = {
            "at": time.strftime("%H:%M:%S"),
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "ms": round((time.perf_counter() - started) * 1000, 1),
            "rows": rows,
        }
        # A refusal's own words (the API's, never a row's value) and API.py's line when the endpoint failed.
        log.append(entry | ({"error": said} if said else {}) | ({"line": line} if line else {}))
        return Response(payload, status, headers=headers | ({LINE_HEADER: str(line)} if line else {}))

    async def logged(request: Request) -> Response:
        if not allowed(request):
            return JSONResponse({"error": "unauthorized"}, 401)
        return JSONResponse({"log": list(log)})

    async def described(request: Request) -> Response:
        if not allowed(request):
            return JSONResponse({"error": "unauthorized"}, 401)
        return JSONResponse({"endpoints": sab_api.describe()})

    base = sab_api.BASE_PATH.rstrip("/")
    routes = [Route("/__sab/log", logged), Route("/__sab/endpoints", described)]
    by_path: dict[str, set[str]] = {}
    for e in sab_api.ENDPOINTS:
        by_path.setdefault(base + e.path, set()).add(e.method)
    routes += [Route(path, one, methods=sorted(methods)) for path, methods in by_path.items()]
    # Any other path or method: the API's own refusal ({"error": ...}; its key asked first; in the log), as an
    # export answers it, never the framework's bare "Not Found".
    routes.append(Route("/{rest:path}", one, methods=list(sab_api.METHODS)))
    return Starlette(routes=routes)


def main() -> int:
    path = Path(os.environ["SAB_API_FILE"])
    key = os.environ["SAB_API_KEY"]
    sab_api.BASE_PATH = os.environ.get("SAB_API_BASE", "")
    door = os.environ[URL_VARIABLE]
    # The adapter's one backend here: every name is the sandbox's tables mocked as that connection, and
    # connection(name) is the adapter's calls on it (the same code an export runs against the real one).
    adapter.use(lambda name: adapter.Remote(door, str(name or "Sandbox").strip() or "Sandbox"))

    def connection(name: str) -> Any:
        return adapter.Connection(str(name or "Sandbox").strip() or "Sandbox")

    sab_api.use_clients(connection)
    _guard(connection)
    try:
        _load(path)
    except BaseException as error:  # API.py's own failure: said with its line, then this process ends
        said = "".join(traceback.format_exception_only(type(error), error)).strip()
        _say({"error": said, "line": _error_line(error, path)})
        return 1
    import uvicorn

    log: collections.deque[dict[str, Any]] = collections.deque(maxlen=LOG_SIZE)
    app = build(key, log, path)
    # IPPROTO_TCP named, as server/lifecycle.py does: asyncio sets TCP_NODELAY only on a socket whose proto
    # says TCP, and without it every answer after a connection's first waited ~40 ms (Nagle and delayed ACK).
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = int(sock.getsockname()[1])
    _say(
        {
            "port": port,
            "endpoints": [{"method": e.method, "path": e.path, "name": e.name} for e in sab_api.ENDPOINTS],
        }
    )
    config = uvicorn.Config(app, log_level="warning", access_log=False, lifespan="off")
    uvicorn.Server(config).run(sockets=[sock])
    return 0


if __name__ == "__main__":
    sys.exit(main())
