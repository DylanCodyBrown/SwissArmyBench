"""SQL Server and Azure SQL made robust (domain/sql_server.py): the connection's own code run against a
stand-in for pyodbc at the seam (it records each connection string, attribute and statement, and answers
typed rows), with a clock and a sleep of the test's own. No SQL Server runs here: the T-SQL the app sends
is checked as text (and parsed as T-SQL). Made-up servers, databases and rows only."""

from __future__ import annotations

import _thread
import datetime as dt
import decimal
import struct
import sys
import threading
import types
import uuid
from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pytest
import sqlglot
from starlette.testclient import TestClient

from swissarmybench.domain import sql_server
from swissarmybench.domain.blades import apply_settings, detect_settings, read_code
from swissarmybench.domain.connection_usage import Calls, status
from tests.conftest import AUTH

# ===== the stand-in for pyodbc =====


class Error(Exception):
    """pyodbc.Error's shape: (SQLSTATE, message)."""


class OperationalError(Error):
    pass


class FakeCursor:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn
        self.description: list[tuple[Any, ...]] | None = None
        self.rows: list[tuple[Any, ...]] = []
        self.cancelled = False
        self.fast_executemany = False

    def execute(self, sql: str, *params: Any) -> FakeCursor:
        self.conn.server.statements.append((sql, params))
        answer = self.conn.server.answer(sql, params, self)
        if isinstance(answer, BaseException):
            raise answer
        self.description, self.rows = answer
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows, self.rows = self.rows, []
        return rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows.pop(0) if self.rows else None

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]:
        rows, self.rows = self.rows[:size], self.rows[size:]
        return rows

    def cancel(self) -> None:
        self.cancelled = True
        self.conn.server.cancelled.set()

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self, server: FakeServer, text: str, attrs: dict[int, bytes] | None) -> None:
        self.server, self.text, self.attrs = server, text, attrs or {}
        self.converters: dict[int, Any] = {}
        self.closed = False
        self.timeout = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def add_output_converter(self, kind: int, function: Any) -> None:
        self.converters[kind] = function

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def getinfo(self, what: int) -> str:
        return "Microsoft SQL Server"


class FakeServer:
    """What the stand-in answers: connect refusals queued, statements answered by a function."""

    def __init__(self) -> None:
        self.drivers = ["ODBC Driver 18 for SQL Server"]
        self.refusals: list[BaseException] = []
        self.connections: list[FakeConnection] = []
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.failures: list[BaseException] = []  # raised by the next statements, one each
        self.tables: dict[str, list[tuple[str, str]]] = {}
        self.result: tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]] = ([("n", int)], [(1,)])
        self.cancelled = threading.Event()
        self.block = False

    def connect(self, text: str, attrs_before: Any = None, timeout: int = 0) -> FakeConnection:
        if self.refusals:
            raise self.refusals.pop(0)
        made = FakeConnection(self, text, attrs_before)
        self.connections.append(made)
        return made

    def answer(self, sql: str, params: tuple[Any, ...], cursor: FakeCursor) -> Any:
        if self.block:
            assert self.cancelled.wait(5), "the statement was never cancelled"
            return OperationalError("HY008", "[HY008] Operation canceled (0) (SQLExecDirectW)")
        if self.failures:
            return self.failures.pop(0)
        if "FROM sys.columns AS c JOIN sys.types" in sql:
            found = self.tables.get(str(params[0]), [])
            return [("name", str), ("type", str)], list(found)
        if sql.startswith("SELECT @@VERSION"):
            version = "Microsoft SQL Azure (RTM) - 12.0.2000.8 \n\tCopyright (C) 2022 Microsoft Corporation"
            return [("v", str)] * 4, [(version, "SQL Azure", "Latin1_General_100_CS_AS", "GP_S_Gen5_1")]
        description = [(name, kind, None, None, None, None, True) for name, kind in self.result[0]]
        return description, list(self.result[1])


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeServer]:
    made = FakeServer()
    module = types.ModuleType("pyodbc")
    module.drivers = lambda: list(made.drivers)  # type: ignore[attr-defined]
    module.connect = made.connect  # type: ignore[attr-defined]
    module.Error = Error  # type: ignore[attr-defined]
    module.SQL_DBMS_NAME = 17  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyodbc", module)
    monkeypatch.delitem(sys.modules, "mssql_python", raising=False)
    yield made


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def clock(self) -> float:
        return self.now


def runtime(clock: Clock | None = None) -> dict[str, Any]:
    """The connection's runtime as its code holds it, with the test's clock."""
    names: dict[str, Any] = {"__name__": "__blade__"}
    exec(compile(sql_server._IMPORTS + sql_server.RUNTIME, "<sqlserver>", "exec"), names)  # noqa: S102
    if clock is not None:
        names["SqlServer"].sleep = staticmethod(clock.sleep)
        names["SqlServer"].clock = staticmethod(clock.clock)
    return names


