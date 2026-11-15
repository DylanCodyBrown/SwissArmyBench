# ruff: noqa: F811
"""Export as one Python script (domain/script_export.py, services/script_export.py): a notebook or
script as ONE .py that runs with plain `python <file>` in a fresh Python, with no Swiss Army Bench, no
password and no row in it. Made-up data only."""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook

from swissarmybench.adapters import script_check
from swissarmybench.domain import script_export as se
from swissarmybench.domain.packages import provided
from swissarmybench.domain.script_export import ExportCell, Piece, Secret
from tests import powerbi_standin as made_up
from tests.fake_keyring import memory_keyring
from tests.test_cli import Live, live, run  # noqa: F401 (the running server, and the agent's commands)

PASSWORD = "made-up-password-0001"  # the keyring's, in the app: never in a script
VAULT_VALUE = "made-up-vault-entry-0002"  # a key vault's entry: never in a script
SHOP = (
    "import sqlite3\nfrom pathlib import Path\n\n"
    'path = Path(r"{path}")\n'
    'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    # SQLite needs no password: the code checks one as a server would (by its hash: no value in the code).
    "import hashlib\n"
    'if hashlib.sha256(secret("password").encode()).hexdigest() != "{digest}":\n'
    '    raise ValueError("wrong password")\n'
)


def shop_code(path: object) -> str:
    return SHOP.format(path=path, digest=hashlib.sha256(PASSWORD.encode()).hexdigest())


VAULT = """import json

values = json.loads(open(r"{path}", encoding="utf-8").read())


def names():
    return list(values)


def get(name):
    return values.get(name)
"""


def shop_piece(path: str = "/data/shop.sqlite", where: str = "keyring") -> Piece:
    secret = (
        Secret("password", "SHOP_PASSWORD", "keyring", blade="Shop")
        if where == "keyring"
        else Secret(
            "WAREHOUSE_PASSWORD",
            "WAREHOUSE_PASSWORD",
            "vault",
            vault="Team vault",
            entry="warehouse-password",
        )
    )
    code = shop_code(path)
    if where != "keyring":
        code = code.replace('secret("password")', 'secret("WAREHOUSE_PASSWORD")')
    return Piece("Shop", "sql", "database", code, "conn", "sqlite", secrets=(secret,))


def vault_piece(path: str = "/data/vault.json") -> Piece:
    return Piece(
        "Team vault",
        "vault",
        "vault",
        VAULT.format(path=path),
        "get",
        vault_mapping={"WAREHOUSE_PASSWORD": "warehouse-password"},
    )


def exported(cells: list[ExportCell], pieces: dict[str, Piece] | None = None, **more: Any) -> se.Exported:
    return se.export(
        "Orders report", "/work/orders_report.ipynb", cells, pieces or {}, {"shop": "Shop"}, **more
    )


def run_body(text: str) -> str:
    """The script's run() as text (its comments too: up to main())."""
    return text[text.index("\ndef run() -> None:") : text.index("\ndef main(")]


# ===== the pieces, one by one =====


def test_the_name_and_the_header_say_how_to_run_it_with_plain_python() -> None:
    assert se.file_name("C:/work/Orders report.ipynb") == "orders_report_automation.py"
    assert se.file_name("/work/2026 sales.py") == "job_2026_sales_automation.py"
    made = exported([ExportCell("code", "import pandas as pd\nimport openpyxl\nframe = pd.DataFrame()")])
    text = made.text
    compile(text, "script", "exec")
    assert made.requirements == ("pandas>=2.0", "openpyxl>=3.1")
    # The requirements as a plain constant, checked before anything of them is imported.
    assert (
        "REQUIREMENTS: dict[str, str] = {\n    'pandas': 'pandas>=2.0',\n    'openpyxl': 'openpyxl>=3.1',\n}"
        in text
    )
    assert "python orders_report_automation.py --install" in text and "-m pip install" in text
    # PEP 723 for uv users (harmless: comments), and the Azure Function's requirements.txt and trigger.
    assert '# /// script\n# requires-python = ">=3.10"\n# dependencies = [\n#     "pandas>=2.0",' in text
    assert "    pandas>=2.0\n    openpyxl>=3.1\n" in text and "@app.timer_trigger(" in text
    assert "import orders_report_automation as job" in text and "job.main()" in text
    assert 'if __name__ == "__main__":\n    sys.exit(cli(sys.argv[1:]))' in text
    # Nothing third-party at the top level: the package check runs first.
    top = [n for n in ast.parse(text).body if isinstance(n, ast.Import | ast.ImportFrom)]
    assert all(
        provided(a.name if isinstance(n, ast.Import) else n.module or "") for n in top for a in n.names
    )
    assert "swissarmybench" not in made.requirements and "import swissarmybench" not in text


