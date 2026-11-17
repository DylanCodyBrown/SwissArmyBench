"""A table's connection swapped (domain/connection_swap.py): matching a table in the other connection's
catalog, the query check, and the code pointed at the new connection (the name only). Made-up names."""

from __future__ import annotations

import json

import pytest

from swissarmybench.domain import connection_swap as swap
from swissarmybench.domain.connection_swap import Place, SwapError


def test_a_table_is_found_by_its_name_in_any_case_and_its_schema_breaks_a_tie() -> None:
    old = Place("", "SALES", "ORDERS")
    candidates = [
        Place("hive", "sales", "orders"),
        Place("hive", "archive", "orders"),
        Place("hive", "sales", "items"),
    ]
    found, named = swap.match_place(old, candidates)
    assert found == Place("hive", "sales", "orders")
    assert len(named) == 2


def test_an_odbc_database_matches_trinos_catalog() -> None:
    old = Place("hive", "", "orders")
    found, _ = swap.match_place(old, [Place("hive", "sales", "orders"), Place("iceberg", "sales", "orders")])
    assert found == Place("hive", "sales", "orders")


def test_a_tie_or_no_table_asks_the_user_to_pick() -> None:
    found, named = swap.match_place(
        Place("", "x", "orders"), [Place("a", "s", "orders"), Place("b", "s", "orders")]
    )
    assert found is None and len(named) == 2
    assert swap.match_place(Place("", "", "orders"), [Place("", "main", "customers")]) == (None, [])


def test_only_one_read_query_runs() -> None:
    assert swap.check_read_query("-- the orders\nSELECT * FROM orders;").startswith("--")
    assert swap.check_read_query("WITH a AS (SELECT 1) SELECT * FROM a")
    assert swap.check_read_query("EVALUATE 'Sales'")
    assert swap.check_read_query("SELECT ';' AS semi")
    for bad in ("DELETE FROM orders", "SELECT 1; DROP TABLE orders", "", "  "):
        with pytest.raises(SwapError):
            swap.check_read_query(bad)


def test_the_name_only_changes_its_other_words_kept() -> None:
    assert swap.renamed("EDP", "EDP", "Trino") == "Trino"
    assert swap.renamed("edp -> orders", "EDP", "Trino") == "Trino -> orders"
    assert swap.renamed("EDP/Sales model", "EDP", "Trino") == "Trino/Sales model"
    assert swap.renamed("EDP2", "EDP", "Trino") == "EDP2"


def test_python_calls_are_pointed_at_the_new_connection_and_other_strings_are_not() -> None:
    code = (
        "import swissarmybench as sab\n"
        "from swissarmybench import read as fetch\n"
        "note = 'EDP is gone'  # EDP\n"
        'orders = sab.sql("EDP", "SELECT * FROM orders")\n'
        "items = fetch('EDP', 'items')\n"
        "label = sab.sql(connection='EDP', query='SELECT 1')\n"
        "other = sab.sql('Warehouse', 'SELECT 2')\n"
        "print('EDP')\n"
    )
    after, count = swap.repoint_python(code, "EDP", "Trino")
    assert count == 3
    assert 'sab.sql("Trino", "SELECT * FROM orders")' in after
    assert "fetch('Trino', 'items')" in after
    assert "connection='Trino'" in after
    assert "note = 'EDP is gone'  # EDP" in after
    assert "print('EDP')" in after
    assert "sab.sql('Warehouse', 'SELECT 2')" in after


def test_magics_are_left_and_non_ascii_text_keeps_its_place() -> None:
    code = "%load_ext swissarmybench\nimport swissarmybench as sab\nx = 'café'; y = sab.read('EDP', 't')\n"
    after, count = swap.repoint_python(code, "EDP", "Trino")
    assert count == 1
    assert after == code.replace("'EDP'", "'Trino'")


def test_a_sql_cells_line_and_a_dax_cells_line() -> None:
    assert swap.repoint_line("%%sql EDP", "EDP", "Trino") == "%%sql Trino"
    assert swap.repoint_line("%%sql EDP -> orders", "EDP", "Trino") == "%%sql 'Trino -> orders'"
    assert swap.repoint_line("%%sql Warehouse", "EDP", "Trino") == "%%sql Warehouse"
    assert (
        swap.repoint_line("%%dax 'Old BI/Sales model'", "Old BI", "Power BI")
        == "%%dax 'Power BI/Sales model'"
    )


def _notebook(cells: list[tuple[str, int, str]]) -> str:
    return json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": kind,
                    "source": source,
                    "metadata": {"swissarmybench": {"number": number}},
                    **({"outputs": [], "execution_count": None} if kind == "code" else {}),
                }
                for kind, number, source in cells
            ],
        }
    )


def test_a_notebooks_ticked_cells_only() -> None:
    text = _notebook(
        [
            ("code", 1, "%%sql EDP\nSELECT * FROM orders"),
            ("code", 2, "import swissarmybench as sab\nx = sab.sql('EDP', 'SELECT 1')"),
            ("code", 3, "print('EDP')"),
            ("markdown", 4, "Read from EDP"),
            ("code", 5, "%%sql EDP\nSELECT 2"),
        ]
    )
    after, changed = swap.repoint_notebook(text, "EDP", "Trino", {1, 2, 3, 4})
    assert changed == [1, 2]
    cells = json.loads(after)["cells"]
    assert "".join(cells[0]["source"]).startswith("%%sql Trino\n")
    assert "sab.sql('Trino'" in "".join(cells[1]["source"])
    assert "".join(cells[2]["source"]) == "print('EDP')"
    assert "".join(cells[3]["source"]) == "Read from EDP"
    assert "".join(cells[4]["source"]).startswith("%%sql EDP")
    # Every cell, unticked: all of them.
    assert swap.repoint_notebook(text, "EDP", "Trino")[1] == [1, 2, 5]


def test_a_scripts_cells_and_its_tables_group_left_to_the_app() -> None:
    text = (
        "import swissarmybench as sab\n"
        "# region Tables\n"
        "# %% [1] [table] orders\n"
        "orders = sab.sql('EDP', 'SELECT * FROM orders')\n"
        "# endregion\n"
        "# %%\n"
        "a = sab.sql('EDP', 'SELECT 1')\n"
        "# %% [4] totals\n"
        "b = sab.sql('EDP', 'SELECT 2')\n"
        "# %% [5]\n"
        "c = sab.read('EDP', 'items')\n"
    )
    after, changed = swap.repoint_script(text, "EDP", "Trino", {4, 5})
    assert changed == [4, 5]
    assert "orders = sab.sql('EDP'" in after
    assert "a = sab.sql('EDP'" in after
    assert "b = sab.sql('Trino'" in after and "c = sab.read('Trino'" in after
    every, cells = swap.repoint_script(text, "EDP", "Trino")
    assert cells == [None, 4, 5] and "orders = sab.sql('EDP'" in every
