"""The SQL Write starters' helper: the database a connection is, and what its SQL needs (docs/ideas.md,
"Writing data"). The statements themselves are written out in each starter's cell.

    w = SqlWrite("Warehouse", "sales.orders", "upsert", orders, dry_run=dry_run, engine="postgres")
    w.check_columns()                       # every column of the rows is one of the table's
    w.check_keys(["order_id"], unique=True)
    upsert = f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()}) ON CONFLICT ..."
    w.would(upsert, updated=w.found(["order_id"]))      # the dry run's plan (then it closes)
    if not dry_run:
        with w.transaction():               # one transaction: a failure rolls back, naming its batch
            w.each_batch(upsert)
        w.done(...)

It knows each database by its driver: PostgreSQL (psycopg), SQLite (sqlite3: the connection opens
read-only, so the same file is opened again to write), MySQL and MariaDB (pymysql, mariadb), SQL Server
and Azure SQL (pyodbc, told apart from any other ODBC source by the driver's own answer), Oracle
(oracledb) and Trino (trino: no transactions on most connectors, so each statement stands by itself).
For each: how it quotes a name (a plain one written the way it reads one unquoted, so Region finds a
column made as region), its parameter marks, how it takes a value, the types a new table gets from the
rows' DuckDB types, and what its refusals usually mean.

Standard library only; the driver is the connection's own (sab.connection signs in its own way).
"""

from __future__ import annotations

import datetime as _dt
import decimal
import re
import sqlite3
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.client.writes import Failed, Rows, Write, WriteError, each_batch, live, words

COUNT_UP_TO: int = 200_000  # a dry run counts the rows the keys find up to this many keys
_PLAIN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DECIMAL = re.compile(r"DECIMAL\((\d+),\s*(\d+)\)")
_ROOM = (50, 100, 255, 500, 1000, 2000, 4000)


def _room(width: int) -> int | None:
    """A text column's width with room to grow (None: longer than a bounded type holds)."""
    return next((r for r in _ROOM if width <= r // 2 or (r == _ROOM[-1] and width <= r)), None)


@dataclass(frozen=True)
class Engine:
    """One database's SQL, as the starters need it."""

    key: str
    title: str
    quote: str  # the opening and closing quote: '""', "[]", "``"
    fold: Callable[[str], str] | None  # how it reads a plain name unquoted (None: as written)
    types: dict[str, str]  # a DuckDB type -> this database's
    decimal: str  # DECIMAL(p, s) -> "numeric({0},{1})"
    text: Callable[[int | None], str]  # a text column of this width (None: unbounded)
    other: str  # a list, a record, anything else
    transactional: bool = True
    hints: tuple[tuple[str, str], ...] = ()
    value: Callable[[Any], Any] | None = None
    drivers: tuple[str, ...] = field(default=())


def _sqlite_value(value: Any) -> Any:
    """A value as SQLite keeps it: a decimal as a number, a date or time as ISO text."""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, _dt.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, _dt.date | _dt.time):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        return value.total_seconds()
    return value


def _oracle_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, _dt.time):
        return value.isoformat()
    return value


def _mysql_value(value: Any) -> Any:
    if isinstance(value, _dt.datetime) and value.tzinfo is not None:  # MySQL keeps no time zone
        return value.astimezone(_dt.UTC).replace(tzinfo=None)
    return value


_COMMON = {
    "BOOLEAN": "boolean",
    "TINYINT": "smallint",
    "SMALLINT": "smallint",
    "INTEGER": "integer",
    "BIGINT": "bigint",
    "UTINYINT": "smallint",
    "USMALLINT": "integer",
    "UINTEGER": "bigint",
    "FLOAT": "real",
    "DOUBLE": "double precision",
    "DATE": "date",
    "TIME": "time",
    "TIMESTAMP": "timestamp",
}

