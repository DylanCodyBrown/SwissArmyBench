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
