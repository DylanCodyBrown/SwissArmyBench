"""Approved outputs (docs/ideas.md, lineage with values and approved outputs, 2026-11-15): the notebook
as the test surface. Pure rules, no I/O.

A cell's output is marked approved: its SNAPSHOT is kept in the cell's metadata
(`swissarmybench.approved`, beside its number and name, so plain Jupyter keeps it). A later run whose
snapshot differs is "Changed since approved", and says how:

  snapshot   a cell's outputs (nbformat's own records) as what is compared: the printed text (stdout;
             stderr holds warnings, which differ between computers), each
             table (read from the HTML pandas and Polars show: its columns, its first rows, its whole
             shape), a mark of each picture or chart, the error. Memory addresses (`at 0x7f...`) and run
             counts make no difference
  compare    an approval against a later snapshot: None when they are the same, else the difference: a
             line diff of the text; for a table its shape, the columns added and removed, and the
             changed cells (capped, the rest counted); a picture that changed; an error
  summary    the difference as plain lines, for the cell's amber note and the headless run's report
  zip        an approval without its rows (`without_rows`): its marks and shapes only, so a project's
             zip carries no rows and a check can still tell that an output changed

Standard library only, and nothing of Swiss Army Bench is imported: this module stands alone, so an
exported notebook or script (the one-script export) can carry a copy of it and check its approvals
wherever it runs.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from html.parser import HTMLParser
from typing import Any

MAX_TEXT: int = 20_000  # characters of printed text kept
MAX_ROWS: int = 50  # a table's first rows kept
MAX_COLUMNS: int = 30
MAX_CELL: int = 200  # characters of one value
MAX_TABLES: int = 10  # tables of one cell
MAX_CHANGES: int = 20  # changed cells said; the rest are counted
MAX_DIFF_LINES: int = 40
MAX_APPROVAL_CHARS: int = 2_000_000
KEY: str = "approved"  # under the cell's own metadata

_ADDRESS = re.compile(r"\bat 0x[0-9a-fA-F]+")
_PANDAS_SHAPE = re.compile("([\\d,]+) rows \u00d7 ([\\d,]+) columns")  # pandas: "3 rows, times, 2 columns"
_PLAIN_SHAPE = re.compile(r"\[([\d,]+) rows x ([\d,]+) columns\]")
_POLARS_SHAPE = re.compile(r"shape: \(([\d_,]+), ([\d_,]+)\)")
_PICTURES = ("image/png", "image/jpeg", "image/gif", "image/svg+xml", "application/vnd.plotly.v1+json")


def _text(value: Any) -> str:
    """nbformat keeps text as one string or a list of lines."""
    if isinstance(value, list):
        return "".join(str(v) for v in value)
    return value if isinstance(value, str) else ""


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _plain(text: str) -> str:
    """Text as compared: no memory addresses, no spaces at a line's end."""
    return "\n".join(line.rstrip() for line in _ADDRESS.sub("at 0x…", text).split("\n")).strip("\n")


def _mark(value: Any) -> str:
    said = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(said.encode("utf-8", "replace")).hexdigest()[:16]


# ===== a table, read from the HTML a DataFrame shows =====


