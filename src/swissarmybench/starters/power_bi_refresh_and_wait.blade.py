# /// swissarmybench-blade
# format = 1
# name = "Power BI refresh and wait"
# kind = "other"
# description = "Refresh a Power BI dataset and wait until it is done"
# tags = ["power bi", "refresh"]
# family = "Power BI"
# variable = "refresh_and_wait"
# ///
"""Refresh a dataset in your Power BI workspace and wait until it is done.

    refresh_and_wait = sab.blade("Power BI refresh and wait")
    done = refresh_and_wait("Sales model", timeout=1800, every=15)
    # {"dataset": "Sales model", "status": "completed", "seconds": 42.0, ...}

It asks Power BI how the refresh is going every `every` seconds. A refresh that fails raises
PowerBIActionError with Power BI's reason; one still running after `timeout` seconds raises it too
(the refresh itself goes on in Power BI).

It signs in through your Power BI workspace connection: WORKSPACE below names it (or name the dataset
as "Finance/Sales model"; or pass workspace="..."). The connection's own sign-in is borrowed, never a copy
of its secret. Errors from Power BI arrive as PowerBIActionError, in plain words.

Power BI's requests: POST .../datasets/{dataset}/refreshes, then GET .../datasets/{dataset}/refreshes
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

NOTIFY = ("NoNotification", "MailOnFailure", "MailOnCompletion")


def _notify(notify: str) -> str:
    """Who Power BI emails about the refresh. An app registration (service principal) may only use
    NoNotification."""
    if notify not in NOTIFY:
        raise PowerBIActionError(f"notify is one of {', '.join(NOTIFY)}, not {notify!r}.")
    return notify


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


def refresh_and_wait(
    dataset: str,
    timeout: float = 1800,
    every: float = 15,
    notify: str = "NoNotification",
    workspace: Any = None,
) -> dict[str, Any]:
    """Start a refresh of `dataset` and wait for it: its last state, or PowerBIActionError when it
    fails or is still running after `timeout` seconds."""
    conn, name = _place(dataset, workspace)
    found = _dataset(conn, name)
    _, headers = _call(conn, "POST", f"/datasets/{found.id}/refreshes", {"notifyOption": _notify(notify)})
    request_id = headers.get("RequestId") or headers.get("requestid") or ""
    deadline = time.monotonic() + timeout
    while True:
        # The refresh this call started: by its request id, else the newest one.
        listed = _refreshes(conn, found.id, 5)
        mine = next((r for r in listed if request_id and r["request_id"] == request_id), None)
        latest = mine or (listed[0] if listed and not request_id else None)
        if latest and latest["status"] not in ("running", "not started"):
            if latest["status"] != "completed":
                reason = f": {latest['error']}" if latest["error"] else ""
                raise PowerBIActionError(f"The refresh of {found.name} {latest['status']}{reason}")
            return {"dataset": found.name, **latest}
        if time.monotonic() > deadline:
            raise PowerBIActionError(
                f"The refresh of {found.name} is still running after {timeout:g} seconds "
                "(it goes on in Power BI)."
            )
        time.sleep(every)
