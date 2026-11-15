# ruff: noqa: F811, S603
"""The owner's real-world use cases, end to end in a real browser, against the test bed (tools/testbed):
real PostgreSQL and MariaDB, made-up files, and stand-ins for Power BI and Azure Key Vault. Each use case
counts the user's actions (clicks, keys, typed values, drags) and holds them under a ceiling, so a change
that makes the work longer shows here. Made-up data only (tools/testbed/company.py).

They run when the test bed is up (`python tools/testbed/testbed.py up`) and skip, saying why, when it is
not (Windows CI, a machine without PostgreSQL or MariaDB). SWISSARMYBENCH_SHOTS=<folder> keeps a
screenshot of each at its most telling moment; SAB_TESTBED_COUNTS=<file> writes the action counts as JSON.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Locator, Page, expect
from tools.testbed import testbed
from tools.testbed.company import Company, make_company

from swissarmybench.renamed import env
from tests.e2e.test_ui import browser, call  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
STATE = testbed.read_state()
SHOTS = env("SWISSARMYBENCH_SHOTS") or None
LONG = 90_000  # milliseconds: a kernel's first start, a catalog's first load


def _why_not() -> str | None:
    if STATE is None:
        return (
            "The real-world test bed is not up: python tools/testbed/testbed.py up (tools/testbed/README.md)."
        )
    for database in ("postgres", "mariadb"):
        if "missing" in (STATE.get(database) or {"missing": database}):
            return f"The test bed has no {database}: {STATE[database].get('missing', '')}"
    for module in ("psycopg", "mariadb", "nbclient"):
        if importlib.util.find_spec(module) is None:
            return f"The test bed's drivers are not in this Python ({module}): see tools/testbed/README.md."
    return None


WHY_NOT = _why_not()
pytestmark = pytest.mark.skipif(WHY_NOT is not None, reason=WHY_NOT or "")
COUNTS: dict[str, int] = {}


class Actions:
    """The user's actions in one use case: each click, key, typed value, choice from a list and drag."""

    def __init__(self, case: str) -> None:
        self.case = case
        self.log: list[str] = []

    def _note(self, what: str) -> None:
        self.log.append(what)

    def click(self, target: Locator, **options: Any) -> None:
        target.click(**options)
        self._note("click")

    def fill(self, target: Locator, value: str) -> None:
        target.fill(value)
        self._note("type")

    def select(self, target: Locator, **options: Any) -> None:
        target.select_option(**options)
        self._note("choose")

    def press(self, page: Page, key: str) -> None:
        page.keyboard.press(key)
        self._note("key")

    def type_code(self, page: Page, code: str) -> None:
        """A cell's code, typed (one typed value: what the user writes, not each key)."""
        page.keyboard.insert_text(code)
        self._note("type")

    def drag(self, source: Locator, target: Locator, **options: Any) -> None:
        source.drag_to(target, **options)
        self._note("drag")

    def outside(self, what: str) -> None:
        """An action outside the app (a command typed, a file copied), counted as the user's."""
        self._note(what)

    @property
    def count(self) -> int:
        return len(self.log)

    def done(self, ceiling: int) -> None:
        COUNTS[self.case] = self.count
        out = os.environ.get("SAB_TESTBED_COUNTS")
        if out:
            path = Path(out)
            known = json.loads(path.read_text()) if path.exists() else {}
            path.write_text(json.dumps(known | {self.case: self.count}, indent=1))
        print(f"\n{self.case}: {self.count} actions")
        assert self.count <= ceiling, f"{self.case} took {self.count} actions (at most {ceiling}): {self.log}"


def shot(page: Page, name: str) -> None:
    if SHOTS:
        page.wait_for_timeout(500)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


# ===== the app, the stand-ins and the company =====


@pytest.fixture(scope="module")
def company() -> Company:
    return make_company()


@pytest.fixture(scope="module")
def standins(company: Company) -> Iterator[dict[str, Any]]:
    """The Power BI and Key Vault stand-ins, started before the app (its child processes read where)."""
    from tools.testbed.standins import KeyVault, power_bi

    powerbi = power_bi(company)
    vault = KeyVault({"shop-password": STATE["postgres"]["password"] if STATE else ""}).start()
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


@pytest.fixture(autouse=True)
def close_pages(browser: Browser) -> Iterator[None]:
    yield
    for context in list(browser.contexts):
        context.close()


def app_page(browser: Browser, bench: dict[str, Any]) -> Page:
    """The app's first page, as `swissarmybench` opens it."""
    context = browser.new_context(
        viewport={"width": 1600, "height": 950}, accept_downloads=True, device_scale_factor=2 if SHOTS else 1
    )
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{bench['port']}/workspace#token={bench['token']}")
    expect(page.locator(".app-row")).to_be_visible(timeout=20000)
    return page


def wait_until(done: Any, seconds: float = 90) -> None:
    for _ in range(int(seconds * 10)):
        if done():
            return
        time.sleep(0.1)
    raise AssertionError("It did not happen in time.")


