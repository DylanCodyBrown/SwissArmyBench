"""The widgets' routes (services/widgets.py), as the Widgets window and the agent use them: the library's
widgets/ folder (one file each, written only when its bytes change), the prebuilt ones read-only (Copy as your
own), the header written alone (a rename checked live), a property's default written back, Run in place, and
the agent's delete waiting for the user's Allow. Made-up data only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from tests.conftest import AGENT, AUTH, make_client, push
from tests.streamlit_helpers import FakeRunner, answering

ORDERS = pa.table({"month": ["2026-01", "2026-02"], "region": ["North", "South"], "revenue": [120.5, 98.0]})


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, FakeRunner]]:
    with make_client(tmp_path) as client:
        runner = FakeRunner()
        client.app.state.ctx.extension["streamlit"].live_runs.use_runner(runner)  # type: ignore[attr-defined]
        assert push(client, "orders", ORDERS).status_code == 200
        yield client, runner


def ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return dict(response.json())


def library(client: TestClient) -> Path:
    return Path(client.app.state.ctx.library.folder()) / "widgets"  # type: ignore[attr-defined]


CODE = (
    'import streamlit as st\n\nfrom sab_canvas import table\n\ntable_name = "orders"  # table\n'
    'colour = "#1f77b4"  # the line\n\nst.dataframe(table(table_name))\n'
)


def test_the_listing_has_the_prebuilt_widgets_by_group_with_their_properties(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, _ = served
    listing = ok(client.get("/streamlit/widgets", headers=AUTH))
    names = {w["name"]: w for w in listing["widgets"]}
    assert len(names) >= 40 and all(w["prebuilt"] for w in names.values())
    chart = names["line_chart"]
    assert chart["group"] == "Charts" and chart["description"]
    assert {p["name"]: p["mask"] for p in chart["properties"]}["colour"] == "colour"
    found = ok(client.get("/streamlit/widgets?q=donut", headers=AUTH))
    assert [w["name"] for w in found["widgets"]] == ["donut_chart"]


def test_the_listing_puts_each_starter_pack_first_in_its_order_with_its_description(
    served: tuple[TestClient, FakeRunner],
) -> None:
    from swissarmybench_streamlit.domain import widget_packs as packs

    client, _ = served
    listing = ok(client.get("/streamlit/widgets", headers=AUTH))
    assert [p["name"] for p in listing["packs"]] == list(packs.PACKS)
    seen: list[str] = []
    for widget in listing["widgets"]:
        heading = widget["pack"] or widget["group"]
        if not seen or seen[-1] != heading:
            assert heading not in seen, heading  # each heading's widgets together
            seen.append(heading)
    assert seen[: len(packs.PACKS)] == list(packs.PACKS)
    kpi = next(w for w in listing["widgets"] if w["name"] == "sales_kpi_row")
    assert kpi["pack"] == "Sales dashboard" and kpi["pack_description"] == packs.PACKS["Sales dashboard"]
    assert next(w for w in listing["widgets"] if w["name"] == "line_chart")["pack"] == ""
    found = ok(client.get("/streamlit/widgets?q=customer+service", headers=AUTH))
    assert {w["pack"] for w in found["widgets"]} == {"Customer service"}


def test_a_new_widget_is_one_file_in_the_library_written_only_when_it_changes(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, _ = served
    made = ok(
        client.post(
            "/streamlit/widgets",
            headers=AUTH,
            json={"name": "sales_table", "description": "Sales", "code": CODE},
        )
    )
    path = library(client) / "sales_table.widget.py"
    assert path.is_file() and made["file"] == str(path) and not made["prebuilt"]
    assert {p["name"]: p["type"] for p in made["properties"]} == {"table_name": "table", "colour": "colour"}
    stamp = path.stat().st_mtime_ns
    ok(client.put("/streamlit/widgets/sales_table", headers=AUTH, json={"code": CODE}))  # nothing changed
    assert path.stat().st_mtime_ns == stamp
    taken = client.post("/streamlit/widgets", headers=AUTH, json={"name": "sales_table"})
    assert taken.status_code == 409 and "taken" in taken.text
    bad = client.post("/streamlit/widgets", headers=AUTH, json={"name": "Sales Table"})
    assert bad.status_code == 400


def test_a_property_is_written_back_into_its_own_characters_and_checked_first(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, _ = served
    ok(client.post("/streamlit/widgets", headers=AUTH, json={"name": "sales_table", "code": CODE}))
    after = ok(
        client.post(
            "/streamlit/widgets/sales_table/property",
            headers=AUTH,
            json={"property": "colour", "value": "#d62728"},
        )
    )
    assert after["code"] == CODE.replace("#1f77b4", "#d62728")
    bad = client.post(
        "/streamlit/widgets/sales_table/property", headers=AUTH, json={"property": "colour", "value": "blue"}
    )
    assert bad.status_code == 400 and "not a colour" in bad.text
    said = ok(
        client.post(
            "/streamlit/widgets/check-value",
            headers=AUTH,
            json={"name": "sales_table", "property": "table_name", "value": "sales"},
        )
    )
    assert said == {
        "ok": False,
        "said": "There is no table called sales here.",
        "fix": "Pick an open table, a data.ipynb table or a connection's, or leave it empty for sample data.",
    }
    assert ok(
        client.post(
            "/streamlit/widgets/check-value",
            headers=AUTH,
            json={"name": "sales_table", "property": "table_name", "value": "orders"},
        )
    )["ok"]
    live = ok(client.post("/streamlit/widgets/properties", headers=AUTH, json={"code": "a = 1\nb = True\n"}))
    assert [(p["name"], p["mask"]) for p in live["properties"]] == [("a", "number"), ("b", "switch")]
    broken = ok(client.post("/streamlit/widgets/properties", headers=AUTH, json={"code": "a = (\n"}))
    assert broken["properties"] == [] and broken["problem"]["line"]


def test_a_prebuilt_widget_is_read_only_and_copied_as_your_own(served: tuple[TestClient, FakeRunner]) -> None:
    client, _ = served
    refused = client.put("/streamlit/widgets/button", headers=AUTH, json={"code": "x = 1\n"})
    assert refused.status_code == 403 and "Copy as your own" in refused.text
    copied = ok(client.post("/streamlit/widgets/button/copy", headers=AUTH))
    assert copied["name"] == "my_button" and not copied["prebuilt"]
    assert (library(client) / "my_button.widget.py").is_file()
    again = ok(client.post("/streamlit/widgets/button/copy", headers=AUTH))
    assert again["name"] == "my_button_2"


def test_name_and_description_go_into_the_header_only_and_the_name_is_checked_live(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, _ = served
    ok(client.post("/streamlit/widgets", headers=AUTH, json={"name": "sales_table", "code": CODE}))
    assert ok(client.get("/streamlit/widgets/check-name?name=button", headers=AUTH))["state"] == "taken"
    assert (
        ok(client.get("/streamlit/widgets/check-name?name=sales_table&own=sales_table", headers=AUTH))[
            "state"
        ]
        == "available"
    )
    assert ok(client.get("/streamlit/widgets/check-name?name=Bad%20name", headers=AUTH))["state"] == "invalid"
    renamed = ok(
        client.patch(
            "/streamlit/widgets/sales_table",
            headers=AUTH,
            json={"name": "region_sales", "description": "Sales by region"},
        )
    )
    assert renamed["name"] == "region_sales" and renamed["description"] == "Sales by region"
    assert renamed["code"] == CODE  # the code's bytes, as they were
    assert not (library(client) / "sales_table.widget.py").exists()
    assert (
        client.patch("/streamlit/widgets/region_sales", headers=AUTH, json={"name": "button"}).status_code
        == 409
    )


def test_run_in_place_writes_the_widget_alone_with_its_values_and_the_tables_it_names(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, runner = served
    ok(client.post("/streamlit/widgets", headers=AUTH, json={"name": "sales_table", "code": CODE}))
    ran = ok(
        client.post(
            "/streamlit/widgets/sales_table/run",
            headers=AUTH,
            json={"values": {"colour": "#000000"}, "window": "w1", "python": "/p"},
        )
    )
    assert ran["ok"] and ran["url"].startswith("/streamlit/run/widget-w1-")
    python, folder, base = runner.started[0]
    assert python == "/p" and ran["url"].startswith(base)
    page = (Path(folder) / "app_pages" / "sales_table.py").read_text()
    assert 'sab.render(\'sales_table\', {"table_name": "orders", "colour": "#000000"}, \'w1\')' in page
    assert (Path(folder) / "data" / "orders.parquet").is_file()
    assert "CODE['sales_table']" in (Path(folder) / "sab_widgets.py").read_text()
    # Run again with the editor's code (not saved): the same process, the files rewritten.
    ok(
        client.post(
            "/streamlit/widgets/sales_table/run",
            headers=AUTH,
            json={"code": CODE.replace("dataframe", "table"), "window": "w1", "python": "/p"},
        )
    )
    assert len(runner.started) == 1 and "st.table(" in (Path(folder) / "sab_widgets.py").read_text()
    assert ok(client.post("/streamlit/widgets/stop", headers=AUTH, json={"window": "w1"}))["ok"]


def test_a_python_without_streamlit_is_said_with_its_install(served: tuple[TestClient, FakeRunner]) -> None:
    client, runner = served
    runner.missing = ["streamlit"]
    ran = ok(client.post("/streamlit/widgets/button/run", headers=AUTH, json={"python": "/p"}))
    assert not ran["ok"] and ran["problem"]["kind"] == "missing" and runner.started == []
    # The page's one install prompt reads what is missing and where it goes: no project open, the app's own.
    problem = ran["problem"]
    assert problem["packages"][0] == "streamlit" and problem["python"] == "/p" and problem["install"] == "app"


def test_the_agents_delete_waits_for_the_users_allow(served: tuple[TestClient, FakeRunner]) -> None:
    client, _ = served
    ok(client.post("/streamlit/widgets", headers=AUTH, json={"name": "sales_table", "code": CODE}))
    pending = lambda: client.get("/agent/approvals", headers=AUTH).json()["pending"]  # noqa: E731

    def answer(request: str, yes: bool) -> Any:
        return client.post(f"/agent/approvals/{request}", headers=AUTH, json={"approve": yes})

    with answering(pending, answer, approve=False) as asked:
        declined = client.delete("/streamlit/widgets/sales_table", headers=AGENT)
    assert declined.status_code == 403 and asked and (library(client) / "sales_table.widget.py").exists()
    with answering(pending, answer, approve=True):
        ok(client.delete("/streamlit/widgets/sales_table", headers=AGENT))
    assert not (library(client) / "sales_table.widget.py").exists()
