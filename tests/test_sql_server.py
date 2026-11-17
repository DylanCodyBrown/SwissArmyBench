"""SQL Server and Azure SQL made robust (domain/sql_server.py), on Microsoft's mssql-python (the owner,
2026-11-17: "We need both Python-TDS for Dataverse and mssql for azure and sql server connections"): the
connection's own code run against a stand-in for mssql-python at the seam (it records each connection
string, attribute and statement, and answers typed rows, its errors shaped as mssql-python's: the server's
words without its number), with a clock and a sleep of the test's own. tests/test_sql_server_real.py runs
the same code against a real SQL Server when one is given. Made-up servers, databases and rows only."""

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
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
import sqlglot
from starlette.testclient import TestClient

from swissarmybench.domain import sql_server
from swissarmybench.domain.blades import apply_settings, detect_settings, read_code
from swissarmybench.domain.connection_usage import Calls, status
from tests.conftest import AUTH

GOLDEN = Path(__file__).parent / "golden" / "sql_server"

# ===== the stand-in for mssql-python =====


class Error(Exception):
    """mssql_python.Error's shape: made of (driver_error, ddbc_error), said as one text."""

    def __init__(self, driver_error: str, ddbc_error: str = "") -> None:
        text = f"Driver Error: {driver_error}; DDBC Error: {ddbc_error}" if ddbc_error else driver_error
        super().__init__(text)


class OperationalError(Error):
    pass


class Handle:
    """mssql-python's statement handle: _cancel() is SQLCancel."""

    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor

    def _cancel(self) -> None:
        self.cursor.cancelled = True
        self.cursor.conn.server.cancelled.set()


class FakeCursor:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn
        self.description: list[tuple[Any, ...]] | None = None
        self.rows: list[tuple[Any, ...]] = []
        self.cancelled = False
        self.hstmt = Handle(self)

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

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self, server: FakeServer, text: str, attrs: dict[int, bytes] | None) -> None:
        self.server, self.text, self.attrs = server, text, attrs or {}
        self.closed = False
        self.timeout = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FakeServer:
    """What the stand-in answers: connect refusals queued, statements answered by a function."""

    def __init__(self) -> None:
        self.refusals: list[BaseException] = []
        self.connections: list[FakeConnection] = []
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.failures: list[BaseException] = []  # raised by the next statements, one each
        self.tables: dict[str, list[tuple[str, str]]] = {}
        self.result: tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]] = ([("n", int)], [(1,)])
        self.cancelled = threading.Event()
        self.block = False
        self.timeouts: list[int] = []

    def connect(self, text: str, attrs_before: Any = None, timeout: int = 0) -> FakeConnection:
        self.timeouts.append(timeout)
        if self.refusals:
            raise self.refusals.pop(0)
        made = FakeConnection(self, text, attrs_before)
        self.connections.append(made)
        return made

    def answer(self, sql: str, params: tuple[Any, ...], cursor: FakeCursor) -> Any:
        if self.block:
            assert self.cancelled.wait(5), "the statement was never cancelled"
            return OperationalError("Operation canceled", "[Microsoft]Operation canceled")
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
    module = types.ModuleType("mssql_python")
    module.connect = made.connect  # type: ignore[attr-defined]
    module.Error = Error  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mssql_python", module)
    monkeypatch.delitem(sys.modules, "pyodbc", raising=False)
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
# As mssql-python says them (Driver Error: the SQLSTATE's words; DDBC Error: the server's own, no number):
# the texts it gave against a real SQL Server 2022 (docs/verified.md), and Azure SQL's documented words.
SERVER = "[Microsoft][SQL Server]"


def said(driver: str, ddbc: str) -> str:
    return f"Driver Error: {driver}; DDBC Error: {ddbc}"


