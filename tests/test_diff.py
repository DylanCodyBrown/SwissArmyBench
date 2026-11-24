"""Compare's diff mode on a made-up price list and its later copy: planted changes (a price, a region
with stray spaces, a cent of rounding), a product on each side only, and the options that decide what
counts as a change."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import diff
from swissarmybench.domain.datasets import Column
from tests.conftest import AGENT, AUTH, grid_id, make_client, push


def lists() -> tuple[pa.Table, pa.Table]:
    before = pa.table(
        {
            "sku": ["A1", "A2", "A3", "A4", "A5"],
            "region": ["North", "South", "East", "West", "North"],
            "price": [10.0, 20.0, 30.0, 40.0, 50.0],
            "note": ["", None, "ok", "ok", "ok"],
        }
    )
    after = pa.table(
        {
            "SKU": ["A1", "A2", "A3", "A4", "A6"],
            "Region": ["North", "South ", "east", "West", "South"],
            "Price": [10.0, 20.01, 33.0, 40.0, 60.0],
            "note": [None, None, "ok", "ok", "new"],
        }
    )
    return before, after


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        yield test_client


@pytest.fixture
def compare(client: TestClient) -> dict[str, Any]:
    before, after = lists()
    left, right = grid_id(push(client, "prices_before", before)), grid_id(push(client, "prices_after", after))
    made = client.post(
        "/compares",
        json={"left": left, "right": right, "keys": [["sku", "SKU"]], "mode": "diff"},
        headers=AGENT,
    )
    assert made.status_code == 200, made.text
    return dict(made.json())


def rows(client: TestClient, cmp: dict[str, Any], side: str) -> Any:
    return client.get(f"/compares/{cmp['compare']}/rows?side={side}&start=0&end=50", headers=AUTH).json()


def change(client: TestClient, cmp: dict[str, Any], **options: Any) -> dict[str, Any]:
    answer = client.patch(f"/compares/{cmp['compare']}", json={"diff": options}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    return dict(answer.json())


def test_only_the_rows_that_differ_with_a_count_per_column(
    client: TestClient, compare: dict[str, Any]
) -> None:
    differ = compare["differ"]
    # A2: price by a cent (and "South " trims to South); A3: price and region's case; A5 and A6 one side each.
    assert differ["matched"] == 4 and differ["differ"] == 2
    assert differ["left_only"] == 1 and differ["right_only"] == 1
    assert differ["columns"] == {"price": 2, "region": 1}  # an empty note is a blank, as None is
    assert differ["compared"] == ["region", "price", "note"]  # by name ignoring case, the key left out
    left = rows(client, compare, "left")
    assert [r[0] for r in left["rows"]] == ["A2", "A3", "A5", None]  # A6 is only on the right
    assert left["placeholders"] == [3]
    assert sorted(map(tuple, left["diffs"])) == [(0, 2), (1, 1), (1, 2)]


def test_the_options_decide_what_counts_as_a_change(client: TestClient, compare: dict[str, Any]) -> None:
    near = change(client, compare, tolerance=0.05)
    assert near["differ"]["columns"] == {"price": 1, "region": 1} and near["differ"]["differ"] == 1
    percent = change(client, compare, tolerance=10, percent=True, ignore_case=True)
    assert percent["differ"]["differ"] == 0  # 33 is 10% of 30; east is East
    strict = change(client, compare, trim=False)
    assert strict["differ"]["columns"]["region"] == 2  # "South " no longer trims to South
    skipped = change(client, compare, skip=["price"])
    assert "price" not in skipped["differ"]["compared"] and skipped["differ"]["differ"] == 1
    focused = change(client, compare, column="region")
    assert focused["row_count"] == 1 and rows(client, compare, "right")["rows"][0][0] == "A3"
    bad = client.patch(f"/compares/{compare['compare']}", json={"diff": {"column": "sku"}}, headers=AUTH)
    assert bad.status_code == 400 and "not a column both tables have" in bad.text
    assert (
        client.patch(
            f"/compares/{compare['compare']}", json={"diff": {"tolerance": -1}}, headers=AUTH
        ).status_code
        == 400
    )


def test_diff_mode_follows_each_grids_steps(client: TestClient, compare: dict[str, Any]) -> None:
    step = {"kind": "filter", "params": {"column": "sku", "op": "ne", "value": "A3"}}
    assert (
        client.post(
            f"/grids/{compare['left']}/step-ops", json={"op": "add", "step": step}, headers=AUTH
        ).status_code
        == 200
    )
    now = client.get(f"/compares/{compare['compare']}", headers=AUTH).json()
    # A3 is now only on the right, so it counts there and no longer as a change.
    assert now["differ"]["right_only"] == 2 and now["differ"]["differ"] == 1


def test_the_python_and_sql_rules_agree_on_edge_values() -> None:
    options = diff.DiffOptions()
    number = diff.Pair(0, 0, Column("x", "DOUBLE"), Column("x", "DOUBLE"), True)
    assert diff.same(0.1 + 0.2, 0.3, True, options) and not diff.same(1.0, None, True, options)
    assert diff.same(float("nan"), float("nan"), True, options) and diff.same(None, None, True, options)
    assert diff.same("", None, False, options) and diff.same(" a ", "a", False, options)
    assert not diff.same("A", "a", False, options) and diff.same(
        "A", "a", False, diff.DiffOptions(ignore_case=True)
    )
    assert "isnan" in diff.differs_sql(number, options)


# ===== only the differing columns, and the compares that are running =====


def test_diff_mode_names_the_columns_to_show_the_keys_and_what_differs(
    client: TestClient, compare: dict[str, Any]
) -> None:
    # On by default: each side's key, then the columns that differ, in that grid's own order and names.
    assert compare["diff"]["only_differing"] is True
    assert compare["differ"]["shown"] == {
        "left": ["sku", "region", "price"],
        "right": ["SKU", "Region", "Price"],
    }
    assert compare["differ"]["first"] == {"left": "region", "right": "Region"}
    # Looking at one column's changes does not change which columns differ in all.
    focused = change(client, compare, column="price")
    assert focused["differ"]["shown"]["left"] == ["sku", "region", "price"]
    # Nothing differs within the tolerance: the keys alone, and no first column.
    calm = change(client, compare, column=None, tolerance=10, percent=True, ignore_case=True)
    assert calm["differ"]["shown"] == {"left": ["sku"], "right": ["SKU"]} and calm["differ"]["first"] is None
    # Switched off, the answer says so and still names the columns (the page shows every column).
    off = change(client, compare, only_differing=False, tolerance=0, percent=False, ignore_case=False)
    assert off["diff"]["only_differing"] is False
    assert off["differ"]["first"] == {"left": "region", "right": "Region"}
    assert (
        client.patch(
            f"/compares/{compare['compare']}", json={"diff": {"only_differing": "yes"}}, headers=AUTH
        ).status_code
        == 400
    )


def test_showing_every_column_again_does_not_join_the_sides_again(
    client: TestClient, compare: dict[str, Any]
) -> None:
    app: Any = client.app
    held = app.state.ctx.compares.get(compare["compare"])
    before = held.signature
    change(client, compare, only_differing=False)
    assert held.signature == before  # the mapping table was kept as it was
    change(client, compare, tolerance=0.05)
    assert held.signature != before  # what counts as a change does rebuild it


def test_the_running_compares_are_listed_until_stopped_or_a_grid_closes(
    client: TestClient, compare: dict[str, Any]
) -> None:
    listed = client.get("/compares", headers=AGENT).json()["compares"]
    assert [c["compare"] for c in listed] == [compare["compare"]]
    assert listed[0]["mode"] == "diff" and listed[0]["left"] == compare["left"]
    assert listed[0]["left_dataset"] == "prices_before" and listed[0]["right_dataset"] == "prices_after"
    # A compare whose grid has closed is gone: there is nothing left to line up.
    assert client.delete(f"/grids/{compare['right']}", headers=AUTH).status_code == 200
    assert client.get("/compares", headers=AUTH).json()["compares"] == []
    assert client.get(f"/compares/{compare['compare']}", headers=AUTH).status_code == 404
