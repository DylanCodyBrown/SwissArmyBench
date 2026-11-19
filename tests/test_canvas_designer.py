"""The designer (the owner, 2026-11-19: "a canvas as flexible as WinForms and WPF"): layout containers
(columns, tabs, expander, container, form, sidebar, popover) that hold blocks and each other, written into
the app's file and read back identical, exported as plain Streamlit; arranging several blocks (align, same
size, distribute: the maths in the grid's own units); the Document Outline; all of it over HTTP and by the
agent's commands. With a Python that has Streamlit, a page built with containers, an event and a binding
exports to code that runs under AppTest. Made-up data only."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks
from swissarmybench_streamlit.domain import designer
from swissarmybench_streamlit.domain import streamlit_cells as rules
from swissarmybench_streamlit.domain import widget_code as wc
from swissarmybench_streamlit.domain.streamlit_cells import Block, Container, Page, PieceCode
from tests.conftest import AUTH
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command
from tests.test_streamlit_apps import (  # noqa: F401 (the fixture)
    STREAMLIT_PYTHON,
    FakeRunner,
    _canvas,
    _ok,
    needs_streamlit,
    served,
)

DOC = "/work/app.ipynb"


def _page() -> Page:
    """A page with one of everything: columns holding a filter and tabs, an expander in a tab, a form,
    a popover, a bordered container, and the sidebar."""
    page = Page(
        "p1",
        "Sales",
        [
            Block("b1", DOC, 1, 1, 1, 12, None, "c1", 0),
            Block("b2", DOC, 2, 1, 1, 12, None, "c2", 0),
            Block("b3", DOC, 3, 1, 1, 6, 4, "c3", 0),
            Block("b4", DOC, 4, 1, 1, 12, None, "c4", 0),
            Block("b5", DOC, 5, 2, 1, 6, None, None, 0, True, True),
            Block("b6", DOC, 6, 1, 1, 12, None, "c5", 0),
            Block("b7", DOC, 7, 1, 1, 12, None, "c6", 0),
            Block("b8", DOC, 8, 1, 1, 12, None, "c7", 0),
        ],
        [
            Container("c1", "columns", 1, 1, 12, None, None, 0, {"widths": [1, 3], "gap": "large"}),
            Container("c2", "tabs", 1, 1, 12, None, "c1", 1, {"labels": ["Chart", "Table"]}),
            Container("c3", "expander", 1, 1, 12, None, "c2", 1, {"label": "More", "expanded": True}),
            Container("c4", "form", 2, 7, 6, None, None, 0, {"submit": "Apply", "submitted": "applied"}),
            Container("c5", "sidebar"),
            Container("c6", "popover", 3, 1, 4, None, None, 0, {"label": "Help"}, "Help box"),
            Container("c7", "container", 3, 5, 8, 5, None, 0, {}, "", False, True),
        ],
    )
    rules.settle_page(page)
    return page


def test_containers_are_written_into_the_apps_file_and_read_back_identical() -> None:
    page = _page()
    text = rules.write_app([page])
    assert '"version": 2' in text
    # One line a block, one line a container: a change is a one-line diff.
    assert (
        '        {"id": "c1", "kind": "columns", "row": 1, "column": 1, "width": 12, "height": null, '
        '"props": {"widths": [1, 3], "gap": "large"}},\n' in text
    )
    assert '"parent": "c1", "slot": 0}' in text and '"hidden": true, "locked": true}' in text
    assert '{"id": "c5", "kind": "sidebar"}' in text
    again = rules.read_app(text)

    def held(made: Page) -> dict[str, Any]:
        """A page without its blocks' ids (the file holds none: they are given in reading order)."""
        said = made.to_json()
        return said | {"blocks": [{k: v for k, v in block.items() if k != "id"} for block in said["blocks"]]}

    assert held(again[0]) == held(page)
    assert [c.id for c in again[0].containers] == [c.id for c in page.containers]
    assert rules.write_app(again) == text
    # A page with no container, nothing hidden and nothing locked is written as it always was.
    plain = rules.write_app([Page("p1", "Plain", [Block("b1", DOC, 1)])])
    assert '"version": 1' in plain and "containers" not in plain and "parent" not in plain


