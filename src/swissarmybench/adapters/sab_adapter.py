"""sab_adapter: every data call in and out of a project, the same file wherever it runs (the app, a Workbench
kernel, a local sandbox API's process, an exported project). It holds nothing: a read streams Arrow record
batches from its source, a write streams them into it, and only tables (named Arrow tables) stay: a grid is
only a view of one.

    from sab_adapter import Filter, Plan, read, table, tables, write

    reader, folded = read("Warehouse", "orders", Plan(columns=("id", "amount"), filters=(Filter("region",
                          "=", "North"),), limit=100))
    for batch in reader: ...                  # Arrow record batches, as the source answers them
    write("Warehouse", "orders", rows, key=("id",), mode="merge")   # -> Counts(inserted, updated, deleted)

It reads top to bottom in the order a call runs:

  1. The plan       what a read asks for (columns, filters, sort, limit, offset, group, totals), and what
                    its source folded
  2. Sources        a source is three functions (tables, read, write); DuckDB (a file, or a connection given),
                    Remote (the project's sandbox through the app, for a local sandbox API's process)
  3. The calls      tables(source), read(source, table, plan), write(source, table, batches, key, mode): by a
                    source's name (use() says how a name is found) or the source itself; what a source could
                    not fold is finished here, in DuckDB, over the stream
  4. JSON to Arrow  pages of records (an API's answer, a request's body) made Arrow by DuckDB, page by page,
                    with the types given (else the first page's)
  5. Tables         table(name): a named Arrow table made from one read and one DuckDB SQL, made on first use
                    and kept; refresh(name) reads it again

The standard library, duckdb and pyarrow only: an export copies this file as it is.
"""

from __future__ import annotations

import contextlib
import http.client
import itertools
import json
import re
import urllib.parse
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import duckdb
import pyarrow as pa
import pyarrow.ipc as ipc

BATCH_ROWS = 50_000  # rows in each record batch a read streams
OPS = ("=", "!=", "<", "<=", ">", ">=", "in", "between", "like", "is null", "is not null")
TOTALS = ("count", "count_distinct", "sum", "avg", "min", "max")
MODES = ("insert", "update", "merge", "delete", "truncate")
KEYED = ("update", "merge", "delete")  # the modes that match rows by a key
PARTS = ("filters", "group", "totals", "columns", "sort", "offset", "limit")  # in the order SQL applies them
ROWS = "rows"  # what a table's SQL calls its read: SELECT region, sum(amount) FROM rows GROUP BY 1


class AdapterError(ValueError):
    """A plan, a table or a write the source cannot take, said in one sentence."""


# ===== 1. The plan =====


@dataclass(frozen=True)
class Filter:
    """One condition: column op value (`in` takes a list, `between` two values, `is null` none)."""

    column: str
    op: str = "="
    value: Any = None


@dataclass(frozen=True)
class Total:
    """One aggregate: count (of rows, or of a column's values), count_distinct, sum, avg, min or max."""

    fn: str
    column: str = ""
    name: str = ""  # its column in the answer; fn_column by default

    @property
    def label(self) -> str:
        return self.name or (f"{self.fn}_{self.column}" if self.column else self.fn)


@dataclass(frozen=True)
class Plan:
    """What a read asks for. Applied as SQL is: filters, then group and totals (or the columns), then sort,
    offset and limit. With totals, the answer is the group's columns and the totals; with none, the columns
    (every column when none are named)."""

    columns: tuple[str, ...] = ()
    filters: tuple[Filter, ...] = ()
    sort: tuple[tuple[str, bool], ...] = ()  # (column, descending)
    limit: int | None = None
    offset: int = 0
    group: tuple[str, ...] = ()
    totals: tuple[Total, ...] = ()

    def parts(self) -> tuple[str, ...]:
        """The parts this plan asks for."""
        asked = {
            "columns": bool(self.columns),
            "filters": bool(self.filters),
            "group": bool(self.group),
            "totals": bool(self.totals),
            "sort": bool(self.sort),
            "offset": bool(self.offset),
            "limit": self.limit is not None,
        }
        return tuple(p for p in PARTS if asked[p])

    def to_json(self) -> dict[str, Any]:
        """The plan as JSON (its filters as [column, op, value], its sort as [column, "asc" | "desc"])."""
        return {
            "columns": list(self.columns),
            "filters": [[f.column, f.op, f.value] for f in self.filters],
            "sort": [[c, "desc" if d else "asc"] for c, d in self.sort],
            "limit": self.limit,
            "offset": self.offset,
            "group": list(self.group),
            "totals": [{"fn": t.fn, "column": t.column, "name": t.name} for t in self.totals],
        }


