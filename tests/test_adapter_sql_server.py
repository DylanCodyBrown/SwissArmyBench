"""The adapter's SQL Server and Azure SQL writes (phase 5, Plans/adapter.plan.md: "SQL Server and Trino writes
move into adapter.py too"): the project scaffold's adapter.py, proven against tests/sqlserver_standin.py at
mssql-python's seam (the adapter's T-SQL run in DuckDB, so the rows that land are read back): the rows staged
in the target's own types, one MERGE WITH (HOLDLOCK), MERGE and TRUNCATE refused and done another way, Azure's
passing errors running the whole write again on a fresh connection, the dry run's staged keys rolled back.
tests/test_sql_server_real.py runs the same write against a real SQL Server when SWISSARMYBENCH_SQLSERVER_TEST
names one. Made-up rows only."""

from __future__ import annotations

import decimal
import sys
from collections.abc import Iterator
from typing import Any

import duckdb
import pyarrow as pa
import pytest

from swissarmybench.adapters import adapter
from tests import sqlserver_standin as standin
from tests.sqlserver_standin import Column

# ===== SQL Server =====

ORDERS = [
    Column("order_id", "int", key=True),
    Column("region", "nvarchar(40)"),
    Column("code", "varchar(10)"),
    Column("amount", "decimal(12,2)"),
]


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[standin.Server]:
    made = standin.Server()
    made.table("dbo.orders", ORDERS, [(1, "North", "N1", decimal.Decimal("10.00")), (9, "North", "N9", 90)])
    monkeypatch.setitem(sys.modules, "mssql_python", made.module())
    monkeypatch.delitem(sys.modules, "pyodbc", raising=False)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    yield made


def source(server: standin.Server, **given: Any) -> adapter.Sql:
    return adapter.Sql(server.connect(), "sqlserver", "Warehouse", **given)


ROWS = pa.table(
    {
        "order_id": pa.array([1, 2, 3], pa.int64()),
        "region": ["Nörth", "South", None],
        "code": ["A1", "B2", "C3"],
        "amount": pa.array([1.5, float("nan"), 3.25]),
    }
)


def test_sql_server_merge_stages_the_rows_in_the_targets_types_then_merges_with_holdlock(
    server: standin.Server,
) -> None:
    done = adapter.write(source(server), "dbo.orders", ROWS, ["order_id"], "merge")
    assert (done.inserted, done.updated, done.notes) == (2, 1, ())
    assert server.rows("dbo.orders") == [
        (1, "Nörth", "A1", decimal.Decimal("1.50")),  # Unicode kept, the decimal at its scale
        (2, "South", "B2", None),  # NaN is NULL
        (3, None, "C3", decimal.Decimal("3.25")),
        (9, "North", "N9", decimal.Decimal("90.00")),
    ]
    sent = server.statements
    assert (
        "CREATE TABLE #sab_stage ([order_id] int NULL, [region] nvarchar(40) COLLATE DATABASE_DEFAULT NULL, "
        "[code] varchar(10) COLLATE DATABASE_DEFAULT NULL, [amount] decimal(12,2) NULL)"
    ) in sent
    merge = next(s for s in sent if s.startswith("MERGE"))
    assert merge.startswith(
        "MERGE INTO [dbo].[orders] WITH (HOLDLOCK) AS t\n"
        "USING #sab_stage AS s ON t.[order_id] = s.[order_id]\n"
    )
    assert server.sizes[0] == [(4, 10, 0), (-9, 40, 0), (12, 10, 0), (3, 12, 2)]  # every parameter typed
    assert server.sizes[1] == []  # then cleared: mssql-python keeps them for the next statements