MSSQL_SAID = {
    "18456": said("Invalid authorization specification", f"{SERVER}Login failed for user 'sam'."),
    "18452": said(
        "Invalid authorization specification",
        f"{SERVER}Login failed. The login is from an untrusted domain and cannot be used with Integrated "
        "authentication.",
    ),
    "4060": said(
        "Invalid authorization specification",
        f'{SERVER}Cannot open database "sales" requested by the login. The login failed.',
    ),
    "40615": said(
        "General error",
        f"{SERVER}Cannot open server 'shop' requested by the login. Client with IP address '203.0.113.7' is "
        "not allowed to access the server.",
    ),
    "40532": said("General error", f'{SERVER}Cannot open server "shop" requested by the login.'),
    "40613": said(
        "General error",
        f"{SERVER}Database 'sales' on server 'shop' is not currently available. Please retry the connection "
        "later.",
    ),
    "40501": said(
        "General error", f"{SERVER}The service is currently busy. Retry the request after 10 seconds."
    ),
    "certificate": said(
        "Client unable to establish connection",
        "[Microsoft]SSL Provider: [error:0A000086:SSL routines::certificate verify failed:self-signed "
        "certificate]",
    ),
    "not found": said("Client unable to establish connection", "[Microsoft]TCP Provider: Error code 0x2AF9"),
    "HYT00": said("Timeout expired", "[Microsoft]Login timeout expired"),
    "229": said(
        "Syntax error or access violation",
        f"{SERVER}The SELECT permission was denied on the object 'orders', database 'sales', schema 'dbo'.",
    ),
    "208": said("Base table or view not found", f"{SERVER}Invalid object name 'nope'."),
    "207": said("Column not found", f"{SERVER}Invalid column name 'nope'."),
    "1205": said(
        "Serialization failure",
        f"{SERVER}Transaction (Process ID 61) was deadlocked on lock resources with another process and "
        "has been chosen as the deadlock victim. Rerun the transaction.",
    ),
    "3906": said(
        "General error", f'{SERVER}Failed to update database "sales" because the database is read-only.'
    ),
    "driver": "No module named 'mssql_python'",
}


@pytest.mark.parametrize("key", sorted(MSSQL_SAID))
def test_each_error_is_said_in_plain_words_with_its_fix(key: str) -> None:
    text = MSSQL_SAID[key]
    assert sql_server.error_key(text) == key
    words, fix = sql_server.ERRORS[key]
    plain = sql_server.explain(text)
    assert plain.startswith(words.split("{")[0]) and fix.split("{")[0][:30] in plain
    assert runtime()["explain"](text) == plain


def test_a_number_in_the_text_still_says_its_entry() -> None:
    assert sql_server.error_key("[28000] Login failed for user 'sam'. (18456)") == "18456"
    assert sql_server.error_key("[HY000] something about (40613)") == "40613"


def test_the_firewall_names_the_address_and_the_portal() -> None:
    plain = sql_server.explain(MSSQL_SAID["40615"])
    assert "203.0.113.7" in plain and "Networking" in plain and "private endpoint" in plain


def test_a_missing_driver_says_the_pip_command_and_no_odbc_driver() -> None:
    plain = sql_server.explain(MSSQL_SAID["driver"])
    assert "pip install mssql-python" in plain and "nothing else to install" in plain
    assert "ODBC" not in plain and "winget" not in plain and "msodbcsql" not in plain


def test_an_error_it_does_not_know_stays_as_it_is() -> None:
    text = said("General error", f"{SERVER}something else entirely")
    assert sql_server.explain(text) == text


@pytest.mark.parametrize("number", sorted(sql_server.TRANSIENT))
def test_azures_passing_errors_are_known(number: str) -> None:
    assert sql_server.transient(f"[HY000] passing ({number})")
    assert runtime()["passing"](OperationalError("General error", f"passing ({number})"))


@pytest.mark.parametrize(("words", "key"), sql_server.WORDS, ids=[k for _, k in sql_server.WORDS])
def test_azures_passing_errors_are_known_by_their_words_too(words: str, key: str) -> None:
    text = said("General error", f"{SERVER}{words.capitalize()} (made up).")
    assert sql_server.transient(text) == (key in sql_server.TRANSIENT)
    assert runtime()["passing"](OperationalError("General error", f"{SERVER}{words}")) == (
        key in sql_server.TRANSIENT
    )


def test_a_dropped_connection_passes_and_a_refusal_does_not() -> None:
    assert not sql_server.transient(MSSQL_SAID["18456"])
    assert sql_server.transient(
        said("Communication link failure", "[Microsoft]TCP Provider: Error code 0x2746")
    )
    assert sql_server.transient("[08S01] Communication link failure (0)")


