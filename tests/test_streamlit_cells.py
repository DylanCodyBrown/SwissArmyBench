"""The Streamlit canvas's rules (docs/ideas.md, 2026-11-15): the app's file both ways and its links;
which Python cells call Streamlit; a notebook or script saved when there was a Streamlit kind of cell
reading cleanly; the grid's rows; the names each cell makes and reads, the run order and a cycle; the
page as one Streamlit page (slots first, blocks in name order, keys of their own); a missing cell;
the export folder's files; the Save as zip's files. Made-up data only."""

from __future__ import annotations

import ast
import json

import pytest

from swissarmygrid.client import table_cells as kernel_side
from swissarmygrid.domain import notebooks, table_cells
from swissarmygrid.domain import streamlit_cells as rules
from swissarmygrid.domain.streamlit_cells import Block, Page, PieceCode
from swissarmygrid.domain.streamlit_use import other_st, uses_streamlit, usual_name

FILTER = '# Region filter\nregion = st.selectbox("Region", sorted(orders["region"].unique()))'
TOTAL = '# Total\nst.metric("Total", int(orders[orders["region"] == region]["amount"].sum()))'
CHART = "# Chart\nimport altair as alt\nst.altair_chart(alt.Chart(orders).mark_bar())"
DOC = "/work/sales.ipynb"


def B(
    block: str,
    cell: int,
    row: int = 1,
    column: int = 1,
    w: int = 12,
    h: int | None = None,
    document: str = DOC,
) -> Block:
    return Block(block, document, cell, row, column, w, h)


PIECES = {
    (DOC, 4): PieceCode(4, "Region filter", FILTER, "sales.ipynb @cell4"),
    (DOC, 5): PieceCode(5, "Total", TOTAL, "sales.ipynb @cell5"),
}

# ===== which Python cells call Streamlit =====


def test_a_cell_that_calls_streamlit_is_found_by_pythons_parser() -> None:
    assert uses_streamlit(FILTER) and uses_streamlit(TOTAL)
    assert uses_streamlit("with st.sidebar:\n    pass") and uses_streamlit("left, right = st.columns(2)")
    assert uses_streamlit("import streamlit as sl\nsl.write('hi')")
    assert uses_streamlit("import streamlit\nstreamlit.title('Sales')")
    assert uses_streamlit("from streamlit import metric\nmetric('Total', 3)")
    assert uses_streamlit("x = st.sidebar.selectbox('Region', ['East'])")
    # An import alone draws nothing, and the kernel still needs the other names.
    assert not uses_streamlit("import streamlit as st\nimport pandas as pd")
    assert not uses_streamlit("from streamlit import metric")
    # Plain Python; a word in a text or a comment; `st` as something else's attribute.
    assert not uses_streamlit("total = orders['amount'].sum()")
    assert not uses_streamlit('note = "st.write(1)"  # st.write(2)')
    assert not uses_streamlit("x = thing.st.write(1)")
    # Another `st`: scipy's stats, a variable, a function's argument.
    assert not uses_streamlit("from scipy import stats as st\np = st.norm.cdf(1.96)")
    assert not uses_streamlit("st = open('log.txt')\nst.write('x')")
    assert other_st("import statistics as st") and not other_st("import streamlit as st")
    # The document says so too: one cell gives `st` another value, the others do not mean Streamlit.
    cells = ["from scipy import stats as st", "p = st.norm.cdf(1.96)"]
    assert not usual_name(cells) and not uses_streamlit(cells[1], usual_name(cells))
    assert usual_name([FILTER, TOTAL])
    # Half-typed code is not a live cell yet.
    assert not uses_streamlit("region = st.selectbox(")
    assert rules.live_cells([(1, "import pandas as pd"), (4, FILTER), (5, TOTAL), (6, "")]) == [4, 5]
    assert rules.live_cells([(1, "# uses orders @cell3\nst.dataframe(orders)")]) == [1]


# ===== a notebook or script saved when there was a Streamlit kind of cell =====


def _old_notebook() -> str:
    """A notebook as it was saved before the canvas: a marked cell, and pages in its metadata."""
    cell = {
        "cell_type": "code",
        "id": "cell-2",
        "metadata": {"swissarmygrid": {"kind": "streamlit", "height": 320, "number": 2}},
        "source": ["# %% [streamlit]\n", *FILTER.splitlines(keepends=True)],
        "outputs": [],
        "execution_count": None,
    }
    plain = {
        "cell_type": "code",
        "id": "cell-1",
        "metadata": {"swissarmygrid": {"number": 1}},
        "source": ["import pandas as pd"],
        "outputs": [],
        "execution_count": None,
    }
    pages = [{"id": "p1", "name": "Sales", "pieces": [{"id": "s1", "cell": 2, "w": 12, "h": None}]}]
    own = {"next_cell": 3, "streamlit": {"pages": pages}}
    return json.dumps({"cells": [plain, cell], "metadata": {"swissarmygrid": own}, "nbformat": 4})


