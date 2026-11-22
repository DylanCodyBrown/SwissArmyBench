"""A project's sandbox (the owner, 2026-11-21: "We need to actually make apis just read and write our local
data
through the API. Not use the connectors that way we could transform scaffold create an app then test it out
and
then reset the data changes and try again. It makes for the ultimate sandbox").

The sandbox is the project's own DuckDB file, `sandbox/sandbox.duckdb` at the project's top (the owner,
2026-11-22: "separate sandbox files ... dont mix them into the app scaffold"; moved once out of an older
project's `.sab/sandbox/`), kept out of Git like `.sab/data/`.
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
FOLDER = "sandbox"  # the rows, at the project's top (Git-ignored)
OLD_FOLDER = ".sab/sandbox"  # where an older project kept them: moved once on open (adapters/sandbox.py)
IGNORE_LINE = "sandbox/"  # the project's .gitignore line for the rows
# The sandbox mirror's two files beside the app's (Plans/adapter.plan.md "The sandbox lives in its own
# files"):
# made by services/scaffold.py; Remove the sandbox deletes them and FOLDER, and nothing else.
DATA_FILE = "sandbox_data.py"
CONNECTIONS_FILE = "sandbox_connections.py"
MOVED = (
    "The sandbox moved to the project's sandbox/ folder (it was in .sab/sandbox/), beside its two files "
    "sandbox_data.py and sandbox_connections.py; .gitignore keeps its rows out of Git."
)
DB_FILE = "sandbox.duckdb"
BASELINE_FILE = "baseline.duckdb"
CHECKPOINTS = "checkpoints"
META_FILE = "sandbox.json"
GRID_PREFIX = "sandbox_"  # an open grid of a sandbox table: sandbox_orders
FORMAT = 1
PLAIN = "duckdb"  # a table from a file or made empty: mocked as a plain DuckDB client
MAX_ROWS_ANSWERED = 10_000  # a table_read's rows at most
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
    if kind == "structure":
        return f"From the structure {source.get('structure', '')}"
    if kind == "made":
        return f"Made by the API ({'a view' if source.get('what') == 'view' else 'a table from a query'})"
    return "Added"


# ===== the Sandbox as a connection (the owner, 2026-11-21: "The moment a sandbox table is created it gets a
# connection type of sandbox") =====

CONNECTION_TYPE = "sandbox"  # every sandbox table's connection type; the Sandbox's tables kind
CARD_WORDS = "Local test data, never live: the project's own copy, written only by the sandbox"
# Its colour on every page: none of the palette's (domain/connection_colours.py), none of the rail's.
COLOUR = "#3a3aa0"  # indigo


def is_sandbox(name: Any) -> bool:
    """`name` is the Sandbox's (any case): never a real connection, never exported as one."""
    return str(name or "").strip().casefold() == NAME.casefold()


NAME_TAKEN = (
    "Sandbox is the project's sandbox's name in DuckDB SQL ([Sandbox].orders): give the connection "
    "another name."
)


# ===== sorting (the owner, 2026-11-21: "We need all sandbox tables to be sortable") =====

SORTS: dict[str, str] = {
    "name": "Name",
    "rows": "Rows",
    "source": "Source",
    "created": "Created",
    "changed": "Last changed",
}


def check_sort(by: Any, order: Any = None) -> tuple[str, bool]:
    """A sort asked for: (one of SORTS, descending). The default: by name, A to Z."""
    key = str(by or "name").strip().lower()
    if key not in SORTS:
        raise SandboxError(f"Sort by one of: {', '.join(SORTS)}.")
    direction = str(order or "").strip().lower()
    if direction not in ("", "asc", "desc"):
        raise SandboxError("order is asc or desc.")
    return key, direction == "desc"


def sort_tables(tables: Sequence[Mapping[str, Any]], by: str, descending: bool) -> list[Mapping[str, Any]]:
    """The sandbox's tables in the order asked: by name (any case), rows, source (in words), created (when
    it came in) or last changed (its last write, else when it came in). Ties keep the name order."""

    def value(t: Mapping[str, Any]) -> Any:
        if by == "rows":
            return int(t.get("rows") or 0)
        if by == "source":
            return str(t.get("source_words") or "").casefold()
        if by == "created":
            return str(t.get("added_at") or "")
        if by == "changed":
            return str(t.get("changed_at") or t.get("added_at") or "")
        return str(t.get("name") or "").casefold()

    named = sorted(tables, key=lambda t: str(t.get("name") or "").casefold())
    return sorted(named, key=value, reverse=descending)


# ===== variants (the owner, 2026-11-21: "And grid table or structure can become a sandbox variant and
# should get its own designation") =====

