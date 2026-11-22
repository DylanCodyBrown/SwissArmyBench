"""The round trip (the owner's B8): part 1's .pbip export reads a Power BI project's .sab/powerbi.json.
An untouched table keeps its M byte for byte; a table whose notebook query changed goes with its new native
query; the measures go with their folders and formats. pbixray is faked (tests/powerbi_pbix_fake.py); the
published dataset is found through tests/powerbi_standin.py. Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench_powerbi.domain import pbix_import as rules
from tests import powerbi_pbix_fake as fake
from tests import powerbi_standin as made_up
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_powerbi import saved_connection


@pytest.fixture(autouse=True)
def extension_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SWISSARMYBENCH_EXTENSIONS", "streamlit,powerbi")
    with memory_keyring():
        yield


@pytest.fixture
def standin(monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def test_the_round_trip_rules_keep_an_untouched_m_and_rebuild_a_changed_one() -> None:
    plan = rules.plan(fake.MODEL, "Sales model", [], [])
    state = rules.state_json(plan, "Sales model.pbix", "", "Sales model file")
    assert state["tables"][0]["columns"][0] == ["OrderKey", "int64"]
    assert state["tables"][0]["columns"][3] == ["Amount", "double"]
    book = rules.notebook_json(rules.notebook_cells(plan, None))
    queries = rules.notebook_queries(book)
    assert queries["Customer"] == "SELECT * FROM dbo.Customer"
    trips = {t.name: t for t in rules.round_trip_tables(state, queries)}
    assert set(trips) == {"Sales", "Customer", "Product"}  # the date table has no M: it stays out
    assert all(t.how == "kept" for t in trips.values())
    assert trips["Product"].m.text == fake.PRODUCT_M and trips["Product"].m.parameters == ("PgHost",)
    changed = dict(queries, Product="SELECT * FROM public.product WHERE active")
    product = {t.name: t for t in rules.round_trip_tables(state, changed)}["Product"]
    assert product.how == "query" and product.m.parameters == ("PgHost",)
    assert 'Value.NativeQuery(Source, "SELECT * FROM public.product WHERE active"' in product.m.text
    measure = rules.kept_measures(state)[0]
    assert measure["display_folder"] == "KPIs" and measure["format_string"] == "#,0"
    assert rules.notebook_queries("not a notebook") == {} and rules.notebook_queries(None) == {}


def _partition_m(tmdl: str) -> str:
    """A table's partition source in a TMDL file, its four tabs of indent taken off."""
    lines = tmdl.splitlines()
    start = lines.index("\t\tsource =") + 1
    body: list[str] = []
    for line in lines[start:]:
        if line and not line.startswith("\t\t\t\t"):
            break
        body.append(line[4:])
    return "\n".join(body).rstrip("\n")


def test_import_change_one_query_then_export_the_round_trip(tmp_path: Path, standin: made_up.StandIn) -> None:
    pbix = fake.fake_pbix(tmp_path)
    with make_client(tmp_path) as client:
        client.app.state.ctx.extension["powerbi"].project.reader = fake.reader  # type: ignore[attr-defined]
        saved_connection(client)
        body = {"path": str(pbix), "folder": str(tmp_path / "projects")}
        folder = Path(ok(client.post("/powerbi/import", json=body, headers=AUTH))["folder"])
        notebook = folder / "data.ipynb"
        book = json.loads(notebook.read_text())
        for cell in book["cells"]:
            if cell["metadata"]["swissarmybench"].get("name") == "Customer source":
                cell["source"] = ["%%sql SalesDb\n", "SELECT * FROM dbo.Customer WHERE Region = 'North'"]
        notebook.write_text(json.dumps(book))

        wanted = {"tables": ["Sales", "Customer", "Product"]}
        plan = ok(client.post("/powerbi/plan", json=wanted, headers=AGENT))
        by = {t["name"]: t for t in plan["tables"]}
        assert by["Sales"]["goes"] and by["Sales"]["notes"] == ["its Power Query as the .pbix had it"]
        assert by["Customer"]["notes"] == ["its notebook query changed: it goes as a native query"]
        assert not any(t["name"].endswith(("_Source", "_PowerBI")) for t in plan["tables"])

        ok(client.post("/powerbi/export", json=wanted, headers=AUTH))
        tables = folder / "powerbi" / "Sales model.SemanticModel" / "definition" / "tables"
        sales = (tables / "Sales.tmdl").read_text()
        assert _partition_m(sales) == fake.SALES_M  # untouched: byte for byte
        assert _partition_m((tables / "Product.tmdl").read_text()) == fake.PRODUCT_M
        customer = _partition_m((tables / "Customer.tmdl").read_text())
        assert customer != fake.CUSTOMER_M
        assert "[Query=\"SELECT * FROM dbo.Customer WHERE Region = 'North'\"]" in customer
        assert "Total Sales" in sales and "SUM(Sales[Amount])" in sales
        assert "displayFolder: KPIs" in sales and "formatString: #,0" in sales
        expressions = (tables.parent / "expressions.tmdl").read_text()
        assert "expression PgHost = " in expressions and "pg01.contoso.example" in expressions
