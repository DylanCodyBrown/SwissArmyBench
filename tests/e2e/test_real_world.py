# ruff: noqa: S603
"""The owner's real-world use cases, end to end, against the test bed (tools/testbed): real PostgreSQL and
MariaDB, made-up files, and stand-ins for Power BI and Azure Key Vault. Made-up data only
(tools/testbed/company.py).

Each use case as the agent works it, through its MCP commands only (agent parity, the golden rule), and the
results run as they run outside the app: a saved notebook headless on this computer (its password the
keyring's) and as an Azure Function would run it (the connection's exported file, its password from the
environment).
The classic pages' versions of these use cases (their clicks counted under a ceiling) went with those pages
(2026-11-23); the Blazor pages' own browser tests are tests/e2e/blazor/.

They run when the test bed is up (`python tools/testbed/testbed.py up`) and skip, saying why, when it is
not (Windows CI, a machine without PostgreSQL or MariaDB).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tools.testbed import testbed
from tools.testbed.company import Company, make_company

ROOT = Path(__file__).resolve().parents[2]
STATE = testbed.read_state()


def _why_not() -> str | None:
    if STATE is None:
        return (
            "The real-world test bed is not up: python tools/testbed/testbed.py up (tools/testbed/README.md)."
        )
    for database in ("postgres", "mariadb"):
        if "missing" in (STATE.get(database) or {"missing": database}):
            return f"The test bed has no {database}: {STATE[database].get('missing', '')}"
    for module in ("psycopg", "pymysql", "nbclient"):
        if importlib.util.find_spec(module) is None:
            return f"The test bed's drivers are not in this Python ({module}): see tools/testbed/README.md."
    return None


WHY_NOT = _why_not()
pytestmark = pytest.mark.skipif(WHY_NOT is not None, reason=WHY_NOT or "")


def call(info: dict[str, Any], method: str, path: str, body: Any = None) -> Any:
    """A route of the server, with its token."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}",
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=200) as response:  # noqa: S310 (127.0.0.1)
        return json.loads(response.read() or b"null")


def export_blade(info: dict[str, Any], name: str, folder: Path) -> Path:
    """A connection's portable file, as its IDE's Export downloads it (GET /blades/{name}/export)."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}/blades/{urllib.parse.quote(name)}/export",
        headers={"Authorization": f"Bearer {info['token']}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (127.0.0.1)
        said = response.headers.get("content-disposition", "")
        file_name = said.split("filename=", 1)[-1].strip('"') or f"{name}.blade.py"
        target = folder / file_name
        target.write_bytes(response.read())
    return target


# ===== the app, the stand-ins and the company =====


@pytest.fixture(scope="module")
def company() -> Company:
    return make_company()


@pytest.fixture(scope="module")
def standins(company: Company) -> Iterator[dict[str, Any]]:
    """The Power BI and Key Vault stand-ins, started before the app (its child processes read where)."""
    from tools.testbed.standins import KeyVault, power_bi

    powerbi = power_bi(company)
    from tests import powerbi_standin as made_up

    secrets = {"shop-password": STATE["postgres"]["password"] if STATE else ""}
    secrets |= {  # the team's app registration for Power BI (use case 7), made up
        "powerbi-tenant-id": made_up.TENANT,
        "powerbi-client-id": made_up.CLIENT,
        "powerbi-client-secret": made_up.SECRET,
    }
    vault = KeyVault(secrets).start()
    variables = powerbi.environment() | vault.environment()
    before = {name: os.environ.get(name) for name in variables}
    os.environ.update(variables)
    yield {"powerbi": powerbi, "vault": vault}
    powerbi.stop()
    vault.stop()
    for name, value in before.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@pytest.fixture(scope="module")
def bench(tmp_path_factory: pytest.TempPathFactory, standins: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """The app, as a person starts it, with its state in a temporary folder. A keyring that keeps its
    values in that folder stands in for the system's (this container has none)."""
    tmp = tmp_path_factory.mktemp("real-world")
    variables = {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "home" / "SwissArmyBench"),
        "SWISSARMYBENCH_OPEN": "0",
        "XDG_DATA_HOME": str(tmp / "data"),
    }
    if importlib.util.find_spec("keyrings") is not None:
        variables["PYTHON_KEYRING_BACKEND"] = "keyrings.alt.file.PlaintextKeyring"
    before = {name: os.environ.get(name) for name in variables}
    os.environ.update(variables)
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"])
    for _ in range(200):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    else:
        process.kill()
        raise AssertionError("server did not start")
    yield info | {"tmp": tmp, "variables": variables}
    process.terminate()
    process.wait(timeout=20)
    for name, value in before.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@pytest.fixture(scope="module")
