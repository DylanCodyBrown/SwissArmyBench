"""adapter: every data call in and out of a project, the same file wherever it runs (the app, a Workbench
kernel, a local sandbox API's process, an exported project). It holds nothing: a read streams Arrow record
batches from its source, a write streams them into it, and only tables (named Arrow tables) stay: a grid is
only a view of one.

    from adapter import Filter, Plan, query, read, table, tables, write

    reader, folded = read("Warehouse", "orders", Plan(columns=("id", "amount"), filters=(Filter("region",
                          "=", "North"),), limit=100))
    for batch in reader: ...                  # Arrow record batches, as the source answers them
    query("Warehouse", "SELECT ... JOIN ...", [region])   # the source's own SQL (joins, CTEs) -> Arrow
    write("Warehouse", "orders", rows, key=("id",), mode="merge")   # -> Counts(inserted, updated, deleted)

    db = Connection("Warehouse")              # what API.py's connection(name) hands out: the same calls
    db.read("orders", filters=[["region", "=", "North"]], limit=100); db.query(sql, params); db.write(...)
    db.write_all([...]); db.planned("orders", rows, key=("id",), mode="merge")   # all or none; a dry run

It reads top to bottom in the order a call runs:

  1. The plan       what a read asks for (columns, filters, sort, limit, offset, group, periods, totals),
                    and what its source folded
  2. Sources        a source is three functions (tables, read, write), and query when it speaks SQL; DuckDB (a
                    file, or a connection given), Remote (the project's sandbox through the app, for a local
                    sandbox API's process), Sql (SQL Server's writes and Trino's in sections of their
                    own), OData, Rows, Files, Excel (a workbook's sheets and named tables; openpyxl
                    imported only when one is used); source_from(client) wraps a connection's own client
                    (or its file's path, or a workbook's bytes) in its backend
  3. The calls      tables(source), read(source, table, plan), query(source, sql, params), write(source,
                    table, batches, key, mode), write_all(source, writes) (several, all or none): by a
                    source's name (use() says how a name is found) or
                    the source itself; what a source could not fold is finished here, in DuckDB, over the
                    stream; Connection(name): the same calls on one source (API.py's connection(name));
                    observe(hook): each call's facts as it ends, for the statistics (never a value)
  4. JSON to Arrow  pages of records (an API's answer, a request's body) made Arrow by DuckDB, page by page,
                    with the types given (else the first page's)
  5. Tables         table(name): a named Arrow table made from one read and one DuckDB SQL, made on first use
                    and kept; refresh(name) reads it again

The standard library, duckdb and pyarrow only (openpyxl too once a workbook is read or written, said in
one sentence when it is missing): an export copies this file as it is. Its contract only grows
(design principle 12b): a version adds, never breaks a caller.

Version 1.10.0 (2026-11-23). What each phase added (Plans/adapter.plan.md):
  phase 1  the contract (tables, read with a Plan and what was Folded, write by mode: insert, update, merge,
           delete), the Plan, JSON pages to Arrow (from_json), tables; the sources DuckDB and Remote
  phase 2  truncate; table(name), Tables, TableSource, make_table; Sql with DIALECTS, OData, Rows; to_json and
           to_ipc (an endpoint's answer)
  phase 3  query (a source's own SQL); Connection; source_from; OData's and Rows' writes; planned (a write's
           dry run by reads); catalog_rows; Files
  1.0.0    Files' format, COPY options and partitioned folders; a failed SQL batch beside its error (Batch,
           batch_of); Sql's value; arrow_of; listed() and each dialect's listing; columns' and tables'
           descriptions and positions; the file and module named adapter (was sab_adapter)
  1.1.0    SQL Server's and Azure SQL's writes (staged in the target's types from sys.columns, MERGE WITH
           (HOLDLOCK), TRUNCATE, identity_insert, passing errors run again whole: Sql's reopen and
           identity_insert; transient, ServerColumn, server_columns); Trino's writes (row batches without a
           transaction, said in NO_TRANSACTION; a truncate with rows refused; Dialect.drains); Counts.notes;
           a source's own planned() and statements() (what a write runs, for a dry run's report); a
           three-part name quoted part by part
  1.2.0    observe(hook): each read's, query's and write's facts as it ends (times in parts, sizes, what the
           source folded against what DuckDB did, the outcome's kind, the result's fingerprint; never a
           value); fingerprint(schema)
  1.3.0    Trino's replace (a truncate with rows) as one CREATE OR REPLACE TABLE ... AS where the catalog has
           it (Iceberg's): its columns' types and properties kept, all or none (TRINO_REPLACE); a catalog
           without it refused as before, nothing changed; at most TRINO_REPLACE_VALUES values in it
  1.4.0    Excel (Plans/excel.plan.md): a workbook (a path, or bytes) as a source: its sheets and named
           tables listed, read as Arrow by one set of type rules (typed, header_names; header_row, cells;
           columns and limit folded), rows written into a sheet (insert below by the header's names, or
           truncate: the sheet replaced), the other sheets kept, the file replaced safely; sheet_value
           (text never a formula, long numbers and early dates exact); source_from takes a workbook's path
           or bytes
  1.5.0    a plan's values keep their type through JSON: Plan.to_json(typed=True) says a date, a date and
           time, a time or a decimal as {"sab_type", "value"} (typed_value), plan_from gives the same type
           (untyped); Remote's read sends its plan so (a date filter is a date on the sandbox's side); Sql's
           read binds its plan's values as the driver takes them (Sql.value: SQLite's a date as its text)
  1.6.0    write_all(source, writes) and Connection.write_all: several writes on one source in one
           transaction, all of them or none, each one's counts (Write; OneWrite; a source's own write_all:
           DuckDB's, Sql's (SQL Server's run whole again on a passing error), Remote's through the door's
           write_all); Trino, Dataverse's Web API, Rows, Files and Excel refuse two or more in one sentence
  1.7.0    Connection.planned(table, rows, key, mode): a write's dry run through the connection object, as
           planned() is (rows as write takes them; a key as one name or several)
  1.8.0    a plan groups by a date's period (Plan.periods: Period(column, unit, name), PERIODS: year, quarter,
           month, week from Monday, day; the period's first day as a date), part of the plan's group: folded
           into DuckDB's and each dialect's own SQL (period_sql; no % but SQLite's), a SQL answer's periods
           made dates (dated); OData and Rows read only the columns a plan with totals needs (Plan.needed)
           and DuckDB groups them over the stream; to_json says periods only when there are some; OData's
           $orderby built only when sent (a sort by a total's name failed)
  1.9.0    a filter's op "contains": its text in any case, taken literally (no wildcard): DuckDB's
           contains(lower(...), lower(?)); each dialect's LOWER(column) LIKE ? ESCAPE '!' with the text
           escaped (contains_pattern; SQL Server's [ too); Dataverse's contains(field,'text') (its strings
           compared in any case), a text with one of its wildcards left to DuckDB; Rows' by DuckDB
  1.9.1    a period in DuckDB groups a date column as it is (no cast first: 59 ms, not 96, on 3.3M rows),
           a column held as text read as a date and time first (plan_sql's texts: DuckDB's own table's
           VARCHAR columns, a stream's string ones)
  1.9.2    sheet_value agrees with sab_excel.cell_value on every value (tests/test_cell_value_copies.py holds
           the two copies equal): numpy's scalars as their Python values (a numpy whole number was written
           as text), pandas' missing time a blank cell, a number that is not one as its plain word (nan)
  1.10.0   a connection's client may say what it is: its `sab_source` (SAB_SOURCES: odata, lake, list, rows)
           is read by source_from and Rows.write before its methods are looked at; a client that says
           nothing (an older saved connection's) is told by its methods as before
"""

from __future__ import annotations

import contextlib
import datetime as dt
import decimal
import hashlib
import http.client
import itertools
import json
import re
import time
import urllib.parse
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

import duckdb
import pyarrow as pa
import pyarrow.ipc as ipc

VERSION = "1.10.0"  # the docstring's change list says what each version added

BATCH_ROWS = 50_000  # rows in each record batch a read streams
OPS = ("=", "!=", "<", "<=", ">", ">=", "in", "between", "like", "is null", "is not null", "contains")
TOTALS = ("count", "count_distinct", "sum", "avg", "min", "max")
PERIODS = (
    "year",
    "quarter",
    "month",
    "week",
    "day",
)  # a date's periods a plan groups by (a week from Monday)
MODES = ("insert", "update", "merge", "delete", "truncate")
KEYED = ("update", "merge", "delete")  # the modes that match rows by a key
PARTS = ("filters", "group", "totals", "columns", "sort", "offset", "limit")  # in the order SQL applies them
ROWS = "rows"  # what a table's SQL calls its read: SELECT region, sum(amount) FROM rows GROUP BY 1


class AdapterError(ValueError):
    """A plan, a table or a write the source cannot take, said in one sentence."""


@dataclass(frozen=True)
class Batch:
    """Which batch of a SQL write the source refused (the write rolled back): its number, the rows before
    it, its size. The source's own error is raised as it was, this beside it as `error.sab_batch` and in
    its notes, so a caller catching the driver's error still does."""

    number: int
    before: int
    size: int

    def where(self) -> str:
        return f"batch {self.number} (rows {self.before + 1:,} to {self.before + self.size:,})"


def batch_of(error: BaseException) -> Batch | None:
    """The batch a SQL write's error came from (None: not from one)."""
    found = getattr(error, "sab_batch", None)
    return found if isinstance(found, Batch) else None


# ===== 1. The plan =====


@dataclass(frozen=True)
class Filter:
    """One condition: column op value (`in` takes a list, `between` two values, `is null` none, `contains`
    text, matched in any case)."""

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
class Period:
    """A group by a date's period: its column's year, quarter, month, week (from Monday) or day, answered as
    the period's first day (a date)."""

    column: str
    unit: str = "month"
    name: str = ""  # its column in the answer; column_unit by default

    @property
    def label(self) -> str:
        return self.name or f"{self.column}_{self.unit}"


@dataclass(frozen=True)
class Plan:
    """What a read asks for. Applied as SQL is: filters, then group and totals (or the columns), then sort,
    offset and limit. With totals, the answer is the periods' and the group's columns and the totals; with
    none, the columns (every column when none are named). A period is part of the group."""

    columns: tuple[str, ...] = ()
    filters: tuple[Filter, ...] = ()
    sort: tuple[tuple[str, bool], ...] = ()  # (column, descending)
    limit: int | None = None
    offset: int = 0
    group: tuple[str, ...] = ()
    totals: tuple[Total, ...] = ()
    periods: tuple[Period, ...] = ()  # grouped by first, before the group's columns

    def parts(self) -> tuple[str, ...]:
        """The parts this plan asks for."""
        asked = {
            "columns": bool(self.columns),
            "filters": bool(self.filters),
            "group": bool(self.group or self.periods),
            "totals": bool(self.totals),
            "sort": bool(self.sort),
            "offset": bool(self.offset),
            "limit": self.limit is not None,
        }
        return tuple(p for p in PARTS if asked[p])

    def to_json(self, typed: bool = False) -> dict[str, Any]:
        """The plan as JSON (its filters as [column, op, value], its sort as [column, "asc" | "desc"]).
        `typed`: a date, a date and time, a time or a decimal as {"sab_type", "value"} (typed_value), so
        plan_from on the far side gives back the same type; else each value as it is."""
        said = typed_value if typed else _as_is
        made = {
            "columns": list(self.columns),
            "filters": [[f.column, f.op, said(f.value)] for f in self.filters],
            "sort": [[c, "desc" if d else "asc"] for c, d in self.sort],
            "limit": self.limit,
            "offset": self.offset,
            "group": list(self.group),
            "totals": [{"fn": t.fn, "column": t.column, "name": t.name} for t in self.totals],
        }
        if self.periods:  # said only when there are some: a plan without one says what it always did
            made["periods"] = [{"column": p.column, "unit": p.unit, "name": p.name} for p in self.periods]
        return made

    def needed(self) -> tuple[str, ...]:
        """The table's columns the plan names (the columns, filters, periods, group, totals and sort), once
        each: what a source that cannot group reads for DuckDB to do the rest."""
        labels = {t.label.casefold() for t in self.totals} | {p.label.casefold() for p in self.periods}
        named = [*self.columns, *(f.column for f in self.filters), *(p.column for p in self.periods)]
        named += [*self.group, *(t.column for t in self.totals if t.column)]
        named += [c for c, _ in self.sort if c.casefold() not in labels]
        return tuple(dict.fromkeys(named))


def plan_from(raw: Mapping[str, Any] | None) -> Plan:
    """A plan from its JSON (Plan.to_json's shape), checked: a wrong op, total or number said plainly."""
    given = dict(raw or {})
    filters = []
    for item in given.get("filters") or []:
        if not isinstance(item, (list, tuple)) or len(item) not in (2, 3):
            raise AdapterError("A filter is [column, op, value].")
        value = untyped(item[2]) if len(item) == 3 else None
        filters.append(Filter(str(item[0]), str(item[1]).lower(), value))
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
        periods=tuple(
            Period(
                str(p.get("column") or ""), str(p.get("unit") or "month").lower(), str(p.get("name") or "")
            )
            for p in given.get("periods") or []
            if isinstance(p, Mapping)
        ),
    )
    check_plan(plan)
    return plan


TYPED = ("date", "timestamp", "time", "decimal")  # what a value's sab_type may say


def _as_is(value: Any) -> Any:
    return value


def typed_value(value: Any) -> Any:
    """A value as JSON carries it with its type: a date, a date and time (its zone kept), a time or a decimal
    as {"sab_type": "date", "value": "2026-01-15"}; a list item by item; anything else as it is."""
    if isinstance(value, list | tuple):
        return [typed_value(v) for v in value]
    if isinstance(value, dt.datetime):
        return {"sab_type": "timestamp", "value": value.isoformat()}
    if isinstance(value, dt.date):
        return {"sab_type": "date", "value": value.isoformat()}
    if isinstance(value, dt.time):
        return {"sab_type": "time", "value": value.isoformat()}
    if isinstance(value, decimal.Decimal):
        return {"sab_type": "decimal", "value": str(value)}
    return value


def untyped(value: Any) -> Any:
    """typed_value's value back as its own type (a list item by item); anything else as it is."""
    if isinstance(value, list | tuple):
        return [untyped(v) for v in value]
    if not (isinstance(value, Mapping) and set(value) == {"sab_type", "value"}):
        return value
    kind, text = str(value["sab_type"]), str(value["value"])
    read = {"date": dt.date.fromisoformat, "timestamp": dt.datetime.fromisoformat,
            "time": dt.time.fromisoformat, "decimal": decimal.Decimal}.get(kind)  # fmt: skip
    if read is None:
        raise AdapterError(f"A value's sab_type is one of {', '.join(TYPED)}, not {kind!r}.")
    try:
        return read(text)
    except (ValueError, ArithmeticError):
        said = {"timestamp": "a date and time", "decimal": "a decimal"}.get(kind, f"a {kind}")
        raise AdapterError(f"{text!r} is not {said}.") from None


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
        if f.op == "contains" and not isinstance(f.value, str):
            raise AdapterError(f"The filter on {f.column} with contains takes text.")
    for t in plan.totals:
        if t.fn not in TOTALS:
            raise AdapterError(f"A total is one of {', '.join(TOTALS)}, not {t.fn!r}.")
        if t.fn != "count" and not t.column:
            raise AdapterError(f"A {t.fn} total names its column.")
    for p in plan.periods:
        if p.unit not in PERIODS:
            raise AdapterError(f"A period is one of {', '.join(PERIODS)}, not {p.unit!r}.")
        if not p.column:
            raise AdapterError("A period names its date column.")
    if (plan.group or plan.periods) and not plan.totals:
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
            periods=() if "group" in done else plan.periods,
        )


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # the source's type name (DuckDB's for a DuckDB source)
    key: bool = False  # part of the table's primary key
    nullable: bool | None = field(default=None, compare=False)  # None: not said
    description: str = field(
        default="", compare=False
    )  # the listing's words (SQL Server's: Primary key. ...)
    position: int | None = field(default=None, compare=False)  # its ordinal as the listing says


@dataclass(frozen=True)
class Table:
    name: str  # the source's own name for it: what read and write take
    columns: tuple[Column, ...] = ()
    # where it is and what it is, as its catalog says (a listing's own words): kept apart from the name
    schema: str = field(default="", compare=False)
    kind: str = field(default="", compare=False)  # BASE TABLE, VIEW ...
    database: str = field(default="", compare=False)
    description: str = field(default="", compare=False)  # the listing's words (SQL Server's: 1,204 rows ...)


def catalog_rows(listed: Sequence[Table]) -> tuple[list[str], list[list[Any]]]:
    """Tables as a catalog's rows, in the columns an information_schema listing has (table_catalog only when
    one is said; description when one is): the app's Catalog reads them as it reads a connection's own List
    the tables. A table's own description is its row with no column (ordinal 0), as SQL Server's listing
    has."""
    with_database = any(t.database for t in listed)
    described = any(t.description or any(c.description for c in t.columns) for t in listed)
    names = ["table_schema", "table_name", "table_type", "column_name", "data_type", "is_nullable",
             "ordinal_position"]  # fmt: skip
    rows: list[list[Any]] = []
    for t in listed:
        bare = t.name.rpartition(".")[2] if t.schema and t.name.startswith(t.schema + ".") else t.name
        lines: list[tuple[list[Any], str]] = []
        if t.description:
            lines.append(([t.schema, bare, t.kind or None, "", "", "YES", 0], t.description))
        for at, c in enumerate(t.columns, 1):
            nullable = None if c.nullable is None else ("YES" if c.nullable else "NO")
            place = c.position if c.position is not None else at
            lines.append(([t.schema, bare, t.kind or None, c.name, c.type, nullable, place], c.description))
        for row, words in lines:
            full = [t.database, *row] if with_database else row
            rows.append([*full, words or None] if described else full)
    heading = ["table_catalog", *names] if with_database else names
    return ([*heading, "description"] if described else heading), rows


@dataclass(frozen=True)
class Counts:
    """A write's rows each way; `notes`: what the source says beside them (a passing error run again, MERGE
    refused and done in two statements, Trino's writes without a transaction)."""

    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    notes: tuple[str, ...] = ()

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

    # and, for a source that speaks SQL: query(self, sql: str, params: Sequence[Any]) -> pa.RecordBatchReader
    # and, with a transaction across writes: write_all(self, writes: Sequence[OneWrite]) -> list[Counts]


# What a connection's own client may say it is (its class's `sab_source`), read before its methods are looked
# at (source_from, Rows.write). Each word names the calls the adapter then makes on it:
#   odata  Dataverse's Web API (OData): catalog(), described(table), rows(table, columns, filter, order_by,
#          limit) -> (records, total), and its writes' calls (_Dataverse)
#   lake   a lake (Rows): catalog(), rows(table, schema, limit, columns, filters), write_delta(path, rows,
#          mode, keys), delete_delta, write_file
#   list   a SharePoint list (Rows): catalog(), rows(...), create(table, rows), update, delete, and
#          ids(table, values)
#   rows   any other client that reads a table itself (Rows: catalog(), rows(...)); it takes no writes
# A client that says nothing, or a word this version does not know, is told by which of those calls it has.
SAB_SOURCES = ("odata", "lake", "list", "rows")


def said_source(client: Any) -> str:
    """The word a client says it is (its `sab_source`, one of SAB_SOURCES), or "" when it says none."""
    word = getattr(client, "sab_source", None)
    return word if isinstance(word, str) and word in SAB_SOURCES else ""


# one of write_all's writes: (table, batches, key, mode)
OneWrite = tuple[str, pa.RecordBatchReader, Sequence[str], str]

READS = ("SELECT", "WITH", "FROM", "VALUES", "TABLE", "SHOW", "DESCRIBE", "SUMMARIZE", "EXPLAIN", "PRAGMA")
COUNT = "count"  # the one column a statement that returns no rows answers: the rows it changed


Params = Sequence[Any] | Mapping[str, Any]  # a query's values: by place (its marks), or by name


def _given(params: Params) -> Any:
    return {str(k): v for k, v in params.items()} if isinstance(params, Mapping) else list(params)


def reads_only(sql: str) -> bool:
    """Whether a statement only reads (its first word; a comment before it skipped)."""
    text = re.sub(r"^(\s|--[^\n]*\n|/\*.*?\*/)+", "", str(sql), flags=re.S)
    head = text.split(None, 1)[0].upper().strip("(") if text.strip() else ""
    return head in READS


def counted(rows: int) -> pa.RecordBatchReader:
    """A statement that returned no rows, answered as one row of its `count`."""
    return pa.table({COUNT: pa.array([max(int(rows), 0)], pa.int64())}).to_reader()


def quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def plan_sql(relation: str, plan: Plan, texts: Sequence[str] = ()) -> tuple[str, list[Any]]:
    """The plan as one DuckDB query over `relation` (a quoted name, or a subquery in brackets), its values
    bound as parameters. `texts`: the columns held as text, a period of one read as a date and time first
    (a date column is grouped as it is: no cast, the fastest)."""
    check_plan(plan)
    params: list[Any] = []
    wheres = [_condition(f, params) for f in plan.filters]
    held = {t.casefold() for t in texts}
    grouped = [
        period_sql("duckdb", p.unit, f"CAST({quote(p.column)} AS TIMESTAMP)")
        if p.column.casefold() in held
        else period_sql("duckdb", p.unit, quote(p.column))
        for p in plan.periods
    ]
    grouped += [quote(c) for c in plan.group]
    if plan.totals:
        labels = [quote(p.label) for p in plan.periods] + [quote(c) for c in plan.group]
        picked = [g if g == n else f"{g} AS {n}" for g, n in zip(grouped, labels, strict=True)]
        picked += [_total(t) for t in plan.totals]
    else:
        picked = [quote(c) for c in plan.columns] or ["*"]
    sql = f"SELECT {', '.join(picked)} FROM {relation}"  # noqa: S608 (names quoted, values bound)
    if wheres:
        sql += " WHERE " + " AND ".join(wheres)
    if grouped:
        sql += " GROUP BY " + ", ".join(grouped)
    if plan.sort:
        sql += " ORDER BY " + ", ".join(f"{quote(c)} {'DESC' if d else 'ASC'}" for c, d in plan.sort)
    if plan.limit is not None:
        sql += f" LIMIT {int(plan.limit)}"
    if plan.offset:
        sql += f" OFFSET {int(plan.offset)}"
    return sql, params


_ORACLE_UNITS = {
    "year": "YYYY",
    "quarter": "Q",
    "month": "MM",
    "week": "IW",
    "day": "DD",
}  # TRUNC's (IW: Monday)


