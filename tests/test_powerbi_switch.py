"""Read Power BI from reaches everything (the owner's E): the project's ONE dataset connection name (named
after the model) resolves through the switch, so DuckDB SQL `[Sales model].Customer`, the scaffolded
`%%dax Sales model` cells and Compare follow Published | Local | the file with no code change. The published
dataset is the workspace stand-in's (tests/powerbi_standin.py), Local the live link's fake
(tests/powerbi_live_fake.py), the .pbix pbixray's fake. Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.client import blades_client, sql_cell
from swissarmybench_powerbi.domain import pbix_import as rules
from tests import powerbi_live_fake as desktop
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


def test_the_dataset_name_and_a_whole_table_query() -> None:
    assert rules.dataset_name({"dataset_name": "Sales model"}) == "Sales model"
    assert rules.dataset_name({"target": r"C:\made-up\Ops review.pbix"}) == "Ops review"
    assert rules.table_of("EVALUATE 'Sales'") == "Sales"
    assert rules.table_of("evaluate Customer;") == "Customer"
    assert rules.table_of("EVALUATE 'It''s'") == "It's"
    assert rules.table_of("EVALUATE TOPN(5, 'Sales')") is None
    plan = rules.plan(fake.MODEL, "Sales model", [], [])
    named = {c.get("name"): c["source"] for c in rules.notebook_cells(plan, "Sales model")}
    assert named["Customer in Power BI"] == "%%dax 'Sales model'\nEVALUATE 'Customer'"


def _kernel_through(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A kernel's calls to the app answered by the test's client (the same routes, the agent's token)."""

    def call(method: str, path: str, body: bytes | None = None, content_type: str = "") -> Any:
        answer = client.request(method, path, content=body, headers=AGENT)
        if answer.status_code == 404:
            raise LookupError(answer.text)
        if answer.status_code != 200:
            raise RuntimeError(answer.text)
        return answer.json()

    def post_bytes(path: str, body: bytes) -> tuple[bytes, dict[str, str]]:
        answer = client.post(path, content=body, headers=AGENT)
        if answer.status_code != 200:
            raise RuntimeError(answer.text)
        return answer.content, dict(answer.headers)

    monkeypatch.setattr(blades_client, "_call", call)
    monkeypatch.setattr(blades_client, "_post_bytes", post_bytes)
    sql_cell._connections.clear()


def test_the_switch_reaches_sql_dax_cells_and_compare(
    tmp_path: Path, standin: made_up.StandIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    pbix = fake.fake_pbix(tmp_path)
    with make_client(tmp_path) as client:
        ctx: Any = client.app.state.ctx  # type: ignore[attr-defined]
        ctx.powerbi_project.reader = fake.reader
        running = desktop.FakeDesktop()
        live = ctx.powerbi_live
        live._discover, live._opener, live._windows = desktop.instances, lambda port: running, lambda: True
        live.stop()
        saved_connection(client)
        body = {"path": str(pbix), "folder": str(tmp_path / "projects")}
        done = ok(client.post("/powerbi/import", json=body, headers=AUTH))
        book = json.loads((Path(done["folder"]) / "data.ipynb").read_text())
        assert any("".join(c["source"]).startswith("%%dax 'Sales model'\n") for c in book["cells"])

        # Published: DuckDB SQL names the project's dataset connection; the workspace stand-in answers.
        query = {"sql": "SELECT * FROM [Sales model].Customer"}
        published = ok(client.post("/connections/sql/prepare", json=query, headers=AGENT))
        assert published["tables"][0]["connection"] == "Sales model" and published["tables"][0]["rows"] > 0
        assert not running.queries

        # A %%dax cell in a kernel: the same name, DAX sent to the app.
        _kernel_through(client, monkeypatch)
        found = sql_cell.connection("Sales model")
        assert found.kind == "alias" and found.language == "dax"
        frame = sql_cell.run(found, "EVALUATE 'Customer'")
        assert len(frame) > 0

        # A Compare between a table of ours and the In Power BI grid.
        ok(client.post("/datasets/regions/paste", content="CustomerKey\tRegion\n1\tNorth\n", headers=AUTH))
        grids = {g["dataset"]: g["grid"] for g in ok(client.get("/grids", headers=AUTH))["grids"]}
        keys = [["CustomerKey", "CustomerKey"]]
        pair = {"left": grids["regions"], "right": grids["Customer_PowerBI"], "keys": keys}
        made = ok(client.post("/compares", json=pair, headers=AUTH))
        before = ok(client.get(f"/compares/{made['compare']}", headers=AGENT))["counts"]

        # Local: the same SQL, cell and Compare now read Power BI Desktop's open model.
        assert ok(client.get("/powerbi/live?asked=1", headers=AGENT))["live"]
        switched = ok(client.put("/powerbi/source", json={"source": "local"}, headers=AGENT))
        assert switched["words"] == "Sales model · Local"
        local = ok(client.post("/connections/sql/prepare", json=query, headers=AGENT))
        assert local["tables"][0]["rows"] == 2  # the fake's two customers, read again (not the kept read)
        assert "EVALUATE 'Customer'" in running.queries
        running.queries.clear()
        frame = sql_cell.run(sql_cell.connection("Sales model"), "EVALUATE 'Customer'")
        assert list(frame["Region"]) == ["North", "South"] and running.queries == ["EVALUATE 'Customer'"]
        compared = ok(client.get(f"/compares/{made['compare']}", headers=AGENT))
        grids = {g["dataset"]: g["grid"] for g in ok(client.get("/grids", headers=AUTH))["grids"]}
        assert compared["right"] == grids["Customer_PowerBI"]  # the same grid, read again
        assert compared["counts"] != before and compared["counts"]["matched"] == 1
        assert compared["counts"]["right_only"] == 1  # the fake's second customer

        # The file: DAX that is not a whole table is refused in words; a whole table reads the file.
        ctx.powerbi_project.live = None
        refused = client.post(
            "/connections/sql/alias/dax",
            json={"name": "Sales model", "dax": "EVALUATE TOPN(1, 'Sales')"},
            headers=AGENT,
        )
        assert refused.status_code == 403 and "whole tables only" in refused.text