def test_an_old_notebooks_streamlit_cell_opens_as_a_python_cell_with_nothing_lost() -> None:
    cells, following = notebooks.read_document(_old_notebook())
    assert [(c.kind, c.source, c.height, c.number) for c in cells] == [
        ("code", "import pandas as pd", None, 1),
        ("code", FILTER, 320, 2),  # the marker line is gone; the code, the height and the number stay
    ]
    assert following == 3
    # Saved again: a plain code cell that keeps its pane's height; no kind, no marker, no pages.
    raw = json.loads(notebooks.write_notebook(cells, next_number=following))
    assert "".join(raw["cells"][1]["source"]) == FILTER
    assert raw["cells"][1]["metadata"]["swissarmygrid"] == {"height": 320, "number": 2}
    assert raw["metadata"]["swissarmygrid"] == {"next_cell": 3}
    assert not hasattr(notebooks, "document_pages")


def test_the_page_may_still_send_the_old_kind_and_it_is_a_python_cell() -> None:
    sent = [{"kind": "streamlit", "source": FILTER, "height": 5000}]
    cell = notebooks.read_cells(sent)[0]
    assert (cell.kind, cell.height) == ("code", 2000)
    assert notebooks.code_of(cell) == FILTER
    with pytest.raises(notebooks.NotebookError, match='"html" or "markdown"'):
        notebooks.read_cells([{"kind": "dash", "source": ""}])
    assert "streamlit" not in notebooks.KINDS


OLD_SCRIPT = f"""import pandas as pd

# %% [4] [streamlit] height=300
{FILTER}
# %% [5] [streamlit]
{TOTAL}
# %% [6]
print("plain")
# %% [streamlit-pages]
# The pages of this file's Streamlit app (SwissArmyGrid's page designer keeps this block).
# {{"id": "p1", "name": "Sales", "pieces": [{{"id": "s1", "cell": 5, "w": 12, "h": null}}]}}
"""
SCRIPT = (
    OLD_SCRIPT.replace(" [streamlit] height=300", " height=300")
    .replace("[5] [streamlit]", "[5]")
    .replace("# %% [streamlit-pages]", "# %% [7] [streamlit-pages]")  # a cell of comments, numbered like any
)


def test_an_old_scripts_streamlit_marker_reads_as_a_plain_cell() -> None:
    ast.parse(OLD_SCRIPT)
    script = table_cells.parse_script(OLD_SCRIPT)
    found = [(c.number, c.kind, c.height, c.title) for c in script.cells if not c.fixed]
    assert found[:3] == [(4, "code", 300, ""), (5, "code", None, ""), (6, "code", None, "")]
    # The old pages block is not read: it stays in the file as the comments it always was.
    assert found[3][3] == "[streamlit-pages]" and not hasattr(rules, "script_pages")
    # Arranged, the markers are plain ones: the number, and the pane's height.
    again, arrangement = table_cells.arrange_script(OLD_SCRIPT, [])
    assert again == SCRIPT and arrangement.tables == []
    assert table_cells.arrange_script(SCRIPT, [])[0] == SCRIPT
    # The editor still shows the two cells live: they call Streamlit.
    outline = table_cells.outline(SCRIPT)
    assert [(c["kind"], c["number"], c["height"]) for c in outline["cells"]][:3] == [
        ("streamlit", 4, 300),
        ("streamlit", 5, None),
        ("code", 6, None),
    ]
    assert rules.document_cells("/work/sales.py", SCRIPT)[:3] == [
        (4, FILTER),
        (5, TOTAL),
        (6, 'print("plain")'),
    ]


def test_a_cell_that_calls_streamlit_is_never_the_cell_that_makes_a_table() -> None:
    # It gives `orders` a value, and no other cell does: it still stays where it is, with its uses line.
    script = "# %% [4]\norders = orders.dropna()\nst.dataframe(orders)\n"
    spec = table_cells.TableSpec("orders", "# orders: no steps", "# load\n# orders: no steps")
    text, arrangement = table_cells.arrange_script(script, [spec])
    assert arrangement.tables[0].maker is None
    assert "# %% [4]\n# uses orders @cell" in text
    plan = [table_cells.PlanCell(4, "code", "orders = orders.dropna()\nst.dataframe(orders)")]
    done = table_cells.arrange(plan, [spec], 5)
    piece = next(c for c in done.cells if c.number == 4)
    assert piece.role == "" and piece.uses is not None and piece.uses.startswith("# uses orders @cell")
    # The same cell without Streamlit does make the table.
    plain = table_cells.arrange([table_cells.PlanCell(4, "code", "orders = load()")], [spec], 5)
    assert plain.tables[0].maker == 4


