"""SQL Server's connection code and its Write starter against a real SQL Server, through Microsoft's own
mssql-python (no ODBC driver installed). Skipped unless SWISSARMYBENCH_SQLSERVER_TEST names one, as
`host,port;user;password` (a throwaway container: `docker run -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=...
-p 127.0.0.1:14333:1433 mcr.microsoft.com/mssql/server:2022-latest`), and mssql-python is in this Python.
Made-up tables and rows only, in a database of its own (sab_made_up), dropped at the end."""

from __future__ import annotations

import _thread
import datetime as dt
import decimal
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import sql_server

GIVEN = os.environ.get("SWISSARMYBENCH_SQLSERVER_TEST", "")
pytest.importorskip("mssql_python")
pytestmark = pytest.mark.skipif(not GIVEN, reason="no SQL Server named (SWISSARMYBENCH_SQLSERVER_TEST)")
DATABASE = "sab_made_up"


def runtime() -> dict[str, Any]:
    names: dict[str, Any] = {"__name__": "__blade__"}
    exec(compile(sql_server._IMPORTS + sql_server.RUNTIME, "<sqlserver>", "exec"), names)  # noqa: S102
    return names


def settings(**more: Any) -> dict[str, Any]:
    address, user, password = GIVEN.split(";", 2)
    _, _, port = address.partition(",")
    found = {"user": user, "password": password, "port": int(port or 1433)}
    found |= {"trust_server_certificate": True, "login_timeout": 10}
    return found | more


@pytest.fixture(scope="module")
def names() -> Iterator[dict[str, Any]]:
    made = runtime()
    host = GIVEN.split(";")[0].split(",")[0]
    admin = made["SqlServer"](host, "master", "sql_login", **settings())
    admin.raw.autocommit = True
    cursor = admin.cursor()
    cursor.execute(f"IF DB_ID('{DATABASE}') IS NOT NULL DROP DATABASE {DATABASE}")
    cursor.execute(f"CREATE DATABASE {DATABASE}")
    made["host"] = host
    yield made
    cursor = admin.cursor()
    cursor.execute(f"ALTER DATABASE {DATABASE} SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
    cursor.execute(f"DROP DATABASE {DATABASE}")
    admin.close()


def connect(names: dict[str, Any], **more: Any) -> Any:
    return names["SqlServer"](names["host"], DATABASE, "sql_login", **settings(**more))


def test_it_signs_in_and_says_the_server(names: dict[str, Any]) -> None:
    about = connect(names, read_only_intent=True).about()
    assert about["driver"] == "mssql-python" and about["version"].startswith("Microsoft SQL Server")
    assert "collation" in about


def test_each_type_reads_into_arrow_exactly(names: dict[str, Any]) -> None:
    conn = connect(names)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE dbo.kinds (id int PRIMARY KEY, small tinyint, amount decimal(12,2), cash money, "
        "at datetime2(7), at_zone datetimeoffset(7), clock time(7), ref uniqueidentifier, flag bit, "
        "raw varbinary(max), words nvarchar(max), doc xml, spot geography, extra sql_variant)"
    )
    cursor.execute(
        "INSERT INTO dbo.kinds VALUES (1, 255, 1234567890.12, 12.3456, '2026-01-31 09:30:00.1234567', "
        "'2026-01-31 09:30:00 +02:00', '13:14:15.123456', '6F9619FF-8B86-D011-B42D-00C04FC964FF', 1, 0x0001, "
        "N'Grüße, 東京', '<a>1</a>', geography::Point(47.6, -122.3, 4326), CAST(5 AS sql_variant))"
    )
    conn.commit()
    table = conn.read_arrow("SELECT * FROM [dbo].[kinds]")
    types = {f.name: str(f.type) for f in table.schema}
    assert types == {
        "id": "int32",
        "small": "uint8",
        "amount": "decimal128(12, 2)",
        "cash": "decimal128(19, 4)",
        "at": "timestamp[us]",
        "at_zone": "timestamp[us, tz=UTC]",
        "clock": "time64[us]",
        "ref": "string",
        "flag": "bool",
        "raw": "binary",
        "words": "string",
        "doc": "string",
        "spot": "string",
        "extra": "string",
    }
    row = table.to_pylist()[0]
    assert row["amount"] == decimal.Decimal("1234567890.12") and row["small"] == 255
    assert row["at_zone"] == dt.datetime(2026, 1, 31, 7, 30, tzinfo=dt.UTC)
    assert (
        row["spot"].startswith("POINT (-122.3 47.6") and row["extra"] == "5" and row["words"] == "Grüße, 東京"
    )
    # Any other query: mssql-python's Arrow cannot read sql_variant, so its rows are read instead.
    other = conn.read_arrow("SELECT id, extra FROM dbo.kinds WHERE id = 1")
    assert other.to_pylist() == [{"id": 1, "extra": "5"}]


def test_its_refusals_are_said_in_plain_words(names: dict[str, Any]) -> None:
    with pytest.raises(Exception, match="refused the sign-in") as wrong:
        connect(names, password="not-the-made-up-password")
    assert "not-the-made-up-password" not in str(wrong.value)
    with pytest.raises(Exception, match="certificate is not one this computer trusts"):
        connect(names, trust_server_certificate=False)
    with pytest.raises(Exception, match="no table or view by that name"):
        connect(names).cursor().execute("SELECT * FROM dbo.no_such_table")


def test_an_interrupt_cancels_a_running_statement_on_the_server(names: dict[str, Any]) -> None:
    conn = connect(names)
    cursor = conn.cursor()
    threading.Timer(1.0, _thread.interrupt_main).start()
    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        cursor.execute("WAITFOR DELAY '00:00:30'")
    assert time.monotonic() - started < 10
    again = conn.cursor()
    again.execute("SELECT 1")
    assert again.fetchall()[0][0] == 1


def test_the_write_starter_upserts_through_mssql_python(names: dict[str, Any]) -> None:
    pd = pytest.importorskip("pandas")
    conn = connect(names)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE dbo.orders (order_id int PRIMARY KEY, region nvarchar(40), code varchar(10), "
        "amount decimal(12,2), placed datetime2(7), ref uniqueidentifier, at_zone datetimeoffset)"
    )
    cursor.execute("INSERT INTO dbo.orders VALUES (1, N'North', 'A1', 10.50, NULL, NULL, NULL)")
    conn.commit()
    starter = (
        Path(__file__).parents[1] / "src" / "swissarmybench" / "starters" / "write_to_sql_server.blade.py"
    )
    space: dict[str, Any] = {"__name__": "__starter__"}
    exec(compile(starter.read_text(encoding="utf-8"), str(starter), "exec"), space)  # noqa: S102
    write = space["write_sql_server"]
    zone = dt.timezone(dt.timedelta(hours=2))
    rows = pd.DataFrame(
        {
            "order_id": [1, 2, 3],
            "region": ["Nörth", "South", None],
            "code": ["A1", "B2", "C3"],
            "amount": [11.25, float("nan"), 3.5],
            "placed": pd.to_datetime(
                pd.Series(["2026-01-02 03:04:05.123456", None, "2026-02-03 00:00:00.000000"])
            ),
            "ref": ["6F9619FF-8B86-D011-B42D-00C04FC964FF", None, None],
            "at_zone": [dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=zone), None, None],
        }
    )
    planned = write(conn, "dbo.orders", rows, mode="upsert", keys=["order_id"], dry_run=True)
    assert "update 1 row" in str(planned) and "insert 2 rows" in str(planned)
    done = write(conn, "dbo.orders", rows, mode="upsert", keys=["order_id"], dry_run=False)
    assert done.counts == {"updated": 1, "inserted": 2}
    check = connect(names).read_arrow("SELECT * FROM dbo.orders ORDER BY order_id").to_pylist()
    assert [r["region"] for r in check] == ["Nörth", "South", None]
    assert check[0]["amount"] == decimal.Decimal("11.25") and check[1]["amount"] is None
    assert check[0]["placed"] == dt.datetime(2026, 1, 2, 3, 4, 5, 123456)
    assert check[0]["at_zone"] == dt.datetime(2026, 1, 2, 1, 4, 5, tzinfo=dt.UTC)
    assert check[0]["ref"].upper() == "6F9619FF-8B86-D011-B42D-00C04FC964FF"