def plan_from(raw: Mapping[str, Any] | None) -> Plan:
    """A plan from its JSON (Plan.to_json's shape), checked: a wrong op, total or number said plainly."""
    given = dict(raw or {})
    filters = []
    for item in given.get("filters") or []:
        if not isinstance(item, (list, tuple)) or len(item) not in (2, 3):
            raise AdapterError("A filter is [column, op, value].")
        filters.append(Filter(str(item[0]), str(item[1]).lower(), item[2] if len(item) == 3 else None))
    sort = []
    for item in given.get("sort") or []:
        column, way = (
            (item, "asc") if isinstance(item, str) else (item[0], item[1] if len(item) > 1 else "asc")
        )
        sort.append((str(column), str(way).lower() == "desc"))
    totals = [
        Total(str(t.get("fn") or ""), str(t.get("column") or ""), str(t.get("name") or ""))
        for t in given.get("totals") or []
    ]
    limit = given.get("limit")
    plan = Plan(
        columns=tuple(str(c) for c in given.get("columns") or []),
        filters=tuple(filters),
        sort=tuple(sort),
        limit=None if limit is None else _whole(limit, "limit"),
        offset=_whole(given.get("offset") or 0, "offset"),
        group=tuple(str(c) for c in given.get("group") or []),
        totals=tuple(totals),
    )
    check_plan(plan)
    return plan


def _whole(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AdapterError(f"A plan's {what} is a whole number of 0 or more, not {value!r}.")
    return value


def check_plan(plan: Plan) -> None:
    for f in plan.filters:
        if f.op not in OPS:
            raise AdapterError(f"A filter's op is one of {', '.join(OPS)}, not {f.op!r}.")
        if f.op == "in" and not (isinstance(f.value, (list, tuple)) and f.value):
            raise AdapterError(f"The filter on {f.column} with in takes a list of values.")
        if f.op == "between" and not (isinstance(f.value, (list, tuple)) and len(f.value) == 2):
            raise AdapterError(f"The filter on {f.column} with between takes two values.")
    for t in plan.totals:
        if t.fn not in TOTALS:
            raise AdapterError(f"A total is one of {', '.join(TOTALS)}, not {t.fn!r}.")
        if t.fn != "count" and not t.column:
            raise AdapterError(f"A {t.fn} total names its column.")
    if plan.group and not plan.totals:
        raise AdapterError("A plan that groups names its totals.")


@dataclass(frozen=True)
class Folded:
    """The parts of a plan its source took (sent to it in its own query); the adapter does the rest."""

    parts: tuple[str, ...] = ()

    def rest(self, plan: Plan) -> Plan:
        """What is left of `plan` for DuckDB to do over the stream."""
        done = set(self.parts)
        return Plan(
            columns=() if "columns" in done else plan.columns,
            filters=() if "filters" in done else plan.filters,
            sort=() if "sort" in done else plan.sort,
            limit=None if "limit" in done else plan.limit,
            offset=0 if "offset" in done else plan.offset,
            group=() if "group" in done else plan.group,
            totals=() if "totals" in done else plan.totals,
        )


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # DuckDB's type name
    key: bool = False  # part of the table's primary key


@dataclass(frozen=True)
class Table:
    name: str  # the source's own name for it: what read and write take
    columns: tuple[Column, ...] = ()


@dataclass(frozen=True)
class Counts:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0

    @property
    def rows(self) -> int:
        return self.inserted + self.updated + self.deleted


# ===== 2. Sources =====


class Source(Protocol):
    """A source plugs in by three functions. read folds what it can of the plan into its own query and says
    which parts it folded; write takes the batches in its own insert, update, merge, delete or truncate."""

    def tables(self) -> list[Table]: ...

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, Folded]: ...

    def write(self, table: str, batches: pa.RecordBatchReader, key: Sequence[str], mode: str) -> Counts: ...


def quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def plan_sql(relation: str, plan: Plan) -> tuple[str, list[Any]]:
    """The plan as one DuckDB query over `relation` (a quoted name, or a subquery in brackets), its values
    bound as parameters."""
    check_plan(plan)
    params: list[Any] = []
    wheres = [_condition(f, params) for f in plan.filters]
    if plan.totals:
        picked = [quote(c) for c in plan.group] + [_total(t) for t in plan.totals]
    else:
        picked = [quote(c) for c in plan.columns] or ["*"]
    sql = f"SELECT {', '.join(picked)} FROM {relation}"  # noqa: S608 (names quoted, values bound)
    if wheres:
        sql += " WHERE " + " AND ".join(wheres)
    if plan.group:
        sql += " GROUP BY " + ", ".join(quote(c) for c in plan.group)
    if plan.sort:
        sql += " ORDER BY " + ", ".join(f"{quote(c)} {'DESC' if d else 'ASC'}" for c, d in plan.sort)
    if plan.limit is not None:
        sql += f" LIMIT {int(plan.limit)}"
    if plan.offset:
        sql += f" OFFSET {int(plan.offset)}"
    return sql, params


def _condition(f: Filter, params: list[Any]) -> str:
    name = quote(f.column)
    if f.op == "is null":
        return f"{name} IS NULL"
    if f.op == "is not null":
        return f"{name} IS NOT NULL"
    if f.op == "in":
        params.extend(f.value)
        return f"{name} IN ({', '.join('?' for _ in f.value)})"
    if f.op == "between":
        params.extend(f.value)
        return f"{name} BETWEEN ? AND ?"
    params.append(f.value)
    if f.op == "like":
        return f"CAST({name} AS VARCHAR) LIKE ?"
    return f"{name} {'<>' if f.op == '!=' else f.op} ?"


def _total(t: Total) -> str:
    if t.fn == "count":
        what = f"count({quote(t.column)})" if t.column else "count(*)"
    elif t.fn == "count_distinct":
        what = f"count(DISTINCT {quote(t.column)})"
    else:
        what = f"{t.fn}({quote(t.column)})"
    return f"{what} AS {quote(t.label)}"


Connect = Callable[[bool], contextlib.AbstractContextManager[Any]]  # (for writing) -> a DuckDB connection


class DuckDB:
    """A DuckDB database as a source: it folds the whole plan. DuckDB.file(path) opens the file for each call
    (read-only to read); DuckDB.over(connection) uses a connection someone else opened (a cursor each call);
    DuckDB(connect) takes a function giving a connection for a call (the sandbox's: under its own lock)."""

    def __init__(self, connect: Connect, name: str = "DuckDB") -> None:
        self._connect = connect
        self.name = name

    @classmethod
    def file(cls, path: str) -> DuckDB:
        @contextlib.contextmanager
        def opened(writing: bool) -> Iterator[Any]:
            con = duckdb.connect(str(path), read_only=not writing, config={"enable_external_access": False})
            try:
                yield con
            finally:
                con.close()

        return cls(opened, str(path))

    @classmethod
    def over(cls, connection: Any, name: str = "DuckDB") -> DuckDB:
        @contextlib.contextmanager
        def cursor(writing: bool) -> Iterator[Any]:
            con = connection.cursor()
            try:
                yield con
            finally:
                con.close()

        return cls(cursor, name)

    def tables(self) -> list[Table]:
        with self._connect(False) as con:
            return [
                Table(name, tuple(Column(*c) for c in _columns(con, schema, table)))
                for name, schema, table in _relations(con)
            ]

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, Folded]:
        return _stream(self._connect, self._query, table, plan), Folded(plan.parts())

    def _query(self, con: Any, table: str, plan: Plan) -> tuple[str, list[Any]]:
        schema, name = self._place(con, table)
        known = {c[0].casefold() for c in _columns(con, schema, name)}
        named = [*plan.columns, *plan.group, *(f.column for f in plan.filters)]
        named += [t.column for t in plan.totals if t.column]
        named += [c for c, _ in plan.sort if c.casefold() not in {t.label.casefold() for t in plan.totals}]
        for column in named:
            if column.casefold() not in known:
                raise AdapterError(f"{table} has no column {column!r}.")
        return plan_sql(f"{quote(schema)}.{quote(name)}", plan)

    def _place(self, con: Any, table: str) -> tuple[str, str]:
        wanted = str(table).casefold()
        for listed, schema, name in _relations(con):
            if listed.casefold() == wanted:
                return schema, name
        raise AdapterError(f"{self.name} has no table {table!r}.")

    def write(self, table: str, batches: pa.RecordBatchReader, key: Sequence[str], mode: str) -> Counts:
        if mode not in MODES:
            raise AdapterError(f"A write's mode is one of {', '.join(MODES)}, not {mode!r}.")
        if mode in KEYED and not key:
            raise AdapterError(f"A {mode} names the key its rows are matched by.")
        names = [str(n) for n in batches.schema.names]
        with self._connect(True) as con:
            schema, name = self._place(con, table)
            target = f"{quote(schema)}.{quote(name)}"
            if names:  # a truncate with no rows has no columns to register
                con.register("sab_incoming", batches)
            con.execute("BEGIN TRANSACTION")
            try:
                done = _written(con, target, names, list(key), mode)
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            finally:
                if names:
                    con.unregister("sab_incoming")
            return done