def test_run_file_leaves_the_cells_that_call_streamlit_out_on_the_same_lines() -> None:
    for text in (SCRIPT, OLD_SCRIPT):
        safe = kernel_side.safe_source(text)
        assert len(safe.split("\n")) == len(text.split("\n"))
        assert "st.selectbox" not in safe and "st.metric" not in safe
        assert 'print("plain")' in safe and "import pandas as pd" in safe
        assert safe.split("\n").index('print("plain")') == text.split("\n").index('print("plain")')
    # A script whose `st` is something else runs whole.
    other = "from scipy import stats as st\n# %% [2]\nprint(st.norm.cdf(1.96))\n"
    assert kernel_side.safe_source(other) == other


# ===== the app's file, both ways; links =====

APP = """{
  "swissarmygrid": "streamlit-app",
  "version": 1,
  "pages": [
    {
      "name": "Sales overview",
      "blocks": [
        {"document": "sales.ipynb", "cell": 4, "row": 1, "column": 1, "width": 4, "height": null},
        {"document": "sales.ipynb", "cell": 5, "row": 1, "column": 7, "width": 6, "height": 5},
        {"document": "../shared/charts.py", "cell": 2, "row": 2, "column": 1, "width": 12, "height": null}
      ]
    },
    {
      "name": "Détails",
      "blocks": []
    }
  ]
}
"""


def test_the_apps_file_is_small_readable_and_reads_back() -> None:
    app = "/work/apps/sales.stapp.json"
    pages = rules.read_app(APP, lambda link: rules.resolve_link(app, link))
    assert [(p.id, p.name, len(p.blocks)) for p in pages] == [
        ("p1", "Sales overview", 3),
        ("p2", "Détails", 0),
    ]
    assert [b.to_json() for b in pages[0].blocks] == [
        {
            "id": "b1",
            "document": "/work/apps/sales.ipynb",
            "cell": 4,
            "row": 1,
            "column": 1,
            "w": 4,
            "h": None,
        },
        {"id": "b2", "document": "/work/apps/sales.ipynb", "cell": 5, "row": 1, "column": 7, "w": 6, "h": 5},
        {
            "id": "b3",
            "document": "/work/shared/charts.py",
            "cell": 2,
            "row": 2,
            "column": 1,
            "w": 12,
            "h": None,
        },
    ]
    # Written again it is the same text: one block a line, links relative to the file, no ids, no code.
    assert rules.write_app(pages, lambda document: rules.relative_link(app, document)) == APP
    assert json.loads(APP)["pages"][0]["blocks"][1] == {
        "document": "sales.ipynb",
        "cell": 5,
        "row": 1,
        "column": 7,
        "width": 6,
        "height": 5,
    }
    assert (
        rules.write_app([]) == '{\n  "swissarmygrid": "streamlit-app",\n  "version": 1,\n  "pages": []\n}\n'
    )
    assert rules.read_app(rules.write_app([])) == []
    # Not an app's file, or one from a newer version, says so.
    with pytest.raises(rules.StreamlitError, match="not a Streamlit app's file"):
        rules.read_app("[1, 2]")
    with pytest.raises(rules.StreamlitError, match="not a Streamlit app's file"):
        rules.read_app('{"cells": []}')
    with pytest.raises(rules.StreamlitError, match="newer"):
        rules.read_app('{"swissarmygrid": "streamlit-app", "version": 2, "pages": []}')
    with pytest.raises(rules.StreamlitError, match="cell's own number"):
        rules.read_app(APP.replace('"cell": 4', '"cell": "four"'))
    assert notebooks.kind_of("/work/Sales.STAPP.json") == "app" and rules.is_app("x.stapp.json")
    assert (
        rules.app_title("C:\\work\\sales.stapp.json") == "sales" and rules.app_title(None) == "Streamlit app"
    )


def test_a_link_is_relative_to_the_apps_own_folder() -> None:
    app = "/work/apps/sales.stapp.json"
    assert rules.relative_link(app, "/work/apps/sales.ipynb") == "sales.ipynb"
    assert rules.relative_link(app, "/work/notebooks/q3/sales.ipynb") == "../notebooks/q3/sales.ipynb"
    assert rules.resolve_link(app, "../notebooks/q3/sales.ipynb") == "/work/notebooks/q3/sales.ipynb"
    assert rules.resolve_link(app, "/else/x.py") == "/else/x.py"
    # An app without a file yet keeps whole paths.
    assert rules.relative_link(None, "/work/sales.ipynb") == "/work/sales.ipynb"
    assert rules.resolve_link(None, "sales.ipynb") == "sales.ipynb"
    # Windows: backslashes in, forward slashes in the file; another drive stays whole.
    win = "C:\\work\\apps\\sales.stapp.json"
    assert rules.relative_link(win, "C:\\work\\nb\\sales.ipynb") == "../nb/sales.ipynb"
    assert rules.resolve_link(win, "../nb/sales.ipynb") == "C:\\work\\nb\\sales.ipynb"
    assert rules.relative_link(win, "D:\\data\\x.py") == "D:\\data\\x.py"
    assert rules.same_file("C:\\Work\\a.py", "c:/work/A.py") and not rules.same_file("/w/a.py", "/w/A.py")