def test_the_layout_opens_each_container_as_plain_streamlit() -> None:
    page = _page()
    made = rules.page_code("Sales", page.blocks, {}, [], containers=page.containers)
    layout = made.code[made.code.index(rules.LAYOUT_LINE) :].split("\n\n")[0].split("\n")[1:]
    assert layout == [
        "_in_c1 = st.columns([1, 3], gap='large')",
        "_slot_b1 = _in_c1[0].container()",
        "_in_c2 = _in_c1[1].tabs(['Chart', 'Table'])",
        "_slot_b2 = _in_c2[0].container()",
        "_in_c3 = _in_c2[1].expander('More', expanded=True)",
        "_row_c3_1 = _in_c3.columns([6, 6])",
        "_slot_b3 = _row_c3_1[0].container(height=160)",
        "_row_2 = st.columns([6, 6])",
        "_slot_b5 = _row_2[0].container()",
        "_in_c4 = _row_2[1].form('c4')",
        "_slot_b4 = _in_c4.container()",
        "applied = _in_c4.form_submit_button('Apply')",
        "_row_3 = st.columns([4, 8])",
        "_in_c6 = _row_3[0].popover('Help')",
        "_slot_b7 = _in_c6.container()",
        "_in_c7 = _row_3[1].container(border=True, height=200)",
        "_slot_b8 = _in_c7.container()",
        "_in_c5 = st.sidebar",
        "_slot_b6 = _in_c5.container()",
    ]
    compile(made.code, "page.py", "exec")
    # A page without containers is laid out exactly as before.
    flat = [Block("b1", DOC, 1, 1, 1, 6), Block("b2", DOC, 2, 1, 7, 6), Block("b3", DOC, 3, 2, 1, 12, 5)]
    assert rules._layout(flat) == [
        "_row_1 = st.columns([6, 6])",
        "_slot_b1 = _row_1[0].container()",
        "_slot_b2 = _row_1[1].container()",
        "_slot_b3 = st.container(height=200)",
    ]


def test_what_goes_inside_what() -> None:
    page = _page()
    block, form, columns = page.blocks[0], page.container("c4"), page.container("c1")
    assert form is not None and columns is not None
    assert rules.check_nesting(page, block, "c2", 1) == ("c2", 1)
    assert rules.check_nesting(page, block, None) == (None, 0)
    for item, parent, slot, why in (
        (block, "c9", 0, "no container c9"),
        (block, "c1", 2, "has 2 slots"),
        (columns, "c3", 0, "does not go inside itself"),
        (page.container("c5"), "c1", 0, "sidebar is the page's own"),
        (Container("c8", "form"), "c4", 0, "form does not go inside another form"),
    ):
        with pytest.raises(rules.StreamlitError, match=why):
            rules.check_nesting(page, item, parent, slot)  # type: ignore[arg-type]
    deep = Page(
        "p",
        "Deep",
        [],
        [Container(f"c{n}", "container", parent=f"c{n - 1}" if n > 1 else None) for n in range(1, 5)],
    )
    with pytest.raises(rules.StreamlitError, match="at most 4 deep"):
        rules.check_nesting(deep, Block("b1", DOC, 1), "c4")
    # Properties are checked against the container's kind; a default is not kept; null resets.
    assert rules.check_props("columns", {"widths": [2, 1.5], "gap": "small", "border": True}) == {
        "widths": [2, 1.5],
        "border": True,
    }
    assert rules.check_props("expander", {"label": None}, {"label": "More", "expanded": True}) == {
        "expanded": True
    }
    for kind, props, why in (
        ("grid", {}, "A container is one of"),
        ("columns", {"widths": []}, "ratios"),
        ("columns", {"widths": [1, 0]}, "ratios"),
        ("tabs", {"labels": ["A", "A"]}, "each its own"),
        ("tabs", {"colour": "red"}, "no property called 'colour'"),
        ("form", {"submitted": "not a name"}, "one word"),
        ("expander", {"expanded": "yes"}, "true or false"),
        ("columns", {"gap": "huge"}, "one of: small, medium, large"),
    ):
        with pytest.raises(rules.StreamlitError, match=why):
            rules.check_props(kind, props)
    # A block whose container is gone comes up to the page; a loop is undone.
    lost = Page(
        "p", "Lost", [Block("b1", DOC, 1, parent="c9", slot=3)], [Container("c1", "tabs", parent="c1")]
    )
    rules.settle_page(lost)
    assert (lost.blocks[0].parent, lost.blocks[0].slot, lost.containers[0].parent) == (None, 0, None)