def _relations(con: Any) -> list[tuple[str, str, str]]:
    """Each table and view of the database: its listed name (table, or schema.table outside main), schema,
    name."""
    rows = con.sql(
        "SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = current_database() "
        "AND NOT internal UNION ALL SELECT schema_name, view_name FROM duckdb_views() "
        "WHERE database_name = current_database() AND NOT internal ORDER BY 1, 2"
    ).fetchall()
    return [(t if s == "main" else f"{s}.{t}", s, t) for s, t in rows]


def _columns(con: Any, schema: str, table: str) -> list[tuple[str, str, bool]]:
    keys = {
        str(c)
        for row in con.sql(
            "SELECT constraint_column_names FROM duckdb_constraints() "
            "WHERE database_name = current_database() "
            "AND schema_name = ? AND table_name = ? AND constraint_type = 'PRIMARY KEY'",
            params=[schema, table],
        ).fetchall()
        for c in row[0] or []
    }
    rows = con.sql(
        "SELECT column_name, data_type FROM duckdb_columns() WHERE database_name = current_database() "
        "AND schema_name = ? AND table_name = ? ORDER BY column_index",
        params=[schema, table],
    ).fetchall()
    return [(str(n), str(t), str(n) in keys) for n, t in rows]


def _stream(
    connect: Connect, query: Callable[[Any, str, Plan], tuple[str, list[Any]]], table: str, plan: Plan
) -> pa.RecordBatchReader:
    """The query's answer as a reader that keeps its connection only while it is read: the batches come as
    DuckDB makes them, never all at once."""

    def batches() -> Iterator[Any]:
        with connect(False) as con:
            sql, params = query(con, table, plan)
            reader = con.sql(sql, params=params).to_arrow_reader(BATCH_ROWS)
            yield reader.schema
            yield from reader

    made = batches()
    schema = next(made)  # started: its connection is closed when the reader is read or dropped
    return pa.RecordBatchReader.from_batches(schema, made)


