"""The Controllers and Text and layout families of the starter pack (docs/ideas.md, controllers and
non-data cells on the canvas, 2026-11-15). Every piece's header is checked with the rest of the Streamlit
pieces (tests/test_starters.py: what it makes and reads, its contract, each `st.` call it uses). Here:
each runs, filled, under Streamlit's own test runner (AppTest) with a made-up table and made-up
pictures; each controller does what it says (a default for a page without it, a form that refuses a
wrong range, a button that does the same twice, a pick that survives a page without its widget, a pick
in the address, a footer pinned); and Test this page finds nothing wrong on a page made of them.

Streamlit is never the app's dependency: these run in the Python named by SWISSARMYBENCH_STREAMLIT_PYTHON,
and are skipped without one, as in tests/test_starters_streamlit.py."""

from __future__ import annotations

import json
import os
import subprocess
import zlib
from pathlib import Path
from typing import Any

from swissarmybench.domain import controllers as ctl
from swissarmybench.domain import streamlit_cells as rules
from swissarmybench.domain.blades import read_blade
from swissarmybench.domain.snippets import fill
from swissarmybench.domain.streamlit_cells import Block, PieceCode
from tests.test_starters_streamlit import PYTHON, TABLE, _run, _script, needs_streamlit

FOLDER = Path(__file__).resolve().parents[1] / "src" / "swissarmybench" / "starters"
CONTROLLERS = {
    p["name"]: p
    for p in (read_blade(f.read_text(encoding="utf-8")) for f in FOLDER.glob("controller_*.blade.py"))
}
LAYOUT = {
    p["name"]: p for p in (read_blade(f.read_text(encoding="utf-8")) for f in FOLDER.glob("page_*.blade.py"))
}
VALUES = {"table": "orders", "column": "region", "value column": "amount"}


def _filled(piece: dict[str, Any], **values: str) -> str:
    return fill(piece["code"], "streamlit", VALUES | values)


def _png() -> bytes:
    """A made-up 2x2 picture (PNG), written by hand."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return len(data).to_bytes(4, "big") + body + zlib.crc32(body).to_bytes(4, "big")

    pixels = b"".join(b"\x00" + b"\x20\x60\xa0" * 2 for _ in range(2))
    head = (2).to_bytes(4, "big") * 2 + bytes([8, 2, 0, 0, 0])
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", head)
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


def _apptest(folder: Path, page: str, steps: str) -> Any:
    """Run `steps` (Python, with `at` an AppTest of `page`) in the Streamlit Python; what it prints last."""
    (folder / "page.py").write_text(page, encoding="utf-8")
    script = (
        "import json\nfrom streamlit.testing.v1 import AppTest\n"
        "at = AppTest.from_file('page.py', default_timeout=60).run()\nout = {}\n"
        + steps
        + "\nprint(json.dumps(out, default=str))\n"
    )
    done = subprocess.run(  # noqa: S603 (the tester's Streamlit Python, on files this test wrote)
        [str(PYTHON), "-I", "-c", script],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=folder,
        env=os.environ | {"STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"},
    )
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_families_have_their_pieces_and_the_controllers_their_contracts() -> None:
    assert sorted(CONTROLLERS) == [
        "Controller action button",
        "Controller cross-page filter",
        "Controller filter with defaults",
        "Controller form with validation",
        "Controller query parameter filter",
    ]
    assert len(LAYOUT) == 9
    roles = {name: ctl.describe(_filled(p)).role for name, p in CONTROLLERS.items()}
    assert roles == {
        "Controller action button": "action",
        "Controller cross-page filter": "filter",
        "Controller filter with defaults": "filter",
        "Controller form with validation": "filter",
        "Controller query parameter filter": "filter",
    }
    made = ctl.describe(_filled(CONTROLLERS["Controller filter with defaults"])).makes
    assert [(m.name, m.type, m.default) for m in made] == [
        ("region", "str", "'All'"),
        ("by_region", "table", "orders"),
    ]
    asked = ctl.describe(_filled(CONTROLLERS["Controller query parameter filter"]))
    assert asked.params == ("region",)  # read through a name the cell gives a text
    assert {ctl.describe(_filled(p)).role for p in LAYOUT.values()} == {"view"}


@needs_streamlit
def test_every_piece_runs_under_streamlits_own_test_runner(tmp_path: Path) -> None:
    for name in ("logo.png", "picture.png"):
        (tmp_path / name).write_bytes(_png())
    pieces = {**CONTROLLERS, **LAYOUT}
    scripts = {name: _script(_filled(piece)) for name, piece in pieces.items()}
    problems = {name: found for name, found in _run(scripts, tmp_path).items() if found}
    assert problems == {}
    assert len(scripts) == 14


@needs_streamlit
def test_a_view_runs_on_the_filters_defaults_when_the_filter_is_not_on_its_page(tmp_path: Path) -> None:
    filter_code = _filled(CONTROLLERS["Controller filter with defaults"])
    view = "# Total\nimport streamlit as st\nst.metric(f'Total ({region})', int(by_region['amount'].sum()))\n"
    codes = {("n", 1): filter_code, ("n", 2): view}
    where = {key: f"n @cell{key[1]}" for key in codes}
    page = rules.Page("p1", "P", [Block("b2", "n", 2, 1, 1, 12)])
    made = rules.page_code(
        "P",
        page.blocks,
        {("n", 2): PieceCode(2, "Total", view, "n @cell2")},
        [],
        elsewhere=rules.elsewhere(page, {k: rules.facts(v) for k, v in codes.items()}, where),
        fallbacks=ctl.fallbacks([("n", 2)], codes, {("n", 1): "Region filter"}, where),
    )
    found = _apptest(tmp_path, TABLE + made.code, "out['metric'] = [m.label for m in at.metric]")
    assert found == {"metric": ["Total (All)"]}


@needs_streamlit
def test_the_form_refuses_a_wrong_range_and_keeps_the_rows_it_had(tmp_path: Path) -> None:
    page = TABLE + _filled(CONTROLLERS["Controller form with validation"], name="in_range")
    steps = """
