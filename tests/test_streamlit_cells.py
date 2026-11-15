"""Streamlit cells (docs/ideas.md, 2026-11-15): the cell in a notebook file and in a script, both
ways, with the saved pages and their layouts; the names each piece makes and reads, the run order and a
cycle; the page as one Streamlit page (slots first, pieces in name order, keys of their own); the
tables a page names; the export folder's files. Made-up data only."""

from __future__ import annotations

import ast
import json

import pytest

from swissarmygrid.client import table_cells as kernel_side
from swissarmygrid.domain import notebooks, table_cells
from swissarmygrid.domain import streamlit_cells as rules
from swissarmygrid.domain.streamlit_cells import Page, PieceCode, Placed

FILTER = '# Region filter\nregion = st.selectbox("Region", sorted(orders["region"].unique()))'
TOTAL = '# Total\nst.metric("Total", int(orders[orders["region"] == region]["amount"].sum()))'
CHART = "# Chart\nimport altair as alt\nst.altair_chart(alt.Chart(orders).mark_bar())"

PIECES = {4: PieceCode(4, "Region filter", FILTER), 5: PieceCode(5, "Total", TOTAL)}

# ===== the cell in a file, both ways =====


def test_a_notebook_streamlit_cell_is_a_marked_code_cell_and_reads_back() -> None:
    cells = [
        notebooks.Cell("code", "import pandas as pd"),
        notebooks.Cell("streamlit", FILTER, height=320),
        notebooks.Cell("streamlit", TOTAL),
    ]
    pages = [Page("p1", "Sales overview", [Placed("s1", 3, 12), Placed("s2", 2, 4, 5)])]
    text = notebooks.write_notebook(cells, pages=pages)
    raw = json.loads(text)
    # In the file: a code cell whose first line is a comment, so plain Jupyter runs it as Python.
    assert raw["cells"][1]["cell_type"] == "code"
    assert "".join(raw["cells"][1]["source"]) == f"# %% [streamlit]\n{FILTER}"
    assert raw["cells"][1]["metadata"]["swissarmygrid"] == {"kind": "streamlit", "height": 320, "number": 2}
    ast.parse("".join(raw["cells"][1]["source"]))
    assert raw["metadata"]["swissarmygrid"]["streamlit"]["pages"] == [
        {
            "id": "p1",
            "name": "Sales overview",
            "pieces": [{"id": "s1", "cell": 3, "w": 12, "h": None}, {"id": "s2", "cell": 2, "w": 4, "h": 5}],
        }
    ]
    back, _ = notebooks.read_document(text)
    assert [(c.kind, c.source, c.height, c.number) for c in back] == [
        ("code", "import pandas as pd", None, 1),
        ("streamlit", FILTER, 320, 2),
        ("streamlit", TOTAL, None, 3),
    ]
    assert notebooks.document_pages(text) == rules.pages_json(pages)
    # A notebook with no pages keeps no word about them, and one from plain Jupyter has none.
    assert "streamlit" not in json.loads(notebooks.write_notebook(cells))["metadata"]["swissarmygrid"]
    assert notebooks.document_pages('{"cells": [], "nbformat": 4}') == []
    assert notebooks.document_pages("not a notebook") == []


def test_the_page_sends_streamlit_cells_and_they_are_checked() -> None:
    sent = [{"kind": "streamlit", "source": FILTER, "height": 5000}]
    assert notebooks.read_cells(sent)[0].height == 2000
    with pytest.raises(notebooks.NotebookError, match="streamlit"):
        notebooks.read_cells([{"kind": "dash", "source": ""}])
    assert notebooks.code_of(notebooks.Cell("streamlit", "x = 1")) == "# %% [streamlit]\nx = 1"


SCRIPT = f"""import pandas as pd

# %% [4] [streamlit] height=300
{FILTER}
# %% [5] [streamlit]
{TOTAL}
# %% [6]
print("plain")
"""