class _Tables(HTMLParser):
    """Each <table>'s header row (its last, for a multi-level header) and body rows, as text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, Any]] = []
        self._depth = 0
        self._part = ""
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self.tables.append({"head": [], "rows": []})
        elif self._depth == 1 and tag in ("thead", "tbody"):
            self._part = tag
        elif self._depth == 1 and tag == "tr":
            self._row = []
        elif self._depth == 1 and tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            self._depth = max(0, self._depth - 1)
        elif self._depth != 1:
            return
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            table = self.tables[-1]
            if self._part == "thead":
                table["head"] = self._row
            elif len(table["rows"]) < MAX_ROWS + 1:
                table["rows"].append(self._row)
            else:
                table["more"] = True
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _number(text: str) -> int:
    return int(re.sub(r"[,_]", "", text))


def _shape(html: str, plain: str, rows: int, columns: int, index: bool) -> list[int]:
    for pattern, text in ((_PANDAS_SHAPE, html), (_POLARS_SHAPE, html), (_PLAIN_SHAPE, plain)):
        found = pattern.search(text)
        if found:
            return [_number(found.group(1)), _number(found.group(2))]
    return [rows, max(0, columns - (1 if index else 0))]


def _tables(html: str, plain: str) -> list[dict[str, Any]]:
    reader = _Tables()
    try:
        reader.feed(html)
        reader.close()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for found in reader.tables[:MAX_TABLES]:
        head = [_cut(h, MAX_CELL) for h in found["head"]]
        rows = [[_cut(v, MAX_CELL) for v in row[:MAX_COLUMNS]] for row in found["rows"][:MAX_ROWS]]
        if not head and rows:  # no header row: the first row names the columns
            head, rows = rows[0], rows[1:]
        index = bool(head) and head[0] == ""  # pandas' index: an empty corner
        shape = _shape(html, plain, len(found["rows"]), len(head), index)
        out.append({"columns": head[:MAX_COLUMNS], "rows": rows, "shape": shape})
    return out


# ===== a snapshot: what is compared =====


def snapshot(outputs: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """A cell's outputs (nbformat's records) as what an approval keeps and a later run is compared with."""
    texts: list[str] = []
    tables: list[dict[str, Any]] = []
    drawings: list[str] = []
    error: str | None = None
    for output in outputs:
        kind = output.get("output_type")
        if kind == "stream" and output.get("name", "stdout") == "stdout":
            texts.append(_text(output.get("text")))  # stderr is warnings: not the output
        elif kind == "error":
            error = _cut(f"{output.get('ename', 'Error')}: {output.get('evalue', '')}".strip(), MAX_CELL * 5)
        elif kind in ("execute_result", "display_data"):
            data = output.get("data")
            if not isinstance(data, Mapping):
                continue
            html = _text(data.get("text/html"))
            plain = _text(data.get("text/plain"))
            found = _tables(html, plain) if "<table" in html.lower() else []
            pictures = [mime for mime in _PICTURES if mime in data]
            if found:
                tables += found
            elif pictures:
                drawings.append(_mark([pictures[0], data[pictures[0]]]))
            elif "text/markdown" in data:
                texts.append(_text(data["text/markdown"]) + "\n")
            elif plain:
                texts.append(plain + "\n")
            elif html:
                drawings.append(_mark(["text/html", _plain(html)]))
    text = _cut(_plain("".join(texts)), MAX_TEXT)
    said = {"text": text, "tables": tables[:MAX_TABLES], "drawings": drawings[:MAX_TABLES], "error": error}
    return said | {"digest": _mark(said)}


def approval(found: Mapping[str, Any], at: str | None = None) -> dict[str, Any]:
    """An approval of a snapshot (`at`: when, as the caller tells it)."""
    return {"snapshot": dict(found), "at": at}


def check_approval(raw: Any) -> dict[str, Any] | None:
    """An approval as a file or a window holds it, checked (None: there is none)."""
    if raw is None:
        return None
    snap = raw.get("snapshot") if isinstance(raw, Mapping) else None
    if (
        not isinstance(snap, Mapping)
        or not isinstance(snap.get("tables"), list)
        or not isinstance(snap.get("drawings"), list)
        or not isinstance(snap.get("digest"), str)
        or not isinstance(snap.get("text", ""), str)
        or len(json.dumps(raw, default=str)) > MAX_APPROVAL_CHARS
    ):
        raise ValueError("That is not an approval of a cell's output (a snapshot, and when).")
    at = raw.get("at")
    return {"snapshot": dict(snap), "at": at if isinstance(at, str) else None}


def without_rows(held: Mapping[str, Any]) -> dict[str, Any]:
    """An approval with no rows and no printed text in it: its marks, each table's columns and shape."""
    snap = held["snapshot"]
    kept = {
        "text": "",
        "text_digest": snap.get("text_digest") or _mark(snap.get("text", "")),
        "tables": [{"columns": t.get("columns", []), "shape": t.get("shape")} for t in snap["tables"]],
        "drawings": list(snap["drawings"]),
        "error": snap.get("error"),
        "digest": snap["digest"],
        "stripped": True,
    }
    return {"snapshot": kept, "at": held.get("at")}


# ===== the comparison =====


def _text_diff(was: str, now: str) -> list[str]:
    lines = [
        line
        for line in difflib.unified_diff(was.split("\n"), now.split("\n"), lineterm="", n=1)
        if not line.startswith(("---", "+++", "@@"))
    ]
    return lines[:MAX_DIFF_LINES] + (
        [f"… and {len(lines) - MAX_DIFF_LINES} more lines"] if len(lines) > MAX_DIFF_LINES else []
    )