def test_sql_server_insert_update_delete_and_truncate_give_the_right_rows(server: standin.Server) -> None:
    db = source(server)
    more = pa.table({"order_id": [5], "region": ["West"], "code": ["W5"], "amount": [5.0]})
    assert adapter.write(db, "dbo.orders", more, mode="insert").inserted == 1
    changed = pa.table({"order_id": [5, 9], "region": ["East", "East"]})
    assert adapter.write(db, "dbo.orders", changed, ["order_id"], "update").updated == 2
    assert [r[1] for r in server.rows("dbo.orders")] == ["North", "East", "East"]
    gone = pa.table({"order_id": [9, 9, 404]})
    assert adapter.write(db, "dbo.orders", gone, ["order_id"], "delete").deleted == 1
    assert (
        "DELETE t FROM [dbo].[orders] AS t JOIN #sab_keys AS s ON t.[order_id] = s.[order_id]"
        in server.statements
    )
    assert [r[0] for r in server.rows("dbo.orders")] == [1, 5]
    fresh = pa.table({"order_id": [7], "region": ["South"], "code": ["S7"], "amount": [7.0]})
    done = adapter.write(db, "dbo.orders", fresh, mode="truncate")
    assert (done.deleted, done.inserted) == (2, 1) and "TRUNCATE TABLE [dbo].[orders]" in server.statements
    assert server.rows("dbo.orders") == [(7, "South", "S7", decimal.Decimal("7.00"))]
    assert adapter.write(db, "dbo.orders", None, mode="truncate").deleted == 1
    assert server.rows("dbo.orders") == []


def test_sql_server_dry_run_stages_the_keys_counts_by_one_join_and_keeps_nothing(
    server: standin.Server,
) -> None:
    db = source(server)
    assert adapter.planned(db, "dbo.orders", ROWS, ["order_id"], "merge") == adapter.Counts(
        inserted=2, updated=1
    )
    assert adapter.planned(db, "dbo.orders", ROWS, ["order_id"], "delete") == adapter.Counts(deleted=1)
    assert adapter.planned(db, "dbo.orders", ROWS, (), "truncate") == adapter.Counts(inserted=3, deleted=2)
    assert "SELECT COUNT(*) FROM #sab_keys AS s JOIN [dbo].[orders] AS t ON t.[order_id] = s.[order_id]" in (
        server.statements
    )
    assert not any(s.startswith(("MERGE", "INSERT INTO [dbo]", "DELETE")) for s in server.statements)
    assert len(server.rows("dbo.orders")) == 2  # nothing written
    with pytest.raises(duckdb.CatalogException):  # the staged keys rolled back with the dry run
        db.connection.db.execute("SELECT * FROM sab_keys")


def test_sql_server_runs_the_whole_write_again_on_a_passing_error_on_a_fresh_connection(
    server: standin.Server,
) -> None:
    busy = standin.Error(
        "Driver Error: General error; DDBC Error: [Microsoft][SQL Server]Database 'shop' on server "
        "'made-up' is "
        "not currently available. Please retry the connection later."
    )
    link = standin.Error(
        "Driver Error: Communication link failure; DDBC Error: [Microsoft]TCP Provider: Error code 0x2746"
    )
    server.failures = [("INSERT INTO #sab_stage", link), ("MERGE", busy)]
    db = source(server, reopen=server.connect)
    done = adapter.write(db, "dbo.orders", ROWS, ["order_id"], "merge")
    assert (done.inserted, done.updated) == (2, 1)
    assert [n[:22] for n in done.notes] == ["Try 1 met a passing er", "Try 2 met a passing er"]
    assert len(server.connections) == 3 and server.connections[0].closed and server.connections[1].closed
    assert len(server.rows("dbo.orders")) == 4  # once: the failed tries rolled back whole
    assert sum(s.startswith("CREATE TABLE #sab_stage") for s in server.statements) == 3


def test_a_refusal_that_does_not_pass_rolls_every_row_back_and_names_its_batch(
    server: standin.Server,
) -> None:
    refused = standin.Error(
        "Driver Error: Integrity constraint violation; DDBC Error: Violation of PRIMARY KEY"
    )
    server.failures = [("INSERT INTO [dbo].[orders]", refused)]
    with pytest.raises(standin.Error) as raised:
        adapter.write(source(server, reopen=server.connect), "dbo.orders", ROWS, mode="insert")
    assert adapter.batch_of(raised.value) == adapter.Batch(1, 0, 3)
    assert len(server.connections) == 1 and len(server.rows("dbo.orders")) == 2  # not tried again


