"""A script's cells as text, the rules that need no page (web/src/scriptCells.ts, pulled out of the script's
one big function): its numbered cells read from its markers, where a new cell goes, a marker with a pane's
height or a name on it, a cell's lines replaced, a table renamed, a table's cell run the safe way. Run by
Node as the page runs them. Made-up scripts."""

from __future__ import annotations

from typing import Any

import pytest

from tests.web_unit import bundled, needs_node

pytestmark = needs_node

# A table's name in Python is a function, which JSON cannot carry: a small caller gives one.
CALLER = """
import { safeBlock } from "@module";
export function safe(block: string, start: number, end: number, cells: any[]) {
  return safeBlock(block, start, end, cells, (table) => table.replace(/\\W/g, "_"));
}
"""

SCRIPT = "\n".join(
    [
        "import pandas as pd",
        "# %% [1] Load the orders",
        "orders = pd.DataFrame({'id': [1, 2]})",
        "",
        "# %% [2] [html] height=200",
        'r"""',
        "<b>{{ total }}</b>",
        '"""',
        "# %% [3]",
        "total = len(orders)",
        "",
    ]
)


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return bundled(tmp_path_factory.mktemp("script-cells"), "scriptCells.ts", CALLER)


def test_a_scripts_numbered_cells_from_its_markers(run: Any) -> None:
    grouped = (
        "# region Tables\n# %% [9] [transformations] orders\norders = orders\n# endregion\n# %%\n" + SCRIPT
    )
    (pieces,) = run(["scriptPieces", grouped])
    assert pieces == [
        {"cell": 1, "code": "orders = pd.DataFrame({'id': [1, 2]})", "name": "Load the orders"},
        {"cell": 2, "code": 'r"""\n<b>{{ total }}</b>\n"""', "kind": "html", "form": "script"},
        {"cell": 3, "code": "total = len(orders)"},
    ]
    # Lines before the first marker and a cell with no code are no cell.
    assert run(["scriptPieces", "x = 1\n# %% [4]\n\n"]) == [[]]


def test_the_indent_lines_share_and_two_paths_of_one_file(run: Any) -> None:
    block = "    if x:\n        y = 1\n\n    z = 2"
    assert run(["sharedIndent", block], ["sharedIndent", "\n\n"], ["dedent", block]) == [
        4,
        0,
        "if x:\n    y = 1\n\nz = 2",
    ]
    assert run(
        ["sameFile", "C:\\Work\\load.py", "c:/work/Load.py"],
        ["sameFile", "/work/load.py", "/work/other.py"],
        ["sameFile", None, "/work/load.py"],
    ) == [True, False, False]


def test_a_new_cell_goes_after_the_cursors_cell_or_at_the_end(run: Any) -> None:
    cell = ["# %% [html]", 'r"""', "<p>hello</p>", '"""']
    at_end, in_code, before_marker = run(
        ["withCell", SCRIPT, None, cell],
        ["withCell", "a = 1\n\nb = 2\n", 1, cell],
        ["withCell", SCRIPT, 4, cell],
    )
    # At the end: after the last line, one newline closing the file.
    assert at_end["at"] == 10 and at_end["text"] == SCRIPT.rstrip("\n") + "\n" + "\n".join(cell) + "\n"
    # What follows is the user's Python: a plain marker keeps it a cell of its own.
    assert in_code == {"text": "\n".join(["a = 1", *cell, "# %%", "", "b = 2"]) + "\n", "at": 1}
    # Before a marker, nothing closes it.
    assert before_marker["text"].split("\n")[4:9] == [*cell, "# %% [2] [html] height=200"]
    # A cursor's cell that ends past the text is the end.
    assert run(["withCell", "x = 1\n", 40, ["# %%", "y = 2"]]) == [{"text": "x = 1\n# %%\ny = 2\n", "at": 1}]


def test_a_dax_cell_is_one_call_and_brings_its_import_once(run: Any) -> None:
    first, again, empty = run(
        ["daxCell", "x = 1\n", "Finance/Sales model", 'EVALUATE ROW("a", 1)\n'],
        ["daxCell", "import swissarmybench as sab\n", "Finance/Sales model", 'EVALUATE """x"""'],
        ["daxCell", "", "Sales", "  "],
    )
    assert first == {
        "lines": [
            "# %% [dax]",
            "import swissarmybench as sab",
            'result = sab.dax("Finance/Sales model", """',
            'EVALUATE ROW("a", 1)',
            '""")',
        ],
        "imported": 1,
        "first": 'EVALUATE ROW("a", 1)',
    }
    assert again["imported"] == 0 and again["lines"][2] == 'EVALUATE \\"\\"\\"x\\"\\"\\"'
    assert empty["first"] == "EVALUATE " and empty["lines"][2:] == [
        'result = sab.dax("Sales", """',
        "EVALUATE ",
        '""")',
    ]


