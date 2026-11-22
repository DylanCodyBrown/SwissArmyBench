"""SQL Server stood in for at mssql-python's seam, for the adapter's SQL Server writes (phase 5): a module
named `mssql_python` whose connect() gives connections over one DuckDB database that keeps the rows. Each
statement the adapter sends in T-SQL is run in DuckDB after a few fixed rewrites (brackets, #temp tables,
table hints, MERGE's BY TARGET, UPDATE and DELETE with a JOIN, the T-SQL types), so a test reads back exactly
what was written. sys.columns, the primary key and the triggers are answered from the columns each table was
made with. A connection is one transaction at a time (begun by its first statement, ended by commit or
rollback), its #temp tables its own and gone on a rollback, as SQL Server's are. `fail` queues errors raised
before a statement starts (a passing error, MERGE or TRUNCATE refused): they leave DuckDB's transaction as it
was. Made-up tables and rows only."""

from __future__ import annotations

import re
import types
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import duckdb

# T-SQL's types as DuckDB keeps them (the rest are DuckDB's too: int, bigint, decimal(p,s), date, real, float)
_TYPES = (
    (r"\bn?varchar\((\d+|max)\)", "VARCHAR"),
    (r"\bn?char\((\d+)\)", "VARCHAR"),
    (r"\bdatetime2\(\d+\)", "TIMESTAMP"),
    (r"\bdatetimeoffset\(\d+\)", "TIMESTAMPTZ"),
    (r"\bdatetime\b", "TIMESTAMP"),
    (r"\buniqueidentifier\b", "UUID"),
    (r"\bbit\b", "BOOLEAN"),
    (r"\bvarbinary\((\d+|max)\)", "BLOB"),
)
SQL_TYPES = {  # ODBC's numbers, as mssql-python names them
    "SQL_WVARCHAR": -9,
    "SQL_VARCHAR": 12,
    "SQL_DECIMAL": 3,
    "SQL_TYPE_TIMESTAMP": 93,
    "SQL_VARBINARY": -3,
    "SQL_INTEGER": 4,
    "SQL_BIT": -7,
    "SQL_BIGINT": -5,
    "SQL_SMALLINT": 5,
    "SQL_TINYINT": -6,
    "SQL_REAL": 7,
    "SQL_DOUBLE": 8,
    "SQL_TYPE_DATE": 91,
}


class Error(Exception):
    """mssql_python.Error's shape: one text, the server's words without their number."""


@dataclass
class Column:
    name: str
    type: str  # T-SQL's: nvarchar(40), decimal(12,2), int ...
    identity: bool = False
    computed: bool = False
    key: bool = False

    def row(self) -> tuple[Any, ...]:
        """sys.columns' row: name, type, max_length (bytes), precision, scale, is_identity, is_computed."""
        found = re.fullmatch(r"(\w+)(?:\((\w+)(?:,\s*(\d+))?\))?", self.type)
        assert found, self.type
        kind, size, scale = found[1].lower(), found[2], found[3]
        if kind in ("nvarchar", "nchar"):
            return (
                self.name,
                kind,
                -1 if size == "max" else 2 * int(size or 1),
                0,
                0,
                self.identity,
                self.computed,
            )
        if kind in ("varchar", "char", "varbinary"):
            return (
                self.name,
                kind,
                -1 if size == "max" else int(size or 1),
                0,
                0,
                self.identity,
                self.computed,
            )
        if kind in ("decimal", "numeric"):
            return (self.name, kind, 9, int(size or 18), int(scale or 0), self.identity, self.computed)
        if kind in ("datetime2", "datetimeoffset"):
            return (self.name, kind, 8, 27, int(size or 7), self.identity, self.computed)
        return (self.name, kind, 4, 10, 0, self.identity, self.computed)


@dataclass
class Server:
    """One made-up SQL Server: its DuckDB database, its tables' columns, what it was sent, what to refuse."""

    db: Any = field(default_factory=duckdb.connect)
    tables: dict[str, list[Column]] = field(default_factory=dict)
    statements: list[str] = field(default_factory=list)
    sizes: list[list[Any]] = field(default_factory=list)
    failures: list[tuple[str, BaseException]] = field(
        default_factory=list
    )  # (the statement's start, the error)
    connections: list[Connection] = field(default_factory=list)
    triggers: dict[str, list[str]] = field(default_factory=dict)

    def table(self, name: str, columns: Sequence[Column], rows: Sequence[Sequence[Any]] = ()) -> None:
        schema, _, table = name.partition(".")
        self.db.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        made = ", ".join(f'"{c.name}" {_duck_type(c.type)}' for c in columns)
        self.db.execute(f'CREATE TABLE "{schema}"."{table}" ({made})')
        for row in rows:
            self.db.execute(
                f'INSERT INTO "{schema}"."{table}" VALUES ({", ".join("?" for _ in row)})',  # noqa: S608
                list(row),
            )
        self.tables[f"[{schema}].[{table}]"] = list(columns)

    def rows(self, name: str) -> list[tuple[Any, ...]]:
        schema, _, table = name.partition(".")
        sql = f'SELECT * FROM "{schema}"."{table}" ORDER BY 1'  # noqa: S608
        found: list[tuple[Any, ...]] = self.db.execute(sql).fetchall()
        return found

    def connect(self, text: str = "", attrs_before: Any = None, timeout: int = 0) -> Connection:
        made = Connection(self)
        self.connections.append(made)
        return made

    def module(self) -> types.ModuleType:
        """The `mssql_python` module a test puts in sys.modules."""
        made = types.ModuleType("mssql_python")
        made.connect = self.connect  # type: ignore[attr-defined]
        made.Error = Error  # type: ignore[attr-defined]
        made.paramstyle = "qmark"  # type: ignore[attr-defined]
        for name, number in SQL_TYPES.items():
            setattr(made, name, number)
        return made