def test_a_script_streamlit_cell_is_plain_python_under_its_marker() -> None:
    ast.parse(SCRIPT)  # the file still runs as Python
    script = table_cells.parse_script(SCRIPT)
    found = [(c.number, c.kind, c.streamlit, c.height) for c in script.cells if not c.fixed]
    assert found == [(4, "streamlit", True, 300), (5, "streamlit", True, None), (6, "code", False, None)]
    assert rules.script_pieces(SCRIPT) == [(4, FILTER + "\n"), (5, TOTAL + "\n")]
    # Arranged with no tables, the file comes back as it was: markers, heights and all.
    again, arrangement = table_cells.arrange_script(SCRIPT, [])
    assert again == SCRIPT and arrangement.tables == []
    outline = table_cells.outline(SCRIPT)
    assert [(c["kind"], c["number"], c["height"]) for c in outline["cells"]] == [
        ("streamlit", 4, 300),
        ("streamlit", 5, None),
        ("code", 6, None),
    ]


def test_a_streamlit_cell_is_never_the_cell_that_makes_a_table() -> None:
    # It gives `orders` a value, and no other cell does: it still stays where it is, with its uses line.
    script = "# %% [4] [streamlit]\norders = orders.dropna()\nst.dataframe(orders)\n"
    spec = table_cells.TableSpec("orders", "# orders: no steps", "# load\n# orders: no steps")
    text, arrangement = table_cells.arrange_script(script, [spec])
    assert arrangement.tables[0].maker is None
    assert "# %% [4] [streamlit]\n# uses orders @cell" in text
    plan = [table_cells.PlanCell(4, "streamlit", "orders = orders.dropna()")]
    done = table_cells.arrange(plan, [spec], 5)
    piece = next(c for c in done.cells if c.number == 4)
    assert piece.role == "" and piece.uses is not None and piece.uses.startswith("# uses orders @cell")


def test_run_file_leaves_a_scripts_streamlit_cells_out_on_the_same_lines() -> None:
    safe = kernel_side.safe_source(SCRIPT)
    assert len(safe.split("\n")) == len(SCRIPT.split("\n"))
    assert "st.selectbox" not in safe and "st.metric" not in safe
    assert 'print("plain")' in safe and "import pandas as pd" in safe
    assert safe.split("\n").index('print("plain")') == SCRIPT.split("\n").index('print("plain")')


# ----- a script's pages: a block of comments -----


def test_a_scripts_pages_are_a_block_of_comments_both_ways() -> None:
    pages = [
        Page("p1", "Sales overview", [Placed("s1", 5, 12), Placed("s2", 4, 4, 6)]),
        Page("p2", "Détails", []),
    ]
    text = rules.with_script_pages(SCRIPT, pages)
    ast.parse(text)  # comments only: the file still runs
    assert text.startswith(SCRIPT) and "# %% [streamlit-pages]\n" in text
    assert [p.to_json() for p in rules.script_pages(text)] == [p.to_json() for p in pages]
    # Changed where it is; nothing else in the file is touched, wherever the block sits.
    moved = text.replace(SCRIPT, "") + SCRIPT
    renamed = rules.with_script_pages(moved, [Page("p1", "Overview", [Placed("s1", 5, 12)])])
    assert renamed.endswith(SCRIPT) and renamed.count("[streamlit-pages]") == 1
    assert [p.name for p in rules.script_pages(renamed)] == ["Overview"]
    # The marker may carry the cell's number (the app numbers every cell).
    numbered = text.replace("# %% [streamlit-pages]", "# %% [9] [streamlit-pages]")
    assert len(rules.script_pages(numbered)) == 2
    # No pages: the block goes, and a script without one stays as it is.
    assert rules.with_script_pages(text, []) == SCRIPT
    assert rules.with_script_pages(SCRIPT, []) == SCRIPT and rules.script_pages(SCRIPT) == []
    # A line someone broke is passed over; the rest still read.
    broken = text.replace('# {"id": "p2"', '# {"id" "p2"')
    assert [p.id for p in rules.script_pages(broken)] == ["p1"]
    # The pages block is not a Streamlit cell.
    assert rules.script_pieces(text) == rules.script_pieces(SCRIPT)


