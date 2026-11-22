"""A Workbench kernel's query waits for one of its connection's slots (services/connection_slots.py: at most
so many queries at once on one connection, the agent's share smaller, the rest waiting in line).

`with slot("Warehouse", "query", sql=text):` asks the app for a slot, waits while the connection is full (the
cell shows "Waiting for a slot on Warehouse (2nd in line)", and can be interrupted: its place is given up),
renews the slot's lease while the query runs (a kernel that dies stops renewing; its slot goes back by itself)
and gives it back however the query ends.

Outside a Workbench kernel (plain Python, Jupyter, an exported automation), or with no app answering: no gate,
never a failure. Standard library only, like the rest of the client.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any

from swissarmybench.client.push_client import _read_info

_TIMEOUT_SECONDS = 5.0
WAIT_POLL_SECONDS = 0.5
RENEW_SECONDS = 5.0


class SlotGaveUp(RuntimeError):
    """The query waited past its connection's wait limit, or was cancelled in the Queries window."""


def kernel_id() -> str:
    return os.environ.get("SWISSARMYBENCH_KERNEL", "")


def kernel_headers() -> dict[str, str]:
    """What a kernel's request to the app carries so its connection calls count as this kernel's."""
    kernel = kernel_id()
    if not kernel or not kernel.replace("-", "").replace("_", "").isalnum() or len(kernel) > 64:
        return {}
    return {"X-Kernel": kernel, "X-Sab-Client": f"kernel-{kernel}"[:40]}


def _post(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    """One small POST to the app; None when no app answers (or it is an older one without the route)."""
    info = _read_info()
    if not info or not info.get("port") or not info.get("token"):
        return None
    request = urllib.request.Request(
        f"http://127.0.0.1:{int(info['port'])}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"}
        | kernel_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 (fixed http://127.0.0.1 URL)
            answer = json.loads(response.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return answer if isinstance(answer, dict) else None


def cancel_mine() -> None:
    """This kernel's waiting requests to the app given up (an interrupt during DuckDB SQL naming a table)."""
    if kernel_id():
        _post("/connections/queries/cancel-mine", {})


class _Shown:
    """The cell's one line while it waits (IPython's display, updated in place; else printed on a change)."""

    def __init__(self) -> None:
        self._handle: Any = None
        self._last = ""

    def say(self, words: str) -> None:
        if words == self._last:
            return
        self._last = words
        try:
            from IPython.display import display

            if self._handle is None:
                shown = {"text/plain": words}
                self._handle = display(shown, raw=True, display_id=True)  # type: ignore[no-untyped-call]
            else:
                self._handle.update({"text/plain": words}, raw=True)
        except Exception:
            print(words, flush=True)

    def done(self) -> None:
        if self._handle is not None:
            with contextlib.suppress(Exception):
                self._handle.update({"text/plain": ""}, raw=True)


@contextlib.contextmanager
def slot(
    connection: str,
    kind: str = "query",
    sql: str = "",
    dialect: str = "",
    targets: tuple[str, ...] = (),
) -> Iterator[None]:
    """The query runs inside one of the connection's slots (no gate outside a Workbench kernel)."""
    name = connection.split("/")[0].strip()
    if not kernel_id() or not name:
        yield
        return
    body = {"connection": name, "kind": kind, "sql": sql, "dialect": dialect, "targets": list(targets)}
    state = _post("/connections/slots/acquire", body)
    if not state or not state.get("ticket"):
        yield  # no app, or one without slots: no gate
        return
    ticket = urllib.parse.quote(str(state["ticket"]), safe="")
    shown = _Shown()
    try:
        while state and state.get("state") == "waiting":
            shown.say(str(state.get("words") or f"Waiting for a slot on {name}"))
            time.sleep(WAIT_POLL_SECONDS)
            state = _post(f"/connections/slots/{ticket}/renew", {})
    except KeyboardInterrupt:
        _post(f"/connections/slots/{ticket}/release", {"outcome": "cancelled"})
        shown.done()
        raise
    shown.done()
    if state and state.get("state") not in ("running", None):
        raise SlotGaveUp(str(state.get("words") or f"No slot on {name}."))
    stop = threading.Event()

    def keep() -> None:
        while not stop.wait(RENEW_SECONDS):
            _post(f"/connections/slots/{ticket}/renew", {})

    renewer = threading.Thread(target=keep, daemon=True, name="sab-connection-slot")
    renewer.start()
    outcome = "ok"
    try:
        yield
    except KeyboardInterrupt:
        outcome = "cancelled"
        raise
    except BaseException:
        outcome = "failed"
        raise
    finally:
        stop.set()
        _post(f"/connections/slots/{ticket}/release", {"outcome": outcome})