def _row(*places: tuple[int, int]) -> list[Block]:
    return [Block(f"b{n}", DOC, n, 1, column, w) for n, (column, w) in enumerate(places, start=1)]


def test_align_same_size_and_distribute_in_the_grids_units() -> None:
    def places(items: list[Block]) -> list[tuple[int, int, int]]:
        return [(i.row, i.column, i.w) for i in items]

    stack = [Block("b1", DOC, 1, 1, 3, 4), Block("b2", DOC, 2, 2, 1, 6), Block("b3", DOC, 3, 3, 7, 2)]
    assert designer.arrange(stack, "left") == ["b1", "b3"] and places(stack) == [
        (1, 1, 4),
        (2, 1, 6),
        (3, 1, 2),
    ]
    stack = [Block("b1", DOC, 1, 1, 3, 4), Block("b2", DOC, 2, 2, 1, 6), Block("b3", DOC, 3, 3, 7, 2)]
    designer.arrange(stack, "right")
    assert [i.column + i.w for i in stack] == [9, 9, 9]
    stack = [Block("b1", DOC, 1, 1, 1, 4), Block("b2", DOC, 2, 2, 1, 12), Block("b3", DOC, 3, 3, 9, 2)]
    designer.arrange(stack, "centre")
    assert [2 * i.column + i.w for i in stack] == [14, 14, 14]  # every centre on the page's middle
    assert designer.arrange(stack, "top") == ["b2", "b3"] and {i.row for i in stack} == {1}
    stack[0].row = 5
    designer.arrange(stack, "bottom")
    assert {i.row for i in stack} == {5}
    # Same size: as the first selected.
    pair = [Block("b1", DOC, 1, 1, 1, 3, 4), Block("b2", DOC, 2, 1, 11, 2, None)]
    designer.arrange(pair, "same_width")
    assert (pair[1].w, pair[1].column) == (3, 10)  # kept on the page
    designer.arrange(pair, "same_height")
    assert pair[1].h == 4
    # Distribute: equal gaps, the outer edges kept; whole columns, the extra from the left.
    row = _row((1, 2), (3, 2), (11, 2))
    assert designer.arrange(row, "distribute") == ["b2"] and [i.column for i in row] == [1, 6, 11]
    row = _row((1, 2), (4, 2), (5, 2), (11, 2))
    designer.arrange(row, "distribute")
    assert [i.column for i in row] == [1, 5, 8, 11]  # gaps of 2, 1, 1
    assert designer.even_gaps(7, 3) == [3, 2, 2] and designer.even_gaps(0, 2) == [0, 0]
    for items, how, why in (
        (row[:1], "left", "two or more"),
        (row, "diagonal", "Arrange is one of"),
        (_row((1, 2), (5, 2)), "distribute", "three or more blocks of one row"),
        ([Block("b1", DOC, 1), Block("b2", DOC, 2, parent="c1")], "left", "same container"),
        ([Block("b1", DOC, 1, locked=True), Block("b2", DOC, 2)], "left", "b1 is locked"),
    ):
        with pytest.raises(rules.StreamlitError, match=why):
            designer.arrange(items, how)


