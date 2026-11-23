"""The Environment's rules that need no page (web/src/environmentRules.ts, pulled out of environmentPage.ts's
one big function): which letters a search marks, an empty tab's line, what Remove says it will do, the
session line about the project's Python, the row the arrow keys move to. Run by Node as the page runs them.
Made-up names."""

from __future__ import annotations

from typing import Any

import pytest

from tests.web_unit import bundled, needs_node

pytestmark = needs_node


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return bundled(tmp_path_factory.mktemp("environment-rules"), "environmentRules.ts")


def test_a_search_marks_the_shortest_stretch_that_spells_each_word(run: Any) -> None:
    assert run(
        ["markSpans", "customer_id", "cust"],
        ["markSpans", "CustomerKey", "customerkey"],
        ["markSpans", "customer_id", "customerid"],
        ["markSpans", "orders", "zzz"],
        ["markSpans", "order_lines", "lines order"],
        ["markSpans", "anything", ""],
    ) == [[[0, 4]], [[0, 11]], [[0, 11]], [], [[0, 5], [6, 11]], []]


def test_an_empty_tabs_line(run: Any) -> None:
    searched, tables, libraries = run(
        ["emptyWords", "variable", "revenue"], ["emptyWords", "table", ""], ["emptyWords", "library", ""]
    )
    assert searched == "Nothing in Variables matches “revenue”."
    assert tables.startswith("No tables yet.")
    assert "Install a library" in libraries


def test_what_remove_says_it_will_do(run: Any) -> None:
    table = {"kind": "table", "open": True, "grids": [{"id": "g1", "name": "orders", "steps": 0}], "from": ""}
    assert run(
        ["removeWords", table, "1 grid"],
        ["removeWords", {**table, "grids": []}, "0 grids"],
        ["removeWords", {**table, "open": None}, "0 grids"],
        [
            "removeWords",
            {"kind": "structure", "saved": True, "from": "structures/order.json", "grids": []},
            "",
        ],
        ["removeWords", {"kind": "structure", "saved": False, "from": "", "grids": []}, ""],
    ) == [
        "The table closes with 1 grid; its source is not touched.",
        "The table closes with no grid; its source is not touched.",
        "It is a table in Python only.",
        "Its file structures/order.json is deleted from the project.",
        "The open structure closes; it was never saved.",
    ]


def test_the_session_line_names_the_python_the_code_runs_in(run: Any) -> None:
    assert run(
        ["pythonWords", {"version": "3.12.4", "own": True}, {"name": "Sales"}],
        ["pythonWords", {"version": "3.12.4", "status": "making"}, {"name": "Sales"}],
        ["pythonWords", {"version": "3.12.4"}, {"name": "Sales"}],
        ["pythonWords", {"version": "3.12.4"}, None],
    ) == [
        "Python 3.12.4 · the project's own (.venv)",
        "Python 3.12.4 · this app's own (the project's is being made)",
        "Python 3.12.4 · this app's own (the project has no .venv yet)",
        "Python 3.12.4 · this app's own",
    ]


def test_the_arrow_keys_stop_at_the_ends(run: Any) -> None:
    ids = ["table:a", "table:b", "table:c"]
    assert run(
        ["stepped", ids, None, "ArrowDown"],
        ["stepped", ids, "table:a", "ArrowDown"],
        ["stepped", ids, "table:c", "ArrowDown"],
        ["stepped", ids, "table:a", "ArrowUp"],
        ["stepped", ids, "table:b", "ArrowUp"],
        ["stepped", ids, None, "ArrowUp"],
        ["stepped", [], None, "ArrowDown"],
    ) == ["table:a", "table:b", "table:c", "table:a", "table:a", "table:a", None]
