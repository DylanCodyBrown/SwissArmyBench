"""A notebook cell's rules that need no page (web/src/notebookCells.ts, pulled out of the notebook's one
big function): how a run's time is said, a cell as it is saved, which snippets a cell takes. Run by Node as
the page runs them. Made-up cells."""

from __future__ import annotations

from typing import Any

import pytest

from tests.web_unit import bundled, needs_node

pytestmark = needs_node

# A drawn cell hands its outputs and its pane's height over as functions, which JSON cannot carry: a small
# caller makes one from plain data.
CALLER = """
import { cellData } from "@module";
export function saved(cell: any, source: string) {
  const design = cell.height === undefined ? null : { height: () => cell.height };
  return cellData({ ...cell, area: { outputs: () => cell.outputs ?? [] }, design }, source);
}
"""


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return bundled(tmp_path_factory.mktemp("notebook-cells"), "notebookCells.ts", CALLER)


def cell(**given: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "code",
        "connection": None,
        "execution_count": 3,
        "number": 7,
        "role": "",
        "table": None,
        "grouped": False,
        "steps": None,
        "name": None,
        "outputs": [{"output_type": "stream", "text": "made-up"}],
    }
    return base | given


def test_a_runs_time_as_its_head_says_it(run: Any) -> None:
    asked = [0.2, 320, 999.4, 1000, 4200, 59_949, 60_000, 125_000, 3_600_000]
    assert run(*[["runTime", ms] for ms in asked]) == [
        "1 ms",
        "320 ms",
        "999 ms",
        "1.0 s",
        "4.2 s",
        "59.9 s",
        "1 min 0 s",
        "2 min 5 s",
        "60 min 0 s",
    ]


def test_a_cell_as_it_is_saved(run: Any) -> None:
    code, sql, text, html, table, tsx = run(
        ["saved", cell(), "x = 1"],
        ["saved", cell(kind="sql", connection="Shop", name="orders by day"), "select 1"],
        ["saved", cell(kind="markdown", connection="Shop"), "# Notes"],
        ["saved", cell(kind="html", height=320, htmlRun={"output": {"output_type": "display_data"}}), "<b>"],
        ["saved", cell(role="transformations", table="orders", steps=[{"type": "filter"}]), "..."],
        ["saved", cell(kind="tsx", height=200), "<App />"],
    )
    # Its text as it stands, its own number and run count; a Python cell names no connection and has no pane.
    assert (code["source"], code["number"], code["execution_count"]) == ("x = 1", 7, 3)
    assert code["connection"] is None and code["height"] is None and "name" not in code
    assert code["outputs"] == [{"output_type": "stream", "text": "made-up"}] and code["steps"] is None
    # A SQL cell keeps the connection picked in its head, and its name when it has one.
    assert sql["connection"] == "Shop" and sql["name"] == "orders by day"
    # A Markdown cell keeps no output and no connection.
    assert text["outputs"] == [] and text["connection"] is None
    # An HTML cell keeps its last run's filled design and its pane's height.
    assert html["outputs"] == [{"output_type": "display_data"}] and html["height"] == 320
    assert run(["saved", cell(kind="html", height=None), ""])[0]["outputs"] == []
    # A table's read-only cell keeps its steps and no rows (its table is drawn again on opening).
    assert table["outputs"] == [] and table["steps"] == [{"type": "filter"}] and table["table"] == "orders"
    assert tsx["height"] == 200


def test_which_snippets_a_cell_takes_and_which_cells_are_the_apps_own(run: Any) -> None:
    kinds = ["code", "sql", "dax", "html", "markdown", "tsx"]
    assert run(*[["snippetLanguage", {"kind": k, "role": ""}] for k in kinds]) == [
        "streamlit",
        None,
        "dax",
        "html",
        "markdown",
        None,
    ]
    assert run(["snippetLanguage", {"kind": "code", "role": "transformations"}]) == [None]
    roles = ["", "maker", "imports", "tables", "table", "transformations"]
    assert run(*[["isApp", r] for r in roles]) == [False, False, False, True, True, True]
    assert run(*[["isHeading", r] for r in roles]) == [False, False, False, True, True, False]
    assert run(*[["hasSource", k] for k in kinds]) == [False, True, True, False, False, False]
    assert run(*[["drawn", k] for k in kinds]) == [False, False, False, True, False, False]