def _table_diff(was: Mapping[str, Any], now: Mapping[str, Any]) -> dict[str, Any] | None:
    columns_was = [c for c in was.get("columns", []) if c]
    columns_now = [c for c in now.get("columns", []) if c]
    changed: dict[str, Any] = {
        "shape": None if was.get("shape") == now.get("shape") else [was.get("shape"), now.get("shape")],
        "added": [c for c in columns_now if c not in columns_was],
        "removed": [c for c in columns_was if c not in columns_now],
        "cells": [],
        "more": 0,
    }
    if "rows" in was:
        heads_was, heads_now = list(was.get("columns", [])), list(now.get("columns", []))
        shared = [c for c in heads_was if c in heads_now and c]
        cells: list[dict[str, Any]] = []
        for at, (row_was, row_now) in enumerate(zip(was["rows"], now.get("rows", []), strict=False)):
            for column in shared:
                i, j = heads_was.index(column), heads_now.index(column)
                old = row_was[i] if i < len(row_was) else None
                new = row_now[j] if j < len(row_now) else None
                if old != new:
                    cells.append({"row": at, "column": column, "was": old, "now": new})
        changed["cells"] = cells[:MAX_CHANGES]
        changed["more"] = max(0, len(cells) - MAX_CHANGES)
    if changed["shape"] is None and not (changed["added"] or changed["removed"] or changed["cells"]):
        return None
    return changed


def compare(held: Mapping[str, Any], now: Mapping[str, Any]) -> dict[str, Any] | None:
    """An approval against a later snapshot: None when the output is the same, else how it differs."""
    was = held["snapshot"]
    if was.get("digest") == now.get("digest"):
        return None
    stripped = was.get("stripped") is True
    diff: dict[str, Any] = {"text": [], "tables": [], "drawings": 0, "error": None, "changed": False}
    if stripped:
        if was.get("text_digest") != _mark(now.get("text", "")):
            diff["text"] = ["(the printed text changed)"]
    elif was.get("text", "") != now.get("text", ""):
        diff["text"] = _text_diff(was.get("text", ""), now.get("text", ""))
    tables_was, tables_now = list(was["tables"]), list(now.get("tables", []))
    for index in range(max(len(tables_was), len(tables_now))):
        if index >= len(tables_was) or index >= len(tables_now):
            shape = (
                [tables_was[index]["shape"], None]
                if index < len(tables_was)
                else [None, tables_now[index]["shape"]]
            )
            diff["tables"].append(
                {"index": index, "shape": shape, "added": [], "removed": [], "cells": [], "more": 0}
            )
            continue
        found = _table_diff(tables_was[index], tables_now[index])
        if found is not None:
            diff["tables"].append({"index": index} | found)
    diff["drawings"] = sum(
        1 for a, b in zip(was["drawings"], now.get("drawings", []), strict=False) if a != b
    )
    diff["drawings"] += abs(len(was["drawings"]) - len(now.get("drawings", [])))
    if was.get("error") != now.get("error"):
        diff["error"] = {"was": was.get("error"), "now": now.get("error")}
    # Something differs that none of the above says (a stripped approval's rows, say).
    diff["changed"] = not (diff["text"] or diff["tables"] or diff["drawings"] or diff["error"])
    return diff


def _shape_lines(prefix: str, shape: Sequence[Any]) -> list[str]:
    was, now = shape
    if was is None:
        return [f"{prefix}a new table: {now[0]:,} rows, {now[1]:,} columns"]
    if now is None:
        return [f"{prefix}a table is gone ({was[0]:,} rows, {was[1]:,} columns)"]
    out: list[str] = []
    if was[0] != now[0]:
        out.append(f"{prefix}rows: {was[0]:,} → {now[0]:,}")
    if was[1] != now[1]:
        out.append(f"{prefix}columns: {was[1]:,} → {now[1]:,}")
    return out


def summary(diff: Mapping[str, Any]) -> list[str]:
    """How an output differs from its approval, as plain lines."""
    lines: list[str] = []
    many = len(diff.get("tables", [])) > 1
    for table in diff.get("tables", []):
        prefix = f"table {table['index'] + 1}, " if many else ""
        if table.get("shape"):
            lines += _shape_lines(prefix, table["shape"])
        if table.get("added"):
            lines.append(f"{prefix}columns added: {', '.join(table['added'])}")
        if table.get("removed"):
            lines.append(f"{prefix}columns removed: {', '.join(table['removed'])}")
        lines += [
            f"{prefix}row {c['row']}, {c['column']}: {c['was']} → {c['now']}" for c in table.get("cells", [])
        ]
        if table.get("more"):
            lines.append(f"{prefix}and {table['more']:,} more changed values")
    lines += list(diff.get("text", []))
    if diff.get("drawings"):
        count = diff["drawings"]
        lines.append("a picture or chart changed" if count == 1 else f"{count} pictures or charts changed")
    error = diff.get("error")
    if error:
        lines.append(f"error: {error['now']}" if error["now"] else f"no error now (was {error['was']})")
    if diff.get("changed"):
        lines.append("the output changed")
    return lines