def _written(con: Any, target: str, names: list[str], key: list[str], mode: str) -> Counts:
    """sab_incoming's rows (its columns `names`) into `target`, in the open transaction. A merge stages them
    once, as it reads them twice. A truncate clears the table (its columns kept), then inserts the rows."""
    if mode == "truncate":
        deleted = _count(con, f"DELETE FROM {target}")  # noqa: S608 (the name quoted)
        if not names:
            return Counts(deleted=deleted)
        inserted = _count(con, f"INSERT INTO {target} BY NAME SELECT * FROM sab_incoming")  # noqa: S608
        return Counts(inserted=inserted, deleted=deleted)
    if mode == "insert":
        return Counts(inserted=_count(con, f"INSERT INTO {target} BY NAME SELECT * FROM sab_incoming"))  # noqa: S608
    if mode == "update":
        return Counts(updated=_count(con, _update_sql(target, "sab_incoming", names, key)))
    if mode == "delete":
        listed = ", ".join(quote(k) for k in key)
        gone = f"DELETE FROM {target} WHERE ({listed}) IN (SELECT ({listed}) FROM sab_incoming)"  # noqa: S608
        return Counts(deleted=_count(con, gone))
    con.execute("CREATE OR REPLACE TEMP TABLE sab_staged AS SELECT * FROM sab_incoming")
    updated = _count(con, _update_sql(target, "sab_staged", names, key))
    match = " AND ".join(f"t.{quote(k)} IS NOT DISTINCT FROM s.{quote(k)}" for k in key)
    inserted = _count(
        con,
        f"INSERT INTO {target} BY NAME SELECT * FROM sab_staged s "  # noqa: S608 (names quoted)
        f"WHERE NOT EXISTS (SELECT 1 FROM {target} t WHERE {match})",
    )
    con.execute("DROP TABLE sab_staged")
    return Counts(inserted=inserted, updated=updated)


def _update_sql(target: str, rows: str, names: list[str], key: list[str]) -> str:
    missing = [k for k in key if k not in names]
    if missing:
        raise AdapterError(f"The rows have no {missing[0]} column to match by.")
    sets = [n for n in names if n not in key]
    if not sets:
        raise AdapterError("The rows have nothing to change but their key.")
    assigned = ", ".join(f"{quote(n)} = s.{quote(n)}" for n in sets)
    match = " AND ".join(f"{target}.{quote(k)} IS NOT DISTINCT FROM s.{quote(k)}" for k in key)
    return f"UPDATE {target} SET {assigned} FROM {rows} s WHERE {match}"  # noqa: S608 (names quoted)


def _count(con: Any, sql: str) -> int:
    found = con.execute(sql).fetchall()
    return int(found[0][0]) if found and found[0] and isinstance(found[0][0], int) else 0


class Remote:
    """The project's sandbox through the app's data door (a local sandbox API's process has no file and no
    connection of its own): `connection` names whose tables these are (a sandbox table mocked as it), the
    reads and writes travel as Arrow IPC streams. The sandbox folds the whole plan."""

    def __init__(self, url: str, connection: str = "Sandbox") -> None:
        self.url = url.rstrip("/")
        self.connection = connection

    def tables(self) -> list[Table]:
        answer = json.loads(
            self._post("/tables", json.dumps({"connection": self.connection}).encode()).read()
        )
        return [
            Table(t["name"], tuple(Column(c["name"], c["type"], bool(c.get("key"))) for c in t["columns"]))
            for t in answer["tables"]
        ]

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, Folded]:
        body = json.dumps({"connection": self.connection, "table": table, "plan": plan.to_json()}).encode()
        answer = self._post("/read", body)
        folded = Folded(tuple(p for p in answer.getheader("X-Sab-Folded", "").split(",") if p))
        reader = ipc.open_stream(answer)  # read as it arrives: one batch at a time
        return pa.RecordBatchReader.from_batches(reader.schema, _closing(reader, answer)), folded

    def write(self, table: str, batches: pa.RecordBatchReader, key: Sequence[str], mode: str) -> Counts:
        sink = pa.BufferOutputStream()
        with ipc.new_stream(sink, batches.schema) as stream:
            for batch in batches:
                stream.write_batch(batch)
        query = urllib.parse.urlencode(
            {"connection": self.connection, "table": table, "key": ",".join(key), "mode": mode}
        )
        answer = json.loads(self._post("/write?" + query, sink.getvalue().to_pybytes()).read())
        return Counts(int(answer["inserted"]), int(answer["updated"]), int(answer["deleted"]))

    def _post(self, path: str, body: bytes) -> http.client.HTTPResponse:
        parts = urllib.parse.urlsplit(self.url + path)
        connection = http.client.HTTPConnection(parts.hostname or "127.0.0.1", parts.port or 80, timeout=600)
        target = parts.path + (f"?{parts.query}" if parts.query else "")
        connection.request("POST", target, body, {"Content-Type": "application/octet-stream"})
        answer = connection.getresponse()
        if answer.status >= 400:
            raw = answer.read()
            connection.close()
            try:
                said = str(json.loads(raw or b"{}").get("error") or answer.reason)
            except ValueError:
                said = answer.reason
            raise AdapterError(said)
        return answer


