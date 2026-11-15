"""The values in a lineage (docs/ideas.md, lineage with values, 2026-11-15), summarised where they live.

Two places hold a cell's values:

  the kernel     a notebook's or script's Workbench kernel: `summaries(names)` is evaluated there as a
                 user expression (nothing printed, nothing in the history) and answers JSON text
  a live page    a Streamlit page the canvas plays: after each block runs, the page calls `note(...)`,
                 which writes the block's values to `lineage-<page>.json` in the page's own temporary
                 folder (removed when the app stops). A filter changed on the page runs the page again,
                 and the file follows

A value is never sent whole: a table is its shape, its column names and its first few rows; a text is
cut; a figure is a small picture. Nothing here imports Swiss Army Bench or anything outside the standard
library, so a copy of this file sits beside a live page (`sab_lineage.py`) in a Python that has only
Streamlit; pandas, Polars, Arrow, DuckDB and matplotlib are told by their shape, never imported.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

HEAD_ROWS: int = 5
HEAD_COLUMNS: int = 12
CELL_CHARS: int = 60
TEXT_CHARS: int = 400
MAX_NAMES: int = 60
PICTURE_BYTES: int = 300_000
PICTURE_DPI: int = 40
_PAGE = re.compile(r"^[A-Za-z0-9]{1,16}$")
_MISSING: Any = object()


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _module(value: Any) -> str:
    return str(getattr(type(value), "__module__", "") or "").split(".")[0]


def _plain(value: Any) -> Any:
    """A value as JSON holds it: numbers, texts, true, false and null as they are; the rest as text."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if abs(value) < 2**53 else str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return _cut(str(value), CELL_CHARS)


def _table(columns: list[Any], rows: list[list[Any]], total: int, width: int) -> dict[str, Any]:
    names = [_cut(str(c), CELL_CHARS) for c in columns[:HEAD_COLUMNS]]
    head = [[_plain(v) for v in list(row)[: len(names)]] for row in rows[:HEAD_ROWS]]
    return {"kind": "table", "rows": total, "columns": width, "names": names, "head": head}


def table_of(value: Any) -> dict[str, Any] | None:
    """A table's shape and first rows, by its kind (None: not a table)."""
    module, kind = _module(value), type(value).__name__
    if module == "pandas" and kind == "DataFrame":
        head = value.head(HEAD_ROWS)
        rows = [list(row) for row in head.itertuples(index=False, name=None)]
        return _table(list(value.columns), rows, len(value), len(value.columns))
    if module == "pandas" and kind == "Series":
        rows = [[v] for v in value.head(HEAD_ROWS).tolist()]
        return _table([value.name if value.name is not None else "value"], rows, len(value), 1)
    if module == "polars" and kind == "DataFrame":
        return _table(
            list(value.columns), [list(r) for r in value.head(HEAD_ROWS).rows()], value.height, value.width
        )
    if module == "pyarrow" and kind in ("Table", "RecordBatch"):
        columns = list(value.schema.names)
        rows = [[row.get(c) for c in columns] for row in value.slice(0, HEAD_ROWS).to_pylist()]
        return _table(columns, rows, value.num_rows, len(columns))
    if module in ("duckdb", "_duckdb") and kind == "DuckDBPyRelation":
        rows = [list(r) for r in value.limit(HEAD_ROWS).fetchall()]
        total = int(value.count("*").fetchall()[0][0])
        return _table(list(value.columns), rows, total, len(value.columns))
    return None


