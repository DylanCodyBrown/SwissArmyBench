"""A Workbench kernel tells the app it used a connection (the Connections page counts its calls this
session): `%%sql`, `%%dax`, `sab.sql` and `sab.dax` are queries, `sab.read` a table read, `sab.blade` and
`sab.connection` a connect.

Only inside a Workbench kernel (SWISSARMYBENCH_KERNEL is set there): code in the user's own Jupyter or
terminal is not counted. Fire and forget: a daemon thread sends one small POST and nothing waits for it
or hears about a failure. It carries the connection's name and the kind of call, nothing else (no SQL,
no rows). Standard library only, like the rest of the client.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.parse
import urllib.request

from swissarmybench.client.push_client import _read_info

_TIMEOUT_SECONDS = 2.0


def _send(name: str, kind: str, ok: bool) -> None:
    try:
        info = _read_info()
        if not info or not info.get("port") or not info.get("token"):
            return
        request = urllib.request.Request(
            f"http://127.0.0.1:{int(info['port'])}/connections/{urllib.parse.quote(name, safe='')}/used",
            data=json.dumps({"kind": kind, "ok": ok}).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS):  # noqa: S310 (fixed http://127.0.0.1 URL)
            pass
    except Exception:  # noqa: S110 (fire and forget: a count that did not arrive changes nothing)
        pass


def report(name: str, kind: str, ok: bool = True) -> None:
    """Tell the app a connection was used (`name`: the connection; a Power BI dataset's `Finance/Sales
    model` counts for Finance). Nothing happens outside a Workbench kernel."""
    if not os.environ.get("SWISSARMYBENCH_KERNEL", ""):
        return
    base = name.split("/")[0].strip()
    if base:
        threading.Thread(target=_send, args=(base, kind, ok), daemon=True, name="sab-connection-use").start()