def test_the_settings_name_every_variable_and_never_a_secrets_value() -> None:
    orders_api = Piece(
        "Orders API",
        "other",
        "python",
        'import os\nconn = {"url": os.environ["ORDERS_URL"], "key": os.environ["ORDERS_KEY"]}',
        "conn",
        read="conn['url']",
        secrets=tuple(
            se.python_sources(
                "Orders API",
                {
                    "ORDERS_URL": {"from": "value", "value": "http://127.0.0.1:1/api"},
                    "ORDERS_KEY": {"from": "keyring"},
                },
                [],
            )
        ),
    )
    cells = [
        ExportCell("sql", "SELECT * FROM customers", "Shop -> customers", number=1),
        ExportCell("code", "import swissarmybench as sab\nrows = sab.read('Orders API', 'orders')", number=2),
    ]
    made = exported(cells, {"Shop": shop_piece(), "Orders API": orders_api})
    text = made.text
    settings = text[text.index("SETTINGS: dict") : text.index("FROM_VAULTS")]
    assert "'SHOP_PASSWORD': None,  # Shop's secret('password'): saved in the keyring" in settings
    assert "'ORDERS_KEY': None,  # Orders API's ORDERS_KEY: saved in the keyring" in settings
    assert (
        "'ORDERS_URL': 'http://127.0.0.1:1/api',  # Orders API's ORDERS_URL: a plain value in the app (no secret)"
        in settings
    )
    assert "REQUIRED: tuple[str, ...] = ('SHOP_PASSWORD', 'ORDERS_KEY',)" in text
    assert {s["variable"]: s["secret"] for s in made.settings} == {
        "SHOP_PASSWORD": True,
        "ORDERS_URL": False,
        "ORDERS_KEY": True,
    }
    assert se.check(text, [PASSWORD]) == []
    assert se.check(text + f"\n# {PASSWORD}\n", [PASSWORD])[0].startswith("it would hold a saved password")


def test_a_vault_is_written_out_with_its_own_code_and_read_only_when_the_variable_is_not_set() -> None:
    cells = [ExportCell("sql", "SELECT 1", "Shop -> one", number=1)]
    made = exported(cells, {"Shop": shop_piece(where="vault"), "Team vault": vault_piece()})
    text = made.text
    assert "def vault_team_vault():" in text and "    return get, names" in text
    assert "    'WAREHOUSE_PASSWORD': ('Team vault', 'warehouse-password')," in text
    assert "'Team vault': vault_team_vault," in text
    # The environment's own value first (an Azure Function's Key Vault reference), then the vault.
    helper = text[text.index("def from_vault(") :]
    assert helper.index("os.environ.get(variable)") < helper.index("VAULTS[vault]()")
    assert (
        "REQUIRED: tuple[str, ...] = ('WAREHOUSE_PASSWORD',)" in text
    )  # checked only when no vault gives it
    assert "name not in FROM_VAULTS" in text
    assert VAULT_VALUE not in text