def test_a_linked_files_python_cells_are_the_ones_a_block_can_name() -> None:
    cells = [
        notebooks.Cell("markdown", "# Sales"),
        notebooks.Cell("code", FILTER),
        notebooks.Cell("sql", "select 1"),
        notebooks.Cell(
            "code", "import duckdb\norders = duckdb.sql('...').df()", role="transformations", table="orders"
        ),
        notebooks.Cell("code", TOTAL),
    ]
    text = notebooks.write_notebook(cells)
    assert rules.document_cells("/work/sales.ipynb", text) == [(2, FILTER), (5, TOTAL)]
    # A script's cell without a number (never opened here) cannot be linked; its main code never.
    assert rules.document_cells("/work/s.py", "x = 1\n# %%\ny = 2\n# %% [3] Named\nz = 3\n") == [(3, "z = 3")]


# ===== named cells (the owner, 2026-11-15): a label; the number stays the cell's identity =====


def test_a_notebook_cells_name_is_kept_in_its_metadata_both_ways() -> None:
    cells = [
        notebooks.Cell("code", FILTER, name="Region [filter] #1"),
        notebooks.Cell("markdown", "# Notes", name="Read me"),
        notebooks.Cell("code", TOTAL),
    ]
    text = notebooks.write_notebook(cells)
    held = json.loads(text)["cells"]
    # Where plain Jupyter keeps it: the cell's own metadata, beside its number.
    assert held[0]["metadata"]["swissarmygrid"] == {"number": 1, "name": "Region [filter] #1"}
    assert held[1]["metadata"]["swissarmygrid"]["name"] == "Read me"
    assert "name" not in held[2]["metadata"]["swissarmygrid"]
    read, _ = notebooks.read_document(text)
    assert [(c.number, c.name) for c in read] == [(1, "Region [filter] #1"), (2, "Read me"), (3, None)]
    assert rules.document_names("/work/sales.ipynb", text) == {1: "Region [filter] #1"}  # Python cells
    # As the window sends it: checked, one line; "" is no name.
    sent = notebooks.read_cells([{"kind": "code", "source": "x = 1", "name": "  Total  "}])
    assert sent[0].name == "Total" and sent[0].to_json()["name"] == "Total"
    assert notebooks.read_cells([{"kind": "code", "source": "", "name": ""}])[0].name is None
    for bad in ("two\nlines", "x" * 81, 7):
        with pytest.raises(notebooks.NotebookError, match="one line"):
            notebooks.read_cells([{"kind": "code", "source": "", "name": bad}])
    # An old file (no names) opens as it did; a name another tool wrote too long is dropped.
    old = text.replace('"name": "Region [filter] #1"', '"name": "' + "y" * 90 + '"')
    assert notebooks.read_document(old)[0][0].name is None
    assert notebooks.read_document(notebooks.write_notebook([notebooks.Cell("code", "1")]))[0][0].name is None


def test_a_script_cells_name_is_its_markers_own_words_both_ways() -> None:
    # Words that would read as the marker's own grammar are written after a backslash.
    for name, words in [
        ("Region filter", "Region filter"),
        ("Sales #1 [by region]", "Sales #1 [by region]"),
        ("[html] report", "\\[html] report"),
        ("[3] three", "\\[3] three"),
        ("height=300 box", "\\height=300 box"),
        ("\\back", "\\\\back"),
    ]:
        assert table_cells.marker_words(name) == words
        assert table_cells.marker_name(f" {words} ") == name
    assert table_cells.marker_words(None) == "" and table_cells.marker_name("  ") is None
    script = (
        "import streamlit as st\n\n"
        f"# %% [4] Region filter\n{FILTER}\n\n"
        f"# %% [5] height=300 \\[html] total\n{TOTAL}\n\n"
        "# %% [6] [html] Report\nhtml = '<b>hi</b>'\n\n"
        "# %% [7]\nx = 1\n"
    )
    assert rules.document_names("/work/sales.py", script) == {4: "Region filter", 5: "[html] total"}
    outline = table_cells.outline(script)
    assert [(c["number"], c["kind"], c["height"], c["name"]) for c in outline["cells"]] == [
        (4, "streamlit", None, "Region filter"),
        (5, "streamlit", 300, "[html] total"),
        (6, "html", None, "Report"),
        (7, "code", None, None),
    ]
    # Arranged again, the marker lines are as they were: the names, the kinds, the heights.
    assert table_cells.arrange_script(script, [])[0] == script