MARK = "sandbox"  # a variant's marker: "orders · sandbox"
VARIANT_SOURCES = ("grid", "connection", "structure")


def ident_of(text: Any) -> str:
    """A name a person gave, as a sandbox table's name in SQL: "orders test" -> orders_test."""
    made = re.sub(r"[^A-Za-z0-9_]+", "_", str(text or "").strip()).strip("_")[:56]
    if not made:
        raise SandboxError("Give the variant a name.")
    return made if re.match(r"[A-Za-z_]", made) else f"t_{made}"


def variant_name(origin: str, taken: Iterable[str], own: Any = None) -> tuple[str, str]:
    """A new variant's (table name, designation). The user's own name is both (its SQL name made of it);
    else "orders · sandbox" as orders_sandbox, then "orders · sandbox 2" as orders_sandbox_2, so several
    variants of one origin are named apart."""
    used = {t.casefold() for t in taken}
    if own is not None and str(own).strip():
        title = str(own).strip()[:80]
        return check_table_name(ident_of(title)), title
    base = ident_of(origin)[:48]
    for n in range(1, 1000):
        name = f"{base}_{MARK}" if n == 1 else f"{base}_{MARK}_{n}"
        if name.casefold() not in used:
            label = f"{origin} · {MARK}" if n == 1 else f"{origin} · {MARK} {n}"
            return check_table_name(name), label
    raise SandboxError(f"{origin} has too many sandbox variants: name this one.")


def variant_record(source: Mapping[str, Any], title: str, at: str) -> dict[str, Any]:
    """A variant's designation and origin: which table, connection or structure, and when it was copied.
    A variant never writes back to its origin: nothing here names a way back."""
    kind = str(source.get("kind") or "")
    origin: dict[str, Any] = {"kind": kind}
    for k in ("table", "connection", "structure", "path"):
        if source.get(k):
            origin[k] = source[k]
    place = source.get("place")
    if "table" not in origin and isinstance(place, Mapping) and place.get("table"):
        origin["table"] = place[
            "table"
        ]  # a connection's table is named by its place (database, schema, table)
    return {"title": title, "origin": origin, "copied_at": at}


def origin_words(variant: Mapping[str, Any] | None) -> str:
    """A variant's origin in words: "A sandbox variant of orders (Warehouse), copied 2026-11-21 14:02"."""
    if not variant:
        return ""
    origin = variant.get("origin") or {}
    kind = origin.get("kind")
    if kind == "structure":
        where = f"the structure {origin.get('structure', '')}"
        if origin.get("path") and origin.get("path") != "$":
            where += f" at {origin['path']}"
    elif kind == "connection":
        where = f"{origin.get('table') or 'a table'} from {origin.get('connection', '')}"
    else:
        where = str(origin.get("table") or "an open table")
        if origin.get("connection"):
            where += f" ({origin['connection']})"
    at = str(variant.get("copied_at") or "").replace("T", " ")[:16]
    return f"A sandbox variant of {where}" + (f", copied {at}" if at else "")


# ===== editing in its grid (the owner, 2026-11-21: approved "Edit sandbox rows in a grid") =====

_EDITABLE_TYPE = re.compile(r"^[A-Z][A-Z0-9_ ]*(?:\(\d+(?:,\s*\d+)?\))?$")
_TEXT_TYPES = ("VARCHAR", "TEXT", "STRING", "CHAR", "BPCHAR", "UUID")
_TYPE_WORDS = (
    (("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UBIGINT", "UINTEGER"), "a whole number"),
    (("DOUBLE", "FLOAT", "REAL", "DECIMAL", "NUMERIC"), "a number"),
    (("BOOLEAN",), "yes or no"),
    (("TIMESTAMP", "DATETIME"), "a date and time, as 2026-01-15 09:30"),
    (("DATE",), "a date, as 2026-01-15"),
    (("TIME",), "a time, as 09:30"),
)
_YES = {"yes": True, "y": True, "true": True, "1": True, "no": False, "n": False, "false": False, "0": False}


# A LIST, STRUCT or MAP column (the owner approved, 2026-11-21: edited as a small JSON box, type-checked): its
# type as DuckDB names it, of these characters only (a struct's field names quoted by DuckDB itself).
_NESTED_CHARS = re.compile(r'^[A-Za-z0-9_ ,()\[\]"]+$')


def is_nested(duck_type: str) -> bool:
    """A list (INTEGER[], VARCHAR[3]), a struct (STRUCT(...)) or a map (MAP(...)): a JSON value in its
    cell."""
    upper = duck_type.upper().strip()
    return upper.endswith("]") or upper.startswith(("STRUCT(", "MAP("))


