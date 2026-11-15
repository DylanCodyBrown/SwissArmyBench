"""A project's data dictionary (the Workbench's Data mode, 2026-11-15): data.ipynb's tables, each column
with its type in plain words, a description the user writes, and where it comes from (the table's file
or connection, or the grid's step that made it).

The descriptions live in data.ipynb itself (the notebook's metadata, `swissarmybench.dictionary`: they
travel with the file and its zip) and go into data.py as comments above the code, so whoever reads the
module reads what each table and column means. Pure rules, no I/O.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

MAX_DESCRIPTION: int = 500
MAX_TABLES: int = 200
MAX_COLUMNS: int = 2_000

# DuckDB's types in plain words (by the type's first word).
_PLAIN: tuple[tuple[str, str], ...] = (
    (r"(\[\d*\]$|^LIST\b)", "List"),  # first: INTEGER[] is a list, not a number
    (r"^(STRUCT|MAP|UNION)\b", "Record"),
    (
        r"^(TINYINT|SMALLINT|INTEGER|INT|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT|UHUGEINT)\b",
        "Whole number",
    ),
    (r"^(DECIMAL|NUMERIC|DOUBLE|FLOAT|REAL)\b", "Decimal"),
    (r"^(VARCHAR|TEXT|STRING|CHAR|BPCHAR|UUID|ENUM)\b", "Text"),
    (r"^DATE\b", "Date"),
    (r"^(TIMESTAMP|DATETIME)", "Date and time"),
    (r"^TIME\b", "Time"),
    (r"^INTERVAL\b", "Length of time"),
    (r"^BOOLEAN\b", "True or false"),
    (r"^(BLOB|BYTEA)\b", "Bytes"),
)


class DictionaryError(ValueError):
    """Descriptions that cannot be kept as sent (the message says why)."""


def plain_type(sql_type: str) -> str:
    """A column's type in plain words: BIGINT -> Whole number, VARCHAR -> Text."""
    upper = sql_type.strip().upper()
    for pattern, words in _PLAIN:
        if re.search(pattern, upper):
            return words
    return sql_type.strip().title() or "Unknown"


def _line(value: Any, what: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_DESCRIPTION or "\x00" in value:
        raise DictionaryError(f"{what}'s description is text (at most {MAX_DESCRIPTION} characters).")
    return " ".join(value.split())  # one line: a description becomes a comment in data.py


def check(sent: Any) -> dict[str, dict[str, Any]]:
    """Descriptions as sent: {"orders": {"description": "...", "columns": {"status": "..."}}}. Empty ones
    are left out."""
    if sent is None:
        return {}
    if not isinstance(sent, dict) or len(sent) > MAX_TABLES:
        raise DictionaryError(
            'The dictionary is {"orders": {"description": "...", "columns": {"status": "..."}}}.'
        )
    out: dict[str, dict[str, Any]] = {}
    for table, entry in sent.items():
        if not isinstance(table, str) or not table.strip() or not isinstance(entry, dict):
            raise DictionaryError('Each table is {"description": "...", "columns": {"column": "..."}}.')
        description = _line(entry.get("description") or "", table)
        columns: dict[str, str] = {}
        raw = entry.get("columns") or {}
        if not isinstance(raw, dict) or len(raw) > MAX_COLUMNS:
            raise DictionaryError(f'{table}\'s columns are {{"column": "description"}}.')
        for column, text in raw.items():
            said = _line(text or "", f"{table}.{column}")
            if isinstance(column, str) and said:
                columns[column] = said
        if description or columns:
            out[table] = {"description": description, "columns": columns}
    return out


def of_notebook(text: str | None) -> dict[str, dict[str, Any]]:
    """The descriptions a notebook's file keeps (its metadata's `swissarmybench.dictionary`)."""
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    own = (data.get("metadata") or {}).get("swissarmybench") if isinstance(data, dict) else None
    return read(own.get("dictionary")) if isinstance(own, dict) else {}


def read(raw: Any) -> dict[str, dict[str, Any]]:
    """Descriptions as a notebook keeps them (anything unreadable left out)."""
    try:
        return check(raw)
    except DictionaryError:
        return {}


def entry(
    table: str,
    columns: Sequence[tuple[str, str]],
    stages: Sequence[Iterable[str]],
    source: str,
    rows: int,
    steps: int,
    descriptions: Mapping[str, Any],
) -> dict[str, Any]:
    """A table's page in the dictionary: its rows, source and steps, its description, and each column
    (name, plain type, description, where it comes from: the source, or "Step 2" when that step made
    it). `stages`: the columns before the steps, then after each step."""
    said = descriptions.get(table) or {}
    own = said.get("columns") or {}
    listed = [set(stage) for stage in stages]

    def comes_from(column: str) -> str:
        if not listed or column in listed[0]:
            return source
        for index, stage in enumerate(listed[1:], start=1):
            if column in stage:
                return f"Step {index}"
        return source

    return {
        "table": table,
        "rows": rows,
        "source": source,
        "steps": steps,
        "description": said.get("description", ""),
        "columns": [
            {
                "name": name,
                "type": plain_type(sql_type),
                "description": own.get(name, ""),
                "comes_from": comes_from(name),
            }
            for name, sql_type in columns
        ],
    }


def comments(descriptions: Mapping[str, Any], tables: Sequence[str] = ()) -> list[str]:
    """data.py's data dictionary: a comment block, each table (in `tables`' order first) with its
    description and each described column. Nothing when nothing is described."""
    order = [t for t in tables if t in descriptions] + [t for t in descriptions if t not in tables]
    lines: list[str] = []
    for table in order:
        said = descriptions[table]
        description = said.get("description") or ""
        lines.append(f"#   {table}: {description}" if description else f"#   {table}")
        for column, text in (said.get("columns") or {}).items():
            lines.append(f"#     {column}: {text}")
    return ["# Data dictionary (written in data.ipynb's Dictionary):", *lines] if lines else []