def test_pages_are_checked_and_given_ids() -> None:
    pages = rules.read_pages(
        [
            {"name": "  Overview  ", "pieces": [{"cell": 4}, {"cell": 4, "id": "s1", "w": 99, "h": 0.4}]},
            {"id": "p1", "pieces": []},
            {"id": "bad id!", "name": "Third"},
        ]
    )
    assert [(p.id, p.name) for p in pages] == [("p1", "Overview"), ("p2", "Page 2"), ("p3", "Third")]
    assert [(s.id, s.cell, s.w, s.h) for s in pages[0].pieces] == [("s1", 4, 6, None), ("s2", 4, 12, 1)]
    assert rules.read_pages(None) == []
    for bad in (
        {"a": 1},
        [1],
        [{"name": "x\ny"}],
        [{"pieces": [{"cell": 0}]}],
        [{"pieces": [{"cell": True}]}],
    ):
        with pytest.raises(rules.StreamlitError):
            rules.read_pages(bad)
    with pytest.raises(rules.StreamlitError, match="at most"):
        rules.read_pages([{}] * (rules.MAX_PAGES + 1))
    assert rules.page_title(1, ["Page 1", "Page 2"]) == "Page 3"


def test_the_board_flows_pieces_into_rows_of_twelve_columns() -> None:
    placed = [Placed("a", 1, 4), Placed("b", 2, 8), Placed("c", 3, 6), Placed("d", 4, 7), Placed("e", 5, 12)]
    assert [[p.id for p in row] for row in rules.rows(placed)] == [["a", "b"], ["c"], ["d"], ["e"]]
    assert rules.rows([]) == []


# ===== a piece: its name, what it makes and reads =====


def test_a_pieces_name_is_its_first_comment() -> None:
    assert rules.piece_name(FILTER, 4) == "Region filter"
    assert rules.piece_name("# uses orders @cell3\n# Total by region\nst.write(1)", 5) == "Total by region"
    assert rules.piece_name("\n\n## Big  \nx = 1", 5) == "Big"
    assert rules.piece_name("st.write(1)\n# not a name", 7) == "Piece 7"
    assert rules.piece_name("# uses orders @cell3\nst.write(orders)", 7) == "Piece 7"
    assert rules.piece_name("", 2) == "Piece 2"


def test_the_names_a_piece_makes_and_reads() -> None:
    found = rules.facts(FILTER)
    assert found.makes == ("region",) and found.reads == ("st", "orders") and found.problem is None
    total = rules.facts(TOTAL)
    assert total.makes == () and set(total.reads) == {"st", "orders", "region"}
    # What it makes itself first is not read; a function's own names are its own; built-ins never.
    own = rules.facts(
        "low, high = st.slider('x', 0, 9, (1, 5))\ndef show(n):\n    return n + low\nprint(len([high]))"
    )
    assert own.makes == ("low", "high", "show") and own.reads == ("st",)
    # The uses line is the app's, not the piece's.
    assert rules.facts("# uses orders @cell3\nx = 1").makes == ("x",)
    assert rules.facts(CHART).modules == ("altair",)
    assert rules.facts("from plotly import express as px\nimport os.path").modules == ("plotly", "os.path")
    half = rules.facts("region = st.selectbox(\n")
    assert half.problem is not None and half.problem.startswith("line 1") and half.makes == ("region",)


def test_the_tables_a_piece_names_are_real_names_only() -> None:
    code = 'st.write(orders)\nx = "customers"  # products\ny = other.products\nz = orders_2026'
    assert rules.tables_named(code, ["orders", "customers", "products"]) == ["orders"]
    assert rules.tables_named("# uses orders @cell3\nst.write(1)", ["orders"]) == []


# ===== the order pieces run in =====


def test_pieces_run_in_the_order_their_names_need() -> None:
    total, picker = rules.facts(TOTAL), rules.facts(FILTER)
    # The total is placed first (above the filter) and still runs after it.
    ordered = rules.run_order([("total", total), ("filter", picker)])
    assert ordered.order == ("filter", "total") and ordered.cycle == ()
    assert ordered.links == (("total", "region", "filter"),)
    # With nothing to link, pieces run as they are placed.
    plain = rules.facts("st.write('a')")
    assert rules.run_order([("b", plain), ("a", plain)]).order == ("b", "a")
    # A chain, placed backwards.
    a, b, c = rules.facts("x = 1"), rules.facts("y = x + 1"), rules.facts("st.write(y)")
    assert rules.run_order([("c", c), ("b", b), ("a", a)]).order == ("a", "b", "c")
    # Two copies of one piece: the first placed makes the name; neither waits on the other.
    twice = rules.run_order([("one", picker), ("two", picker), ("total", total)])
    assert twice.order == ("one", "two", "total") and twice.links == (("total", "region", "one"),)