def _closing(reader: Any, answer: Any) -> Iterator[pa.RecordBatch]:
    try:
        yield from reader
    finally:
        answer.close()


# ===== 3. The calls =====

_find: Callable[[str], Source] | None = None


def use(find: Callable[[str], Source] | None) -> None:
    """How a source's name is found: set once by whatever runs this (the app, a local sandbox API's process,
    an export's connections.py)."""
    global _find
    _find = find


def source_of(source: str | Source) -> Source:
    if not isinstance(source, str):
        return source
    if _find is None:
        raise AdapterError(f"No source is named {source!r} here.")
    return _find(source)


def tables(source: str | Source) -> list[Table]:
    """The source's tables: names, columns and types."""
    return source_of(source).tables()


def read(source: str | Source, table: str, plan: Plan | None = None) -> tuple[pa.RecordBatchReader, Folded]:
    """A table read as a stream of Arrow batches, and what the source folded of the plan. What it could not
    fold is done here by DuckDB over the stream (never a copy of the whole read)."""
    asked = plan or Plan()
    check_plan(asked)
    reader, folded = source_of(source).read(table, asked)
    took = [p in folded.parts for p in asked.parts()]
    if any(later and not earlier for earlier, later in itertools.pairwise(took)):
        raise AdapterError(
            "A source folds a plan's parts in the order SQL applies them, never a later one alone."
        )
    rest = folded.rest(asked)
    if not rest.parts():
        return reader, folded
    return _finished(reader, rest), folded


def _finished(reader: pa.RecordBatchReader, rest: Plan) -> pa.RecordBatchReader:
    def batches() -> Iterator[Any]:
        con = duckdb.connect()
        try:
            con.register("sab_read", reader)
            sql, params = plan_sql("sab_read", rest)
            finished = con.sql(sql, params=params).to_arrow_reader(BATCH_ROWS)
            yield finished.schema
            yield from finished
        finally:
            con.close()

    made = batches()
    schema = next(made)
    return pa.RecordBatchReader.from_batches(schema, made)


def write(
    source: str | Source,
    table: str,
    batches: pa.RecordBatchReader | pa.Table | None = None,
    key: Sequence[str] = (),
    mode: str = "insert",
) -> Counts:
    """Arrow batches into a table: insert, update (by key), merge (update, else insert, by key), delete
    (by key) or truncate (the table cleared, its columns kept, then the rows inserted; no rows: only
    cleared); all or none. The counts of rows each way."""
    if mode not in MODES:
        raise AdapterError(f"A write's mode is one of {', '.join(MODES)}, not {mode!r}.")
    if batches is None:
        if mode != "truncate":
            raise AdapterError(f"A {mode} takes the rows it writes.")
        batches = pa.table({})
    reader = batches if isinstance(batches, pa.RecordBatchReader) else batches.to_reader()
    return source_of(source).write(table, reader, tuple(key), mode)


# ===== 4. JSON to Arrow =====

_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]*(\(\s*\d+\s*(,\s*\d+\s*)?\))?(\[\])?$")


def from_json(
    pages: Iterable[str | bytes | Sequence[Mapping[str, Any]]],
    columns: Mapping[str, str] | None = None,
    strict: bool = False,
) -> pa.RecordBatchReader:
    """Pages of records (each a JSON array of objects, as text, bytes or a list) as Arrow, one batch a page,
    each value in its column's DuckDB type (`columns`; else the first page's types, kept for every page so a
    page missing a field keeps the type). `strict`: a value that is not of its type is refused, not blank."""
    texts = (_text(p) for p in pages)
    con = duckdb.connect()
    first, shape = "", None
    for first in texts:  # the first page with records sets the types when none are given
        shape = _structure(con, first, columns)
        if shape is not None:
            break
    if shape is None:
        con.close()
        return pa.RecordBatchReader.from_batches(pa.schema([]), iter([]))
    convert = "json_transform_strict" if strict else "json_transform"
    sql = f"SELECT r.* FROM (SELECT unnest({convert}(?::JSON, '{shape}')) AS r)"  # noqa: S608 (types checked)

    def one(text: str) -> pa.Table:
        try:
            return con.sql(sql, params=[text]).to_arrow_table()
        except duckdb.Error as error:
            raise AdapterError(str(error).split("\n")[0]) from None

    head = one(first)

    def batches() -> Iterator[pa.RecordBatch]:
        try:
            yield from head.to_batches()
            for text in texts:
                yield from one(text).to_batches()  # the same structure: the same schema
        finally:
            con.close()

    return pa.RecordBatchReader.from_batches(head.schema, batches())