def test_a_named_cell_is_called_by_its_name_on_a_canvas() -> None:
    assert rules.cell_title(FILTER, 4, "Pick a region") == "Pick a region"
    assert rules.cell_title(FILTER, 4, None) == "Region filter"  # the first comment line, as before
    assert rules.cell_title("", 9) == "Cell 9"


# ===== pages and the grid =====


def test_pages_are_checked_and_given_ids() -> None:
    pages = rules.read_pages(
        [
            {
                "name": " Sales ",
                "blocks": [{"document": DOC, "cell": 4}, {"document": DOC, "cell": 5, "w": 99, "h": 0}],
            },
            {
                "id": "p1",
                "name": "",
                "blocks": [{"id": "b1", "document": DOC, "cell": 4, "column": 11, "w": 6}],
            },
        ]
    )
    assert [(p.id, p.name) for p in pages] == [("p1", "Sales"), ("p2", "Page 2")]
    assert [(b.id, b.row, b.column, b.w, b.h) for b in pages[0].blocks] == [
        ("b1", 1, 1, 6, None),
        ("b2", 2, 1, 12, 1),
    ]
    # An id used twice is made anew; a block past column 12 is pulled back to fit.
    assert [(b.id, b.column, b.w) for b in pages[1].blocks] == [("b3", 7, 6)]
    assert rules.read_pages(None) == []
    bads: tuple[object, ...] = (
        {},
        [1],
        [{"blocks": [{"document": DOC, "cell": 0}]}],
        [{"blocks": [{"cell": 2}]}],
        [{"blocks": 5}],
    )
    for bad in bads:
        with pytest.raises(rules.StreamlitError):
            rules.read_pages(bad)
    with pytest.raises(rules.StreamlitError, match="at most 30"):
        rules.read_pages([{"name": f"P{i}"} for i in range(31)])
    assert rules.next_id("b", ["b1", "b2", "b4"]) == "b3"
    assert rules.page_title(1, ["Page 1", "Page 2"]) == "Page 3"


def test_the_grid_keeps_blocks_in_rows_none_on_top_of_another() -> None:
    blocks = [
        B("a", 1, 1, 1, 4),
        B("b", 2, 1, 7, 6),
        B("c", 3, 3, 3, 6),
        B("d", 4, 3, 5, 6),
        B("e", 5, 9, 1, 12),
    ]
    rules.settle(blocks)
    # `d` would lie on `c`: it starts a row of its own below. Rows are counted from 1, none empty.
    assert [(b.id, b.row, b.column) for b in blocks] == [
        ("a", 1, 1),
        ("b", 1, 7),
        ("c", 2, 3),
        ("d", 3, 5),
        ("e", 4, 1),
    ]
    assert [[b.id for b in row] for row in rules.rows(blocks)] == [["a", "b"], ["c"], ["d"], ["e"]]
    assert rules.rows([]) == []
    # A new block goes beside the last one when the row has room, else below.
    assert rules.free_place([]) == (1, 1)
    assert rules.free_place([B("a", 1, 1, 1, 6)]) == (1, 7)
    assert rules.free_place([B("a", 1, 1, 1, 6), B("b", 2, 1, 7, 6)]) == (2, 1)
    assert rules.free_place([B("a", 1, 1, 1, 8)]) == (2, 1) and rules.free_place([B("a", 1, 1, 1, 8)], 4) == (
        1,
        9,
    )


# ===== a cell: its title, what it makes and reads =====


def test_a_blocks_title_is_the_cells_first_comment_or_first_line() -> None:
    assert rules.piece_name(FILTER, 4) == "Region filter"
    assert rules.piece_name("# uses orders @cell3\n# Total by region\nst.write(1)", 5) == "Total by region"
    assert rules.piece_name("\n\n## Big  \nx = 1", 5) == "Big"
    assert rules.piece_name("st.write(1)\n# not a name", 7) == "st.write(1)"
    assert rules.piece_name("# uses orders @cell3\nst.write(orders)", 7) == "st.write(orders)"
    assert rules.piece_name("", 2) == "Cell 2" and len(rules.piece_name("x = " + "1" * 200, 2)) == 80