def add_database(act: Actions, page: Page, kind: str, name: str, where: dict[str, Any]) -> None:
    """Connections, Add connection, a database's form filled in, Test, Save, Close."""
    dialog = page.locator("dialog")
    act.click(page.locator(".app-row").get_by_role("button", name="Connections"))
    act.click(page.get_by_role("button", name="Add connection"))
    act.click(page.locator(".connection-type", has_text=kind))
    act.fill(dialog.get_by_label("Name", exact=True), name)
    act.fill(dialog.get_by_label("Server", exact=True), where["host"])
    act.fill(dialog.get_by_label("Port", exact=True), str(where["port"]))
    act.fill(dialog.get_by_label("Database", exact=True), where["database"])
    act.fill(dialog.get_by_label("User", exact=True), where["user"])
    act.fill(dialog.get_by_label("Password", exact=True), where["password"])
    act.click(dialog.get_by_role("button", name="Test connection"))
    expect(dialog.locator(".connection-result")).to_contain_text("It works", timeout=LONG)
    act.click(dialog.get_by_role("button", name="Save"))
    expect(dialog.locator(".connection-row", has_text=name)).to_be_visible(timeout=20000)
    act.click(dialog.locator(".dialog-foot").get_by_role("button", name="Close"))


def open_catalog(act: Actions, page: Page) -> Page:
    """Blades and catalog: a window of its own."""
    with page.context.expect_page() as opened:
        act.click(page.locator(".app-row").get_by_role("button", name="Blades and catalog"))
    catalog = opened.value
    expect(catalog.locator('[role="treeitem"]').first).to_be_visible(timeout=LONG)
    return catalog


def open_as_grid(act: Actions, catalog: Page, table: str, schema: str | None = None) -> None:
    """A table of the catalog's tree, then its page's Open as grid."""
    tree = catalog.locator('[role="treeitem"]')
    if schema is not None:
        node = tree.filter(has=catalog.locator(f':scope > .node > .node-label:text-is("{schema}")'))
        if node.first.get_attribute("aria-expanded") == "false":
            act.click(node.first.locator(":scope > .node .node-label"))
    label = catalog.locator(f'[role="treeitem"] > .node > .node-label:text-is("{table}")').first
    act.click(label)
    act.click(catalog.locator("#detail").get_by_role("button", name="Open as grid"))
    expect(catalog.locator(".toast", has_text="is open as a grid")).to_be_visible(timeout=LONG)


def open_workbench(act: Actions, page: Page) -> Page:
    with page.context.expect_page() as opened:
        act.click(page.locator(".tab-workbench"))
    workbench = opened.value
    workbench.set_viewport_size({"width": 1600, "height": 950})
    expect(workbench.locator(".wb-welcome")).to_be_visible(timeout=20000)
    return workbench


def save_as(act: Actions, workbench: Page, name: str) -> None:
    """Save as…, the file's name, Save here (the chooser opens in the app's own folder)."""
    act.click(workbench.get_by_role("button", name="Save as…").first)
    chooser = workbench.locator(".file-chooser")
    act.fill(chooser.get_by_label("File name"), name)
    act.click(chooser.get_by_role("button", name="Save here"))
    expect(chooser).to_be_hidden(timeout=20000)


def type_into_cell(act: Actions, workbench: Page, cell: Locator, code: str) -> None:
    act.click(cell.locator(".monaco-editor"))
    act.type_code(workbench, code)


# ===== headless: a plain Python with the client wheel, no app =====


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


# ===== 1. orders from a database, cleaned in the grid, the notebook saved =====

EXPORT_CELL = 'orders.to_parquet("clean_orders.parquet")'


