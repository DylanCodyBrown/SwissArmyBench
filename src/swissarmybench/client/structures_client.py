"""Structures from any Python: a saved structure's value, its list of records as a table, and a value of
yours shown on the Structures page.

    gates = sab.structure("gates")                       # the saved file's value: a dict or a list
    rules = sab.structure("gates", "$.gates[0]")         # the node at a path
    orders = sab.structure_table("payload", "$.orders")  # a list of records as a DataFrame (dotted keys)
    sab.show_structure(response, name="payload")         # a dict or list opened on the Structures page

With the app running, a structure is found by its name (the open project's structures/ folder, or the
Workbench's own); without it, a file of that name (gates.json, gates.toml, gates.yaml) beside this Python's
working folder or in its structures/ folder. Standard library only (YAML needs PyYAML, XML is the app's).
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

from swissarmybench.client.push_client import ServerNotRunningError, ensure_server
from swissarmybench.domain import structures as rules

_TIMEOUT_SECONDS: float = 60.0


def _call(method: str, path: str, body: Any = None) -> Any:
    import urllib.error
    import urllib.request

    info = ensure_server()
    data = None if body is None else json.dumps(body, default=str).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 (fixed http://127.0.0.1 URL)
            return json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", "replace")
        if error.code == 404:
            raise LookupError(message) from None
        raise RuntimeError(f"Swiss Army Bench refused ({error.code}): {message}") from None


def _from_file(name: str) -> Any:
    for folder in (Path.cwd(), Path.cwd() / "structures"):
        for suffix, fmt in rules.SUFFIXES.items():
            file = folder / (name + suffix)
            if not file.is_file():
                continue
            text = file.read_text(encoding="utf-8-sig")
            if fmt == "yaml":
                import yaml  # type: ignore[import-untyped]  # optional: only for a YAML file

                return yaml.safe_load(text)
            return rules.parse(text, fmt)
    raise LookupError(f"There is no structure {name}: no {name}.json, .yaml, .toml or .xml here.")


def structure(name: str, path: str = "$") -> Any:
    """A saved structure's value (a dict, a list, a value), or the node at `path` ("$.orders[0]")."""
    try:
        query = urllib.parse.urlencode({"name": name, "path": path})
        return _call("GET", f"/structures/saved?{query}")["value"]
    except ServerNotRunningError:
        value = _from_file(name)
        return rules.get(value, path) if path not in ("", "$") else value


def structure_table(name: str, path: str = "$") -> Any:
    """The list of records at `path` as a table: a pandas DataFrame when pandas is here (nested keys
    dotted: customer.region), else the list of flat dicts."""
    rows = rules.records(structure(name, path), path)
    try:
        import pandas
    except ImportError:
        return rows
    return pandas.DataFrame.from_records(rows)


def show_structure(value: Any, name: str = "Python") -> dict[str, Any]:
    """A dict or a list (anything JSON can hold) opened as a tab of the Structures page."""
    plain = json.loads(json.dumps(value, default=str))
    answer: dict[str, Any] = _call(
        "POST", "/structures", {"value": plain, "name": name, "origin": {"kind": "kernel", "variable": name}}
    )
    return {"id": answer.get("id"), "name": answer.get("name")}