def test_the_names_a_cell_makes_and_reads() -> None:
    found = rules.facts(FILTER)
    assert found.makes == ("region",) and found.reads == ("st", "orders") and found.problem is None
    total = rules.facts(TOTAL)
    assert total.makes == () and set(total.reads) == {"st", "orders", "region"}
    # What it makes itself first is not read; a function's own names are its own; built-ins never.
    own = rules.facts(
        "low, high = st.slider('x', 0, 9, (1, 5))\ndef show(n):\n    return n + low\nprint(len([high]))"
    )
    assert own.makes == ("low", "high", "show") and own.reads == ("st",)
    # The uses line is the app's, not the cell's.
    assert rules.facts("# uses orders @cell3\nx = 1").makes == ("x",)
    assert rules.facts(CHART).modules == ("altair",)
    assert rules.facts("from plotly import express as px\nimport os.path").modules == ("plotly", "os.path")
    half = rules.facts("region = st.selectbox(\n")
    assert half.problem is not None and half.problem.startswith("line 1") and half.makes == ("region",)


def test_the_tables_a_cell_names_are_real_names_only() -> None:
    code = 'st.write(orders)\nx = "customers"  # products\ny = other.products\nz = orders_2026'
    assert rules.tables_named(code, ["orders", "customers", "products"]) == ["orders"]
    assert rules.tables_named("# uses orders @cell3\nst.write(1)", ["orders"]) == []


# ===== the order blocks run in =====


def test_blocks_run_in_the_order_their_names_need() -> None:
    total, picker = rules.facts(TOTAL), rules.facts(FILTER)
    # The total is placed first (above the filter) and still runs after it.
    ordered = rules.run_order([("total", total), ("filter", picker)])
    assert ordered.order == ("filter", "total") and ordered.cycle == ()
    assert ordered.links == (("total", "region", "filter"),)
    # With nothing to link, blocks run as they are placed.
    plain = rules.facts("st.write('a')")
    assert rules.run_order([("b", plain), ("a", plain)]).order == ("b", "a")
    # A chain, placed backwards.
    a, b, c = rules.facts("x = 1"), rules.facts("y = x + 1"), rules.facts("st.write(y)")
    assert rules.run_order([("c", c), ("b", b), ("a", a)]).order == ("a", "b", "c")
    # Two blocks of one cell: the first placed makes the name; neither waits on the other.
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
        [B("a", 1, 1, 1, 6), B("b", 2, 1, 7, 6)],
        {
            (DOC, 1): PieceCode(1, "First", "first = second + 1"),
            (DOC, 2): PieceCode(2, "Second", "second = first + 1"),
        },
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


def test_a_page_draws_its_slots_first_then_runs_blocks_in_name_order() -> None:
    # The filter is placed BELOW the total; the total still gets `region`.
    placed = [B("b1", 5, 1, 1, 12), B("b2", 4, 2, 1, 4, 3)]
    made = rules.page_code("Sales overview", placed, PIECES, ["orders", "customers"])
    ast.parse(made.code)
    code = made.code
    assert made.order == ("b2", "b1") and made.problems == () and made.tables == ("orders",)
    slots = code.index("_slot_b1 = st.container()"), code.index("_slot_b2 = _row_2[0].container(height=120)")
    assert "_row_2 = st.columns([4, 8])" in code  # the spare columns keep the block 4 wide
    first_block = code.index("with _slot_")
    assert max(slots) < first_block  # every slot is drawn before any block runs
    assert code.index("with _slot_b2:") < code.index("with _slot_b1:")  # the filter runs first
    assert slots[0] < slots[1]  # and the total's slot is above the filter's
    # Each block fills its own slot, its widgets keyed by its place; a failure stays in its slot.
    assert 'region = st.selectbox("Region", sorted(orders["region"].unique()), key="b2_1")' in code
    assert code.count("except Exception as _error:") == 2 and "st.exception(_error)" in code
    assert "# Region filter (sales.ipynb @cell4): makes region" in code
    # Two blocks of the filter do not clash.
    twice = rules.page_code("Two", [B("b1", 4, 1, 1, 6), B("b2", 4, 1, 7, 6)], PIECES, ["orders"])
    assert 'key="b1_1"' in twice.code and 'key="b2_1"' in twice.code
    assert "_row_1 = st.columns([6, 6])" in twice.code


def test_a_block_sits_in_its_own_columns_with_the_gaps_left_empty() -> None:
    placed = [B("b1", 4, 1, 3, 4), B("b2", 5, 1, 9, 3), B("b3", 4, 2, 7, 6)]
    code = rules.page_code("Gaps", placed, PIECES, ["orders"]).code
    # Columns 1-2 empty, the block on 3-6, 7-8 empty, the block on 9-11, column 12 empty.
    assert "_row_1 = st.columns([2, 4, 2, 3, 1])" in code
    assert "_slot_b1 = _row_1[1].container()" in code and "_slot_b2 = _row_1[3].container()" in code
    assert "_row_2 = st.columns([6, 6])" in code and "_slot_b3 = _row_2[1].container()" in code


