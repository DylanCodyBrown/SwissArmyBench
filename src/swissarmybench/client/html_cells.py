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

import json
import sys
from typing import Any

from swissarmybench.client.kernel_values import namespace as _namespace
from swissarmybench.domain import html_cells as rules

_MISSING: Any = object()
MIME: str = "application/vnd.swissarmybench.html-cell+json"


def value_of(name: str, namespace: dict[str, Any] | None = None) -> dict[str, Any]:
    """What `{{ name }}` draws. A name this Python does not hold, or a value that cannot be read, is a
    plain marker in the design, never an error."""
    held = (namespace if namespace is not None else _namespace()).get(name, _MISSING)
    if held is _MISSING:
        return rules.missing_value(name)
    return rules.record_of(held, name)  # told by its shape (a Streamlit page reads its values so too)


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
