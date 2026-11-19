"""The canvas's property pane over HTTP and by the agent's canvas_* commands (the owner, 2026-11-19): a
block's properties, widgets, uses (tables, variables, connections, cells), used by, state and cache from a
made-up project (data.ipynb, an app notebook, a canvas with three blocks); a table's preview; a change to a
cell's code as a plan of only its own characters; Now (the running app's session state and caches) written
for the live page. With a Python that has Streamlit, the live page really takes a Now value. Made-up data."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks
from swissarmybench_streamlit.domain import app_settings
from tests.conftest import AUTH
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command
from tests.test_streamlit_apps import (  # noqa: F401 (the fixture)
    ORDERS,
    STREAMLIT_PYTHON,
    FakeRunner,
    _canvas,
    _files,
    _ok,
    needs_streamlit,
    served,
)

DATA = "# Tax\nTAX = 0.2\n"
FILTER = """# Region filter
import os
import streamlit as st

region = st.selectbox("Region", ["All", "East", "West"], index=0, key="region_pick")
least = st.slider("Least amount", 0, 500, 50)
folder = os.environ["REPORT_FOLDER"]
"""
CHART = """# Sales by region
import streamlit as st


@st.cache_data(ttl=600)
def by_region(orders, region, least):
    kept = orders[orders["amount"] >= least]
    return kept if region == "All" else kept[kept["region"] == region]


shown = by_region(orders, region, least)
st.bar_chart(shown, x="region", y="amount")
st.caption(f"Tax {TAX}")
"""
TOTAL = """# Total
import streamlit as st

st.metric("Total", int(shown["amount"].sum()), delta=compute_delta(shown))
"""


def _project(folder: Path) -> str:
    (folder / "data.ipynb").write_text(
        notebooks.write_notebook([notebooks.Cell("code", DATA)]), encoding="utf-8"
    )
    cells = [notebooks.Cell("code", code) for code in (FILTER, CHART, TOTAL)]
    path = folder / "app.ipynb"
    path.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    return str(path)


def _built(client: TestClient, folder: Path) -> tuple[str, str]:
    """A canvas saved beside the project's notebooks, its three cells on one page."""
    path = _project(folder)
    app = _canvas(client, document=str(folder / "sales.stapp.json"))["app"]
    _ok(client.post(f"/streamlit/apps/{app}/pages", headers=AUTH, json={"name": "Sales"}))
    for cell in (1, 2, 3):
        body = {"document": path, "cell": cell}
        _ok(client.post(f"/streamlit/apps/{app}/pages/p1/blocks", headers=AUTH, json=body))
    return app, path


def _inspect(client: TestClient, app: str, **asked: str) -> dict[str, Any]:
    return _ok(client.get(f"/streamlit/apps/{app}/inspect", headers=AUTH, params=asked))