def test_the_preamble_reads_only_the_tables_the_page_names() -> None:
    made = rules.page_code("Sales", [B("b1", 4)], PIECES, ["orders", "customers"])
    assert 'orders = _table("orders", (_DATA / "orders.parquet").stat().st_mtime)' in made.code
    assert "customers" not in made.code and made.tables == ("orders",)
    assert '_DATA = Path(__file__).resolve().parent / "data"' in made.code and "@st.cache_data" in made.code
    # A page that names no table reads none (and needs no data folder).
    plain = rules.page_code(
        "Plain", [B("b1", 1)], {(DOC, 1): PieceCode(1, "Hi", 'st.write("hi")')}, ["orders"]
    )
    assert "_table" not in plain.code and "Path" not in plain.code and plain.tables == ()
    assert plain.code.startswith("# Plain\nimport pandas as pd\nimport streamlit as st\n")
    # A table named only in a text or a comment is not read.
    quiet = {(DOC, 1): PieceCode(1, "Hi", 'st.write("orders")  # orders')}
    assert rules.page_code("Quiet", [B("b1", 1)], quiet, ["orders"]).tables == ()


def test_a_page_says_what_it_cannot_run_and_runs_the_rest() -> None:
    pieces = {
        (DOC, 5): PieceCode(5, "Total", TOTAL, "sales.ipynb @cell5"),
        (DOC, 6): PieceCode(6, "Half", "x = st.slider(\n", "sales.ipynb @cell6"),
        (DOC, 7): PieceCode(7, "Notes", "# Notes\n"),
    }
    placed = [
        B("b1", 5, 1, 1, 6),
        B("b2", 6, 1, 7, 6),
        B("b3", 9, 2, 1, 6),
        B("b4", 7, 2, 7, 6),
        B("b5", 2, 3, 1, 6, None, "/work/gone.ipynb"),
    ]
    # Every Python cell of the linked files: the filter is in the notebook, but not on this page.
    found = {key: rules.facts(p.code) for key, p in pieces.items()} | {(DOC, 4): rules.facts(FILTER)}
    where = {(DOC, 4): "sales.ipynb @cell4"}
    page = Page("p1", "Sales", placed)
    gone = {
        "b3": "sales.ipynb has no cell 9 now: it was deleted. Take the block off the page.",
        "b5": "/work/gone.ipynb is missing: the block links to its cell 2.",
    }
    made = rules.page_code(
        "Sales", placed, pieces, ["orders"], elsewhere=rules.elsewhere(page, found, where), gone=gone
    )
    ast.parse(made.code)
    assert len(made.problems) == 4
    said = "\n".join(made.problems)
    assert (
        "Total reads region (sales.ipynb @cell4), which is not on this page: place that cell here too."
        in said
    )
    assert "Half (sales.ipynb @cell6) is not whole Python yet: line 1" in said
    assert "sales.ipynb has no cell 9 now" in said and "/work/gone.ipynb is missing" in said
    assert "st.metric" not in made.code and "st.slider" not in made.code
    assert "with _slot_b4:\n    try:\n        pass\n" in made.code  # a cell of comments runs nothing
    # A name that is an open table is the table, whatever cell also makes it.
    loads = found | {(DOC, 1): rules.facts("orders = pd.read_csv('orders.csv')")}
    only = Page("p1", "Only", [B("b1", 4)])
    quiet = rules.page_code(
        "Only",
        only.blocks,
        {(DOC, 4): PIECES[(DOC, 4)]},
        ["orders"],
        elsewhere=rules.elsewhere(only, loads, where),
    )
    assert quiet.problems == ()


def test_a_cell_alone_shows_with_the_cells_that_make_its_names() -> None:
    order = [4, 5]
    pieces = {4: PIECES[(DOC, 4)], 5: PIECES[(DOC, 5)]}
    alone = rules.preview_code(5, pieces, order, ["orders"])
    ast.parse(alone.code)
    assert alone.order == ("c4", "c5") and alone.tables == ("orders",)
    assert "st.caption('region comes from cell 4')" in alone.code
    assert alone.code.index("_slot_c4 = st.container()") < alone.code.index("_slot_c5 = st.container()")
    # A cell that reads no other cell's name is alone.
    assert rules.preview_code(4, pieces, order, ["orders"]).order == ("c4",)
    # The nearest maker above wins; one below is used when none is above; inputs of inputs come too.
    more = {
        1: PieceCode(1, "A", "base = 1"),
        2: PieceCode(2, "B", "level = base + st.slider('x', 0, 9)"),
        3: PieceCode(3, "C", "st.write(level)"),
        4: PieceCode(4, "D", "level = 100"),
    }
    found = rules.makers({c: p.code for c, p in more.items()}, [1, 2, 3, 4])
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