def _nested_words(duck_type: str) -> str:
    upper = duck_type.upper().strip()
    if upper.endswith("]"):
        return "a list, written in JSON as [1, 2]"
    if upper.startswith("MAP("):
        return 'a map, written in JSON as {"key": 1}'
    return 'a record, written in JSON as {"field": 1}'


def cast_mark(cast: str) -> str:
    """The bound value's mark as it is written into its column: a nested one from its JSON text."""
    return f"CAST(?::JSON AS {cast})" if is_nested(cast) else f"CAST(? AS {cast})"


def type_words(duck_type: str) -> str:
    if is_nested(duck_type):
        return _nested_words(duck_type)
    upper = duck_type.upper()
    for names, words in _TYPE_WORDS:
        if upper.split("(")[0].strip() in names or upper.startswith(names):
            return words
    return "text" if upper.startswith(_TEXT_TYPES) else upper.lower()


def editable_type(column: str, duck_type: str) -> str:
    """A column's type as an edit's CAST names it (DuckDB's own words for a plain type), or SandboxError."""
    if is_nested(duck_type):
        if not _NESTED_CHARS.match(duck_type.strip()):
            raise SandboxError(f"{column} is a {duck_type}: change it through the API, not in the grid.")
        return duck_type.strip()
    upper = duck_type.upper().strip()
    if not _EDITABLE_TYPE.match(upper):
        raise SandboxError(f"{column} is a {duck_type}: change it through the API, not in the grid.")
    return upper


def cell_value(value: Any, duck_type: str) -> Any:
    """What a cell edit sent, as it is bound: an empty box is blank for anything but text; yes and no for a
    yes/no column; every other value as sent (DuckDB's CAST checks it)."""
    upper = duck_type.upper()
    if is_nested(duck_type):  # its JSON text (DuckDB casts it to the column's own type)
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if not isinstance(value, str):
            return json.dumps(value)
        try:
            json.loads(value)
        except ValueError:
            raise SandboxError(
                f"{value[:40]!r} is not JSON: this column takes {_nested_words(duck_type)}."
            ) from None
        return value
    if isinstance(value, str):
        if value == "" and not upper.startswith(_TEXT_TYPES):
            return None
        if upper == "BOOLEAN" and value.strip().lower() in _YES:
            return _YES[value.strip().lower()]
    if isinstance(value, (dict, list)):
        raise SandboxError("A cell takes one value.")
    return value


def not_a(column: str, value: Any, duck_type: str) -> str:
    """The refusal of a value that is not its column's type, in one sentence."""
    shown = str(value)[:40]
    return f"{shown!r} is not {type_words(duck_type)}: {column} is {duck_type}."


def _row_where(table: str, columns: Sequence[str], values: Sequence[Any]) -> tuple[str, list[Any]]:
    """One row of `table`, found by every value it shows (the grid's row): its rowid, the first of equal
    rows (equal rows cannot be told apart, so either is the same row)."""
    if len(columns) != len(values) or not columns:
        raise SandboxError("A row is every one of its table's values.")
    match = " AND ".join(f"{quote(c)} IS NOT DISTINCT FROM ?" for c in columns)
    sub = f"SELECT rowid FROM {quote(table)} WHERE {match} LIMIT 1"  # noqa: S608 (checked names, bound values)
    return f"rowid = ({sub})", list(values)


def edit_update(
    table: str, columns: Sequence[str], row: Sequence[Any], column: str, value: Any, cast: str
) -> Statement:
    """A cell's new value: the one row the grid shows (all its values), that column set (CAST to its type)."""
    if column not in columns:
        raise SandboxError(f"{table} has no column named {column}.")
    where, params = _row_where(table, columns, row)
    sql = f"UPDATE {quote(table)} SET {quote(column)} = {cast_mark(cast)} WHERE {where}"  # noqa: S608
    return Statement(sql, [value, *params])


def edit_update_where(
    table: str, columns: Sequence[str], values: Mapping[str, tuple[Any, str]], where: Any
) -> Statement:
    """The rows `where` picks, each column given set (its value and its CAST type, a nested one from JSON)."""
    if not values:
        raise SandboxError("update takes the values to set: a dict of column to value.")
    known = _known(table, columns, values)
    sets = ", ".join(f"{quote(known[c])} = {cast_mark(cast)}" for c, (_, cast) in values.items())
    clause, more = _where(table, columns, where)
    sql = f"UPDATE {quote(table)} SET {sets} WHERE {clause}"  # noqa: S608 (checked names and types)
    return Statement(sql, [v for v, _ in values.values()] + more)


