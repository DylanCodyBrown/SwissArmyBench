"""Controllers (docs/ideas.md, "After the beta: controllers", 2026-11-15): a cell's contract (its header's
Makes line, read by Python's parser), its role, the page's defaults when a maker is not on it, the check
(a contract its code does not keep, a name made twice, a cycle named), and Test this page's plan, runner
and answer. The runner runs under Streamlit's AppTest in a Python that has it (the tests' stand-in for
the app's Python: SWISSARMYBENCH_STREAMLIT_PYTHON), else those tests are skipped."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

from swissarmybench.domain import controllers as ctl
from swissarmybench.domain import streamlit_cells as rules
from swissarmybench.domain.streamlit_cells import Block, Fallback, PieceCode
from tests.test_starters_streamlit import PYTHON, needs_streamlit

FILTER = """# Region filter
# Makes: region: str = "All"; by_region: table = orders
import streamlit as st

region = st.selectbox("Region", ["All", *sorted(orders["region"].unique())], key="region_pick")
by_region = orders if region == "All" else orders[orders["region"] == region]
"""
VIEW = """# Sales by product
import streamlit as st

st.bar_chart(by_region.groupby("product")["amount"].sum())
st.caption(f"Region: {region}")
"""


# ===== a cell's contract =====


def test_the_makes_line_is_read_with_types_and_defaults() -> None:
    found = ctl.describe(FILTER)
    assert [m.to_json() for m in found.makes] == [
        {"name": "region", "type": "str", "default": "'All'", "declared": True},
        {"name": "by_region", "type": "table", "default": "orders", "declared": True},
    ]
    assert found.role == "filter" and found.problems == () and found.declared
    assert found.widgets[0].to_json() == {
        "kind": "selectbox",
        "key": "region_pick",
        "label": "Region",
        "form": False,
        "callback": False,
    }


def test_plain_names_nothing_and_words_after_them_are_contracts_too() -> None:
    # The starter pieces' headers: names only, "nothing", and a few words in brackets.
    plain = (
        "# Makes: by_region\nimport streamlit as st\nby_region = orders[orders.region == st.text_input('R')]"
    )
    assert [(m.name, m.type, m.default) for m in ctl.describe(plain).makes] == [("by_region", "", None)]
    words = "# Makes: a, b (the pick, the rows)\nimport streamlit as st\na = st.toggle('x')\nb = 1"
    assert [m.name for m in ctl.describe(words).makes] == ["a", "b"] and not ctl.describe(words).problems
    shows = "# Makes: nothing (it only shows)\nimport streamlit as st\nst.write(orders)"
    assert ctl.describe(shows).makes == () and ctl.describe(shows).role == "view"
    # Without a Makes line the names come from the code, undeclared.
    bare = "import streamlit as st\npick = st.radio('P', ['a', 'b'])\n_own = 1"
    assert [m.to_json() for m in ctl.describe(bare).makes] == [
        {"name": "pick", "type": "", "default": None, "declared": False}
    ]


def test_a_contract_its_code_does_not_keep_says_so() -> None:
    def problems(line: str) -> tuple[str, ...]:
        return ctl.describe(
            f"# Makes: {line}\nimport streamlit as st\nregion = st.text_input('R')\n"
        ).problems

    assert problems('region: str = "All"') == ()
    assert problems("region: colour") == (
        "region's type is one of str, int, float, bool, date, list, table, any.",
    )
    assert problems("region: int = 'All'") == ("region's default 'All' is not a int.",)
    assert problems("region: str = DEFAULT") == (
        "region's default is a plain value: only a table's is a name.",
    )
    assert problems("region: str = len('x')") == (
        "region's default is a plain value (a text, a number, True, a list).",
    )
    assert problems("region: table = 'orders'") == (
        "region is a table: its default is a table's name (orders).",
    )
    assert problems("region; area: str = 'x'") == ("The Makes line names area, which the cell never makes.",)
    assert problems("region: str = (") == (
        "The Makes line is `name: type = default`, a `;` between: region: str = (",
    )
    # A float takes a whole number; a date is text in the ISO form, written as a date on the page.
    made = ctl.describe("# Makes: least: float = 0; since: date = '2026-01-31'\nleast = 1.0\nsince = 2").makes
    assert [(m.type, m.default) for m in made] == [("float", "0.0"), ("date", "_sab_date(2026, 1, 31)")]


def test_the_role_is_said_or_read_from_the_code() -> None:
    action = "import streamlit as st\ndef _go():\n    print(1)\nst.button('Go', on_click=_go)"
    assert ctl.describe(action).role == "action"
    assert ctl.describe(VIEW).role == "view"
    assert ctl.describe("total = orders['amount'].sum()").role == ""
    said = "# Role: action\nimport streamlit as st\nx = st.toggle('x')"
    assert ctl.describe(said).role == "action"
    assert ctl.describe("# Role: boss\nx = 1").problems == ("The Role line is one of filter, action, view.",)


def test_widgets_in_a_form_with_callbacks_and_the_query_parameters_read() -> None:
    code = """import streamlit as st
