"""Unnest this column: a LIST or STRUCT column (an API's answer read by DuckDB) opened up by a SQL step."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow as pa
import pytest

from swissarmybench.domain import steps
from tests.conftest import AUTH, grid_id, make_client, push


def test_the_kinds_and_a_structs_fields() -> None:
    assert steps.unnest_kind("INTEGER[]") == "list"
    assert steps.unnest_kind("STRUCT(a INTEGER)[]") == "list"
    assert steps.unnest_kind("VARCHAR[3]") == "list"
    assert steps.unnest_kind('STRUCT(id INTEGER, "a b" VARCHAR)') == "struct"
    assert steps.unnest_kind("VARCHAR") is None
    assert steps.struct_fields('STRUCT(id INTEGER, "a ""b""" VARCHAR, c STRUCT(x INTEGER, y DOUBLE))') == [
        "id",
        'a "b"',
        "c",
    ]


def made_up() -> duckdb.DuckDBPyConnection:
    db = duckdb.connect()
    db.execute(
        "CREATE TABLE grid AS SELECT 1 AS id, ['north', 'south'] AS regions, "
        "{'id': 7, 'name': 'Acme'} AS client UNION ALL SELECT 2, [], {'id': 8, 'name': 'Globex'} "
        "UNION ALL SELECT 3, NULL, NULL"
    )
    return db


def test_a_list_gives_a_row_per_item_and_keeps_an_empty_one() -> None:
    sql = steps.unnest_sql("regions", "VARCHAR[]")
    rows = made_up().execute(sql + " ORDER BY id, regions").fetchall()
    assert [(r[0], r[1]) for r in rows] == [(1, "north"), (1, "south"), (2, None), (3, None)]


def test_a_struct_gives_its_fields_as_columns_that_never_clash() -> None:
    db = made_up()
    type_text = db.execute("SELECT typeof(client) FROM grid LIMIT 1").fetchone()[0]  # type: ignore[index]
    sql = steps.unnest_sql("client", type_text, ["id", "regions", "client", "client.id"])
    got = db.execute(sql + " ORDER BY id")
    assert [d[0] for d in got.description] == ["id", "regions", "client.id (2)", "client.name"]
    assert [r[2:] for r in got.fetchall()] == [(7, "Acme"), (8, "Globex"), (None, None)]


def test_another_column_is_refused_in_words() -> None:
    with pytest.raises(steps.StepError, match="only a list or a struct column"):
        steps.unnest_sql("amount", "DOUBLE")


# ===== on the server: the Column menu's Unnest this column, the agent's column_unnest =====


def test_unnest_this_column_adds_a_sql_step_the_user_can_read(tmp_path: Path) -> None:
    table = pa.table(
        {
            "order_id": [1, 2],
            "lines": [["widget", "gadget"], []],
            "client": [{"id": 7, "name": "Acme"}, {"id": 8, "name": "Globex"}],
        }
    )
    with make_client(tmp_path) as client:
        grid = grid_id(push(client, "orders_answer", table))
        done = client.post(f"/grids/{grid}/unnest", json={"column": "lines"}, headers=AUTH)
        assert done.status_code == 200, done.text
        step = done.json()["steps"][-1]
        assert step["kind"] == "sql" and "unnest(" in step["params"]["sql"]
        assert step["description"] == "Unnest lines (SQL)"
        done = client.post(f"/grids/{grid}/unnest", json={"column": "client"}, headers=AUTH)
        assert [c["name"] for c in done.json()["columns"]] == [
            "order_id",
            "lines",
            "client.id",
            "client.name",
        ]
        rows = client.get(f"/grids/{grid}/rows?start=0&end=10", headers=AUTH).json()["rows"]
        assert [r[:4] for r in rows] == [
            [1, "widget", 7, "Acme"],
            [1, "gadget", 7, "Acme"],
            [2, None, 8, "Globex"],
        ]
        refused = client.post(f"/grids/{grid}/unnest", json={"column": "order_id"}, headers=AUTH)
        assert refused.status_code == 400 and "only a list or a struct" in refused.text