def _text(page: str | bytes | Sequence[Mapping[str, Any]]) -> str:
    if isinstance(page, bytes):
        return page.decode("utf-8")
    return page if isinstance(page, str) else json.dumps(list(page), default=str)


def _structure(con: Any, first: str, columns: Mapping[str, str] | None) -> str | None:
    """json_transform's structure ([{"name": "TYPE", ...}]) as a SQL string's text; None for a first page with
    no records and no types given."""
    if columns:
        for kind in columns.values():
            if not _TYPE.match(str(kind)):
                raise AdapterError(f"{kind!r} is not a DuckDB type.")
        return json.dumps([{str(n): str(k) for n, k in columns.items()}]).replace("'", "''")
    try:
        found = str(con.sql("SELECT json_structure(?::JSON)", params=[first]).fetchall()[0][0])
    except duckdb.Error as error:
        raise AdapterError(str(error).split("\n")[0]) from None
    if found in ("[]", '["NULL"]'):
        return None
    if not found.startswith("[{"):
        raise AdapterError("A page is a JSON array of objects (records).")
    return found.replace("'", "''")


# ===== 5. Tables =====


@dataclass(frozen=True)
class TableSource:
    """Where a table comes from: one source's table read with a plan, then (if given) one DuckDB SQL over the
    read, which it names `rows`."""

    source: str | Source
    table: str
    plan: Plan = field(default_factory=Plan)
    sql: str = ""


def make_table(made_from: TableSource) -> pa.Table:
    """The table (the one copy): the read streamed through its SQL, and nothing of the read kept."""
    reader, _ = read(made_from.source, made_from.table, made_from.plan)
    if not made_from.sql:
        return reader.read_all()
    con = duckdb.connect()
    try:
        con.register(ROWS, reader)
        return con.sql(made_from.sql).to_arrow_table()
    finally:
        con.close()


class Tables:
    """Named Arrow tables, the only data kept (a grid only shows one): made on first use, read again on
    refresh."""

    def __init__(self) -> None:
        self._from: dict[str, TableSource] = {}
        self._made: dict[str, pa.Table] = {}

    def define(
        self, name: str, source: str | Source, table: str, plan: Plan | None = None, sql: str = ""
    ) -> None:
        self._from[name] = TableSource(source, table, plan or Plan(), sql)
        self._made.pop(name, None)

    def table(self, name: str) -> pa.Table:
        if name not in self._made:
            self._made[name] = make_table(self._defined(name))
        return self._made[name]

    def refresh(self, name: str) -> pa.Table:
        self._made[name] = make_table(self._defined(name))
        return self._made[name]

    def drop(self, name: str) -> None:
        self._from.pop(name, None)
        self._made.pop(name, None)

    def names(self) -> list[str]:
        return list(self._from)

    def _defined(self, name: str) -> TableSource:
        found = self._from.get(name)
        if found is None:
            raise AdapterError(f"No table is named {name!r}.")
        return found


TABLES = Tables()  # this process's tables
define, table, refresh = TABLES.define, TABLES.table, TABLES.refresh

__all__ = [
    "AdapterError",
    "Column",
    "Counts",
    "DuckDB",
    "Filter",
    "Folded",
    "Plan",
    "Remote",
    "Source",
    "Table",
    "TableSource",
    "Tables",
    "Total",
    "define",
    "from_json",
    "make_table",
    "plan_from",
    "plan_sql",
    "read",
    "refresh",
    "table",
    "tables",
    "use",
    "write",
]
