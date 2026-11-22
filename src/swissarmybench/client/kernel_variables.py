"""The Workbench's Variables overlay, read inside the kernel: every variable the user's code made, with
its type, size and a short preview; the connections and blades by their names in code (open, or not yet);
and the environment variables that vaults, secret blades and connection passwords use, by name only.

`snapshot()` is called by the Workbench as a user expression (nothing is printed, nothing runs in the
cell's history); it answers a JSON text. A value is never read whole: a table gives its shape, a list its
length, and a preview stops at a few hundred characters. A secret's value never leaves the kernel.
Standard library only.
"""

from __future__ import annotations

import json
import os
import reprlib
import sys
import time
import types
from typing import Any

from swissarmybench.client.kernel_values import is_table, type_name

_PREVIEW = reprlib.Repr()
_PREVIEW.maxstring = 120
_PREVIEW.maxother = 120
_PREVIEW.maxlist = _PREVIEW.maxtuple = _PREVIEW.maxset = _PREVIEW.maxdict = 8
_MAX_VARIABLES: int = 500
_MAX_PREVIEW: int = 200
_PREVIEW_SECONDS: float = 1.0
_MAX_KIDS: int = 50
_GONE = object()
# IPython's own names, and the names the Workbench's setup makes.
_HIDDEN = frozenset({"In", "Out", "exit", "quit", "get_ipython", "open", "sab"})


