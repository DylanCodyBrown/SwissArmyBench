"""The mock clients a local sandbox API gets from `connection(name)` (the owner, 2026-11-21: "Things that get
built
should always hand back to a client that mimics the connections client shape" / "No never run against live
data
ever").

Each mock has its real client's shape (the same public methods, arguments and return types;
tests/test_sandbox_
clients.py holds each against the real one) and reads and writes only the project's sandbox, through the app's
/sandbox/data/<key> route: the statements in the source's own language, made DuckDB SQL there
(domain/sandbox_dialects.py). Nothing here can reach a connection: this process has no connection code, no
variable and no secret.

  MockDbApi         a database connection (sqlite3, psycopg, PyMySQL, snowflake, oracledb, trino): cursor(),
                    execute, commit, rollback, close; its cursor's execute(sql, params), fetch*, description
  MockSqlServer     the SQL Server starter's SqlServer: cursor() whose execute(sql, *params) is
  mssql-python's,
                    read_arrow(sql), for_writes(), about(), tested(), raw
  MockDataverse     the Dataverse starter's Dataverse: tables(), columns(), rows()/read() with an OData filter
  and
                    order, fetch(FetchXML), count(), catalog(), cursor() (T-SQL SELECT)
  MockSharePoint    the SharePoint lists starter's SharePointLists: tables(), rows()/read() with filters,
                    create(), update(), delete(), ids(), catalog()
  MockDuckDB        a table from a file or made empty (connection("Sandbox")): DuckDB's execute and fetch*

A refusal says the API.py line it came from. Standard library (pyarrow and pandas where a real one answers
them).
"""

from __future__ import annotations

import datetime
import decimal
import http.client
import inspect
import json
import os
import re
import threading
import time
import urllib.parse
from collections.abc import Iterator, Sequence
from typing import Any

URL_VARIABLE = "SAB_SANDBOX_DATA"  # the app's /sandbox/data/<key> address, this process's only door
MANY_AT_ONCE = 50_000  # an executemany's parameter sets sent in one call


class MockError(RuntimeError):
    """A refusal from the sandbox (a table it does not have, SQL it cannot emulate), with its API.py line."""


class SqlServerError(MockError):
    pass


class DataverseError(MockError):
    pass


class SharePointError(MockError):
    pass


def _where_in_api() -> str:
    for frame in inspect.stack()[2:]:
        name = os.path.basename(frame.filename)
        if name.lower() == "api.py" or name.startswith("api_"):
            return f"{name} line {frame.lineno}: "
    return ""


def _sql_line(said: str) -> str:
    """A refusal that starts with its SQL's own line ("Line 3: ..."), said after API.py's line without a
    second "Line": the first line of the SQL goes unsaid, a later one is "(line 3 of its SQL)"."""
    found = re.match(r"Line (\d+): (.*)$", said, re.S)
    if not found:
        return said
    rest = found.group(2)
    rest = rest[:1].upper() + rest[1:]
    return rest if found.group(1) == "1" else f"{rest.rstrip()} (line {found.group(1)} of its SQL)"


class Link:
    """The one door: a JSON POST to the app's sandbox data route with this run's key in its path. Each thread
    keeps its connection open (HTTP/1.1 keep-alive), so a call is one request, not a new TCP connection."""

    def __init__(self, url: str, error: type[MockError] = MockError) -> None:
        self.url = url
        self.error = error
        parts = urllib.parse.urlsplit(url)
        self._host, self._port, self._path = parts.hostname or "127.0.0.1", parts.port or 80, parts.path
        self._local = threading.local()

    def _connection(self) -> http.client.HTTPConnection:
        found: http.client.HTTPConnection | None = getattr(self._local, "connection", None)
        if found is None:
            found = http.client.HTTPConnection(self._host, self._port, timeout=600)
            self._local.connection = found
        return found

    def _drop(self) -> None:
        found = getattr(self._local, "connection", None)
        if found is not None:
            found.close()
        self._local.connection = None

    def ask(self, op: str, **body: Any) -> dict[str, Any]:
        data = json.dumps({"op": op} | body, default=_json_default).encode()
        headers = {"Content-Type": "application/json"}
        for attempt in (1, 2):  # a kept connection the server closed meanwhile: once more on a new one
            try:
                connection = self._connection()
                connection.request("POST", self._path, data, headers)
                answer = connection.getresponse()
                raw = answer.read()
            except (http.client.HTTPException, ConnectionError) as failed:
                self._drop()
                if attempt == 2:
                    raise self.error(
                        f"{_where_in_api()}The sandbox could not be reached ({failed})."
                    ) from None
                continue
            except OSError as failed:
                self._drop()
                raise self.error(f"{_where_in_api()}The sandbox could not be reached ({failed}).") from None
            if answer.status >= 400:
                try:
                    said = json.loads(raw or b"{}").get("error") or answer.reason
                except ValueError:
                    said = answer.reason
                raise self.error(f"{_where_in_api()}{_sql_line(str(said))}")
            return dict(json.loads(raw or b"{}"))
        raise self.error(f"{_where_in_api()}The sandbox could not be reached.")  # pragma: no cover


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return str(value)