def plain_python(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fresh Python with only the client wheel and what the notebooks import (pandas, DuckDB, the
    database driver, Jupyter's runner): no server, no app. As an Azure Function's environment is."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not on PATH: it builds the wheel and the plain Python")
    folder = tmp_path_factory.mktemp("plain")
    subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(folder / "dist")], cwd=ROOT, check=True, capture_output=True
    )
    wheel = next((folder / "dist").glob("swissarmybench-*.whl"))
    venv = folder / "venv"
    subprocess.run([uv, "venv", "--python", sys.executable, str(venv)], check=True, capture_output=True)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    packages = [
        str(wheel),
        "pandas",
        "pyarrow",
        "duckdb",
        "psycopg[binary]",
        "openpyxl",
        "nbclient",
        "nbconvert",
        "ipykernel",
    ]
    packages += ["keyring", "keyrings.alt"]  # this computer's keyring (use case 2); the function has none
    packages += ["streamlit"]  # a saved project's pages, run with Streamlit's AppTest (use case 11)
    subprocess.run(
        [uv, "pip", "install", "--python", str(python), *packages], check=True, capture_output=True
    )
    return python


def plain_environment(home: Path, **extra: str) -> dict[str, str]:
    """A run with nothing of the app's: a home of its own, no connection file that names a server."""
    keep = {
        k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")
    }
    return (
        keep
        | {"HOME": str(home), "USERPROFILE": str(home), "SWISSARMYBENCH_INFO": str(home / "nobody.json")}
        | extra
    )


def wait_until(done: Any, seconds: float = 90) -> None:
    for _ in range(int(seconds * 10)):
        if done():
            return
        time.sleep(0.1)
    raise AssertionError("It did not happen in time.")


def close_tables(bench: dict[str, Any]) -> None:
    """Each use case starts from no open tables (closing earlier ones is not the use case's work)."""
    for dataset in call(bench, "GET", "/datasets")["datasets"]:
        call(bench, "DELETE", f"/datasets/{dataset['name']}")


def ensure_shop(bench: dict[str, Any]) -> None:
    """The Shop connection use case 1 adds, when a use case runs alone (not counted: it is there)."""
    if not any(c["name"] == "Shop" for c in call(bench, "GET", "/connections")["connections"]):
        assert STATE is not None
        where = STATE["postgres"]
        code = (
            "import psycopg\n\nconn = psycopg.connect(\n"
            f'    host="{where["host"]}",\n    port={where["port"]},\n    dbname="{where["database"]}",\n'
            f'    user="{where["user"]}",\n    password=secret("password"),\n)'
        )
        kind = next(t for t in call(bench, "GET", "/blades/templates")["templates"] if t["id"] == "postgres")
        body = {"name": "Shop", "kind": "sql", "template": "postgres", "dialect": "postgres", "code": code}
        call(bench, "POST", "/connections", body | {"variable": "conn", "catalog": kind["catalog"]})
        call(bench, "PUT", "/blades/Shop/secrets", {"password": where["password"]})
    if not any(c["name"] == "Shop" for c in call(bench, "GET", "/catalogs")["catalogs"]):
        call(bench, "POST", "/blades/Shop/refresh", {})
        wait_until(lambda: any(c["name"] == "Shop" for c in call(bench, "GET", "/catalogs")["catalogs"]))


def agent(command: str, **args: Any) -> Any:
    """One of the agent's MCP commands (the registry the MCP server's tools are made from), as the
    agent sends it: its answer as JSON."""
    from swissarmybench.cli.commands import execute_result

    answer = execute_result(command, args)
    assert isinstance(answer, str)
    if "<untrusted-data" in answer:  # an answer with the user's values in it, marked as data
        answer = (
            answer.split("<untrusted-data source=", 1)[1].split(">", 1)[1].rsplit("</untrusted-data>", 1)[0]
        )
    answer = answer.strip()
    return json.loads(answer) if answer[:1] in "[{" else answer


