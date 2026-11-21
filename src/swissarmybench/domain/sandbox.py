"""A project's sandbox (the owner, 2026-11-21: "We need to actually make apis just read and write our local
data
through the API. Not use the connectors that way we could transform scaffold create an app then test it out
and
then reset the data changes and try again. It makes for the ultimate sandbox").

The sandbox is the project's own DuckDB file, `.sab/sandbox/sandbox.duckdb`, kept out of Git like
`.sab/data/`.
Tables get in on the user's action only (an open grid's view, a connection's table read once, a file, an empty
table defined by its columns). Its **baseline** is a copy of the file (`baseline.duckdb`): Reset puts every
table
back to it in one step; named **checkpoints** are copies too (`checkpoints/<name>.duckdb`). `sandbox.json`
holds
where each table came from, the baseline's time, the checkpoints and the change log (rows inserted, updated
and
deleted per table since the baseline). A local sandbox API reads and writes only here; a connection is never
written.

Pure rules: names, the meta file's text, the change log, the column types of an empty table, and the SQL a
write
is made of (identifiers checked against the table's own columns, values always bound). Standard library only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

NAME = "Sandbox"  # its name in DuckDB SQL: [Sandbox].orders
FOLDER = ".sab/sandbox"
DB_FILE = "sandbox.duckdb"
BASELINE_FILE = "baseline.duckdb"
CHECKPOINTS = "checkpoints"
META_FILE = "sandbox.json"
GRID_PREFIX = "sandbox_"  # an open grid of a sandbox table: sandbox_orders
FORMAT = 1
PLAIN = "duckdb"  # a table from a file or made empty: mocked as a plain DuckDB client
MAX_ROWS_ANSWERED = 10_000  # a query's rows sent back at most (the API's own paging says the rest)
MAX_WRITE_ROWS = 5_000  # rows one insert takes

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_CHECKPOINT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,47}$")

# An empty table's column types: the words the form shows, and DuckDB's type.
COLUMN_TYPES: dict[str, str] = {
    "text": "VARCHAR",
    "integer": "BIGINT",
    "number": "DOUBLE",
    "decimal": "DECIMAL(18,2)",
    "yes/no": "BOOLEAN",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
}


class SandboxError(ValueError):
    """A request the sandbox cannot do as asked, in one sentence."""


def check_table_name(name: Any) -> str:
    text = str(name or "").strip()
    if not _IDENT.match(text):
        raise SandboxError(
            f"{text or 'That'} is not a sandbox table name: letters, digits and _, starting with a letter."
        )
    return text


def check_checkpoint_name(name: Any) -> str:
    text = str(name or "").strip()
    if not _CHECKPOINT.match(text):
        raise SandboxError("A checkpoint's name is up to 48 letters, digits, spaces, _ . or -.")
    return text


def checkpoint_file(name: str) -> str:
    """A checkpoint's file name: its name made safe for any file system."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".duckdb"


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def grid_name(table: str) -> str:
    return GRID_PREFIX + table


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # DuckDB's
    key: bool = False


def columns_spec(raw: Any) -> list[Column]:
    """An empty table's columns: [{name, type (a word of COLUMN_TYPES or DuckDB's), key?}]."""
    if not isinstance(raw, list) or not raw:
        raise SandboxError("Give the table at least one column: [{name, type}].")
    out: list[Column] = []
    seen: set[str] = set()
    allowed = {v.upper() for v in COLUMN_TYPES.values()}
    for item in raw[:200]:
        if not isinstance(item, Mapping):
            raise SandboxError("Each column is {name, type}.")
        name = check_table_name(item.get("name"))
        if name.casefold() in seen:
            raise SandboxError(f"{name} is named twice.")
        seen.add(name.casefold())
        word = str(item.get("type") or "text").strip()
        typed = COLUMN_TYPES.get(word.lower()) or (word.upper() if word.upper() in allowed else None)
        if typed is None:
            raise SandboxError(f"{name}'s type is one of: {', '.join(COLUMN_TYPES)}.")
        out.append(Column(name, typed, bool(item.get("key"))))
    return out


def create_sql(table: str, columns: Sequence[Column]) -> str:
    keys = [c.name for c in columns if c.key]
    parts = [f"{quote(c.name)} {c.type}" for c in columns]
    if keys:
        parts.append("PRIMARY KEY (" + ", ".join(quote(k) for k in keys) + ")")
    return f"CREATE TABLE {quote(table)} (" + ", ".join(parts) + ")"


