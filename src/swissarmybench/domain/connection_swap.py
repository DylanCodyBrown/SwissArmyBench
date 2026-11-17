"""A table's connection swapped for another (the owner, 2026-11-16: "I deleted the edp but need its
queries to run on the other ... so I need a option to swap that sql to run on trino (non odbc)").

  [MATCH]     a catalog table read from one connection found in another's catalog: the table's name is
              the same in any case; the schema, then the database, breaks a tie (an ODBC connection's
              "database" may be Trino's catalog, so a database matching the other's schema counts too).
              None found, or a tie: the user picks from the other connection's catalog
  [QUERY]     a table read by a query goes over as its query, looked over first (ODBC and native Trino may
              name tables differently); the query must be one read (SELECT, WITH, VALUES, a DAX EVALUATE)
  [CODE]      the documents that name the old connection pointed at the new one: the name only, inside the
              client's call (ast: a string that merely holds the name is left alone) or a SQL or DAX cell's
              first line; the rest of the name (`Finance/Sales model`, `Warehouse -> orders`) is kept

Standard library only; no I/O.
"""

from __future__ import annotations

import ast
import json
import re
import shlex
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain import connection_usage as usage
from swissarmybench.domain import notebooks

MAX_CANDIDATES = 200
_READ_FIRST = ("select", "with", "values", "table", "evaluate", "define", "show", "describe", "explain")
_SQL_LINE = re.compile(r"^(\s*%%(sql|dax))(\s.*)?$")
_SCRIPT_MARKER = re.compile(r"^# ?%%(?:\s*\[(\d+)\])?")
_REGION_START = re.compile(r"^#\s*region\s+Tables\b", re.IGNORECASE)
_REGION_END = re.compile(r"^#\s*endregion\b", re.IGNORECASE)


class SwapError(ValueError):
    """A swap that cannot be done as asked, in words."""


@dataclass(frozen=True)
class Place:
    """A table in a connection's catalog."""

    database: str
    schema: str
    table: str

    def to_json(self) -> dict[str, str]:
        return {"database": self.database, "schema": self.schema, "table": self.table}

    def words(self) -> str:
        return ".".join(p for p in (self.database, self.schema, self.table) if p)


def place_of(raw: Any) -> Place | None:
    """A place as the page or the agent sends it ({"database"?, "schema"?, "table"}); None without a table."""
    if not isinstance(raw, dict):
        return None
    parts = [raw.get(k) or "" for k in ("database", "schema", "table")]
    if not all(isinstance(p, str) and len(p) <= 400 for p in parts):
        raise SwapError("A table's place is its database, schema and table, each a name.")
    return Place(*parts) if parts[2] else None


def _same(a: str, b: str) -> bool:
    return bool(a) and a.casefold() == b.casefold()


def match_place(old: Place, candidates: Iterable[Place]) -> tuple[Place | None, list[Place]]:
    """The other connection's table that `old` is (None: none, or a tie), and the ones of that name."""
    named = [c for c in candidates if c.table.casefold() == old.table.casefold()][:MAX_CANDIDATES]
    if not named:
        return None, []

    def score(c: Place) -> int:
        return (
            8 * _same(c.schema, old.schema)
            + 4 * _same(c.database, old.database)
            + 2 * (_same(c.schema, old.database) or _same(c.database, old.schema))
            + (c.table == old.table)
        )

    best = max(score(c) for c in named)
    top = [c for c in named if score(c) == best]
    return (top[0] if len(top) == 1 else None), named


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return "\n".join(re.sub(r"--.*$|//.*$", "", line) for line in sql.split("\n"))


def check_read_query(sql: Any) -> str:
    """A query to run on a connection: one read (its words kept as typed)."""
    if not isinstance(sql, str) or not sql.strip():
        raise SwapError("Write the query to run.")
    if len(sql) > 200_000:
        raise SwapError("A query is at most 200,000 characters.")
    plain = _strip_comments(sql).strip().rstrip(";").strip()
    first = re.match(r"[(\s]*([A-Za-z]+)", plain)
    if first is None or first.group(1).casefold() not in _READ_FIRST:
        raise SwapError("The query must read: SELECT, WITH, VALUES or a DAX EVALUATE.")
    # Quoted text aside, a second statement after a semicolon is refused.
    unquoted = re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", plain)
    if ";" in unquoted:
        raise SwapError("Send one query: no second statement after a semicolon.")
    return sql


# ===== code: the name only =====


def renamed(named: str, old: str, new: str) -> str:
    """A cell's or a call's words with the connection's part changed: `EDP -> orders` -> `Trino ->
    orders`, `Finance/Sales model` -> `Finance 2/Sales model`; any other words as they were."""
    head, arrow, tail = named.partition(" -> ")
    base, slash, rest = head.partition("/")
    if not usage.same_name(base.strip(), old):
        return named
    lead = base[: len(base) - len(base.lstrip())]
    trail = base[len(base.rstrip()) :]
    return f"{lead}{new}{trail}{slash}{rest}{arrow}{tail}"


def _literal(segment: str, value: str) -> str | None:
    """A plain string literal's text with a new value, written as it was (its prefix and quotes)."""
    found = re.fullmatch(r"([rRuUbB]{0,2})('''|\"\"\"|'|\")(.*)\2", segment, flags=re.DOTALL)
    if found is None or "f" in found.group(1).lower() or "b" in found.group(1).lower():
        return None
    prefix, quote = found.group(1), found.group(2)
    raw = "r" in prefix.lower()
    if raw and (quote[0] in value or value.endswith("\\")):
        return None
    text = value if raw else value.replace("\\", "\\\\").replace(quote[0], "\\" + quote[0])
    return f"{prefix}{quote}{text}{quote}"