def test_the_outline_is_the_page_as_a_tree_and_reset_layout() -> None:
    page = _page()
    tree = designer.outline(page, {b.id: f"Cell {b.cell}" for b in page.blocks})
    assert [n["id"] for n in tree] == ["c1", "b5", "c4", "c6", "c7", "c5"]
    columns = tree[0]
    assert [s["name"] for s in columns["slots"]] == ["Column 1", "Column 2"]
    assert [i["id"] for i in columns["slots"][0]["items"]] == ["b1"]
    tabs = columns["slots"][1]["items"][0]
    assert (tabs["kind"], [s["name"] for s in tabs["slots"]]) == ("tabs", ["Chart", "Table"])
    assert tabs["slots"][1]["items"][0]["slots"][0]["items"][0]["title"] == "Cell 3"
    assert (tree[1]["hidden"], tree[1]["locked"], tree[3]["title"]) == (True, True, "Help box")
    designer.reset_layout(page)
    rules.settle_page(page)
    assert page.containers == [] and all(b.parent is None and not b.locked for b in page.blocks)
    assert [(b.row, b.column, b.w) for b in page.blocks][:3] == [(1, 1, 6), (1, 7, 6), (2, 1, 6)]


# ===== over HTTP =====

CELLS = [
    "# Region\nimport streamlit as st\nregion = st.selectbox('Region', ['All', 'East'], key='region_pick')",
    "# Total\nimport streamlit as st\nst.metric('Total', 5)",
    "# Note\nimport streamlit as st\nst.caption('Made up')",
]


def _built(client: TestClient, folder: Path) -> tuple[str, str]:
    path = folder / "app.ipynb"
    path.write_text(notebooks.write_notebook([notebooks.Cell("code", c) for c in CELLS]), encoding="utf-8")
    app = _canvas(client)["app"]
    _ok(client.post(f"/streamlit/apps/{app}/pages", headers=AUTH, json={"name": "Sales"}))
    return app, str(path)


def test_containers_nest_blocks_over_http(
    served: tuple[TestClient, FakeRunner],  # noqa: F811
    tmp_path: Path,
) -> None:
    client, runner = served
    app, path = _built(client, tmp_path)
    base = f"/streamlit/apps/{app}/pages/p1"

    def post(tail: str, **body: Any) -> Any:
        return client.post(f"{base}/{tail}", headers=AUTH, json=body)

    def patch(item: str, **body: Any) -> Any:
        return client.patch(f"{base}/blocks/{item}", headers=AUTH, json=body)

    made = _ok(post("containers", kind="columns", props={"widths": [1, 2]}))
    assert made["container"] == "c1"
    _ok(post("blocks", document=path, cell=1, parent="c1", slot=0, w=12))
    _ok(post("blocks", document=path, cell=2, parent="c1", slot=1, w=12))
    _ok(post("blocks", document=path, cell=3))
    tabs = _ok(post("containers", kind="tabs", parent="c1", slot=1))["container"]
    state = _ok(patch("b2", parent=tabs, slot=1))
    page = state["pages"][0]
    assert page["grids"] == {"": [["c1"], ["b3"]], "c1:0": [["b1"]], "c1:1": [["c2"]], "c2:1": [["b2"]]}
    assert page["rows"] == [["c1"], ["b3"]]
    assert [(c["id"], c["kind"], c["slots"], c["slot_names"]) for c in page["containers"]] == [
        ("c1", "columns", 2, ["Column 1", "Column 2"]),
        ("c2", "tabs", 2, ["First", "Second"]),
    ]
    assert next(b for b in page["blocks"] if b["id"] == "b2")["parent"] == "c2"
    # A container's own properties; a slot taken away brings what it held into the last one.
    assert _ok(patch("c2", props={"labels": ["Only"]}))["pages"][0]["grids"]["c2:0"] == [["b2"]]
    assert patch("c2", props={"labels": []}).status_code == 400
    # Locked: it is not moved or sized until it is unlocked; hidden is the designer's own.
    _ok(patch("b3", locked=True, hidden=True))
    refused = patch("b3", w=4)
    assert refused.status_code == 409 and "locked" in refused.text
    assert _ok(patch("b3", locked=False, w=4))["pages"][0]["blocks"][-1]["w"] == 4
    # The outline, and the page as Play writes it.
    outline = _ok(client.get(f"/streamlit/apps/{app}/outline?page=p1", headers=AUTH))["pages"][0]["tree"]
    assert [n["id"] for n in outline] == ["c1", "b3"] and outline[1]["hidden"] is True
    assert outline[0]["slots"][0]["items"][0]["title"] == "Region"
    _ok(client.post(f"/streamlit/apps/{app}/run", headers=AUTH))
    written = next(Path(runner.started[-1][1]).glob("page_p1_*.py")).read_text(encoding="utf-8")
    assert "_in_c1 = st.columns([1, 2])" in written and "_in_c2 = _in_c1[1].tabs(['Only'])" in written
    assert "_slot_b2 = _in_c2[0].container()" in written
    compile(written, "page.py", "exec")
    # A container taken off the page leaves its blocks where it was; the sidebar is one a page.
    state = _ok(client.delete(f"{base}/blocks/c1", headers=AUTH))
    assert state["pages"][0]["grids"][""][0] == ["b1", "c2"] or state["pages"][0]["grids"][""][0] == ["b1"]
    assert all(c["id"] != "c1" for c in state["pages"][0]["containers"])
    _ok(post("containers", kind="sidebar"))
    assert post("containers", kind="sidebar").status_code == 409
    assert post("containers", kind="grid").status_code == 400
    assert post("blocks", document=path, cell=1, parent="c9").status_code == 400