def test_a_sql_cells_first_line_as_the_kernel_runs_it(run: Any) -> None:
    assert run(
        ["sqlLine", None], ["sqlLine", "Shop"], ["sqlLine", "Finance Captive"], ["sqlLine", "Dan's db"]
    ) == [
        "%%sql",
        "%%sql Shop",
        "%%sql 'Finance Captive'",
        "%%sql 'Dan'\"'\"'s db'",
    ]


def test_whether_code_makes_a_name(run: Any) -> None:
    makes = [
        "orders = load()",
        "a, orders = 1, 2",
        "orders, b = 1, 2",
        "def orders():\n    pass",
        "class orders:\n    pass",
        "import pandas as orders",
        "from shop import orders",
        "import orders",
        "x = 1\n  orders = 2",
        "for orders in batches:\n    pass",
    ]
    reads = [
        "print(orders)",
        "orders == 3",
        "my_orders = 1",
        "# orders = 1 is said, never made",
        "orders2 = 1",
    ]
    assert run(*[["makesName", "orders", code] for code in makes]) == [True] * len(makes)
    assert run(*[["makesName", "orders", code] for code in reads]) == [False] * len(reads)
    # A name with a character a pattern would read is taken as written.
    assert run(["makesName", "a.b", "a.b = 1"], ["makesName", "a.b", "axb = 1"]) == [True, False]


def key(name: str, **held: bool) -> dict[str, Any]:
    return {"key": name, "shift": False, "ctrl": False, "meta": False, "alt": False} | held


def test_what_a_key_does_in_command_mode(run: Any) -> None:
    asked = {
        "Enter": "edit",
        "a": "above",
        "B": "below",
        "d": "d",
        "y": "code",
        "m": "markdown",
        "s": "sql",
        "x": "dax",
        "h": "html",
        "c": "copy",
        "v": "paste",
        "z": "undo",
        "j": "down",
        "ArrowDown": "down",
        "k": "up",
        "ArrowUp": "up",
        "o": "output",
        "q": None,
        "Escape": None,
    }
    assert run(*[["commandFor", key(k), ""] for k in asked]) == list(asked.values())
    # Enter runs with Shift (and goes on) or Ctrl; on a heading's line it folds.
    assert run(
        ["commandFor", key("Enter", shift=True), ""],
        ["commandFor", key("Enter", ctrl=True), ""],
        ["commandFor", key("Enter", meta=True), ""],
        ["commandFor", key("Enter", alt=True), ""],
        ["commandFor", key("Enter"), "tables"],
        ["commandFor", key("Enter"), "table"],
        ["commandFor", key("Enter"), "transformations"],
    ) == ["runNext", "run", "run", None, "fold", "fold", "edit"]
    # The browser's own keys stay the browser's (Ctrl+C, Ctrl+Z), and Shift+A is not A.
    assert run(
        ["commandFor", key("c", ctrl=True), ""],
        ["commandFor", key("z", meta=True), ""],
        ["commandFor", key("A", shift=True), ""],
        ["commandFor", key("X", shift=True), ""],
        ["commandFor", key("M", shift=True), ""],
    ) == [None, None, None, None, "markdown"]
    # One of the app's own cells keeps its kind; it is still deleted (D D asks) and passed over.
    kinds = ["y", "m", "s", "x", "h"]
    assert run(*[["commandFor", key(k), "transformations"] for k in kinds]) == [None] * 5
    assert run(["commandFor", key("d"), "transformations"], ["commandFor", key("j"), "tables"]) == [
        "d",
        "down",
    ]


def test_a_cells_mark_from_the_run_order(run: Any) -> None:
    assert run(
        ["flowWords", None],
        ["flowWords", {"state": "current", "because": []}],
        ["flowWords", {"state": "edited", "because": []}],
        ["flowWords", {"state": "outOfDate", "because": ["orders", "rates"]}],
        ["flowWords", {"state": "outOfDate", "because": []}],
    ) == [
        {"words": "", "title": ""},
        {"words": "", "title": ""},
        {"words": "edited", "title": ""},
        {"words": "out of date", "title": "Made again since it ran: orders, rates"},
        {"words": "out of date", "title": ""},
    ]