ENGINES: dict[str, Engine] = {
    "postgres": Engine(
        "postgres",
        "PostgreSQL",
        '""',
        str.lower,
        _COMMON
        | {
            "HUGEINT": "numeric(38,0)",
            "UBIGINT": "numeric(20,0)",
            "TIMESTAMP WITH TIME ZONE": "timestamptz",
            "BLOB": "bytea",
            "UUID": "uuid",
            "INTERVAL": "interval",
            "JSON": "jsonb",
        },
        "numeric({0},{1})",
        lambda width: "text",
        "text",
        hints=(
            (
                "no unique or exclusion constraint",
                "ON CONFLICT needs a primary key or a unique index on exactly the key columns.",
            ),
            (
                "violates foreign key",
                "Another table's rows point at these: write those first, or delete them.",
            ),
            (
                "permission denied",
                "This sign-in may not write this table: its owner grants INSERT, UPDATE...",
            ),
        ),
        drivers=("psycopg",),
    ),
    "sqlite": Engine(
        "sqlite",
        "SQLite",
        '""',
        None,
        {"BOOLEAN": "INTEGER", "DOUBLE": "REAL", "FLOAT": "REAL", "BLOB": "BLOB"}
        | {t: "INTEGER" for t in ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "UTINYINT", "USMALLINT")}
        | {"UINTEGER": "INTEGER", "HUGEINT": "NUMERIC", "UBIGINT": "NUMERIC"},
        "NUMERIC",
        lambda width: "TEXT",
        "TEXT",
        hints=(
            (
                "ON CONFLICT clause does not match",
                "ON CONFLICT needs a PRIMARY KEY or UNIQUE index on the keys.",
            ),
            ("database is locked", "Another program is writing this file: close it there and run again."),
            ("readonly database", "The file is read-only for this sign-in (its folder's permissions)."),
        ),
        value=_sqlite_value,
        drivers=("sqlite3",),
    ),
    "mysql": Engine(
        "mysql",
        "MySQL / MariaDB",
        "``",
        None,
        {
            "BOOLEAN": "boolean",
            "TINYINT": "tinyint",
            "SMALLINT": "smallint",
            "INTEGER": "int",
            "BIGINT": "bigint",
            "UTINYINT": "tinyint unsigned",
            "USMALLINT": "smallint unsigned",
            "UINTEGER": "int unsigned",
            "UBIGINT": "bigint unsigned",
            "HUGEINT": "decimal(38,0)",
            "FLOAT": "float",
            "DOUBLE": "double",
            "DATE": "date",
            "TIME": "time(6)",
            "TIMESTAMP": "datetime(6)",
            "TIMESTAMP WITH TIME ZONE": "datetime(6)",
            "BLOB": "longblob",
            "UUID": "char(36)",
            "JSON": "json",
        },
        "decimal({0},{1})",
        lambda width: f"varchar({width})" if width and width <= 1000 else "longtext",
        "longtext",
        hints=(
            ("Duplicate entry", "A key is in the table already: the upsert starter updates it instead."),
            ("command denied", "This sign-in may not write this table: an admin grants INSERT, UPDATE..."),
        ),
        value=_mysql_value,
        drivers=("pymysql", "mariadb", "MySQLdb", "mysql"),
    ),
    "sqlserver": Engine(
        "sqlserver",
        "SQL Server",
        "[]",
        None,
        {
            "BOOLEAN": "bit",
            "TINYINT": "smallint",
            "SMALLINT": "smallint",
            "INTEGER": "int",
            "BIGINT": "bigint",
            "UTINYINT": "tinyint",
            "USMALLINT": "int",
            "UINTEGER": "bigint",
            "UBIGINT": "decimal(20,0)",
            "HUGEINT": "decimal(38,0)",
            "FLOAT": "real",
            "DOUBLE": "float",
            "DATE": "date",
            "TIME": "time",
            "TIMESTAMP": "datetime2",
            "TIMESTAMP WITH TIME ZONE": "datetimeoffset",
            "BLOB": "varbinary(max)",
            "UUID": "uniqueidentifier",
        },
        "decimal({0},{1})",
        lambda width: f"nvarchar({width})" if width else "nvarchar(max)",
        "nvarchar(max)",
        hints=(
            ("Cannot truncate table", "Another table's foreign key points at it: use DELETE FROM instead."),
            (
                "PRIMARY KEY constraint",
                "A key is in the table already: the upsert starter updates it instead.",
            ),
            (
                "permission was denied",
                "This sign-in may not write this table: an admin grants INSERT, UPDATE...",
            ),
        ),
        drivers=("pyodbc",),
    ),
    "oracle": Engine(
        "oracle",
        "Oracle",
        '""',
        str.upper,
        {
            "BOOLEAN": "NUMBER(1)",
            "TINYINT": "NUMBER(3)",
            "SMALLINT": "NUMBER(5)",
            "INTEGER": "NUMBER(10)",
            "BIGINT": "NUMBER(19)",
            "UTINYINT": "NUMBER(3)",
            "USMALLINT": "NUMBER(5)",
            "UINTEGER": "NUMBER(10)",
            "UBIGINT": "NUMBER(20)",
            "HUGEINT": "NUMBER(38)",
            "FLOAT": "BINARY_FLOAT",
            "DOUBLE": "BINARY_DOUBLE",
            "DATE": "DATE",
            "TIME": "VARCHAR2(16)",
            "TIMESTAMP": "TIMESTAMP",
            "TIMESTAMP WITH TIME ZONE": "TIMESTAMP WITH TIME ZONE",
            "BLOB": "BLOB",
            "UUID": "VARCHAR2(36)",
            "INTERVAL": "INTERVAL DAY TO SECOND",
        },
        "NUMBER({0},{1})",
        lambda width: f"VARCHAR2({width} CHAR)" if width else "CLOB",
        "CLOB",
        hints=(
            (
                "ORA-00942",
                "There is no such table, or this sign-in may not see it (its owner grants SELECT).",
            ),
            ("ORA-00001", "A key is in the table already: the upsert starter updates it instead."),
            ("ORA-01031", "This sign-in may not write this table: its owner grants INSERT, UPDATE..."),
        ),
        value=_oracle_value,
        drivers=("oracledb", "cx_Oracle"),
    ),
    "trino": Engine(
        "trino",
        "Trino",
        '""',
        str.lower,
        {
            "BOOLEAN": "boolean",
            "TINYINT": "tinyint",
            "SMALLINT": "smallint",
            "INTEGER": "integer",
            "BIGINT": "bigint",
            "UTINYINT": "smallint",
            "USMALLINT": "integer",
            "UINTEGER": "bigint",
            "UBIGINT": "decimal(20,0)",
            "HUGEINT": "decimal(38,0)",
            "FLOAT": "real",
            "DOUBLE": "double",
            "DATE": "date",
            "TIME": "time(6)",
            "TIMESTAMP": "timestamp(6)",
            "TIMESTAMP WITH TIME ZONE": "timestamp(6) with time zone",
            "BLOB": "varbinary",
            "UUID": "uuid",
        },
        "decimal({0},{1})",
        lambda width: "varchar",
        "varchar",
        transactional=False,
        hints=(
            (
                "does not support MERGE",
                "This catalog's connector has no MERGE: Iceberg, Delta Lake, Hive (transactional tables) and "
                "some JDBC connectors do. The append and replace starters work on the others.",
            ),
            (
                "does not support",
                "This catalog's connector cannot do that: Trino's connectors differ in what they write "
                "(the connector's own page in Trino's documentation lists it).",
            ),
            ("Access Denied", "This sign-in may not write there: Trino's access control refused it."),
        ),
        drivers=("trino",),
    ),
    "odbc": Engine(
        "odbc",
        "ODBC",
        '""',
        None,
        _COMMON | {"HUGEINT": "decimal(38,0)", "UBIGINT": "decimal(20,0)", "BLOB": "varbinary(8000)"},
        "decimal({0},{1})",
        lambda width: f"varchar({width})" if width else "varchar(8000)",
        "varchar(8000)",
        drivers=("pyodbc",),
    ),
}