def test_arrange_and_reset_over_http_and_by_the_agents_commands(live: Live, tmp_path: Path) -> None:  # noqa: F811
    path = tmp_path / "app.ipynb"
    path.write_text(notebooks.write_notebook([notebooks.Cell("code", c) for c in CELLS]), encoding="utf-8")
    app = command("streamlit_open")["app"]
    page = command("streamlit_page_add", app=app, name="Sales")["page"]
    for cell, column in ((1, 3), (2, 1), (3, 7)):
        command(
            "streamlit_block_place",
            app=app,
            page=page,
            document=str(path),
            cell=cell,
            row=cell,
            column=column,
            w=4,
        )
    done = command("canvas_arrange", app=app, page=page, how="left", blocks='["b2", "b1", "b3"]')
    assert sorted(done["changed"]) == ["b1", "b3"]
    assert [b["column"] for b in done["pages"][0]["blocks"]] == [1, 1, 1]
    # The agent designs as the user does: a container, a block moved into it, the outline, the reset.
    box = command("canvas_container", app=app, page=page, kind="expander", props='{"label": "Details"}')[
        "container"
    ]
    moved = command("streamlit_block_change", app=app, page=page, block="b3", parent=box, slot=0)
    assert next(b for b in moved["pages"][0]["blocks"] if b["id"] == "b3")["parent"] == box
    tree = command("canvas_outline", app=app, page=page)["pages"][0]["tree"]
    assert tree[-1]["title"] == "Expander: Details" and tree[-1]["slots"][0]["items"][0]["id"] == "b3"
    reset = command("canvas_arrange", app=app, page=page, how="reset")
    assert reset["pages"][0]["containers"] == [] and reset["pages"][0]["grids"] == {
        "": [["b1", "b2"], ["b3"]]
    }
    with pytest.raises(Exception, match="two or more"):
        command("canvas_arrange", app=app, page=page, how="left", blocks='["b1"]')


# ===== the export runs under Streamlit's own test runner =====

FILTER = """# Region filter
import streamlit as st

region = st.selectbox("Region", ["All", "East", "West"], key="region_pick")
"""
BUTTON = """# Count
import streamlit as st

if "clicks" not in st.session_state:
    st.session_state["clicks"] = 0
pressed = st.button("Count", key="count")
st.write("clicks", st.session_state["clicks"])
"""
ECHO = """# Echo
import streamlit as st

note = st.text_input("Note", value="made up", key="note")
"""
VIEW = """# View
import streamlit as st

st.metric("Region", region)
st.caption(f"applied={applied}")
"""
SIDE = '# Side\nimport streamlit as st\n\nst.caption("In the sidebar")\n'