def run_code(code: str, secrets: dict[str, str] | None = None) -> dict[str, Any]:
    """A starter's whole code, run as the app runs it (secret() by name)."""
    names: dict[str, Any] = {"__name__": "__blade__", "secret": lambda n: (secrets or {})[n]}
    exec(compile(code, "<blade>", "exec"), names)  # noqa: S102
    return names


def opened(server: FakeServer) -> str:
    return server.connections[-1].text


# ===== the errors, in plain words =====
D18 = "[Microsoft][ODBC Driver 18 for SQL Server]"

PYODBC_SAID = {
    "18456": f"[28000] {D18}[SQL Server]Login failed for user 'sam'. (18456)",
    "40615": f"[42000] {D18}[SQL Server]Cannot open server 'shop' requested "
    "by the login. Client with IP address '203.0.113.7' is not allowed to access the server. (40615)",
    "40613": f"[HY000] {D18}[SQL Server]Database 'sales' on server 'shop' is "
    "not currently available. Please retry the connection later. (40613)",
    "certificate": f"[08001] {D18}SSL Provider: [error:0A000086:SSL "
    "routines::certificate verify failed:self-signed certificate] (-1) (SQLDriverConnect)",
    "IM002": "[IM002] [unixODBC][Driver Manager]Data source name not found and no default driver specified",
    "not found": f"[08001] {D18}TCP Provider: Error code 0x2AF9 (11001)",
    "HYT00": f"[HYT00] {D18}Login timeout expired (0) (SQLDriverConnect)",
    "229": f"[42000] {D18}[SQL Server]The SELECT permission was denied on the "
    "object 'orders'. (229) (SQLExecDirectW)",
    "3906": '[42000] [SQL Server]Failed to update database "sales" because the database is read-only. (3906)',
}


@pytest.mark.parametrize("key", sorted(PYODBC_SAID))
def test_each_error_is_said_in_plain_words_with_its_fix(key: str) -> None:
    said = PYODBC_SAID[key]
    assert sql_server.error_key(said) == key
    words, fix = sql_server.ERRORS[key]
    plain = sql_server.explain(said, "Linux")
    assert plain.startswith(words.split("{")[0]) and fix.split("{")[0][:30] in plain
    assert runtime()["explain"](said).split("[")[0] == plain.split("[")[0] or key == "IM002"


def test_the_firewall_names_the_address_and_the_portal() -> None:
    plain = sql_server.explain(PYODBC_SAID["40615"])
    assert "203.0.113.7" in plain and "Networking" in plain and "private endpoint" in plain


def test_a_missing_driver_says_the_install_command_for_this_system() -> None:
    assert "winget install --id Microsoft.msodbcsql.18" in sql_server.explain("[IM002]", "Windows")
    assert "brew install msodbcsql18" in sql_server.explain("[IM002]", "Darwin")
    assert "apt-get install -y msodbcsql18" in sql_server.explain("[IM002]", "Linux")
    assert "mssql-python" in sql_server.explain("[IM002]", "Linux")


def test_an_error_it_does_not_know_stays_as_it_is() -> None:
    assert (
        sql_server.explain("[42S22] something else entirely (99999)")
        == "[42S22] something else entirely (99999)"
    )


@pytest.mark.parametrize("number", sorted(sql_server.TRANSIENT))
def test_azures_passing_errors_are_known(number: str) -> None:
    assert sql_server.transient(f"[HY000] passing ({number})")
    assert runtime()["passing"](OperationalError("HY000", f"passing ({number})"))


def test_a_refusal_does_not_pass() -> None:
    assert not sql_server.transient(PYODBC_SAID["18456"])
    assert sql_server.transient("[08S01] Communication link failure (0)")


# ===== connecting: drivers, sign-ins, options =====


def test_the_newest_odbc_driver_is_chosen_then_17(server: FakeServer) -> None:
    names = runtime()
    server.drivers = ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"]
    conn = names["SqlServer"]("sql01.shop.local", "sales", "windows")
    assert opened(server).startswith("Driver={ODBC Driver 18 for SQL Server};") and conn.about()["driver"]
    server.drivers = ["ODBC Driver 17 for SQL Server"]
    names["SqlServer"]("sql01.shop.local", "sales", "windows")
    assert "Driver={ODBC Driver 17 for SQL Server}" in opened(server) and "Encrypt=yes;" in opened(server)
    with pytest.raises(names["SqlServerError"], match="strict needs ODBC Driver 18"):
        names["SqlServer"]("sql01.shop.local", "sales", "windows", encrypt="strict")