def period_sql(dialect: str, unit: str, column: str) -> str:
    """A date's period's first day as a date, in one database's SQL (`column` already quoted): DuckDB's and
    PostgreSQL's, Snowflake's, Trino's and Databricks' DATE_TRUNC; SQL Server's DATEFROMPARTS (every version,
    a week from Monday whatever its DATEFIRST); MySQL's and SQLite's date functions; Oracle's TRUNC. No % in
    the text but SQLite's (its driver's marks are ?, a pyformat driver's %s would misread one)."""
    if dialect in ("duckdb", "postgres", "snowflake", "trino", "databricks"):
        return f"CAST(DATE_TRUNC('{unit}', {column}) AS DATE)"  # a date or a date and time as it is
    if dialect == "sqlserver":
        weekday = f"(DATEPART(weekday, {column}) + @@DATEFIRST - 2)"  # 0 on a Monday, +7 at most
        return {
            "year": f"DATEFROMPARTS(YEAR({column}), 1, 1)",
            "quarter": f"DATEFROMPARTS(YEAR({column}), (DATEPART(quarter, {column}) - 1) * 3 + 1, 1)",
            "month": f"DATEFROMPARTS(YEAR({column}), MONTH({column}), 1)",
            "week": f"DATEADD(day, -({weekday} - 7 * ({weekday} / 7)), CAST({column} AS DATE))",
            "day": f"CAST({column} AS DATE)",
        }[unit]
    if dialect == "mysql":
        return {
            "year": f"MAKEDATE(YEAR({column}), 1)",
            "quarter": f"(MAKEDATE(YEAR({column}), 1) + INTERVAL (QUARTER({column}) - 1) QUARTER)",
            "month": f"DATE_SUB(DATE({column}), INTERVAL (DAYOFMONTH({column}) - 1) DAY)",
            "week": f"DATE_SUB(DATE({column}), INTERVAL WEEKDAY({column}) DAY)",
            "day": f"DATE({column})",
        }[unit]
    if dialect == "oracle":
        return f"TRUNC({column}, '{_ORACLE_UNITS[unit]}')"
    if dialect == "sqlite":
        return {
            "year": f"date({column}, 'start of year')",
            "quarter": f"date({column}, 'start of month', '-' || ((CAST(strftime('%m', {column}) AS INTEGER)"
            " - 1) % 3) || ' months')",
            "month": f"date({column}, 'start of month')",
            "week": f"date({column}, '-' || ((CAST(strftime('%w', {column}) AS INTEGER) + 6) % 7)"
            " || ' days')",
            "day": f"date({column})",
        }[unit]
    raise AdapterError(f"{dialect} has no period of its own here: read the dates and group them in DuckDB.")


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
    if f.op == "contains":  # in any case, the text taken literally (no wildcard)
        return f"contains(lower(CAST({name} AS VARCHAR)), lower(?))"
    return f"{name} {'<>' if f.op == '!=' else f.op} ?"


def contains_pattern(text: str, dialect: str = "") -> str:
    """contains' text as a LIKE pattern for LOWER(column) LIKE ? ESCAPE '!': lowered, its own %, _ and ! (and,
    in SQL Server's, [) escaped with !, so they are matched as themselves; wrapped in %."""
    said = str(text).lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return "%" + (said.replace("[", "![") if dialect == "sqlserver" else said) + "%"


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
    def session(cls, connection: Any, name: str = "DuckDB") -> DuckDB:
        """A connection used as it is (its views and registered tables seen, never closed here): the app's
        engine session, a query's own cursor."""

        @contextlib.contextmanager
        def same(writing: bool) -> Iterator[Any]:
            yield connection

        return cls(same, name)

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
            database = str(con.sql("SELECT current_database()").fetchall()[0][0])
            return [
                Table(name, tuple(Column(*c) for c in _columns(con, schema, table)), schema, kind, database)
                for name, schema, table, kind in _relations(con)
            ]

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, Folded]:
        return _stream(self._connect, self._query, table, plan), Folded(plan.parts())

    def _query(self, con: Any, table: str, plan: Plan) -> tuple[str, list[Any]]:
        schema, name = self._place(con, table)
        columns = _columns(con, schema, name)
        known = {c[0].casefold() for c in columns}
        for column in plan.needed():
            if column.casefold() not in known:
                raise AdapterError(f"{table} has no column {column!r}.")
        texts = [c[0] for c in columns if c[1] == "VARCHAR"] if plan.periods else []
        return plan_sql(f"{quote(schema)}.{quote(name)}", plan, texts)

    def _place(self, con: Any, table: str) -> tuple[str, str]:
        wanted = str(table).casefold()
        for listed, schema, name, _ in _relations(con):
            if listed.casefold() == wanted:
                return schema, name
        raise AdapterError(f"{self.name} has no table {table!r}.")

    def write(self, table: str, batches: pa.RecordBatchReader, key: Sequence[str], mode: str) -> Counts:
        return self.write_all([(table, batches, key, mode)])[0]

    def write_all(self, writes: Sequence[OneWrite]) -> list[Counts]:
        """Each (table, batches, key, mode) in turn on one connection, in one transaction: all or none."""
        for _, _, key, mode in writes:
            _checked_write(mode, key)
        with self._connect(True) as con:
            places = [self._place(con, table) for table, _, _, _ in writes]
            con.execute("BEGIN TRANSACTION")
            done: list[Counts] = []
            try:
                for (schema, name), (_, batches, key, mode) in zip(places, writes, strict=True):
                    names = [str(n) for n in batches.schema.names]
                    if names:  # a truncate with no rows has no columns to register
                        con.register("sab_incoming", batches)
                    done.append(_written(con, f"{quote(schema)}.{quote(name)}", names, list(key), mode))
                    if names:
                        con.unregister("sab_incoming")
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                with contextlib.suppress(Exception):  # after the rollback: an aborted one refuses it
                    con.unregister("sab_incoming")
                raise
            return done

    def query(self, sql: str, params: Params = ()) -> pa.RecordBatchReader:
        """DuckDB's own SQL: a read streamed as it is made; a write run at once in its own transaction,
        answering its RETURNING rows, else its count."""
        if reads_only(sql):

            def run(con: Any, _table: str, _plan: Plan) -> tuple[str, Any]:
                return sql, _given(params)

            return _stream(self._connect, run, "", Plan())
        with self._connect(True) as con:
            found = con.sql(sql, params=_given(params))
            if found is None:
                return counted(0)
            made = found.to_arrow_table()
        if made.column_names == ["Count"]:
            return counted(int(made.column(0)[0].as_py() or 0) if made.num_rows else 0)
        return made.to_reader()


def _relations(con: Any) -> list[tuple[str, str, str, str]]:
    """Each table and view of the database: its listed name (table, or schema.table outside main), schema,
    name, kind (BASE TABLE or VIEW, as information_schema says)."""
    rows = con.sql(
        "SELECT schema_name, table_name, 'BASE TABLE' FROM duckdb_tables() "
        "WHERE database_name = current_database() AND NOT internal UNION ALL "
        "SELECT schema_name, view_name, 'VIEW' FROM duckdb_views() "
        "WHERE database_name = current_database() AND NOT internal ORDER BY 1, 2"
    ).fetchall()
    return [(t if s == "main" else f"{s}.{t}", s, t, k) for s, t, k in rows]


def _columns(con: Any, schema: str, table: str) -> list[tuple[str, str, bool, bool]]:
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
        "SELECT column_name, data_type, is_nullable FROM duckdb_columns() "
        "WHERE database_name = current_database() AND schema_name = ? AND table_name = ? "
        "ORDER BY column_index",
        params=[schema, table],
    ).fetchall()
    return [(str(n), str(t), str(n) in keys, bool(nullable)) for n, t, nullable in rows]


def _stream(
    connect: Connect, query: Callable[[Any, str, Plan], tuple[str, Any]], table: str, plan: Plan
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
    """A source through the app's data door, its reads and writes as Arrow IPC streams: the project's sandbox
    (a local sandbox API's process has no file and no connection of its own; `connection` names whose tables
    these are, a sandbox table mocked as it), or a kernel's open tables (`headers` the token). Each folds the
    whole plan."""

    def __init__(
        self, url: str, connection: str = "Sandbox", headers: Mapping[str, str] | None = None
    ) -> None:
        self.url = url.rstrip("/")
        self.connection = connection
        self.headers = dict(headers or {})  # the app's token, for a kernel reading the open tables

    def tables(self) -> list[Table]:
        answer = json.loads(
            self._post("/tables", json.dumps({"connection": self.connection}).encode()).read()
        )
        return [
            Table(t["name"], tuple(Column(c["name"], c["type"], bool(c.get("key"))) for c in t["columns"]))
            for t in answer["tables"]
        ]

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, Folded]:
        body = json.dumps(
            {"connection": self.connection, "table": table, "plan": plan.to_json(typed=True)}
        ).encode()  # each value with its type: a date filter is a date on the far side (plan_from)
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

    def write_all(self, writes: Sequence[OneWrite]) -> list[Counts]:
        """Several writes in one request, applied in one transaction on the far side: a JSON line naming each
        ({"connection", "writes": [{"table", "key", "mode", "bytes"}]}), then each one's Arrow IPC stream."""
        streams, said = [], []
        for table, batches, key, mode in writes:
            sink = pa.BufferOutputStream()
            with ipc.new_stream(sink, batches.schema) as stream:
                for batch in batches:
                    stream.write_batch(batch)
            streams.append(sink.getvalue().to_pybytes())
            said.append({"table": table, "key": list(key), "mode": mode, "bytes": len(streams[-1])})
        head = json.dumps({"connection": self.connection, "writes": said}).encode() + b"\n"
        answer = json.loads(self._post("/write_all", head + b"".join(streams)).read())
        return [Counts(int(a["inserted"]), int(a["updated"]), int(a["deleted"])) for a in answer["counts"]]

    def query(self, sql: str, params: Params = ()) -> pa.RecordBatchReader:
        """The source's own SQL, answered as Arrow (the sandbox makes it DuckDB SQL over its tables)."""
        body = json.dumps(
            {"connection": self.connection, "sql": sql, "params": _given(params)}, default=_json_value
        ).encode()
        answer = self._post("/query", body)
        reader = ipc.open_stream(answer)
        return pa.RecordBatchReader.from_batches(reader.schema, _closing(reader, answer))

    def _post(self, path: str, body: bytes) -> http.client.HTTPResponse:
        parts = urllib.parse.urlsplit(self.url + path)
        connection = http.client.HTTPConnection(parts.hostname or "127.0.0.1", parts.port or 80, timeout=600)
        target = parts.path + (f"?{parts.query}" if parts.query else "")
        connection.request("POST", target, body, {"Content-Type": "application/octet-stream", **self.headers})
        answer = connection.getresponse()
        if answer.status >= 400:
            raw = answer.read()
            connection.close()
            try:
                said = str(json.loads(raw or b"{}").get("error") or answer.reason)
            except ValueError:
                said = answer.reason
            raise AdapterError(sql_line(said))
        return answer


def sql_line(said: str) -> str:
    """A refusal that starts with its SQL's own line ("Line 3: ..."), said without a second "Line" (the
    endpoint's own line is the caller's): the first line of the SQL goes unsaid, a later one is "(line 3 of
    its SQL)"."""
    found = re.match(r"Line (\d+): (.*)$", said, re.S)
    if not found:
        return said
    rest = found.group(2)
    rest = rest[:1].upper() + rest[1:]
    return rest if found.group(1) == "1" else f"{rest.rstrip()} (line {found.group(1)} of its SQL)"


def _closing(reader: Any, answer: Any) -> Iterator[pa.RecordBatch]:
    try:
        yield from reader
    finally:
        answer.close()


# ----- SQL databases: any DB-API connection, its dialect's rules as data -----

_INFO_COLUMNS = (
    "SELECT c.table_schema, c.table_name, c.column_name, c.data_type, t.table_type, c.is_nullable, "
    "c.table_catalog FROM information_schema.columns c JOIN information_schema.tables t "
    "ON t.table_catalog = c.table_catalog AND t.table_schema = c.table_schema "
    "AND t.table_name = c.table_name "
    "WHERE c.table_schema NOT IN ('information_schema', 'pg_catalog', 'INFORMATION_SCHEMA', 'sys') {where}"
    "ORDER BY c.table_schema, c.table_name, c.ordinal_position"
)
_INFO_KEYS = (
    "SELECT k.table_schema, k.table_name, k.column_name FROM information_schema.table_constraints t "
    "JOIN information_schema.key_column_usage k ON k.constraint_name = t.constraint_name "
    "AND k.table_schema = t.table_schema AND k.table_name = t.table_name "
    "WHERE t.constraint_type = 'PRIMARY KEY'"
)


# Each database's whole listing as its Connections starter lists it (every schema but the system's; SQL
# Server's descriptions: a column's Primary key., Identity. ..., a table's rows), and the shape of its rows:
# what `listed()` runs for the app's Catalog. tables() keeps each dialect's own scope (the columns query).
_LISTED = ("database", "schema", "table", "kind", "column", "type", "nullable", "position")
_INFO_LISTING = """SELECT c.table_catalog, c.table_schema, c.table_name, t.table_type,
       c.column_name, c.data_type, c.is_nullable, c.ordinal_position
FROM information_schema.columns AS c
JOIN information_schema.tables AS t
  ON t.table_catalog = c.table_catalog
 AND t.table_schema = c.table_schema
 AND t.table_name = c.table_name
WHERE c.table_schema NOT IN ('information_schema', 'INFORMATION_SCHEMA', 'pg_catalog', 'sys')
ORDER BY c.table_schema, c.table_name, c.ordinal_position"""
_MYSQL_LISTING = """SELECT c.table_catalog, c.table_schema, c.table_name, t.table_type,
       c.column_name, c.data_type, c.is_nullable, c.ordinal_position
FROM information_schema.columns AS c
JOIN information_schema.tables AS t
  ON t.table_catalog = c.table_catalog
 AND t.table_schema = c.table_schema
 AND t.table_name = c.table_name
WHERE c.table_schema NOT IN ('information_schema', 'INFORMATION_SCHEMA', 'mysql', 'performance_schema', 'sys')
ORDER BY c.table_schema, c.table_name, c.ordinal_position"""
_ORACLE_LISTING = """SELECT c.owner, c.table_name, o.object_type AS table_type, c.column_name, c.data_type,
       c.nullable, c.column_id
FROM all_tab_columns c
JOIN all_objects o ON o.owner = c.owner AND o.object_name = c.table_name
                  AND o.object_type IN ('TABLE', 'VIEW')
WHERE c.owner NOT IN ('SYS', 'SYSTEM', 'XDB', 'MDSYS', 'CTXSYS', 'ORDSYS', 'OUTLN', 'DBSNMP',
                      'APEX_PUBLIC_USER')
ORDER BY c.owner, c.table_name, c.column_id"""
_SQLSERVER_LISTING = """SELECT DB_NAME() AS table_catalog, s.name AS table_schema, o.name AS table_name,
       CASE o.type WHEN 'V' THEN 'VIEW' WHEN 'SN' THEN 'VIEW' ELSE 'BASE TABLE' END AS table_type,
       c.name AS column_name,
       CASE
         WHEN t.name IN ('varchar', 'char', 'varbinary', 'binary')
           THEN t.name + '('
             + CASE c.max_length WHEN -1 THEN 'max' ELSE CAST(c.max_length AS varchar(5)) END + ')'
         WHEN t.name IN ('nvarchar', 'nchar')
           THEN t.name + '('
             + CASE c.max_length WHEN -1 THEN 'max' ELSE CAST(c.max_length / 2 AS varchar(5)) END + ')'
         WHEN t.name IN ('decimal', 'numeric')
           THEN t.name + '(' + CAST(c.precision AS varchar(3)) + ',' + CAST(c.scale AS varchar(3)) + ')'
         WHEN t.name IN ('datetime2', 'datetimeoffset', 'time')
           THEN t.name + '(' + CAST(c.scale AS varchar(3)) + ')'
         ELSE t.name
       END AS data_type,
       CASE c.is_nullable WHEN 1 THEN 'YES' ELSE 'NO' END AS is_nullable,
       c.column_id AS ordinal_position,
       NULLIF(LTRIM(CONCAT(
         CASE WHEN pk.column_id IS NOT NULL THEN ' Primary key.' END,
         CASE WHEN c.is_identity = 1 THEN ' Identity.' END,
         CASE WHEN c.is_computed = 1 THEN ' Computed.' END,
         CASE WHEN c.is_sparse = 1 THEN ' Sparse.' END,
         CASE WHEN c.generated_always_type > 0 THEN ' Period column.' END,
         ' ' + CAST(ep.value AS nvarchar(4000)))), '') AS description
FROM sys.objects AS o
JOIN sys.schemas AS s ON s.schema_id = o.schema_id
LEFT JOIN sys.synonyms AS sn ON sn.object_id = o.object_id
JOIN sys.columns AS c ON c.object_id = CASE
  WHEN sn.object_id IS NULL THEN o.object_id
  WHEN COALESCE(PARSENAME(sn.base_object_name, 3), DB_NAME()) = DB_NAME() THEN OBJECT_ID(sn.base_object_name)
END  -- a synonym: its object's columns, when the object is in this database
JOIN sys.types AS t ON t.user_type_id = c.user_type_id
LEFT JOIN (
  SELECT ic.object_id, ic.column_id FROM sys.indexes AS i
  JOIN sys.index_columns AS ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
  WHERE i.is_primary_key = 1
) AS pk ON pk.object_id = c.object_id AND pk.column_id = c.column_id
LEFT JOIN sys.extended_properties AS ep
  ON ep.class = 1 AND ep.major_id = c.object_id AND ep.minor_id = c.column_id AND ep.name = 'MS_Description'
WHERE o.type IN ('U', 'V', 'SN') AND o.is_ms_shipped = 0
UNION ALL
SELECT DB_NAME(), s.name, o.name, CASE o.type WHEN 'V' THEN 'VIEW' ELSE 'BASE TABLE' END, '', '', 'YES', 0,
       NULLIF(STUFF(CONCAT(
         CASE WHEN o.type = 'U' THEN N' · ' + FORMAT(COALESCE(r.n, 0), 'N0') + N' rows' END,
         CASE WHEN tb.temporal_type = 2 THEN N' · temporal (history: ' + hs.name + N'.' + h.name + N')' END,
         CASE WHEN tb.temporal_type = 1 THEN N' · history table' END,
         N' · ' + CAST(ep.value AS nvarchar(4000))), 1, 3, N''), N'')
FROM sys.objects AS o
JOIN sys.schemas AS s ON s.schema_id = o.schema_id
LEFT JOIN sys.tables AS tb ON tb.object_id = o.object_id
LEFT JOIN sys.tables AS h ON h.object_id = tb.history_table_id
LEFT JOIN sys.schemas AS hs ON hs.schema_id = h.schema_id
LEFT JOIN (
  SELECT object_id, SUM(rows) AS n FROM sys.partitions WHERE index_id IN (0, 1) GROUP BY object_id
) AS r ON r.object_id = o.object_id
LEFT JOIN sys.extended_properties AS ep
  ON ep.class = 1 AND ep.major_id = o.object_id AND ep.minor_id = 0 AND ep.name = 'MS_Description'
WHERE o.type IN ('U', 'V') AND o.is_ms_shipped = 0
ORDER BY 2, 3, 8"""


@dataclass(frozen=True)
class Dialect:
    """What one database's SQL needs for a plan and a write: how it quotes a name, how it says a limit and
    an offset (`limit`: LIMIT n OFFSET m; `offset_limit`: OFFSET m LIMIT n; `fetch`: OFFSET m ROWS FETCH
    NEXT n ROWS ONLY, T-SQL's wanting an ORDER BY), its catalog (rows of schema, table, column, type) and
    primary keys (schema, table, column), the schema a bare name is in, whether a write is one transaction."""

    name: str
    quotes: str = '""'
    limit: str = "limit"
    columns: str = _INFO_COLUMNS.format(where="")
    keys: str = _INFO_KEYS
    default_schema: tuple[str, ...] = ()  # listed without its schema (public, dbo, main)
    transactional: bool = True
    order_needed: bool = False  # an OFFSET needs an ORDER BY (T-SQL)
    no_limit: str = ""  # what LIMIT says for "every row" before an OFFSET (MySQL's, SQLite's)
    listing: str = ""  # its starter's whole listing (listed()); "": its tables() are its listing
    listing_shape: tuple[str, ...] = _LISTED  # what each of the listing's columns is, in order
    drains: bool = False  # a statement runs as its answer is read (Trino): every write's answer fetched

    def quote(self, name: str) -> str:
        opening, closing = self.quotes[0], self.quotes[1]
        return opening + str(name).replace(closing, closing * 2) + closing


DIALECTS: dict[str, Dialect] = {
    "postgres": Dialect("postgres", default_schema=("public",)),
    "mysql": Dialect(
        "mysql", "``", columns=_INFO_COLUMNS.format(where="AND c.table_schema = DATABASE() "),
        default_schema=("*",), no_limit="18446744073709551615", listing=_MYSQL_LISTING,
    ),
    "sqlserver": Dialect(
        "sqlserver", "[]", "fetch", columns=_INFO_COLUMNS.format(where=""), default_schema=("dbo",),
        order_needed=True, listing=_SQLSERVER_LISTING, listing_shape=(*_LISTED, "description"),
    ),
    "oracle": Dialect(
        "oracle", limit="fetch",
        columns="SELECT owner, table_name, column_name, data_type FROM all_tab_columns WHERE owner = USER "
        "ORDER BY owner, table_name, column_id",
        keys="SELECT c.owner, c.table_name, c.column_name FROM all_cons_columns c JOIN all_constraints k "
        "ON k.owner = c.owner AND k.constraint_name = c.constraint_name WHERE k.constraint_type = 'P' "
        "AND c.owner = USER",
        default_schema=("*",), listing=_ORACLE_LISTING, listing_shape=_LISTED[1:],
    ),
    "sqlite": Dialect(
        "sqlite",
        columns="SELECT 'main', m.name, p.name, p.type, m.type, CASE WHEN p.\"notnull\" = 1 THEN 'NO' ELSE "
        "'YES' END FROM sqlite_master m JOIN pragma_table_info(m.name) p "
        "WHERE m.type IN ('table', 'view') AND m.name NOT LIKE 'sqlite_%' ORDER BY m.name, p.cid",
        keys="SELECT 'main', m.name, p.name FROM sqlite_master m JOIN pragma_table_info(m.name) p "
        "WHERE m.type = 'table' AND p.pk > 0",
        default_schema=("main",), no_limit="-1",
    ),
    "snowflake": Dialect(
        "snowflake", columns=_INFO_COLUMNS.format(where="AND c.table_schema = CURRENT_SCHEMA() "),
        default_schema=("*",), listing=_INFO_LISTING,
    ),
    "trino": Dialect(
        "trino", limit="offset_limit", columns=_INFO_COLUMNS.format(where=""), keys="", transactional=False,
        listing=_INFO_LISTING, drains=True,
    ),
    "databricks": Dialect(
        "databricks", "``", columns=_INFO_COLUMNS.format(where="AND c.table_schema = current_schema() "),
        keys="", default_schema=("*",), listing=_INFO_LISTING,
    ),
}  # fmt: skip