def test_each_connection_kind_is_a_small_function_of_its_own_code() -> None:
    folder = Piece("Sales files", "other", "file", 'path = r"/data/sales"', "path")
    workspace = Piece("Finance", "sql", "database", "conn = make_workspace()", "conn", "dax", secrets=())
    reader = Piece(
        "Orders API",
        "other",
        "python",
        'conn = {"base": "http://127.0.0.1:1"}\n\ndef fetch(t):\n    return [{"t": t}]',
        "conn",
        read="fetch(table)",
    )
    writer = Piece(
        "Excel write table",
        "other",
        None,
        "def write_table(path, sheet, frame):\n    return path",
        "write_table",
    )
    cells = [
        ExportCell("sql", 'SELECT * FROM "orders"', "Sales files -> sales", number=1),
        ExportCell("dax", "EVALUATE 'Sales'", "Finance/Sales model -> model_sales", number=2),
        ExportCell(
            "code",
            "import swissarmybench as sab\nrows = sab.read('Orders API', 'orders')\n"
            "write_table = sab.blade('Excel write table')\napi = sab.connection('Orders API')",
            number=3,
        ),
    ]
    pieces = {p.name: p for p in (folder, workspace, reader, writer)}
    text = exported(cells, pieces).text
    compile(text, "script", "exec")
    assert '@functools.cache\ndef connect_sales_files():\n    """Sales files: a file connection' in text
    assert 'def connect_finance():\n    """Finance: a Power BI workspace: its sign-in, then DAX' in text
    assert "        return (fetch(table))\n" in text and "    return conn, read" in text  # Read a table
    assert "def blade_excel_write_table():" in text and "    return write_table\n" in text
    body = run_body(text)
    assert (
        "sales = run_sql('Sales files', " in body and "model_sales = run_dax('Finance/Sales model', " in body
    )
    assert "rows = read_table('Orders API', 'orders')" in body
    assert "write_table = blade('Excel write table')" in body and "api = connection('Orders API')" in body
    assert "def run_dax(" in text and "def read_table(" in text and "def open_files(" in text


def test_a_tables_cell_keeps_its_load_and_steps_and_a_pasted_table_is_a_stub() -> None:
    orders = ExportCell(
        "code",
        "import duckdb\n\norders = duckdb.read_csv('/data/orders.csv').df()\n\n"
        'orders = duckdb.sql("""\nSELECT * FROM orders WHERE amount > 5\n""").df()',
        role="transformations",
        table="orders",
        number=4,
    )
    pasted = ExportCell(
        "code",
        'import duckdb\n\nfruit = duckdb.sql("""\nSELECT\n    CAST(c1 AS VARCHAR) AS "item"\nFROM (VALUES\n'
        '    (\'apple\')\n) AS pasted(c1)\n""").df()\n\nfruit = duckdb.sql("""\nSELECT * FROM fruit LIMIT 1\n""").df()',
        role="transformations",
        table="fruit",
        number=5,
    )
    pushed = ExportCell(
        "code",
        "# made was made outside this file (in the console, or sent with sab.push).\n"
        "# Put the code that makes it in a cell above this one.",
        role="transformations",
        table="made",
        number=6,
    )
    made = exported([orders, pasted, pushed])
    body = run_body(made.text)
    assert "orders = duckdb.read_csv('/data/orders.csv').df()" in body and "WHERE amount > 5" in body
    assert "# ===== FILL IN: fruit =====" in body and 'raise FillIn("FILL IN: fruit has no load.' in body
    assert "apple" not in made.text and "AS pasted(" not in made.text  # no rows, ever
    assert "SELECT * FROM fruit LIMIT 1" in body  # its steps stay, for once the load is filled in
    assert "FILL IN: made" in body and made.stubs == ("fruit", "made")
    assert se.check(made.text, []) == []


def test_sql_dax_and_blade_calls_are_written_out_and_the_package_import_goes() -> None:
    cell = ExportCell(
        "code",
        "import swissarmybench as sab\nfrom swissarmybench import dax\n"
        "late = sab.sql('Shop', 'SELECT * FROM orders')\nmodel = dax('Finance/Sales model', \"EVALUATE 'Sales'\")",
        number=1,
    )
    assert se.references([cell], {}) == ["Shop", "Finance"]
    body = run_body(
        exported(
            [cell],
            {"Shop": shop_piece(), "Finance": Piece("Finance", "sql", "database", "conn = 1", "conn", "dax")},
        ).text
    )
    assert "late = run_sql('Shop', 'SELECT * FROM orders')" in body
    assert "model = run_dax('Finance/Sales model', " in body and "swissarmybench" not in body.replace(
        "Swiss Army Bench", ""
    )
    # A connection named by its Workbench variable is opened as the Workbench opens it.
    by_name = ExportCell("code", "rows = shop.cursor().execute('SELECT 1').fetchall()", number=2)
    assert se.references([by_name], {"shop": "Shop"}) == ["Shop"]
    assert "shop = connection('Shop')  # the Workbench's shop" in run_body(
        exported([by_name], {"Shop": shop_piece()}).text
    )
    # A connection's name that is not written in the code cannot be exported.
    named = ExportCell(
        "code", "import swissarmybench as sab\nname = 'Shop'\nrows = sab.sql(name, 'SELECT 1')", number=3
    )
    assert "must name its connection as a text" in str(exported([named]).problems[0])