# ===== connecting: the driver, sign-ins, options =====


def test_mssql_python_is_the_one_driver_no_odbc_driver_named(server: FakeServer) -> None:
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "sql_login", user="sam", password="made-up")
    assert not opened(server).startswith("Driver=") and "Driver" not in opened(server)
    assert conn.about()["driver"] == "mssql-python"
    assert server.timeouts[-1] == 30  # the login timeout


def test_a_missing_mssql_python_is_the_import_error_the_install_prompt_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "mssql_python", None)  # importing it fails, as when it is not there
    with pytest.raises(ModuleNotFoundError) as raised:
        runtime()["SqlServer"]("sql01.shop.local", "sales", "sql_login", user="sam", password="made-up")
    assert raised.value.name == "mssql_python"


def test_an_older_codes_driver_setting_is_taken_and_left_alone(server: FakeServer) -> None:
    runtime()["SqlServer"]("sql01.shop.local", "sales", "windows", driver="ODBC Driver 17 for SQL Server")
    assert "Driver" not in opened(server)


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
    names["SqlServer"]("sql01.shop.local", "sales", "windows", encrypt="strict")
    assert "Encrypt=strict;" in opened(server) and "TrustServerCertificate" not in opened(server)
    names["SqlServer"]("sql01.shop.local", "sales", "windows", encrypt="yes")  # an older code's word
    assert "Encrypt=mandatory;" in opened(server)


def test_the_connection_string_uses_only_keys_mssql_python_takes(server: FakeServer) -> None:
    allowed = {
        "server",
        "database",
        "uid",
        "pwd",
        "authentication",
        "trusted_connection",
        "encrypt",
        "trustservercertificate",
        "hostnameincertificate",
        "applicationintent",
        "multisubnetfailover",
        "connectretrycount",
    }  # mssql_python.constants._ALLOWED_CONNECTION_STRING_PARAMS (it refuses any other key)
    names = runtime()
    for way in sql_server.ORDER["sqlserver"]:
        if way in ("entra_you", "app_certificate", "managed_identity", "app_secret"):
            continue  # a token: below
        names["SqlServer"](
            "sql01.shop.local",
            "sales",
            way,
            user="sam",
            password="made-up",
            host_name_in_certificate="x",
            read_only_intent=True,
            multi_subnet_failover=True,
        )
        keys = {p.split("=", 1)[0].lower() for p in opened(server).split(";") if p}
        assert keys <= allowed, (way, keys - allowed)


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
    paused = OperationalError("General error", MSSQL_SAID["40613"])
    server.refusals = [paused, paused, paused]
    conn = names["SqlServer"]("shop.database.windows.net", "sales", "sql_login", user="sam", password="x")
    assert clock.slept == [1, 2, 4] and len(server.connections) == 1
    assert all("resuming" in n for n in conn.notes) and "resuming" in capsys.readouterr().err


def test_a_database_that_stays_paused_is_said_in_plain_words(server: FakeServer) -> None:
    clock = Clock()
    names = runtime(clock)
    server.refusals = [OperationalError("General error", MSSQL_SAID["40613"]) for _ in range(20)]
    with pytest.raises(OperationalError) as raised:  # the driver's own class: except mssql_python.Error works
        names["SqlServer"]("shop.database.windows.net", "sales", "sql_login", user="sam", password="x")
    assert (
        sum(clock.slept) >= sql_server.RESUME_SECONDS - 16
        and sum(clock.slept) <= sql_server.RESUME_SECONDS + 16
    )
    assert "serverless database that was paused" in str(raised.value)
    assert "not currently available" in str(raised.value)  # the driver's own words after


def test_other_passing_errors_are_tried_again_a_few_times_then_said(server: FakeServer) -> None:
    clock = Clock()
    names = runtime(clock)
    busy = OperationalError("General error", MSSQL_SAID["40501"])
    server.refusals = [busy, busy]
    names["SqlServer"]("shop.database.windows.net", "sales", "sql_login", user="sam", password="x")
    assert clock.slept == [1, 2]
    server.refusals = [busy] * 10
    with pytest.raises(OperationalError, match="Azure SQL is busy"):
        names["SqlServer"]("shop.database.windows.net", "sales", "sql_login", user="sam", password="x")
    assert clock.slept[2:] == [1, 2, 4, 8]  # TRIES (5) in all