def dialect_sql(dialect: Dialect, table: str, plan: Plan, style: str = "qmark") -> tuple[str, list[Any]]:
    """The plan as one query in `dialect` over `table` ("schema.table" or "table"), its values bound in the
    driver's parameter style (PEP 249's paramstyle)."""
    check_plan(plan)
    params: list[Any] = []
    q = dialect.quote

    def mark(value: Any) -> str:
        params.append(value)
        return _mark(style, len(params))

    def condition(f: Filter) -> str:
        name = q(f.column)
        if f.op in ("is null", "is not null"):
            return f"{name} {f.op.upper()}"
        if f.op == "in":
            return f"{name} IN ({', '.join(mark(v) for v in f.value)})"
        if f.op == "between":
            return f"{name} BETWEEN {mark(f.value[0])} AND {mark(f.value[1])}"
        if (
            f.op == "contains"
        ):  # in any case, its text escaped (a pyformat driver's marks keep % in the value)
            return f"LOWER({name}) LIKE {mark(contains_pattern(f.value, dialect.name))} ESCAPE '!'"
        return f"{name} {'<>' if f.op == '!=' else f.op.upper()} {mark(f.value)}"

    def total(t: Total) -> str:
        if t.fn == "count":
            what = f"COUNT({q(t.column)})" if t.column else "COUNT(*)"
        elif t.fn == "count_distinct":
            what = f"COUNT(DISTINCT {q(t.column)})"
        else:
            what = f"{t.fn.upper()}({q(t.column)})"
        return f"{what} AS {q(t.label)}"

    grouped = [period_sql(dialect.name, p.unit, q(p.column)) for p in plan.periods] + [
        q(c) for c in plan.group
    ]
    if plan.totals:
        picked = [f"{g} AS {q(p.label)}" for g, p in zip(grouped, plan.periods, strict=False)]
        picked += [q(c) for c in plan.group] + [total(t) for t in plan.totals]
    else:
        picked = [q(c) for c in plan.columns] or ["*"]
    wheres = [condition(f) for f in plan.filters]
    top = ""
    paged = plan.limit is not None or plan.offset
    if dialect.limit == "fetch" and dialect.order_needed and paged and not plan.sort and not plan.offset:
        top = f"TOP ({int(plan.limit or 0)}) "  # T-SQL: a limit with no order is TOP
        paged = False
    sql = f"SELECT {top}{', '.join(picked)} FROM {table_name(dialect, table)}"  # noqa: S608 (quoted, bound)
    if wheres:
        sql += " WHERE " + " AND ".join(wheres)
    if grouped:
        sql += " GROUP BY " + ", ".join(grouped)
    if plan.sort:
        sql += " ORDER BY " + ", ".join(f"{q(c)} {'DESC' if d else 'ASC'}" for c, d in plan.sort)
    elif paged and dialect.order_needed:
        sql += " ORDER BY (SELECT NULL)"
    if paged:
        sql += _paging(dialect, plan.limit, plan.offset)
    return sql, params


def _paging(dialect: Dialect, limit: int | None, offset: int) -> str:
    if dialect.limit == "fetch":
        said = f" OFFSET {int(offset)} ROWS"
        return said + (f" FETCH NEXT {int(limit)} ROWS ONLY" if limit is not None else "")
    if dialect.limit == "offset_limit":
        return (f" OFFSET {int(offset)}" if offset else "") + (
            f" LIMIT {int(limit)}" if limit is not None else ""
        )
    if limit is None:
        return (
            f" LIMIT {dialect.no_limit} OFFSET {int(offset)}"
            if dialect.no_limit
            else f" OFFSET {int(offset)}"
        )
    return f" LIMIT {int(limit)}" + (f" OFFSET {int(offset)}" if offset else "")


def _mark(style: str, at: int) -> str:
    if style in ("format", "pyformat"):
        return "%s"
    if style == "numeric":
        return f":{at}"
    if style == "named":
        return f":p{at}"
    return "?"


def _bound(style: str, params: list[Any]) -> Any:
    return {f"p{i}": v for i, v in enumerate(params, 1)} if style == "named" else params


def table_name(dialect: Dialect, table: str) -> str:
    """A listed name ("schema.table", "table" in its default schema, or "catalog.schema.table": Trino's, SQL
    Server's database.schema.table) quoted for `dialect`, each part on its own."""
    return ".".join(dialect.quote(part) for part in str(table).split(".", 2))


def paramstyle(connection: Any) -> str:
    """A DB-API connection's parameter style, from its driver's module (qmark when it does not say)."""
    import sys

    module = sys.modules.get(type(connection).__module__.split(".")[0])
    style = getattr(module, "paramstyle", "qmark")
    return style if style in ("qmark", "format", "pyformat", "numeric", "named") else "qmark"


class Sql:
    """A SQL database as a source, through its own DB-API connection (the one its connection's code made):
    the whole plan folded into one query in its dialect, the answer streamed as Arrow batches as the cursor
    fetches them; a write in its own statements, in one transaction (all or none)."""

    def __init__(
        self,
        connection: Any,
        dialect: str | Dialect,
        name: str = "",
        style: str = "",
        value: Callable[[Any], Any] | None = None,
        reopen: Callable[[], Any] | None = None,
        identity_insert: bool = False,
    ) -> None:
        self.connection = connection
        self.dialect = dialect if isinstance(dialect, Dialect) else DIALECTS[dialect]
        self.name = name or self.dialect.name
        self.style = style or paramstyle(getattr(connection, "raw", connection))
        self._value = value  # a value as the driver takes it, when the caller knows better (a Write starter)
        self.reopen = reopen  # a fresh connection for a write run again after a passing error (SQL Server)
        self.identity_insert = identity_insert  # SQL Server: the rows' own values go into its identity column

    def tables(self) -> list[Table]:
        keys = (
            {(str(s), str(t), str(c)) for s, t, c in self._rows(self.dialect.keys)}
            if self.dialect.keys
            else set()
        )
        listed: dict[tuple[str, str], list[Column]] = {}
        about: dict[tuple[str, str], tuple[str, str]] = {}  # (kind, database) as the listing says
        for row in self._rows(self.dialect.columns):
            schema, table, column, kind = (str(v) for v in row[:4])
            place = (schema, table)
            nullable = (
                None if len(row) < 6 or row[5] is None else str(row[5]).upper() in ("YES", "Y", "1", "TRUE")
            )
            listed.setdefault(place, []).append(Column(column, kind, (*place, column) in keys, nullable))
            about.setdefault(
                place, (str(row[4] or "") if len(row) > 4 else "", str(row[6] or "") if len(row) > 6 else "")
            )
        return [Table(self._listed(s, t), tuple(cols), s, *about[(s, t)]) for (s, t), cols in listed.items()]

    def listed(self) -> list[Table]:
        """Its whole catalog as its starter lists it (the app's Catalog): every schema but the system's, each
        table's and column's description where the listing has one; else its tables()."""
        if not self.dialect.listing:
            return self.tables()
        keys = (
            {tuple(str(v) for v in k) for k in self._rows(self.dialect.keys)} if self.dialect.keys else set()
        )
        found: dict[tuple[str, str], Table] = {}
        for row in self._rows(self.dialect.listing):
            said = {name: row[i] for i, name in enumerate(self.dialect.listing_shape) if i < len(row)}
            schema, table = str(said.get("schema") or ""), str(said.get("table") or "")
            made = found.get((schema, table)) or Table(
                self._listed(schema, table) if schema not in ("", "*") else table,
                (),
                schema,
                str(said.get("kind") or ""),
                str(said.get("database") or ""),
            )
            words = str(said.get("description") or "")
            if not said.get("column"):  # the table's own row (its description)
                found[(schema, table)] = replace(made, description=words)
                continue
            column = str(said["column"])
            key = (schema, table, column) in keys or "Primary key." in words
            added = Column(column, str(said.get("type") or ""), key, _yes(said.get("nullable")), words,
                           int(said["position"]) if said.get("position") is not None else None)  # fmt: skip
            found[(schema, table)] = replace(made, columns=(*made.columns, added))
        return list(found.values())

    def _listed(self, schema: str, table: str) -> str:
        bare = "*" in self.dialect.default_schema or schema in self.dialect.default_schema
        return table if bare else f"{schema}.{table}"

    def _rows(self, sql: str) -> list[Any]:
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql)
            return list(cursor.fetchall())
        finally:
            _quietly(cursor.close)

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, Folded]:
        sql, params = dialect_sql(self.dialect, table, plan, self.style)
        params = [self.value(v) for v in params]  # as the driver takes it (SQLite: a date as its text)
        periods = [p.label for p in plan.periods]
        typed = getattr(self.connection, "read_arrow", None)  # a connection typing its own Arrow (SQL Server)
        if callable(typed) and not params:
            return dated(typed(sql).to_reader(), periods), Folded(plan.parts())
        cursor = self.connection.cursor()
        try:
            if params:
                cursor.execute(sql, _bound(self.style, params))
            else:
                cursor.execute(sql)
        except Exception:
            _quietly(cursor.close)
            raise
        return dated(cursor_batches(cursor), periods), Folded(plan.parts())

    def write(self, table: str, batches: pa.RecordBatchReader, key: Sequence[str], mode: str) -> Counts:
        if mode not in MODES:
            raise AdapterError(f"A write's mode is one of {', '.join(MODES)}, not {mode!r}.")
        if mode in KEYED and not key:
            raise AdapterError(f"A {mode} names the key its rows are matched by.")
        if self.dialect.name == "sqlserver":
            return _server_written(self, table, batches, list(key), mode)
        if self.dialect.name == "trino":
            return _trino_written(self, table, batches, list(key), mode)
        if not self.dialect.transactional:
            raise AdapterError(f"{self.name} takes no transactions, so a write could not be all or none.")
        target = table_name(self.dialect, table)
        names = [str(n) for n in batches.schema.names]
        cursor = self.connection.cursor()
        try:
            done = _sql_written(self, cursor, target, names, list(key), mode, batches)
            self.connection.commit()
            return done
        except BaseException:
            _quietly(self.connection.rollback)
            raise
        finally:
            _quietly(cursor.close)

    def write_all(self, writes: Sequence[OneWrite]) -> list[Counts]:
        """Several writes in one transaction: all of them or none (SQL Server's run whole again on a passing
        error, as one write is); Trino, with no transaction, refuses before anything is sent."""
        for _, _, key, mode in writes:
            _checked_write(mode, key)
        if self.dialect.name == "trino" or not self.dialect.transactional:
            why = "it writes row batches without a transaction" if self.dialect.name == "trino" else (
                "it takes no transactions"
            )  # fmt: skip
            raise AdapterError(f"{self.name} cannot make several writes all or none ({why}).")
        if self.dialect.name == "sqlserver":
            return _server_written_all(self, [(t, b.read_all(), list(k), m) for t, b, k, m in writes])
        cursor = self.connection.cursor()
        try:
            done = [
                _sql_written(self, cursor, table_name(self.dialect, table), [str(n) for n in b.schema.names],
                             list(key), mode, b)
                for table, b, key, mode in writes
            ]  # fmt: skip
            self.connection.commit()
            return done
        except BaseException:
            _quietly(self.connection.rollback)
            raise
        finally:
            _quietly(cursor.close)

    def query(self, sql: str, params: Params = ()) -> pa.RecordBatchReader:
        """Its own SQL with its driver's marks: a read streamed from the cursor; a write committed (rolled
        back when it fails), answering its RETURNING rows, else its count."""
        cursor = self.connection.cursor()
        bound: Any = (
            {str(k): self.value(v) for k, v in params.items()}
            if isinstance(params, Mapping)
            else _bound(self.style, [self.value(v) for v in params])
        )
        try:
            if bound:
                cursor.execute(sql, bound)
            else:
                cursor.execute(sql)
            if reads_only(sql) and cursor.description:
                return cursor_batches(cursor)
            answer = None
            if self.dialect.drains:  # Trino runs a statement as its answer is read
                cursor.fetchall()
            elif cursor.description:
                answer = cursor_batches(cursor).read_all()
            changed = int(getattr(cursor, "rowcount", 0) or 0)
            if self.dialect.transactional:
                self.connection.commit()
        except BaseException:
            _quietly(cursor.close)
            if not reads_only(sql) and self.dialect.transactional:
                _quietly(self.connection.rollback)
            raise
        _quietly(cursor.close)
        return answer.to_reader() if answer is not None else counted(changed)

    def value(self, value: Any) -> Any:
        """A value as the driver takes it (SQLite: a decimal as a number, a date or time as text)."""
        if self._value is not None:
            return self._value(value)
        if self.dialect.name != "sqlite":
            return value
        if isinstance(value, decimal.Decimal):
            return float(value)
        if isinstance(value, dt.datetime):
            return value.isoformat(sep=" ")
        if isinstance(value, dt.date | dt.time):
            return value.isoformat()
        return value

    def planned(self, table: str, rows: pa.Table, key: Sequence[str], mode: str) -> Counts:
        """A write's dry run on this database: SQL Server's keys staged and counted by one join (then rolled
        back); Trino's counted by reads, its writes without a transaction said; any other's by reads."""
        if self.dialect.name == "sqlserver":
            return _server_planned(self, table, rows, list(key), mode)
        counts = counted_by_reads(self, table, rows, key, mode)
        if self.dialect.name == "trino":
            _trino_checked(table, rows.schema.names, mode, rows.num_rows)
            replaces = mode == "truncate" and rows.num_rows > 0
            return replace(counts, notes=(TRINO_REPLACE if replaces else NO_TRANSACTION,))
        return counts

    def statements(self, table: str, names: Sequence[str], key: Sequence[str], mode: str) -> list[str]:
        """What a write will run here, in its own SQL, for a dry run's report (SQL Server's and Trino's; []:
        the generic INSERT, UPDATE and DELETE, which a caller says itself)."""
        if self.dialect.name == "sqlserver":
            return _server_statements(self, table, list(names), list(key), mode)
        if self.dialect.name == "trino":
            return _trino_statements(self, table, list(names), list(key), mode)
        return []


def _quietly(close: Callable[[], Any]) -> None:
    with contextlib.suppress(Exception):
        close()


@dataclass(frozen=True)
class _Statements:
    """A SQL write's statements over one target, its values bound by the driver's marks."""

    target: str
    names: list[str]  # the rows' columns, as an insert binds them
    key: list[str]
    order: list[str]  # an update's values: the columns it sets, then the key
    insert: str
    update: str
    delete: str


def _sql_written(
    db: Sql,
    cursor: Any,
    target: str,
    names: list[str],
    key: list[str],
    mode: str,
    batches: pa.RecordBatchReader,
) -> Counts:
    """The rows into `target` by `mode`, on one cursor of the open transaction, a batch at a time (a batch
    the source refuses raises its own error, its Batch beside it). A merge asks which keys are there first,
    then    updates those and inserts the rest."""
    q, style = db.dialect.quote, db.style
    marks = ", ".join(_mark(style, i) for i in range(1, len(names) + 1))
    sets = [n for n in names if n not in key]
    if mode in ("update", "merge"):
        missing = [k for k in key if k not in names]
        if missing:
            raise AdapterError(f"The rows have no {missing[0]} column to match by.")
        if not sets:
            raise AdapterError("The rows have nothing to change but their key.")
    assigned = ", ".join(f"{q(n)} = {_mark(style, i)}" for i, n in enumerate(sets, 1))
    matched = " AND ".join(f"{q(k)} = {_mark(style, len(sets) + i)}" for i, k in enumerate(key, 1))
    gone = " AND ".join(f"{q(k)} = {_mark(style, i)}" for i, k in enumerate(key, 1))
    said = _Statements(
        target,
        names,
        key,
        sets + key,
        f"INSERT INTO {target} ({', '.join(q(n) for n in names)}) VALUES ({marks})",  # noqa: S608
        f"UPDATE {target} SET {assigned} WHERE {matched}",  # noqa: S608 (names quoted, values bound)
        f"DELETE FROM {target} WHERE {gone}",  # noqa: S608
    )
    counts = {"inserted": 0, "updated": 0, "deleted": 0}
    if mode == "truncate":
        cursor.execute(f"DELETE FROM {target}")  # noqa: S608 (the name quoted)
        counts["deleted"] = max(int(getattr(cursor, "rowcount", 0) or 0), 0)
    before = 0
    for number, batch in enumerate(batches, 1):
        try:
            _sql_batch(db, cursor, batch.to_pylist(), mode, said, counts)
        except Exception as error:
            _batch_noted(error, Batch(number, before, batch.num_rows), target)
            raise
        before += batch.num_rows
    return Counts(counts["inserted"], counts["updated"], counts["deleted"])


def _batch_noted(error: BaseException, failed: Batch, target: str) -> None:
    """The batch a write's error came from, beside the source's own error (error.sab_batch and its notes)."""
    with contextlib.suppress(AttributeError, TypeError):  # a driver's error that takes no attribute
        error.sab_batch = failed  # type: ignore[attr-defined]
    error.add_note(f"{failed.where()} of the write to {target}")


def _many(db: Sql, cursor: Any, sql: str, rows: list[list[Any]]) -> int:
    if rows:
        cursor.executemany(sql, [_bound(db.style, [db.value(v) for v in r]) for r in rows])
    return len(rows)


def _sql_batch(
    db: Sql, cursor: Any, rows: list[dict[str, Any]], mode: str, said: _Statements, counts: dict[str, int]
) -> None:
    """One batch of a write's rows by `mode`, its counts added."""
    names, key = said.names, said.key
    if mode in ("insert", "truncate"):
        counts["inserted"] += _many(db, cursor, said.insert, [[r[n] for n in names] for r in rows])
        return
    if mode == "delete":
        for r in rows:
            cursor.execute(said.delete, _bound(db.style, [db.value(r[k]) for k in key]))
            counts["deleted"] += max(int(getattr(cursor, "rowcount", 0) or 0), 0)
        return
    there = _present(db, cursor, said.target, key, rows)
    found = [r for r in rows if tuple(r[k] for k in key) in there]
    counts["updated"] += _many(db, cursor, said.update, [[r[n] for n in said.order] for r in found])
    if mode == "merge":
        new = [r for r in rows if tuple(r[k] for k in key) not in there]
        counts["inserted"] += _many(db, cursor, said.insert, [[r[n] for n in names] for r in new])


def _present(
    db: Sql, cursor: Any, target: str, key: list[str], rows: list[dict[str, Any]]
) -> set[tuple[Any, ...]]:
    """Which of the rows' keys the table has, asked 100 rows at a time."""
    q, found = db.dialect.quote, set[tuple[Any, ...]]()
    for at in range(0, len(rows), 100):
        part = rows[at : at + 100]
        values: list[Any] = []
        ors = []
        for r in part:
            ands = []
            for k in key:
                values.append(db.value(r[k]))
                ands.append(f"{q(k)} = {_mark(db.style, len(values))}")
            ors.append("(" + " AND ".join(ands) + ")")
        picked = ", ".join(q(k) for k in key)
        cursor.execute(f"SELECT {picked} FROM {target} WHERE {' OR '.join(ors)}", _bound(db.style, values))  # noqa: S608
        found.update(tuple(row) for row in cursor.fetchall())
    return found


def dated(reader: pa.RecordBatchReader, names: Sequence[str]) -> pa.RecordBatchReader:
    """A read's columns `names` (its periods) as dates, batch by batch, whatever the driver answered them
    as (SQLite's text, Oracle's date and time); the reader as it is when they are dates already."""
    wanted = set(names)
    schema = pa.schema([f.with_type(pa.date32()) if f.name in wanted else f for f in reader.schema])
    if schema.equals(reader.schema):
        return reader

    def batches() -> Iterator[pa.RecordBatch]:
        for batch in reader:
            arrays = [
                c.cast(pa.date32()) if f.name in wanted else c for f, c in zip(reader.schema, batch.columns,
                                                                                strict=True)
            ]  # fmt: skip
            yield pa.RecordBatch.from_arrays(arrays, schema=schema)

    return pa.RecordBatchReader.from_batches(schema, batches())


def cursor_batches(cursor: Any, size: int = BATCH_ROWS) -> pa.RecordBatchReader:
    """A DB-API cursor's answer as Arrow batches of `size` rows, fetched as they are read; each column keeps
    the first batch's type (a column with no value in it is text). The cursor is closed at the end."""
    names = [str(d[0]) for d in cursor.description or []]
    first = cursor.fetchmany(size)
    head = _rows_batch(names, first, None)

    def batches() -> Iterator[pa.RecordBatch]:
        try:
            yield head
            while True:
                rows = cursor.fetchmany(size)
                if not rows:
                    break
                yield _rows_batch(names, rows, head.schema)
        finally:
            _quietly(cursor.close)

    return pa.RecordBatchReader.from_batches(head.schema, batches())


def _rows_batch(names: list[str], rows: Sequence[Sequence[Any]], schema: pa.Schema | None) -> pa.RecordBatch:
    arrays = []
    for i, name in enumerate(names):
        values = [row[i] for row in rows]
        kind = schema.field(i).type if schema is not None else None
        try:
            made = pa.array(values, type=kind) if kind is not None else pa.array(values)
        except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError):
            if kind is not None and kind != pa.string():
                raise AdapterError(f"{name}'s values changed type part way through the read.") from None
            made = pa.array([None if v is None else str(v) for v in values], pa.string())
        if kind is None and pa.types.is_null(made.type):
            made = made.cast(pa.string())
        arrays.append(made)
    return pa.RecordBatch.from_arrays(arrays, names=names) if names else pa.RecordBatch.from_pylist([])


# ----- SQL Server and Azure SQL writes: staged in the target's own types, merged, run again whole -----
# The SQL Server Write starter's robustness, moved in (phase 5; the owner, 2026-11-17: "SQL server and azure
# SQL are two things I use alot so make them robust"). A write here:
#   types      read from the target (sys.columns): keyed rows staged in a #temp table of exactly those types,
#              the driver told each text's, decimal's and datetime2's size (setinputsizes), so varchar stays
#              varchar, nvarchar Unicode, a decimal its scale; NaN is NULL, an id a uniqueidentifier's text,
#              a zoned time a datetimeoffset's
#   inserts    executemany, one round trip a batch (mssql-python binds arrays itself; an older pyodbc
#              connection's fast_executemany), batches sized by the rows' width
#   merges     the rows staged, then one MERGE ... WITH (HOLDLOCK) (where MERGE is refused: UPDATE, then
#              INSERT, in the same transaction); an update and a delete join the staged rows or keys
#   truncate   TRUNCATE TABLE in the transaction (where a foreign key refuses it: DELETE FROM)
#   identity   the rows' own values in the identity column only with identity_insert (SET IDENTITY_INSERT)
#   retries    Azure's passing errors, a deadlock, a dropped connection: the WHOLE transaction again, on a
#              fresh connection, after 1, 2, 4 seconds; never half of one
#   dry run    the keys staged, one COUNT join (no row fetched), then rolled back