# ===== the meta file =====


@dataclass
class Counts:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0

    def to_json(self) -> dict[str, int]:
        return {"inserted": self.inserted, "updated": self.updated, "deleted": self.deleted}

    @property
    def any(self) -> bool:
        return bool(self.inserted or self.updated or self.deleted)


@dataclass
class Checkpoint:
    name: str
    at: str
    log: dict[str, Counts] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "at": self.at, "log": log_json(self.log)}


@dataclass
class Meta:
    tables: dict[str, dict[str, Any]] = field(default_factory=dict)  # name -> {source, added_at, key}
    baseline_at: str | None = None
    checkpoints: list[Checkpoint] = field(default_factory=list)
    log: dict[str, Counts] = field(default_factory=dict)

    def checkpoint(self, name: str) -> Checkpoint | None:
        return next((c for c in self.checkpoints if c.name.casefold() == name.casefold()), None)


def log_json(log: Mapping[str, Counts]) -> dict[str, dict[str, int]]:
    return {t: c.to_json() for t, c in sorted(log.items()) if c.any}


def _counts(raw: Any) -> Counts:
    given = raw if isinstance(raw, Mapping) else {}
    return Counts(*(max(0, int(given.get(k) or 0)) for k in ("inserted", "updated", "deleted")))


def meta_text(meta: Meta) -> str:
    """sandbox.json: sorted, the same bytes for the same state."""
    body = {
        "format": FORMAT,
        "tables": {k: meta.tables[k] for k in sorted(meta.tables)},
        "baseline_at": meta.baseline_at,
        "checkpoints": [c.to_json() for c in meta.checkpoints],
        "log": log_json(meta.log),
    }
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def read_meta(text: str | None) -> Meta:
    if not text:
        return Meta()
    try:
        raw = json.loads(text)
    except ValueError:
        return Meta()
    if not isinstance(raw, dict):
        return Meta()
    tables = raw.get("tables") if isinstance(raw.get("tables"), dict) else {}
    points = [
        Checkpoint(
            str(c.get("name")),
            str(c.get("at") or ""),
            {str(t): _counts(v) for t, v in dict(c.get("log") or {}).items()},
        )
        for c in raw.get("checkpoints") or []
        if isinstance(c, dict) and c.get("name")
    ]
    return Meta(
        {str(k): dict(v) for k, v in dict(tables or {}).items() if isinstance(v, dict)},
        raw.get("baseline_at") if isinstance(raw.get("baseline_at"), str) else None,
        points,
        {str(t): _counts(v) for t, v in dict(raw.get("log") or {}).items()},
    )


def noted(log: dict[str, Counts], table: str, op: str, rows: int) -> None:
    """A write counted in the change log: op is insert, update or delete."""
    counts = log.setdefault(table, Counts())
    if op == "insert":
        counts.inserted += rows
    elif op == "update":
        counts.updated += rows
    elif op == "delete":
        counts.deleted += rows


def copied_log(log: Mapping[str, Counts]) -> dict[str, Counts]:
    return {t: Counts(c.inserted, c.updated, c.deleted) for t, c in log.items()}


def log_words(log: Mapping[str, Counts]) -> str:
    """The change log in one line: "orders: 2 inserted, 1 updated · No changes since the baseline"."""
    parts = []
    for table, c in sorted(log.items()):
        said = [
            f"{n} {w}"
            for n, w in ((c.inserted, "inserted"), (c.updated, "updated"), (c.deleted, "deleted"))
            if n
        ]
        if said:
            parts.append(f"{table}: " + ", ".join(said))
    return " · ".join(parts) or "No changes since the baseline"


# ===== reads and writes =====


def check_read(sql: Any, parse: Callable[[str], dict[str, Any]]) -> str:
    """A query an API sends: one SELECT (or WITH ... SELECT), by DuckDB's own parse. A write goes through
    insert, update or delete, which name their table and columns."""
    text = str(sql or "").strip().rstrip(";").strip()
    if not text:
        raise SandboxError("The query is empty.")
    parsed = parse(text)
    if parsed.get("error") or len(parsed.get("statements") or []) != 1:
        raise SandboxError(
            "data.query reads with one SELECT; write with data.insert, data.update or data.delete."
        )
    return text


