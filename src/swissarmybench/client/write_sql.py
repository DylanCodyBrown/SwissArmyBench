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
and Azure SQL (Microsoft's mssql-python; an older connection's pyodbc, told apart from any other ODBC
source by the driver's own answer), Oracle
(oracledb) and Trino (trino: no transactions on most connectors, so a write is row batches without one).
For each: how it quotes a name (a plain one written the way it reads one unquoted, so Region finds a
column made as region), its parameter marks, how it takes a value, the types a new table gets from the
rows' DuckDB types, and what its refusals usually mean.

Standard library only; the driver is the connection's own (sab.connection signs in its own way).
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import decimal
import re
import sqlite3
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Self

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
        drivers=("mssql_python", "pyodbc"),
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
                "some JDBC connectors do. Append works on the others.",
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


def writable(conn: Any) -> Any:
    """A connection as the adapter's write takes it (sab.write): SQL Server's without read-only intent, a
    SQLite file opened again to write, in transactions the adapter commits or rolls back."""
    conn = _writable(for_writes(conn))
    if isinstance(conn, sqlite3.Connection):
        conn.isolation_level = "DEFERRED"  # begun by the first statement: the adapter's one transaction
    return conn


def for_writes(conn: Any) -> Any:
    """The connection a write goes through: the SQL Server connection's without read-only intent (a read
    replica refuses writes; domain/sql_server.py), any other as it is."""
    writer = getattr(conn, "for_writes", None) if getattr(conn, "dbms", None) == "sqlserver" else None
    return writer() if callable(writer) else conn


def detect(conn: Any) -> Engine:
    """The database a connection is, by its driver (mssql-python: SQL Server; pyodbc: by the source's
    own answer)."""
    if getattr(conn, "dbms", None) == "sqlserver":  # the SQL Server connection's own (domain/sql_server.py)
        return ENGINES["sqlserver"]
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
        conn = for_writes(conn)
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
            f"{why[:1].upper()}{why[1:]}. {self.engine.title} writes row batches without a transaction: "
            f"{written}."
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

    # ===== the write, by the adapter =====

    def by_adapter(self, keys: Sequence[str] = ()) -> Self:
        """The write by the adapter's Sql (adapter.write: its own statements; one transaction where the
        database has them; Plans/adapter.plan.md), the dry run its planned(): the rows checked against the
        table first, what it would run said (the adapter's own words where it has them: SQL Server's staging
        and MERGE, Trino's batches), then, with dry_run False, written (a failure rolls every row back where
        it can and names its batch). Modes: append, create (the table made from the rows' types first),
        replace, upsert, delete."""
        from swissarmybench.adapters import (
            adapter,
        )  # imported when a write runs: this module stays stdlib

        mode = ADAPTER_MODES[self.what]
        columns, keys = self._checked([k for k in keys if k])
        data = self.need_rows().arrow()
        data = data.rename_columns([columns.get(n.casefold(), n) for n in data.column_names])
        if mode == "delete":
            data = data.select([columns.get(k.casefold(), k) for k in keys])
        names = [columns.get(k.casefold(), k) for k in keys]
        if isinstance(self.conn, sqlite3.Connection):
            self.conn.isolation_level = "DEFERRED"  # the adapter's one transaction, begun by the first write
        source = self._source(adapter)
        target = ".".join(self._bare(p) for p in self._parts())
        create = f"CREATE TABLE {self.table} (\n{self.column_types()}\n)" if self.what == "create" else ""
        statements = self._statements(create, mode, keys)
        try:
            said = [] if create else adapter.statements(source, target, data.column_names, names, mode)
            planned = self._planned(adapter, source, target, data, names, mode, bool(create))
        except adapter.AdapterError as error:
            raise WriteError(str(error)) from None
        except Exception as error:
            raise WriteError(
                f"{self.target} cannot be read on {self.connection}: {self._said(error)}"
            ) from None
        self.would(*(said or statements), **planned)
        if self.dry_run:
            return self
        done = adapter.Counts()
        try:
            if create:
                adapter.query(source, create).read_all()
                self.on_failure(f"DROP TABLE {self.table}")  # a write that fails takes its new table away
            done = adapter.write(source, target, data.to_reader(max_chunksize=self.batch_size), names, mode)
        except Exception as error:
            self._follow(source)
            batch = adapter.batch_of(error)
            said_error = f"{batch.where()} failed: {self._said(error)}" if batch else self._said(error)
            self._failed(said_error, batch.before if batch else 0)
        finally:
            self._follow(source)
            with contextlib.suppress(Exception):
                self.conn.close()
        self.notes += list(done.notes)
        self.done(**{k: int(getattr(done, k)) for k in _COUNTED[mode]})
        return self

    def _planned(
        self, adapter: Any, source: Any, target: str, data: Any, names: list[str], mode: str, create: bool
    ) -> dict[str, int | None]:
        """The dry run's counts (adapter.planned) and its notes. A new table's: its rows. SQL Server and Trino
        count in a dry run only (their starters always did): writing, only an insert's rows are said."""
        if create:
            return {"inserted": data.num_rows}
        if not self.dry_run and self.engine.key in ("sqlserver", "trino"):
            return {
                k: data.num_rows if k == "inserted" and mode == "insert" else None for k in _COUNTED[mode]
            }
        counted = adapter.planned(source, target, data, names, mode)
        self.notes += [n for n in counted.notes if n not in self.notes]
        return {k: int(getattr(counted, k)) for k in _COUNTED[mode]}

    def _source(self, adapter: Any) -> Any:
        """The connection as the adapter's Sql source, its values as this database takes them."""
        dialect = adapter.DIALECTS.get(self.engine.key) or adapter.Dialect(self.engine.key)
        return adapter.Sql(self.conn, dialect, self.connection, self._paramstyle, self._value)

    def _follow(self, source: Any) -> None:
        """The connection the adapter ended on (a fresh one after a passing error): what is closed, and where
        an undo (a new table dropped) runs."""
        if source.connection is not self.conn:
            self.conn = source.connection
            self.cursor = self.conn.cursor()

    def _checked(self, keys: list[str]) -> tuple[dict[str, str], list[str]]:
        """The checks before a write (the table there or not, its columns, the keys); the table's own name
        for each of the rows' columns by its case-folded name (Region writes region), and the keys."""
        if self.what == "create":
            self.check_new()
            return {n.casefold(): self._bare(n) for n in self.need_rows().names}, keys
        if self.what == "delete":
            self.check_columns(keys)
        else:
            self.check_columns()
        if self.what in ("upsert", "delete"):
            if self.what == "upsert" and not keys:
                raise WriteError('An upsert finds each row by its key columns: keys=["order_id"].')
            self.check_keys(keys, unique=self.what == "upsert")
        return {c.casefold(): c for c in self.target_columns()}, keys

    def _parts(self) -> list[str]:
        quotes = self.engine.quote + '"'
        return [p.strip().strip(quotes) for p in str(self.target).split(".")]

    def _bare(self, name: str) -> str:
        """A name as the database holds it: a plain one the way it reads one unquoted."""
        return self.engine.fold(name) if self.engine.fold and _PLAIN.fullmatch(name) else name

    def _statements(self, create: str, mode: str, keys: list[str]) -> list[str]:
        """What the adapter will run, in this database's SQL, for the report."""
        insert = f"INSERT INTO {self.table} ({self.columns}) VALUES ({self.marks()})"
        if mode == "delete":
            where = " AND ".join(f"{self.name(k)} = {self.mark(i)}" for i, k in enumerate(keys))
            return [f"DELETE FROM {self.table} WHERE {where}"]
        if mode == "merge":
            others = [c for c in self.need_rows().names if c not in keys]
            sets = ", ".join(f"{self.name(c)} = {self.mark(i)}" for i, c in enumerate(others))
            where = " AND ".join(f"{self.name(k)} = {self.mark(len(others) + i)}" for i, k in enumerate(keys))
            return [
                f"UPDATE {self.table} SET {sets} WHERE {where}  -- the rows whose keys are there",
                f"{insert}  -- the others",
            ]
        return [s for s in (create, f"DELETE FROM {self.table}" if mode == "truncate" else "", insert) if s]


# A starter's mode -> the adapter's (create: the table made, then an insert).
ADAPTER_MODES: dict[str, str] = {
    "append": "insert",
    "create": "insert",
    "replace": "truncate",
    "upsert": "merge",
    "delete": "delete",
}
_COUNTED: dict[str, tuple[str, ...]] = {
    "insert": ("inserted",),
    "truncate": ("deleted", "inserted"),
    "merge": ("updated", "inserted"),
    "delete": ("deleted",),
}


# ===== SQL Server and Azure SQL: the checks; the write is the adapter's =====


class SqlServerWrite(SqlWrite):
    """A write to SQL Server or Azure SQL (Microsoft's mssql-python), made robust (the owner, 2026-11-17:
    "SQL server and azure SQL are two things I use alot so make them robust"). Since the adapter's phase 5 its
    writing is the adapter's SQL Server section (adapter.py: the rows staged in a #temp table of the target's
    own types with each value's size, one MERGE WITH (HOLDLOCK), TRUNCATE, identity_insert, Azure's passing
    errors running the whole write again on a fresh connection, the dry run's keys counted by one join); this
    keeps what is checked first:

      columns    every column of the rows is the target's (sys.columns), none computed, the identity
                 column only with identity_insert chosen; the target's enabled triggers said
      keys       the keys given, else the target's primary key (none: refused)
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
        self._target: list[Any] | None = None
        super().__init__(connection, target, what, rows, dry_run, batch_size, engine)
        self.identity_insert = bool(identity_insert)

    # ===== the target, as sys.columns says it =====

    def target_table(self) -> list[Any]:
        """The target's columns (adapter.ServerColumn: name, type, size, identity, computed), read once."""
        from swissarmybench.adapters import adapter

        if self._target is None:
            try:
                self._target = adapter.server_columns(self._source(adapter), ".".join(self._parts()))
            except adapter.AdapterError:
                raise WriteError(
                    f"{self.target} is not a table on {self.connection} this sign-in may see."
                ) from None
        return self._target

    def target_columns(self) -> list[str]:
        return [c.name for c in self.target_table()]

    def column(self, name: str) -> Any:
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

    def _checked(self, keys: list[str]) -> tuple[dict[str, str], list[str]]:
        """SQL Server's checks: the keys first (none given: the primary key), then the columns."""
        if self.what == "create":
            return super()._checked(keys)
        if self.what in ("upsert", "delete"):
            keys = self.check_keys(keys, unique=self.what == "upsert")
        self.check_columns(keys if self.what == "delete" else None)
        return {c.casefold(): c for c in self.target_columns()}, keys

    # ===== values, and the adapter's source =====

    def _value(self, value: Any) -> Any:
        import math
        import uuid

        if isinstance(value, float) and math.isnan(value):
            return None  # NaN is NULL (pandas' NaT already is: DuckDB reads it as no value)
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, _dt.datetime) and value.tzinfo is not None:
            return value.isoformat(sep=" ")  # a datetimeoffset takes it as text: the instant, with its offset
        return super()._value(value)

    def _source(self, adapter: Any) -> Any:
        """The adapter's SQL Server source: identity_insert as chosen, a fresh connection (signed in its own
        way again) for a write run again after a passing error."""
        return adapter.Sql(
            self.conn,
            "sqlserver",
            self.connection,
            self._paramstyle,
            self._value,
            reopen=self._reopened,
            identity_insert=self.identity_insert,
        )

    def _reopened(self) -> Any:
        _, conn = live(self._given)
        return for_writes(conn)

    def __getattr__(self, name: str) -> Any:
        """A copy of the SQL Server starter made before the adapter wrote it (its own in_transaction, stage,
        merge...): refused in one line that says what to do."""
        if name in GONE_METHODS:
            raise WriteError(
                f"w.{name} went in 0.0.32: SQL Server's write is the adapter's now. Copy the Write to SQL "
                "Server starter as your own again, or end your cell with return w.by_adapter(keys)."
            )
        raise AttributeError(name)


# What the SQL Server starter called before the adapter wrote for it (a copy made then names them).
GONE_METHODS: frozenset[str] = frozenset(
    {
        "in_transaction", "insert", "insert_into", "stage", "matching", "merge", "merge_sql",
        "update_then_insert_sql", "delete_staged", "joined", "identity", "input_sizes", "rows_a_batch",
    }
)  # fmt: skip


__all__ = ["ENGINES", "Rows", "SqlServerWrite", "SqlWrite", "WriteError", "detect"]