def test_what_only_shows_something_is_left_out_with_a_line_that_says_so() -> None:
    cells = [
        ExportCell("html", "<b>{{ total }}</b>", number=1),
        ExportCell("code", "import streamlit as st\nst.metric('Total', 3)", number=2),
        ExportCell(
            "code",
            "import swissarmybench as sab\ntotal = 3\ndisplay(total)\nsab.push(total)\nif total:\n    display(total)\ntotal",
            number=3,
        ),
        ExportCell("code", "frame.head()", number=4),
        ExportCell("markdown", "## Notes\nMade-up.", number=5),
    ]
    made = exported(cells)
    body = run_body(made.text)
    assert "# cell 1: an HTML cell, a design shown in the notebook: left out" in body
    assert "# cell 2: it calls Streamlit (a page shown in the app): left out" in body
    assert "    # display(...): shown in the notebook only" in body
    assert "        pass  # display(...): shown in the notebook only" in body  # inside a block: pass
    assert (
        "# sab.push(...): it shows in the app, left out" in body
        and "# total: shown in the notebook only" in body
    )
    assert "# frame.head(): shown in the notebook only" in body and "    # ## Notes" in body
    assert "st.metric" not in body and not made.problems
    compile(made.text, "script", "exec")


def test_magics_are_translated_where_python_has_the_same_and_refused_by_their_cell() -> None:
    good = ExportCell(
        "code",
        "%pip install requests\n%matplotlib inline\n%env REGION=North\n%env API_TOKEN=made-up-typed-0009\n"
        "%time x = 1 + 1\n%cd /tmp",
        number=1,
    )
    made = exported([good])
    body = run_body(made.text)
    assert (
        "os.environ.setdefault('REGION', 'North')" in body
        and "x = 1 + 1" in body
        and "os.chdir('/tmp')" in body
    )
    assert (
        "made-up-typed-0009" not in made.text
        and "'API_TOKEN': None,  # API_TOKEN: set with %env" in made.text
    )
    assert "requests" in made.requirements and not made.problems
    bad = ExportCell("code", "x = 1\n!ls -la\n%run other.ipynb", number=7)
    refused = exported([good, bad])
    assert [str(p) for p in refused.problems] == [
        "cell 7: line 2: !ls -la is a shell command: plain Python has no same",
        "cell 7: line 3: %run other.ipynb is IPython's own: plain Python has no same",
    ]
    stubbed = exported([good, bad], stub=True)
    assert "# ===== FILL IN: cell 7 =====" in stubbed.text and stubbed.stubs == ("cell 7",)
    assert 'raise FillIn("FILL IN: cell 7 could not be exported' in stubbed.text
    compile(stubbed.text, "script", "exec")
    star = exported([ExportCell("code", "from os.path import *", number=8)])
    assert "import *" in str(star.problems[0])


def test_a_script_document_reads_by_its_cells() -> None:
    text = "import pandas as pd\n\n# %% [2] Load\nframe = pd.DataFrame({'a': [1]})\n# %% [3]\nframe\n"
    cells = se.script_cells(text)
    made = se.export("job", "/work/job.py", cells, {}, {})
    body = run_body(made.text)
    assert "# ----- the main code -----" in body and "# ----- cell 2 (Load) -----" in body
    assert "# frame: shown in the notebook only" in body


def test_ruff_finds_a_name_nothing_makes(tmp_path: Path) -> None:
    findings = script_check.lint("def run():\n    print(missing_name)\n")
    if findings is None:
        pytest.skip("no ruff in this Python")
    assert [f["code"] for f in findings] == ["F821"] and findings[0]["line"] == 2


# ===== end to end: exported through the app, run in a fresh Python =====


def _distributions(names: list[str]) -> set[str]:
    """The installed distributions these requirements need, with theirs (this machine's installs)."""
    seen: set[str] = set()
    stack = list(names)
    while stack:
        name = re.split(r"[<>=!~\[; ]", stack.pop(), maxsplit=1)[0]
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue  # a marker's package this platform does not install
        key = dist.metadata["Name"].lower()
        if key in seen:
            continue
        seen.add(key)
        stack += [r for r in dist.requires or [] if "extra ==" not in r]
    return seen