def test_sql_server_does_merge_and_truncate_another_way_where_they_are_refused(
    server: standin.Server,
) -> None:
    server.failures = [
        ("MERGE", standin.Error("MERGE is not supported in this version of SQL Server.")),
        ("TRUNCATE", standin.Error("Cannot truncate table because it is being referenced by a FOREIGN KEY")),
    ]
    db = source(server)
    merged = adapter.write(db, "dbo.orders", ROWS, ["order_id"], "merge")
    assert (merged.inserted, merged.updated) == (2, 1)
    assert merged.notes == ("MERGE was refused here: UPDATE, then INSERT, in the same transaction.",)
    assert len(server.rows("dbo.orders")) == 4
    cleared = adapter.write(db, "dbo.orders", ROWS.slice(0, 1), mode="truncate")
    assert (cleared.deleted, cleared.inserted) == (4, 1)
    assert cleared.notes == (
        "TRUNCATE was refused (a foreign key points at the table): DELETE FROM instead.",
    )
    assert [r[0] for r in server.rows("dbo.orders")] == [1]


def test_identity_and_computed_columns_are_refused_unless_asked_and_said_in_the_statements(
    server: standin.Server,
) -> None:
    server.table("dbo.events", [Column("row_no", "int", identity=True), Column("total", "int", computed=True),
                                Column("note", "nvarchar(20)")])  # fmt: skip
    numbered = pa.table({"row_no": [7], "note": ["made-up"]})
    with pytest.raises(
        adapter.AdapterError, match=r"row_no is dbo\.events's identity column: SQL Server numbers it"
    ):
        adapter.write(source(server), "dbo.events", numbered)
    assert adapter.write(source(server, identity_insert=True), "dbo.events", numbered).inserted == 1
    on = server.statements.index("SET IDENTITY_INSERT [dbo].[events] ON")
    assert server.statements[on + 1].startswith("INSERT INTO [dbo].[events] ([row_no], [note])")
    assert server.statements[on + 2] == "SET IDENTITY_INSERT [dbo].[events] OFF"
    assert server.rows("dbo.events") == [(7, None, "made-up")]
    with pytest.raises(adapter.AdapterError, match=r"total is computed by dbo\.events"):
        adapter.write(source(server), "dbo.events", pa.table({"total": [1]}))
    said = adapter.statements(source(server), "dbo.orders", ["order_id", "region"], ["order_id"], "merge")
    assert said[0].startswith("CREATE TABLE #sab_stage (the target's own types)")
    assert said[1].endswith(
        "WHEN NOT MATCHED BY TARGET THEN INSERT ([order_id], [region]) VALUES (s.[order_id], s.[region]);"
    )


def test_a_sql_server_connection_writes_through_the_adapter_as_its_code_makes_it(
    server: standin.Server,
) -> None:
    """The SQL Server connection's own object (domain/sql_server.py: a SqlServer over mssql-python) as the
    adapter's source, as sab.write and an export's connections.py use it."""
    from swissarmybench.domain import sql_server

    names: dict[str, Any] = {"__name__": "__blade__"}
    exec(compile(sql_server._IMPORTS + sql_server.RUNTIME, "<sqlserver>", "exec"), names)  # noqa: S102
    conn = names["SqlServer"]("made-up.database.windows.net", "shop", sign_in="sql", user="u", password="p")
    found = adapter.source_from(conn, name="Warehouse")
    assert isinstance(found, adapter.Sql) and found.dialect.name == "sqlserver"
    done = adapter.write(found, "dbo.orders", ROWS, ["order_id"], "merge")
    assert (done.inserted, done.updated) == (2, 1) and len(server.rows("dbo.orders")) == 4
