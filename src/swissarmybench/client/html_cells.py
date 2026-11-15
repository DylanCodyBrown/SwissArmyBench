"""An HTML cell's names, filled in the kernel (docs/ideas.md, 2026-11-14; the Workbench runs the cell
as `%%sab_html`).

`{{ name }}` in an HTML cell is a variable of this Python. This module reads each one and says what
goes into the design (the rules are domain/html_cells.py's): a single value as its text; a table (a
pandas or Polars DataFrame, an Arrow table, a DuckDB relation) as its first rows; a figure or a picture
as a PNG. Nothing a value holds can become markup or script: the text is escaped where it is made.

`show` sends the design as an output: the filled HTML (what plain Jupyter's `%%html` would show), and
beside it each name's value, so the Workbench can fill the cell's HTML again as it is edited.
`marks` says, for some names, a short mark of what each would draw now: the Workbench compares it
with the mark from the cell's last run to say "Out of date".

Standard library only; pandas, Polars, Arrow, DuckDB and matplotlib are told by their shape, never
imported here.
"""

from __future__ import annotations

import base64
import io
import json
import sys
from typing import Any

from swissarmybench.domain import html_cells as rules

_MISSING: Any = object()
MIME: str = "application/vnd.swissarmybench.html-cell+json"


def _namespace() -> dict[str, Any]:
    ipython = sys.modules.get("IPython")
    shell = ipython.get_ipython() if ipython is not None else None
    if shell is not None:
        return shell.user_ns  # type: ignore[no-any-return]
    main = sys.modules.get("__main__")
    return vars(main) if main is not None else {}


def _module(value: Any) -> str:
    return str(getattr(type(value), "__module__", "") or "").split(".")[0]


def _table(value: Any) -> dict[str, Any] | None:
    """A table's first rows, by its kind (None: not a table)."""
    module, kind = _module(value), type(value).__name__
    need = rules.DATA_ROWS
    if module == "pandas" and kind == "DataFrame":
        head = value.head(need)
        columns = [str(c) for c in head.columns]
        rows = [list(row) for row in head.itertuples(index=False, name=None)]
        return rules.table_value(columns, rows, len(value), len(columns))
    if module == "polars" and kind == "DataFrame":
        head = value.head(need)
        rows = [list(row) for row in head.rows()]
        return rules.table_value(list(head.columns), rows, value.height, value.width)
    if module == "pyarrow" and kind in ("Table", "RecordBatch"):
        columns = list(value.schema.names)
        head = value.slice(0, need).to_pylist()
        rows = [[row.get(c) for c in columns] for row in head]
        return rules.table_value(columns, rows, value.num_rows, len(columns))
    if module in ("duckdb", "_duckdb") and kind == "DuckDBPyRelation":
        columns = list(value.columns)
        rows = [list(row) for row in value.limit(need).fetchall()]
        total = len(rows)
        if total >= need:
            total = int(value.count("*").fetchall()[0][0])
        return rules.table_value(columns, rows, total, len(columns))
    return None


def _picture(value: Any, name: str) -> dict[str, Any] | None:
    """A figure or an image as a PNG (None: not a picture, or too large to put in a design)."""
    data: Any = None
    module = _module(value)
    if module == "matplotlib" and hasattr(value, "savefig"):
        target = io.BytesIO()
        value.savefig(target, format="png", bbox_inches="tight")
        data = target.getvalue()
    elif hasattr(value, "_repr_png_"):
        data = value._repr_png_()
        if isinstance(data, tuple):  # (bytes, metadata)
            data = data[0]
        if isinstance(data, str):  # already base64
            data = base64.b64decode(data)
    if not isinstance(data, bytes | bytearray) or not data:
        return None
    if len(data) > rules.PICTURE_BYTES:
        return rules.text_value(f"({name}: a picture too large for a design)")
    return rules.picture_value(base64.b64encode(bytes(data)).decode("ascii"), name)


def value_of(name: str, namespace: dict[str, Any] | None = None) -> dict[str, Any]:
    """What `{{ name }}` draws. A name this Python does not hold, or a value that cannot be read, is a
    plain marker in the design, never an error."""
    held = (namespace if namespace is not None else _namespace()).get(name, _MISSING)
    if held is _MISSING:
        return rules.missing_value(name)
    try:
        return _table(held) or _picture(held, name) or rules.text_value(held)
    except Exception as error:
        return rules.text_value(f"({name} could not be shown: {type(error).__name__})")


def values(names: list[str], namespace: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    return {name: value_of(name, namespace) for name in names[: rules.MAX_NAMES] if name.isidentifier()}


def marks(names: list[str], namespace: dict[str, Any] | None = None) -> str:
    """Each name's mark, as JSON text: the same mark as at the cell's last run, the same design."""
    return json.dumps({name: rules.digest(value) for name, value in values(names, namespace).items()})


def bundle(text: str, namespace: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The cell's output as (data, metadata): the filled HTML, and what filled it."""
    found = values(rules.names(text), namespace)
    filled = rules.fill(text, found)
    detail = {
        "values": found,
        "marks": {name: rules.digest(value) for name, value in found.items()},
        "missing": list(filled.missing),
        "notes": list(filled.notes),
    }
    data = {"text/html": filled.html, "text/plain": f"An HTML cell ({len(found)} filled)", MIME: detail}
    return data, {"swissarmybench": {"html_cell": True}}


def show(text: str, namespace: dict[str, Any] | None = None) -> None:
    """Fill the cell's HTML from this Python's variables and send it as the cell's output."""
    data, metadata = bundle(text, namespace)
    display = sys.modules.get("IPython.display") or __import__("IPython.display").display
    display.publish_display_data(data, metadata)


def _magic(line: str, cell: str) -> None:
    show(cell)


def install(shell: Any) -> None:
    """`%%sab_html`: how the Workbench runs an HTML cell that asks for names."""
    if shell is not None:
        for name in ("sab_html", "sag_html"):  # sag_html: the old name, for old notebooks (renamed.py)
            shell.register_magic_function(_magic, magic_kind="cell", magic_name=name)