def edit_delete(table: str, columns: Sequence[str], row: Sequence[Any]) -> Statement:
    where, params = _row_where(table, columns, row)
    return Statement(f"DELETE FROM {quote(table)} WHERE {where}", params)  # noqa: S608


def edit_insert(table: str, values: Mapping[str, tuple[Any, str]]) -> Statement:
    """A new row: each column given (its value and its CAST type); the rest blank (or their default)."""
    if not values:
        return Statement(f"INSERT INTO {quote(table)} DEFAULT VALUES", [])
    names = ", ".join(quote(c) for c in values)
    marks = ", ".join(cast_mark(cast) for _, cast in values.values())
    sql = f"INSERT INTO {quote(table)} ({names}) VALUES ({marks})"  # noqa: S608 (checked names and types)
    return Statement(sql, [v for v, _ in values.values()])


# ===== what an API makes through its mock (the test app's gap 8): views, query tables, sequences =====


def not_made(name: str, verb: str) -> str:
    """The refusal of a definition over a table the user added: only what an API made is replaced or
    dropped."""
    doing = "replace" if verb == "create" else "drop"
    return (
        f"{name} is a sandbox table you added: an API cannot {doing} it (make a view or table under another "
        "name; remove a table on the Sandbox page)."
    )


def made_record(what: str, client: Mapping[str, Any], at: str) -> dict[str, Any]:
    """sandbox.json's record of a view or a query's table an API made: its connection's table from then on."""
    connection = str(client.get("connection") or NAME)
    return {
        "source": {"kind": "made", "what": what, "connection": connection},
        "client": dict(client),
        "added_at": at,
    }


def unmade(meta: Meta, there: Iterable[str]) -> list[str]:
    """After Reset or Restore: the records of what an API made that the file no longer holds, taken out."""
    held = {t.casefold() for t in there}
    gone = [
        t
        for t, record in meta.tables.items()
        if (record.get("source") or {}).get("kind") == "made" and t.casefold() not in held
    ]
    for t in gone:
        meta.tables.pop(t, None)
        meta.log.pop(t, None)
    return gone


# ===== the sandbox keeps its keys (the owner approved, 2026-11-21): a duplicate refused as a database
# would =====


def check_key(key: Any, columns: Iterable[str]) -> list[str]:
    """A primary key asked for: its columns' own names (any case), or SandboxError."""
    wanted = [key] if isinstance(key, str) else list(key) if isinstance(key, (list, tuple)) else []
    if not wanted or not all(isinstance(k, str) and k.strip() for k in wanted):
        raise SandboxError("A key is one column's name, or a list of them.")
    by_case = {c.casefold(): c for c in columns}
    out = []
    for k in wanted:
        found = by_case.get(k.strip().casefold())
        if found is None:
            raise SandboxError(f"There is no column named {k} to be the key.")
        out.append(found)
    return list(dict.fromkeys(out))


_DUPLICATE = re.compile(r'Duplicate key "(.+?)" violates (?:primary key|unique) constraint', re.S)
_BLANK = re.compile(r'NOT NULL constraint failed: "?([^".]+)\.?([^"]*)"?', re.S)


def db_words(error: BaseException | str) -> str:
    """DuckDB's refusal of a write in one sentence, a key's as a database says it (its key and value)."""
    text = str(error).split("\n")[0]
    found = _DUPLICATE.search(text)
    if found:
        return f"Duplicate key: a row with {found.group(1)} is there already (its primary key)."
    if "Data contains duplicates on indexed column" in text:
        return "Duplicate key: two rows have the same key, so it cannot be the table's primary key."
    blank = _BLANK.search(text)
    if blank and "PRIMARY" in text.upper():
        return "A key column cannot be blank: every row needs its primary key."
    if blank:
        column = blank.group(2) or blank.group(1)
        return f"{column} cannot be blank."
    return text


def touched(meta: Meta, tables: Iterable[str], at: str) -> None:
    """A write's time on each table it changed (Last changed)."""
    for table in tables:
        if table in meta.tables:
            meta.tables[table]["changed_at"] = at


def ignored(gitignore: str | None) -> str | None:
    """The project's .gitignore with the sandbox's rows kept out (None: already there). An older project's
    `.sab/sandbox/` line stays (harmless); only the missing line is added, at the end."""
    lines = (gitignore or "").splitlines()
    if any(
        line.strip() in (IGNORE_LINE, "/" + IGNORE_LINE, IGNORE_LINE.rstrip("/"), "/sandbox")
        for line in lines
    ):
        return None
    head = (gitignore or "").rstrip("\n")
    note = "# Swiss Army Bench: the sandbox's rows (made-up or copied test data) stay out of Git."
    return (head + "\n\n" if head else "") + note + "\n" + IGNORE_LINE + "\n"