TRANSIENT_ERRORS: frozenset[str] = frozenset(
    {"40613", "40197", "40501", "49918", "49919", "49920", "10928", "10929", "4221", "1205"}
)
TRANSIENT_STATES: frozenset[str] = frozenset({"08S01", "08001", "40001", "HYT00", "HYT01"})
TRANSIENT_SOCKETS: frozenset[str] = frozenset({"10053", "10054", "10060"})
TRANSIENT_WORDS: tuple[str, ...] = (  # mssql-python says the server's words without the number
    "not currently available",  # 40613
    "the service has encountered an error processing your request",  # 40197
    "the service is currently busy",  # 40501
    "not enough resources to process request",  # 49918
    "too many create or update operations in progress",  # 49919
    "too many operations in progress for subscription",  # 49920
    "the server is currently too busy",  # 10929
    "limit for the database is",  # 10928
    "login to read-secondary failed",  # 4221
    "deadlocked on lock",  # 1205
    "communication link failure",  # 08S01
    "error code 0x2745",  # 10053
    "error code 0x2746",  # 10054
    "error code 0x274c",  # 10060
)
TRIES = 4  # a write met by passing errors is run whole this many times at most
BATCH_BYTES = 16_000_000  # about this much of values in one executemany batch
STAGE = "#sab_stage"  # the rows, in the target's own types
STAGED_KEYS = "#sab_keys"  # their keys, each once (a dry run, a delete)
_COLLATE = " COLLATE DATABASE_DEFAULT"  # a #temp table's text in the database's collation (not tempdb's)
_SERVER_COLUMNS = (
    "SELECT c.name, t.name, c.max_length, c.precision, c.scale, c.is_identity, c.is_computed "
    "FROM sys.columns AS c JOIN sys.types AS t ON t.user_type_id = c.user_type_id "
    "WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id"
)
# A column's type as mssql-python names it, where the target's own type does not size it (its SQL type, size,
# scale); mssql-python takes a type for every parameter or for none.
_MSSQL_TYPES: dict[str, tuple[str, int, int]] = {
    "bit": ("SQL_BIT", 1, 0),
    "tinyint": ("SQL_TINYINT", 3, 0),
    "smallint": ("SQL_SMALLINT", 5, 0),
    "int": ("SQL_INTEGER", 10, 0),
    "bigint": ("SQL_BIGINT", 19, 0),
    "real": ("SQL_REAL", 24, 0),
    "float": ("SQL_DOUBLE", 53, 0),
    "money": ("SQL_DECIMAL", 19, 4),
    "smallmoney": ("SQL_DECIMAL", 10, 4),
    "date": ("SQL_TYPE_DATE", 10, 0),
    "datetime": ("SQL_TYPE_TIMESTAMP", 23, 3),
    "smalldatetime": ("SQL_TYPE_TIMESTAMP", 16, 0),
    "uniqueidentifier": ("SQL_WVARCHAR", 36, 0),  # its text
    "datetimeoffset": ("SQL_WVARCHAR", 40, 0),  # its text, the zone kept
}


def transient(error: BaseException) -> bool:
    """Whether a SQL Server error passes by itself, so its transaction is run again: Azure's reconfiguration,
    busy and throttling errors, a deadlock, a dropped connection (by its SQLSTATE, number or words)."""
    args = [str(a) for a in getattr(error, "args", ())]
    if args and args[0] in TRANSIENT_STATES:
        return True
    text = " ".join(args) or str(error)
    if set(re.findall(r"(?<!\d)(\d{4,5})(?!\d)", text)) & (TRANSIENT_ERRORS | TRANSIENT_SOCKETS):
        return True
    lowered = text.lower()
    return any(w in lowered for w in TRANSIENT_WORDS)


@dataclass(frozen=True)
class ServerColumn:
    """One of a SQL Server table's columns, as sys.columns says it."""

    name: str
    type: str  # sys.types' name: nvarchar, decimal, datetime2...
    max_length: int  # bytes; -1 for (max)
    precision: int
    scale: int
    identity: bool = False
    computed: bool = False

    def declared(self) -> str:
        """The column's type as T-SQL declares it: nvarchar(40), decimal(12,2), datetime2(7)..."""
        kind = self.type.lower()
        if kind in ("nvarchar", "nchar"):
            return f"{kind}({'max' if self.max_length < 0 else max(1, self.max_length // 2)})"
        if kind in ("varchar", "char", "varbinary", "binary"):
            return f"{kind}({'max' if self.max_length < 0 else max(1, self.max_length)})"
        if kind in ("decimal", "numeric"):
            return f"{kind}({self.precision},{self.scale})"
        if kind in ("datetime2", "datetimeoffset", "time"):
            return f"{kind}({self.scale})"
        return kind

    @property
    def text(self) -> bool:
        return self.type.lower() in ("nvarchar", "nchar", "varchar", "char")


def server_columns(db: Sql, table: str) -> list[ServerColumn]:
    """A SQL Server table's columns (name, type, size, identity, computed) from sys.columns; refused in one
    sentence when this sign-in sees no such table."""
    cursor = db.connection.cursor()
    try:
        cursor.execute(_SERVER_COLUMNS, [table_name(db.dialect, table)])
        found = list(cursor.fetchall())
    finally:
        _quietly(cursor.close)
    if not found:
        raise AdapterError(f"{table} is not a table on {db.name} this sign-in may see.")
    return [
        ServerColumn(str(r[0]), str(r[1]), int(r[2]), int(r[3]), int(r[4]), bool(r[5]), bool(r[6]))
        for r in found
    ]


def _server_value(value: Any) -> Any:
    """A value as SQL Server takes it: NaN is NULL, an id its text, a zoned time its text with the offset (a
    datetimeoffset keeps the instant), a list or a record JSON."""
    import math

    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if getattr(value, "tzinfo", None) is not None and hasattr(value, "date"):
        return value.isoformat(sep=" ")
    if isinstance(value, list | dict):
        return json.dumps(value, default=str)
    return value


def _server_driver(connection: Any) -> Any:
    """The connection's driver module (mssql-python, or an older connection's pyodbc), for its SQL types."""
    import sys

    top = type(getattr(connection, "raw", connection)).__module__.split(".")[0]
    if top in ("mssql_python", "pyodbc"):
        return sys.modules.get(top)
    return sys.modules.get("mssql_python") or sys.modules.get("pyodbc")


def _server_size(driver: Any, column: ServerColumn) -> Any:
    """The driver's size for a column (setinputsizes): text by the target's own type and length, a decimal by
    its precision and scale, a datetime2 by its scale (fast_executemany cut its fractions), varbinary by its
    length; None: the driver's own choice."""
    kind = column.type.lower()
    if column.text:
        wide = kind in ("nvarchar", "nchar")
        size = 0 if column.max_length < 0 else column.max_length // (2 if wide else 1)
        return (driver.SQL_WVARCHAR if wide else driver.SQL_VARCHAR, size, 0)
    if kind in ("decimal", "numeric"):
        return (driver.SQL_DECIMAL, column.precision, column.scale)
    if kind == "datetime2":
        return (getattr(driver, "SQL_TYPE_TIMESTAMP", 93), 20 + column.scale, column.scale)
    if kind in ("varbinary", "binary"):
        return (getattr(driver, "SQL_VARBINARY", -3), 0 if column.max_length < 0 else column.max_length, 0)
    return None  # bit, uniqueidentifier (its text), datetimeoffset (its text, the zone kept), ints


def _server_sizes(driver: Any, columns: Sequence[ServerColumn]) -> list[Any]:
    """Every column's size for setinputsizes ([]: none to give). mssql-python takes one for every parameter
    or for none: the ones left to the driver named by their type, else none at all."""
    if driver is None:
        return []
    sizes = [_server_size(driver, c) for c in columns]
    if driver.__name__ != "mssql_python" or None not in sizes:
        return sizes
    for at, column in enumerate(columns):
        named = _MSSQL_TYPES.get(column.type.lower())
        if sizes[at] is None and named is not None and getattr(driver, named[0], None) is not None:
            sizes[at] = (getattr(driver, named[0]), named[1], named[2])
    return [] if None in sizes else sizes