out['first'] = at.caption[0].value
at.number_input(key='in_range_low').set_value(80.0)
at.number_input(key='in_range_high').set_value(20.0)
for b in at.button:
    b.click()
at.run()
out['wrong'] = [e.value for e in at.error]
out['kept'] = at.caption[0].value
at.number_input(key='in_range_low').set_value(20.0)
at.number_input(key='in_range_high').set_value(50.0)
for b in at.button:
    b.click()
at.run()
out['right'] = [e.value for e in at.error]
out['now'] = at.caption[0].value
"""
    found = _apptest(tmp_path, page, steps)
    assert found["first"].startswith("40 rows from ")
    assert found["wrong"] == ["From (80.00) is more than To (20.00): swap them."]
    assert found["kept"] == found["first"]
    assert found["right"] == [] and found["now"] != found["first"] and "from 20.00 to 50.00" in found["now"]


@needs_streamlit
def test_the_action_button_puts_the_filter_back_and_twice_is_once(tmp_path: Path) -> None:
    picked = _filled(CONTROLLERS["Controller filter with defaults"])
    button = _filled(CONTROLLERS["Controller action button"], **{"widget keys": "by_region_pick"})
    steps = """
at.selectbox(key='by_region_pick').set_value('South').run()
out['picked'] = at.selectbox(key='by_region_pick').value
at.button(key='clear_filters_button').click().run()
out['once'] = at.selectbox(key='by_region_pick').value
at.button(key='clear_filters_button').click().run()
out['twice'] = at.selectbox(key='by_region_pick').value
out['errors'] = [str(e.value) for e in at.exception]
"""
    found = _apptest(tmp_path, TABLE + picked + "\n" + button, steps)
    assert found == {"picked": "South", "once": "All", "twice": "All", "errors": []}


@needs_streamlit
def test_the_cross_page_pick_survives_a_page_without_its_widget(tmp_path: Path) -> None:
    piece = _filled(CONTROLLERS["Controller cross-page filter"])
    # Another page stood in for: a run in which the filter's widget is not drawn at all.
    page = TABLE + "import streamlit as st\n\nif st.toggle('This page', value=True, key='here'):\n"
    page += rules.indented(piece) + "\nst.write(f'Picked: {st.session_state.get(\"every_page_region\")}')\n"
    steps = """