def detect(conn: Any) -> Engine:
    """The database a connection is, by its driver (pyodbc: by the source's own answer)."""
    top = type(conn).__module__.split(".")[0]
    if top == "pyodbc":
        try:
            pyodbc = sys.modules["pyodbc"]
            name = str(conn.getinfo(pyodbc.SQL_DBMS_NAME))
        except Exception:  # an ODBC driver that does not say
            name = ""
        return ENGINES["sqlserver" if "SQL Server" in name else "odbc"]
    for engine in ENGINES.values():
        if top in engine.drivers:
            return engine
    raise WriteError(
        f"A {type(conn).__name__} connection ({top}) is not one the SQL Write starters know: PostgreSQL, "
        "SQL Server, MySQL, MariaDB, SQLite, Oracle, Trino or an ODBC source."
    )


def _writable(conn: Any) -> Any:
    """A SQLite connection that may write: the SQLite connection opens its file read-only (so a wrong
    path fails instead of making an empty database), so the same file is opened again. Writes are in
    one transaction each: autocommit off by hand (BEGIN, then COMMIT or ROLLBACK)."""
    if not isinstance(conn, sqlite3.Connection):
        return conn
    found = conn.execute("PRAGMA database_list").fetchall()
    path = next((str(r[2]) for r in found if r[1] == "main"), "")
    if not path:  # a database in memory: written as it is
        conn.isolation_level = None
        return conn
    conn.close()
    again = sqlite3.connect(path)
    again.isolation_level = None
    return again