# ===== 1a. orders from a database, cleaned and the notebook saved, by the agent =====

EXPORT_CELL = 'orders.to_parquet("clean_orders.parquet")'


def test_1a_the_agent_cleans_the_orders_and_saves_the_notebook_through_its_commands_only(
    bench: dict[str, Any], company: Company
) -> None:
    assert STATE is not None
    close_tables(bench)
    where = STATE["postgres"]
    kind = next(t for t in agent("connections_types")["types"] if t["id"] == "postgres")
    code = (
        kind["code"]
        .replace("my-server", where["host"])
        .replace("5432", str(where["port"]))
        .replace("my_database", where["database"])
        .replace("my_user", where["user"])
    )
    agent(
        "connections_create",
        name="Shop by the agent",
        kind="sql",
        template="postgres",
        dialect="postgres",
        code=code,
        catalog=kind["catalog"],
        secrets={"password": where["password"]},  # what the user told the agent; never shown back
    )
    assert where["password"] not in json.dumps(agent("connections_get", name="Shop by the agent"))
    agent("connections_open_table", name="Shop by the agent", schema="sales", table="orders", all=True)
    grid = next(g["grid"] for g in agent("tabs_list")["grids"] if g["dataset"] == "orders")
    agent("table_clean_text", grid=grid, fn="trim_both", columns=["status"])
    agent("table_clean_text", grid=grid, fn="lower", columns=["status"])
    agent("table_filter", grid=grid, column="status", op="ne", value="test")
    agent("table_distinct", grid=grid)
    assert agent("row_count", grid=grid)["row_count"] == len(company.clean_orders())
    table = next(t for t in agent("workbench_table_cells")["tables"] if t["name"] == "orders")
    book = Path(bench["variables"]["SWISSARMYBENCH_WORKBENCH_DIR"]) / "clean_orders.ipynb"
    book.parent.mkdir(parents=True, exist_ok=True)
    agent(
        "workbench_save",
        path=str(book),
        cells=[{"kind": "code", "source": table["loaded"]}, {"kind": "code", "source": EXPORT_CELL}],
    )
    ran = agent("workbench_run_notebook", path=str(book))
    assert ran["cells_run"] == 2 and "Error" not in json.dumps(ran["results"]), ran
    import pandas as pd

    assert len(pd.read_parquet(book.parent / "clean_orders.parquet")) == len(company.clean_orders())


# ===== 2. that notebook, run headless (on this computer, the app closed) =====


def test_2_the_saved_notebook_runs_headless_with_the_password_saved_on_this_computer(
    bench: dict[str, Any], plain_python: Path, company: Company, tmp_path: Path
) -> None:
    """As a scheduled task on this computer: `jupyter nbconvert --execute`, the app not running. The
    connection is this computer's saved one; its password the keyring's."""
    folder = Path(bench["variables"]["SWISSARMYBENCH_WORKBENCH_DIR"])
    if not (folder / "clean_orders.ipynb").exists():
        pytest.skip("use case 1a saves the notebook this one runs")
    work = tmp_path / "scheduled"
    work.mkdir()
    shutil.copy(folder / "clean_orders.ipynb", work)
    variables = plain_environment(
        tmp_path / "home",
        SWISSARMYBENCH_STATE=bench["variables"]["SWISSARMYBENCH_STATE"],  # this computer's own app folder
        XDG_DATA_HOME=bench["variables"]["XDG_DATA_HOME"],
        **(
            {"PYTHON_KEYRING_BACKEND": bench["variables"]["PYTHON_KEYRING_BACKEND"]}
            if "PYTHON_KEYRING_BACKEND" in bench["variables"]
            else {}
        ),
    )
    jupyter = plain_python.parent / "jupyter"
    command = [
        str(jupyter),
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        "clean_orders.ipynb",
        "--output",
        "ran.ipynb",
    ]
    ran = subprocess.run(command, cwd=work, env=variables, capture_output=True, text=True, timeout=600)
    assert ran.returncode == 0, ran.stderr[-3000:]
    import pandas as pd

    written = pd.read_parquet(work / "clean_orders.parquet")
    assert len(written) == len(company.clean_orders())


