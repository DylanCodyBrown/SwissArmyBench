"""Projects' rules (docs/ideas.md, 2026-11-15): data.py as the export of data.ipynb's code cells,
importing in a plain Python with no Streamlit; what is left out; a stub for a table the app cannot
read again; a notebook for a zip without a pasted table's rows; requirements.txt keeping the user's
lines; which of a folder's files open. Made-up data only."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import projects as rules
from swissarmybench.domain.projects import DataCell


def _import(path: Path, show: str) -> Any:
    """Import a data.py in a Python of its own (as a kernel or a page would: this process's DuckDB
    may be the app's locked one) and give back `show`, an expression over the module `data`."""
    code = (
        "import json, sys\nsys.path.insert(0, sys.argv[1])\nimport data\n"
        f"print(json.dumps({show}))\nprint('streamlit' in sys.modules)"
    )
    done = subprocess.run(  # noqa: S603 (this Python, on a file the test wrote)
        [sys.executable, "-c", code, str(path.parent)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    shown, streamlit = done.stdout.strip().splitlines()[-2:]
    assert streamlit == "False"  # this Python has none: nothing of it is needed
    return json.loads(shown)


def _cells(csv: Path) -> list[DataCell]:
    table = (
        f"import duckdb\n\norders = duckdb.read_csv({str(csv)!r}).df()\n\n"
        'orders = duckdb.sql("""\nSELECT *\nFROM orders\nWHERE amount > 50\n""").df()'
    )
    return [
        DataCell("markdown", "# Tables", "tables"),
        DataCell("markdown", "## orders", "table", "orders"),
        DataCell("code", table, "transformations", "orders", 2),
        DataCell("markdown", "Notes for me"),
        DataCell("code", "# uses orders @cell2\nbig = orders[orders['amount'] > 200]\nTAX = 0.2", number=3),
        DataCell("code", "%matplotlib inline\nrate = TAX * 2", number=4),
        DataCell("sql", "select 1", number=5),
        DataCell("code", "st.dataframe(orders)", number=6),
        DataCell("code", "", number=7),
    ]


def test_data_py_is_data_ipynbs_code_cells_in_order_and_imports_in_a_plain_python(tmp_path: Path) -> None:
    csv = tmp_path / "orders.csv"
    csv.write_text("region,amount\nEast,100\nWest,250\nEast,40\n")
    made = rules.data_module("sales", _cells(csv))
    ast.parse(made.text)
    text = made.text
    assert made.names == ("orders", "big", "TAX", "rate") and made.fill_in == ()
    assert "from data import orders, big" in text and "Do not edit: change data.ipynb." in text
    # The cells in order, each under its number; the table's cell as it stands (the SQL not indented).
    assert text.index("# cell 2: orders") < text.index("# cell 3") < text.index("# cell 4")
    assert "\nSELECT *\nFROM orders\nWHERE amount > 50\n" in text
    # Left out: Markdown, the SQL cell, the cell that calls Streamlit, IPython's own line, the uses line.
    assert "Notes for me" not in text and "select 1" not in text and "st.dataframe" not in text
    assert "    # %matplotlib inline\n    rate = TAX * 2" in text and "# uses" not in text
    assert [s.split(":")[0] for s in made.skipped] == ["cell 4", "cell 5", "cell 6"]
    (tmp_path / "data.py").write_text(text)
    shown = _import(
        tmp_path / "data.py", "[list(data.orders['amount']), list(data.big['region']), data.rate, data.TAX]"
    )
    assert shown == [[100, 250], ["West"], 0.4, 0.2]
    # Nothing to export: a head that still imports.
    empty = rules.data_module("sales", [DataCell("markdown", "# hi")])
    ast.parse(empty.text)
    assert empty.names == ()


def test_code_that_cannot_sit_in_a_function_runs_as_the_module(tmp_path: Path) -> None:
    made = rules.data_module("x", [DataCell("code", "from math import *\nroot = sqrt(16)", number=1)])
    assert "def _load" not in made.text and made.names == ("root",)
    (tmp_path / "data.py").write_text(made.text)
    assert _import(tmp_path / "data.py", "data.root") == 4


PASTED = (
    'import duckdb\n\ncustomers = duckdb.sql("""SELECT\n    CAST(c1 AS VARCHAR) AS "name"\nFROM (VALUES\n'
    "    ('Acme'),\n    ('Globex')\n) AS pasted(c1)\"\"\").df()\n\n"
    "# customers: no transformations yet. Steps made in the grid appear here."
)
PUSHED = (
    "# clients was made outside this file (in the console, or sent with sab.push).\n"
    "# Put the code that makes it in a cell above this one.\n\n"
    'import duckdb\n\nclients = duckdb.sql("""SELECT * FROM clients LIMIT 5""").df()'
)


def test_a_table_the_app_cannot_read_again_is_a_stub_and_no_rows_are_written(tmp_path: Path) -> None:
    cells = [
        DataCell("code", PASTED, "transformations", "customers", 1),
        DataCell("code", PUSHED, "transformations", "clients", 2),
        DataCell("code", "ready = 1", number=3),
    ]
    made = rules.data_module("sales", cells)
    assert made.fill_in == ("customers", "clients")
    assert "Acme" not in made.text and "Globex" not in made.text and "VALUES" not in made.text
    assert "# ===== FILL IN: customers =====" in made.text and "customers = None" in made.text
    assert "LIMIT 5" not in made.text  # nothing to transform until it is read
    (tmp_path / "data.py").write_text(made.text)
    # It still imports: the other names are there.
    assert _import(tmp_path / "data.py", "[data.ready, data.customers]") == [1, None]
    # With a cell of the user's that makes it, the table's cell is exported as it stands.
    filled = rules.data_module(
        "sales", [DataCell("code", "clients = load_clients()", "maker", "clients", 1), *cells[1:]]
    )
    assert filled.fill_in == () and "LIMIT 5" in filled.text and "clients = load_clients()" in filled.text
    # A pasted table's cell holds its rows: with a cell of the user's that makes it, the user's cell
    # is the table and the pasted rows still stay out.
    own = rules.data_module(
        "sales", [DataCell("code", "customers = load_customers()", number=5), cells[0], cells[2]]
    )
    assert "Acme" not in own.text and "VALUES" not in own.text and "customers = None" not in own.text
    assert "customers = load_customers()" in own.text and own.fill_in == ()
    assert own.skipped == ("cell 1: customers's cell holds the rows pasted into the app.",)
    # A notebook for a zip: the pasted rows are taken out of the cell.
    zipped = rules.without_rows(cells)
    assert "Acme" not in zipped[0].source and "FILL IN: customers" in zipped[0].source
    assert zipped[1:] == cells[1:]


def test_requirements_keep_the_users_lines() -> None:
    needed = rules.data_requirements(
        "orders = sab.sql('W', 'x')\norders = duckdb.sql('y').df()\npd.read_excel('a')"
    )
    assert needed[:3] == ["pandas", "duckdb", "openpyxl"] and needed[3].startswith("# swissarmybench:")
    held = "pandas==2.2.0\nrequests\n"
    merged = rules.merged_requirements(held, ["streamlit>=1.36", "pandas", "duckdb", needed[3]])
    assert merged.split("\n")[:4] == ["pandas==2.2.0", "requests", "streamlit>=1.36", "duckdb"]
    assert rules.merged_requirements(merged, ["streamlit>=1.36", "pandas", "duckdb", needed[3]]) == merged
    assert rules.merged_requirements(None, ["pandas"]) == "pandas\n"


def test_a_projects_files_open_data_first() -> None:
    names = [
        "zeta.py",
        "mockups.ipynb",
        "sales.stapp.json",
        "data.py",
        "data.ipynb",
        "README.txt",
        ".hidden.py",
    ]
    assert rules.project_files(names) == ["data.ipynb", "sales.stapp.json", "mockups.ipynb", "zeta.py"]
    # The project scaffold's made files are not documents either (the sweep, 2026-11-22: opening a
    # project's Scripts page opened adapter.py and the sandbox mirror as tabs, and connections.py counted
    # as a reference to every connection it holds). API.py is the user's own: it opens.
    grown = [*names, "adapter.py", "connections.py", "sandbox_data.py", "sandbox_connections.py", "API.py"]
    assert rules.project_files(grown) == [
        "data.ipynb", "sales.stapp.json", "mockups.ipynb", "API.py", "zeta.py",
    ]  # fmt: skip
    assert rules.check_folder_name(" sales 2026 ") == "sales 2026"
    for bad in ("", "a/b", "..", "x" * 61, "what?"):
        with pytest.raises(rules.ProjectError):
            rules.check_folder_name(bad)


def test_a_sql_cell_that_keeps_its_result_is_in_data_py_as_sab_sql(tmp_path: Path) -> None:
    # Test app one (BI review, 2026-11-22): data.ipynb's `%%sql -> monthly` cell was left out of data.py, and
    # the next cell's `monthly` was a name no line of data.py made (the import failed).
    cells = [
        DataCell(
            "code",
            "import pandas as pd\nsales = pd.DataFrame({'region': ['E', 'W', 'E'], 'amount': [1, 2, 3]})",
            number=1,
        ),
        DataCell(
            "sql",
            "SELECT region, sum(amount) AS total\nFROM sales GROUP BY region ORDER BY region",
            number=2,
            connection="-> totals",
        ),
        DataCell("code", "# uses totals @cell2\nbest = totals.iloc[-1]['region']", number=3),
        DataCell("sql", "SELECT 1", number=4, connection="Warehouse"),  # no result kept: left out
    ]
    made = rules.data_module("sales", cells)
    assert 'totals = sab.sql("""\nSELECT region' in made.text and "SELECT 1" not in made.text
    assert [s.split(":")[0] for s in made.skipped] == ["cell 4"]
    assert made.names == ("sales", "totals", "best")
    named = rules.data_module(
        "x", [DataCell("sql", "SELECT 1", number=1, connection="Larkfield Warehouse -> one")]
    )
    assert 'one = sab.sql("Larkfield Warehouse", """\nSELECT 1\n""")' in named.text
    (tmp_path / "data.py").write_text(made.text)
    assert _import(tmp_path / "data.py", "[data.best, list(data.totals['total'])]") == ["W", [4, 2]]