def test_dataverses_cursor_reads_tds_through_python_tds(names: dict[str, Any]) -> None:
    """Dataverse's SQL cursor (its marks, its plain-word refusals) on python-tds against this SQL Server's
    TDS: signed in with a SQL login here, as Dataverse's endpoint takes only an Entra token (not reached)."""
    pytds = pytest.importorskip("pytds")
    from swissarmybench.domain import dataverse

    code = dataverse.MANAGED
    space: dict[str, Any] = {}
    start = code.index("def marks(")
    exec(code[start : code.index("\n\n\n", start)], space)  # noqa: S102
    words = code.index("def sql_words(")
    head = "import re\nclass DataverseError(RuntimeError):\n    pass\nclass Dataverse:\n    TDS_OFF = 'off'\n"
    exec(head + code[words : code.index("class Dataverse:", words)], space)  # noqa: S102
    _, user, password = GIVEN.split(";", 2)
    port = int(GIVEN.split(";")[0].partition(",")[2] or 1433)
    raw = pytds.connect(server=names["host"], port=port, user=user, password=password, autocommit=True)
    cursor = space["SqlCursor"](raw.cursor())
    cursor.execute("SELECT name FROM sys.databases WHERE name = ? AND database_id < ?", "master", 10)
    assert cursor.description[0][0] == "name" and cursor.fetchall() == [("master",)]
    cursor.execute("SELECT TOP 1 100 % 7 AS m, '?' AS q FROM sys.databases")  # no parameters: as it is
    assert cursor.fetchall() == [(2, "?")]
    with pytest.raises(RuntimeError, match="Dataverse's SQL endpoint refused: .*Invalid object name"):
        cursor.execute("SELECT * FROM dbo.no_such_table")
    raw.close()