def test_a_markers_height_and_name(run: Any) -> None:
    sized, bare, by_line, none, clamped = run(
        ["withHeight", SCRIPT, 2, 5, 320],
        ["withHeight", SCRIPT, 2, 5, None],
        ["withHeight", "# %% [html] [streamlit] height=90 Banner\nr'''x'''", None, 1, 120],
        ["withHeight", SCRIPT, 8, 1, 320],
        ["paneHeight", 12.4],
    )
    assert sized.split("\n")[4] == "# %% [2] [html] height=320"
    assert bare.split("\n")[4] == "# %% [2] [html]"
    assert by_line.split("\n")[0] == "# %% [html] height=120 Banner"
    assert none is None and clamped == 60
    assert run(["paneHeight", 5000], ["paneHeight", 300.6]) == [2000, 301]
    named, cleared, missing = run(
        ["withName", SCRIPT, 3, "Totals"], ["withName", SCRIPT, 1, ""], ["withName", SCRIPT, 7, "x"]
    )
    assert named.split("\n")[8] == "# %% [3] Totals"
    assert cleared.split("\n")[1] == "# %% [1]" and missing is None


def test_a_cells_lines_replaced_under_its_marker(run: Any) -> None:
    middle, last, missing = run(
        ["withSource", SCRIPT, 1, "orders = load()\nprint(orders)\n\n"],
        ["withSource", SCRIPT, 3, "total = 0"],
        ["withSource", SCRIPT, 9, "x"],
    )
    # The blank line before the next marker stays, as typed.
    assert middle.split("\n")[1:6] == [
        "# %% [1] Load the orders",
        "orders = load()",
        "print(orders)",
        "",
        "# %% [2] [html] height=200",
    ]
    assert last.split("\n")[8:] == ["# %% [3]", "total = 0"]
    assert missing is None


def test_a_tables_markers(run: Any) -> None:
    text = (
        "# region Tables\n# %% [7] [table] orders\n# %% [8] [transformations] orders\nx = 1\n"
        "# %% [9] [transformations] orders-2023\n"
    )
    assert run(
        ["holdsTableCell", text, "orders"],
        ["holdsTableCell", text, "order"],
        ["holdsTableCell", text, "customers"],
        ["tablesInFile", text],
    ) == [True, False, False, ["orders", "orders-2023"]]
    (renamed,) = run(["renamedTable", text, "orders", "sales"])
    # The table's own markers follow; another table whose name starts the same does not.
    assert renamed.split("\n")[1:5] == [
        "# %% [7] [table] sales",
        "# %% [8] [transformations] sales",
        "x = 1",
        "# %% [9] [transformations] orders-2023",
    ]


def test_the_next_line_with_code(run: Any) -> None:
    text = "x = 1\n\n# a note\n   \ny = 2\n# the end"
    assert run(["nextCodeLine", text, 1], ["nextCodeLine", text, 4], ["nextCodeLine", text, 5]) == [5, 5, 6]


def test_a_tables_cell_inside_lines_runs_the_safe_way(run: Any) -> None:
    block = (
        "a = 1\n# %% [8] [transformations] my orders\norders = orders[orders.id > 1]\n"
        "orders = orders.head()\nb = 2"
    )
    cells = [
        {"role": "transformations", "table": "my orders", "line": 2, "end": 4},
        {"role": "", "table": None, "line": 1, "end": 1},
    ]
    (safe,) = run(["safe", block, 1, 5, cells])
    lines = safe.split("\n")
    assert lines[0] == "a = 1" and lines[1].startswith("# %% [8]") and lines[3] == "" and lines[4] == "b = 2"
    assert lines[2] == (
        "__import__('swissarmybench.client.table_cells', fromlist=['run'])"
        '.run("my_orders", "orders = orders[orders.id > 1]\\norders = orders.head()")'
    )
    # A cell only partly inside the lines runs as written, and so do lines that start past line 1.
    assert run(["safe", "\n".join(block.split("\n")[:3]), 1, 3, cells]) == ["\n".join(block.split("\n")[:3])]
    (later,) = run(["safe", "\n".join(block.split("\n")[1:]), 2, 5, cells])
    assert later.split("\n")[1].startswith("__import__(") and later.split("\n")[2] == ""