def _offsets(lines: Sequence[str]) -> list[int]:
    starts, at = [], 0
    for line in lines:
        starts.append(at)
        at += len(line) + 1
    return starts


def _column(line: str, byte_offset: int) -> int:
    """ast's columns count UTF-8 bytes: the character there."""
    return len(line.encode("utf-8")[:byte_offset].decode("utf-8", errors="ignore"))


def repoint_python(code: str, old: str, new: str, lines_kept: set[int] | None = None) -> tuple[str, int]:
    """Python with each client call that names `old` (sab.sql("EDP", ...), sab.read, sab.dax, sab.blade,
    sab.connection, imported or aliased) naming `new`: the string only. `lines_kept`: only calls on
    these lines (from 1). The code, and how many calls changed."""
    tree = usage._python_tree(code)
    if tree is None:
        return code, 0
    modules, functions = usage._aliases(tree)
    lines = code.split("\n")
    starts = _offsets(lines)
    edits: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        word: str | None = None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in modules:
            word = func.attr if func.attr in usage._NAMED_FIRST else None
        elif isinstance(func, ast.Name):
            word = functions.get(func.id)
        if word is None:
            continue
        first = (
            node.args[0]
            if node.args
            else next((k.value for k in node.keywords if k.arg in usage._KEYWORDS), None)
        )
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        if lines_kept is not None and node.lineno not in lines_kept:
            continue
        value = renamed(first.value, old, new)
        if value == first.value or first.end_lineno is None or first.end_col_offset is None:
            continue
        begin_line, end_line = first.lineno - 1, first.end_lineno - 1
        begin = starts[begin_line] + _column(lines[begin_line], first.col_offset)
        end = starts[end_line] + _column(lines[end_line], first.end_col_offset)
        written = _literal(code[begin:end], value)
        if written is not None:
            edits.append((begin, end, written))
    for begin, end, written in sorted(edits, reverse=True):
        code = code[:begin] + written + code[end:]
    return code, len(edits)


def repoint_line(first: str, old: str, new: str) -> str:
    """A SQL or DAX cell's first line naming `new` (`%%sql EDP` -> `%%sql Trino`)."""
    found = _SQL_LINE.match(first)
    if found is None or not (found.group(3) or "").strip():
        return first
    kind = found.group(2)
    try:
        named = " ".join(shlex.split(found.group(3)))
    except ValueError:
        named = found.group(3).strip()
    changed = renamed(named, old, new)
    if changed == named:
        return first
    line = notebooks.sql_line(changed) if kind == "sql" else notebooks.dax_line(changed)
    return found.group(1)[: len(found.group(1)) - len(found.group(1).lstrip())] + line


def _is_cell(raw: Any) -> bool:
    return isinstance(raw, dict) and raw.get("cell_type") in ("markdown", "code", "raw")


def repoint_notebook(text: str, old: str, new: str, cells: set[int] | None = None) -> tuple[str, list[int]]:
    """A notebook's file with its cells (all, or the numbered ones) naming `new`; the cells changed. A
    table's read-only cell follows its table on its own, so it is left as it is."""
    found, _ = notebooks.read_document(text)
    data = json.loads(text)
    raws = [r for r in data["cells"][: notebooks.MAX_CELLS] if _is_cell(r)]
    changed: list[int] = []
    for cell, raw in zip(found, raws, strict=False):
        if cell.number is None or (cells is not None and cell.number not in cells):
            continue
        if cell.role not in ("", "maker"):
            continue
        source = notebooks._text(raw.get("source"))
        if cell.kind in ("sql", "dax"):
            first, newline, rest = source.partition("\n")
            line = repoint_line(first, old, new)
            after = line + newline + rest if line != first else source
        elif cell.kind == "code":
            after = repoint_python(source, old, new)[0]
        else:
            continue
        if after != source:
            raw["source"] = notebooks._lines(after)
            changed.append(cell.number)
    if not changed:
        return text, []
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n", changed


def script_cells(text: str) -> list[int | None]:
    """Each line's cell in a script (from 0): its `# %% [7]` number, None for the main code, -1 inside
    the Tables group (the app's own lines)."""
    owner: list[int | None] = []
    current: int | None = None
    grouped = False
    for line in text.split("\n"):
        if _REGION_START.match(line):
            grouped = True
        if grouped:
            owner.append(-1)
            if _REGION_END.match(line):
                grouped = False
            continue
        marker = _SCRIPT_MARKER.match(line)
        if marker is not None:
            current = int(marker.group(1)) if marker.group(1) else None
        owner.append(current)
    return owner


def repoint_script(
    text: str, old: str, new: str, cells: set[int | None] | None = None
) -> tuple[str, list[int | None]]:
    """A script with its calls (in every cell, or in the numbered ones; None: its main code) naming `new`;
    the cells changed. The Tables group's lines are the app's and follow their tables."""
    owner = script_cells(text)
    kept = {i + 1 for i, cell in enumerate(owner) if cell != -1 and (cells is None or cell in cells)}
    before = text.split("\n")
    after, count = repoint_python(text, old, new, kept)
    if not count:
        return text, []
    changed: list[int | None] = []
    for i, (a, b) in enumerate(zip(before, after.split("\n"), strict=False)):
        if a != b and owner[i] not in changed:
            changed.append(owner[i])
    return after, changed


def repoint_document(
    path: str, text: str, old: str, new: str, cells: set[int | None] | None = None
) -> tuple[str, list[int | None]]:
    """A notebook or a script by its kind (any other file is left as it is)."""
    kind = notebooks.kind_of(path)
    if kind == "notebook":
        numbered = None if cells is None else {c for c in cells if c is not None}
        written, done = repoint_notebook(text, old, new, numbered)
        return written, list(done)
    if kind == "script":
        return repoint_script(text, old, new, cells)
    return text, []