def test_a_refused_login_is_never_tried_again(server: FakeServer) -> None:
    clock = Clock()
    names = runtime(clock)
    server.refusals = [Error("Invalid authorization specification", MSSQL_SAID["18456"])]
    with pytest.raises(Error, match="refused the sign-in") as raised:
        names["SqlServer"]("sql01.shop.local", "sales", "sql_login", user="sam", password="made-up")
    assert clock.slept == [] and "Login failed for user 'sam'" in str(raised.value)
    assert "made-up" not in str(raised.value)  # the password is never in the words


# ===== reading =====


def test_a_read_is_run_again_on_a_new_connection_after_a_passing_error(server: FakeServer) -> None:
    clock = Clock()
    names = runtime(clock)
    conn = names["SqlServer"]("sql01.shop.local", "sales", "windows")
    dropped = said("Communication link failure", "[Microsoft]TCP Provider: Error code 0x2746")
    server.failures = [OperationalError(dropped)]
    cursor = conn.cursor().execute("SELECT order_id FROM dbo.orders")
    assert cursor.fetchall() == [(1,)] and len(server.connections) == 2 and clock.slept == [1]
    server.failures = [OperationalError(dropped)]
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
    # (as SQL Server declares it, mssql-python's description: type, size, precision, scale), values, Arrow
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
    ("varbinary(max)", (bytes, 0, 0, 0), [b"\x00\x01"], "binary"),
    ("nvarchar(max)", (str, 0, 0, 0), ["Grüße, 東京"], "string"),
    ("xml", (str, 0, 0, 0), ["<a>1</a>"], "string"),
    ("sql_variant", (str, 8000, 8000, 0), [5], "string"),
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
    elif "uniqueidentifier" in declared or declared == "sql_variant":
        assert got == [str(v) for v in values]
    elif arrow == "binary":
        assert got == [bytes(v) for v in values]
    else:
        assert got == values


# mssql-python's own Arrow types (as it gave them against SQL Server 2022, docs/verified.md) made the
# rows' path's: an instant in UTC, a time in microseconds, plain strings and bytes.
NATIVE = [
    (pa.timestamp("us", tz="+00:00"), "timestamp[us, tz=UTC]"),
    (pa.timestamp("us"), "timestamp[us]"),
    (pa.time64("ns"), "time64[us]"),
    (pa.large_string(), "string"),
    (pa.large_binary(), "binary"),
    (pa.decimal128(19, 4), "decimal128(19, 4)"),
    (pa.uint8(), "uint8"),
]


def test_mssql_pythons_own_arrow_batches_are_read_with_the_same_types(server: FakeServer) -> None:
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    schema = pa.schema([pa.field(f"c{i}", t, False) for i, (t, _) in enumerate(NATIVE)])
    batch = pa.RecordBatch.from_pylist([], schema=schema)
    asked: list[int] = []

    def arrow_batch(self: FakeCursor, size: int) -> pa.RecordBatch:
        asked.append(size)
        return batch

    FakeCursor.arrow_batch = arrow_batch  # type: ignore[attr-defined]
    try:
        table = conn.read_arrow("SELECT * FROM dbo.kinds")
    finally:
        del FakeCursor.arrow_batch  # type: ignore[attr-defined]
    assert [str(f.type) for f in table.schema] == [want for _, want in NATIVE] and asked == [50_000]


def test_a_column_its_arrow_cannot_read_is_read_as_rows(server: FakeServer) -> None:
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    server.result = ([("id", int), ("extra", str)], [(1, "5")])

    def arrow_batch(self: FakeCursor, size: int) -> pa.RecordBatch:
        raise RuntimeError("Unsupported data type for Arrow batch fetch for column - extra, Type - -150")

    FakeCursor.arrow_batch = arrow_batch  # type: ignore[attr-defined]
    try:
        table = conn.read_arrow("SELECT id, extra FROM dbo.kinds")
    finally:
        del FakeCursor.arrow_batch  # type: ignore[attr-defined]
    assert table.to_pylist() == [{"id": 1, "extra": "5"}]