def fresh_python(where: Path, with_pip: bool = False) -> Path:
    """A new venv from the base interpreter: no Swiss Army Bench, nothing installed."""
    base = getattr(sys, "_base_executable", sys.executable)
    flags = [] if with_pip else ["--without-pip"]
    subprocess.run([base, "-m", "venv", *flags, str(where)], check=True, capture_output=True)  # noqa: S603
    return where / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def install_from_this_machine(python: Path, requirements: list[str]) -> None:
    """The requirements (and only theirs) linked in from this machine's installed packages."""
    site = Path(
        subprocess.run(  # noqa: S603
            [str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    for name in _distributions(requirements):
        dist = importlib.metadata.distribution(name)
        tops = {Path(str(f)).parts[0] for f in dist.files or [] if not str(f).startswith("..")}
        for top in tops:
            source = Path(str(dist.locate_file(top)))
            if source.exists() and not (site / top).exists() and not top.endswith(".pth"):
                (site / top).symlink_to(source)


def run_script(
    python: Path, script: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("SWISSARMY", "PYTHON", "VIRTUAL_ENV"))}
    return subprocess.run(  # noqa: S603 (the exported, made-up script)
        [str(python), str(script), *args],
        capture_output=True,
        text=True,
        env=clean | (env or {}),
        cwd=script.parent,
        timeout=600,
        check=False,
    )


@pytest.fixture
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture
def made_up_shop(tmp_path: Path) -> Path:
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE customers (id INTEGER, name TEXT, region TEXT)")
        db.executemany(
            "INSERT INTO customers VALUES (?, ?, ?)",
            [(1, "Made-up Ann", "North"), (2, "Made-up Bob", "South"), (3, "Made-up Cy", "North")],
        )
    return database


def notebook_cells(live: Live, table: str) -> list[dict[str, Any]]:
    """A notebook as the Workbench makes it: the table's Tables group, then the user's cells."""
    group = live.user(
        "POST", "/workbench/tables/arrange", {"kind": "notebook", "cells": [], "tables": [table]}
    )
    return [
        *group["cells"],
        {"kind": "markdown", "source": "# Orders by region\nMade-up data.", "number": 10},
        {
            "kind": "sql",
            "connection": "Shop -> customers",
            "source": "SELECT id, name, region FROM customers",
            "number": 11,
        },
        {
            "kind": "code",
            "source": "import pandas as pd\n\nreport = orders.merge(customers, left_on='customer_id', right_on='id')\n"
            "by_region = report.groupby('region', as_index=False)['amount'].sum()\nby_region",
            "number": 12,
        },
        {
            "kind": "code",
            "source": "import os\n\nimport swissarmybench as sab\n\nfolder = os.environ['REPORT_FOLDER']\n"
            "write_table = sab.blade('Excel write table')\n"
            "write_table(folder + '/report.xlsx', 'By region', by_region)\n"
            "by_region.to_csv(folder + '/by_region.csv', index=False)\nsab.push(by_region, name='by_region')",
            "number": 13,
        },
    ]


def test_a_notebook_exports_and_runs_in_a_fresh_python_with_only_its_requirements(
    live: Live, keyring: None, made_up_shop: Path, tmp_path: Path
) -> None:
    connection = {
        "name": "Shop",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "variable": "conn",
    }
    live.user("POST", "/connections", connection | {"code": shop_code(made_up_shop)})
    live.user("PUT", "/blades/Shop/secrets", {"password": PASSWORD})
    csv = tmp_path / "orders.csv"
    csv.write_text(
        "order_id,customer_id,amount\n1,1,10.5\n2,2,7.0\n3,1,2.5\n4,3,40.0\n5,2,31.0\n", encoding="utf-8"
    )
    grid = run("datasets_load", path=str(csv), name="orders")["grid"]
    live.user(
        "POST",
        f"/grids/{grid}/steps",
        {"steps": [{"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 5}}]},
    )
    notebook = tmp_path / "work" / "Orders report.ipynb"
    notebook.parent.mkdir()
    live.user("POST", "/workbench/save", {"path": str(notebook), "cells": notebook_cells(live, "orders")})
    # The agent's command (the golden rule): beside the notebook, named after it.
    done = run("workbench_export_script", path=str(notebook))
    print("DONE", json.dumps({k: done[k] for k in ("problems", "lint", "stubs", "skipped")}))
    script = notebook.parent / "orders_report_automation.py"
    assert done["path"] == str(script) and done["run"] == "python orders_report_automation.py", done
    assert not done["problems"] and not done["stubs"] and done["linted"] in (True, False) and not done["lint"]
    assert done["requirements"] == ["duckdb>=1.1", "pandas>=2.0", "openpyxl>=3.1"]
    text = script.read_text(encoding="utf-8")
    assert PASSWORD not in text and "Made-up Ann" not in text and "10.5" not in text  # no secret, no row
    assert 'WHERE "amount" > 5' in text  # the grid's step, as DuckDB SQL
    assert "'SHOP_PASSWORD': None,  # Shop's secret('password'): saved in the keyring" in text
    assert "'REPORT_FOLDER': None,  # cell 13's REPORT_FOLDER: the notebook's own code reads it" in text
    out = tmp_path / "out"
    out.mkdir()
    python = fresh_python(tmp_path / "venv", with_pip=os.environ.get("SWISSARMYBENCH_TEST_PIP") == "1")
    # 1. No packages yet: one clear message, the command for this Python, and exit 3.
    bare = run_script(python, script, env={"SHOP_PASSWORD": PASSWORD, "REPORT_FOLDER": str(out)})
    assert bare.returncode == 3, bare.stderr
    assert "This script needs duckdb>=1.1, pandas>=2.0, openpyxl>=3.1" in bare.stderr
    assert f"{python} -m pip install" in bare.stderr and "--install" in bare.stderr
    # 2. Installed: with --install from the package index when asked for, else this machine's own.
    env = {"SHOP_PASSWORD": PASSWORD, "REPORT_FOLDER": str(out)}
    if os.environ.get("SWISSARMYBENCH_TEST_PIP") == "1":
        first = run_script(python, script, "--install", env=env)
    else:
        install_from_this_machine(python, done["requirements"])
        first = run_script(python, script, env=env)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "Started" in first.stdout and "cell 13" in first.stdout and "Done" in first.stdout
    assert subprocess.run(  # noqa: S603 (the fresh Python: it has no Swiss Army Bench)
        [str(python), "-c", "import swissarmybench"], capture_output=True, check=False
    ).returncode
    sheet = load_workbook(out / "report.xlsx")["By region"]
    assert [list(r) for r in sheet.iter_rows(values_only=True)] == [
        ["region", "amount"],
        ["North", 50.5],
        ["South", 38.0],
    ]
    assert (out / "by_region.csv").read_text(encoding="utf-8").splitlines() == [
        "region,amount",
        "North,50.5",
        "South,38.0",
    ]
    # 3. A setting missing: named, with where it came from, and exit 2 (nothing ran).
    (out / "report.xlsx").unlink()
    missing = run_script(python, script, env={"REPORT_FOLDER": str(out)})
    assert missing.returncode == 2 and "SHOP_PASSWORD  (Shop's secret('password')" in missing.stdout
    assert not (out / "report.xlsx").exists()
    # A wrong password is the connection's own failure: exit 1, and the value is never logged.
    wrong = run_script(python, script, env={"SHOP_PASSWORD": "made-up-wrong-9", "REPORT_FOLDER": str(out)})
    assert (
        wrong.returncode == 1 and "wrong password" in wrong.stdout and "made-up-wrong-9" not in wrong.stdout
    )


def test_the_page_sends_the_open_document_and_what_cannot_be_exported_is_asked_first(
    live: Live, keyring: None, tmp_path: Path
) -> None:
    cells = [
        {"kind": "code", "source": "x = 1\n!ls", "number": 1},
        {"kind": "code", "source": "y = x + 1", "number": 2},
    ]
    target = tmp_path / "job_automation.py"
    body = {"kind": "notebook", "cells": cells, "name": "job.ipynb", "to": str(target)}
    asked = live.user("POST", "/workbench/export-script", body)
    assert asked["path"] is None and asked["problems"] == [
        "cell 1: line 2: !ls is a shell command: plain Python has no same"
    ]
    assert "stub: true" in asked["ask"] and not target.exists()
    written = live.user("POST", "/workbench/export-script", body | {"stub": True})
    assert written["path"] == str(target) and written["stubs"] == ["cell 1"]
    assert "raise FillIn(" in target.read_text(encoding="utf-8")
    # A cell that holds a saved password's value: refused, nothing written.
    live.user(
        "POST",
        "/connections",
        {
            "name": "Shop",
            "kind": "sql",
            "template": "sqlite",
            "dialect": "sqlite",
            "variable": "conn",
            "code": shop_code(tmp_path / "x.sqlite"),
        },
    )
    live.user("PUT", "/blades/Shop/secrets", {"password": PASSWORD})
    leaked = [
        {
            "kind": "code",
            "source": f"import swissarmybench as sab\npassword = '{PASSWORD}'\nconn = sab.connection('Shop')",
            "number": 1,
        }
    ]
    with pytest.raises(Exception, match="403"):
        live.user(
            "POST",
            "/workbench/export-script",
            {"kind": "notebook", "cells": leaked, "to": str(tmp_path / "leak.py")},
        )
    assert not (tmp_path / "leak.py").exists()


def test_the_power_bi_workspace_signs_in_from_a_vault_and_runs_dax_with_no_app(
    live: Live, keyring: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from swissarmybench.server.blade_templates import BY_ID, POWERBI_VAULT

    standin = made_up.StandIn().start()
    try:
        vault_file = tmp_path / "vault.json"
        values = {
            "powerbi-tenant-id": made_up.TENANT,
            "powerbi-client-id": made_up.CLIENT,
            "powerbi-client-secret": made_up.SECRET,
        }
        vault_file.write_text(json.dumps(values), encoding="utf-8")
        vault = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault", "variable": "get"}
        live.user(
            "POST",
            "/connections",
            vault | {"code": VAULT.format(path=vault_file), "vault_all": True, "vault_mapping": []},
        )
        code = POWERBI_VAULT.replace("my-workspace-id", made_up.WORKSPACE)
        for secret, entry in (
            ("tenant id", "powerbi-tenant-id"),
            ("client id", "powerbi-client-id"),
            ("client secret", "powerbi-client-secret"),
        ):
            source = {
                "code": code,
                "secret": secret,
                "from": "vault",
                "vault": "Team vault",
                "vault_secret": entry,
            }
            code = live.user("POST", "/connections/source", source)["code"]
        template = BY_ID["powerbi"].to_json()
        workspace = {"name": "Finance", "kind": "sql", "template": "powerbi", "dialect": "dax", "code": code}
        live.user("POST", "/connections", workspace | {"variable": "conn", "catalog": template["catalog"]})
        cells = [
            {
                "kind": "dax",
                "connection": "Finance/Sales model -> sales",
                "source": "EVALUATE TOPN(5, 'Sales')",
                "number": 1,
            },
            {
                "kind": "code",
                "source": "import os\nsales.to_csv(os.environ['REPORT_FOLDER'] + '/sales.csv', index=False)",
                "number": 2,
            },
        ]
        script = tmp_path / "finance_automation.py"
        done = live.user(
            "POST", "/workbench/export-script", {"kind": "notebook", "cells": cells, "to": str(script)}
        )
        assert done["path"] == str(script) and not done["problems"], done
        text = script.read_text(encoding="utf-8")
        assert (
            made_up.SECRET not in text and made_up.TENANT not in text
        )  # the vault's values stay in the vault
        assert "def vault_team_vault():" in text and "def connect_finance():" in text
        assert "sales = run_dax('Finance/Sales model', " in text
        env = standin.environment() | {"REPORT_FOLDER": str(tmp_path)}
        clean = {k: v for k, v in os.environ.items() if not k.startswith("SWISSARMY")}
        ran = subprocess.run(  # noqa: S603 (the exported, made-up script, in a Python of its own)
            [sys.executable, "-I", str(script)],
            capture_output=True,
            text=True,
            env=clean | env,
            timeout=300,
            check=False,
        )
        assert ran.returncode == 0, ran.stdout + ran.stderr
        assert "Reading" in ran.stdout and "from the key vault Team vault" in ran.stdout
        assert (
            len((tmp_path / "sales.csv").read_text(encoding="utf-8").splitlines()) == 6
        )  # its header and 5 rows
    finally:
        standin.stop()