def test_a_cycle_is_reported_and_the_rest_still_run() -> None:
    a = rules.facts("first = second + 1")
    b = rules.facts("second = first + 1")
    free = rules.facts("st.write('free')")
    after = rules.facts("st.write(first)")
    ordered = rules.run_order([("a", a), ("free", free), ("b", b), ("after", after)])
    assert ordered.order == ("free",)
    assert ordered.cycle == ("a", "b")  # `after` only waits on the cycle: it is not part of it
    made = rules.page_code(
        "Loop",
        [Placed("a", 1, 6), Placed("b", 2, 6)],
        {1: PieceCode(1, "First", "first = second + 1"), 2: PieceCode(2, "Second", "second = first + 1")},
        [],
    )
    ast.parse(made.code)
    assert (
        len(made.problems) == 2
        and "First and Second need each other's names (first and second)" in made.problems[0]
    )
    assert "st.error(" in made.code and "first = second + 1" not in made.code


# ===== widget keys =====


def test_each_widget_gets_a_key_of_the_pieces_own() -> None:
    code = (
        'region = st.selectbox("Region", ["East", "West"])\n'
        "if st.button('Go'):\n"
        "    st.write(region)\n"
        'year = st.sidebar.slider(\n    "Year",\n    2020,\n    2026,  # the last one\n)\n'
        'kept = st.text_input("Name", key="mine")\n'
        'col.checkbox("Café ☕", value=True,)\n'
        "st.number_input(**options)\n"
        "st.write(st.toggle('On'))"
    )
    keyed = rules.keyed(code, "s2")
    tree = ast.parse(keyed)
    keys = [
        (node.func.attr, k.value.value)  # type: ignore[attr-defined]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        for k in node.keywords
        if k.arg == "key"
    ]
    assert sorted(keys) == [
        ("button", "s2_2"),
        ("checkbox", "s2_4"),
        ("selectbox", "s2_1"),
        ("slider", "s2_3"),
        ("text_input", "mine"),
        ("toggle", "s2_5"),
    ]
    # Only the keys are added: the text is otherwise as typed, comments and all.
    assert 'st.selectbox("Region", ["East", "West"], key="s2_1")' in keyed
    assert "2026,  # the last one\n" in keyed and 'col.checkbox("Café ☕", value=True,key="s2_4")' in keyed
    assert "st.number_input(**options)" in keyed  # its key may be among the options
    assert "st.write(region)" in keyed  # not a widget
    # A key after a comment on the same line starts a new line, or it would be part of the comment.
    odd = rules.keyed('x = st.radio("Pick", options  # all of them\n)', "s1")
    assert ast.parse(odd) and 'key="s1_1"' in odd.split("\n")[-1]
    # Two copies of one piece: different keys. Half-typed code is left as it is.
    assert rules.keyed(code, "s9") != keyed and rules.keyed("st.button(", "s1") == "st.button("


