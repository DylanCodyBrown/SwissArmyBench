"""Controllers on the canvas (docs/ideas.md, "After the beta: controllers", 2026-11-15), over HTTP and by
the agent's commands: each block's controller (the Properties panel's API), a default used when its
maker is not on the page (said quietly, and written into the live page, the export and the saved
pages), the check (a cycle named, a name made twice, a contract its code breaks), a thin-cell hint and
its move, and Test this page: the test page and plan written, its answer on the blocks; with a Python
that has Streamlit, the real AppTest run. Made-up data only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks
from swissarmybench_streamlit.domain import controllers as ctl
from swissarmybench_streamlit.server import streamlit_apps
from tests.conftest import AUTH
from tests.test_streamlit_apps import (  # noqa: F401 (the fixture)
    STREAMLIT_PYTHON,
    FakeRunner,
    _canvas,
    _ok,
    needs_streamlit,
    served,
)

FILTER = """# Region filter
# Makes: region: str = "All"; by_region: table = orders
import streamlit as st

region = st.selectbox("Region", ["All", *sorted(orders["region"].unique())], key="region_pick")
by_region = orders if region == "All" else orders[orders["region"] == region]
"""
VIEW = """# Sales by region
import streamlit as st

if region == "North":
    raise KeyError("North")
st.metric("Total", int(by_region["amount"].sum()))
"""
THICK = """# Top orders
import streamlit as st

top = orders[orders["amount"] > 50]
st.dataframe(top)
"""
LOOP_A = "# A\nimport streamlit as st\nx = y + 1\nst.write(x)"
LOOP_B = "# B\nimport streamlit as st\ny = x * 2\nst.write(y)"


def _notebook(folder: Path) -> str:
    cells = [notebooks.Cell("code", code) for code in (FILTER, VIEW, THICK, LOOP_A, LOOP_B)]
    path = folder / "sales.ipynb"
    path.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    return str(path)


class StandIn(FakeRunner):
    """Stands in for the test runner: keeps the folder's page and plan, and answers as told."""

    def __init__(self, answer: dict[str, Any]) -> None:
        super().__init__()
        self.answer = answer
        self.seen: list[dict[str, Any]] = []

    async def test(self, python: str, folder: str, plan: str) -> str:
        files = sorted(str(p.relative_to(folder)) for p in Path(folder).rglob("*") if p.is_file())
        page = (Path(folder) / "page.py").read_text(encoding="utf-8")
        rows = pq.read_table(Path(folder) / "data" / "orders.parquet").num_rows
        self.seen.append(
            {"python": python, "files": files, "page": page, "plan": json.loads(plan), "rows": rows}
        )
        return "warming up\n" + ctl.ANSWER + json.dumps(self.answer)


def _page(client: TestClient, path: str, *cells: int) -> tuple[str, dict[str, Any]]:
    app = _canvas(client)["app"]
    state = _ok(client.post(f"/streamlit/apps/{app}/pages", headers=AUTH, json={"name": "Sales"}))
    for cell in cells:
        state = _ok(
            client.post(
                f"/streamlit/apps/{app}/pages/p1/blocks", headers=AUTH, json={"document": path, "cell": cell}
            )
        )
    return app, state["pages"][0]