@needs_streamlit
def test_a_page_with_containers_an_event_and_a_binding_exports_and_runs_under_apptest(tmp_path: Path) -> None:
    # The event: Add handler writes the stub; its body is the user's. The binding: the note's value reads
    # the filter's session state key.
    button = wc.add_handler(BUTTON, 0).code.replace("    pass\n", '    st.session_state["clicks"] += 1\n')
    echo = wc.bind(ECHO, 0, "value", "state", "region_pick").code
    assert "on_click=on_count_click" in button and 'value=st.session_state["region_pick"]' in echo
    codes = {1: FILTER, 2: button, 3: echo, 4: VIEW, 5: SIDE}
    pieces = {(DOC, n): PieceCode(n, rules.cell_title(code, n), code) for n, code in codes.items()}
    page = Page(
        "p1",
        "Sales",
        [
            Block("b1", DOC, 1, 1, 1, 12, None, "c1", 0),
            Block("b2", DOC, 2, 1, 1, 12, None, "c2", 0),
            Block("b3", DOC, 3, 1, 1, 12, None, "c2", 1),
            Block("b4", DOC, 4, 1, 1, 12, None, "c3", 0),
            Block("b5", DOC, 5, 1, 1, 12, None, "c4", 0),
        ],
        [
            Container("c1", "columns", 1, 1, 12, None, None, 0, {"widths": [1, 2]}),
            Container("c2", "tabs", 1, 1, 12, None, "c1", 1, {"labels": ["Count", "Echo"]}),
            Container("c3", "form", 2, 1, 12, None, None, 0, {"submit": "Apply", "submitted": "applied"}),
            Container("c4", "sidebar"),
        ],
    )
    rules.settle_page(page)
    # The canvas's file reads back identical, and the export is made from what was read back.
    saved = rules.write_app([page])
    opened = rules.read_app(saved)
    assert opened[0].to_json() == page.to_json() and rules.write_app(opened) == saved
    made = rules.export("Sales", opened, pieces, [])
    assert made.problems == ()
    for name, text in made.files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    written = made.files["app_pages/sales.py"]
    assert "%%" not in written and "_in_c2 = _in_c1[1].tabs(['Count', 'Echo'])" in written
    script = textwrap.dedent(
        """
        import json, sys
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(sys.argv[1], default_timeout=60).run()
        first = [str(e.value) for e in at.exception]
        tabs = [t.label for t in at.tabs]
        at.button(key="count").click().run()
        at.button(key="count").click().run()
        clicks = at.session_state["clicks"]
        at.selectbox(key="region_pick").set_value("West").run()
        applied_before = [c.value for c in at.caption if c.value.startswith("applied=")]
        submit = [b for b in at.button if b.label == "Apply"][0]
        submit.click().run()
        applied_after = [c.value for c in at.caption if c.value.startswith("applied=")]
        print(json.dumps({
            "errors": first + [str(e.value) for e in at.exception],
            "tabs": tabs,
            "columns": len(at.columns),
            "clicks": clicks,
            "note": at.text_input(key="note").value,
            "metric": at.metric[0].value,
            "sidebar": [c.value for c in at.sidebar.caption],
            "applied": [applied_before, applied_after],
        }))
        """
    )
    assert STREAMLIT_PYTHON is not None
    done = subprocess.run(  # noqa: S603
        [STREAMLIT_PYTHON, "-c", script, str(tmp_path / "app_pages" / "sales.py")],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr[-3000:]
    seen = json.loads(done.stdout.strip().splitlines()[-1])
    assert seen["errors"] == []
    assert seen["tabs"] == ["Count", "Echo"] and seen["columns"] >= 2
    assert seen["clicks"] == 2  # the handler ran on each click
    assert seen["metric"] == "West" and seen["sidebar"] == ["In the sidebar"]
    assert seen["applied"] == [["applied=False"], ["applied=True"]]  # the form's button, by its name
