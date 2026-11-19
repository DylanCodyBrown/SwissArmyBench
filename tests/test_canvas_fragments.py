"""Fragments in a canvas's pages (docs/research/app-builders-2026-11.md, items 1 and 3; 2026-11-19): a
block whose widgets feed only itself runs as an st.fragment, so a change of its widget reruns it alone; a
widget that feeds another block keeps the whole-page rerun. Its query blocks are cached by default
(tests/test_canvas_queries.py). With a Python that has Streamlit, AppTest proves it: a fragment's widget changes, another block does not run
again (a made-up counter in session state). Made-up data only."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

from swissarmybench_streamlit.domain import streamlit_cells as rules
from swissarmybench_streamlit.domain.streamlit_cells import Block, Container, Page, PieceCode
from tests.test_streamlit_apps import STREAMLIT_PYTHON, needs_streamlit

DOC = "/work/app.ipynb"
ZOOM = '# Zoom\nzoom = st.slider("Zoom", 1, 10, 3, key="zoom")\nst.write(f"zoomed {zoom * 2}")'
COUNT = '# Count\nst.session_state["runs"] = st.session_state.get("runs", 0) + 1\nst.write("counted")'
PICK = '# Pick\npick = st.selectbox("Pick", ["East", "West"], key="pick")'
SHOW = '# Show\nst.write(f"picked {pick}")'
PIECES = {
    (DOC, 1): PieceCode(1, "Zoom", ZOOM),
    (DOC, 2): PieceCode(2, "Count", COUNT),
    (DOC, 3): PieceCode(3, "Pick", PICK),
    (DOC, 4): PieceCode(4, "Show", SHOW),
}


def _page(containers: list[Container] | None = None, parent: str | None = None) -> Page:
    blocks = [
        Block("b1", DOC, 1, 1, 1, 6, None, parent),
        Block("b2", DOC, 2, 1, 7, 6),
        Block("b3", DOC, 3, 2, 1, 6),
        Block("b4", DOC, 4, 2, 7, 6),
    ]
    page = Page("p1", "Overview", blocks, containers or [])
    rules.settle_page(page)
    return page


def _facts(page: Page) -> tuple[dict[str, rules.Facts], dict[str, str]]:
    codes = {b.id: PIECES[b.key].code for b in page.blocks}
    return {i: rules.facts(c) for i, c in codes.items()}, codes


def test_a_block_whose_widgets_feed_only_itself_is_a_fragment() -> None:
    page = _page()
    found, codes = _facts(page)
    # Zoom's slider feeds only Zoom; Pick's select feeds Show (the whole page reruns); Count has no widget.
    assert rules.fragment_blocks(page.blocks, found, codes) == {"b1"}
    # In a form or the sidebar, Streamlit keeps a fragment's widgets out: no fragment.
    for kind in ("form", "sidebar"):
        boxed = _page([Container("c1", kind, 1, 1, 12)], parent="c1")
        found, codes = _facts(boxed)
        assert rules.fragment_blocks(boxed.blocks, found, codes, boxed.containers) == set()
    # A tab is no wall.
    tabbed = _page([Container("c1", "tabs", 1, 1, 12, props={"labels": ["A"]})], parent="c1")
    found, codes = _facts(tabbed)
    assert rules.fragment_blocks(tabbed.blocks, found, codes, tabbed.containers) == {"b1"}
    # Code that cannot be a function's body stays as it is.
    odd = {"b1": ZOOM + "\nfrom math import *"}
    assert rules.fragment_blocks(page.blocks[:1], {"b1": rules.facts(odd["b1"])}, odd) == set()
    # A block that reads a name before it makes it (zoom = zoom + z) would read a local not set yet: none.
    again = {"b1": 'z = st.slider("Z", 1, 5)\nzoom = zoom + z'}
    assert rules.fragment_blocks(page.blocks[:1], {"b1": rules.facts(again["b1"])}, again) == set()


def test_the_page_runs_a_fragment_in_its_own_slot() -> None:
    made = rules.page_code("Overview", _page().blocks, PIECES, [], guard=False)
    assert made.fragments == ("b1",)
    assert "@st.fragment\ndef _sab_part_b1():" in made.code
    assert "with _slot_b1:\n    _sab_part_b1()" in made.code
    assert "@st.fragment\ndef _sab_part_b3" not in made.code  # Pick feeds Show
    compile(made.code, "page.py", "exec")
    plain = rules.page_code("Overview", _page().blocks, PIECES, [], guard=False, fragments=False)
    assert "st.fragment" not in plain.code and plain.fragments == ()


FRAGMENT_TEST = textwrap.dedent(
    """
    import functools, json, sys
    from streamlit.runtime.scriptrunner import RerunData
    import streamlit.testing.v1.local_script_runner as runner
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(sys.argv[1], default_timeout=60).run()
    first = at.session_state["runs"]
    errors = [str(e.value) for e in at.exception]
    # What the browser asks when a fragment's widget changes: a rerun of that fragment alone.
    parts = list(at._fragment_storage._fragments)
    plain = runner.RerunData
    runner.RerunData = functools.partial(plain, fragment_id_queue=parts, is_fragment_scoped_rerun=True)
    at.slider(key="zoom").set_value(7).run()
    after_zoom = at.session_state["runs"]
    zoomed = [m.value for m in at.markdown if "zoomed" in m.value]
    runner.RerunData = plain
    at.run()  # the whole page again (a fragment rerun's tree holds only the fragment)
    at.selectbox(key="pick").set_value("West").run()
    after_pick = at.session_state["runs"]
    errors += [str(e.value) for e in at.exception]
    picked = [m.value for m in at.markdown if "picked" in m.value]
    print(json.dumps({"parts": len(parts), "runs": [first, after_zoom, after_pick], "zoomed": zoomed,
                      "picked": picked, "errors": errors}))
    """
)


@needs_streamlit
def test_a_fragments_widget_does_not_run_another_block_again(tmp_path: Path) -> None:
    made = rules.export("Overview", [_page()], PIECES, [])
    for name, text in made.files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    assert STREAMLIT_PYTHON is not None
    done = subprocess.run(  # noqa: S603 (a Python with Streamlit, our own test)
        [STREAMLIT_PYTHON, "-c", FRAGMENT_TEST, str(tmp_path / "app_pages" / "overview.py")],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr[-3000:]
    seen = json.loads(done.stdout.strip().splitlines()[-1])
    assert seen["errors"] == [] and seen["parts"] == 1
    # Zoom's change reran Zoom alone (Count did not run again); Pick's reran the page.
    assert seen["runs"] == [1, 1, 3]
    assert seen["zoomed"] == ["zoomed 14"] and seen["picked"] == ["picked West"]