with st.form("f"):
    least = st.number_input("Least", value=0.0, key="least")
    sent = st.form_submit_button("Show")
st.button("Clear", on_click=print, key="clear")
region = st.query_params.get("region", "All")
if "area" in st.query_params:
    area = st.query_params["area"]
"""
    shown = [(w.kind, w.key, w.label, w.form, w.callback) for w in ctl.widgets(code)]
    assert shown == [
        ("number_input", "least", "Least", True, False),
        ("form_submit_button", None, "Show", True, False),
        ("button", "clear", "Clear", False, True),
    ]
    assert ctl.params(code) == ["region", "area"]


# ===== the page: defaults when the maker is not on it, the check =====

KEYS = {("n.ipynb", 1): FILTER, ("n.ipynb", 2): VIEW}
WHERE = {("n.ipynb", 1): "n.ipynb @cell1", ("n.ipynb", 2): "n.ipynb @cell2"}


def _page(*cells: int, fallen: bool = True, record: bool = False) -> rules.PageCode:
    placed = [Block(f"b{c}", "n.ipynb", c, i + 1, 1, 12) for i, c in enumerate(cells)]
    pieces = {
        key: PieceCode(key[1], rules.cell_title(code, key[1]), code, WHERE[key]) for key, code in KEYS.items()
    }
    found = {key: rules.facts(code) for key, code in KEYS.items()}
    page = rules.Page("p1", "Page 1", placed)
    titles = {key: piece.name for key, piece in pieces.items()}
    fallbacks = ctl.fallbacks([b.key for b in placed], KEYS, titles, WHERE) if fallen else None
    return rules.page_code(
        "Page 1",
        placed,
        pieces,
        ["orders"],
        elsewhere=rules.elsewhere(page, found, WHERE),
        fallbacks=fallbacks,
        record=record,
    )


def test_a_view_whose_maker_is_not_on_the_page_uses_the_default_and_says_so() -> None:
    made = _page(2)
    assert made.problems == () and made.defaulted == (("b2", "by_region"), ("b2", "region"))
    assert "region = 'All'  # Region filter, n.ipynb @cell1" in made.code
    assert "by_region = orders  # Region filter, n.ipynb @cell1" in made.code
    assert made.tables == ("orders",)  # the table default is read by the page
    ast.parse(made.code)
    # Without the maker's contract the page says where the maker is, as before.
    plain = _page(2, fallen=False)
    assert (
        plain.defaulted == () and "which is not on this page: place that cell here too" in plain.problems[0]
    )
    # With the maker on the page its own names run: no default.
    both = _page(1, 2)
    assert both.defaulted == () and "region = 'All'" not in both.code


def test_the_check_names_defaults_contract_problems_twice_made_names_and_cycles() -> None:
    made = _page(2)
    fallen = ctl.fallbacks([("n.ipynb", 2)], KEYS, {("n.ipynb", 1): "Region filter"}, WHERE)
    check = ctl.check_page([("b2", VIEW)], made, fallen)
    assert check.block("b2").defaults == (
        ("by_region", "orders", "Region filter, n.ipynb @cell1"),
        ("region", "'All'", "Region filter, n.ipynb @cell1"),
    )
    a = "# Makes: x: int = 1\nx = y + 1"
    b = "y = x * 2"
    c = "x = 3"
    looped = ctl.check_page([("b1", a), ("b2", b)], rules.PageCode("", (), (), ()), {})
    assert looped.to_json()["cycles"] == [{"blocks": ["b1", "b2"], "names": ["x", "y"]}]
    twice = ctl.check_page([("b1", a), ("b3", c)], rules.PageCode("", (), (), ()), {})
    assert twice.to_json()["twice"] == [{"name": "x", "blocks": ["b1", "b3"]}]
    broken = ctl.check_page([("b1", "# Makes: z\nx = 1")], rules.PageCode("", (), (), ()), {})
    assert broken.to_json()["blocks"] == [
        {"block": "b1", "defaults": [], "problems": ["The Makes line names z, which the cell never makes."]}
    ]


def test_a_date_default_is_written_as_a_date() -> None:
    since = "# Since filter\n# Makes: since: date = '2026-01-31'\nimport streamlit as st\n"
    since += "since = st.date_input('S')"
    reader = "import streamlit as st\nst.write(since)"
    codes = {("a", 1): since, ("a", 2): reader}
    where = {("a", 1): "a @cell1", ("a", 2): "a @cell2"}
    fallen = ctl.fallbacks([("a", 2)], codes, {("a", 1): "Since filter"}, where)
    assert fallen == {"since": Fallback("_sab_date(2026, 1, 31)", "Since filter, a @cell1", None)}
    page = rules.Page("p", "P", [Block("b2", "a", 2, 1, 1, 12)])
    made = rules.page_code(
        "P",
        page.blocks,
        {("a", 2): PieceCode(2, "Reader", reader, "a @cell2")},
        [],
        elsewhere=rules.elsewhere(page, {k: rules.facts(v) for k, v in codes.items()}, where),
        fallbacks=fallen,
    )
    assert "from datetime import date as _sab_date\nsince = _sab_date(2026, 1, 31)" in made.code


def test_a_page_written_for_a_test_records_each_blocks_error() -> None:
    made = _page(2, record=True)
    assert made.code.split("\n")[1:4] == [
        "import streamlit as st",
        "",
        "st.session_state['_sab_failures'] = {}",
    ]
    assert "st.session_state['_sab_failures']['b2'] = f\"{type(_error).__name__}: {_error}\"" in made.code
    ast.parse(made.code)
    gone = rules.page_code("P", [Block("b9", "x", 9, 1, 1, 12)], {}, [], record=True)
    assert "st.session_state['_sab_failures']['b9'] = 'Cell 9 is gone" in gone.code


# ===== Test this page =====


def test_the_plan_tries_each_keyed_widget_and_query_parameter() -> None:
    code = rules.keyed(
        rules.body(FILTER) + "\nlimit = st.slider('Limit', 1, 9)\nst.text_input(f'{x}', key=f'k{x}')", "b1"
    )
    code += "\nr = st.query_params.get('region')"
    plan = ctl.test_plan([("b1", "Region filter", code)])
    assert [(w["key"], w["kind"], w["label"]) for w in plan["widgets"]] == [
        ("region_pick", "selectbox", "Region"),
        ("b1_1", "slider", "Limit"),
    ]
    assert plan["params"] == [{"block": "b1", "name": "Region filter", "param": "region"}]
    assert plan["untried"] == ["Region filter: text_input (its key is worked out as it runs)"]
    assert plan["record"] == "_sab_failures" and plan["answer"] == ctl.ANSWER


def test_the_answer_lands_on_the_blocks_that_failed_once_each() -> None:
    said = {
        "runs": 5,
        "tries": 4,
        "stopped": False,
        "skipped": ["x"],
        "cases": [
            {"case": "Region filter: Region = 'South'", "failures": {"b2": "KeyError: 'South'"}, "page": []},
            {"case": "Region filter: Region = 'East'", "failures": {"b2": "KeyError: 'South'"}, "page": []},
            {"case": "As the page opens", "failures": {"zz": "nope"}, "page": ["FileNotFoundError: data"]},
        ],
    }
    out = ctl.read_results("noise\n" + ctl.ANSWER + json.dumps(said), {"untried": ["u"]}, ["b1", "b2"])
    assert out.to_json() == {
        "runs": 5,
        "tries": 4,
        "failed": 2,
        "failures": {"b2": [{"case": "Region filter: Region = 'South'", "error": "KeyError: 'South'"}]},
        "page": [{"case": "As the page opens", "error": "FileNotFoundError: data"}],
        "untried": ["u", "x"],
        "stopped": False,
        "problem": None,
    }
    assert ctl.read_results("Traceback: ModuleNotFoundError", {}, []).problem == (
        "The test did not finish: Traceback: ModuleNotFoundError"
    )


@needs_streamlit
def test_the_runner_tries_each_value_and_finds_the_block_that_fails(tmp_path: Path) -> None:
    table = (
        "import pandas as pd\n"
        "orders = pd.DataFrame({'region': ['North', 'South', 'East'] * 3, 'product': list('abc') * 3,"
        " 'amount': [1.0, 2.0, 3.0] * 3})\n"
    )
    view = """# Sales by product
