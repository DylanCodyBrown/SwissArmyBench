"""sab.api(): the project's local sandbox API from a Workbench kernel or any Python on this computer.

    shop = sab.api()
    shop.get("/orders/West", params={"limit": 10})      # the answer's JSON
    shop.post("/orders", json={"order_id": 4, "region": "West", "amount": 2.5})

Each call goes through the app (POST /local-api/call), so it is timed and in the API's request log, and
reaches
only the project's sandbox. A refusal (a status of 400 or more) raises ApiCallError with its status and words.
Standard library only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from swissarmybench.client.push_client import ensure_server

_TIMEOUT_SECONDS = 180


class ApiCallError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class LocalApi:
    """The running local sandbox API (Run it on the APIs page, or api(run))."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name

    def _send(self, method: str, path: str, params: dict[str, Any] | None, body: Any) -> Any:
        info = ensure_server()
        sent = {"method": method, "path": path, "query": params or {}, "body": body}
        request = urllib.request.Request(
            f"http://127.0.0.1:{info['port']}/local-api/call",
            data=json.dumps(sent, default=str).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 (127.0.0.1)
                answer = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            try:
                said = json.loads(error.read() or b"{}").get("error") or error.reason
            except ValueError:
                said = error.reason
            raise ApiCallError(int(error.code), str(said)) from None
        status = int(answer.get("status") or 0)
        if status >= 400:
            body_said = answer.get("body")
            words = body_said.get("error") if isinstance(body_said, dict) else body_said
            raise ApiCallError(status, str(words))
        return answer.get("body")

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._send("GET", path, params, None)

    def post(self, path: str, json: Any = None, params: dict[str, Any] | None = None) -> Any:
        return self._send("POST", path, params, json)

    def put(self, path: str, json: Any = None, params: dict[str, Any] | None = None) -> Any:
        return self._send("PUT", path, params, json)

    def patch(self, path: str, json: Any = None, params: dict[str, Any] | None = None) -> Any:
        return self._send("PATCH", path, params, json)

    def delete(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._send("DELETE", path, params, None)


def api(name: str | None = None) -> LocalApi:
    """The project's local sandbox API (one per project: API.py; a name is for what is said only)."""
    return LocalApi(name)


def run(
    api: str, action: str, inputs: dict[str, Any] | None = None, required: list[str] | tuple[str, ...] = ()
) -> dict[str, Any]:
    """Any API's action through api_adapter (Plans/api-adapter.plan.md), through the app (POST /actions/run):
    the library's APIs by name, the project's local sandbox API as "local". Its one envelope: ok, status,
    kind, records / record / value / file, paging, shape (with its drift), raw, error. `required`: field paths
    that must be there (only these fail a call when the API's answer changes)."""
    info = ensure_server()
    sent = {"api": api, "action": action, "inputs": inputs or {}, "required": list(required)}
    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}/actions/run",
        data=json.dumps(sent, default=str).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 (127.0.0.1)
            answer: dict[str, Any] = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            said = json.loads(error.read() or b"{}").get("error") or error.reason
        except ValueError:
            said = error.reason
        raise ApiCallError(int(error.code), str(said)) from None
    return answer


def records(answer: dict[str, Any]) -> Any:
    """An envelope's records as an Arrow table, through the adapter (api_adapter's table)."""
    from swissarmybench.adapters import adapter, api_adapter

    return api_adapter.table(answer, adapter)