def test_a_block_shows_its_widgets_and_everything_it_uses(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, _ = served
    app, path = _built(client, tmp_path)
    block = _inspect(client, app, page="p1", block="b1")
    assert block["target"] == "block" and block["editable"] and block["problem"] is None
    assert block["block"]["name"] == "Region filter" and block["block"]["where"] == "app.ipynb @cell1"
    assert block["makes"] == ["os", "region", "least", "folder"]
    region, least = block["widgets"]
    assert (region["call"], region["target"], region["key"], region["state_key"]) == (
        "selectbox", "region", "region_pick", "region_pick",
    )  # fmt: skip
    assert region["arguments"]["index"]["value"] == 0 and region["default"] == "index"
    assert region["arguments"]["options"]["value"] == ["All", "East", "West"]
    assert {p["name"] for p in region["params"]} >= {"label", "options", "index", "key", "help", "disabled"}
    assert all(p["words"] and p["category"] for p in region["params"])
    assert (least["key"], least["state_key"], least["now"], least["held"]) == (None, "b1_1", None, False)
    # Uses: the variable it reads (never its value unless the Variables page shows it), no table.
    uses = block["uses"]
    assert [v["name"] for v in uses["variables"]] == ["REPORT_FOLDER"]
    assert uses["variables"][0]["defined"] is False and "value" not in uses["variables"][0]
    assert uses["tables"] == [] and uses["cells"] == []
    # Used by: the chart reads region and least.
    assert [(u["block"], u["names"], u["title"]) for u in uses["used_by"]] == [
        ("b2", ["region", "least"], "Sales by region")
    ]
    # The exact code the page runs for it: each widget keyed, inside its slot.
    assert block["code"].startswith("with _slot_b1:\n    # Region filter\n")
    assert 'st.slider("Least amount", 0, 500, 50, key="b1_1")' in block["code"]

    chart = _inspect(client, app, block="b2")  # the page found from the block
    uses = chart["uses"]
    assert uses["tables"] == [
        {
            "name": "orders",
            "dataset": "orders",
            "grid": uses["tables"][0]["grid"],
            "rows": 6,
            "columns": 3,
            "steps": 0,
        }
    ]
    assert [(c["name"], c["where"], c["block"]) for c in uses["cells"]] == [
        ("region", "app.ipynb @cell1", "b1"),
        ("least", "app.ipynb @cell1", "b1"),
        ("TAX", "data.ipynb", None),
    ]
    assert [u["block"] for u in uses["used_by"]] == ["b3"]
    # Its lineage as one line ends at this block's cell.
    assert uses["lineage"] and uses["lineage"][-1]["target"] is True
    assert [c["function"] if "function" in c else c["name"] for c in chart["cache"]] == ["by_region"]
    cached = chart["cache"][0]
    assert (cached["cache"], cached["settings"]["ttl"]["value"], cached["own"]) == ("data", 600, True)
    # Code that is not a plain value is shown as what it is.
    total = _inspect(client, app, page="p1", block="b3")
    assert total["widgets"][0]["arguments"]["delta"]["kind"] == "expression"
    assert total["widgets"][0]["arguments"]["value"]["kind"] == "expression"

    page = _inspect(client, app, page="p1")
    assert page["target"] == "page" and page["tables"] == ["orders"]
    assert [b["name"] for b in page["blocks"]] == ["Region filter", "Sales by region", "Total"]
    whole = _inspect(client, app)
    assert whole["target"] == "app" and whole["documents"] == [path]
    assert whole["pages"] == [{"id": "p1", "name": "Sales", "blocks": 3}]
    assert client.get(f"/streamlit/apps/{app}/inspect?block=b9", headers=AUTH).status_code == 404


def test_a_table_opens_beside_the_canvas_with_its_steps_in_words(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
) -> None:
    client, _ = served
    grid = _ok(client.get("/streamlit/tables/orders", headers=AUTH))["grid"]
    step = {"kind": "limit", "params": {"n": 3}}
    added = client.post(f"/grids/{grid}/steps", headers=AUTH, json={"steps": [step]})
    assert added.status_code == 200, added.text
    table = _ok(client.get("/streamlit/tables/orders", headers=AUTH))
    assert table["grid"] == grid and table["rows"] == 3
    assert [c["name"] for c in table["columns"]] == ["order_id", "region", "amount"]
    assert all(c["type"] for c in table["columns"])
    assert len(table["steps"]) == 1 and "3" in table["steps"][0]
    assert [row[2] for row in table["head"]] == [100, 250, 40]
    assert client.get("/streamlit/tables/nothing", headers=AUTH).status_code == 404


def test_a_change_to_a_cells_code_is_a_plan_of_only_its_own_characters(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, _ = served
    app, path = _built(client, tmp_path)
    url = f"/streamlit/apps/{app}/pages/p1/blocks"

    def plan(block: str, **body: Any) -> Any:
        return client.post(f"{url}/{block}/code", headers=AUTH, json=body)

    on_disk = Path(path).read_text(encoding="utf-8")
    made = _ok(plan("b1", do="set", widget=1, name="default", value=120))
    assert (made["document"], made["cell"], made["where"], made["changed"]) == (
        path,
        1,
        "app.ipynb @cell1",
        True,
    )
    assert made["before"] == FILTER.rstrip("\n") or made["before"] == FILTER
    assert made["code"] == made["before"].replace("0, 500, 50)", "0, 500, 120)")
    assert made["edits"] == [
        {"start": made["before"].index("50)"), "end": made["before"].index("50)") + 2, "text": "120"}
    ]
    # Nothing was written anywhere: the file is as it was.
    assert Path(path).read_text(encoding="utf-8") == on_disk
    # The widget's own default by name (a selectbox's is index); a key added; a handler; a cache's setting.
    assert "index=2, key" in _ok(plan("b1", do="set", widget=0, name="default", value=2))["code"]
    assert 'key="least")' in _ok(plan("b1", do="set", widget=1, name="key", value="least"))["code"]
    handled = _ok(plan("b1", do="handler", widget=0))
    assert handled["handler"] == "on_region_pick_change" and handled["line"] == 5
    assert "on_change=on_region_pick_change)" in handled["code"]
    cached = _ok(plan("b2", do="cache", function="by_region", kind="data", settings={"ttl": 60}))
    assert cached["code"] == cached["before"].replace("ttl=600", "ttl=60")
    # A function of a cell this one calls is changed in ITS cell.
    other = _ok(plan("b3", do="cache", function="by_region", kind="resource", document=path, cell=2))
    assert (other["cell"], "@st.cache_resource(ttl=600)" in other["code"]) == (2, True)
    # Refused plainly: code that is not a plain value, an element that is not there, a missing action.
    refused = plan("b3", do="set", widget=0, name="delta", value=5)
    assert refused.status_code == 409 and "is code, not a plain value" in refused.text
    assert plan("b3", do="set", widget=7, name="value", value=5).status_code == 400
    assert plan("b3", do="rewrite").status_code == 400
    assert plan("b9", do="set", widget=0, name="value", value=5).status_code == 404
    # The same change again changes nothing.
    again = _ok(plan("b1", do="set", widget=1, name="default", value=50))
    assert again["changed"] is False and again["edits"] == []


def test_now_is_written_for_the_running_page_only(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, runner = served
    app, _ = _built(client, tmp_path)
    now = f"/streamlit/apps/{app}/now"
    idle = client.post(now, headers=AUTH, json={"key": "region_pick", "value": "East"})
    assert idle.status_code == 409 and "Play the page first" in idle.text
    _ok(client.post(f"/streamlit/apps/{app}/run", headers=AUTH))
    folder = _files(runner)
    page = next(folder.glob("page_p1_*.py")).read_text(encoding="utf-8")
    assert page.index("_sab_clear = _sab_now()") < page.index("# The layout")
    assert page.rstrip().endswith("st.rerun()")
    compile(page, "page.py", "exec")
    entry = (folder / "app.py").read_text(encoding="utf-8")
    assert _ok(client.post(now, headers=AUTH, json={"key": "region_pick", "value": "East"}))["made"] == {
        "set": {"region_pick": "East"}
    }
    _ok(client.post(now, headers=AUTH, json={"clear": "by_region"}))
    _ok(client.post(now, headers=AUTH, json={"key": "b1_1", "forget": True}))
    held = json.loads((folder / app_settings.NOW_FILE).read_text(encoding="utf-8"))
    assert held["made"] == [
        {"n": 1, "set": {"region_pick": "East"}},
        {"n": 2, "clear": ["by_region"]},
        {"n": 3, "forget": ["b1_1"]},
    ]
    # The open pages run again (the entry's text changed), and every page is still there.
    assert (folder / "app.py").read_text(encoding="utf-8") != entry
    assert list(folder.glob("page_p1_*.py"))
    for bad in ({"key": "_sab_now", "value": 1}, {"clear": "not a name"}, {"key": "x"}, [1]):
        assert client.post(now, headers=AUTH, json=bad).status_code == 400
    _ok(client.post(f"/streamlit/apps/{app}/stop", headers=AUTH))
    assert client.post(now, headers=AUTH, json={"clear": "*"}).status_code == 409


def test_the_toolbox_and_a_dropped_elements_cell(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, _ = served
    app, _ = _built(client, tmp_path)
    listed = _ok(client.get("/streamlit/toolbox", headers=AUTH))
    assert listed["groups"][0] == "Input" and any(i["id"] == "tabs" for i in listed["items"])
    made = _ok(client.post(f"/streamlit/apps/{app}/toolbox", headers=AUTH, json={"element": "slider"}))
    assert made == {
        "code": '# Slider 1\nslider_1 = st.slider("Slider 1", min_value=0, max_value=100, value=50, '
        'key="slider_1")\n',
        "name": "Slider 1",
        "variable": "slider_1",
        "element": "slider",
        "kind": "code",
    }
    # A data element shows an open table.
    frame = _ok(client.post(f"/streamlit/apps/{app}/toolbox", headers=AUTH, json={"element": "dataframe"}))
    assert frame["code"].split("\n")[1] in ("st.dataframe(orders)", "st.dataframe(customers)")
    assert (
        client.post(f"/streamlit/apps/{app}/toolbox", headers=AUTH, json={"element": "x"}).status_code == 400
    )


def test_the_agent_inspects_and_changes_a_canvas_by_its_commands(live: Live, tmp_path: Path) -> None:  # noqa: F811
    path = _project(tmp_path)
    app = command("streamlit_open")["app"]
    page = command("streamlit_page_add", app=app, name="Sales")["page"]
    for cell in (1, 2):
        command("streamlit_block_place", app=app, page=page, document=path, cell=cell)
    seen = command("canvas_inspect", app=app, page=page, block="b1")
    assert [w["call"] for w in seen["widgets"]] == ["selectbox", "slider"]
    assert command("canvas_inspect", app=app)["target"] == "app"
    assert any(i["id"] == "slider" for i in command("canvas_toolbox")["items"])
    assert command("canvas_toolbox", app=app, element="toggle")["variable"] == "toggle_1"
    # The app is open without a Workbench window: a change to a cell's code says where it is made.
    for name, args in (
        ("canvas_set_default", {"value": 120, "widget": 1}),
        ("canvas_set_property", {"name": "help", "value": '"Pick one"'}),
        ("canvas_bind", {"name": "disabled", "kind": "state", "target": "locked"}),
        ("canvas_add_handler", {}),
    ):
        with pytest.raises(Exception, match="without a Workbench window"):
            command(name, app=app, page=page, block="b1", **args)
    with pytest.raises(Exception, match="without a Workbench window"):
        command("canvas_set_cache", app=app, page=page, block="b2", function="by_region", settings={"ttl": 5})
    # Now needs the page playing.
    with pytest.raises(Exception, match="Play the page first"):
        command("canvas_state_set", app=app, key="region_pick", value='"East"')
    with pytest.raises(Exception, match="Play the page first"):
        command("canvas_cache_clear", app=app)
    with pytest.raises(Exception, match="No open table is called orders"):
        command("canvas_table", name="orders")


NOW_PAGE = """
import streamlit as st
{head}
region = st.selectbox("Region", ["All", "East", "West"], key="region_pick")
st.write("picked", region)
{tail}
"""


@needs_streamlit
def test_the_live_page_takes_a_now_value_and_forgets_a_fresh_sessions(tmp_path: Path) -> None:
    """The page's own head, run by Streamlit's AppTest: a session that is running takes what Now asked
    once; a session that starts afterwards starts fresh."""
    (tmp_path / "page.py").write_text(
        NOW_PAGE.format(head=app_settings.NOW_HEAD, tail=app_settings.NOW_TAIL), encoding="utf-8"
    )
    script = textwrap.dedent(
        """
        import json, sys
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        folder = Path(sys.argv[1])
        at = AppTest.from_file(str(folder / "page.py")).run()
        first = at.selectbox[0].value
        asked = {"made": [{"n": 1, "set": {"region_pick": "West"}}]}
        (folder / "_sab_now.json").write_text(json.dumps(asked))
        at.run()
        second = at.selectbox[0].value
        at.run()
        fresh = AppTest.from_file(str(folder / "page.py")).run()
        print(json.dumps([first, second, at.selectbox[0].value, fresh.selectbox[0].value, len(at.exception)]))
        """
    )
    assert STREAMLIT_PYTHON is not None
    done = subprocess.run(  # noqa: S603
        [STREAMLIT_PYTHON, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert json.loads(done.stdout.strip().splitlines()[-1]) == ["All", "West", "West", "All", 0]