def picture_of(value: Any) -> dict[str, Any] | None:
    """A figure or an image as a small PNG (None: not a picture, or too large)."""
    data: Any = None
    if _module(value) == "matplotlib" and hasattr(value, "savefig"):
        target = io.BytesIO()
        value.savefig(target, format="png", dpi=PICTURE_DPI, bbox_inches="tight")
        data = target.getvalue()
    elif hasattr(value, "_repr_png_"):
        data = value._repr_png_()
        if isinstance(data, tuple):
            data = data[0]
        if isinstance(data, str):
            data = base64.b64decode(data)
    elif _module(value) in ("plotly", "altair") or type(value).__name__ in ("Figure", "Chart"):
        return {"kind": "chart", "text": f"a {type(value).__name__} ({_module(value)})"}
    if not isinstance(data, bytes | bytearray) or not data or len(data) > PICTURE_BYTES:
        return None
    return {"kind": "picture", "png": base64.b64encode(bytes(data)).decode("ascii")}


def summary(value: Any) -> dict[str, Any]:
    """What a lineage card shows of one value: a table's shape and first rows, a picture, else the
    value as itself (cut). A value that cannot be read says so, never an error."""
    try:
        found = table_of(value) or picture_of(value)
        if found is not None:
            return found
        return {"kind": "value", "text": _cut(str(value), TEXT_CHARS), "type": type(value).__name__}
    except Exception as error:
        return {"kind": "value", "text": f"(could not be shown: {type(error).__name__})", "type": ""}


def _namespace() -> dict[str, Any]:
    ipython = sys.modules.get("IPython")
    shell = ipython.get_ipython() if ipython is not None else None
    if shell is not None:
        return shell.user_ns  # type: ignore[no-any-return]
    main = sys.modules.get("__main__")
    return vars(main) if main is not None else {}


def summaries(names: list[str], namespace: Mapping[str, Any] | None = None) -> str:
    """Each name's summary, as JSON text (the kernel's answer). A name this Python does not hold is
    "missing": the cell that makes it has not run here."""
    held = namespace if namespace is not None else _namespace()
    out: dict[str, Any] = {}
    for name in names[:MAX_NAMES]:
        if not isinstance(name, str) or not name.isidentifier():
            continue
        value = held.get(name, _MISSING)
        out[name] = {"kind": "missing"} if value is _MISSING else summary(value)
    return json.dumps(out, default=str)


# ===== a live page: each block's values after it runs =====

_runs: dict[str, dict[str, Any]] = {}


def _file(page_file: str, page: str) -> Path:
    return Path(page_file).resolve().parent / f"lineage-{page}.json"


def _write(page_file: str, page: str) -> None:
    target = _file(page_file, page)
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=".lineage-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(_runs[page], out, default=str)
        os.replace(temporary, target)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass


def start(page_file: str, page: str) -> None:
    """A page starts running: its blocks' values are noted again from here."""
    if not _PAGE.match(page):
        return
    run = int(_runs.get(page, {}).get("run", 0)) + 1
    _runs[page] = {"page": page, "run": run, "blocks": {}}
    _write(page_file, page)


def note(
    page_file: str,
    page: str,
    block: str,
    getters: Mapping[str, Callable[[], Any]],
    error: BaseException | None = None,
) -> None:
    """A block ran: its names' values (each read through its getter; a NameError: not made), and its
    error when it failed. Nothing here ever stops the page."""
    try:
        _note(page_file, page, block, getters, error)
    except Exception:  # noqa: S110 (the lineage never breaks the page it watches)
        pass


def _note(
    page_file: str,
    page: str,
    block: str,
    getters: Mapping[str, Callable[[], Any]],
    error: BaseException | None,
) -> None:
    if not _PAGE.match(page) or page not in _runs:
        return
    found: dict[str, Any] = {}
    for name, get in list(getters.items())[:MAX_NAMES]:
        try:
            found[name] = summary(get())
        except NameError:
            found[name] = {"kind": "missing"}
        except Exception as failed:
            found[name] = {
                "kind": "value",
                "text": f"(could not be read: {type(failed).__name__})",
                "type": "",
            }
    said = None if error is None else _cut(f"{type(error).__name__}: {error}", TEXT_CHARS)
    _runs[page]["blocks"][block] = {"values": found, "error": said}
    _write(page_file, page)
