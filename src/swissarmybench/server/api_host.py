"""A project's local sandbox API, hosted (run as `python -I api_host.py`, a process of its own:
services/local_api.py).

What it reads from its environment, and nothing else: SAB_API_FILE (the project's API.py), SAB_API_KEY (every
request carries it: `Authorization: Bearer <key>`), SAB_API_BASE (the base path), SAB_SANDBOX_DATA (the app's
/sandbox/data/<key> address: the mock clients' only door). Its environment has no connection's code, variable
or
secret (the server builds it from scratch), and the app's own client functions are taken over before API.py is
imported: `swissarmybench.connection`, `.blade`, `.read`, `.sql`, `.dax` and `.load` give the sandbox's mock
or
refuse, so nothing here reaches a real connection.

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
import time
import traceback
from pathlib import Path
from typing import Any

from swissarmybench.server import api_runtime as sab_api
from swissarmybench.server import sandbox_clients

LOG_SIZE = 200
REFUSED = (
    "A local sandbox API never reaches a real connection: use connection(name) from sab_api, which gives the "
    "sandbox's mock of it."
)


def _say(answer: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(answer) + "\n")
    sys.stdout.flush()


def _guard(connection: Any) -> None:
    """The app's client functions in this process: the sandbox's mock, or a refusal."""
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


def build(key: str, log: collections.deque[dict[str, Any]]) -> Any:
    from starlette.applications import Starlette
    from starlette.concurrency import run_in_threadpool
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    expected = f"Bearer {key}".encode()

    def allowed(request: Request) -> bool:
        given = request.headers.get("authorization", "").encode("latin-1")
        return secrets.compare_digest(given, expected)

    async def one(request: Request) -> Response:
        if not allowed(request):
            return JSONResponse(
                {"error": "This local sandbox API takes its key (Authorization: Bearer)."}, 401
            )
        started = time.perf_counter()
        body = await request.body()
        query = dict(request.query_params)
        status, headers, payload = await run_in_threadpool(
            sab_api.handle, request.method, request.url.path, query, body
        )
        rows = None
        try:
            parsed = json.loads(payload) if payload else None
            rows = len(parsed) if isinstance(parsed, list) else 1 if isinstance(parsed, dict) else None
        except ValueError:
            pass
        log.append(
            {
                "at": time.strftime("%H:%M:%S"),
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "ms": round((time.perf_counter() - started) * 1000, 1),
                "rows": rows,
            }
        )
        return Response(payload, status, headers=headers)

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
    return Starlette(routes=routes)


def main() -> int:
    path = Path(os.environ["SAB_API_FILE"])
    key = os.environ["SAB_API_KEY"]
    sab_api.BASE_PATH = os.environ.get("SAB_API_BASE", "")
    connection = sandbox_clients.clients(os.environ[sandbox_clients.URL_VARIABLE])
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
    app = build(key, log)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