def test_reads_come_in_batches_and_a_value_that_does_not_fit_makes_the_column_text(
    server: FakeServer,
) -> None:
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    server.result = ([("id", int), ("code", int)], [(i, i if i < 5 else "X-7") for i in range(10)])
    table = conn.read_arrow("SELECT id, code FROM dbo.orders", batch_rows=3)
    assert table.num_rows == 10 and table.column("id").num_chunks == 4
    assert table.schema.field("code").type == pa.string() and table.column("code").to_pylist()[-1] == "X-7"


def test_an_interrupt_cancels_the_statement_on_the_server(server: FakeServer) -> None:
    conn = runtime()["SqlServer"]("sql01.shop.local", "sales", "windows")
    cursor = conn.cursor()
    server.block = True
    threading.Timer(0.3, _thread.interrupt_main).start()  # as the kernel's Interrupt does
    with pytest.raises(KeyboardInterrupt):
        cursor.execute("SELECT * FROM dbo.big_table")
    assert server.cancelled.is_set()  # mssql-python's statement handle: SQLCancel


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
    cursor.arraysize = 7  # the driver's own setting, set through
    assert cursor._inner.arraysize == 7


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


def test_the_code_needs_only_mssql_python_and_for_three_ways_azure_identity() -> None:
    from swissarmybench.domain.blades import needed

    for way in sql_server.ORDER["sqlserver"]:
        pips = [p.pip for p in needed(sql_server.code(way), lambda m: True)]
        identity = way in ("entra_you", "app_certificate", "entra_default")
        assert pips == (["azure-identity", "mssql-python"] if identity else ["mssql-python"]), way
        assert "pyodbc" not in sql_server.code(way) and "ODBC Driver" not in sql_server.code(way)


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
        return {{"found": "signed in", "about": {{"driver": "mssql-python",
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
    assert card["status"] == "works"
    assert card["about"][0] == "mssql-python · " + sql_server.label_of("entra_you")
    assert "GP_S_Gen5_1" in card["about"][1] and "Case-sensitive collation" in card["about"][2]
    words = sql_server.explain(MSSQL_SAID["40615"])
    assert client.post("/connections", json=_stand_in("Shop", fail=words), headers=AUTH).status_code == 200
    assert client.post("/blades/Shop/test", headers=AUTH).status_code != 200
    card = next(
        c for c in client.get("/connections/usage", headers=AUTH).json()["connections"] if c["name"] == "Shop"
    )
    assert card["status"] == "failing" and "203.0.113.7" in card["error"] and "Networking" in card["error"]


def test_a_resuming_database_is_its_own_status() -> None:
    failed = Calls({"test": 1}, 1.0, "test", False)
    assert status(failed, [], False, sql_server.explain(MSSQL_SAID["40613"])) == "resuming"
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


def test_onelakes_sql_endpoint_signs_in_with_the_same_token_code() -> None:
    from swissarmybench.domain import lakes

    assert sql_server.TOKEN_CODE in lakes.SQL_ENDPOINT


def test_the_robust_code_is_told_from_an_older_one() -> None:
    assert sql_server.is_robust(sql_server.code("windows"))
    assert not sql_server.is_robust(
        'import pyodbc\nconn = pyodbc.connect("Driver={ODBC Driver 18 for SQL Server};")'
    )
    assert sql_server.way_of(sql_server.code("app_certificate")) == "app_certificate"


# ===== an older connection, on pyodbc: Update to the new driver =====
# tests/golden/sql_server/old_<way>.txt: the code the app made before (pyodbc, an ODBC driver found), as a
# saved connection holds it, with made-up settings; new_<way>.txt: what Update to the new driver makes of it.
OLD_WAYS = ["sql_login", "windows", "entra_you", "app_secret", "managed_identity", "app_certificate"]


@pytest.mark.parametrize("way", OLD_WAYS)
def test_an_older_code_is_told_and_made_again_with_the_same_settings(way: str) -> None:
    old = (GOLDEN / f"old_{way}.txt").read_text(encoding="utf-8")
    assert sql_server.is_old(old) and sql_server.is_robust(old)
    new = sql_server.upgraded(old)
    assert new == (GOLDEN / f"new_{way}.txt").read_text(encoding="utf-8")
    assert not sql_server.is_old(new) and "pyodbc" not in new and "driver=" not in new
    assert sql_server.way_of(new) == way
    tail = old[old.index("conn = SqlServer(") :]
    for line in tail.splitlines():
        if "driver=" not in line:
            assert line in new, line  # every setting the user gave, as it was
    compile(new, f"<{way}>", "exec")


def test_the_new_code_after_an_update_is_todays_starter_code() -> None:
    old = (GOLDEN / "old_sql_login.txt").read_text(encoding="utf-8")
    new = sql_server.upgraded(old)
    start = new.index("conn = SqlServer(")
    assert (
        new[:start] == sql_server.code("sql_login")[: sql_server.code("sql_login").index("conn = SqlServer(")]
    )


def test_todays_code_and_a_connection_of_the_users_own_are_never_rewritten() -> None:
    for way in sql_server.ORDER["sqlserver"]:
        assert not sql_server.is_old(sql_server.code(way))
    own = 'import pyodbc\nconn = pyodbc.connect("Driver={ODBC Driver 18 for SQL Server};Server=x;")'
    assert not sql_server.is_old(own)
    with pytest.raises(ValueError, match="not the earlier SQL Server code"):
        sql_server.upgraded(own)


@pytest.mark.parametrize("way", sorted(sql_server.ORDER["sqlserver"]))
def test_each_ways_code_is_its_golden_file(way: str) -> None:
    """The generated connection code per sign-in, as a golden file (tests/golden/sql_server/code_<way>.txt):
    a change to it is a change to every new SQL Server connection."""
    assert sql_server.code(way) == (GOLDEN / f"code_{way}.txt").read_text(encoding="utf-8")


def test_the_card_offers_update_to_the_new_driver_and_the_agent_can_do_it(client: TestClient) -> None:
    from tests.conftest import AGENT

    old = (GOLDEN / "old_windows.txt").read_text(encoding="utf-8")
    body = {"name": "Ledger", "kind": "sql", "template": "sqlserver", "dialect": "sqlserver", "code": old}
    assert client.post("/connections", json=body, headers=AUTH).status_code == 200

    def card() -> dict[str, Any]:
        cards = client.get("/connections/usage", headers=AUTH).json()["connections"]
        return next(c for c in cards if c["name"] == "Ledger")

    before = card()
    assert before["update_driver"] is True
    assert [x["key"] for x in before["local"]] == ["windows"]  # Windows sign-in: this machine's only
    answer = client.post("/connections/Ledger/update-driver", headers=AGENT)  # the agent's, as the user's
    assert answer.status_code == 200
    assert answer.json() == {"name": "Ledger", "changed": True, "driver": "mssql-python"}
    code = client.get("/connections/Ledger", headers=AUTH).json()["code"]
    assert code == (GOLDEN / "new_windows.txt").read_text(encoding="utf-8")
    assert card()["update_driver"] is False
    again = client.post("/connections/Ledger/update-driver", headers=AUTH).json()
    assert again == {"name": "Ledger", "changed": False}


def test_update_to_the_new_driver_never_rewrites_the_users_own_code(client: TestClient) -> None:
    own = 'import pyodbc\n\nconn = pyodbc.connect("Driver={ODBC Driver 18 for SQL Server};Server=sql01;")\n'
    body = {"name": "Own", "kind": "sql", "template": "sqlserver", "dialect": "sqlserver", "code": own}
    assert client.post("/connections", json=body, headers=AUTH).status_code == 200
    answer = client.post("/connections/Own/update-driver", headers=AUTH)
    assert answer.status_code == 400 and "left as it is" in answer.text
    assert client.get("/connections/Own", headers=AUTH).json()["code"] == own
    cards = client.get("/connections/usage", headers=AUTH).json()["connections"]
    card = next(c for c in cards if c["name"] == "Own")
    assert card["update_driver"] is False and [x["key"] for x in card["local"]] == ["odbc"]
