# /// swissarmybench-blade
# format = 1
# name = "Power BI refresh status"
# kind = "other"
# description = "A Power BI dataset's latest refresh: running, completed or failed"
# tags = ["power bi", "refresh"]
# family = "Power BI"
# variable = "refresh_status"
# ///
"""The latest refresh of a dataset in your Power BI workspace: running, completed or failed.

    refresh_status = sab.blade("Power BI refresh status")
    refresh_status("Sales model")
    # {"dataset": "Sales model", "status": "completed", "started": "...", "seconds": 42.0, ...}

The status is "never" when the dataset has not been refreshed yet. "Power BI refresh history" gives
the refreshes before it, as a table.

It signs in through your Power BI workspace connection: WORKSPACE below names it (or name the dataset
as "Finance/Sales model"; or pass workspace="..."). The connection's own sign-in is borrowed, never a copy
of its secret. Errors from Power BI arrive as PowerBIActionError, in plain words.

Power BI's request: GET .../groups/{workspace}/datasets/{dataset}/refreshes?$top=1
"""

import json
import time
import urllib.error
import urllib.request
from typing import Any

import pandas as pd

import swissarmybench as sab

# ===== the workspace and its sign-in (the same in every Power BI starter) =====

# Your Power BI workspace connection's name (the Connections window). A dataset may also be named with
# its connection, as the app names it: "Finance/Sales model".
WORKSPACE = "Finance"


class PowerBIActionError(RuntimeError):
    """Power BI refused, or the connection is not a Power BI workspace: the message says why."""


def _workspace(connection: Any = None) -> Any:
    """The workspace connection, signed in its own way (its vault, its app registration): the action
    borrows that sign-in and never holds a copy of the secret."""
    named = connection is None or isinstance(connection, str)
    conn = sab.connection(connection or WORKSPACE) if named else connection
    if not hasattr(conn, "url") or not hasattr(conn, "dataset"):
        raise PowerBIActionError(f"{connection or WORKSPACE} is not a Power BI workspace connection.")
    return conn


def _place(item: str, workspace: Any = None) -> tuple[Any, str]:
    """The workspace and the item's own name: "Finance/Sales model" names both."""
    connection, slash, name = str(item).partition("/")
    if slash and workspace is None:
        return _workspace(connection), name.strip()
    return _workspace(workspace), str(item).strip()


def _token(conn: Any) -> str:
    """The connection's current token, signed in again when it is about to run out."""
    if hasattr(conn, "access_token"):
        return str(conn.access_token())
    if time.time() > conn.expires - 300:  # a connection saved before access_token() existed
        conn.token, conn.expires = conn.sign_in()
    return str(conn.token)


_HINTS = {
    400: "Power BI could not take the request as sent.",
    401: "The sign-in was not accepted: test the workspace connection.",
    403: "This sign-in may not do that: it must be a member (or admin) of the workspace.",
    404: "The workspace has no such item: check its name.",
    409: "Power BI is busy with that item: a refresh may already be running.",
    429: "Too many requests to Power BI: wait a minute.",
}


def _plain(status: int, body: bytes) -> str:
    """Power BI's refusal in plain words: its own message, then what usually causes that status."""
    try:
        said = json.loads(body)
        error = said.get("error", said) if isinstance(said, dict) else said
        message = (error.get("message") or error.get("code")) if isinstance(error, dict) else error
    except ValueError:
        message = body.decode("utf-8", "replace")[:300]
    words = str(message or "no reason given").strip().splitlines()[0]
    return f"Power BI refused ({status}): {words}. {_HINTS.get(status, '')}".strip()


def _call(conn: Any, method: str, path: str, body: Any = None) -> tuple[Any, dict[str, str]]:
    """One request to Power BI's REST API, under the workspace: its JSON answer (None when it sends
    none) and its headers."""
    data = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {_token(conn)}", "Content-Type": "application/json"}
    request = urllib.request.Request(conn.url + path, data, headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as answer:
            raw = answer.read()
            return (json.loads(raw) if raw.strip() else None), dict(answer.headers.items())
    except urllib.error.HTTPError as refused:
        raise PowerBIActionError(_plain(refused.code, refused.read())) from None
    except urllib.error.URLError as error:
        raise PowerBIActionError(f"Power BI could not be reached: {error.reason}") from None


def _dataset(conn: Any, name: str) -> Any:
    """A dataset of the workspace, by its name or id (the connection's own conn.dataset)."""
    try:
        return conn.dataset(name)
    except RuntimeError as error:  # the connection's own PowerBIError: no such dataset, or a refusal
        raise PowerBIActionError(str(error)) from None


# ===== this starter =====

# Power BI's words for a refresh's state, and ours ("Unknown" is Power BI's word for one still running).
STATES = {
    "Unknown": "running",
    "NotStarted": "not started",
    "Completed": "completed",
    "Failed": "failed",
    "Cancelled": "cancelled",
    "Disabled": "disabled",
}


def _refresh_row(found: dict[str, Any]) -> dict[str, Any]:
    """One refresh as Power BI lists it, in plain words."""
    started, ended = found.get("startTime"), found.get("endTime")
    seconds = None
    if started and ended:
        seconds = (pd.Timestamp(ended) - pd.Timestamp(started)).total_seconds()
    error = found.get("serviceExceptionJson")
    if error:
        try:
            said = json.loads(error)
            error = said.get("errorDescription") or said.get("errorCode") or error
        except ValueError:
            pass
    return {
        "status": STATES.get(str(found.get("status")), str(found.get("status") or "").lower()),
        "started": started,
        "ended": ended,
        "seconds": seconds,
        "type": found.get("refreshType"),
        "error": error or None,
        "request_id": found.get("requestId"),
    }


def _refreshes(conn: Any, dataset_id: str, top: int) -> list[dict[str, Any]]:
    """The dataset's latest refreshes, newest first."""
    answer, _ = _call(conn, "GET", f"/datasets/{dataset_id}/refreshes?$top={int(top)}")
    return [_refresh_row(found) for found in (answer or {}).get("value", [])]


def refresh_status(dataset: str, workspace: Any = None) -> dict[str, Any]:
    """The latest refresh of `dataset`: {"dataset", "status", "started", "ended", "seconds", "type",
    "error", "request_id"}; status is running, completed, failed, cancelled, disabled or never."""
    conn, name = _place(dataset, workspace)
    found = _dataset(conn, name)
    latest = _refreshes(conn, found.id, 1)
    if not latest:
        return {"dataset": found.name, "status": "never"}
    return {"dataset": found.name, **latest[0]}