class SqlWrite(Write):
    """A write to a database table: the connection (signed in its own way), the target's name quoted
    for its SQL, the rows' columns and parameter marks, the counts, the batches and the transaction."""

    def __init__(
        self,
        connection: Any,
        target: str,
        what: str,
        rows: Any = None,
        dry_run: bool = True,
        batch_size: int = 1000,
        engine: str | Sequence[str] | None = None,
    ) -> None:
        name, conn = live(connection)
        super().__init__(name, target, what, rows, dry_run)
        self.engine = detect(conn)
        wanted = [engine] if isinstance(engine, str) else list(engine or [])
        if wanted and self.engine.key not in wanted:
            titles = " or ".join(ENGINES[k].title for k in wanted)
            raise WriteError(
                f"{name} is a {self.engine.title} connection: this starter writes to {titles}. "
                f"The {self.engine.title} Write starters write to it."
            )
        self.conn = _writable(conn)
        self.cursor = self.conn.cursor()
        self.batch_size = max(1, int(batch_size))
        self.table = self.qualified(target)
        self._paramstyle = getattr(
            sys.modules.get(type(self.conn).__module__.split(".")[0]), "paramstyle", "qmark"
        )
        self._undo: list[str] = []
        self.fact("Database", self.engine.title + ("" if self.engine.transactional else " (no transactions)"))

    # ===== names and marks =====

    def name(self, name: str) -> str:
        """A name as this database's SQL writes it, quoted: a plain one first written the way it reads
        one unquoted (Region is region in PostgreSQL and Trino, REGION in Oracle)."""
        if self.engine.fold and _PLAIN.fullmatch(name):
            name = self.engine.fold(name)
        opening, closing = self.engine.quote[0], self.engine.quote[-1]
        return opening + name.replace(closing, closing * 2) + closing

    def names(self, names: Sequence[str]) -> str:
        return ", ".join(self.name(n) for n in names)

    def qualified(self, text: str) -> str:
        """A table's name, each part quoted: schema.table (or table, or catalog.schema.table)."""
        quotes = self.engine.quote + '"'
        parts = [p.strip().strip(quotes) for p in str(text).split(".")]
        if not all(parts):
            raise WriteError(f"target is a table's name (schema.table), not {text!r}.")
        return ".".join(self.name(p) for p in parts)

    @property
    def columns(self) -> str:
        """The rows' columns, quoted, in order."""
        return self.names(self.need_rows().names)

    def mark(self, at: int = 0) -> str:
        """The parameter mark for the value at `at` (0 first): ?, %s or :1."""
        if self._paramstyle in ("format", "pyformat"):
            return "%s"
        if self._paramstyle in ("numeric", "named"):
            return f":{at + 1}"
        return "?"

    def marks(self, count: int | None = None, start: int = 0) -> str:
        """`count` marks (the rows' columns' number, by default): ?, ?, ?"""
        total = len(self.need_rows().names) if count is None else count
        return ", ".join(self.mark(start + i) for i in range(total))

    def column_types(self) -> str:
        """The rows' columns as a new table's: each name and this database's type, one per line."""
        rows = self.need_rows()
        widths = rows.widths()
        lines = []
        for column, duck in rows.columns:
            found = _DECIMAL.fullmatch(duck)
            if found:
                kind = self.engine.decimal.format(found[1], found[2])
            elif duck == "VARCHAR":
                kind = self.engine.text(_room(max(1, widths.get(column, 1))))
            else:
                kind = self.engine.types.get(duck, self.engine.other)
            lines.append(f"    {self.name(column)} {kind}")
        return ",\n".join(lines)

    # ===== reading the target =====

    def execute(self, sql: str, values: Sequence[Any] | None = None) -> None:
        """One statement."""
        if values:
            self.cursor.execute(sql, list(values))
        else:
            self.cursor.execute(sql)
        if self.engine.key == "trino":  # Trino runs a statement as its answer is read
            self.cursor.fetchall()

    def query(self, sql: str, values: Sequence[Any] | None = None) -> list[Any]:
        if values:
            self.cursor.execute(sql, list(values))
        else:
            self.cursor.execute(sql)
        return list(self.cursor.fetchall())

    def target_columns(self) -> list[str]:
        """The target table's columns; a plain WriteError when it is not there or cannot be read."""
        try:
            self.query(f"SELECT * FROM {self.table} WHERE 1 = 0")
        except Exception as error:
            raise WriteError(
                f"{self.target} cannot be read on {self.connection}: {self._said(error)}"
            ) from None
        return [str(d[0]) for d in self.cursor.description or []]

    def exists(self) -> bool:
        try:
            self.query(f"SELECT * FROM {self.table} WHERE 1 = 0")
        except Exception:
            self._rollback()  # a failed statement ends the transaction in some databases
            return False
        return True

    def check_new(self) -> None:
        """The target is not there yet (create)."""
        if self.exists():
            raise WriteError(
                f"{self.target} is already on {self.connection}: the append, replace or upsert starters "
                "write into it."
            )

    def check_columns(self, names: Sequence[str] | None = None) -> None:
        """Every column of the rows (or `names`) is one of the table's (any case)."""
        columns = self.target_columns()
        have = {c.casefold() for c in columns}
        missing = [n for n in (names or self.need_rows().names) if n.casefold() not in have]
        if missing:
            raise WriteError(
                f"{self.target} has no column {', '.join(missing)}: rename or drop it in the rows first "
                f"({self.target} has {', '.join(columns)})."
            )

    def check_keys(self, keys: Sequence[str], unique: bool) -> list[str]:
        found = self.need_rows().check_keys(keys, unique)
        self.fact("Keys", ", ".join(found))
        return found

    def count(self) -> int:
        """The rows in the target table now."""
        return int(self.query(f"SELECT COUNT(*) FROM {self.table}")[0][0])

    def found(self, keys: Sequence[str], size: int = 100) -> int | None:
        """How many of the table's rows the rows' keys find (None: more keys than a dry run counts)."""
        rows = self.need_rows()
        if rows.distinct(keys) > COUNT_UP_TO:
            return None
        found = 0
        for batch in rows.batches(keys, size, self._value, distinct=True):
            where, values = self.where_keys(batch, keys)
            found += int(self.query(f"SELECT COUNT(*) FROM {self.table} WHERE {where}", values)[0][0])
        return found

    def where_keys(self, batch: Sequence[Sequence[Any]], keys: Sequence[str]) -> tuple[str, list[Any]]:
        """A batch of keys as one condition, (k1 = ? AND k2 = ?) OR (...), and its values in order."""
        clauses, at = [], 0
        for _ in batch:
            clauses.append(
                "(" + " AND ".join(f"{self.name(k)} = {self.mark(at + i)}" for i, k in enumerate(keys)) + ")"
            )
            at += len(keys)
        return " OR ".join(clauses), [v for row in batch for v in row]

    # ===== the plan, then the write =====

    def would(self, *statements: str, **counts: int | None) -> None:
        """The plan; in a dry run the end of it: rolled back (it only read) and closed."""
        super().would(*statements, **counts)
        if self.dry_run:
            self._rollback()
            self.conn.close()

    def each_batch(self, sql: str, columns: Sequence[str] | None = None, distinct: bool = False) -> int:
        """`sql` run for every row (or distinct row of `columns`), a batch of rows at a time."""
        rows = self.need_rows()
        names = list(columns or rows.names)
        batches = rows.batches(names, self.batch_size, self._value, distinct)
        return each_batch(batches, lambda batch: self.cursor.executemany(sql, batch))

    def each_values(self, head: str, tail: str = "", columns: Sequence[str] | None = None) -> int:
        """`head` + VALUES (...), (...) + `tail`: a batch of rows in one statement (Trino's way)."""
        rows = self.need_rows()
        names = list(columns or rows.names)

        def run(batch: list[Any]) -> None:
            groups = [f"({self.marks(len(names), i * len(names))})" for i in range(len(batch))]
            self.execute(head + ", ".join(groups) + tail, [v for row in batch for v in row])

        return each_batch(rows.batches(names, self.batch_size, self._value), run)

    def each_where(self, head: str, keys: Sequence[str], size: int = 100) -> int:
        """`head` + (k1 = ? AND ...) OR (...): the distinct keys, a batch at a time (a delete)."""
        batches = self.need_rows().batches(keys, size, self._value, distinct=True)

        def run(batch: list[Any]) -> None:
            where, values = self.where_keys(batch, keys)
            self.execute(head + where, values)

        return each_batch(batches, run)

    def copy(self, sql: str) -> int:
        """PostgreSQL's COPY ... FROM STDIN: each batch of rows streamed in (psycopg)."""
        rows = self.need_rows()

        def run(batch: list[Any]) -> None:
            with self.cursor.copy(sql) as copy:
                for row in batch:
                    copy.write_row(row)

        return each_batch(rows.batches(rows.names, self.batch_size, self._value), run)

    def on_failure(self, sql: str) -> None:
        """A statement that undoes what a database commits by itself (MySQL's and Oracle's CREATE TABLE),
        run when the write fails."""
        self._undo.append(sql)

    @contextmanager
    def transaction(self) -> Iterator[SqlWrite]:
        """The write in one transaction: committed when all of it went in; on a failure rolled back,
        and a WriteError says which batch (Trino: which batches were written before it)."""
        if isinstance(self.conn, sqlite3.Connection):
            self.conn.execute("BEGIN")
        try:
            yield self
        except Failed as failed:
            self._failed(f"{failed.where()} failed: {self._said(failed.error)}", failed.before)
        except WriteError:
            self._failed("", 0)
            raise
        except Exception as error:
            self._failed(self._said(error), 0)
        else:
            if self.engine.transactional:
                self.conn.commit()
        finally:
            try:
                self.conn.close()
            except Exception:  # noqa: S110 (closing after a failure: the failure is what is said)
                pass

    def _failed(self, why: str, before: int) -> None:
        self._rollback()
        for sql in self._undo:
            try:
                self.execute(sql)
                if self.engine.transactional:
                    self.conn.commit()
            except Exception:  # noqa: S110 (the write's own failure is the one to say)
                pass
        if not why:
            return
        if self.engine.transactional:
            raise WriteError(f"Nothing was written: {why}") from None
        written = f"the {before:,} rows before it were written" if before else "nothing was written"
        raise WriteError(
            f"{why[:1].upper()}{why[1:]}. {self.engine.title} writes each statement by itself: {written}."
        ) from None

    def _rollback(self) -> None:
        if self.engine.transactional:
            try:
                self.conn.rollback()
            except Exception:  # noqa: S110 (nothing to roll back)
                pass

    def _value(self, value: Any) -> Any:
        """A value as the driver takes it: an id as text, a list or a record as JSON."""
        import json
        import uuid

        if isinstance(value, uuid.UUID) and self.engine.key not in ("postgres", "trino"):
            value = str(value)
        elif isinstance(value, list | dict):
            value = json.dumps(value, default=str)
        return self.engine.value(value) if self.engine.value else value

    def _said(self, error: BaseException) -> str:
        """The database's own words, and what they usually mean."""
        said = words(error)
        hint = next((h for found, h in self.engine.hints if found.lower() in str(error).lower()), "")
        return f"{said} {hint}".strip()