def _typed(value: Any, kind: str) -> Any:
    """A value back in the type the real driver gives for its DuckDB type."""
    if value is None:
        return None
    upper = kind.upper()
    try:
        if upper == "DATE":
            return datetime.date.fromisoformat(str(value))
        if upper.startswith("TIMESTAMP"):
            return datetime.datetime.fromisoformat(str(value))
        if upper.startswith("TIME"):
            return datetime.time.fromisoformat(str(value))
        if upper.startswith("DECIMAL"):
            return decimal.Decimal(str(value))
    except ValueError:
        return value
    return value


def _rows(answer: dict[str, Any]) -> tuple[list[str], list[str], list[tuple[Any, ...]]]:
    columns = list(answer.get("columns") or [])
    types = list(answer.get("types") or ["VARCHAR"] * len(columns))
    rows = []
    for r in answer.get("rows") or []:
        values = [r.get(c) for c in columns] if isinstance(r, dict) else list(r)
        rows.append(tuple(_typed(v, t) for v, t in zip(values, types, strict=False)))
    return columns, types, rows


def _frame(columns: list[str], rows: list[tuple[Any, ...]]) -> Any:
    """Rows as a DataFrame (a list of dicts without pandas), as the real clients give them."""
    try:
        import pandas as pd
    except ImportError:
        return [dict(zip(columns, r, strict=False)) for r in rows]
    return pd.DataFrame.from_records(rows, columns=columns)


def _arrow(columns: list[str], rows: list[tuple[Any, ...]]) -> Any:
    import pyarrow as pa

    if not rows:
        return pa.table({c: pa.array([], pa.string()) for c in columns})
    return pa.Table.from_pylist([dict(zip(columns, r, strict=False)) for r in rows])


# ===== a DB-API database =====


class MockCursor:
    """A DB-API 2.0 cursor over the sandbox: the source's SQL and its driver's parameter marks."""

    arraysize = 1
    description: list[tuple[Any, ...]] | None = None
    rowcount = -1

    def __init__(self, owner: Any) -> None:
        self._owner = owner
        self._rows: list[tuple[Any, ...]] = []
        self._at = 0
        self.description: list[tuple[Any, ...]] | None = None
        self.rowcount = -1

    def _run(self, sql: str, params: Any) -> Any:
        answer = self._owner._link.ask(
            "sql", connection=self._owner._name, sql=sql, params=params, dialect=self._owner._dialect
        )
        columns, types, rows = _rows(answer)
        self._rows, self._at = rows, 0
        self.description = [
            (c, t, None, None, None, None, None) for c, t in zip(columns, types, strict=False)
        ] or None
        self.rowcount = int(answer.get("rowcount", len(rows)))
        return self

    def execute(self, sql: str, parameters: Any = ()) -> Any:
        return self._run(sql, list(parameters) if isinstance(parameters, tuple) else parameters)

    def executemany(self, sql: str, seq_of_parameters: Any) -> Any:
        """Every parameter set in one call to the sandbox (a part of MANY_AT_ONCE sets at a time), each
        part in one transaction: the same rows as one execute each, without a round trip a row."""
        sets = [list(p) if isinstance(p, tuple) else p for p in seq_of_parameters]
        total = 0
        for at in range(0, len(sets), MANY_AT_ONCE):
            answer = self._owner._link.ask(
                "sql_many",
                connection=self._owner._name,
                sql=sql,
                params=sets[at : at + MANY_AT_ONCE],
                dialect=self._owner._dialect,
            )
            total += int(answer.get("rowcount", 0))
        self._rows, self._at, self.description = [], 0, None
        self.rowcount = total
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        if self._at >= len(self._rows):
            return None
        self._at += 1
        return self._rows[self._at - 1]

    def fetchmany(self, size: int | None = None) -> list[tuple[Any, ...]]:
        size = size or self.arraysize
        got = self._rows[self._at : self._at + size]
        self._at += len(got)
        return got

    def fetchall(self) -> list[tuple[Any, ...]]:
        got = self._rows[self._at :]
        self._at = len(self._rows)
        return got

    def close(self) -> None:
        self._rows = []

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        while (row := self.fetchone()) is not None:
            yield row

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class MockDbApi:
    """A database connection's DB-API shape. Each statement commits as it runs: rollback() undoes nothing in
    the sandbox (Reset or a checkpoint does)."""

    def __init__(self, name: str, dialect: str, link: Link) -> None:
        self._name, self._dialect, self._link = name, dialect, link

    def cursor(self) -> MockCursor:
        return MockCursor(self)

    def execute(self, sql: str, parameters: Any = ()) -> Any:
        return self.cursor().execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: Any) -> Any:
        return self.cursor().executemany(sql, seq_of_parameters)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ===== the SQL Server starter's SqlServer =====