class Connection:
    """mssql-python's connection over the stand-in's DuckDB: a transaction at a time, its own #temp."""

    def __init__(self, server: Server) -> None:
        self.server = server
        self.db = server.db.cursor()  # its own DuckDB connection to the same database: its own temp tables
        self.open = False
        self.closed = False

    def cursor(self) -> Cursor:
        assert not self.closed, "a closed connection's cursor"
        return Cursor(self)

    def begin(self) -> None:
        if not self.open:
            self.db.execute("BEGIN TRANSACTION")
            self.open = True

    def commit(self) -> None:
        if self.open:
            self.db.execute("COMMIT")
        self.open = False

    def rollback(self) -> None:
        if self.open:
            self.db.execute("ROLLBACK")
        self.open = False

    def close(self) -> None:
        self.rollback()
        self.closed = True


class Cursor:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        self.description: list[tuple[Any, ...]] | None = None
        self.rowcount = -1
        self._rows: list[tuple[Any, ...]] = []

    def setinputsizes(self, sizes: list[Any]) -> None:
        self.conn.server.sizes.append(list(sizes))

    def execute(self, sql: str, *params: Any) -> Cursor:
        values = list(params[0]) if len(params) == 1 and isinstance(params[0], list | tuple) else list(params)
        self._run(sql, [values])
        return self

    def executemany(self, sql: str, batch: Sequence[Sequence[Any]]) -> None:
        self._run(sql, [list(r) for r in batch])

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows, self._rows = self._rows, []
        return rows

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]:
        rows, self._rows = self._rows[:size], self._rows[size:]
        return rows

    def close(self) -> None:
        pass

    def _run(self, sql: str, batches: list[list[Any]]) -> None:
        server = self.conn.server
        server.statements.append(sql)
        for at, (start, error) in enumerate(server.failures):
            if sql.startswith(start):
                del server.failures[at]
                raise error
        answered = self._answered(sql, batches[0] if batches else [])
        if answered is not None:
            self.description, self._rows = [(n,) for n in answered[0]], answered[1]
            return
        translated = translate(sql)
        if not translated:
            return
        self.conn.begin()
        db = self.conn.db
        if len(batches) > 1:
            db.executemany(translated, batches)
        else:
            db.execute(translated, batches[0] if batches and batches[0] else None)
        self.description = [(d[0],) for d in db.description] if db.description else None
        self._rows = db.fetchall() if db.description else []
        self.rowcount = -1

    def _answered(self, sql: str, values: list[Any]) -> tuple[list[str], list[tuple[Any, ...]]] | None:
        """sys.columns, the primary key and the triggers, from the columns each table was made with."""
        server = self.conn.server
        if "FROM sys.columns AS c JOIN sys.types" in sql:
            return ["name", "type", "max_length", "precision", "scale", "identity", "computed"], [
                c.row() for c in server.tables.get(str(values[0]), [])
            ]
        if "is_primary_key" in sql:
            return ["name"], [(c.name,) for c in server.tables.get(str(values[0]), []) if c.key]
        if "sys.triggers" in sql:
            return ["name"], [(t,) for t in server.triggers.get(str(values[0]), [])]
        return None


def _duck_type(kind: str) -> str:
    for pattern, duck in _TYPES:
        kind = re.sub(pattern, duck, kind, flags=re.I)
    return kind


def translate(sql: str) -> str:
    """The adapter's T-SQL as DuckDB runs it ("": a statement with nothing to do here)."""
    text = sql.strip().rstrip(";")
    if re.match(r"(SAVE|ROLLBACK) TRANSACTION \w+$|SET IDENTITY_INSERT ", text):
        return ""  # a savepoint (a refusal here is raised before its statement starts), the identity switch
    dropped = re.match(r"IF OBJECT_ID\('tempdb\.\.#(\w+)'\) IS NOT NULL DROP TABLE #\w+$", text)
    if dropped:
        return f"DROP TABLE IF EXISTS {dropped[1]}"
    temp = text.startswith("CREATE TABLE #")
    text = re.sub(r"\[([^\]]*)\]", r'"\1"', text)
    text = re.sub(r"#(\w+)", r"\1", text)
    text = re.sub(r" WITH \((?:UPDLOCK, )?HOLDLOCK\)", "", text)
    text = text.replace(" COLLATE DATABASE_DEFAULT", "")
    text = _duck_type(text)
    if temp:
        text = text.replace("CREATE TABLE ", "CREATE TEMP TABLE ", 1)
    deleted = re.match(r"DELETE t FROM (\S+) AS t JOIN (\S+) AS s ON (.+)$", text, re.S)
    if deleted:
        return f"DELETE FROM {deleted[1]} AS t USING {deleted[2]} AS s WHERE {deleted[3]}"  # noqa: S608
    updated = re.match(r"UPDATE t SET (.+) FROM (\S+) AS t JOIN (\S+) AS s ON (.+)$", text, re.S)
    if updated:
        sets = re.sub(r"\bt\.", "", updated[1])
        return f"UPDATE {updated[2]} AS t SET {sets} FROM {updated[3]} AS s WHERE {updated[4]}"  # noqa: S608
    if text.startswith("MERGE INTO "):
        text = text.replace(" BY TARGET", "")
        text = re.sub(
            r"UPDATE SET (.+)$", lambda m: "UPDATE SET " + re.sub(r"\bt\.", "", m[1]), text, flags=re.M
        )
    return text