# ===== SQL Server and Azure SQL: staged, typed from the target, merged, retried =====

# Azure SQL's and SQL Server's errors that pass: a database moving or busy, a throttle, a deadlock, a
# dropped connection. The whole transaction is run again (never half of one), after a wait that grows.
TRANSIENT_ERRORS: frozenset[str] = frozenset(
    {"40613", "40197", "40501", "49918", "49919", "49920", "10928", "10929", "4221", "1205"}
)
TRANSIENT_STATES: frozenset[str] = frozenset({"08S01", "08001", "40001", "HYT00", "HYT01"})
TRANSIENT_SOCKETS: frozenset[str] = frozenset({"10053", "10054", "10060"})
TRIES: int = 4
SQLSERVER_PARAMETERS: int = 2100  # the most parameters one statement takes
SQLSERVER_VALUES_ROWS: int = 1000  # the most rows one VALUES list takes
BATCH_BYTES: int = 16_000_000  # about this much of values in one fast_executemany batch
STAGE: str = "#sab_stage"
STAGED_KEYS: str = "#sab_keys"


def transient(error: BaseException) -> bool:
    """Whether a SQL Server error passes by itself, so the transaction is run again: Azure's
    reconfiguration, busy and throttling errors, a deadlock, a dropped connection."""
    args = [str(a) for a in getattr(error, "args", ())]
    if args and args[0] in TRANSIENT_STATES:
        return True
    numbers = set(re.findall(r"(?<!\d)(\d{4,5})(?!\d)", " ".join(args) or str(error)))
    return bool(numbers & (TRANSIENT_ERRORS | TRANSIENT_SOCKETS))


