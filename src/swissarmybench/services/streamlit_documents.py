"""A document's cells as a Streamlit app reads them (services/streamlit.py): sent by its window as the
user types, or read from its file. The rules are domain/streamlit_cells.py's."""

from __future__ import annotations

from typing import Any

from swissarmybench.domain import html_cells, notebooks
from swissarmybench.domain import streamlit_cells as rules
from swissarmybench.domain.streamlit_cells import StreamlitError

Cells = tuple[list[tuple[int, str]], dict[int, str], dict[int, str]]


def sent_cells(sent: Any) -> Cells:
    """The cells a window sends ({"cell", "code", "name"?, "kind"?}): (number, code) in order, the
    names the cells have, and which are Markdown or HTML cells. A Markdown or HTML cell sends its text
    (a script's HTML cell its lines, with "form": "script"); its code is the page's (rules.text_code)."""
    if not isinstance(sent, list) or len(sent) > rules.MAX_PIECES:
        raise StreamlitError(
            'Send the cells as a list: [{"cell": 4, "code": "...", "name"?, "kind"?: "markdown" | "html"}].'
        )
    found: list[tuple[int, str]] = []
    names: dict[int, str] = {}
    kinds: dict[int, str] = {}
    seen: set[int] = set()
    for raw in sent:
        cell = raw.get("cell") if isinstance(raw, dict) else None
        code = raw.get("code") if isinstance(raw, dict) else None
        if isinstance(cell, bool) or not isinstance(cell, int) or cell < 1 or cell in seen:
            raise StreamlitError("Each cell is named by its own number, once.")
        if not isinstance(code, str) or len(code) > notebooks.MAX_CELL_CHARS:
            raise StreamlitError("A cell's code is text of at most a million characters.")
        try:
            name = notebooks.check_name(raw.get("name"))
        except notebooks.NotebookError as error:
            raise StreamlitError(str(error)) from None
        kind = raw.get("kind", "code")
        if kind not in ("code", *rules.TEXT_KINDS):
            raise StreamlitError('A cell\'s kind is "code", "markdown" or "html".')
        seen.add(cell)
        if kind != "code":
            text = html_cells.read_script_body(code)[0] if raw.get("form") == "script" else code
            if text is None:
                continue  # a script's HTML cell whose string is not whole yet: not on a page
            code = rules.text_code(kind, text, cell)
            kinds[cell] = kind
        found.append((cell, code))
        if name:
            names[cell] = name
    return found, names, kinds


def file_cells(path: str, text: str) -> Cells:
    """A notebook's or script's file as `sent_cells` gives a window's cells (rules.linkable)."""
    found = rules.linkable(path, text)
    return (
        [(c.number, c.code) for c in found],
        {c.number: c.name for c in found if c.name},
        {c.number: c.kind for c in found if c.kind != "code"},
    )