def test_indenting_leaves_the_lines_inside_a_text_alone() -> None:
    code = 'st.markdown("""\n# Title\n  indented text\n""")\nif x:\n    y = f"""a\n{b}\nc"""\n'
    moved = rules.indented(code)
    wrapped = f"with slot:\n{moved}"
    held = [
        n.value
        for n in ast.walk(ast.parse(wrapped))
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    assert "\n# Title\n  indented text\n" in held and "a\n" in held and "\nc" in held
    assert moved.startswith('    st.markdown("""\n# Title\n') and "    if x:\n        y = f" in moved


# ===== the page as one Streamlit page =====


def test_a_page_draws_its_slots_first_then_runs_pieces_in_name_order() -> None:
    # The filter is placed BELOW the total; the total still gets `region`.
    placed = [Placed("s1", 5, 12), Placed("s2", 4, 4, 3)]
    made = rules.page_code("Sales overview", placed, PIECES, ["orders", "customers"])
    ast.parse(made.code)
    code = made.code
    assert made.order == ("s2", "s1") and made.problems == () and made.tables == ("orders",)
    slots = code.index("_slot_s1 = st.container()"), code.index("_slot_s2 = _row_2[0].container(height=120)")
    assert "_row_2 = st.columns([4, 8])" in code  # the spare columns keep the piece 4 wide
    first_piece = code.index("with _slot_")
    assert max(slots) < first_piece  # every slot is drawn before any piece runs
    assert code.index("with _slot_s2:") < code.index("with _slot_s1:")  # the filter runs first
    assert slots[0] < slots[1]  # and the total's slot is above the filter's
    # Each piece fills its own slot, its widgets keyed by its place; a failure stays in its slot.
    assert 'region = st.selectbox("Region", sorted(orders["region"].unique()), key="s2_1")' in code
    assert code.count("except Exception as _error:") == 2 and "st.exception(_error)" in code
    assert "# Region filter (cell 4): makes region" in code
    # Two copies of the filter do not clash.
    twice = rules.page_code("Two", [Placed("s1", 4, 6), Placed("s2", 4, 6)], PIECES, ["orders"])
    assert 'key="s1_1"' in twice.code and 'key="s2_1"' in twice.code
    assert "_row_1 = st.columns([6, 6])" in twice.code


def test_the_preamble_reads_only_the_tables_the_page_names() -> None:
    made = rules.page_code("Sales", [Placed("s1", 4, 12)], PIECES, ["orders", "customers"])
    assert 'orders = _table("orders", (_DATA / "orders.parquet").stat().st_mtime)' in made.code
    assert "customers" not in made.code and made.tables == ("orders",)
    assert '_DATA = Path(__file__).resolve().parent / "data"' in made.code and "@st.cache_data" in made.code
    # A page that names no table reads none (and needs no data folder).
    plain = rules.page_code(
        "Plain", [Placed("s1", 1, 12)], {1: PieceCode(1, "Hi", 'st.write("hi")')}, ["orders"]
    )
    assert "_table" not in plain.code and "Path" not in plain.code and plain.tables == ()
    assert plain.code.startswith("# Plain\nimport pandas as pd\nimport streamlit as st\n")
    # A table named only in a text or a comment is not read.
    quiet = {1: PieceCode(1, "Hi", 'st.write("orders")  # orders')}
    assert rules.page_code("Quiet", [Placed("s1", 1, 12)], quiet, ["orders"]).tables == ()


def test_a_page_says_what_it_cannot_run_and_runs_the_rest() -> None:
    pieces = {
        4: PieceCode(4, "Region filter", FILTER),
        5: PieceCode(5, "Total", TOTAL),
        6: PieceCode(6, "Half", "x = st.slider(\n"),
        7: PieceCode(7, "Notes", "# Notes\n"),
    }
    placed = [Placed("s1", 5, 6), Placed("s2", 6, 6), Placed("s3", 9, 6), Placed("s4", 7, 6)]
    found = {cell: rules.facts(p.code) for cell, p in pieces.items()}
    page = Page("p1", "Sales", placed)
    made = rules.page_code("Sales", placed, pieces, ["orders"], elsewhere=rules.elsewhere(page, found))
    ast.parse(made.code)
    assert len(made.problems) == 3
    said = "\n".join(made.problems)
    assert (
        "Total reads region (the piece in cell 4), which is not on this page: push that piece here too."
        in said
    )
    assert "Half (cell 6) is not whole Python yet: line 1" in said
    assert "The piece from cell 9 is gone" in said
    assert "st.metric" not in made.code and "st.slider" not in made.code
    assert "with _slot_s4:\n    try:\n        pass\n" in made.code  # a piece of comments runs nothing


def test_a_piece_alone_shows_with_the_pieces_that_make_its_names() -> None:
    order = [4, 5]
    alone = rules.preview_code(5, PIECES, order, ["orders"])
    ast.parse(alone.code)
    assert alone.order == ("c4", "c5") and alone.tables == ("orders",)
    assert "st.caption('region comes from the piece in cell 4')" in alone.code
    assert alone.code.index("_slot_c4 = st.container()") < alone.code.index("_slot_c5 = st.container()")
    # A piece that reads no other piece's name is alone.
    assert rules.preview_code(4, PIECES, order, ["orders"]).order == ("c4",)
    # The nearest maker above wins; one below is used when none is above; inputs of inputs come too.
    pieces = {
        1: PieceCode(1, "A", "base = 1"),
        2: PieceCode(2, "B", "level = base + st.slider('x', 0, 9)"),
        3: PieceCode(3, "C", "st.write(level)"),
        4: PieceCode(4, "D", "level = 100"),
    }
    found = rules.makers({c: p.code for c, p in pieces.items()}, [1, 2, 3, 4])
    assert rules.inputs_of(3, found, [1, 2, 3, 4]) == [(1, "base"), (2, "level")]
    assert rules.inputs_of(3, found, [3, 4]) == [(4, "level")]
    assert rules.inputs_of(1, found, [1, 2, 3, 4]) == []


def test_the_live_entry_and_the_names_of_modules() -> None:
    ast.parse(rules.ENTRY)
    ast.parse(rules.HOME)
    assert 'position="hidden"' in rules.ENTRY and "manifest.json" in rules.ENTRY
    assert rules.slug("Sales overview") == "sales_overview" and rules.slug("Détails 2026!") == "d_tails_2026"
    assert rules.slug("2026") == "page_2026" and rules.slug("???") == "page"
    assert rules.slug("Sales", ["sales", "sales_2"]) == "sales_3"


# ===== export =====


def test_the_export_is_a_folder_that_runs_without_the_app() -> None:
    pieces = PIECES | {
        6: PieceCode(6, "Chart", CHART),
        7: PieceCode(7, "Extra", "import sklearn, os, swissarmygrid"),
    }
    pages = [
        Page("p1", "Sales overview", [Placed("s1", 5, 12), Placed("s2", 4, 4)]),
        Page("p2", "Sales overview", [Placed("s3", 6, 12)]),
    ]
    made = rules.export("Sales app", pages, pieces, ["orders", "customers"])
    assert sorted(made.files) == [
        "README.txt",
        "app.py",
        "app_pages/sales_overview.py",
        "app_pages/sales_overview_2.py",
        "requirements.txt",
    ]
    for name, text in made.files.items():
        if name.endswith(".py"):
            ast.parse(text)
    app = made.files["app.py"]
    assert "st.Page(\"app_pages/sales_overview.py\", title='Sales overview', default=True)" in app
    assert (
        "st.Page(\"app_pages/sales_overview_2.py\", title='Sales overview')" in app
        and "st.navigation(" in app
    )
    first = made.files["app_pages/sales_overview.py"]
    # Laid out as designed, pieces in name order, plain code (no guard), data beside app.py.
    assert first.index("with _slot_s2:") < first.index("with _slot_s1:")
    assert "try:" not in first and "swissarmygrid" not in first.lower().replace("# sales overview", "")
    assert '_DATA = Path(__file__).resolve().parent.parent / "data"' in first
    assert made.tables == ("orders",) and made.problems == ()
    # What the pages import, and only the pieces that are on a page.
    assert made.files["requirements.txt"] == "streamlit>=1.36\npandas\npyarrow\naltair\n"
    assert "streamlit run app.py" in made.files["README.txt"]
    assert rules.requirements(["import sklearn, os, swissarmygrid\nimport PIL.Image"]) == [
        "streamlit>=1.36",
        "pandas",
        "pyarrow",
        "scikit-learn",
        "Pillow",
    ]
    with pytest.raises(rules.StreamlitError, match="no page"):
        rules.export("Empty", [], pieces, [])
    # A page that cannot run a piece says so in the export's answer too.
    lone = rules.export("Lone", [Page("p1", "Only total", [Placed("s1", 5, 12)])], pieces, ["orders"])
    assert lone.problems == (
        "Only total: Total reads region (the piece in cell 4), which is not on this page: "
        "push that piece here too.",
    )