def _more_pieces() -> dict[tuple[str, int], PieceCode]:
    return PIECES | {
        (DOC, 6): PieceCode(6, "Chart", CHART, "sales.ipynb @cell6"),
        (DOC, 7): PieceCode(7, "Extra", "import sklearn, os, swissarmygrid"),
    }


def _two_pages() -> list[Page]:
    return [
        Page("p1", "Sales overview", [B("b1", 5, 1, 1, 12), B("b2", 4, 2, 1, 4)]),
        Page("p2", "Sales overview", [B("b3", 6)]),
    ]


def test_the_export_is_a_folder_that_runs_without_the_app() -> None:
    pieces = _more_pieces()
    made = rules.export("Sales app", _two_pages(), pieces, ["orders", "customers"])
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
    # Laid out as designed, blocks in name order, plain code (no guard), data beside app.py.
    assert first.index("with _slot_b2:") < first.index("with _slot_b1:")
    assert "try:" not in first and "swissarmygrid" not in first.lower()
    assert '_DATA = Path(__file__).resolve().parent.parent / "data"' in first
    assert made.tables == ("orders",) and made.problems == ()
    # What the pages import, and only the cells that are on a page.
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
    # A page that cannot run a block says so in the export's answer too.
    found = {key: rules.facts(p.code) for key, p in pieces.items()}
    lone = rules.export(
        "Lone",
        [Page("p1", "Only total", [B("b1", 5)])],
        pieces,
        ["orders"],
        found,
        {(DOC, 4): "sales.ipynb @cell4"},
    )
    assert lone.problems == (
        "Only total: Total reads region (sales.ipynb @cell4), which is not on this page: "
        "place that cell here too.",
    )


# ===== Save as: pages to drop into another Streamlit app =====


def test_save_as_makes_pages_that_import_their_tables_from_data_py() -> None:
    pieces = _more_pieces() | {(DOC, 8): PieceCode(8, "Customers", "st.dataframe(customers)")}
    pages = [*_two_pages(), Page("p3", "Customers", [B("b4", 8)])]
    made = rules.saved_pages(pages, pieces, ["orders", "customers", "regions"], app="sales.stapp.json")
    assert sorted(made.files) == [
        "pages/customers.py",
        "pages/sales_overview.py",
        "pages/sales_overview_2.py",
    ]
    for text in made.files.values():
        ast.parse(text)
    page = made.files["pages/sales_overview.py"]
    # A page of somebody else's app: no app.py, no page config, no data folder, no rows.
    assert page.startswith(
        "# Sales overview\n"
        "# Written from sales.stapp.json by SwissArmyGrid: change the canvas, not this file.\n"
        "import pandas as pd\nimport streamlit as st\n\nfrom data import orders\n"
    )
    # Save as writes over (and takes away) only this app's own saved pages.
    assert rules.is_saved_page(page, "sales.stapp.json")
    assert not rules.is_saved_page(page, "other.stapp.json")
    assert not rules.is_saved_page("import streamlit as st\nst.write('mine')\n", "sales.stapp.json")
    assert "_DATA" not in page and "set_page_config" not in page and "parquet" not in page
    assert page.index("with _slot_b2:") < page.index("with _slot_b1:") and "try:" not in page
    assert "from data import customers\n" in made.files["pages/customers.py"]
    assert made.tables == ("orders", "customers") and made.problems == ()
    assert made.requirements == ("streamlit>=1.36", "pandas", "altair")
    with pytest.raises(rules.StreamlitError, match="no page"):
        rules.saved_pages([], pieces, [])
    # A page that names no table imports nothing from data.py.
    plain = rules.saved_pages(
        [Page("p1", "Hi", [B("b1", 1)])], {(DOC, 1): PieceCode(1, "Hi", "st.write(1)")}, []
    )
    assert "from data" not in plain.files["pages/hi.py"]


def test_the_zips_workbench_files_have_names_of_their_own() -> None:
    names = rules.bundle_names(
        ["/work/sales.ipynb", "/other/sales.ipynb", "C:\\x\\Charts.py", "/work/sales.ipynb"]
    )
    assert names == {
        "/work/sales.ipynb": "sales.ipynb",
        "/other/sales.ipynb": "sales_2.ipynb",
        "C:\\x\\Charts.py": "Charts.py",
    }
    # Never a name the project's own files have in the zip.
    assert rules.bundle_names(["/other/data.py", "/x/Analysis.ipynb"], ["data.py", "analysis.ipynb"]) == {
        "/other/data.py": "data_2.py",
        "/x/Analysis.ipynb": "Analysis_2.ipynb",
    }