def _known(table: str, columns: Iterable[str], named: Iterable[str]) -> dict[str, str]:
    """The names a write gives, each matched to the table's own column (any case)."""
    by_case = {c.casefold(): c for c in columns}
    out: dict[str, str] = {}
    for name in named:
        real = by_case.get(str(name).casefold())
        if real is None:
            raise SandboxError(f"{table} has no column named {name}.")
        out[str(name)] = real
    return out


@dataclass(frozen=True)
class Statement:
    sql: str
    params: list[Any]


def insert_statements(table: str, columns: Sequence[str], rows: Any) -> list[Statement]:
    """INSERT one statement per row (each row a dict of column -> value), values bound."""
    batch = [rows] if isinstance(rows, Mapping) else rows
    if not isinstance(batch, list) or not batch or not all(isinstance(r, Mapping) for r in batch):
        raise SandboxError("insert takes a row (a dict of column to value) or a list of them.")
    if len(batch) > MAX_WRITE_ROWS:
        raise SandboxError(f"One insert takes up to {MAX_WRITE_ROWS:,} rows.")
    out = []
    for row in batch:
        if not row:
            raise SandboxError("A row to insert names at least one column.")
        known = _known(table, columns, row)
        names = ", ".join(quote(known[k]) for k in row)
        marks = ", ".join("?" for _ in row)
        sql = f"INSERT INTO {quote(table)} ({names}) VALUES ({marks})"  # noqa: S608 (checked names, bound values)
        out.append(Statement(sql, [row[k] for k in row]))
    return out


def _where(table: str, columns: Sequence[str], where: Any) -> tuple[str, list[Any]]:
    if not isinstance(where, Mapping) or not where:
        raise SandboxError("Say which rows: where is a dict of column to value (every row: all=True).")
    known = _known(table, columns, where)
    parts, params = [], []
    for k, v in where.items():
        if v is None:
            parts.append(f"{quote(known[k])} IS NULL")
        else:
            parts.append(f"{quote(known[k])} = ?")
            params.append(v)
    return " AND ".join(parts), params


def update_statement(
    table: str, columns: Sequence[str], values: Any, where: Any, every: bool = False
) -> Statement:
    if not isinstance(values, Mapping) or not values:
        raise SandboxError("update takes the values to set: a dict of column to value.")
    known = _known(table, columns, values)
    sets = ", ".join(f"{quote(known[k])} = ?" for k in values)
    params = [values[k] for k in values]
    if every and not where:
        return Statement(f"UPDATE {quote(table)} SET {sets}", params)  # noqa: S608
    clause, more = _where(table, columns, where)
    return Statement(f"UPDATE {quote(table)} SET {sets} WHERE {clause}", params + more)  # noqa: S608


def delete_statement(table: str, columns: Sequence[str], where: Any, every: bool = False) -> Statement:
    if every and not where:
        return Statement(f"DELETE FROM {quote(table)}", [])  # noqa: S608
    clause, params = _where(table, columns, where)
    return Statement(f"DELETE FROM {quote(table)} WHERE {clause}", params)  # noqa: S608


def table_read(
    table: str, columns: Sequence[str], where: Any = None, limit: Any = None, offset: Any = None
) -> Statement:
    """data.table(name, where=, limit=, offset=): its rows in its own order, values bound."""
    sql = f"SELECT * FROM {quote(table)}"  # noqa: S608 (a checked name)
    params: list[Any] = []
    if where:
        clause, params = _where(table, columns, where)
        sql += f" WHERE {clause}"
    most = _bounded(limit, MAX_ROWS_ANSWERED, MAX_ROWS_ANSWERED)
    sql += f" LIMIT {most} OFFSET {_bounded(offset, 0, 10**12)}"
    return Statement(sql, params)


def _bounded(value: Any, default: int, most: int) -> int:
    try:
        number = int(value) if value is not None else default
    except (TypeError, ValueError) as error:
        raise SandboxError("limit and offset are whole numbers.") from error
    return max(0, min(number, most))


def source_words(source: Mapping[str, Any]) -> str:
    """Where a table came from, in words (the sandbox's list)."""
    kind = source.get("kind")
    if kind == "grid":
        return f"From the open table {source.get('table', '')}"
    if kind == "connection":
        return f"Read once from {source.get('connection', '')}"
    if kind == "file":
        return f"From {source.get('file', '')}"
    if kind == "columns":
        return "Made empty, by its columns"
    return "Added"
