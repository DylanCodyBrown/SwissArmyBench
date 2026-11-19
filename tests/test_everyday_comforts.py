"""Everyday comforts (feel-b, 2026-11-19): a column's values with counts for the filter's checklist,
the status bar's numbers (no Sum or Average of an id; each to its column's scale), and Copy as
Markdown.

All data is made up.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.commands import execute
from swissarmybench.domain.datasets import Column
from swissarmybench.domain.export import markdown_table
from swissarmybench.domain.grids import display_digits, id_like
from tests.conftest import AGENT, AUTH, grid_id, push

SHOPS = pa.table(
    {
        "order_id": pa.array([101, 102, 103, 104, 105, 106, 107], pa.int64()),
        "store_id": pa.array([1, 2, 2, 3, 3, 3, None], pa.int64()),
        "city": pa.array(["Oslo", "Lima", "Lima", "Pune", "Pune", "Pune", None]),
        "amount": pa.array([10.25, 20.5, 30.0, 40.75, 50.0, 60.0, 70.0]),
    }
)


# ===== id-like columns and the status bar's scale =====


@pytest.mark.parametrize(
    ("name", "kind", "expected"),
    [
        ("id", "BIGINT", True),
        ("order_id", "BIGINT", True),
        ("CustomerID", "INTEGER", True),
        ("customerId", "INTEGER", True),
        ("store_key", "INTEGER", True),
        ("ProductKey", "BIGINT", True),
        ("order_no", "INTEGER", True),
        ("invoice_number", "BIGINT", True),
        ("zip_code", "INTEGER", True),
        ("amount", "DOUBLE", False),
        ("paid", "INTEGER", False),
        ("valid", "INTEGER", False),
        ("quantity", "INTEGER", False),
        ("monkey", "INTEGER", False),
        ("rate_id", "DOUBLE", False),  # a fraction is not an identifier, whatever its name
    ],
)
def test_id_like_columns(name: str, kind: str, expected: bool) -> None:
    assert id_like(Column(name, kind)) is expected


def test_display_digits_follow_the_columns_scale() -> None:
    assert display_digits([Column("n", "INTEGER")]) == {"sum": 0, "mean": 2}
    assert display_digits([Column("p", "DECIMAL(18,3)")]) == {"sum": 3, "mean": 3}
    assert display_digits([Column("p", "DECIMAL(18,0)"), Column("q", "DECIMAL(9,1)")]) == {
        "sum": 1,
        "mean": 2,
    }
    assert display_digits([Column("x", "DOUBLE")]) == {"sum": 2, "mean": 2}
    assert display_digits([]) == {"sum": 0, "mean": 2}


def test_selection_stats_leave_ids_out_of_sum_and_average(client: TestClient) -> None:
    grid = grid_id(push(client, "shops", SHOPS))

    def stats(selection: dict[str, Any]) -> Any:
        response = client.post(f"/grids/{grid}/selection-stats", json={"selection": selection}, headers=AUTH)
        assert response.status_code == 200, response.text
        return response.json()

    ids = stats({"rows": None, "columns": ["order_id", "store_id"]})
    assert ids["count"] == 13 and ids["sum"] is None and ids["mean"] is None
    assert ids["id_like"] == ["order_id", "store_id"]
    mixed = stats({"rows": None, "columns": ["order_id", "amount"]})
    assert mixed["sum"] == pytest.approx(281.5) and mixed["mean"] == pytest.approx(281.5 / 7)
    assert mixed["id_like"] == ["order_id"] and mixed["digits"] == {"sum": 2, "mean": 2}
    assert mixed["count"] == 14  # the ids are still counted


# ===== a column's values, for the filter's checklist =====


def test_column_values_with_counts_most_common_first(client: TestClient) -> None:
    grid = grid_id(push(client, "shops", SHOPS))
    got = client.get(f"/grids/{grid}/values", params={"column": "city"}, headers=AUTH)
    assert got.status_code == 200, got.text
    body = got.json()
    # Blanks are not values to tick ("is blank" is its own condition); they are counted beside them.
    assert body["values"] == [
        {"value": "Pune", "count": 3},
        {"value": "Lima", "count": 2},
        {"value": "Oslo", "count": 1},
    ]
    assert body["blanks"] == 1 and body["distinct"] == 3 and body["more"] is False


def test_column_values_search_and_limit(client: TestClient) -> None:
    grid = grid_id(push(client, "shops", SHOPS))
    found = client.get(f"/grids/{grid}/values", params={"column": "city", "search": "l"}, headers=AUTH).json()
    assert [v["value"] for v in found["values"]] == ["Lima", "Oslo"]
    # Any case, and characters LIKE would read as wildcards are plain text.
    assert client.get(
        f"/grids/{grid}/values", params={"column": "city", "search": "PU"}, headers=AUTH
    ).json()["values"] == [{"value": "Pune", "count": 3}]
    assert (
        client.get(f"/grids/{grid}/values", params={"column": "city", "search": "%"}, headers=AUTH).json()[
            "values"
        ]
        == []
    )
    first = client.get(
        f"/grids/{grid}/values", params={"column": "store_id", "limit": 2}, headers=AUTH
    ).json()
    assert first["values"] == [{"value": 3, "count": 3}, {"value": 2, "count": 2}] and first["more"] is True


def test_column_values_follow_the_steps_entering(client: TestClient) -> None:
    grid = grid_id(push(client, "shops", SHOPS))
    put = client.post(
        f"/grids/{grid}/steps",
        json={"steps": [{"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 25}}]},
        headers=AUTH,
    )
    assert put.status_code == 200, put.text
    after = client.get(f"/grids/{grid}/values", params={"column": "city"}, headers=AUTH).json()
    assert {v["value"] for v in after["values"]} == {"Lima", "Pune"}
    # Editing the filter itself: the values entering it, every row.
    entering = client.get(f"/grids/{grid}/values", params={"column": "city", "upto": 0}, headers=AUTH).json()
    assert {v["value"] for v in entering["values"]} == {"Lima", "Oslo", "Pune"}


def test_column_values_refusals(client: TestClient) -> None:
    grid = grid_id(push(client, "shops", SHOPS))
    missing = client.get(f"/grids/{grid}/values", params={"column": "nope"}, headers=AUTH)
    assert missing.status_code in (400, 404) and "nope" in missing.text
    assert client.get(f"/grids/{grid}/values", headers=AUTH).status_code == 400
    assert client.get(f"/grids/{grid}/values", params={"column": "city"}).status_code == 401


def test_the_agent_reads_a_columns_values(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    grid = grid_id(push(client, "shops", SHOPS))

    def call(method: str, path: str, body: Any = None, params: Any = None, timeout: float = 0) -> Any:
        response = client.request(method, path, json=body, params=params, headers=AGENT)
        if response.status_code >= 400:
            raise CommandError(f"{response.status_code}: {response.text}")
        return response.json()

    monkeypatch.setattr(api, "call", call)
    out = execute("column_values", {"grid": grid, "column": "city", "search": "un"})
    assert "Pune" in out and "Lima" not in out


# ===== Copy as Markdown =====


def test_markdown_table_escapes_and_aligns() -> None:
    text = markdown_table(["city", "amount"], [["Oslo|North", "10.25"], ["", "3"]], [False, True])
    assert text.splitlines() == [
        "| city | amount |",
        "| --- | ---: |",
        "| Oslo\\|North | 10.25 |",
        "|  | 3 |",
    ]
    # A line break inside a cell stays inside it.
    assert markdown_table(["note"], [["two\nlines"]], [False]).splitlines()[2] == "| two<br>lines |"


def test_selection_copies_as_markdown(client: TestClient) -> None:
    grid = grid_id(push(client, "shops", SHOPS))
    got = client.get(
        f"/grids/{grid}/export",
        params={
            "scope": "selection",
            "selection": '{"rows": [[0, 1]], "columns": ["city", "amount"]}',
            "format": "md",
            "provenance": "0",
        },
        headers=AUTH,
    )
    assert got.status_code == 200, got.text
    assert got.content.decode().splitlines() == [
        "| city | amount |",
        "| --- | ---: |",
        "| Oslo | 10.25 |",
        "| Lima | 20.5 |",
    ]