class MockSqlServerCursor(MockCursor):
    def execute(self, sql: str, *params: Any) -> Any:  # mssql-python's own
        if len(params) == 1 and isinstance(params[0], (list, tuple)):
            params = tuple(params[0])
        return self._run(sql, list(params))

    def executemany(self, sql: str, rows: Any) -> Any:
        return MockCursor.executemany(self, sql, [list(r) for r in rows])


class MockSqlServer:
    """The SQL Server starter's SqlServer over the sandbox: T-SQL with mssql-python's ? marks."""

    dbms = "sqlserver"
    TRIES = 1
    RESUME_SECONDS = 0
    BATCH_ROWS = 50_000
    sleep = staticmethod(time.sleep)
    clock = staticmethod(time.monotonic)

    def __init__(self, name: str, link: Link) -> None:
        self._name, self._dialect, self._link = name, "sqlserver", link
        self.settings: dict[str, Any] = {"server": "the sandbox", "database": name}
        self.sign_in = "the sandbox (no sign-in)"
        self.notes: list[str] = []

    def driver(self) -> Any:
        raise SqlServerError(
            f"{_where_in_api()}The sandbox's mock has no driver: use cursor() or read_arrow()."
        )

    def connection_string(self) -> str:
        return ""  # nothing to sign in to

    def access_token(self) -> str:
        raise SqlServerError(f"{_where_in_api()}The sandbox's mock signs in to nothing: it has no token.")

    def uses_token(self) -> bool:
        return False

    def connect(self) -> Any:
        return self

    @property
    def raw(self) -> Any:
        return self

    def cursor(self) -> MockSqlServerCursor:
        return MockSqlServerCursor(self)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def for_writes(self) -> Any:
        return self

    def read_arrow(self, sql: str, batch_rows: int | None = None) -> Any:
        cursor = self.cursor().execute(sql)
        if cursor.description is None:
            raise SqlServerError(f"{_where_in_api()}The statement returned no rows to read.")
        return _arrow([d[0] for d in cursor.description], cursor.fetchall())

    def about(self) -> dict[str, Any]:
        return {"driver": "the sandbox's mock", "sign_in": self.sign_in, "version": "DuckDB over the sandbox"}

    def tested(self, rows: int = 20) -> dict[str, Any]:
        return {"found": "the sandbox's mock", "about": self.about(), "notes": []}


# ===== the Dataverse starter's Dataverse =====


class MockDataverseCursor(MockSqlServerCursor):
    """The SQL endpoint's cursor (T-SQL, SELECT only)."""

    def execute(self, sql: str, *parameters: Any) -> Any:
        if len(parameters) == 1 and isinstance(parameters[0], (list, tuple)):
            parameters = tuple(parameters[0])
        head = str(sql).lstrip().split(None, 1)[0].upper() if str(sql).strip() else ""
        if head not in ("SELECT", "WITH"):
            raise DataverseError(f"{_where_in_api()}Dataverse's SQL endpoint is read-only: SELECT only.")
        return self._run(sql, list(parameters))