at.selectbox(key='by_region_pick').set_value('East').run()
at.toggle(key='here').set_value(False).run()
out['away'] = [m.value for m in at.markdown]
at.toggle(key='here').set_value(True).run()
out['back'] = at.selectbox(key='by_region_pick').value
"""
    found = _apptest(tmp_path, page, steps)
    assert found == {"away": ["Picked: East"], "back": "East"}


@needs_streamlit
def test_the_query_parameter_filter_opens_from_the_address_and_writes_it(tmp_path: Path) -> None:
    page = TABLE + _filled(CONTROLLERS["Controller query parameter filter"])
    steps = """
from streamlit.testing.v1 import AppTest
asked = AppTest.from_file('page.py', default_timeout=60)
asked.query_params['region'] = 'West'
asked.run()
out['asked'] = asked.selectbox(key='by_region_pick').value
odd = AppTest.from_file('page.py', default_timeout=60)
odd.query_params['region'] = 'Nowhere'
odd.run()
out['odd'] = [odd.selectbox(key='by_region_pick').value, dict(odd.query_params)]
out['odd'].append([str(e.value) for e in odd.exception])
at.selectbox(key='by_region_pick').set_value('North').run()
out['written'] = dict(at.query_params)
"""
    found = _apptest(tmp_path, page, steps)
    assert found["asked"] == "West"
    assert found["odd"] == ["All", {}, []]
    assert found["written"] == {"region": "North"}


@needs_streamlit
def test_the_footer_says_its_source_and_pins_itself_only_when_asked(tmp_path: Path) -> None:
    footer = LAYOUT["Page footer"]
    steps = "out['said'] = [c.value for c in at.caption]\nout['style'] = [h.proto.body for h in at.html]"
    pinned = _apptest(tmp_path, TABLE + _filled(footer), steps)
    assert pinned["said"][0].startswith("Source: Made-up sales data · 40 rows · read ")
    assert "position: fixed" in pinned["style"][0] and ".st-key-page_footer" in pinned["style"][0]
    loose = _apptest(tmp_path, TABLE + _filled(footer, **{"pin to the bottom": "no"}), steps)
    assert loose["style"] == []


@needs_streamlit
def test_test_this_page_finds_nothing_wrong_on_a_page_of_controllers(tmp_path: Path) -> None:
    codes = [
        _filled(CONTROLLERS["Controller filter with defaults"]),
        _filled(CONTROLLERS["Controller form with validation"], table="by_region", name="in_range"),
        _filled(CONTROLLERS["Controller action button"], **{"widget keys": "by_region_pick, in_range_low"}),
        _filled(CONTROLLERS["Controller query parameter filter"], column="product", name="by_product"),
        "# Total\nimport streamlit as st\nst.metric('Total', round(float(in_range['amount'].sum()), 2))\n",
        _filled(LAYOUT["Page footer"], table="in_range"),
    ]
    placed = [Block(f"b{i}", "n", i, i, 1, 12) for i in range(1, len(codes) + 1)]
    pieces = {
        b.key: PieceCode(b.cell, rules.cell_title(code, b.cell), code, f"n @cell{b.cell}")
        for b, code in zip(placed, codes, strict=True)
    }
    made = rules.page_code("P", placed, pieces, [], record=True)
    assert made.problems == ()
    (tmp_path / "page.py").write_text(made.code.replace("# P\n", "# P\n" + TABLE, 1), encoding="utf-8")
    plan = ctl.test_plan(
        [(b.id, pieces[b.key].name, rules.keyed(rules.body(pieces[b.key].code), b.id)) for b in placed]
    )
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    done = subprocess.run(  # noqa: S603 (the tester's Streamlit Python, on files this test wrote)
        [str(PYTHON), "-I", "-c", ctl.RUNNER, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=tmp_path,
    )
    found = ctl.read_results(done.stdout, plan, [b.id for b in placed])
    assert found.problem is None, done.stderr[-2000:]
    assert found.failures == {} and found.outside == [] and found.tries > 10
    assert found.untried == []