class _ServerWrite:
    """One try of a SQL Server write on one cursor of its transaction: the target's columns, the rows staged
    or inserted in their types, the MERGE, UPDATE, DELETE or TRUNCATE, the counts and the notes."""

    def __init__(self, db: Sql, cursor: Any, table: str, data: pa.Table, size: int, notes: list[str]) -> None:
        self.db, self.cursor, self.table, self.data, self.size, self.notes = (
            db,
            cursor,
            table,
            data,
            size,
            notes,
        )
        self.target = table_name(db.dialect, table)
        self.columns = {c.name.casefold(): c for c in server_columns(db, table)}
        self.value = db._value or _server_value

    def column(self, name: str) -> ServerColumn:
        found = self.columns.get(str(name).casefold())
        if found is None:
            raise AdapterError(f"{self.table} has no column {name}.")
        return found

    def name(self, name: str) -> str:
        return self.db.dialect.quote(self.column(name).name)

    def names(self, names: Sequence[str]) -> str:
        return ", ".join(self.name(n) for n in names)

    def run(self, sql: str, values: Sequence[Any] | None = None) -> None:
        if values:
            self.cursor.execute(sql, list(values))
        else:
            self.cursor.execute(sql)

    def one(self, sql: str) -> int:
        self.run(sql)
        return int(self.cursor.fetchall()[0][0])

    def checked(self) -> None:
        """The rows' columns are the target's, none computed, its identity only with identity_insert."""
        for name in self.data.column_names:
            column = self.column(name)
            if column.computed:
                raise AdapterError(f"{name} is computed by {self.table}: drop it from the rows.")
            if column.identity and not self.db.identity_insert:
                raise AdapterError(
                    f"{name} is {self.table}'s identity column: SQL Server numbers it. Drop it from the rows "
                    "(the SQL Server Write starter's identity_insert=True writes the rows' own values)."
                )

    def joined(self, keys: Sequence[str], left: str = "t", right: str = "s") -> str:
        return " AND ".join(f"{left}.{self.name(k)} = {right}.{self.name(k)}" for k in keys)

    def insert_into(self, into: str, names: Sequence[str], distinct: bool = False) -> int:
        """The rows' `names` columns (each distinct row once) into `into` (the target, or a #temp table), a
        batch a round trip with each value's size; a batch that fails is named beside its error."""
        rows = _distinct(self.data.select(list(names))) if distinct else self.data.select(list(names))
        picked = [self.column(n) for n in names]
        width = sum(4000 if c.max_length < 0 else max(8, c.max_length) for c in picked)
        size = max(1, min(self.size, BATCH_BYTES // max(1, width)))
        driver = _server_driver(self.db.connection)
        if type(getattr(self.db.connection, "raw", self.db.connection)).__module__.split(".")[0] == "pyodbc":
            self.cursor.fast_executemany = True  # an older connection's: one round trip a batch
        sizes = _server_sizes(driver, picked)
        if any(sizes):
            self.cursor.setinputsizes(sizes)
        sql = f"INSERT INTO {into} ({self.names(names)}) VALUES ({', '.join('?' for _ in names)})"  # noqa: S608
        try:
            return self.batches(sql, rows, size, into)
        finally:
            if any(sizes) and driver is not None and driver.__name__ == "mssql_python":
                self.cursor.setinputsizes([])  # mssql-python keeps them for the next statements

    def batches(self, sql: str, rows: pa.Table, size: int, into: str) -> int:
        before = 0
        for number, batch in enumerate(rows.to_batches(max_chunksize=size), 1):
            values = [column.to_pylist() for column in batch.columns]
            try:
                self.cursor.executemany(
                    sql, [tuple(self.value(v) for v in row) for row in zip(*values, strict=True)]
                )
            except Exception as error:
                _batch_noted(error, Batch(number, before, batch.num_rows), into)
                raise
            before += batch.num_rows
        return before

    def stage(self, names: Sequence[str], into: str = STAGE, distinct: bool = False) -> None:
        """The rows' `names` columns in a #temp table of the target's own types (tempdb's collation is not the
        target's: text columns take the database's)."""
        declared = ", ".join(
            f"{self.name(n)} {self.column(n).declared()}{_COLLATE if self.column(n).text else ''} NULL"
            for n in names
        )
        self.run(f"IF OBJECT_ID('tempdb..{into}') IS NOT NULL DROP TABLE {into}")
        self.run(f"CREATE TABLE {into} ({declared})")
        self.insert_into(into, names, distinct)

    def matching(self, keys: Sequence[str], staged: str, hint: str = "") -> int:
        """The target's rows the staged rows' keys find: one COUNT join, no row fetched."""
        return self.one(
            f"SELECT COUNT(*) FROM {staged} AS s JOIN {self.target} AS t{hint} ON {self.joined(keys)}"  # noqa: S608
        )

    def identity(self, on: bool) -> None:
        carried = any(self.column(n).identity for n in self.data.column_names)
        if carried and self.db.identity_insert:
            self.run(f"SET IDENTITY_INSERT {self.target} {'ON' if on else 'OFF'}")

    def written(self, key: list[str], mode: str) -> Counts:
        """The write by `mode`, on this try's cursor (the caller commits)."""
        self.checked()
        if mode == "delete":
            self.stage(key, STAGED_KEYS, distinct=True)
            found = self.matching(key, STAGED_KEYS)
            self.run(f"DELETE t FROM {self.target} AS t JOIN {STAGED_KEYS} AS s ON {self.joined(key)}")
            return Counts(deleted=found)
        deleted = self.cleared() if mode == "truncate" else 0
        if mode in ("insert", "truncate"):
            self.identity(True)
            inserted = self.insert_into(self.target, self.data.column_names) if self.data.num_columns else 0
            self.identity(False)
            return Counts(inserted=inserted, deleted=deleted)
        self.stage(self.data.column_names)
        matched = self.matching(key, STAGE, " WITH (UPDLOCK, HOLDLOCK)")
        total = self.one(f"SELECT COUNT(*) FROM {STAGE}")  # noqa: S608
        if mode == "update":
            self.run(_server_update(self, key))
            return Counts(updated=matched)
        self.identity(True)
        self.merged(key)
        self.identity(False)
        return Counts(updated=matched, inserted=total - matched)

    def cleared(self) -> int:
        """TRUNCATE TABLE in the transaction (it fires no DELETE trigger); where a foreign key points at the
        table SQL Server refuses it, so DELETE FROM. The rows there before."""
        before = self.one(f"SELECT COUNT(*) FROM {self.target}")  # noqa: S608
        self.run("SAVE TRANSACTION sab_clear")
        try:
            self.run(f"TRUNCATE TABLE {self.target}")
        except Exception as error:
            if transient(error) or "FOREIGN KEY" not in str(error).upper():
                raise
            self.run("ROLLBACK TRANSACTION sab_clear")
            self.notes.append(
                "TRUNCATE was refused (a foreign key points at the table): DELETE FROM instead."
            )
            self.run(f"DELETE FROM {self.target}")  # noqa: S608
        return before

    def merged(self, key: list[str]) -> None:
        """One MERGE ... WITH (HOLDLOCK); where MERGE is refused, UPDATE then INSERT in the transaction."""
        self.run("SAVE TRANSACTION sab_merge")
        try:
            self.run(_server_merge(self, key))
        except Exception as error:
            if transient(error) or "MERGE" not in str(error).upper():
                raise
            self.run("ROLLBACK TRANSACTION sab_merge")
            self.notes.append("MERGE was refused here: UPDATE, then INSERT, in the same transaction.")
            for statement in _server_update_then_insert(self, key):
                self.run(statement)


def _settable(w: _ServerWrite, key: Sequence[str]) -> tuple[list[str], list[str]]:
    """The rows' columns as the target names them, and those a match sets (not the key, not the identity)."""
    names = [w.column(n).name for n in w.data.column_names]
    wanted = {k.casefold() for k in key}
    return names, [n for n in names if n.casefold() not in wanted and not w.column(n).identity]


def _server_merge(w: _ServerWrite, key: Sequence[str]) -> str:
    names, others = _settable(w, key)
    text = f"MERGE INTO {w.target} WITH (HOLDLOCK) AS t\nUSING {STAGE} AS s ON {w.joined(key)}\n"
    if others:
        text += (
            f"WHEN MATCHED THEN UPDATE SET {', '.join(f't.{w.name(n)} = s.{w.name(n)}' for n in others)}\n"
        )
    values = ", ".join(f"s.{w.name(n)}" for n in names)
    return text + f"WHEN NOT MATCHED BY TARGET THEN INSERT ({w.names(names)}) VALUES ({values});"  # noqa: S608


def _server_update(w: _ServerWrite, key: Sequence[str]) -> str:
    _, others = _settable(w, key)
    if not others:
        raise AdapterError("The rows have nothing to change but their key.")
    sets = ", ".join(f"t.{w.name(n)} = s.{w.name(n)}" for n in others)
    locked = f"{w.target} AS t WITH (UPDLOCK, HOLDLOCK)"
    return f"UPDATE t SET {sets} FROM {locked} JOIN {STAGE} AS s ON {w.joined(key)}"  # noqa: S608


def _server_update_then_insert(w: _ServerWrite, key: Sequence[str]) -> list[str]:
    """MERGE's work in two statements, for where MERGE is refused."""
    names, others = _settable(w, key)
    said = [_server_update(w, key)] if others else []
    picked = ", ".join(f"s.{w.name(n)}" for n in names)
    return [
        *said,
        f"INSERT INTO {w.target} ({w.names(names)}) SELECT {picked} FROM {STAGE} AS s WHERE NOT EXISTS "  # noqa: S608
        f"(SELECT 1 FROM {w.target} AS t WITH (UPDLOCK, HOLDLOCK) WHERE {w.joined(key)})",
    ]


def _distinct(rows: pa.Table) -> pa.Table:
    """Each distinct row once (DuckDB over the Arrow table: no copy of it), in one chunk (DuckDB's threads
    may answer in several: they would be batches of their own)."""
    con = duckdb.connect()
    try:
        con.register("sab_rows", rows)
        return con.sql("SELECT DISTINCT * FROM sab_rows").to_arrow_table().combine_chunks()
    finally:
        con.close()


def _server_written(db: Sql, table: str, batches: pa.RecordBatchReader, key: list[str], mode: str) -> Counts:
    """A SQL Server write in one transaction, run WHOLE again (never half) on a passing error, on a fresh
    connection after 1, 2, 4 seconds. The rows are kept for that (they are in memory already: no copy)."""
    return _server_written_all(db, [(table, batches.read_all(), key, mode)])[0]


def _server_written_all(db: Sql, writes: Sequence[tuple[str, pa.Table, list[str], str]]) -> list[Counts]:
    """SQL Server's writes, in turn, in one transaction, run WHOLE again (every one of them) on a passing
    error; each one's counts carry the notes."""
    notes: list[str] = []
    for attempt in range(1, TRIES + 1):
        cursor = db.connection.cursor()
        try:
            done = []
            for table, data, key, mode in writes:
                size = max((b.num_rows for b in data.to_batches()), default=BATCH_ROWS) or BATCH_ROWS
                done.append(_ServerWrite(db, cursor, table, data, size, notes).written(key, mode))
            db.connection.commit()
            return [replace(d, notes=tuple(notes)) for d in done]
        except Exception as error:
            _quietly(db.connection.rollback)
            if attempt == TRIES or not transient(error):
                raise
            said = (str(error).strip().splitlines() or [type(error).__name__])[0][:400]
            notes.append(f"Try {attempt} met a passing error ({said}): run again, whole.")
            time.sleep(2 ** (attempt - 1))
            _server_again(db)
        finally:
            _quietly(cursor.close)
    raise AdapterError("Nothing was written.")  # pragma: no cover (the last try returns or raises)


def _server_again(db: Sql) -> None:
    """A fresh connection for the next try: the caller's (reopen); else a SqlServer connection closed (it
    signs in again by itself on its next cursor); else the driver's own, rolled back, as it is."""
    if db.reopen is not None:
        _quietly(db.connection.close)
        db.connection = db.reopen()
    elif callable(getattr(db.connection, "for_writes", None)):
        _quietly(db.connection.close)


def _server_planned(db: Sql, table: str, rows: pa.Table, key: list[str], mode: str) -> Counts:
    """SQL Server's dry run: an insert's rows; a truncate's rows now; the keys staged in a #temp table and one
    COUNT join for the rest; then rolled back (nothing kept)."""
    if mode == "insert":
        return Counts(inserted=rows.num_rows)
    cursor = db.connection.cursor()
    try:
        w = _ServerWrite(db, cursor, table, rows, BATCH_ROWS, [])
        if mode == "truncate":
            return Counts(inserted=rows.num_rows, deleted=w.one(f"SELECT COUNT(*) FROM {w.target}"))  # noqa: S608
        w.stage(key, STAGED_KEYS, distinct=True)
        found = w.matching(key, STAGED_KEYS)
    finally:
        _quietly(db.connection.rollback)
        _quietly(cursor.close)
    if mode == "merge":
        return Counts(updated=found, inserted=rows.num_rows - found)
    return Counts(updated=found) if mode == "update" else Counts(deleted=found)


def _server_statements(db: Sql, table: str, names: list[str], key: list[str], mode: str) -> list[str]:
    """What a SQL Server write runs, for a dry run's report (a merge's staging and its MERGE)."""
    target = table_name(db.dialect, table)
    q = db.dialect.quote
    insert = (
        f"INSERT INTO {target} ({', '.join(q(n) for n in names)}) VALUES ({', '.join('?' for _ in names)})"  # noqa: S608
    )
    if mode == "insert":
        return [insert]
    if mode == "truncate":
        return [f"TRUNCATE TABLE {target}", insert] if names else [f"TRUNCATE TABLE {target}"]
    if mode == "delete":
        joined = " AND ".join(f"t.{q(k)} = s.{q(k)}" for k in key)
        return [f"DELETE t FROM {target} AS t JOIN {STAGED_KEYS} AS s ON {joined}"]
    cursor = db.connection.cursor()
    try:
        w = _ServerWrite(
            db, cursor, table, pa.table({n: pa.array([], pa.null()) for n in names}), BATCH_ROWS, []
        )
    finally:
        _quietly(cursor.close)
    staged = f"CREATE TABLE {STAGE} (the target's own types), the rows into it by executemany (as arrays)"
    return [staged, _server_merge(w, key) if mode == "merge" else _server_update(w, key)]


# ----- Trino writes: row batches without a transaction -----
# Trino's connectors take no transaction (most of them), so a write is a statement a batch: a failure part-way
# leaves the batches before it written, which its error says. An insert is INSERT ... VALUES (...), (...); a
# merge and an update MERGE INTO ... USING (VALUES ...) on the connectors that have MERGE (Iceberg, Delta
# Lake, Hive transactional tables, some JDBC ones); a delete DELETE ... WHERE the batch's keys. A truncate
# with rows (a replace): one CREATE OR REPLACE TABLE ... AS where the catalog has it (Iceberg), else refused.

NO_TRANSACTION = (
    "Trino writes row batches without a transaction: a failure part-way leaves the rows already written."
)


TRINO_REPLACE = (
    "Trino replaces the table in one statement (CREATE OR REPLACE TABLE ... AS, its columns' types and its "
    "properties kept): all of its rows or none."
)
TRINO_REPLACE_VALUES = 100_000  # values one replace's statement carries at most (Trino's query length)
_TRINO_WITH = re.compile(r"\)\s*WITH\s*\((.*)\)\s*$", re.DOTALL)


def _trino_checked(table: str, names: Sequence[str], mode: str, rows: int = 0) -> None:
    """A replace (a truncate with rows) is one statement: refused before anything runs when it is too big."""
    if mode == "truncate" and names and rows * len(names) > TRINO_REPLACE_VALUES:
        raise AdapterError(
            f"A replace of {rows:,} rows is too big for one Trino statement (at most "
            f"{TRINO_REPLACE_VALUES:,} values), and {NO_TRANSACTION[:-1]}. Clear {table} first (truncate "
            "with no rows), then insert the rows."
        )


def _trino_refused(table: str) -> str:
    """A catalog without CREATE OR REPLACE TABLE ... AS (Hive's): the replace refused, nothing changed."""
    return (
        f"{table}'s catalog cannot replace a table in one statement (CREATE OR REPLACE TABLE ... AS: "
        f"Iceberg's can), and {NO_TRANSACTION[:-1]}, so a truncate with rows could clear it and then fail, "
        "leaving it without its rows. Clear it first (truncate with no rows), then insert the rows."
    )


def _trino_types(db: Sql, cursor: Any, table: str) -> dict[str, str]:
    """The table's columns' own types (its catalog's information_schema), so a replace keeps them."""
    parts = str(table).split(".", 2)
    q = db.dialect.quote
    where = f"{q(parts[0])}.information_schema.columns" if len(parts) == 3 else "information_schema.columns"
    named = parts[-2:] if len(parts) > 1 else parts
    sql = f"SELECT column_name, data_type FROM {where} WHERE table_name = {_mark(db.style, 1)}"  # noqa: S608
    values = [named[-1]]
    if len(named) == 2:
        sql += f" AND table_schema = {_mark(db.style, 2)}"
        values.append(named[0])
    try:
        cursor.execute(sql, _bound(db.style, values))
        return {str(n): str(t) for n, t in cursor.fetchall()}
    except Exception:
        return {}  # a table not there yet: the replace makes it with the rows' types


def _trino_properties(cursor: Any, target: str) -> str:
    """The table's properties (format, partitioning, location...) from SHOW CREATE TABLE: what a replace says
    again in its WITH, so the new table is laid out as the old one."""
    try:
        cursor.execute(f"SHOW CREATE TABLE {target}")
        shown = str(cursor.fetchall()[0][0])
    except Exception:
        return ""
    found = _TRINO_WITH.search(shown)
    return " ".join(found.group(1).split()) if found else ""


def _trino_replace_sql(
    db: Sql, target: str, names: list[str], types: Mapping[str, str], props: str, rows: int
) -> str:
    q = db.dialect.quote
    picked = ", ".join(
        f"CAST({q(n)} AS {types[n].upper()}) AS {q(n)}" if n in types else f"{q(n)} AS {q(n)}" for n in names
    )
    groups = ", ".join("(" + ", ".join(_mark(db.style, 1) for _ in names) + ")" for _ in range(rows))
    shown = f"\nWITH ({props})" if props else ""
    cols = ", ".join(q(n) for n in names)
    return (
        f"CREATE OR REPLACE TABLE {target}{shown}\nAS SELECT {picked}\nFROM (VALUES {groups}) AS s ({cols})"
    )


def _trino_replace(db: Sql, cursor: Any, table: str, target: str, batches: pa.RecordBatchReader) -> Counts:
    """A replace as one statement where the catalog has it (Iceberg's): its rows in one CREATE OR REPLACE
    TABLE ... AS, each column cast to its own type, its properties said again; all or none. A catalog without
    it refuses the statement: nothing changed, and the refusal says what to do instead."""
    data = batches.read_all()
    names = [str(n) for n in data.schema.names]
    _trino_checked(table, names, "truncate", data.num_rows)
    try:
        before = _trino_count(db, cursor, target)
    except Exception:
        before = 0  # not there yet: the replace makes it
    if not data.num_rows:  # no rows: only cleared
        _trino_run(db, cursor, f"DELETE FROM {target}", [])  # noqa: S608
        return Counts(deleted=before, notes=(NO_TRANSACTION,))
    types, props = _trino_types(db, cursor, table), _trino_properties(cursor, target)
    values = [db.value(r[n]) for r in data.to_pylist() for n in names]
    try:
        _trino_run(db, cursor, _trino_replace_sql(db, target, names, types, props, data.num_rows), values)
    except Exception as error:
        if "not supported" in str(error).lower() or "NOT_SUPPORTED" in str(error):
            raise AdapterError(_trino_refused(table)) from error
        raise
    return Counts(inserted=data.num_rows, deleted=before, notes=(TRINO_REPLACE,))


def _trino_sql(db: Sql, target: str, names: list[str], key: list[str], mode: str, rows: int) -> str:
    """One batch's statement: `rows` rows of marks in VALUES."""
    q = db.dialect.quote
    cols = ", ".join(q(n) for n in names)
    groups = ", ".join("(" + ", ".join(_mark(db.style, 1) for _ in names) + ")" for _ in range(rows))
    if mode == "insert":
        return f"INSERT INTO {target} ({cols}) VALUES {groups}"  # noqa: S608
    others = [n for n in names if n not in key]
    text = f"MERGE INTO {target} AS t USING (VALUES {groups}) AS s ({cols})\nON "
    text += " AND ".join(f"t.{q(k)} = s.{q(k)}" for k in key) + "\n"
    if others:
        text += "WHEN MATCHED THEN UPDATE SET " + ", ".join(f"{q(c)} = s.{q(c)}" for c in others) + "\n"
    if mode == "update":
        return text.rstrip("\n")
    return (
        text + f"WHEN NOT MATCHED THEN INSERT ({cols}) VALUES (" + ", ".join(f"s.{q(c)}" for c in names) + ")"  # noqa: S608
    )


def _trino_written(db: Sql, table: str, batches: pa.RecordBatchReader, key: list[str], mode: str) -> Counts:
    """A Trino write, a statement a batch (each answer read: Trino runs a statement as its answer is read)."""
    names = [str(n) for n in batches.schema.names]
    if mode == "update" and not [n for n in names if n not in key]:
        raise AdapterError("The rows have nothing to change but their key.")
    target = table_name(db.dialect, table)
    cursor = db.connection.cursor()
    try:
        if mode == "truncate" and names:  # a replace: one statement, all or none
            return _trino_replace(db, cursor, table, target, batches)
        before = _trino_count(db, cursor, target) if mode in ("merge", "delete", "truncate") else 0
        if mode == "truncate":
            _trino_run(db, cursor, f"DELETE FROM {target}", [])  # noqa: S608
            return Counts(deleted=before, notes=(NO_TRANSACTION,))
        written, updated = _trino_batches(db, cursor, table, target, batches, key, mode)
        after = _trino_count(db, cursor, target) if mode in ("merge", "delete") else 0
    finally:
        _quietly(cursor.close)
    if mode == "insert":
        return Counts(inserted=written, notes=(NO_TRANSACTION,))
    if mode == "delete":
        return Counts(deleted=before - after, notes=(NO_TRANSACTION,))
    if mode == "update":
        return Counts(updated=updated, notes=(NO_TRANSACTION,))
    return Counts(inserted=after - before, updated=written - (after - before), notes=(NO_TRANSACTION,))


def _trino_batches(
    db: Sql, cursor: Any, table: str, target: str, batches: pa.RecordBatchReader, key: list[str], mode: str
) -> tuple[int, int]:
    """Each batch's statement; a failure names its batch and the rows written before it. The rows written,
    and an update's rows that were there (counted by reads before each batch)."""
    names = [str(n) for n in batches.schema.names]
    before = updated = 0
    for number, batch in enumerate(batches, 1):
        rows = pa.Table.from_batches([batch])
        try:
            if mode == "update":
                updated += present(db, table, rows, key)
            _trino_rows(db, cursor, target, names, key, mode, rows)
        except Exception as error:
            _batch_noted(error, Batch(number, before, batch.num_rows), target)
            error.add_note(
                f"Trino writes row batches without a transaction: the {before:,} rows before it were written."
            )
            raise
        before += batch.num_rows
    return before, updated


def _trino_rows(
    db: Sql, cursor: Any, target: str, names: list[str], key: list[str], mode: str, rows: pa.Table
) -> None:
    """One batch's rows: one statement; a delete's keys, a hundred a statement."""
    records = rows.to_pylist()
    if mode != "delete":
        values = [db.value(r[n]) for r in records for n in names]
        _trino_run(db, cursor, _trino_sql(db, target, names, key, mode, len(records)), values)
        return
    keys = list(dict.fromkeys(tuple(r[k] for k in key) for r in records))
    q = db.dialect.quote
    one = "(" + " AND ".join(f"{q(k)} = {_mark(db.style, 1)}" for k in key) + ")"
    for at in range(0, len(keys), 100):
        part = keys[at : at + 100]
        where = " OR ".join(one for _ in part)
        _trino_run(db, cursor, f"DELETE FROM {target} WHERE {where}", [db.value(v) for k in part for v in k])  # noqa: S608


def _trino_run(db: Sql, cursor: Any, sql: str, values: list[Any]) -> None:
    if values:
        cursor.execute(sql, _bound(db.style, values))
    else:
        cursor.execute(sql)
    cursor.fetchall()  # Trino runs a statement as its answer is read


def _trino_count(db: Sql, cursor: Any, target: str) -> int:
    cursor.execute(f"SELECT COUNT(*) FROM {target}")  # noqa: S608
    return int(cursor.fetchall()[0][0])


def _trino_statements(db: Sql, table: str, names: list[str], key: list[str], mode: str) -> list[str]:
    """What a Trino write runs, for a dry run's report (a batch's statement, its rows as (...))."""
    target = table_name(db.dialect, table)
    if mode == "truncate" and names:  # a replace: one statement (its columns' types read first)
        one = _trino_replace_sql(db, target, names, {}, "its properties", 1)
        groups = "(" + ", ".join(_mark(db.style, 1) for _ in names) + ")"
        return [
            one.replace(f"VALUES {groups}", f"VALUES {groups}, ...", 1) + "  -- every row in one statement"
        ]
    if mode == "truncate":
        return [f"DELETE FROM {target}"]  # noqa: S608
    if mode == "delete":
        where = " AND ".join(f"{db.dialect.quote(k)} = ?" for k in key)
        return [f"DELETE FROM {target} WHERE ({where}) OR ...  -- a hundred keys a statement"]  # noqa: S608
    one = _trino_sql(db, target, names, key, mode, 1)
    groups = "(" + ", ".join(_mark(db.style, 1) for _ in names) + ")"
    return [one.replace(f"VALUES {groups}", f"VALUES {groups}, ...", 1) + "  -- a batch of rows a statement"]


# ----- Dataverse's Web API: OData folded into its connection's own read -----

ODATA_TYPES = {
    "String": "VARCHAR",
    "Memo": "VARCHAR",
    "Integer": "BIGINT",
    "BigInt": "BIGINT",
    "Double": "DOUBLE",
    "Decimal": "DOUBLE",
    "Money": "DOUBLE",
    "Boolean": "BOOLEAN",
    "DateTime": "TIMESTAMP",
}  # fmt: skip  every other kind (a lookup's id, a choice's label, an id) is text
_ODATA_OPS = {"=": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}


def odata_literal(value: Any) -> str:
    """A value as an OData literal: text quoted ('' inside), true/false, null, a number or a date as is."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    if type(value).__name__ == "Decimal":
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def odata_filter(filters: Sequence[Filter], fields: Mapping[str, str]) -> str | None:
    """The filters as one OData $filter over the Web API's field names (`fields`: a column's name ->
    its field); None when one cannot be said in OData (a pattern with a % inside, a choice's label)."""
    said = []
    for f in filters:
        field = fields.get(f.column.casefold())
        if field is None:
            return None
        if f.op in _ODATA_OPS:
            said.append(f"{field} {_ODATA_OPS[f.op]} {odata_literal(f.value)}")
        elif f.op in ("is null", "is not null"):
            said.append(f"{field} {'eq' if f.op == 'is null' else 'ne'} null")
        elif f.op == "in":
            either = " or ".join(f"{field} eq {odata_literal(v)}" for v in f.value)
            said.append(either if len(filters) == 1 else f"({either})")  # brackets only among others
        elif f.op == "between":
            low, high = f.value
            said.append(f"({field} ge {odata_literal(low)} and {field} le {odata_literal(high)})")
        elif f.op == "contains":  # Dataverse compares every string in any case; its wildcards are DuckDB's
            if any(c in str(f.value) for c in "%_[]"):
                return None
            said.append(f"contains({field},{odata_literal(str(f.value))})")
        else:  # like: a leading and/or trailing % only
            text = str(f.value)
            inner = text.strip("%")
            if "%" in inner or "_" in inner or not inner:
                return None
            fn = (
                "contains"
                if text.startswith("%") and text.endswith("%")
                else ("endswith" if text.startswith("%") else "startswith" if text.endswith("%") else "")
            )
            said.append(
                f"{fn}({field},{odata_literal(inner)})" if fn else f"{field} eq {odata_literal(inner)}"
            )
    return " and ".join(said)


class OData:
    """A Dataverse environment through its Web API, by its connection's own calls (rows, described,
    catalog): filters, columns, sort and limit folded into one OData read ($filter, $select, $orderby, $top),
    the records typed by the table's metadata. The rest (offset, group, totals, a filter OData cannot say) is
    done by DuckDB over the answer. `total` is the row count the last read's source gave (None: not said)."""

    def __init__(self, connection: Any, name: str = "Dataverse", batch_size: int = 1000) -> None:
        self.connection = connection
        self.name = name
        self.total: int | None = None
        self.batch_size = batch_size  # rows in each $batch change set (a write)

    def tables(self) -> list[Table]:
        listed: dict[str, list[Column]] = {}
        for row in self.connection.catalog():
            columns = listed.setdefault(str(row["table_name"]), [])
            if row.get("column_name"):
                columns.append(
                    Column(str(row["column_name"]), ODATA_TYPES.get(str(row["data_type"]), "VARCHAR"))
                )
        return [Table(name, tuple(columns)) for name, columns in listed.items()]

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, Folded]:
        described = list(self.connection.described(table))
        types = {str(c["name"]): ODATA_TYPES.get(str(c["type"]), "VARCHAR") for c in described}
        plain = {str(c["name"]).casefold(): str(c["field"]) for c in described if not c.get("label")}
        filter_text = odata_filter(plan.filters, plain) if plan.filters else None
        sortable = all(c.casefold() in plain for c, _ in plan.sort)
        foldable = {"columns", "limit"} | ({"filters"} if filter_text is not None else set())
        foldable |= {"sort"} if sortable else set()
        folded: list[str] = []
        for part in plan.parts():
            if part not in foldable:
                break
            folded.append(part)
        by_name = {n.casefold(): n for n in types}
        asked = plan.columns if "columns" in folded else plan.needed() if plan.totals else ()
        picked = [by_name.get(c.casefold(), c) for c in asked]  # with totals: the columns DuckDB groups
        order = (
            ", ".join(f"{plain[c.casefold()]}{' desc' if d else ''}" for c, d in plan.sort)
            if "sort" in folded
            else ""
        )  # only when sent: a sort by a total's or a period's name is DuckDB's
        records, self.total = self.connection.rows(
            table,
            columns=picked or None,
            filter=filter_text if "filters" in folded else None,
            order_by=order if "sort" in folded else None,
            limit=plan.limit if "limit" in folded else None,
        )
        given = {n: types[n] for n in (picked or list(types)) if n in types}
        return from_json([records], given), Folded(tuple(folded))

    def write(self, table: str, batches: pa.RecordBatchReader, key: Sequence[str], mode: str) -> Counts:
        """Rows into a table through the Web API's $batch change sets (_dataverse_written)."""
        _checked_write(mode, key)
        one = _one_key(key, "A Dataverse record")
        rows = [r for batch in batches for r in batch.to_pylist()]
        return _dataverse_written(self, table, rows, [str(n) for n in batches.schema.names], one, mode)


# ----- a connection that reads a table itself: the lakes and SharePoint -----

_ROWS_OPS = {"!=": "<>"} | {
    op: op for op in ("=", "<", "<=", ">", ">=", "in", "between", "is null", "is not null")
}


class Rows:
    """A connection whose own code reads a table given its columns, filters and a limit, and answers Arrow
    and the count (`rows(table, schema, limit, columns, filters)`: the lakes' and SharePoint's, each sending
    what its service takes, $filter or a file's partitions, and applying the rest in DuckDB). A table is
    named `schema/table` (its folders) or `table`. Filters, columns and limit are folded; `total` is the count
    the last read gave."""

    def __init__(self, connection: Any, name: str = "") -> None:
        self.connection = connection
        self.name = name or type(connection).__name__
        self.total: int | None = None

    def tables(self) -> list[Table]:
        listed: dict[str, list[Column]] = {}
        for row in self.connection.catalog():
            schema, table = str(row.get("table_schema") or ""), str(row["table_name"])
            columns = listed.setdefault(f"{schema}/{table}" if schema else table, [])
            if row.get("column_name"):
                columns.append(Column(str(row["column_name"]), str(row.get("data_type") or "VARCHAR")))
        return [Table(name, tuple(columns)) for name, columns in listed.items()]

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, Folded]:
        sendable = all(f.op in _ROWS_OPS for f in plan.filters)
        foldable = {"columns", "limit"} | ({"filters"} if sendable else set())
        folded: list[str] = []
        for part in plan.parts():
            if part not in foldable:
                break
            folded.append(part)
        schema, _, name = str(table).rpartition("/")
        filters = (
            [[f.column, _ROWS_OPS[f.op], f.value] for f in plan.filters] if "filters" in folded else None
        )
        answer = self.connection.rows(
            name,
            schema=schema,
            limit=plan.limit if "limit" in folded else None,
            columns=(
                list(plan.columns) if "columns" in folded else list(plan.needed()) if plan.totals else None
            ),  # with totals (never folded here): only the columns DuckDB groups
            filters=filters,
            frame=False,
        )
        found, self.total = answer if isinstance(answer, tuple) else (answer, None)
        if not isinstance(found, pa.Table):
            pandas = type(found).__module__.startswith("pandas")
            found = (
                pa.Table.from_pandas(found, preserve_index=False)
                if pandas
                else pa.Table.from_pylist(list(found))
            )
        return found.to_reader(), Folded(tuple(folded))

    def write(self, table: str, batches: pa.RecordBatchReader, key: Sequence[str], mode: str) -> Counts:
        """Rows into a lake's table (write_delta, delete_delta, write_file) or a SharePoint list (create,
        update, delete, ids): the connection's own calls."""
        _checked_write(mode, key)
        conn = self.connection
        said = said_source(conn)  # what it says it is, else what its methods show (an older client)
        lake = said == "lake" if said else callable(getattr(conn, "write_delta", None))
        listed = (
            said == "list"
            if said
            else callable(getattr(conn, "create", None)) and callable(getattr(conn, "ids", None))
        )
        if lake:
            return _lake_written(self, table, batches.read_all(), list(key), mode)
        if listed:
            one = _one_key(key, "A SharePoint item")
            rows = [r for batch in batches for r in batch.to_pylist()]
            return _list_written(self, table, rows, one, mode)
        raise AdapterError(f"{self.name} takes no writes: it is read only.")


def _checked_write(mode: str, key: Sequence[str]) -> None:
    if mode not in MODES:
        raise AdapterError(f"A write's mode is one of {', '.join(MODES)}, not {mode!r}.")
    if mode in KEYED and not key:
        raise AdapterError(f"A {mode} names the key its rows are matched by.")


def _one_key(key: Sequence[str], what: str) -> str:
    if len(key) > 1:
        raise AdapterError(f"{what} is found by one key column, not {len(key)}.")
    return key[0] if key else ""


def _unique_keys(rows: list[dict[str, Any]], key: str) -> None:
    """Each row has a key of its own (an update or a merge would write the second over the first)."""
    empty = sum(1 for r in rows if r.get(key) is None)
    if empty:
        raise AdapterError(f"{empty:,} rows have no value in the key column {key}.")
    seen: set[Any] = set()
    shared = 0
    for r in rows:
        value = _same(r[key])
        shared += value in seen
        seen.add(value)
    if shared:
        raise AdapterError(
            f"{shared:,} keys are shared by more than one row: each row needs a key of its own."
        )


def _same(value: Any) -> Any:
    """A key's value as two sources compare it: text in any case (Dataverse answers ids in small letters)."""
    return value.casefold() if isinstance(value, str) else value


# ----- Dataverse's writes: the Web API's $batch change sets (the Write starters' code, moved in) -----

DV_CHOICES = frozenset({"Picklist", "State", "Status", "MultiSelectPicklist"})
DV_LOOKUPS = frozenset({"Lookup", "Customer", "Owner"})
_DV_METADATA = {
    "Picklist": "PicklistAttributeMetadata",
    "State": "StateAttributeMetadata",
    "Status": "StatusAttributeMetadata",
    "MultiSelectPicklist": "MultiSelectPicklistAttributeMetadata",
}
CHANGE_SET = 1000  # requests in one $batch change set at most (Dataverse's)
DV_WAITS = 5  # a throttled $batch goes again this many times
_DV_LONGEST_WAIT = 300.0
_DV_KEYS_AT_ONCE = 25  # keys asked about in one GET ($filter ... or ...)
_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_DV_HINTS = {
    400: "Dataverse could not take a record as sent: a column's value may be of the wrong type.",
    401: "The sign-in was not accepted: test the Dataverse connection.",
    403: "This sign-in may not write this table: its security role needs Create, Write or Delete on it.",
    404: "A record is not there: check the key's values (an update or a delete finds each one).",
    412: "A record changed or is not there (If-Match).",
    429: "Dataverse kept asking to wait: try again later, or with a smaller batch size.",
}