def _count(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def _size(value: Any) -> str:
    """Rows by columns for a table, the shape of an array, the length of anything that has one."""
    shape = getattr(value, "shape", None)
    if isinstance(shape, tuple) and all(isinstance(n, int) for n in shape):
        if len(shape) == 2 and hasattr(value, "columns"):
            return f"{_count(shape[0], 'row')} by {_count(shape[1], 'column')}"
        return " by ".join(f"{n:,}" for n in shape) or "scalar"
    num_rows = getattr(value, "num_rows", None)  # a pyarrow Table
    if isinstance(num_rows, int) and hasattr(value, "num_columns"):
        return f"{_count(num_rows, 'row')} by {_count(value.num_columns, 'column')}"
    if isinstance(value, str | bytes | list | tuple | dict | set | frozenset):
        return f"{len(value):,}"
    return ""


def _preview(value: Any) -> str:
    """A short look at the value, never the whole of a big one."""
    columns = getattr(value, "columns", None)
    if columns is not None and getattr(value, "shape", None) is not None:
        names = [str(c) for c in list(columns)[:8]]
        more = len(columns) - len(names)
        return "columns: " + ", ".join(names) + (f" and {more} more" if more > 0 else "")
    try:
        text = _PREVIEW.repr(value)
    except Exception as error:  # a repr that fails says so instead of breaking the overlay
        text = f"<no preview: {type(error).__name__}>"
    return text if len(text) <= _MAX_PREVIEW else text[: _MAX_PREVIEW - 1] + "…"


def _kids(value: Any) -> list[list[str]]:
    """One level inside a value, for the Environment's rows that unfold: a table's columns with their types,
    a dictionary's keys, a list's items (the first _MAX_KIDS; each a name, a type and a short look)."""
    columns = getattr(value, "columns", None)
    if columns is not None and getattr(value, "shape", None) is not None:
        types = getattr(value, "dtypes", None)
        named = [str(c) for c in list(columns)[:_MAX_KIDS]]
        kinds = [str(t) for t in list(types)[:_MAX_KIDS]] if types is not None else []
        return [[c, kinds[i] if i < len(kinds) else "", ""] for i, c in enumerate(named)]
    if isinstance(value, dict):
        pairs = [(k if isinstance(k, str) else repr(k), v) for k, v in list(value.items())[:_MAX_KIDS]]
    elif isinstance(value, list | tuple):
        pairs = [(f"[{i}]", v) for i, v in enumerate(value[:_MAX_KIDS])]
    else:
        return []
    return [[key, type_name(item), _safe_preview(item)] for key, item in pairs]


def names(namespace: dict[str, Any]) -> list[dict[str, str]]:
    """The watcher's report of what a session holds besides its tables (client/watcher.py): each variable's
    name, type and size, never a value. The Environment lists them; sorted, so a repeated look compares
    equal."""
    found: list[dict[str, str]] = []
    for name, value in list(namespace.items()):
        if not isinstance(name, str) or name.startswith("_") or name in _HIDDEN:
            continue
        if isinstance(value, types.ModuleType | types.FunctionType | types.BuiltinFunctionType | type):
            continue
        if len(found) >= _MAX_VARIABLES:
            break
        try:
            if is_table(value):
                continue
            found.append({"name": name, "type": type_name(value), "size": _size(value)})
        except Exception:  # noqa: S112 (one object that misbehaves costs its own row, never the list)
            continue
    return sorted(found, key=lambda row: row["name"].casefold())


def _user_namespace() -> dict[str, Any]:
    ipython = sys.modules.get("IPython")
    shell = ipython.get_ipython() if ipython is not None else None
    return shell.user_ns if shell is not None else {}


def forget(names: list[str], namespace: dict[str, Any] | None = None) -> str:
    """The Environment's Remove on a variable (and "Also delete it in Python" on a table): the names
    deleted from the user's namespace. Answers the ones that were there, as JSON."""
    held = _user_namespace() if namespace is None else namespace
    gone = [name for name in names if not name.startswith("_") and held.pop(name, _GONE) is not _GONE]
    return json.dumps(gone)


def rename(old: str, new: str, namespace: dict[str, Any] | None = None) -> str:
    """The Environment's Rename on a variable: the same object under its new name (never a copy). Answers
    {"renamed": bool, "why": ...} as JSON; a name already taken is not replaced."""
    held = _user_namespace() if namespace is None else namespace
    if old not in held:
        return json.dumps({"renamed": False, "why": f"{old} is not a variable any more."})
    if not new.isidentifier() or new.startswith("_") or new in _HIDDEN:
        return json.dumps({"renamed": False, "why": f"{new} is not a name Python can give a variable."})
    if new in held:
        return json.dumps({"renamed": False, "why": f"{new} is already a variable: remove it first."})
    held[new] = held.pop(old)
    return json.dumps({"renamed": True})


def _safe_preview(value: Any) -> str:
    try:
        return _preview(value)
    except Exception as error:
        return f"<could not be read: {type(error).__name__}>"


def snapshot(env_names: list[str] | None = None, namespace: dict[str, Any] | None = None) -> str:
    """The overlay's rows, as JSON: connections and blades, the user's variables, the environment."""
    if namespace is None:
        ipython = sys.modules.get("IPython")
        shell = ipython.get_ipython() if ipython is not None else None
        namespace = shell.user_ns if shell is not None else {}
    try:
        from swissarmybench.client.kernel_connections import code_names

        connections = code_names()
    except Exception:
        connections = {}
    rows: list[dict[str, Any]] = []
    left_out = 0
    started = time.monotonic()
    for name, value in list(namespace.items()):
        if name.startswith("_") or name in _HIDDEN or name in connections:
            continue
        if isinstance(value, types.ModuleType | types.FunctionType | types.BuiltinFunctionType | type):
            continue
        if len(rows) >= _MAX_VARIABLES:
            left_out += 1
            continue
        # One object that misbehaves (a property that raises, a slow repr) costs its own row, never the
        # list: its row says so; after a second of previews the rest show without one.
        row: dict[str, Any] = {"name": name, "type": "", "size": "", "value": "", "table": False}
        try:
            row["type"] = type_name(value)
            row["table"] = is_table(value)
            row["size"] = _size(value)
            quick = time.monotonic() - started < _PREVIEW_SECONDS
            row["value"] = _preview(value) if quick else "…"
            if quick:
                row["kids"] = _kids(value)
        except Exception as error:
            row["value"] = f"<could not be read: {type(error).__name__}>"
        rows.append(row)
    rows.sort(key=lambda r: r["name"].casefold())
    opened = [
        {
            "name": name,
            "connection": connection,
            "open": name in namespace,
            "type": type_name(namespace[name]) if name in namespace else "",
            "value": _safe_preview(namespace[name])
            if name in namespace
            else "opened when a cell first uses it",
            "table": name in namespace and is_table(namespace[name]),
        }
        for name, connection in sorted(connections.items())
    ]
    environment = [{"name": env, "set": bool(os.environ.get(env))} for env in sorted(set(env_names or []))]
    found = {"connections": opened, "variables": rows, "environment": environment, "left_out": left_out}
    return json.dumps(found, default=str)
