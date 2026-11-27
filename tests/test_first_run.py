"""A first run that feels better (the owner, 2026-11-19): the made-up sample store every empty page offers
(Try it with sample data), and the rail's names, on until the user turns them off and kept on this computer.
The agent does both too."""

from __future__ import annotations

from pathlib import Path

import pytest

from swissarmybench.domain import navigation, sample_data
from tests.conftest import AGENT, AUTH, make_client
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command


def test_the_sample_store_is_made_up_joins_and_is_the_same_every_time() -> None:
    tables = {t.name: t for t in sample_data.store()}
    assert list(tables) == ["customers", "products", "orders"]
    assert sample_data.store() == sample_data.store()
    customers = {row[0] for row in tables["customers"].rows}
    products = {row[0] for row in tables["products"].rows}
    orders = tables["orders"]
    assert len(orders.rows) == sample_data.ORDERS and len(customers) == sample_data.CUSTOMERS
    at = orders.columns.index
    # Every order names a customer and a product that are there: the ERD's finder has joins to find.
    assert {row[at("customer_id")] for row in orders.rows} <= customers
    assert {row[at("product_id")] for row in orders.rows} <= products
    assert all(len(row) == len(t.columns) for t in tables.values() for row in t.rows)
    assert orders.dates == ("order_date",)
    assert all(str(row[at("order_date")]).startswith("2026-") for row in orders.rows)


def test_the_sample_opens_as_tables_under_free_names(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        first = client.post("/samples/store", headers=AUTH)
        assert first.status_code == 200, first.text
        assert [t["name"] for t in first.json()["tables"]] == ["customers", "products", "orders"]
        again = client.post("/samples/store", headers=AGENT).json()["tables"]
        assert [t["name"] for t in again] == ["customers_2", "products_2", "orders_2"]
        names = {d["name"] for d in client.get("/datasets", headers=AUTH).json()["datasets"]}
        assert {"customers", "orders_2"} <= names
        grid = first.json()["tables"][2]["grid"]
        count = client.get(f"/grids/{grid}/count", headers=AUTH)
        assert count.status_code == 200, count.text
        assert sample_data.ORDERS in count.json().values()


def test_the_samples_tables_say_sample_data_and_a_paste_says_pasted(tmp_path: Path) -> None:
    """Home said "from Pasted" for the tables Try it with sample data made: they say Sample data, in the
    project's summary and after the project is saved and opened again; a real paste keeps Pasted."""
    with make_client(tmp_path) as client:
        made = client.post("/project/new", json={"name": "made_up_samples"}, headers=AUTH)
        assert made.status_code == 200, made.text
        folder = made.json()["project"]["folder"]
        client.post("/samples/store", headers=AUTH)
        pasted = client.post(
            "/datasets/made_up_paste/paste", content=b"region\tunits\nNorth\t3\n", headers=AUTH
        )
        assert pasted.status_code == 200, pasted.text

        def sources() -> dict[str, str]:
            tables = client.get("/project/summary", headers=AUTH).json()["tables"]
            return {t["name"]: t["from"] for t in tables}

        assert sources() == {
            "customers": "Sample data",
            "products": "Sample data",
            "orders": "Sample data",
            "made_up_paste": "Pasted",
        }
        keep = dict.fromkeys(("customers", "products", "orders", "made_up_paste"), True)
        saved = client.post("/project/save", json={"keep_rows": keep}, headers=AUTH)
        assert saved.status_code == 200, saved.text
        assert client.post("/project/close", json={}, headers=AUTH).status_code == 200
        opened = client.post("/project/open", json={"path": folder}, headers=AUTH)
        assert opened.status_code == 200, opened.text
        assert sources()["orders"] == "Sample data" and sources()["made_up_paste"] == "Pasted"


def test_rail_names_are_on_until_turned_off() -> None:
    assert navigation.rail_labels(None) is True
    assert navigation.rail_labels({"labels": False}) is False
    assert navigation.rail_labels({"labels": "no"}) is True
    assert navigation.rail_change({"labels": False}) is False
    bad: object
    for bad in ({}, {"labels": "off"}, [], None):
        with pytest.raises(navigation.NavigationError, match="labels"):
            navigation.rail_change(bad)


def test_rail_names_are_kept_on_this_computer(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/rail", headers=AUTH).json() == {"labels": True}
        assert client.put("/rail", json={"labels": False}, headers=AUTH).json() == {"labels": False}
        assert client.put("/rail", json={"labels": "x"}, headers=AUTH).status_code == 400
    with make_client(tmp_path) as client:
        assert client.get("/rail", headers=AGENT).json() == {"labels": False}


def test_the_agent_opens_the_sample_and_sets_the_rail(live: Live) -> None:  # noqa: F811
    opened = command("datasets_sample")["tables"]
    assert [t["name"].split("_")[0] for t in opened] == ["customers", "products", "orders"]
    assert command("app_rail", labels=False) == {"labels": False}
    assert live.user("GET", "/rail") == {"labels": False}
    assert command("app_rail") == {"labels": False}
    command("app_rail", labels=True)
    for t in opened:
        command("datasets_close", name=t["name"])