class _Dataverse:
    """One write to a Dataverse table through its Web API: the connection's own address (`api`), sign-in
    (`access_token()`), tables (`table`, `described`) and reads (`get`, `rows`). Each change set is one
    $batch request, all of it or none (Dataverse's transaction); a refusal names its batch and rows, and the
    batches before it stay written. A throttled request (429, 503) waits as Retry-After says, then goes
    again. A choice column takes its labels (Won, not 1); a lookup is a column named <column>@odata.bind."""

    def __init__(self, conn: Any, table: str, size: int) -> None:
        self.conn = conn
        try:
            found = conn.table(table)
            self.logical, self.entity_set = str(found["table"]), str(found["set"])
            self.kinds = {str(c["name"]).lower(): str(c["type"]) for c in conn.described(self.logical)}
        except RuntimeError as error:  # the connection's own DataverseError, in plain words
            raise AdapterError(str(error)) from None
        self.size = max(1, min(int(size), CHANGE_SET))
        self._options: dict[str, dict[str, int]] = {}

    def check(self, names: Sequence[str]) -> None:
        """Each column is the table's (a lookup as <column>@odata.bind)."""
        missing = [n for n in names if "@" not in n and n.lower() not in self.kinds]
        if missing:
            some = ", ".join(sorted(self.kinds)[:20])
            raise AdapterError(f"{self.logical} has no column {', '.join(missing)} (it has {some} ...).")
        lookups = [n for n in names if self.kinds.get(n.lower()) in DV_LOOKUPS]
        if lookups:
            raise AdapterError(
                f"{lookups[0]} is a lookup: name the rows' column {lookups[0]}@odata.bind and give each row "
                '"/<entity set>(<id>)" (for example "/contacts(00000000-0000-0000-0000-000000000000)").'
            )

    def options(self, column: str) -> dict[str, int]:
        column = column.lower()
        if column not in self._options:
            kind = _DV_METADATA[self.kinds[column]]
            path = (
                f"EntityDefinitions(LogicalName='{self.logical}')/Attributes(LogicalName='{column}')/"
                f"Microsoft.Dynamics.CRM.{kind}?$select=LogicalName&$expand=OptionSet($select=Options)"
            )
            answer = self.get(path, f"Reading {self.logical}.{column}'s options")
            found = (answer.get("OptionSet") or {}).get("Options") or []
            self._options[column] = {_dv_label(o.get("Label")).casefold(): int(o["Value"]) for o in found}
        return self._options[column]

    def value(self, column: str, value: Any) -> Any:
        """A value as the Web API takes it: a choice's label as its number, dates as ISO text."""
        value = _json_value(value)
        kind = self.kinds.get(column.lower())
        if kind not in DV_CHOICES or value is None or isinstance(value, int | float):
            return value
        labels = self.options(column)
        many = kind == "MultiSelectPicklist"
        given = value if isinstance(value, list) else str(value).split(";") if many else [value]
        numbers = []
        for one in given:
            word = str(one).strip()
            if word.lstrip("-").isdigit():
                numbers.append(int(word))
            elif word.casefold() in labels:
                numbers.append(labels[word.casefold()])
            else:
                known = ", ".join(sorted(labels))
                raise AdapterError(f"{column} has no choice {word!r}: its choices are {known}.")
        return ",".join(map(str, numbers)) if many else numbers[0]

    def body(self, row: Mapping[str, Any], without: str = "", skip_empty: bool = False) -> dict[str, Any]:
        out = {}
        for column, value in row.items():
            if column.lower() == without.lower() or (skip_empty and value is None):
                continue
            out[column if "@" in column else column.lower()] = self.value(column, value)
        return out

    def is_id(self, key: str) -> bool:
        return self.kinds.get(key.lower()) == "Uniqueidentifier"

    def literal(self, key: str, value: Any) -> str:
        value = _json_value(value)
        if self.is_id(key):
            if not _GUID.fullmatch(str(value)):
                raise AdapterError(f"{key} holds ids (00000000-0000-0000-0000-000000000000), not {value!r}.")
            return str(value)
        return odata_literal(value)

    def address(self, key: str, value: Any) -> str:
        """A record's address: accounts(<id>), or by an alternate key accounts(accountnumber='AC-1')."""
        literal = self.literal(key, value)
        inside = literal if self.is_id(key) else f"{key.lower()}={literal}"
        return f"{self.entity_set}({urllib.parse.quote(inside, safe=chr(39) + '=-')})"

    def existing(self, key: str, values: Iterable[Any]) -> set[Any]:
        """Which of the keys are records already (compared as _same), asked a few at a time."""
        field = key.lower()
        wanted = list(dict.fromkeys(values))
        found: set[Any] = set()
        for at in range(0, len(wanted), _DV_KEYS_AT_ONCE):
            condition = " or ".join(
                f"{field} eq {self.literal(key, v)}" for v in wanted[at : at + _DV_KEYS_AT_ONCE]
            )
            query = urllib.parse.urlencode(
                {"$select": field, "$filter": condition}, quote_via=urllib.parse.quote
            )
            answer = self.get(f"{self.entity_set}?{query}", f"Looking up {self.logical}'s {key}")
            found |= {_same(r.get(field)) for r in answer.get("value") or []}
        return found

    def every_id(self) -> list[str]:
        """Every record's id (a truncate's deletes)."""
        named = f"{self.logical}id"
        column = (
            named
            if self.kinds.get(named) == "Uniqueidentifier"
            else next((n for n, k in self.kinds.items() if k == "Uniqueidentifier"), "")
        )
        if not column:
            raise AdapterError(f"{self.logical} has no id column, so it cannot be cleared.")
        records, _ = self.conn.rows(self.logical, columns=[column])
        return [str(r[column]) for r in records if r.get(column)]

    def get(self, path: str, what: str) -> dict[str, Any]:
        try:
            found = self.conn.get(path, what)
        except RuntimeError as error:
            raise AdapterError(str(error)) from None
        return found if isinstance(found, dict) else {}

    def send(self, requests: Sequence[tuple[str, str, Any, dict[str, str]]]) -> list[int]:
        """The requests (method, address, body, headers) sent a change set at a time: each one's status."""
        statuses: list[int] = []
        for number, at in enumerate(range(0, len(requests), self.size), 1):
            part = requests[at : at + self.size]
            try:
                statuses += self._change_set(part)
            except AdapterError as error:
                before = f"the {at:,} rows before it were written" if at else "nothing was written"
                raise AdapterError(
                    f"Batch {number} (rows {at + 1:,} to {at + len(part):,}) was refused and rolled back: "
                    f"{error} Each batch is a transaction of its own (up to {CHANGE_SET:,} rows): {before}."
                ) from None
        return statuses

    def _change_set(self, requests: Sequence[tuple[str, str, Any, dict[str, str]]]) -> list[int]:
        batch, change = f"batch_{uuid.uuid4().hex}", f"changeset_{uuid.uuid4().hex}"
        parts = []
        for n, (method, path, body, headers) in enumerate(requests, 1):
            lines = [
                f"--{change}",
                "Content-Type: application/http",
                "Content-Transfer-Encoding: binary",
                f"Content-ID: {n}",
                "",
                f"{method} {self.conn.api}/{path} HTTP/1.1",
                "Content-Type: application/json; charset=utf-8",
                *(f"{k}: {v}" for k, v in headers.items()),
                "",
                "" if body is None else json.dumps(body),
            ]
            parts.append("\r\n".join(lines))
        text = (
            f"--{batch}\r\nContent-Type: multipart/mixed; boundary={change}\r\n\r\n"
            + "\r\n".join(parts)
            + f"\r\n--{change}--\r\n--{batch}--\r\n"
        )
        answer = self._post(text.encode("utf-8"), batch)
        statuses = [int(s) for s in re.findall(r"HTTP/1\.1 (\d{3})", answer)]
        failed = next((s for s in statuses if s >= 400), None)
        if failed is not None or not statuses:
            raise AdapterError(_dv_refusal(answer, failed or 0))
        return statuses

    def _post(self, data: bytes, boundary: str) -> str:
        import urllib.error
        import urllib.request

        for attempt in range(DV_WAITS + 1):
            headers = {
                "Authorization": f"Bearer {self.conn.access_token()}",
                "Content-Type": f"multipart/mixed; boundary={boundary}",
                "Accept": "application/json",
                "OData-MaxVersion": "4.0",
                "OData-Version": "4.0",
            }
            request = urllib.request.Request(f"{self.conn.api}/$batch", data, headers, method="POST")  # noqa: S310
            try:
                with urllib.request.urlopen(request, timeout=300) as answer:  # noqa: S310 (the connection's api)
                    return str(answer.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as refused:
                if refused.code in (429, 503) and attempt < DV_WAITS:
                    wait = refused.headers.get("Retry-After") or ""
                    seconds = float(wait) if wait.strip().replace(".", "", 1).isdigit() else 2.0**attempt
                    time.sleep(min(seconds, _DV_LONGEST_WAIT))
                    continue
                said = refused.read().decode("utf-8", "replace")
                raise AdapterError(_dv_refusal(said, refused.code)) from None
            except urllib.error.URLError as error:
                raise AdapterError(f"Dataverse could not be reached: {error.reason}") from None
        raise AdapterError("Dataverse kept asking to wait (429).")


def _dv_label(label: Any) -> str:
    if not isinstance(label, dict):
        return ""
    own = label.get("UserLocalizedLabel") or {}
    if own.get("Label"):
        return str(own["Label"])
    return next((str(e["Label"]) for e in label.get("LocalizedLabels") or [] if e.get("Label")), "")


def _dv_refusal(text: str, status: int) -> str:
    """Dataverse's own message from an answer, and what its status usually means."""
    found = re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    message = (
        json.loads(f'"{found.group(1)}"') if found else (text.strip().splitlines() or ["no reason"])[0][:300]
    )
    return f"Dataverse refused ({status}): {message}. {_DV_HINTS.get(status, '')}".strip()


def _dataverse_written(source: OData, table: str, rows: list[dict[str, Any]], names: list[str],
                       key: str, mode: str) -> Counts:  # fmt: skip
    """Rows into a Dataverse table by mode: insert (POST), update (PATCH If-Match: *, every key a record),
    merge (PATCH: Dataverse makes a record that is not there), delete (DELETE the keys that are records),
    truncate (every record deleted, then the rows made)."""
    dv = _Dataverse(source.connection, table, source.batch_size)
    dv.check([key] if mode == "delete" else names)
    if mode in ("update", "merge", "delete"):
        if key.lower() not in dv.kinds:
            raise AdapterError(
                f"{dv.logical} has no column {key}: the key is its id or an alternate key's column."
            )
        _unique_keys(rows, key)
    if mode == "insert":
        made = dv.send([("POST", dv.entity_set, dv.body(r, skip_empty=True), {}) for r in rows])
        return Counts(inserted=len(made))
    if mode == "truncate":
        ids = dv.every_id()
        gone = dv.send([("DELETE", f"{dv.entity_set}({i})", None, {}) for i in ids]) if ids else []
        made = (
            dv.send([("POST", dv.entity_set, dv.body(r, skip_empty=True), {}) for r in rows]) if rows else []
        )
        return Counts(inserted=len(made), deleted=len(gone))
    found = dv.existing(key, [r[key] for r in rows])
    if mode == "update":
        missing = [str(r[key]) for r in rows if _same(_json_value(r[key])) not in found]
        if missing:  # an update only updates: a key that is not a record stops it (merge makes them)
            raise AdapterError(f"{len(missing):,} keys are not records of {table}: {', '.join(missing[:5])}")
        changed = dv.send(
            [("PATCH", dv.address(key, r[key]), dv.body(r, without=key), {"If-Match": "*"}) for r in rows]
        )
        return Counts(updated=len(changed))
    if mode == "merge":
        prefer = {"Prefer": "return=representation"}  # answered 201 when made, 200 when updated
        answers = dv.send([("PATCH", dv.address(key, r[key]), dv.body(r, without=key), prefer) for r in rows])
        return Counts(inserted=answers.count(201), updated=len(answers) - answers.count(201))
    there = [r for r in rows if _same(_json_value(r[key])) in found]
    gone = dv.send([("DELETE", dv.address(key, r[key]), None, {}) for r in there]) if there else []
    return Counts(deleted=len(gone))


# ----- a SharePoint list's writes and a lake's: by the connection's own calls (Graph's $batch, Delta) -----


def _key_values(source: Rows, table: str, key: Sequence[str]) -> set[tuple[Any, ...]]:
    """The keys a table has now (read through the source), as _same compares them."""
    found = read(source, table, Plan(columns=tuple(key)))[0].read_all().to_pylist()
    return {tuple(_same(_json_value(r[k])) for k in key) for r in found}


def _list_written(source: Rows, table: str, rows: list[dict[str, Any]], key: str, mode: str) -> Counts:
    """Rows into a SharePoint list by its client's own calls: create, update and delete (Graph's $batch, 20
    changes a request, retried on 429; SharePoint has no transaction, so a failure says how many were
    refused and the changes before it stay made). An item is found by its id or a column whose values are
    one item each."""
    conn = source.connection
    _, _, name = str(table).rpartition("/")
    if mode == "insert":
        return Counts(inserted=int(conn.create(name, rows)["done"]) if rows else 0)
    if mode == "truncate":
        every, _ = conn.rows(name, columns=["id"])
        ids = [r["id"] for r in (every.to_pylist() if hasattr(every, "to_pylist") else every)]
        gone = int(conn.delete(name, ids)["done"]) if ids else 0
        made = int(conn.create(name, rows)["done"]) if rows else 0
        return Counts(inserted=made, deleted=gone)
    key = key or "id"
    _unique_keys(rows, key)
    if mode == "update":
        return Counts(updated=int(conn.update(name, rows, key)["done"]))
    there = _key_values(source, table, (key,))
    found = [r for r in rows if (_same(_json_value(r[key])),) in there]
    if mode == "delete":
        if not found:
            return Counts()
        ids = conn.ids(name, [r[key] for r in found], key)
        return Counts(deleted=int(conn.delete(name, [ids[r[key]] for r in found])["done"]))
    new = [r for r in rows if (_same(_json_value(r[key])),) not in there]
    updated = int(conn.update(name, found, key)["done"]) if found else 0
    inserted = int(conn.create(name, new)["done"]) if new else 0
    return Counts(inserted=inserted, updated=updated)


_FILES = ("parquet", "csv")


def _lake_place(conn: Any, table: str) -> tuple[dict[str, Any] | None, str, str]:
    """A lake table's entry (None: not there yet), its path and its kind (delta, or a file's format)."""
    schema, _, name = str(table).rpartition("/")
    stem, _, suffix = name.rpartition(".")
    for wanted in (name, stem) if suffix.lower() in _FILES and stem else (name,):
        try:
            found = conn.table(wanted, schema)
        except Exception:  # noqa: S112 (the lake's own "no table": tried by its other name, else a new one)
            continue
        return dict(found), str(found["path"]), str(found.get("kind") or "")
    kind = suffix.lower() if suffix.lower() in _FILES and stem else "delta"
    return None, str(conn.target_path(name, schema)), kind


def _delta_condition(rows: list[dict[str, Any]], key: Sequence[str]) -> str:
    """The rows' keys as one SQL condition (a Delta delete's predicate)."""

    def literal(value: Any) -> str:
        value = _json_value(value)
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            return repr(value)
        return "'" + str(value).replace("'", "''") + "'"

    def name(column: str) -> str:
        return column if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column) else quote(column)

    distinct = list(dict.fromkeys(tuple(r[k] for k in key) for r in rows))
    if len(key) == 1:
        values = [v[0] for v in distinct if v[0] is not None]
        said = [f"{name(key[0])} IN ({', '.join(literal(v) for v in values)})"] if values else []
        said += [f"{name(key[0])} IS NULL"] if len(values) < len(distinct) else []
        return " OR ".join(said)
    return " OR ".join(
        "(" + " AND ".join(f"{name(k)} IS NULL" if v is None else f"{name(k)} = {literal(v)}"
                           for k, v in zip(key, one, strict=True)) + ")"
        for one in distinct
    )  # fmt: skip


def _lake_written(source: Rows, table: str, data: pa.Table, key: list[str], mode: str) -> Counts:
    """Rows into a lake: a Delta table by the deltalake package (one commit each: append, overwrite, merge
    by keys, delete by the keys' condition), or one Parquet or CSV file put in its place whole (truncate;
    an insert reads the file and writes it again with the rows added)."""
    conn = source.connection
    entry, path, kind = _lake_place(conn, table)
    if entry is None and mode not in ("insert", "truncate"):
        raise AdapterError(f"{source.name} has no table {table!r}.")
    rows = data.to_pylist() if mode in ("update", "delete") else []
    before = 0
    if mode == "truncate" and entry is not None:
        before = int(
            read(source, table, Plan(totals=(Total("count"),)))[0].read_all().column(0)[0].as_py() or 0
        )
    if not data.num_columns and entry is not None:  # a truncate with no rows: the table's own columns
        data = read(source, table, Plan(limit=0))[0].read_all()
    if kind == "delta":
        if mode == "insert":
            done = conn.write_delta(path, data, "append")
            return Counts(inserted=int(done.get("written", data.num_rows)))
        if mode == "truncate":
            conn.write_delta(path, data, "overwrite")
            return Counts(inserted=data.num_rows, deleted=before)
        if mode == "delete":
            condition = _delta_condition(rows, key)
            return (
                Counts(deleted=int(conn.delete_delta(path, condition)["deleted"])) if condition else Counts()
            )
        if mode == "update":  # a merge of only the rows whose keys are there
            there = _key_values(source, table, key)
            keep = [i for i, r in enumerate(rows) if tuple(_same(_json_value(r[k])) for k in key) in there]
            if not keep:
                return Counts()
            data = data.take(pa.array(keep, pa.int64()))
        done = conn.write_delta(path, data, "merge", key)
        return Counts(inserted=int(done.get("inserted", 0)), updated=int(done.get("updated", 0)))
    if kind in _FILES or (
        entry is not None and str(entry.get("format")) in _FILES and kind == entry.get("format")
    ):
        fmt = kind if kind in _FILES else str(entry.get("format") if entry else "parquet")
        if mode == "truncate":
            conn.write_file(path, data, fmt)
            return Counts(inserted=data.num_rows, deleted=before)
        if mode == "insert":
            whole = data
            if entry is not None:
                old = read(source, table)[0].read_all()
                whole = pa.concat_tables([old, data], promote_options="default")
            conn.write_file(path, whole, fmt)
            return Counts(inserted=data.num_rows)
        raise AdapterError(
            f"{table} is one {fmt} file: it is written whole (truncate) or added to (insert), not {mode}d."
        )
    raise AdapterError(
        f"{table} is a folder of {kind or 'files'}: write it as a Delta table, or as one file."
    )


# ----- files: a file connection's CSV, Parquet and JSON files (one, or a folder of them) -----

FILE_FORMATS = {".csv": "csv", ".tsv": "csv", ".txt": "csv", ".parquet": "parquet", ".json": "json",
                ".jsonl": "json", ".ndjson": "json"}  # fmt: skip
_READERS = {"csv": "read_csv", "parquet": "read_parquet", "json": "read_json"}


class Files:
    """A file connection as a source: one CSV, Parquet or JSON file, or a folder of them, each a table named
    by its path below the folder without its suffix (sales/orders). A read is DuckDB over the file (the whole
    plan folded, streamed); query is DuckDB SQL with every file a view by its name; a write puts a file
    in its place whole (truncate) or adds to it (insert, the file read and written again), in its suffix's
    format: a new name takes a suffix (orders.parquet). A write may say its file's format (a name with no
    suffix of one), DuckDB COPY's options (DELIMITER ';', ARRAY true, COMPRESSION zstd) and, for a folder of
    Parquet files, its partition columns (a write then fills the folder: truncate replaces it, insert
    adds)."""

    def __init__(
        self, path: str, name: str = "", format: str = "", options: str = "", partition_by: Sequence[str] = ()
    ) -> None:
        import pathlib

        self.path = pathlib.Path(path)
        self.name = name or self.path.name
        self.format, self.options, self.partition_by = format, options, tuple(partition_by)

    def _files(self) -> dict[str, Any]:
        if self.path.is_file():
            return {self.path.stem: self.path}
        if not self.path.is_dir():
            raise AdapterError(f"{self.name} reaches no file or folder ({self.path}).")
        found: dict[str, Any] = {}
        for file in sorted(self.path.rglob("*")):
            if file.is_file() and file.suffix.lower() in FILE_FORMATS and not file.name.startswith("."):
                relative = file.relative_to(self.path).with_suffix("").as_posix()
                found.setdefault(relative, file)
        return found

    def _file(self, table: str) -> Any:
        files = self._files()
        wanted = str(table).replace("\\", "/").casefold()
        stem, _, suffix = wanted.rpartition(".")
        for name, file in files.items():
            if name.casefold() in (wanted, stem if "." + suffix in FILE_FORMATS else wanted):
                return file
        raise AdapterError(f"{self.name} has no table {table!r}.")

    @staticmethod
    def _relation(file: Any) -> str:
        reader = _READERS[FILE_FORMATS[file.suffix.lower()]]
        return f"{reader}('{str(file).replace(chr(39), chr(39) * 2)}')"

    @contextlib.contextmanager
    def _duck(self, writing: bool = False) -> Iterator[Any]:
        con = duckdb.connect()
        try:
            yield con
        finally:
            con.close()

    def tables(self) -> list[Table]:
        listed = []
        with self._duck() as con:
            for name, file in self._files().items():
                described = con.sql(f"DESCRIBE SELECT * FROM {self._relation(file)}").fetchall()  # noqa: S608
                columns = tuple(Column(str(c[0]), str(c[1]), nullable=True) for c in described)
                schema = name.rpartition("/")[0]
                listed.append(Table(name, columns, schema, FILE_FORMATS[file.suffix.lower()]))
        return listed

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, Folded]:
        relation = self._relation(self._file(table))

        def run(con: Any, _table: str, asked: Plan) -> tuple[str, Any]:
            return plan_sql(f"(SELECT * FROM {relation})", asked)  # noqa: S608 (the path quoted)

        return _stream(self._duck, run, table, plan), Folded(plan.parts())

    def query(self, sql: str, params: Params = ()) -> pa.RecordBatchReader:
        """DuckDB SQL over the files, each a view named by its table name ("sales/orders" as sales_orders)."""
        if not reads_only(sql):
            raise AdapterError(f"{self.name}'s files are read by query: write a file with write().")
        views = {re.sub(r"\W", "_", n): f for n, f in self._files().items()}

        def run(con: Any, _table: str, _plan: Plan) -> tuple[str, Any]:
            for view, file in views.items():
                con.execute(f"CREATE TEMP VIEW {quote(view)} AS SELECT * FROM {self._relation(file)}")  # noqa: S608
            return sql, _given(params)

        return _stream(self._duck, run, "", Plan())

    def write(self, table: str, batches: pa.RecordBatchReader, key: Sequence[str], mode: str) -> Counts:
        import os
        import pathlib

        _checked_write(mode, key)
        if self.partition_by:
            return self._folder_written(batches, mode)
        try:
            file = self._file(table)
        except AdapterError:
            if mode not in ("insert", "truncate"):
                raise
            base = self.path if self.path.is_dir() else self.path.parent
            file = base / pathlib.Path(str(table).replace("\\", "/"))
            if file.suffix.lower() not in FILE_FORMATS and not self.format:
                raise AdapterError(
                    f"A new file is named with its format: {table}.parquet, .csv or .json."
                ) from None
        if mode not in ("insert", "truncate"):
            raise AdapterError(
                f"{table} is one file: it is written whole (truncate) or added to (insert), not {mode}d."
            )
        fmt = self.format or FILE_FORMATS[file.suffix.lower()]
        copy = (
            f"(FORMAT {fmt}{', HEADER' if fmt == 'csv' else ''}{', ' + self.options if self.options else ''})"
        )
        data = batches.read_all()
        before = 0
        relation = f"{_READERS[fmt]}('{str(file).replace(chr(39), chr(39) * 2)}')"
        with self._duck(True) as con:
            existing = file.exists()
            if existing:
                before = int(con.sql(f"SELECT count(*) FROM {relation}").fetchall()[0][0])  # noqa: S608
            if not data.num_columns and existing:  # a truncate with no rows: the file's own columns
                data = con.sql(f"SELECT * FROM {relation} LIMIT 0").to_arrow_table()  # noqa: S608
            con.register("sab_rows", data)
            rows = "SELECT * FROM sab_rows"
            if mode == "insert" and existing:
                rows = f"SELECT * FROM {relation} UNION ALL BY NAME SELECT * FROM sab_rows"  # noqa: S608
            file.parent.mkdir(parents=True, exist_ok=True)
            partial = file.with_name(f".{file.name}.sab-writing")
            try:
                con.execute(f"COPY ({rows}) TO '{str(partial).replace(chr(39), chr(39) * 2)}' {copy}")
                os.replace(partial, file)
            finally:
                if partial.exists():
                    partial.unlink()
        return Counts(inserted=data.num_rows, deleted=before if mode == "truncate" else 0)

    def _folder_written(self, batches: pa.RecordBatchReader, mode: str) -> Counts:
        """A folder of Parquet files, a folder for each value of the partition columns: written beside, then
        put in the folder's place (truncate) or its files moved in (insert); a failure leaves it as it was."""
        import os
        import shutil

        if mode not in ("insert", "truncate"):
            raise AdapterError(
                f"{self.name} is a folder of files: it is replaced (truncate) or added to (insert)."
            )
        data = batches.read_all()
        missing = [c for c in self.partition_by if c not in data.column_names]
        if missing:
            raise AdapterError(f"The rows have no {missing[0]} column to partition by.")
        partial = self.path.with_name(f".{self.path.name}.sab-writing")
        parts = ", ".join(quote(c) for c in self.partition_by)
        options = f", {self.options}" if self.options else ""
        try:
            with self._duck(True) as con:
                con.register("sab_rows", data)
                con.execute(
                    f"COPY (SELECT * FROM sab_rows) TO '{str(partial).replace(chr(39), chr(39) * 2)}' "  # noqa: S608 (the path and columns quoted)
                    f"(FORMAT parquet{options}, PARTITION_BY ({parts}), FILENAME_PATTERN 'data_{{uuid}}')"
                )
            if mode == "insert" and self.path.exists():
                for made in sorted(p for p in partial.rglob("*") if p.is_file()):
                    place = self.path / made.relative_to(partial)
                    place.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(made, place)
            else:
                if self.path.exists():
                    shutil.rmtree(self.path)
                os.replace(partial, self.path)
        finally:
            shutil.rmtree(partial, ignore_errors=True)
        return Counts(inserted=data.num_rows)