@dataclass(frozen=True)
class Column:
    """One of the target table's columns, as sys.columns says it."""

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


class SqlServerWrite(SqlWrite):
    """A write to SQL Server or Azure SQL (pyodbc), made robust (the owner, 2026-11-17: "SQL server and
    azure SQL are two things I use alot so make them robust"):

      types      read from the target (sys.columns): the rows are staged in a #temp table of exactly
                 those types, and pyodbc is told each text column's and decimal's size (setinputsizes),
                 so varchar stays varchar, nvarchar Unicode, a decimal its precision and scale; NaN and
                 NaT are NULL; an id is a uniqueidentifier's text; a zoned time a datetimeoffset's
      inserts    fast_executemany (one round trip a batch), batches sized by the rows' width; without
                 it (fast = False), multi-row VALUES under 2,100 parameters and 1,000 rows a statement
      upserts    staged, then one MERGE ... WITH (HOLDLOCK); where MERGE is refused, UPDATE then
                 INSERT; all in one transaction. No keys given: the target's primary key (none: refused)
      identity   SET IDENTITY_INSERT only when the rows carry the identity column and identity_insert
                 is chosen; otherwise that column is refused, by name
      triggers   the target's enabled triggers are said in the dry run (they fire on the write)
      retries    Azure's passing errors (40613, 40197, 40501, 49918, 10928, 10929, 4221), a deadlock
                 (1205), a dropped connection (08S01, 10053, 10054): the whole transaction again on a
                 fresh connection, after 1, 2, 4 seconds; never half of one
      dry run    the keys staged in a #temp table, then one COUNT join says how many rows will update
                 and how many insert (no row fetched)
    """

    def __init__(
        self,
        connection: Any,
        target: str,
        what: str,
        rows: Any = None,
        dry_run: bool = True,
        batch_size: int = 1000,
        identity_insert: bool = False,
        engine: str | Sequence[str] | None = "sqlserver",
    ) -> None:
        self._given = connection
        self._target: list[Column] | None = None
        super().__init__(connection, target, what, rows, dry_run, batch_size, engine)
        self.identity_insert = bool(identity_insert)
        self.fast = True  # fast_executemany; False: rows in multi-row VALUES statements

    # ===== the target, as sys.columns says it =====

    def target_table(self) -> list[Column]:
        """The target's columns (name, type, size, identity, computed), read once."""
        if self._target is None:
            found = self.query(
                "SELECT c.name, t.name, c.max_length, c.precision, c.scale, c.is_identity, c.is_computed "
                "FROM sys.columns AS c JOIN sys.types AS t ON t.user_type_id = c.user_type_id "
                "WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id",
                [self.table],
            )
            if not found:
                raise WriteError(f"{self.target} is not a table on {self.connection} this sign-in may see.")
            self._target = [
                Column(str(r[0]), str(r[1]), int(r[2]), int(r[3]), int(r[4]), bool(r[5]), bool(r[6]))
                for r in found
            ]
        return self._target

    def target_columns(self) -> list[str]:
        return [c.name for c in self.target_table()]

    def column(self, name: str) -> Column:
        return next(c for c in self.target_table() if c.name.casefold() == name.casefold())

    def check_columns(self, names: Sequence[str] | None = None) -> None:
        """Every column of the rows (or `names`) is the table's; none computed; the identity column
        only with identity_insert chosen. The target's enabled triggers are said."""
        super().check_columns(names)
        given = list(names or self.need_rows().names)
        computed = [n for n in given if self.column(n).computed]
        if computed:
            raise WriteError(f"{', '.join(computed)} is computed by {self.target}: drop it from the rows.")
        identity = [n for n in given if self.column(n).identity]
        if identity and names is None:
            if not self.identity_insert:
                raise WriteError(
                    f"{identity[0]} is {self.target}'s identity column: SQL Server numbers it. Drop it from "
                    "the rows, or set identity_insert = True to write the rows' own values."
                )
            self.fact("Identity", f"{identity[0]}: the rows' own values (SET IDENTITY_INSERT ON)")
        listed = self.query(
            "SELECT name FROM sys.triggers WHERE parent_id = OBJECT_ID(?) AND is_disabled = 0", [self.table]
        )
        if listed:
            self.fact("Triggers", f"{', '.join(str(r[0]) for r in listed)} fire on this write")

    def primary_key(self) -> list[str]:
        found = self.query(
            "SELECT c.name FROM sys.indexes AS i JOIN sys.index_columns AS ic ON ic.object_id = i.object_id "
            "AND ic.index_id = i.index_id JOIN sys.columns AS c ON c.object_id = ic.object_id "
            "AND c.column_id = ic.column_id WHERE i.object_id = OBJECT_ID(?) AND i.is_primary_key = 1 "
            "ORDER BY ic.key_ordinal",
            [self.table],
        )
        return [str(r[0]) for r in found]

    def check_keys(self, keys: Sequence[str], unique: bool) -> list[str]:
        """The keys given, else the target's primary key (none: refused)."""
        if not [k for k in keys if k]:
            primary = self.primary_key()
            if not primary:
                raise WriteError(f"{self.target} has no primary key: name the key columns in keys.")
            names = {n.casefold(): n for n in self.need_rows().names}
            keys = [names.get(k.casefold(), k) for k in primary]
        return super().check_keys(list(keys), unique)

    # ===== values, sizes, batches =====

    def _value(self, value: Any) -> Any:
        import math
        import uuid

        if isinstance(value, float) and math.isnan(value):
            return None  # NaN is NULL (pandas' NaT already is: DuckDB reads it as no value)
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, _dt.datetime) and value.tzinfo is not None:
            return value.isoformat(sep=" ")  # a datetimeoffset takes it as text, its zone kept
        return super()._value(value)

    def input_sizes(self, names: Sequence[str]) -> list[Any]:
        """pyodbc's size for each column (setinputsizes): text by the target's own type and length, a
        decimal by its precision and scale; None: pyodbc's own choice."""
        pyodbc = sys.modules.get("pyodbc")
        sizes: list[Any] = []
        for name in names:
            column = self.column(name)
            kind = column.type.lower()
            if column.text and pyodbc is not None:
                wide = kind in ("nvarchar", "nchar")
                size = 0 if column.max_length < 0 else column.max_length // (2 if wide else 1)
                sizes.append((pyodbc.SQL_WVARCHAR if wide else pyodbc.SQL_VARCHAR, size, 0))
            elif kind in ("decimal", "numeric") and pyodbc is not None:
                sizes.append((pyodbc.SQL_DECIMAL, column.precision, column.scale))
            else:
                sizes.append(None)
        return sizes

    def rows_a_batch(self, names: Sequence[str]) -> int:
        """Rows in one batch: batch_size, fewer for wide rows; in multi-row VALUES, under 2,100
        parameters and 1,000 rows a statement."""
        width = sum(4000 if c.max_length < 0 else max(8, c.max_length) for c in map(self.column, names))
        size = max(1, min(self.batch_size, BATCH_BYTES // max(1, width)))
        if not self.fast:
            size = min(size, SQLSERVER_VALUES_ROWS, max(1, (SQLSERVER_PARAMETERS - 1) // max(1, len(names))))
        return size

    def insert_into(self, table: str, names: Sequence[str] | None = None, distinct: bool = False) -> int:
        """The rows' `names` columns inserted into `table` (the target, or the stage), a batch at a
        time: fast_executemany with the target's sizes, or multi-row VALUES."""
        rows = self.need_rows()
        picked = [self.column(n).name for n in (names or rows.names)]
        columns = self.names(picked)
        batches = rows.batches(list(names or rows.names), self.rows_a_batch(picked), self._value, distinct)
        if self.fast:
            self.cursor.fast_executemany = True  # one round trip a batch
            self.cursor.setinputsizes(self.input_sizes(picked))
            sql = f"INSERT INTO {table} ({columns}) VALUES ({self.marks(len(picked))})"
            return each_batch(batches, lambda batch: self.cursor.executemany(sql, batch))

        def run(batch: list[Any]) -> None:
            groups = ", ".join(f"({self.marks(len(picked), i * len(picked))})" for i in range(len(batch)))
            self.cursor.execute(
                f"INSERT INTO {table} ({columns}) VALUES {groups}", [v for r in batch for v in r]
            )

        return each_batch(batches, run)

    def insert(self) -> int:
        """The rows inserted into the target (with IDENTITY_INSERT when chosen)."""
        with self.identity():
            return self.insert_into(self.table)

    def stage(self, names: Sequence[str] | None = None, into: str = STAGE, distinct: bool = False) -> str:
        """The rows (or their `names` columns) in a #temp table of the target's own types: CREATE, then
        the batches inserted. Its CREATE, in words."""
        picked = list(names or self.need_rows().names)
        declared = []
        for name in picked:
            column = self.column(name)
            collate = (
                " COLLATE DATABASE_DEFAULT" if column.text else ""
            )  # tempdb's collation is not the target's
            declared.append(f"{self.name(column.name)} {column.declared()}{collate} NULL")
        create = f"CREATE TABLE {into} ({', '.join(declared)})"
        self.execute(f"IF OBJECT_ID('tempdb..{into}') IS NOT NULL DROP TABLE {into}")
        self.execute(create)
        self.insert_into(into, picked, distinct)
        return create

    def joined(self, keys: Sequence[str], left: str = "t", right: str = "s") -> str:
        named = [self.name(self.column(k).name) for k in keys]
        return " AND ".join(f"{left}.{n} = {right}.{n}" for n in named)

    def matching(self, keys: Sequence[str], staged: str = STAGED_KEYS) -> int:
        """The rows the staged keys find in the target: one COUNT join, no row fetched."""
        sql = f"SELECT COUNT(*) FROM {staged} AS s JOIN {self.table} AS t ON {self.joined(keys)}"
        return int(self.query(sql)[0][0])

    def _settable(self, keys: Sequence[str]) -> tuple[list[str], list[str]]:
        names = [self.column(n).name for n in self.need_rows().names]
        wanted = {k.casefold() for k in keys}
        others = [n for n in names if n.casefold() not in wanted and not self.column(n).identity]
        return names, others

    def merge_sql(self, keys: Sequence[str]) -> str:
        names, others = self._settable(keys)
        text = f"MERGE INTO {self.table} WITH (HOLDLOCK) AS t\nUSING {STAGE} AS s ON {self.joined(keys)}\n"
        if others:
            sets = ", ".join(f"t.{self.name(n)} = s.{self.name(n)}" for n in others)
            text += f"WHEN MATCHED THEN UPDATE SET {sets}\n"
        values = ", ".join(f"s.{self.name(n)}" for n in names)
        return text + f"WHEN NOT MATCHED BY TARGET THEN INSERT ({self.names(names)}) VALUES ({values});"

    def update_then_insert_sql(self, keys: Sequence[str]) -> list[str]:
        """MERGE's work in two statements, for where MERGE is refused."""
        names, others = self._settable(keys)
        statements = []
        if others:
            sets = ", ".join(f"t.{self.name(n)} = s.{self.name(n)}" for n in others)
            statements.append(
                f"UPDATE t SET {sets} FROM {self.table} AS t WITH (UPDLOCK, HOLDLOCK) "
                f"JOIN {STAGE} AS s ON {self.joined(keys)}"
            )
        picked = ", ".join(f"s.{self.name(n)}" for n in names)
        statements.append(
            f"INSERT INTO {self.table} ({self.names(names)}) SELECT {picked} FROM {STAGE} AS s "
            "WHERE NOT EXISTS "
            f"(SELECT 1 FROM {self.table} AS t WITH (UPDLOCK, HOLDLOCK) WHERE {self.joined(keys)})"
        )
        return statements

    def merge(self, keys: Sequence[str]) -> dict[str, int]:
        """The staged rows merged into the target (MERGE, else UPDATE then INSERT): its counts."""
        locked = (
            f"SELECT COUNT(*) FROM {STAGE} AS s JOIN {self.table} AS t WITH (UPDLOCK, HOLDLOCK) "
            f"ON {self.joined(keys)}"
        )
        matched = int(self.query(locked)[0][0])
        total = int(self.query(f"SELECT COUNT(*) FROM {STAGE}")[0][0])
        with self.identity():
            self.execute("SAVE TRANSACTION sab_merge")
            try:
                self.execute(self.merge_sql(keys))
            except Exception as error:
                if transient(error) or "MERGE" not in str(error).upper():
                    raise
                self.execute("ROLLBACK TRANSACTION sab_merge")  # MERGE refused: the same in two statements
                self.notes.append("MERGE was refused here: UPDATE, then INSERT, in the same transaction.")
                for statement in self.update_then_insert_sql(keys):
                    self.execute(statement)
        return {"updated": matched, "inserted": total - matched}

    def delete_staged(self, keys: Sequence[str]) -> int:
        """The target's rows the staged keys find, deleted: their count."""
        found = self.matching(keys)
        self.execute(f"DELETE t FROM {self.table} AS t JOIN {STAGED_KEYS} AS s ON {self.joined(keys)}")
        return found

    @contextmanager
    def identity(self) -> Iterator[None]:
        """SET IDENTITY_INSERT ON around a write, when the rows carry the identity column and
        identity_insert was chosen."""
        carried = [n for n in self.need_rows().names if self.column(n).identity]
        on = bool(carried) and self.identity_insert
        if on:
            self.execute(f"SET IDENTITY_INSERT {self.table} ON")
        try:
            yield
        finally:
            if on:
                self.execute(f"SET IDENTITY_INSERT {self.table} OFF")

    # ===== the transaction, run again whole when its error passes =====

    def in_transaction(self, work: Callable[[], dict[str, int]]) -> dict[str, int]:
        """`work` in one transaction, committed when all of it went in. A passing error (Azure's, a
        deadlock, a dropped connection) runs the WHOLE transaction again on a fresh connection, after 1,
        2, 4 seconds; any other failure rolls back and says which batch. Closed at the end."""
        import time

        try:
            for attempt in range(1, TRIES + 1):
                try:
                    counts = work()
                    self.conn.commit()
                    return counts
                except Exception as error:
                    cause = error.error if isinstance(error, Failed) else error
                    self._rollback()
                    if transient(cause) and attempt < TRIES:
                        self.notes.append(
                            f"Try {attempt} met a passing error ({words(cause)}): run again, whole."
                        )
                        time.sleep(2 ** (attempt - 1))
                        self._reopen()
                        continue
                    if isinstance(error, WriteError):
                        raise
                    where = f"{error.where()} failed: " if isinstance(error, Failed) else ""
                    raise WriteError(f"Nothing was written: {where}{self._said(cause)}") from None
            raise WriteError("Nothing was written.")
        finally:
            self._close()

    def _reopen(self) -> None:
        self._close()
        _, conn = live(self._given)
        self.conn = conn
        self.cursor = conn.cursor()
        self._target = None

    def _close(self) -> None:
        try:
            self.conn.close()
        except Exception:  # noqa: S110 (already closed, or the connection dropped)
            pass


__all__ = ["ENGINES", "Rows", "SqlServerWrite", "SqlWrite", "WriteError", "detect", "transient"]