# ===== 3. the same, with its password from an environment variable (an Azure Function) =====


def test_3_the_notebook_runs_as_an_azure_function_would_with_its_password_from_the_environment(
    bench: dict[str, Any], plain_python: Path, company: Company, tmp_path: Path
) -> None:
    """No app, no saved connections, no keyring: the connection's exported file beside the notebook, and
    the password in the function's settings (SHOP_PASSWORD). A plain runner (nbclient), as a function's
    code would call it."""
    folder = Path(bench["variables"]["SWISSARMYBENCH_WORKBENCH_DIR"])
    if not (folder / "clean_orders.ipynb").exists():
        pytest.skip("use case 1a saves the notebook this one runs")
    function = tmp_path / "function"
    function.mkdir()
    exported = export_blade(bench, "Shop by the agent", function).read_text(encoding="utf-8")
    shutil.copy(folder / "clean_orders.ipynb", function)
    assert STATE is not None
    assert STATE["postgres"]["password"] not in exported  # names only, never a value
    runner = function / "function_app.py"
    runner.write_text(
        "import nbformat\nfrom nbclient import NotebookClient\n\n"
        'book = nbformat.read("clean_orders.ipynb", as_version=4)\n'
        'resources = {"metadata": {"path": "."}}\n'
        'NotebookClient(book, timeout=600, kernel_name="python3", resources=resources).execute()\n',
        encoding="utf-8",
    )
    variables = plain_environment(tmp_path / "home", SHOP_PASSWORD=STATE["postgres"]["password"])
    ran = subprocess.run(
        [str(plain_python), "function_app.py"],
        cwd=function,
        env=variables,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert ran.returncode == 0, ran.stderr[-3000:]
    import pandas as pd

    assert len(pd.read_parquet(function / "clean_orders.parquet")) == len(company.clean_orders())


# ===== 4a. Excel statements: one workbook per customer, from a template, by the agent =====

# The one Excel module (Plans/excel.plan.md): the three Excel starters, each a line of its own; the
# statements need only Fill a template.
STARTERS = ("Excel read a workbook", "Excel make a workbook", "Excel fill a template")
VARIABLES = ("read_workbook", "make_workbook", "fill_template")


def statements_code(template: str) -> str:
    """What the user writes under the three starters' lines: a statement of open invoices for each
    customer that has one, the template filled (labels in A4:A7, the invoices' headings on row 9 and the
    invoices from A10 down: a table that grows)."""
    return (
        "\n\nfrom pathlib import Path\n\n"
        f'template = r"{template}"\n'
        'columns = ["invoice_id", "order_id", "invoice_date", "due_date", "amount"]\n'
        'places = [{"kind": "value", "place": f"B{4 + i}", "value": {"column": name}}\n'
        '          for i, name in enumerate(["customer_name", "customer_id", "statement_date", "open"])]\n'
        'places += [{"kind": "value", "place": f"{letter}9", "value": {"text": name}}\n'
        '           for letter, name in zip("ABCDE", columns)]\n'
        'places += [{"kind": "table", "place": "A10", "columns": columns, "rows": 1}]\n'
        'for customer_id, rows in invoices.groupby("customer_id"):\n'
        '    who = customers[customers["customer_id"] == customer_id].iloc[0]\n'
        '    values = {"customer_name": who["customer_name"], "customer_id": int(customer_id),\n'
        '              "statement_date": "2026-11-01", "open": len(rows)}\n'
        '    to = Path("statements") / f"statement-{customer_id}.xlsx"\n'
        "    fill_template(template, to, places, values, rows[columns])\n"
    )


def check_statements(folder: Path, company: Company) -> None:
    import openpyxl

    unpaid = [i for i in company.invoices if i["paid_date"] is None]
    customers = {i["customer_id"] for i in unpaid}
    assert {p.name for p in folder.glob("*.xlsx")} == {f"statement-{c}.xlsx" for c in customers}
    first = min(customers)
    sheet = openpyxl.load_workbook(folder / f"statement-{first}.xlsx")["Invoice"]
    who = next(c for c in company.customers if c["customer_id"] == first)
    mine = [i for i in unpaid if i["customer_id"] == first]
    assert sheet["A1"].value == "Quillmere Supply"  # the template's own heading
    assert (sheet["B4"].value, sheet["B5"].value, sheet["B7"].value) == (
        who["customer_name"],
        first,
        len(mine),
    )
    assert [c.value for c in sheet[9]][:5] == ["invoice_id", "order_id", "invoice_date", "due_date", "amount"]
    assert {sheet.cell(10 + k, 1).value for k in range(len(mine))} == {i["invoice_id"] for i in mine}


def test_4a_the_agent_makes_the_same_statements_through_its_commands_only(
    bench: dict[str, Any], company: Company, tmp_path: Path
) -> None:
    """Agent parity: the same statements, by the agent's MCP commands alone (no browser)."""
    ensure_shop(bench)
    close_tables(bench)
    assert STATE is not None
    for table in ("invoices", "customers"):
        agent("connections_open_table", name="Shop", schema="sales", table=table, all=True)
    grid = next(g["grid"] for g in agent("tabs_list")["grids"] if g["dataset"] == "invoices")
    agent("table_filter", grid=grid, column="paid_date", op="blank")
    tables = agent("workbench_table_cells")["tables"]
    lines = "\n".join(f'{v} = sab.blade("{n}")' for n, v in zip(STARTERS, VARIABLES, strict=True))
    starters = {b["name"] for family in agent("blades_starters")["families"] for b in family["blades"]}
    assert set(STARTERS) <= starters
    cells = [{"kind": "code", "source": t["loaded"]} for t in tables]
    cells.append({"kind": "code", "source": lines + statements_code(STATE["files"]["invoice_template"])})
    book = tmp_path / "statements.ipynb"
    agent("workbench_save", path=str(book), cells=cells)
    ran = agent("workbench_run_notebook", path=str(book))
    assert ran["cells_run"] == 3 and "Error" not in json.dumps(ran["results"]), ran
    check_statements(tmp_path / "statements", company)


# ===== 11a. a widget on a canvas, by the agent =====

WIDGET = """import streamlit as st
from sab_canvas import table

# table: the invoices to count
table_name = "invoices"
# The words above the number
label = "Invoices"
# The accent colour
colour = "#1f77b4"

rows = table(table_name)
st.markdown(f"<div style='color:{colour};font-weight:600'>{label}</div>", unsafe_allow_html=True)
st.metric(label, f"{len(rows):,}")
"""


def streamlit_python() -> str:
    from tests.streamlit_helpers import STREAMLIT_PYTHON

    if STREAMLIT_PYTHON is None:
        pytest.skip("no Python with Streamlit here (set SWISSARMYBENCH_STREAMLIT_PYTHON to one)")
    return STREAMLIT_PYTHON


def test_11a_the_agent_makes_the_same_canvas_through_its_commands_only(
    bench: dict[str, Any], company: Company, tmp_path: Path
) -> None:
    """The same, by the agent's commands only: a widget, a canvas of the project, a container, the widget
    in it, the page checked headless (each widget's own errors), and its builds' history after a launch."""
    streamlit_python()
    ensure_shop(bench)
    close_tables(bench)
    agent("connections_open_table", name="Shop", schema="sales", table="invoices", all=True)
    try:
        agent("widgets_new", name="invoice_total_agent", description="Invoices counted", code=WIDGET)
    except Exception:  # noqa: S110 (made by an earlier run)
        pass
    project = tmp_path / "agent-project"
    project.mkdir()
    canvas = agent("canvas_open", path=str(project / "invoices.canvas.json"))["canvas"]
    made = agent("canvas_add_container", canvas=canvas, x=0, y=0, w=600, h=240)["made"]
    agent("canvas_insert_widget", canvas=canvas, widget="invoice_total_agent", parent=made)
    checked = agent("canvas_play", canvas=canvas, check=True)
    assert checked["ok"], checked
    launched = agent("app_launch", canvas=canvas)
    assert launched["build"] == 1
    assert agent("canvas_builds", canvas=canvas)["builds"][0]["changed"] == ["The first build."]
    agent("app_launch", canvas=canvas, stop=True)
    del company