def test_no_driver_says_what_to_install_never_silently(server: FakeServer) -> None:
    names = runtime()
    server.drivers = []
    with pytest.raises(names["SqlServerError"], match="ODBC Driver 18 for SQL Server"):
        names["SqlServer"]("sql01.shop.local", "sales", "windows")


def test_mssql_python_is_used_when_there_is_no_odbc_driver(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    module = types.ModuleType("mssql_python")

    def connect(text: str, attrs_before: Any = None, timeout: int = 0) -> FakeConnection:
        calls.append(text)
        return FakeConnection(server, text, attrs_before)

    module.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mssql_python", module)
    server.drivers = []
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    assert not calls[0].startswith("Driver=") and conn.about()["driver"] == "mssql-python"


def test_every_option_goes_into_the_connection_string(server: FakeServer) -> None:
    names = runtime()
    names["SqlServer"](
        "sql01.shop.local",
        "sales",
        "sql_login",
        user="sam",
        password="pa;ss}word",
        instance="REPORTS",
        trust_server_certificate=True,
        host_name_in_certificate="*.shop.local",
        read_only_intent=True,
        multi_subnet_failover=True,
        encrypt="optional",
    )
    text = opened(server)
    assert "Server=sql01.shop.local\\REPORTS;" in text and "Database=sales;" in text
    assert "UID=sam;" in text and "PWD={pa;ss}}word};" in text  # braced, its } doubled
    assert "Encrypt=optional;TrustServerCertificate=yes;" in text
    assert (
        "HostNameInCertificate={*.shop.local}" not in text and "HostNameInCertificate=*.shop.local;" in text
    )
    assert "ApplicationIntent=ReadOnly;" in text and "MultiSubnetFailover=Yes;" in text
    names["SqlServer"]("sql01.shop.local", "sales", "windows", port=14330)
    assert "Server=sql01.shop.local,14330;" in opened(server) and "Trusted_Connection=yes;" in opened(server)
    names["SqlServer"]("tcp:shop.database.windows.net,1433", "sales", "entra_default")
    assert "Server=tcp:shop.database.windows.net,1433;" in opened(server)
    assert "Authentication=ActiveDirectoryDefault;" in opened(server)


def test_a_token_goes_beside_the_connection_string_and_is_taken_again_before_it_runs_out(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = runtime()
    issued: list[float] = []

    class Credential:
        def get_token(self, scope: str) -> Any:
            assert scope == "https://database.windows.net/.default"
            issued.append(names["time"].time())
            return types.SimpleNamespace(token=f"made-up-token-{len(issued)}", expires_on=issued[-1] + 3600)

    conn = names["SqlServer"]("shop.database.windows.net", "sales", "entra_you", credential=Credential())
    sent = server.connections[-1].attrs[1256]
    token = "made-up-token-1".encode("utf-16-le")
    assert sent == struct.pack(f"<I{len(token)}s", len(token), token)
    assert "UID=" not in opened(server) and "PWD=" not in opened(server)
    conn.cursor()
    assert len(server.connections) == 1  # an hour left: the same connection
    later = issued[0] + 3600 - 200  # under five minutes left
    monkeypatch.setattr(names["time"], "time", lambda: later)
    conn.cursor()
    assert len(server.connections) == 2 and server.connections[0].closed
    assert server.connections[-1].attrs[1256] != sent  # a new token


def test_a_paused_serverless_database_is_waited_for_and_said(server: FakeServer, capsys: Any) -> None:
    clock = Clock()
    names = runtime(clock)
    paused = OperationalError("HY000", PYODBC_SAID["40613"])
    server.refusals = [paused, paused, paused]
    conn = names["SqlServer"]("shop.database.windows.net", "sales", "windows")
    assert clock.slept == [1, 2, 4] and len(server.connections) == 1
    assert all("resuming" in n for n in conn.notes) and "resuming" in capsys.readouterr().err


def test_a_database_that_stays_paused_is_said_in_plain_words(server: FakeServer) -> None:
    clock = Clock()
    names = runtime(clock)
    server.refusals = [OperationalError("HY000", PYODBC_SAID["40613"]) for _ in range(20)]
    with pytest.raises(OperationalError) as raised:  # the driver's own class: except pyodbc.Error still works
        names["SqlServer"]("shop.database.windows.net", "sales", "windows")
    assert (
        sum(clock.slept) >= sql_server.RESUME_SECONDS - 16
        and sum(clock.slept) <= sql_server.RESUME_SECONDS + 16
    )
    assert raised.value.args[0] == "HY000" and "serverless database that was paused" in raised.value.args[1]


def test_other_passing_errors_are_tried_again_a_few_times_then_said(server: FakeServer) -> None:
    clock = Clock()
    names = runtime(clock)
    busy = OperationalError("HY000", "[HY000] Azure SQL busy (40501)")
    server.refusals = [busy, busy]
    names["SqlServer"]("shop.database.windows.net", "sales", "windows")
    assert clock.slept == [1, 2]
    server.refusals = [busy] * 10
    with pytest.raises(OperationalError, match="Azure SQL is busy"):
        names["SqlServer"]("shop.database.windows.net", "sales", "windows")
    assert clock.slept[2:] == [1, 2, 4, 8]  # TRIES (5) in all


def test_a_refused_login_is_never_tried_again(server: FakeServer) -> None:
    clock = Clock()
    names = runtime(clock)
    server.refusals = [Error("28000", PYODBC_SAID["18456"])]
    with pytest.raises(Error, match="refused the sign-in") as raised:
        names["SqlServer"]("sql01.shop.local", "sales", "sql_login", user="sam", password="made-up")
    assert clock.slept == [] and raised.value.args[0] == "28000" and "(18456)" in raised.value.args[1]
    assert "made-up" not in str(raised.value)  # the password is never in the words


# ===== reading =====


def test_a_read_is_run_again_on_a_new_connection_after_a_passing_error(server: FakeServer) -> None:
    clock = Clock()
    names = runtime(clock)
    conn = names["SqlServer"]("sql01.shop.local", "sales", "windows")
    server.failures = [OperationalError("08S01", "[08S01] Communication link failure (10054)")]
    cursor = conn.cursor().execute("SELECT order_id FROM dbo.orders")
    assert cursor.fetchall() == [(1,)] and len(server.connections) == 2 and clock.slept == [1]
    server.failures = [OperationalError("08S01", "[08S01] Communication link failure (10054)")]
    with pytest.raises(OperationalError):  # a write is never run again here
        conn.cursor().execute("UPDATE dbo.orders SET amount = 1")
    assert len(server.connections) == 2


def test_columns_the_driver_cannot_read_are_read_as_text() -> None:
    read = runtime()["plain_read"]
    columns = [("id", "int"), ("where", "geography"), ("path", "hierarchyid"), ("extra", "sql_variant")]
    assert read("SELECT TOP 100 * FROM [dbo].[shops]", columns) == (
        "SELECT TOP 100 [id], [where].ToString() AS [where], [path].ToString() AS [path], "
        "CAST([extra] AS nvarchar(4000)) AS [extra] FROM [dbo].[shops]"
    )
    assert read("SELECT [id], [where] FROM [dbo].[shops] WHERE [id] = 3", columns) == (
        "SELECT [id], [where].ToString() AS [where] FROM [dbo].[shops] WHERE [id] = 3"
    )
    assert read("SELECT * FROM [dbo].[orders]", [("id", "int")]) is None  # nothing to change
    assert read("SELECT id FROM dbo.shops JOIN x ON 1 = 1", columns) is None  # not a plain read


def test_a_plain_read_asks_sys_columns_once_per_table(server: FakeServer) -> None:
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    server.tables["[dbo].[shops]"] = [("id", "int"), ("where", "geography")]
    for _ in range(2):
        conn.cursor().execute("SELECT TOP 5 * FROM [dbo].[shops]")
    sent = [s for s, _ in server.statements]
    assert sum("sys.columns" in s for s in sent) == 1
    assert sent[-1] == "SELECT TOP 5 [id], [where].ToString() AS [where] FROM [dbo].[shops]"


TYPES = [
    # (as SQL Server declares it, pyodbc's description: type, size, precision, scale), values, Arrow
    ("int", (int, 10, 10, 0), [1, None], "int32"),
    ("bigint", (int, 19, 19, 0), [2**40], "int64"),
    ("smallint", (int, 5, 5, 0), [-3], "int16"),
    ("tinyint", (int, 3, 3, 0), [255], "uint8"),
    ("bit", (bool, 1, 1, 0), [True, False], "bool"),
    ("decimal(12,2)", (decimal.Decimal, 12, 12, 2), [decimal.Decimal("1234567890.12")], "decimal128(12, 2)"),
    ("money", (decimal.Decimal, 19, 19, 4), [decimal.Decimal("12.3456")], "decimal128(19, 4)"),
    ("smallmoney", (decimal.Decimal, 10, 10, 4), [decimal.Decimal("-1.5")], "decimal128(10, 4)"),
    ("float", (float, 53, 53, 0), [1.5], "double"),
    ("real", (float, 24, 24, 0), [1.5], "float"),
    ("date", (dt.date, 10, 10, 0), [dt.date(2026, 1, 31)], "date32[day]"),
    ("time(7)", (dt.time, 16, 16, 7), [dt.time(13, 14, 15, 123456)], "time64[us]"),
    ("datetime2(7)", (dt.datetime, 27, 27, 7), [dt.datetime(2026, 1, 31, 9, 30, 0, 123456)], "timestamp[us]"),
    (
        "datetimeoffset(7)",
        (dt.datetime, 34, 34, 7),
        [dt.datetime(2026, 1, 31, 9, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))],
        "timestamp[us, tz=UTC]",
    ),
    ("uniqueidentifier", (str, 36, 36, 0), ["6F9619FF-8B86-D011-B42D-00C04FC964FF"], "string"),
    ("uniqueidentifier (native)", (uuid.UUID, 36, 36, 0), [uuid.UUID(int=5)], "string"),
    ("varbinary(max)", (bytearray, 0, 0, 0), [bytearray(b"\x00\x01")], "binary"),
    ("nvarchar(max)", (str, 0, 0, 0), ["Grüße, 東京"], "string"),
    ("xml", (str, 0, 0, 0), ["<a>1</a>"], "string"),
    ("geography (as text)", (str, 0, 0, 0), ["POINT (-122.3 47.6)"], "string"),
]


@pytest.mark.parametrize(("declared", "described", "values", "arrow"), TYPES, ids=[t[0] for t in TYPES])
def test_each_type_reads_into_arrow_exactly(
    server: FakeServer, declared: str, described: tuple[Any, ...], values: list[Any], arrow: str
) -> None:
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    kind, size, precision, scale = described
    server.result = ([("value", kind)], [(v,) for v in values])
    original = server.answer

    def typed(sql: str, params: tuple[Any, ...], cursor: FakeCursor) -> Any:
        answer = original(sql, params, cursor)
        if isinstance(answer, tuple) and answer[0] and answer[0][0][0] == "value":
            return [("value", kind, None, size, precision, scale, True)], answer[1]
        return answer

    server.answer = typed  # type: ignore[method-assign]
    table = conn.read_arrow("SELECT value FROM dbo.kinds")
    assert str(table.schema.field("value").type) == arrow, declared
    got = table.column("value").to_pylist()
    if arrow.startswith("timestamp[us, tz"):
        assert got[0] == values[0]  # the same instant (kept as UTC)
    elif "uniqueidentifier" in declared:
        assert got == [str(v) for v in values]
    elif arrow == "binary":
        assert got == [bytes(v) for v in values]
    else:
        assert got == values


def test_reads_come_in_batches_and_a_value_that_does_not_fit_makes_the_column_text(
    server: FakeServer,
) -> None:
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    server.result = ([("id", int), ("code", int)], [(i, i if i < 5 else "X-7") for i in range(10)])
    table = conn.read_arrow("SELECT id, code FROM dbo.orders", batch_rows=3)
    assert table.num_rows == 10 and table.column("id").num_chunks == 4
    assert table.schema.field("code").type == pa.string() and table.column("code").to_pylist()[-1] == "X-7"


def test_a_datetimeoffset_keeps_its_offset() -> None:
    raw = struct.pack("<6hI2h", 2026, 3, 1, 23, 30, 5, 123456700, -5, 0)
    found = runtime()["offset_time"](raw)
    assert found == dt.datetime(2026, 3, 1, 23, 30, 5, 123456, dt.timezone(dt.timedelta(hours=-5)))


def test_the_driver_is_told_how_to_read_what_it_cannot(server: FakeServer) -> None:
    runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    assert set(server.connections[-1].converters) == {-155, -151, -150}


def test_an_interrupt_cancels_the_statement_on_the_server(server: FakeServer) -> None:
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    cursor = conn.cursor()
    server.block = True
    threading.Timer(0.3, _thread.interrupt_main).start()  # as the kernel's Interrupt does
    with pytest.raises(KeyboardInterrupt):
        cursor.execute("SELECT * FROM dbo.big_table")
    assert server.cancelled.is_set()


# ===== writes: the Write starters' connection =====


def test_writes_go_through_the_primary_and_know_sql_server(server: FakeServer) -> None:
    from swissarmybench.client.write_sql import detect, for_writes

    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows", read_only_intent=True)
    assert "ApplicationIntent=ReadOnly" in opened(server)
    writer = for_writes(conn)
    assert writer is not conn and "ApplicationIntent" not in opened(server)
    assert detect(conn).key == "sqlserver" and detect(writer).key == "sqlserver"
    plain = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    assert for_writes(plain) is plain
    cursor = plain.cursor()
    cursor.fast_executemany = True  # the driver's own setting, set through
    assert cursor._inner.fast_executemany is True


def test_a_closed_connection_opens_again_for_the_next_try(server: FakeServer) -> None:
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    conn.close()
    conn.cursor()
    assert len(server.connections) == 2


# ===== the starters' code and the form =====


@pytest.mark.parametrize("template", ["sqlserver", "azuresql"])
def test_every_way_to_sign_in_runs(
    server: FakeServer, template: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = types.ModuleType("azure.identity")

    class Credential:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def get_token(self, scope: str) -> Any:
            return types.SimpleNamespace(token="made-up", expires_on=4_000_000_000)

    for name in (
        "AzureCliCredential",
        "ChainedTokenCredential",
        "InteractiveBrowserCredential",
        "VisualStudioCodeCredential",
        "CertificateCredential",
    ):
        setattr(identity, name, Credential)
    monkeypatch.setitem(sys.modules, "azure", types.ModuleType("azure"))
    monkeypatch.setitem(sys.modules, "azure.identity", identity)
    for label, mark, code in sql_server.sign_ins(template):
        if mark in (sql_server.mark("managed_identity"), sql_server.mark("app_secret")):
            continue  # web requests: below
        names = run_code(code, {"password": "made-up", "client secret": "made-up"})
        assert names["conn"].sign_in in mark, label
        assert read_code(code).variable == "conn"


def test_the_app_registration_and_managed_identity_sign_in_with_the_standard_library(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = runtime()
    asked: list[str] = []

    class Answer:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def read(self) -> bytes:
            return self.body

        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *exc: Any) -> None:
            pass

    def urlopen(request: Any, timeout: int = 0) -> Answer:
        asked.append(request.full_url)
        return Answer(b'{"access_token": "made-up", "expires_in": 3600}')

    monkeypatch.setattr(names["urllib"].request, "urlopen", urlopen)
    names["SqlServer"](
        "shop.database.windows.net", "sales", "app_secret", tenant_id="t1", client_id="c1", client_secret="s"
    )
    assert asked == ["https://login.microsoftonline.com/t1/oauth2/v2.0/token"]
    assert 1256 in server.connections[-1].attrs

    class Opener:
        def open(self, request: Any, timeout: int = 0) -> Answer:
            asked.append(request.full_url)
            return Answer(b'{"access_token": "made-up", "expires_on": "4000000000"}')

    monkeypatch.setattr(names["urllib"].request, "build_opener", lambda *a: Opener())
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://127.0.0.1:9/msi/token")
    monkeypatch.setenv("IDENTITY_HEADER", "made-up")
    names["SqlServer"]("shop.database.windows.net", "sales", "managed_identity", client_id="c2")
    assert asked[-1].startswith("http://127.0.0.1:9/msi/token?api-version=2019-08-01&resource=")
    assert "client_id=c2" in asked[-1]


def test_the_code_needs_only_pyodbc_and_for_two_ways_azure_identity() -> None:
    from swissarmybench.domain.blades import needed

    for way in sql_server.ORDER["sqlserver"]:
        pips = [p.pip for p in needed(sql_server.code(way), lambda m: True)]
        assert pips == (
            ["azure-identity", "pyodbc"] if way in ("entra_you", "app_certificate") else ["pyodbc"]
        ), way


def test_server_database_user_client_id_and_tenant_may_come_from_environment_variables() -> None:
    code = sql_server.code("app_secret")
    settings = {s.name: s for s in detect_settings(code)}
    values = {
        settings["server"].id: {"value": "sql01.shop.local", "env": "WAREHOUSE_SERVER"},
        settings["database"].id: {"value": "sales", "env": "WAREHOUSE_DATABASE"},
        settings["tenant_id"].id: {"value": "my-tenant-id", "env": "AZURE_TENANT_ID"},
        settings["client_id"].id: {"value": "my-client-id", "env": "AZURE_CLIENT_ID"},
    }
    mapped = apply_settings(code, values)
    assert 'server=os.environ.get("WAREHOUSE_SERVER", "sql01.shop.local")' in mapped
    assert 'tenant_id=os.environ.get("AZURE_TENANT_ID", "my-tenant-id")' in mapped
    back = {s.name: s.env for s in detect_settings(mapped) if s.env}
    assert back == {
        "server": "WAREHOUSE_SERVER",
        "database": "WAREHOUSE_DATABASE",
        "tenant_id": "AZURE_TENANT_ID",
        "client_id": "AZURE_CLIENT_ID",
    }
    user = sql_server.code("sql_login")
    found = {s.name: s for s in detect_settings(user)}["user"]
    mapped = apply_settings(user, {found.id: {"value": "sam", "env": "WAREHOUSE_USER"}})
    assert 'user=os.environ.get("WAREHOUSE_USER", "sam")' in mapped
    # Plain again: the value typed, no variable.
    again = {s.name: s for s in detect_settings(mapped)}["user"]
    assert 'user="sam"' in apply_settings(mapped, {again.id: {"value": "sam", "env": None}})


def test_the_form_offers_options_choices_and_variables(client: TestClient) -> None:
    types_ = {t["id"]: t for t in client.get("/connections/types", headers=AUTH).json()["types"]}
    form = types_["azuresql"]
    assert form["env_settings"] == ["server", "database", "user", "client_id", "tenant_id"]
    assert "encryption" in form["options"] and "trust server certificate" in form["options"]
    assert form["choices"]["encryption"] == ["mandatory", "optional", "strict"]
    assert types_["postgres"]["env_settings"] == [] and types_["postgres"]["options"] == []
    assert form["catalog"]["command"] == sql_server.CATALOG


# ===== the T-SQL the app sends =====


@pytest.mark.parametrize("name", ["CATALOG", "FOREIGN_KEYS", "UNIQUE_KEYS"])
def test_the_system_view_queries_are_t_sql(name: str) -> None:
    sqlglot.parse_one(getattr(sql_server, name), read="tsql")


def test_the_catalog_reads_the_system_views_not_a_count_of_rows() -> None:
    text = sql_server.CATALOG
    for view in (
        "sys.columns",
        "sys.types",
        "sys.partitions",
        "MS_Description",
        "sys.synonyms",
        "temporal_type",
    ):
        assert view in text
    assert "COUNT(" not in text and "CONCAT_WS" not in text  # 2016 has no CONCAT_WS


def test_a_tables_row_count_comes_from_sys_partitions() -> None:
    text = sql_server.count_sql("dbo", "Order Lines")
    assert "sys.partitions" in text and "N'[dbo].[Order Lines]'" in text
    assert "COUNT_BIG(*) FROM [dbo].[Order Lines]" in text  # a view's are counted
    sqlglot.parse_one(text, read="tsql")
    assert "O''Brien" in sql_server.count_sql("dbo", "O'Brien")


# ===== foreign keys into the ERD =====

FKS = {
    "columns": [
        "name",
        "from_schema",
        "from_table",
        "from_column",
        "to_schema",
        "to_table",
        "to_column",
        "position",
        "disabled",
    ],
    "rows": [
        ["FK_lines_orders", "dbo", "Order Lines", "order_id", "dbo", "orders", "order_id", 1, False],
        ["FK_lines_stock", "dbo", "Order Lines", "sku", "dbo", "stock", "sku", 2, 0],
        ["FK_lines_stock", "dbo", "Order Lines", "shop_id", "dbo", "stock", "shop_id", 1, 0],
        ["FK_orders_customers", "sales", "orders", "customer_id", "sales", "customers", "id", 1, 1],
        ["FK_profile", "dbo", "profiles", "customer_id", "sales", "customers", "id", 1, 0],
    ],
}
UNIQUE = {
    "columns": ["table_schema", "table_name", "index_name", "column_name"],
    "rows": [["dbo", "profiles", "UQ_profiles_customer", "customer_id"]],
}


def test_foreign_keys_become_the_models_relationships_composite_keys_whole() -> None:
    model = sql_server.relationships_model("Warehouse", [FKS, UNIQUE])
    by = {r.note: r for r in model.relationships}
    stock = by["foreign key FK_lines_stock"]
    assert (stock.from_table, stock.from_columns, stock.to_table, stock.to_columns) == (
        "Order_Lines",
        ("shop_id", "sku"),
        "stock",
        ("shop_id", "sku"),
    )
    assert by["foreign key FK_lines_orders"].kind == "many-to-one"
    assert by["foreign key FK_profile"].kind == "one-to-one"  # its column is a unique key
    assert by["foreign key FK_orders_customers"].active is False  # disabled
    assert model.sources["orders"] == "connection:Warehouse"


def test_a_database_with_no_foreign_keys_says_so(client: TestClient) -> None:
    saved = client.post("/connections", json=_stand_in("Empty", fks=[]), headers=AUTH)
    assert saved.status_code == 200, saved.text
    answer = client.post("/connections/Empty/relationships", json={}, headers=AUTH)
    assert answer.status_code == 400 and "no foreign keys" in answer.text


def _stand_in(name: str, fks: list[list[Any]] | None = None, fail: str = "") -> dict[str, Any]:
    """A SQL Server connection at the seam: code whose `conn` answers the app's T-SQL with made-up rows
    (no driver), as the real one's cursor does; `fail`: what its Test raises."""
    rows = FKS["rows"] if fks is None else fks
    code = f"""
class Cursor:
    def __init__(self):
        self.description, self.rows = None, []

    def execute(self, sql, *params):
        if {fail!r}:
            raise RuntimeError({fail!r})
        if "sys.foreign_keys" in sql:
            names = {FKS["columns"]!r}
            self.rows = [tuple(r) for r in {rows!r}]
        elif "sys.indexes" in sql:
            names = {UNIQUE["columns"]!r}
            self.rows = [tuple(r) for r in {UNIQUE["rows"]!r}]
        else:
            names, self.rows = ["n"], [(1,)]
        self.description = [(n, str, None, None, None, None, True) for n in names]
        return self

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class Warehouse:
    dbms = "sqlserver"

    def cursor(self):
        return Cursor()

    def tested(self, rows):
        Cursor().execute("SELECT 1")
        return {{"found": "signed in", "about": {{"driver": "ODBC Driver 18 for SQL Server",
                 "sign_in": "entra_you", "version": "Microsoft SQL Azure (RTM) - 12.0.2000.8",
                 "edition": "SQL Azure", "service_objective": "GP_S_Gen5_1",
                 "collation": "Latin1_General_100_CS_AS", "case_sensitive": True}}}}

    def close(self):
        pass


conn = Warehouse()
"""
    return {"name": name, "kind": "sql", "template": "azuresql", "dialect": "sqlserver", "code": code}


def test_import_relationships_reads_the_foreign_keys_into_the_erd(client: TestClient) -> None:
    assert client.post("/connections", json=_stand_in("Warehouse"), headers=AUTH).status_code == 200
    answer = client.post("/connections/Warehouse/relationships", json={}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    got = answer.json()
    assert len(got["imported"]) == 4 and "Order_Lines" in got["tables"]
    model = client.get("/relationships", headers=AUTH).json()
    joins = {(r["from"], tuple(r["from_columns"]), r["to"]) for r in model["relationships"]}
    assert ("Order_Lines", ("shop_id", "sku"), "stock") in joins


def test_the_card_says_the_server_and_a_failing_ones_plain_error(client: TestClient) -> None:
    assert client.post("/connections", json=_stand_in("Warehouse"), headers=AUTH).status_code == 200
    assert client.post("/blades/Warehouse/test", headers=AUTH).status_code == 200
    card = next(
        c
        for c in client.get("/connections/usage", headers=AUTH).json()["connections"]
        if c["name"] == "Warehouse"
    )
    assert card["status"] == "works" and card["about"][
        0
    ] == "ODBC Driver 18 for SQL Server · " + sql_server.label_of("entra_you")
    assert "GP_S_Gen5_1" in card["about"][1] and "Case-sensitive collation" in card["about"][2]
    words = sql_server.explain(PYODBC_SAID["40615"])
    assert client.post("/connections", json=_stand_in("Shop", fail=words), headers=AUTH).status_code == 200
    assert client.post("/blades/Shop/test", headers=AUTH).status_code != 200
    card = next(
        c for c in client.get("/connections/usage", headers=AUTH).json()["connections"] if c["name"] == "Shop"
    )
    assert card["status"] == "failing" and "203.0.113.7" in card["error"] and "Networking" in card["error"]


def test_a_resuming_database_is_its_own_status() -> None:
    failed = Calls({"test": 1}, 1.0, "test", False)
    assert status(failed, [], False, sql_server.explain(PYODBC_SAID["40613"])) == "resuming"
    assert status(failed, [], False, "something else") == "failing"


def test_the_card_words() -> None:
    lines = sql_server.card_words(
        {
            "driver": "mssql-python",
            "sign_in": "managed_identity",
            "version": "Microsoft SQL Server 2022 (RTM-CU12)",
            "edition": "Developer Edition (64-bit)",
        }
    )
    assert lines == [
        "mssql-python · Microsoft Entra: managed identity (in Azure)",
        "Microsoft SQL Server 2022 (RTM-CU12) · Developer Edition (64-bit)",
    ]


def test_dataverse_signs_its_sql_endpoint_in_with_the_same_token_code() -> None:
    from swissarmybench.domain import dataverse

    assert sql_server.TOKEN_CODE in dataverse.YOU


def test_the_robust_code_is_told_from_an_older_one() -> None:
    assert sql_server.is_robust(sql_server.code("windows"))
    assert not sql_server.is_robust(
        'import pyodbc\nconn = pyodbc.connect("Driver={ODBC Driver 18 for SQL Server};")'
    )
    assert sql_server.way_of(sql_server.code("app_certificate")) == "app_certificate"