# ----- a workbook: an Excel file's sheets and named tables (openpyxl, imported only when one is used) -----

WORKBOOKS = (".xlsx", ".xlsm")
SHEET_ROWS = 1_048_576  # the rows one sheet holds, its header too
EXCEL_DIGITS = 15  # the digits of a number Excel keeps: a longer whole number is written as text
EXCEL_FIRST_DAY = (1900, 3, 1)  # an earlier date reads back as another day: written as text
SAMPLE_ROWS = 1_000  # the rows tables() types a column from (a read types every row)
_ARROW_NAMES = {"int64": "BIGINT", "double": "DOUBLE", "bool": "BOOLEAN", "string": "VARCHAR",
                "timestamp[us]": "TIMESTAMP", "date32[day]": "DATE", "time64[us]": "TIME"}  # fmt: skip
_PACKAGE = re.compile(r"<(?:\w+:)?(sheet|Relationship|table)\b[^>]*>")
_ATTRIBUTE = re.compile(r"([\w:]+)=\"([^\"]*)\"")


def _openpyxl() -> Any:
    """openpyxl, imported on a workbook's first use; missing, said in one sentence with its fix."""
    try:
        import openpyxl
    except ModuleNotFoundError:
        raise ModuleNotFoundError(
            "An Excel workbook is read and written with openpyxl, which this Python does not have: "
            "pip install openpyxl",
            name="openpyxl",
        ) from None
    return openpyxl


def header_names(cells: Sequence[Any]) -> list[str]:
    """A header row's cells as unique column names: a blank one is column_<n>, a repeat gets _2 (a repeat in
    another case too: DuckDB matches names without case)."""
    names: list[str] = []
    taken: set[str] = set()
    for n, cell in enumerate(cells, start=1):
        base = str(cell).strip() if cell is not None and str(cell).strip() else f"column_{n}"
        name, k = base, 2
        while name.casefold() in taken:
            name, k = f"{base}_{k}", k + 1
        names.append(name)
        taken.add(name.casefold())
    return names


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict | list | tuple):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def typed(values: Sequence[Any]) -> pa.Array:
    """One column's values as Arrow, by the one rule for a sheet's cells: numbers (whole, or DOUBLE), text,
    dates and times, yes/no as Arrow reads them; a column that mixes kinds (a number column with an "n/a"
    in it) keeps every value, as text."""
    try:
        return pa.array(values)
    except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError):
        return pa.array([_as_text(v) for v in values], pa.string())


def _one_type(chunks: Sequence[pa.Array]) -> pa.ChunkedArray:
    """A column's chunks (each typed alone, as it was read) as one type: the same rule over the whole."""
    kinds = {c.type for c in chunks if c.type != pa.null()}
    target = pa.string()
    if len(kinds) == 1:
        target = next(iter(kinds))
    elif kinds and kinds <= {pa.int64(), pa.float64()}:
        target = pa.float64()
    made = []
    for chunk in chunks:
        if chunk.type == target:
            made.append(chunk)
        elif chunk.type == pa.null() or target == pa.float64():
            made.append(chunk.cast(target))
        else:
            made.append(pa.array([_as_text(v) for v in chunk.to_pylist()], pa.string()))
    return pa.chunked_array(made, target)


def sheet_value(value: Any) -> tuple[Any, bool]:
    """A value as a sheet's cell holds it, and whether it is a text cell (text is never a formula): a whole
    number of more digits than Excel keeps, a date before 1900-03-01 and a time with a zone are written as
    text, exact; a decimal as a number; a list or a record as JSON."""
    if value is None or isinstance(value, bool):
        return value, False
    if isinstance(value, int):
        return (value, False) if abs(value) < 10**EXCEL_DIGITS else (str(value), True)
    if isinstance(value, float):
        number = float(value)  # numpy's float64 as Python's own
        return (number, False) if number == number and abs(number) != float("inf") else (repr(number), True)
    if isinstance(value, str):
        return _sheet_text(value), True
    if hasattr(value, "as_tuple"):  # a decimal: a number while Excel keeps its digits
        fits = value.is_finite() and len(value.as_tuple().digits) <= EXCEL_DIGITS
        return (float(value), False) if fits else (str(value), True)
    if hasattr(value, "year"):  # a date, or a date and time
        if value != value:  # pandas' missing time: a blank cell
            return None, False
        zoned = getattr(value, "tzinfo", None) is not None
        early = (value.year, value.month, value.day) < EXCEL_FIRST_DAY
        return (value.isoformat(), True) if zoned or early else (value, False)
    if hasattr(value, "hour") or hasattr(value, "total_seconds"):  # a time of day, a duration
        return value, False
    if hasattr(value, "item") and not isinstance(value, bytes | dict | list | tuple):  # numpy's scalars
        with contextlib.suppress(TypeError, ValueError):
            return sheet_value(value.item())
    return _sheet_text(str(_as_text(value))), True


_UNWRITABLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]|_(?=x[0-9A-Fa-f]{4}_)")


def _sheet_text(text: str) -> str:
    """Text as a workbook's file holds it: a character XML cannot hold as Excel's own _xHHHH_ (a literal
    _xHHHH_ kept literal), so Excel shows the text as it was."""
    return _UNWRITABLE.sub(lambda m: f"_x{ord(m.group(0)):04X}_", text) if _UNWRITABLE.search(text) else text


def _listed_parts(archive: Any, part: str) -> list[dict[str, str]]:
    """The sheet, Relationship and table tags of one part of a workbook's file, each as its attributes
    (its tag under "")."""
    import html

    if part not in archive.namelist():
        return []
    text = archive.read(part).decode("utf-8", "replace")
    return [
        {k: html.unescape(v) for k, v in _ATTRIBUTE.findall(m.group(0))} | {"": m.group(1)}
        for m in _PACKAGE.finditer(text)
    ]


class Excel:
    """A workbook as a source: a path, or its bytes (an upload's, a SharePoint document's). Each sheet is a
    table and each named table (Insert > Table) too, by its own name. A read takes the first row as the
    column names (`header_row`: another; `cells`: a range such as B3:F40 instead of the whole sheet), a
    formula's last result as its value, and types each column by one rule (typed); columns and a limit are
    folded. A write puts rows into a sheet, the other sheets kept: added below its rows by its header's
    names (insert; a new sheet, or a new workbook, gets the column names on top) or in the sheet's place
    (truncate); written beside the file, then put in its place. Bytes written are `data`, the new bytes."""

    def __init__(self, workbook: Any, name: str = "", header_row: int = 1, cells: str = "") -> None:
        import pathlib

        held = isinstance(workbook, bytes | bytearray | memoryview)
        self.data: bytes | None = bytes(workbook) if held else None
        self.path: Any = None if held else pathlib.Path(workbook)
        self.name = name or (self.path.name if self.path else "The workbook")
        self.header_row, self.cells = max(1, int(header_row)), str(cells or "").strip()

    # --- the workbook, opened ---

    def _file(self) -> Any:
        import io

        if self.data is not None:
            return io.BytesIO(self.data)
        if self.path.suffix.lower() == ".xls":
            raise AdapterError(f"{self.name} is an older .xls workbook: save it as .xlsx first.")
        if not self.path.is_file():
            raise AdapterError(f"{self.name} reaches no file ({self.path}).")
        return str(self.path)

    @contextlib.contextmanager
    def _book(self, writing: bool = False) -> Iterator[Any]:
        import zipfile

        openpyxl = _openpyxl()
        macros = self.path is not None and self.path.suffix.lower() == ".xlsm"
        try:
            if writing:
                book = openpyxl.load_workbook(self._file(), keep_vba=macros)
            else:
                book = openpyxl.load_workbook(self._file(), read_only=True, data_only=True)
        except (zipfile.BadZipFile, KeyError, ValueError, OSError) as error:
            raise AdapterError(f"Could not read {self.name} as an Excel workbook: {error}") from error
        try:
            yield book
        finally:
            book.close()

    def _parts(self) -> list[tuple[str, str, str]]:
        """(name, sheet, cells) of each sheet, then of each named table, from the file's own lists (no cell
        is read). A named table called as a sheet is found by the sheet."""
        import posixpath
        import zipfile

        try:
            archive = zipfile.ZipFile(self._file())
        except (zipfile.BadZipFile, OSError) as error:
            raise AdapterError(f"Could not read {self.name} as an Excel workbook: {error}") from error
        sheets, named = [], []
        with archive:
            rels = _listed_parts(archive, "xl/_rels/workbook.xml.rels")
            targets = {r.get("Id"): r.get("Target", "") for r in rels}
            for sheet in (s for s in _listed_parts(archive, "xl/workbook.xml") if s[""] == "sheet"):
                title = sheet.get("name", "")
                sheets.append((title, title, ""))
                target = targets.get(sheet.get("r:id"), "")
                part = target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
                folder, _, file = posixpath.normpath(part).rpartition("/")
                for rel in _listed_parts(archive, f"{folder}/_rels/{file}.rels"):
                    if not rel.get("Type", "").endswith("/table"):
                        continue
                    place = posixpath.normpath(posixpath.join(folder, rel.get("Target", ""))).lstrip("/")
                    for table in (t for t in _listed_parts(archive, place) if t[""] == "table"):
                        called = table.get("displayName") or table.get("name", "")
                        named.append((called, title, table.get("ref", "")))
        taken = {s[0].casefold() for s in sheets}
        return sheets + [n for n in named if n[0] and n[0].casefold() not in taken]

    def _place(self, table: str) -> tuple[str, str, str]:
        parts = self._parts()
        names = ", ".join(p[0] for p in parts)
        if not str(table or "").strip():
            if len(parts) != 1:
                what = "sheets and named tables" if any(p[2] for p in parts) else "sheets"
                raise AdapterError(f"{self.name} has {len(parts)} {what} ({names}): name the one to read.")
            return parts[0]
        for part in parts:
            if part[0].casefold() == str(table).strip().casefold():
                return part
        raise AdapterError(f"{self.name} has no sheet or named table {str(table)!r}. It has: {names}.")

    # --- tables and read ---

    def tables(self) -> list[Table]:
        listed = []
        parts = self._parts()
        with self._book() as book:
            for name, sheet, cells in parts:
                found = self._rows(book, (name, sheet, cells), (), SAMPLE_ROWS, empty=True)
                columns = tuple(
                    Column(f.name, _ARROW_NAMES.get(str(f.type), str(f.type).upper()), nullable=True)
                    for f in found.schema
                )
                words = f"A named table on the sheet {sheet} ({cells})." if cells else ""
                kind = "named table" if cells else "sheet"
                listed.append(Table(name, columns, kind=kind, description=words))
        return listed

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, Folded]:
        folded: list[str] = []
        for part in plan.parts():
            if part not in ("columns", "limit"):
                break
            folded.append(part)
        place = self._place(table)
        columns = plan.columns if "columns" in folded else ()
        with self._book() as book:
            found = self._rows(book, place, columns, plan.limit if "limit" in folded else None)
        return found.to_reader(BATCH_ROWS), Folded(tuple(folded))

    def _rows(
        self,
        book: Any,
        place: tuple[str, str, str],
        columns: Sequence[str],
        limit: int | None,
        empty: bool = False,
    ) -> pa.Table:
        """A sheet's (or a range's) rows as one Arrow table: read once, a batch of rows typed at a time, so
        a large sheet is held as Arrow, never as Python values. Blank rows inside the data are kept, the
        blank rows a sheet often reports after it are not; a column with no name and no value is left out."""
        name, sheet, cells = place
        left, top, right, bottom = self._bounds(cells or self.cells)
        first = top if cells else top + self.header_row - 1
        rows = book[sheet].iter_rows(
            min_row=first, max_row=bottom, min_col=left, max_col=right, values_only=True
        )
        header = list(next(rows, None) or [])
        if all(c is None for c in header):
            if empty:
                return pa.table({})
            raise AdapterError(f"{name} of {self.name} is empty.")
        names = header_names(header)
        picks = list(range(len(names)))
        if columns:
            missing = [c for c in columns if c not in names]
            if missing:
                raise AdapterError(f"{name} has no column {missing[0]!r}. It has: {', '.join(names)}.")
            picks = [names.index(c) for c in columns]
        chunks: list[list[pa.Array]] = [[] for _ in picks]
        held: list[Sequence[Any]] = []
        blank = count = 0
        for row in rows:
            if limit is not None and count >= limit:
                break
            if all(value is None for value in row):
                blank += 1
                continue
            if limit is not None and count + blank >= limit:  # the limit ends among blank rows
                held.extend([()] * (limit - count))
                break
            held.extend([()] * blank)  # the blank rows before this one: inside the data
            held.append(row)
            count, blank = count + blank + 1, 0
            if len(held) >= BATCH_ROWS:
                _typed_into(chunks, picks, held)
        _typed_into(chunks, picks, held)
        made = {names[pick]: _one_type(chunks[at]) for at, pick in enumerate(picks)}
        if not columns:  # a column with no header and no value: not a column of the table
            made = {
                names[at]: column
                for at, column in enumerate(made.values())
                if header[at] is not None or column.null_count < len(column)
            }
        return pa.table(made)

    def _bounds(self, cells: str) -> tuple[int | None, int, int | None, int | None]:
        if not cells:
            return None, 1, None, None
        from openpyxl.utils import range_boundaries

        try:
            left, top, right, bottom = range_boundaries(cells.replace("$", ""))
        except (ValueError, TypeError):
            raise AdapterError(f"{cells!r} is not a range of cells: write it like B3:F40.") from None
        return left, top or 1, right, bottom

    # --- write ---

    def write(self, table: str, batches: pa.RecordBatchReader, key: Sequence[str], mode: str) -> Counts:
        _checked_write(mode, key)
        if mode not in ("insert", "truncate"):
            raise AdapterError(
                f"A sheet's rows are added to (insert) or replaced (truncate), not {mode}d: read it, "
                "change the rows in DuckDB, and write it whole."
            )
        openpyxl = _openpyxl()
        data = batches.read_all()
        if self.data is None and not self.path.is_file():
            book = openpyxl.Workbook()
            book.remove(book.active)
            return self._written(book, table, data, mode)
        with self._book(writing=True) as book:
            return self._written(book, table, data, mode)

    def _written(self, book: Any, table: str, data: pa.Table, mode: str) -> Counts:
        title = next((s for s in book.sheetnames if s.casefold() == str(table).casefold()), "")
        names = list(data.column_names)
        before = 0
        if title and mode == "truncate":
            at = book.sheetnames.index(title)
            before = max(0, int(book[title].max_row or 0) - 1)
            book.remove(book[title])
            sheet = book.create_sheet(title, at)
        elif title:
            sheet = book[title]
        elif not str(table).strip() or len(str(table)) > 31:
            raise AdapterError("A sheet's name is 1 to 31 characters.")
        else:
            sheet = book.create_sheet(str(table))
        header = [c.value for c in next(sheet.iter_rows(min_row=1, max_row=1), ())]
        if any(c is not None for c in header):
            held = header_names(header)
            missing = [n for n in names if n not in held]
            if missing:
                raise AdapterError(f"{sheet.title} has no column {missing[0]!r}. It has: {', '.join(held)}.")
            places = [held.index(n) + 1 for n in names]
            row = int(sheet.max_row or 1)
        else:
            places = list(range(1, len(names) + 1))
            row = 1
            for place, name in zip(places, names, strict=True):
                sheet.cell(row=1, column=place, value=name).data_type = "s"
        if row + data.num_rows > SHEET_ROWS:
            raise AdapterError(f"{sheet.title} would hold more than the {SHEET_ROWS:,} rows of one sheet.")
        for batch in data.to_batches(BATCH_ROWS):
            for place, column in zip(places, batch.columns, strict=True):
                _sheet_column(sheet, row, place, column.to_pylist())
            row += batch.num_rows
        self._saved(book)
        return Counts(inserted=data.num_rows, deleted=before)

    def _saved(self, book: Any) -> None:
        """The workbook written beside its file, then put in its place (a failure leaves it as it was)."""
        import io
        import os

        if self.path is None:
            out = io.BytesIO()
            book.save(out)
            self.data = out.getvalue()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_name(f".{self.path.name}.sab-writing")
        try:
            book.save(str(partial))
            os.replace(partial, self.path)
        except PermissionError as error:
            raise AdapterError(
                f"Nothing was written to {self.name}: {error} (is the workbook open in Excel?)"
            ) from error
        finally:
            if partial.exists():
                partial.unlink()


def _typed_into(chunks: list[list[pa.Array]], picks: Sequence[int], held: list[Sequence[Any]]) -> None:
    """The rows held so far as one typed chunk a column (a short row's missing cells blank), then let go."""
    for at, pick in enumerate(picks):
        chunks[at].append(typed([r[pick] if pick < len(r) else None for r in held]))
    held.clear()


def _sheet_column(sheet: Any, after: int, place: int, values: Sequence[Any]) -> None:
    """One column's values into the rows after `after`: each as sheet_value says, text never a formula."""
    for at, value in enumerate(values, start=1):
        if value is None:
            continue
        held, text = sheet_value(value)
        cell = sheet.cell(row=after + at, column=place, value=held)
        if text:
            cell.data_type = "s"


# ===== 3. The calls =====

_find: Callable[[str], Source] | None = None
_OBSERVERS: list[Callable[[dict[str, Any]], Any]] = []


# Each call's facts, for the statistics (Plans/stats.plan.md): handed to observe()'s hook as the call ends
# (a read's or a query's when its stream ends or is dropped). Never a value: names, times, sizes, the
# result's fingerprint (its columns' names and types, hashed). No hook: nothing is timed or wrapped.


def observe(hook: Callable[[dict[str, Any]], Any] | None) -> None:
    """A hook handed each read's, query's and write's facts as it ends:
    {"call": read | query | write, "source", "kind" (the source's class), "table", "mode" (a write's),
     "ms": {"connect" (a name found: its source made), "first_row", "total"},
     "size": {"rows", "bytes", "batches", "columns" (returned), "asked" (columns the plan named; 0: all)},
     "folded": the plan's parts the source took, "by_duckdb": the parts DuckDB did after,
     "outcome": {"ok", "error": its kind (the exception's class), never its words}, "fingerprint"}.
    None: no hook (the default). A hook that fails never fails a call."""
    _OBSERVERS.clear()
    if hook is not None:
        _OBSERVERS.append(hook)


def fingerprint(schema: pa.Schema) -> str:
    """A result's shape in 12 characters: its columns' names and types, hashed (never a value)."""
    said = "|".join(f"{f.name}:{f.type}" for f in schema)
    return hashlib.sha1(said.encode(), usedforsecurity=False).hexdigest()[:12]