def test_each_block_carries_its_controller_and_a_missing_maker_gives_its_default(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, _ = served
    path = _notebook(tmp_path)
    app, page = _page(client, path, 2)
    view = page["blocks"][0]
    # The filter is not on the page: the view reads its defaults, said quietly; the page runs.
    assert view["defaults"] == [
        {"name": "by_region", "value": "orders", "maker": "Region filter, sales.ipynb @cell1"},
        {"name": "region", "value": "'All'", "maker": "Region filter, sales.ipynb @cell1"},
    ]
    assert page["problems"] == [] and view["controller"]["role"] == "view" and view["thin"] is None
    # With the filter placed, its controller: the role, what it makes with types and defaults.
    _, page = _page(client, path, 1, 2)
    made = page["blocks"][0]["controller"]
    assert made["role"] == "filter" and made["makes"] == [
        {"name": "region", "type": "str", "default": "'All'", "declared": True},
        {"name": "by_region", "type": "table", "default": "orders", "declared": True},
    ]
    assert made["widgets"][0]["key"] == "region_pick" and page["blocks"][1]["defaults"] == []
    # The thin-cell hint: a view that filters a table.
    _, thick = _page(client, path, 3)
    assert thick["blocks"][0]["thin"] == {"words": "Filters a table: top", "names": ["top"]}
    # The page as it runs live reads the defaults; so do the export and the saved pages.
    exported = _ok(
        client.post(f"/streamlit/apps/{app}/export", headers=AUTH, json={"folder": str(tmp_path / "out")})
    )
    written = (Path(exported["folder"]) / "app_pages" / "sales.py").read_text(encoding="utf-8")
    assert "region = 'All'  # Region filter, sales.ipynb @cell1" in written
    assert "by_region = orders" in written and exported["tables"] == ["orders"]


def test_the_check_names_cycles_and_names_made_twice_and_the_agent_reads_it(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, _ = served
    path = _notebook(tmp_path)
    app, page = _page(client, path, 4, 5, 1, 1)
    assert "need each other's names (x and y)" in page["problems"][0]
    assert page["check"]["cycles"] == [{"blocks": ["b1", "b2"], "names": ["x", "y"]}]
    assert {"name": "region", "blocks": ["b3", "b4"]} in page["check"]["twice"]
    checked = _ok(client.get(f"/streamlit/apps/{app}/check", headers=AUTH))
    one = checked["pages"][0]
    assert one["cycles"] == page["check"]["cycles"] and one["name"] == "Sales"
    assert [(c["block"], c["role"]) for c in one["controllers"]] == [
        ("b1", "view"),
        ("b2", "view"),
        ("b3", "filter"),
        ("b4", "filter"),
    ]
    assert client.get(f"/streamlit/apps/{app}/check?page=p9", headers=AUTH).status_code == 404


def test_a_thin_cells_move_is_its_lines_for_data_ipynb_and_one_read_left(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, _ = served
    path = _notebook(tmp_path)
    app, page = _page(client, path, 3, 2)
    plan = _ok(client.get(f"/streamlit/apps/{app}/pages/p1/blocks/b1/move-to-data", headers=AUTH))
    assert plan["document"] == path and plan["cell"] == 3 and plan["title"] == "top"
    assert plan["notebook"] == str(tmp_path / "data.ipynb") and plan["words"] == "Filters a table: top"
    assert plan["data_code"] == (
        '# From Top orders, sales.ipynb cell 3\ntop = orders[orders["amount"] > 50]\n'
    )
    assert (
        plan["cell_code"]
        == "# Top orders\nimport streamlit as st\n\nfrom data import top\nst.dataframe(top)\n"
    )
    refused = client.get(f"/streamlit/apps/{app}/pages/p1/blocks/b2/move-to-data", headers=AUTH)
    assert refused.status_code == 409 and "does no model work" in refused.text
    del page


def test_test_this_page_writes_the_page_and_its_plan_and_puts_the_answer_on_the_blocks(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, runner = served
    path = _notebook(tmp_path)
    app, page = _page(client, path, 1, 2)
    answer = {
        "runs": 6,
        "tries": 5,
        "cases": [
            {"case": "Region filter: Region = 'North'", "failures": {"b2": "KeyError: 'North'"}, "page": []}
        ],
        "skipped": [],
        "stopped": False,
    }
    tester = StandIn(answer)
    client.app.state.ctx.controllers._tester = tester  # type: ignore[attr-defined]
    done = _ok(client.post(f"/streamlit/apps/{app}/pages/p1/test", headers=AUTH))
    assert done["failed"] == 1 and done["failures"] == {
        "b2": [{"case": "Region filter: Region = 'North'", "error": "KeyError: 'North'"}]
    }
    seen = tester.seen[0]
    assert seen["files"] == ["data/orders.parquet", "page.py"] and seen["rows"] == 6
    assert "st.session_state['_sab_failures']['b2']" in seen["page"]
    assert [(w["block"], w["key"]) for w in seen["plan"]["widgets"]] == [("b1", "region_pick")]
    # The folder is gone; the blocks show what failed, red only there, until the page changes.
    state = _ok(client.get(f"/streamlit/apps/{app}", headers=AUTH))["pages"][0]
    assert [b["failures"] for b in state["blocks"]] == [[], done["failures"]["b2"]]
    assert state["tested"]["failed"] == 1 and state["tested"]["tries"] == 5
    _ok(client.patch(f"/streamlit/apps/{app}/pages/p1/blocks/b2", headers=AUTH, json={"w": 12, "row": 3}))
    moved = _ok(client.get(f"/streamlit/apps/{app}", headers=AUTH))["pages"][0]
    assert moved["tested"] is not None  # the layout is not the code: the result holds
    # A Python without Streamlit says so, as Play does.
    tester.missing = ["streamlit"]
    missing = _ok(client.post(f"/streamlit/apps/{app}/pages/p1/test", headers=AUTH))
    assert missing["problem"]["kind"] == "missing" and missing["problem"]["packages"] == ["streamlit"]
    assert missing["problem"]["feature"] == "Test this page"
    del runner, page


@needs_streamlit
def test_the_real_apptest_finds_the_value_that_breaks_a_block(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, runner = served
    runner.default_python = lambda: str(STREAMLIT_PYTHON)  # type: ignore[method-assign]
    client.app.state.ctx.controllers._tester = streamlit_apps.Runner()  # type: ignore[attr-defined]
    path = _notebook(tmp_path)
    app, _ = _page(client, path, 1, 2)
    done = _ok(client.post(f"/streamlit/apps/{app}/pages/p1/test", headers=AUTH))
    assert done["problem"] is None, done
    assert done["failures"] == {
        "b2": [{"case": "Region filter: Region = 'North'", "error": "KeyError: 'North'"}]
    }
    assert done["outside"] == [] and done["tries"] == 4  # All, East, North, West