def test_1_orders_from_a_database_are_cleaned_in_the_grid_and_the_notebook_saved(
    browser: Browser, bench: dict[str, Any], company: Company
) -> None:
    act = Actions("1. orders from a database, cleaned, the notebook saved")
    page = app_page(browser, bench)
    add_database(act, page, "PostgreSQL", "Shop", STATE["postgres"] if STATE else {})
    catalog = open_catalog(act, page)
    open_as_grid(act, catalog, "orders")
    act.click(page.locator(".tab-item[data-grid]", has_text="orders"))  # back to the app's window
    page.bring_to_front()
    status = page.locator("#status")
    expect(status).to_contain_text("of 1,307", timeout=LONG)

    # Clean: the status trimmed and lower case, the web shop's test orders out, each order once.
    act.click(page.locator(".ag-header-cell[col-id='status'] .sab-header-name"))
    act.click(page.get_by_role("button", name="Clean text…"))
    dialog = page.locator("dialog[open]")
    act.click(dialog.get_by_role("button", name="Add step"))  # Trim both ends, the first choice
    act.click(page.get_by_role("button", name="Clean text…"))  # the column is still selected
    act.select(dialog.get_by_label("Clean-up"), label="lower case")
    act.click(dialog.get_by_role("button", name="Add step"))
    act.click(page.get_by_role("button", name="Filter…"))
    act.select(dialog.get_by_label("Condition"), label="does not equal")
    act.fill(dialog.get_by_label("Value", exact=True), "test")
    act.click(dialog.get_by_role("button", name="Add step"))
    act.click(page.get_by_role("button", name="Distinct rows"))
    clean = company.clean_orders()
    expect(status).to_contain_text(f"of {len(clean):,}", timeout=20000)
    # The column stayed selected through the steps, and its count is the cleaned view's.
    expect(status.locator("xpath=..")).to_contain_text(f"Count {len(clean):,}", timeout=20000)
    shot(page, "1-orders-cleaned-in-the-grid")

    # The notebook: its Tables group holds the table's cell (the steps as one query); one line of the
    # user's own writes the result; Run all; Save as.
    workbench = open_workbench(act, page)
    act.click(workbench.get_by_role("button", name="Start a notebook"))
    cell = workbench.locator(".wb-cell").first
    expect(cell.locator(".monaco-editor")).to_be_visible(timeout=20000)
    type_into_cell(act, workbench, cell, EXPORT_CELL)
    act.click(workbench.get_by_role("button", name="Run all"))
    folder = Path(bench["variables"]["SWISSARMYBENCH_WORKBENCH_DIR"])
    wait_until(lambda: (folder / "clean_orders.parquet").exists(), 120)
    save_as(act, workbench, "clean_orders.ipynb")
    shot(workbench, "1-the-notebook-saved")
    act.done(ceiling=40)

    saved = json.loads((folder / "clean_orders.ipynb").read_text(encoding="utf-8"))
    sources = ["".join(c["source"]) for c in saved["cells"]]
    load = next(s for s in sources if "sab.sql('Shop'" in s)
    assert "LIMIT" not in load  # the table came whole: read whole again
    for word in ("trim(", "lower(", "<> 'test'", "GROUP BY ALL"):
        assert word in load
    assert any(s.endswith(EXPORT_CELL) for s in sources)
    import pandas as pd

    written = pd.read_parquet(folder / "clean_orders.parquet")
    assert len(written) == len(clean) and set(written["status"]) == {
        "shipped",
        "delivered",
        "pending",
        "cancelled",
    }


# ===== 2. that notebook, run headless (on this computer, the app closed) =====


def test_2_the_saved_notebook_runs_headless_with_the_password_saved_on_this_computer(
    bench: dict[str, Any], plain_python: Path, company: Company, tmp_path: Path
) -> None:
    """As a scheduled task on this computer: `jupyter nbconvert --execute`, the app not running. The
    connection is this computer's saved one; its password the keyring's."""
    act = Actions("2. the notebook run headless")
    folder = Path(bench["variables"]["SWISSARMYBENCH_WORKBENCH_DIR"])
    if not (folder / "clean_orders.ipynb").exists():
        pytest.skip("use case 1 saves the notebook this one runs")
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
    act.outside("the scheduled command")
    ran = subprocess.run(command, cwd=work, env=variables, capture_output=True, text=True, timeout=600)
    assert ran.returncode == 0, ran.stderr[-3000:]
    import pandas as pd

    written = pd.read_parquet(work / "clean_orders.parquet")
    assert len(written) == len(company.clean_orders())
    act.done(ceiling=1)


# ===== 3. the same, with its password from an environment variable (an Azure Function) =====


def test_3_the_notebook_runs_as_an_azure_function_would_with_its_password_from_the_environment(
    browser: Browser, bench: dict[str, Any], plain_python: Path, company: Company, tmp_path: Path
) -> None:
    """No app, no saved connections, no keyring: the connection's exported file beside the notebook, and
    the password in the function's settings (SHOP_PASSWORD). A plain runner (nbclient), as a function's
    code would call it."""
    act = Actions("3. headless, the password from an environment variable")
    folder = Path(bench["variables"]["SWISSARMYBENCH_WORKBENCH_DIR"])
    if not (folder / "clean_orders.ipynb").exists():
        pytest.skip("use case 1 saves the notebook this one runs")
    page = app_page(browser, bench)
    catalog = open_catalog(act, page)
    act.click(catalog.locator(".blade-item", has_text="Shop").locator(".blade-name, .blade-text").first)
    with catalog.expect_download() as downloaded:
        act.click(catalog.get_by_role("button", name="Export", exact=True))
    function = tmp_path / "function"
    function.mkdir()
    downloaded.value.save_as(function / downloaded.value.suggested_filename)
    act.outside("the exported file and the notebook copied into the function's folder")
    shutil.copy(folder / "clean_orders.ipynb", function)
    assert STATE is not None
    exported = (function / downloaded.value.suggested_filename).read_text(encoding="utf-8")
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
    act.outside("SHOP_PASSWORD set in the function's settings")
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
    act.done(ceiling=6)