class MockDataverse:
    """The Dataverse starter's Dataverse over the sandbox: OData reads, FetchXML, the SQL endpoint."""

    API = "/api/data/v9.2"
    PAGE = 5000

    def __init__(self, name: str, link: Link) -> None:
        self._name, self._dialect, self._link = name, "sqlserver", link
        self.url = "https://sandbox.invalid"
        self.api = self.url + self.API

    def _ask(self, op: str, **body: Any) -> dict[str, Any]:
        return self._link.ask(op, connection=self._name, **body)

    def access_token(self) -> str:
        raise DataverseError(f"{_where_in_api()}The sandbox's mock signs in to nothing: it has no token.")

    def get(self, path: str, what: str, prefer: str | None = None) -> Any:
        raise DataverseError(
            f"{_where_in_api()}The sandbox's mock cannot emulate a Web API call ({what}: {path}); "
            "use rows(), read(), fetch() or cursor()."
        )

    def pages(self, path: str, limit: int | None) -> Any:
        return self.get(path, "Reading pages")

    def tables(self) -> list[dict[str, str]]:
        names = self._ask("client")["tables"]
        return [{"table": n, "title": n, "set": n + "s"} for n in names]

    @staticmethod
    def listed(table: Any) -> dict[str, str]:
        return {
            "table": str(table["LogicalName"]),
            "title": str(table["LogicalName"]),
            "set": str(table["EntitySetName"]),
        }

    def table(self, name: str) -> dict[str, str]:
        wanted = str(name).strip().casefold()
        for t in self.tables():
            if wanted in (t["table"].casefold(), t["set"].casefold(), t["title"].casefold()):
                return t
        raise DataverseError(f"{_where_in_api()}The sandbox has no table {name!r} from {self._name}.")

    def described(self, name: str) -> list[dict[str, Any]]:
        answer = self._link.ask("columns", table=self.table(name)["table"])
        return [
            {"name": c["name"], "field": c["name"], "type": c["type"], "title": c["name"]}
            for c in answer["columns"]
        ]

    def columns(self, name: str) -> list[dict[str, Any]]:
        return [{"column": c["name"], "type": c["type"], "title": c["title"]} for c in self.described(name)]

    def catalog(self) -> list[dict[str, Any]]:
        rows = []
        for t in self.tables():
            place = {"table_schema": "dbo", "table_name": t["table"]}
            rows.append(place | {"column_name": "", "data_type": "", "description": t["title"]})
            rows += [
                place | {"column_name": c["column"], "data_type": c["type"], "description": c["title"]}
                for c in self.columns(t["table"])
            ]
        return rows

    def count(self, name: str) -> int | None:
        answer = self._ask("odata", table=self.table(name)["table"], limit=0)
        return int(answer.get("total") or 0)

    def rows(
        self,
        name: str,
        columns: Sequence[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        frame: bool = False,
    ) -> tuple[Any, int | None]:
        answer = self._ask(
            "odata", table=self.table(name)["table"], columns=list(columns or []), filter=filter,
            order_by=order_by, limit=limit,
        )  # fmt: skip
        names, _, rows = _rows(answer)
        found = _frame(names, rows) if frame else [dict(zip(names, r, strict=False)) for r in rows]
        return found, answer.get("total")

    def read(
        self,
        name: str,
        columns: Sequence[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> Any:
        return self.rows(name, columns, filter, order_by, limit, frame=True)[0]

    def fetch(self, fetch_xml: str) -> Any:
        names, _, rows = _rows(self._ask("fetchxml", fetch_xml=fetch_xml))
        return _frame(names, rows)

    def tested(self, rows: int = 20) -> dict[str, Any]:
        listed = self.tables()
        return {"found": f"the sandbox's mock: {len(listed)} tables"}

    def cursor(self) -> MockDataverseCursor:
        return MockDataverseCursor(self)

    def close(self) -> None:
        return None


# ===== the SharePoint lists starter's SharePointLists =====


class MockSharePoint:
    """The SharePoint lists starter's SharePointLists over the sandbox: each list a sandbox table."""

    def __init__(self, name: str, link: Link) -> None:
        self._name, self._link = name, link
        self.how = "the sandbox"
        self.found: list[dict[str, Any]] | None = None

    def _ask(self, op: str, **body: Any) -> dict[str, Any]:
        return self._link.ask(op, connection=self._name, **body)

    def _refused(self, what: str) -> MockError:
        return SharePointError(
            f"{_where_in_api()}The sandbox's mock cannot emulate {what}; use rows() or read()."
        )

    def all_lists(self) -> list[dict[str, Any]]:
        return [{"id": t["id"], "name": t["table"], "displayName": t["table"]} for t in self.tables()]

    def lookup_texts(self, target: Any, ids: Any) -> Any:
        raise self._refused("a lookup's texts")

    def items(self, list_id: str, columns: Any, limit: int | None = None, filters: Any = None) -> Any:
        raise self._refused("Graph's items")

    def duck(self) -> Any:
        raise self._refused("its own DuckDB")

    def finish(
        self, rows: Any, names: Any, types: Any, limit: Any, columns: Any, filters: Any, frame: Any, how: Any
    ) -> Any:
        raise self._refused("finish()")

    def finish_arrow(self, table: Any, limit: Any, columns: Any, filters: Any, frame: Any, how: Any) -> Any:
        raise self._refused("finish_arrow()")

    def tables(self) -> list[dict[str, Any]]:
        names = self._ask("client")["tables"]
        return [{"schema": "", "table": n, "id": n, "web": ""} for n in names]

    def table(self, name: str, schema: str = "") -> dict[str, Any]:
        wanted = str(name).strip().casefold()
        for t in self.tables():
            if wanted in (t["table"].casefold(), t["id"].casefold()):
                return t
        raise SharePointError(f"{_where_in_api()}The sandbox has no list {name!r} from {self._name}.")

    def columns(self, list_id: str) -> list[dict[str, Any]]:
        answer = self._link.ask("columns", table=self.table(list_id)["table"])
        return [
            {
                "name": c["name"],
                "field": c["name"],
                "kind": "text",
                "type": c["type"],
                "indexed": c["key"],
                "target": None,
            }
            for c in answer["columns"]
            if c["name"] != "id"
        ]

    def catalog(self) -> list[dict[str, Any]]:
        rows = []
        for t in self.tables():
            place = {"table_schema": "", "table_name": t["table"], "table_type": "TABLE"}
            rows.append(place | {"column_name": "", "data_type": "", "description": "SharePoint list"})
            rows += [
                place | {"column_name": c["name"], "data_type": c["type"], "description": c["kind"]}
                for c in self.columns(t["id"])
            ]
        return rows

    def rows(
        self,
        table: str,
        schema: str = "",
        limit: int | None = None,
        columns: Sequence[str] | None = None,
        filters: Any = None,
        frame: bool = False,
    ) -> tuple[Any, int]:
        answer = self._ask(
            "list",
            table=self.table(table)["table"],
            columns=list(columns or []),
            filters=filters,
            limit=limit,
        )
        names, _, rows = _rows(answer)
        table_out = _arrow(names, rows)
        if frame:
            try:
                return table_out.to_pandas(), int(answer.get("total") or 0)
            except ImportError:
                return table_out, int(answer.get("total") or 0)
        return table_out, int(answer.get("total") or 0)

    def read(
        self,
        table: str,
        schema: str = "",
        columns: Sequence[str] | None = None,
        filters: Any = None,
        limit: int | None = None,
    ) -> Any:
        return self.rows(table, schema, limit, columns, filters, frame=True)[0]

    def create(self, table: str, rows: Any) -> dict[str, int]:
        t = self.table(table)["table"]
        done = self._link.ask("insert", table=t, rows=[{k: v for k, v in r.items()} for r in rows])
        return {"done": int(done.get("rows") or 0)}

    def update(self, table: str, rows: Any, key: str = "id") -> dict[str, int]:
        t = self.table(table)["table"]
        ops = [
            {
                "op": "update",
                "table": t,
                "values": {k: v for k, v in r.items() if k != key},
                "where": {key: r[key]},
            }
            for r in rows
        ]
        done = self._link.ask("batch", ops=ops)
        return {"done": len(done.get("counts") or [])}

    def delete(self, table: str, ids: Any) -> dict[str, int]:
        t = self.table(table)["table"]
        done = self._link.ask("batch", ops=[{"op": "delete", "table": t, "where": {"id": i}} for i in ids])
        return {"done": len(done.get("counts") or [])}

    def ids(self, table: str, values: Any, key: str = "id") -> dict[Any, Any]:
        if key == "id":
            return {v: v for v in values}
        found, _ = self.rows(table, columns=["id", key])
        by_value: dict[Any, list[Any]] = {}
        for r in found.to_pylist():
            by_value.setdefault(r[key], []).append(r["id"])
        missing = [v for v in values if v not in by_value]
        if missing:
            raise SharePointError(f"{_where_in_api()}No item has {key} {missing[0]!r}.")
        return {v: by_value[v][0] for v in values}

    def tested(self, rows: int = 20) -> dict[str, Any]:
        return {"found": f"the sandbox's mock: {len(self.tables())} lists"}

    def cursor(self) -> Any:
        raise SharePointError(
            f"{_where_in_api()}SharePoint has no SQL of its own: read a list with rows() or read()."
        )

    def close(self) -> None:
        return None


# ===== a plain DuckDB client: a table from a file or made empty =====


class _PerThread(threading.local):
    rows: list[tuple[Any, ...]]
    at: int = 0
    description: list[tuple[Any, ...]] | None = None
    rowcount: int = -1

    def __init__(self) -> None:
        self.rows = []


class MockDuckDB(MockCursor):
    """DuckDB's connection shape over the sandbox (execute returns the connection; fetch* read its answer).

    connection("Sandbox") is one object for the whole process, and an API answers several requests at once
    (each in a thread of its own): what execute() answered is kept per thread, so one request never fetches
    another's rows."""

    def __init__(self, link: Link) -> None:
        self._name, self._dialect, self._link = "Sandbox", "duckdb", link
        self._state = _PerThread()
        super().__init__(self)

    @property
    def _rows(self) -> list[tuple[Any, ...]]:
        return self._state.rows

    @_rows.setter
    def _rows(self, value: list[tuple[Any, ...]]) -> None:
        self._state.rows = value

    @property
    def _at(self) -> int:
        return self._state.at

    @_at.setter
    def _at(self, value: int) -> None:
        self._state.at = value

    @property
    def description(self) -> list[tuple[Any, ...]] | None:
        return self._state.description

    @description.setter
    def description(self, value: list[tuple[Any, ...]] | None) -> None:
        self._state.description = value

    @property
    def rowcount(self) -> int:
        return self._state.rowcount

    @rowcount.setter
    def rowcount(self, value: int) -> None:
        self._state.rowcount = value

    def execute(self, query: str, parameters: Any = None) -> Any:
        return self._run(query, parameters or [])

    def cursor(self) -> MockDuckDB:
        return MockDuckDB(self._link)

    def commit(self) -> Any:
        return self

    def rollback(self) -> Any:
        return self

    def df(self) -> Any:
        return _frame([d[0] for d in self.description or []], self.fetchall())

    def fetch_arrow_table(self) -> Any:
        return _arrow([d[0] for d in self.description or []], self.fetchall())


# ===== which mock a connection gets =====

NO_MOCK = (
    "The sandbox has no mock for {name} ({kind}) yet: its tables answer in DuckDB SQL through "
    'connection("Sandbox").'
)


def mock_for(name: str, client: dict[str, Any], link: Link) -> Any:
    """The mock for what the sandbox says `name` is: its tables kind, template and dialect."""
    kind = str(client.get("kind") or "duckdb")
    dialect = str(client.get("dialect") or "")
    template = str(client.get("template") or "")
    if kind == "duckdb":
        return MockDuckDB(link)
    if kind in ("dataverse", "dataverse_web"):
        return MockDataverse(name, Link(link.url, DataverseError))
    if kind == "sharepoint":
        return MockSharePoint(name, Link(link.url, SharePointError))
    if kind == "database" and dialect in ("sqlserver", "tsql") and "pyodbc" not in template:
        return MockSqlServer(name, Link(link.url, SqlServerError))
    if kind == "database":
        return MockDbApi(name, dialect or "duckdb", link)
    raise MockError(_where_in_api() + NO_MOCK.format(name=name, kind=kind))


def clients(url: str | None = None) -> Any:
    """connection(name) for this process: each name's mock, made once."""
    link = Link(url or os.environ[URL_VARIABLE])
    made: dict[str, Any] = {}

    def connection(name: str) -> Any:
        key = str(name or "Sandbox").strip()
        if key.casefold() not in made:
            client = link.ask("client", connection=key)
            made[key.casefold()] = mock_for(key, client, link)
        return made[key.casefold()]

    return connection
