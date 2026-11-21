"""A connection's usage (domain/connection_usage.py): where notebooks, scripts and Streamlit apps name it,
the calls this session, the card's word, and the settings the configuration shows. Made-up names."""

from __future__ import annotations

import json
from typing import Any

import pytest

from swissarmybench.domain import connection_usage as usage
from swissarmybench.domain import notebooks


def _plain(cells: list[notebooks.Cell]) -> str:
    raw: list[dict[str, Any]] = []
    for n, cell in enumerate(cells, start=1):
        meta = {"swissarmybench": {"cell": n}}
        if cell.kind == "markdown":
            raw.append({"cell_type": "markdown", "metadata": meta, "source": cell.source})
            continue
        source = cell.source
        if cell.kind == "sql":
            source = f"{notebooks.sql_line(cell.connection)}\n{cell.source}"
        elif cell.kind == "dax":
            source = f"{notebooks.dax_line(cell.connection)}\n{cell.source}"
        raw.append(
            {"cell_type": "code", "metadata": meta, "source": source, "outputs": [], "execution_count": None}
        )
    return json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": raw})


def test_python_calls_name_the_connection_and_nothing_else_does() -> None:
    code = "\n".join(
        [
            "import swissarmybench as sab",
            "# sab.sql('Warehouse', 'SELECT 1') in a comment is no use",
            "note = \"sab.blade('Warehouse')\"  # nor a string that says it",
            "orders = sab.sql('Warehouse', 'SELECT * FROM orders')",
            "conn = sab.connection(name='warehouse')",
            "rows = sab.read('Orders API', 'orders')",
            "sales = sab.dax('Finance/Sales model', \"EVALUATE 'Sales'\")",
            "other = sab.sql('Warehouse archive', 'SELECT 1')",
            "frame.read('Warehouse')",
        ]
    )
    found = usage.python_uses(code, "Warehouse")
    assert [u.how for u in found] == ["sab.sql", "sab.connection"]
    assert found[0].line.startswith("orders = sab.sql(")
    assert [u.how for u in usage.python_uses(code, "Orders  api")] == ["sab.read"]
    assert [u.how for u in usage.python_uses(code, "Finance")] == ["sab.dax"]


def test_an_alias_and_a_function_imported_by_name_are_uses_and_magics_do_not_break_it() -> None:
    code = "\n".join(
        [
            "%load_ext swissarmybench",
            "import swissarmybench as bench",
            "from swissarmybench import blade as run",
            "bench.blade('Ledger')",
            "run('Ledger')",
            "!echo hello",
        ]
    )
    assert [u.how for u in usage.python_uses(code, "Ledger")] == ["sab.blade", "sab.blade"]
    assert usage.python_uses("def broken(:\n  sab.sql('Ledger', 'x')", "Ledger") == []


def test_sql_and_dax_cells_are_found_by_their_first_line() -> None:
    text = _plain(
        [
            notebooks.Cell("sql", "SELECT * FROM orders", "Warehouse"),
            notebooks.Cell("dax", "EVALUATE 'Sales'", "Finance/Sales model"),
            notebooks.Cell("markdown", "Uses %%sql Warehouse in its words only"),
            notebooks.Cell("code", "x = sab.sql('Warehouse', 'SELECT 2')"),
            notebooks.Cell("sql", "SELECT 1", "Warehouse archive"),
        ]
    )
    found = usage.notebook_references("/work/orchard.ipynb", "orchard.ipynb", text, "warehouse")
    assert [(r.how, r.cell, r.kind) for r in found] == [("%%sql", 1, "notebook"), ("sab.sql", 4, "notebook")]
    assert found[0].line == "%%sql Warehouse"
    dax = usage.notebook_references("/work/orchard.ipynb", "orchard.ipynb", text, "Finance")
    assert [(r.how, r.line) for r in dax] == [("%%dax", "%%dax 'Finance/Sales model'")]


def test_a_script_cell_and_a_tables_load_are_found_and_the_table_cell_is_told_apart() -> None:
    text = "\n".join(
        [
            "import swissarmybench as sab",
            "# region Tables",
            "# %% [3] [table] orders",
            "orders = sab.sql('Warehouse', 'SELECT * FROM orders')",
            "# endregion",
            "# %%",
            "",
            "# %% [5] Totals",
            "totals = sab.sql('Warehouse', 'SELECT 1')",
            "",
        ]
    )
    found = usage.script_references("/work/totals.py", "totals.py", text, "Warehouse")
    assert [(r.cell, r.kind) for r in found] == [(3, "script"), (5, "script")]
    assert found[1].name == "Totals"


def test_the_calls_count_by_kind_and_the_card_word_follows_them() -> None:
    calls = None
    assert usage.status(calls, [], False) == "ready"
    assert usage.status(calls, ["WAREHOUSE_PASSWORD"], False) == "needs"
    calls = usage.record(calls, usage.call_kind("rows"), True, 10.0)
    calls = usage.record(calls, usage.call_kind("sql"), True, 12.0)
    calls = usage.record(calls, "query", True, 13.0)
    assert calls.to_json() == {
        "total": 3,
        "by_kind": {"catalog": 0, "query": 2, "read": 1, "test": 0, "connect": 0},
        "last_used": 13.0,
        "last_kind": "query",
        "last_ok": True,
    }
    assert usage.status(calls, [], False) == "works"
    assert usage.status(calls, [], True) == "failing"
    assert usage.status(usage.record(calls, "test", False, 14.0), [], False) == "failing"
    with pytest.raises(ValueError):
        usage.call_kind("delete everything")


def test_the_configuration_never_shows_a_setting_that_may_be_a_password() -> None:
    fields: list[dict[str, Any]] = [
        {"name": "server", "value": "db.example.test"},
        {"name": "port", "value": 5432},
        {"name": "password", "value": "made-up-secret"},
        {"name": "api_key", "value": "made-up-key"},
        {"name": "dsn", "value": "Server=db.example.test;Pwd=made-up-secret"},
    ]
    assert usage.shown_settings(fields) == [
        {"name": "server", "value": "db.example.test"},
        {"name": "port", "value": 5432},
    ]
    ways = [
        {"label": "Windows", "mark": "Trusted_Connection"},
        {"label": "User name and password", "mark": "UID="},
    ]
    assert usage.sign_in_of("conn = connect('UID=' + user)", ways) == "User name and password"
    assert usage.sign_in_of("x = 1", ways) is None


def test_a_workbench_kernel_reports_a_call_and_other_pythons_do_not(monkeypatch: pytest.MonkeyPatch) -> None:
    from swissarmybench.client import connection_use

    sent: list[tuple[str, str, bool]] = []

    class Now:
        def __init__(self, target: Any, args: tuple[str, str, bool], **_: Any) -> None:
            self.args = args

        def start(self) -> None:
            sent.append(self.args)

    monkeypatch.setattr("threading.Thread", Now)
    monkeypatch.delenv("SWISSARMYBENCH_KERNEL", raising=False)
    connection_use.report("Warehouse", "query")
    assert sent == []  # the user's own Jupyter, a terminal: not counted
    monkeypatch.setenv("SWISSARMYBENCH_KERNEL", "k1")
    connection_use.report("Finance/Sales model", "query")
    connection_use.report("Orders API", "read", ok=False)
    assert sent == [("Finance", "query", True), ("Orders API", "read", False)]