import streamlit as st

if region == "East":
    raise KeyError("East")
st.bar_chart(by_region.groupby("product")["amount"].sum())
"""
    action = """# Refresh
import streamlit as st

def _go():
    st.session_state["refreshed"] = True

st.button("Refresh", on_click=_go, key="refresh")
"""
    codes = {("n", 1): FILTER, ("n", 2): view, ("n", 3): action}
    placed = [Block(f"b{c}", "n", c, c, 1, 12) for c in (1, 2, 3)]
    pieces = {k: PieceCode(k[1], rules.cell_title(v, k[1]), v, f"n @cell{k[1]}") for k, v in codes.items()}
    made = rules.page_code("P", placed, pieces, [], record=True)
    (tmp_path / "page.py").write_text(made.code.replace("# P\n", "# P\n" + table, 1), encoding="utf-8")
    keyed = [(b.id, pieces[b.key].name, rules.keyed(rules.body(pieces[b.key].code), b.id)) for b in placed]
    plan = ctl.test_plan(keyed)
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    done = subprocess.run(  # noqa: S603 (the tester's Streamlit Python, on files this test wrote)
        [str(PYTHON), "-I", "-c", ctl.RUNNER, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=tmp_path,
    )
    found = ctl.read_results(done.stdout, plan, [b.id for b in placed])
    assert found.problem is None, done.stderr[-2000:]
    assert found.failures == {"b2": [{"case": "Region filter: Region = 'East'", "error": "KeyError: 'East'"}]}
    assert found.page == [] and found.tries == 6  # All, North, South, East; Refresh twice
    assert PYTHON is not None


def test_the_runner_is_python() -> None:
    ast.parse(ctl.RUNNER)
