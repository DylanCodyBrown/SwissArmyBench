"""A tiny made-up web service on this computer, for the tests of a connection from your own Python:
`http.server` on 127.0.0.1, serving made-up tables as JSON, answering only to a made-up API key.

  GET /tables                      [{"name", "columns": [{"name", "type"}]}]
  GET /tables/<name>/rows?limit=N  {"rows": [...], "total": how many it holds}

The starter's own three boxes (server/blade_templates.py PYTHON) talk to exactly this."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

API_KEY = "made-up-key-7391"  # made up: the service answers only to it

TABLES: dict[str, dict[str, list[dict[str, Any]]]] = {
    "orders": {
        "columns": [{"name": "order_id", "type": "integer"}, {"name": "amount", "type": "number"}],
        "rows": [{"order_id": n, "amount": round(n * 2.5, 2)} for n in range(1, 31)],  # thirty, made up
    },
    "clients": {
        "columns": [{"name": "client", "type": "text"}],
        "rows": [{"client": "Ada"}, {"client": "Grace"}],
    },
}

# A made-up key vault in plain Python (the Azure starter's shape: get, names): it holds the API key.
VAULT_CODE = (
    f'values = {{"orders-api-key": "{API_KEY}", "other": "made-up"}}\n\n\n'
    "def names():\n    return list(values)\n\n\ndef get(name):\n    return values[name]\n"
)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.headers.get("X-Api-Key") != API_KEY:
            self.send_error(401, "Bad API key")
            return
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        if parts == ["tables"]:
            answer: Any = [{"name": name, "columns": t["columns"]} for name, t in TABLES.items()]
        elif len(parts) == 3 and parts[0] == "tables" and parts[2] == "rows" and parts[1] in TABLES:
            rows = TABLES[parts[1]]["rows"]
            limit = parse_qs(url.query).get("limit")
            answer = {"rows": rows[: int(limit[0])] if limit else rows, "total": len(rows)}
        else:
            self.send_error(404)
            return
        body = json.dumps(answer).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # quiet
        pass


class Service:
    """The service, running on a free port of 127.0.0.1 until stopped."""

    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> Service:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)