class _Timed:
    """One call's facts while it runs; made only while observe() has a hook."""

    def __init__(self, call: str, source: str | Source, table: str, asked: int, mode: str) -> None:
        self.began = time.perf_counter()
        self.facts: dict[str, Any] = {
            "call": call,
            "source": source if isinstance(source, str) else str(getattr(source, "name", "") or ""),
            "kind": "" if isinstance(source, str) else type(source).__name__,
            "table": str(table),
            "mode": mode,
            "ms": {"connect": None, "first_row": None, "total": None},
            "size": {"rows": 0, "bytes": 0, "batches": 0, "columns": 0, "asked": asked},
            "folded": [],
            "by_duckdb": [],
            "outcome": {"ok": True, "error": ""},
            "fingerprint": "",
        }
        self.told = False

    @classmethod
    def start(cls, call: str, source: str | Source, table: str, asked: int, mode: str = "") -> _Timed | None:
        return cls(call, source, table, asked, mode) if _OBSERVERS else None

    def ms(self) -> float:
        return round((time.perf_counter() - self.began) * 1000, 2)

    @staticmethod
    def failed(timed: _Timed | None, error: BaseException) -> None:
        if timed is not None:
            timed.facts["outcome"] = {"ok": False, "error": type(error).__name__}
            timed.tell()

    def tell(self) -> None:
        if self.told:
            return
        self.told = True
        self.facts["ms"]["total"] = self.ms()
        for hook in list(_OBSERVERS):
            try:
                hook(self.facts)
            except Exception:  # noqa: S110 (a statistics hook never fails a call)
                pass

    def counted(self, batch: pa.RecordBatch) -> None:
        size = self.facts["size"]
        if size["batches"] == 0:
            self.facts["ms"]["first_row"] = self.ms()
        size["batches"] += 1
        size["rows"] += batch.num_rows
        size["bytes"] += batch.get_total_buffer_size()

    def streamed(
        self, reader: pa.RecordBatchReader, folded: Sequence[str], rest: Sequence[str]
    ) -> pa.RecordBatchReader:
        """The stream as it was, counted batch by batch; its facts told when it ends (or is dropped)."""
        self.facts["folded"], self.facts["by_duckdb"] = list(folded), list(rest)
        self.facts["size"]["columns"] = len(reader.schema)
        self.facts["fingerprint"] = fingerprint(reader.schema)
        return pa.RecordBatchReader.from_batches(reader.schema, self._counting(reader))

    def _counting(self, reader: pa.RecordBatchReader) -> Iterator[pa.RecordBatch]:
        try:
            for batch in reader:
                self.counted(batch)
                yield batch
        except Exception as error:
            self.facts["outcome"] = {"ok": False, "error": type(error).__name__}
            raise
        finally:
            self.tell()

    def taking(self, given: pa.RecordBatchReader | pa.Table) -> None:
        """A write's columns and shape; its rows' bytes when given whole (a stream is never wrapped: DuckDB
        takes Arrow natively, a Python generator would cost it its parallel read)."""
        self.facts["size"]["columns"] = len(given.schema)
        self.facts["fingerprint"] = fingerprint(given.schema)
        if isinstance(given, pa.Table):
            self.facts["size"]["bytes"] = given.get_total_buffer_size()

    def wrote(self, counts: Counts) -> None:
        self.facts["size"]["rows"] = counts.rows
        self.tell()


def _found(source: str | Source, timed: _Timed | None) -> Source:
    """source_of, its making timed (connect) when a name is found."""
    found = source_of(source)
    if timed is not None and isinstance(source, str):
        timed.facts["ms"]["connect"] = timed.ms()
        timed.facts["kind"] = type(found).__name__
    return found


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


def listed(source: str | Source) -> list[Table]:
    """The source's whole catalog as the app's Catalog lists it (a SQL database's: its starter's listing,
    every schema but the system's, with descriptions); a source with no listing of its own: its tables()."""
    found = source_of(source)
    whole = getattr(found, "listed", None)
    return list(whole()) if callable(whole) else found.tables()


def _yes(said: Any) -> bool | None:
    """A listing's nullable as a bool (YES, Y, 1, true; NO, N, 0, false), None when it says nothing."""
    if said is None or str(said).strip() == "":
        return None
    return str(said).strip().upper() in ("YES", "Y", "1", "TRUE")


def read(source: str | Source, table: str, plan: Plan | None = None) -> tuple[pa.RecordBatchReader, Folded]:
    """A table read as a stream of Arrow batches, and what the source folded of the plan. What it could not
    fold is done here by DuckDB over the stream (never a copy of the whole read)."""
    asked = plan or Plan()
    check_plan(asked)
    timed = _Timed.start("read", source, table, len(asked.columns))
    try:
        reader, folded = _found(source, timed).read(table, asked)
        took = [p in folded.parts for p in asked.parts()]
        if any(later and not earlier for earlier, later in itertools.pairwise(took)):
            raise AdapterError(
                "A source folds a plan's parts in the order SQL applies them, never a later one alone."
            )
        rest = folded.rest(asked)
        answer = reader if not rest.parts() else _finished(reader, rest)
    except Exception as error:
        _Timed.failed(timed, error)
        raise
    if timed is None:
        return answer, folded
    return timed.streamed(answer, folded.parts, rest.parts()), folded


def _finished(reader: pa.RecordBatchReader, rest: Plan) -> pa.RecordBatchReader:
    def batches() -> Iterator[Any]:
        con = duckdb.connect()
        try:
            con.register("sab_read", reader)
            texts = [
                f.name
                for f in reader.schema
                if pa.types.is_string(f.type) or pa.types.is_large_string(f.type)
            ]
            sql, params = plan_sql("sab_read", rest, texts)
            finished = con.sql(sql, params=params).to_arrow_reader(BATCH_ROWS)
            yield finished.schema
            yield from finished
        finally:
            con.close()

    made = batches()
    schema = next(made)
    return pa.RecordBatchReader.from_batches(schema, made)


def query(source: str | Source, sql: str, params: Params = ()) -> pa.RecordBatchReader:
    """SQL a plan cannot say (joins, CTEs, a write with RETURNING), in the source's own SQL and its driver's
    marks, answered as Arrow; a statement that returns no rows answers one `count` column. The sandbox makes
    it DuckDB SQL over its tables, so the same statement runs against the real source in an export."""
    timed = _Timed.start("query", source, "", 0)
    try:
        found = _found(source, timed)
        run = getattr(found, "query", None)
        if not callable(run):
            said = getattr(found, "name", "") or type(found).__name__
            raise AdapterError(f"{said} has no SQL of its own: read its tables with a plan (read).")
        answer = run(sql, params)
        if not isinstance(answer, pa.RecordBatchReader):
            answer = answer.to_reader()
    except Exception as error:
        _Timed.failed(timed, error)
        raise
    return answer if timed is None else timed.streamed(answer, (), ())


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
    timed = _Timed.start("write", source, table, 0, mode)
    if timed is not None:
        timed.taking(batches)
    reader = batches if isinstance(batches, pa.RecordBatchReader) else batches.to_reader()
    try:
        found = _found(source, timed)
        counts = found.write(table, reader, tuple(key), mode)
    except Exception as error:
        _Timed.failed(timed, error)
        raise
    if timed is not None:
        timed.wrote(counts)
    return counts


@dataclass(frozen=True)
class Write:
    """One of several writes write_all makes all or none: rows (Arrow, a DataFrame, a list of dicts; None: a
    truncate that only clears) into a table by mode, matched by key."""

    table: str
    rows: Any = None
    key: tuple[str, ...] = ()
    mode: str = "insert"


_ONE_AT_A_TIME = {
    "OData": "Dataverse's Web API keeps all or none to one change set of one table",
    "Rows": "each write is its service's own call",
    "Files": "each file is replaced on its own",
    "Excel": "each sheet is written on its own",
}  # the sources with no transaction across writes, and why


def write_all(
    source: str | Source, writes: Sequence[Write | Mapping[str, Any] | Sequence[Any]]
) -> list[Counts]:
    """Several writes on one source in one transaction: all of them or none (a status set and its audit row
    added). Each is a Write, or its parts ({"table", "rows", "key", "mode"}, or (table, rows, key, mode)).
    Each write's counts, in order. A source without a transaction across writes (Trino, Dataverse's Web API,
    the lakes and SharePoint, files, a workbook) refuses two or more in one sentence, nothing written."""
    given = [_write_of(w) for w in writes]
    if not given:
        return []
    for w in given:
        _checked_write(w.mode, w.key)
        if w.rows is None and w.mode != "truncate":
            raise AdapterError(f"A {w.mode} takes the rows it writes.")
    shown = ", ".join(dict.fromkeys(w.table for w in given))
    timed = _Timed.start("write", source, shown, 0, " + ".join(w.mode for w in given))
    try:
        found = _found(source, timed)
        prepared: list[OneWrite] = [(w.table, _reader_of(w.rows), w.key, w.mode) for w in given]
        if len(prepared) == 1:
            counts = [found.write(*prepared[0])]
        elif callable(getattr(found, "write_all", None)):
            counts = list(found.write_all(prepared))  # type: ignore[attr-defined]
        else:
            said = getattr(found, "name", "") or type(found).__name__
            why = _ONE_AT_A_TIME.get(type(found).__name__, "it has no transaction across writes")
            raise AdapterError(f"{said} cannot make several writes all or none ({why}).")
    except Exception as error:
        _Timed.failed(timed, error)
        raise
    if timed is not None:
        timed.wrote(Counts(*(sum(getattr(c, n) for c in counts) for n in ("inserted", "updated", "deleted"))))
    return counts


def _reader_of(rows: Any) -> pa.RecordBatchReader:
    """A write's rows as a stream: a reader as it is, anything else made Arrow (none: no rows, no columns)."""
    if rows is None:
        return pa.table({}).to_reader()
    return rows if isinstance(rows, pa.RecordBatchReader) else arrow_of(rows).to_reader()


def _write_of(item: Write | Mapping[str, Any] | Sequence[Any]) -> Write:
    if isinstance(item, Mapping):
        parts = [item.get("table"), item.get("rows"), item.get("key"), item.get("mode")]
    elif isinstance(item, Write):
        parts = [item.table, item.rows, item.key, item.mode]
    elif isinstance(item, Sequence) and not isinstance(item, str) and 1 <= len(item) <= 4:
        parts = [*item, None, None, None][:4]
    else:
        raise AdapterError("A write is a Write, {table, rows, key, mode}, or (table, rows, key, mode).")
    table, rows, key, mode = parts
    if not table:
        raise AdapterError("A write names its table.")
    keys = ((key,) if key else ()) if isinstance(key, str) else tuple(str(k) for k in key or ())
    return Write(str(table), rows, keys, str(mode or "insert"))


def planned(
    source: str | Source,
    table: str,
    batches: pa.RecordBatchReader | pa.Table | None = None,
    key: Sequence[str] = (),
    mode: str = "insert",
) -> Counts:
    """What a write would do, nothing written (a Write starter's dry run): an insert's rows; an update's and a
    merge's keys that are there (a merge inserts the rest), a delete's; a truncate's rows now and the rows it
    inserts. Counted by reads through the source, or by the source's own dry run where it has one (SQL
    Server's staged keys); its notes say what to know before writing (Trino's: no transaction)."""
    _checked_write(mode, key)
    found = source_of(source)
    data = (
        pa.table({})
        if batches is None
        else batches.read_all()
        if isinstance(batches, pa.RecordBatchReader)
        else batches
    )
    own = getattr(found, "planned", None)
    if callable(own):
        return own(table, data, tuple(key), mode)  # type: ignore[no-any-return]
    return counted_by_reads(found, table, data, key, mode)


def counted_by_reads(found: Source, table: str, data: pa.Table, key: Sequence[str], mode: str) -> Counts:
    """planned()'s counts by reads through the source: a count for a truncate, the keys that are there."""
    if mode == "insert":
        return Counts(inserted=data.num_rows)
    if mode == "truncate":
        try:
            counted_now = read(found, table, Plan(totals=(Total("count"),)))[0].read_all()
        except Exception:
            if _listed(found, table):
                raise
            return Counts(inserted=data.num_rows)  # a table not there yet: made by the write
        return Counts(inserted=data.num_rows, deleted=int(counted_now.column(0)[0].as_py() or 0))
    there = present(found, table, data, key)
    if mode == "update":
        return Counts(updated=there)
    if mode == "merge":
        return Counts(updated=there, inserted=data.num_rows - there)
    return Counts(deleted=there)


def statements(
    source: str | Source, table: str, names: Sequence[str], key: Sequence[str] = (), mode: str = "insert"
) -> list[str]:
    """What a write of rows with these columns would run, in the source's own SQL, for a dry run's report:
    SQL Server's staging and MERGE, Trino's batch statements; [] when the source does not say."""
    _checked_write(mode, key)
    say = getattr(source_of(source), "statements", None)
    return list(say(table, list(names), list(key), mode)) if callable(say) else []


def _listed(source: Source, table: str) -> bool:
    """Whether the source lists the table (a file's name with or without its suffix)."""
    names = {t.name.casefold() for t in source.tables()}
    wanted = str(table).casefold()
    stem, _, suffix = wanted.rpartition(".")
    return wanted in names or (suffix in _FILES and stem in names)


def present(source: str | Source, table: str, rows: pa.Table, key: Sequence[str]) -> int:
    """How many of the rows' keys the table has (text compared in any case), read through the source: one
    key a hundred values at a time (a filter the source folds), several keys by reading them whole."""
    wanted = [tuple(_same(_json_value(r[k])) for k in key) for r in rows.select(list(key)).to_pylist()]
    if not wanted:
        return 0
    there: set[tuple[Any, ...]] = set()
    if len(key) == 1:
        values = list(dict.fromkeys(_json_value(r[key[0]]) for r in rows.select(list(key)).to_pylist()))
        values = [v for v in values if v is not None]
        for at in range(0, len(values), 100):
            plan = Plan(columns=tuple(key), filters=(Filter(key[0], "in", values[at : at + 100]),))
            found = read(source, table, plan)[0].read_all().to_pylist()
            there |= {(_same(_json_value(r[key[0]])),) for r in found}
    else:
        found = read(source, table, Plan(columns=tuple(key)))[0].read_all().to_pylist()
        there = {tuple(_same(_json_value(r[k])) for k in key) for r in found}
    return sum(1 for w in wanted if w in there)


# ----- one source's calls together: what API.py's connection(name) hands out -----

GONE_CALLS = (
    "cursor",
    "execute",
    "executemany",
    "fetchone",
    "fetchall",
    "fetchmany",
    "commit",
    "rollback",
    "read_arrow",
    "rows",
    "fetch",
    "create",
    "update",
    "delete",
    "ids",
    "for_writes",
    "df",
    "fetch_arrow_table",
)  # fmt: skip  the old per-source clients' calls, said in the adapter's words


class Connection:
    """One source's calls: what `connection(name)` gives an endpoint, here (the sandbox behind it) and in an
    export (the real connection behind it), so the same code runs in both.

        db = connection("Warehouse")
        db.tables()                                   # names, columns, types
        db.read("orders", columns=["id"], filters=[["region", "=", "North"]], sort=[["id", "desc"]], limit=10)
        db.query("SELECT ... JOIN ...", [region])     # its own SQL -> Arrow (a write: its count)
        db.write("orders", rows, key=["id"], mode="merge")   # rows: Arrow, or a list of dicts -> Counts
    """

    def __init__(self, source: str | Source, name: str = "") -> None:
        self._source = source
        self.name = name or (source if isinstance(source, str) else str(getattr(source, "name", "") or ""))

    @property
    def source(self) -> Source:
        return source_of(self._source)

    def tables(self) -> list[Table]:
        return tables(self.source)

    def columns(self, table: str) -> list[Column]:
        """A table's columns (its name in any case)."""
        wanted = str(table).casefold()
        for found in self.tables():
            if found.name.casefold() == wanted:
                return list(found.columns)
        raise AdapterError(f"{self.name or 'The source'} has no table {table!r}.")

    def read(
        self,
        table: str,
        plan: Plan | Mapping[str, Any] | None = None,
        *,
        columns: Sequence[str] = (),
        filters: Sequence[Any] = (),
        sort: Sequence[Any] = (),
        limit: int | None = None,
        offset: int = 0,
    ) -> pa.RecordBatchReader:
        """A table's rows as Arrow: a Plan, or its parts by name (filters as [column, op, value], sort as
        [column, "asc" | "desc"])."""
        if plan is None:
            plan = plan_from(
                {"columns": list(columns), "filters": [list(f) for f in filters], "limit": limit,
                 "offset": offset, "sort": [s if isinstance(s, str) else list(s) for s in sort]}
            )  # fmt: skip
        elif not isinstance(plan, Plan):
            plan = plan_from(plan)
        return read(self.source, table, plan)[0]

    def query(self, sql: str, params: Params = ()) -> pa.RecordBatchReader:
        return query(self.source, sql, params)

    def write(
        self,
        table: str,
        rows: pa.Table | pa.RecordBatchReader | Sequence[Mapping[str, Any]] | None = None,
        key: Sequence[str] = (),
        mode: str = "insert",
    ) -> Counts:
        """Rows (Arrow, or a list of dicts) into a table by mode; the counts."""
        given: pa.Table | pa.RecordBatchReader | None = None
        if rows is not None:
            given = (
                rows
                if isinstance(rows, pa.Table | pa.RecordBatchReader)
                else pa.Table.from_pylist([dict(r) for r in rows])
            )
        return write(self.source, table, given, key, mode)

    def write_all(self, writes: Sequence[Write | Mapping[str, Any] | Sequence[Any]]) -> list[Counts]:
        """Several writes in one transaction, all or none (write_all): each a Write, {table, rows, key, mode}
        or (table, rows, key, mode); each one's counts."""
        return write_all(self.source, writes)

    def planned(
        self,
        table: str,
        rows: pa.Table | pa.RecordBatchReader | Sequence[Mapping[str, Any]] | None = None,
        key: Sequence[str] | str = (),
        mode: str = "insert",
    ) -> Counts:
        """What write(table, rows, key, mode) would do, nothing written (planned): the counts it would give,
        and its notes. For a keyed mode the key columns alone are enough."""
        keys = ((key,) if key else ()) if isinstance(key, str) else tuple(key)
        given = None if rows is None else _reader_of(rows)
        return planned(self.source, table, given, keys, mode)

    def __getattr__(self, name: str) -> Any:
        if name in GONE_CALLS:
            raise AttributeError(
                f"connection({self.name!r}) has no {name}(): it is the adapter's now: query(sql, params), "
                "read(table, columns=, filters=, sort=, limit=), write(table, rows, key, mode), tables()."
            )
        raise AttributeError(f"'Connection' object has no attribute {name!r}")


_DRIVERS = {
    "sqlite3": "sqlite",
    "psycopg": "postgres",
    "psycopg2": "postgres",
    "pg8000": "postgres",
    "pymysql": "mysql",
    "mysql": "mysql",
    "MySQLdb": "mysql",
    "mariadb": "mysql",
    "oracledb": "oracle",
    "cx_Oracle": "oracle",
    "snowflake": "snowflake",
    "trino": "trino",
    "databricks": "databricks",
    "mssql_python": "sqlserver",
    "pymssql": "sqlserver",
    "pyodbc": "sqlserver",
    "pytds": "sqlserver",
}  # fmt: skip  a DB-API driver's module -> its dialect


def source_from(client: Any, dialect: str = "", name: str = "") -> Source:
    """A connection's own client (what its code made) as the adapter's source: a DuckDB connection; a file
    connection's path (a file or folder of CSV, Parquet, JSON); a client that reads a table with OData
    (Dataverse: rows, described, catalog) or by its own rows (the lakes, SharePoint), as its `sab_source`
    says (SAB_SOURCES), else as its methods show; a DB-API connection in its dialect (`dialect`, else its
    `dbms`, else its driver's)."""
    if isinstance(client, DuckDB | Sql | OData | Rows | Remote | Files | Excel):
        return client
    if isinstance(client, bytes | bytearray | memoryview):  # a workbook's bytes (an upload, a document)
        return Excel(client, name)
    if isinstance(client, str) or hasattr(client, "__fspath__"):  # a file connection: the file it reaches
        if str(client).lower().endswith((*WORKBOOKS, ".xls")):
            return Excel(str(client), name)
        return Files(str(client), name)
    if isinstance(client, duckdb.DuckDBPyConnection):
        return DuckDB.over(client, name or "DuckDB")
    said = said_source(client)  # what the client says it is, first (its methods: an older one's)
    if said == "odata":
        return OData(client, name or "Dataverse")
    if said:
        return Rows(client, name)
    if callable(getattr(client, "rows", None)) and callable(getattr(client, "catalog", None)):
        if callable(getattr(client, "described", None)):
            return OData(client, name or "Dataverse")
        return Rows(client, name)
    if callable(getattr(client, "cursor", None)):
        found = dialect or str(getattr(client, "dbms", "") or "")
        if not found:
            module = type(getattr(client, "raw", client)).__module__.split(".")[0]
            found = _DRIVERS.get(module, "")
        if found in DIALECTS:
            return Sql(client, found, name)
        raise AdapterError(
            f"{name or 'The connection'}'s SQL dialect is not known: "
            "name it (source_from(client, dialect=...))."
        )
    raise AdapterError(
        f"The adapter cannot tell what {name or type(client).__name__} is: it has no cursor, rows or catalog."
    )


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


def _json_value(value: Any) -> Any:
    """A value as JSON carries it (sab_api's rules): dates and times as ISO text, decimals as numbers, an id
    as text, bytes as hex; lists and records as they nest."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bytes | bytearray):
        return value.hex()
    if isinstance(value, Mapping):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(v) for v in value]
    if type(value).__name__ == "Decimal":
        return float(value)
    return str(value)


def to_json(data: pa.Table | pa.RecordBatchReader) -> Iterator[bytes]:
    """Arrow as a JSON array of records, a batch at a time (an endpoint's answer): the text comes as the
    batches are read, never the whole answer held as Python objects at once."""
    reader = data if isinstance(data, pa.RecordBatchReader) else data.to_reader()
    yield b"["
    first = True
    for batch in reader:
        for row in batch.to_pylist():
            yield (b"" if first else b",") + json.dumps(_json_value(row)).encode()
            first = False
    yield b"]"


def to_ipc(data: pa.Table | pa.RecordBatchReader) -> bytes:
    """Arrow as an Arrow IPC stream (an endpoint's answer to a widget that asks for Arrow)."""
    reader = data if isinstance(data, pa.RecordBatchReader) else data.to_reader()
    sink = pa.BufferOutputStream()
    with ipc.new_stream(sink, reader.schema) as stream:
        for batch in reader:
            stream.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


def is_arrow(value: Any) -> bool:
    return isinstance(value, pa.Table | pa.RecordBatchReader)


def arrow_of(rows: Any) -> pa.Table:
    """Rows as an Arrow table: Arrow (a table or a reader), a DataFrame (pandas, polars), a DuckDB relation,
    or a list of dicts (records: each key a column, the first record's order)."""
    if isinstance(rows, pa.RecordBatchReader):
        return rows.read_all()
    if isinstance(rows, pa.Table):
        return rows
    if isinstance(rows, list) and all(isinstance(r, Mapping) for r in rows):
        return pa.Table.from_pylist([dict(r) for r in rows])
    made = getattr(rows, "to_arrow_table", None) or getattr(rows, "to_arrow", None)  # DuckDB, polars
    if callable(made):
        found = made()
        return found.read_all() if isinstance(found, pa.RecordBatchReader) else found
    if type(rows).__module__.split(".")[0] == "pandas":
        return pa.Table.from_pandas(rows, preserve_index=False)
    raise AdapterError(
        "The rows are a DataFrame, an Arrow table, a list of dicts or an open table's name, "
        f"not {type(rows).__name__}."
    )


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
    "DIALECTS",
    "SAB_SOURCES",
    "AdapterError",
    "Column",
    "Connection",
    "Counts",
    "Dialect",
    "DuckDB",
    "Files",
    "Filter",
    "Folded",
    "OData",
    "Plan",
    "Remote",
    "Rows",
    "Source",
    "Sql",
    "Table",
    "TableSource",
    "Tables",
    "Total",
    "catalog_rows",
    "cursor_batches",
    "define",
    "dialect_sql",
    "from_json",
    "is_arrow",
    "make_table",
    "plan_from",
    "plan_sql",
    "planned",
    "present",
    "query",
    "read",
    "refresh",
    "said_source",
    "source_from",
    "table",
    "tables",
    "to_ipc",
    "to_json",
    "use",
    "write",
]
