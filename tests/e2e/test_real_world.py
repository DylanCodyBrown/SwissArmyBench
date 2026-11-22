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
import re
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

from tests.e2e.test_ui import browser, call  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
STATE = testbed.read_state()
SHOTS = os.environ.get("SWISSARMYBENCH_SHOTS", "") or None
LONG = 90_000  # milliseconds: a kernel's first start, a catalog's first load


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
    expect(page.locator(".nav-rail")).to_be_visible(timeout=20000)
    return page


def wait_until(done: Any, seconds: float = 90) -> None:
    for _ in range(int(seconds * 10)):
        if done():
            return
        time.sleep(0.1)
    raise AssertionError("It did not happen in time.")


def add_database(act: Actions, page: Page, kind: str, name: str, where: dict[str, Any]) -> None:
    """Connections, Add connection, a database's form filled in, Test, Save, back to the grids."""
    dialog = page.locator(".area-page[data-page='connections']")
    act.click(page.locator(".nav-rail [data-area='connections']"))
    act.click(
        dialog.get_by_role("button", name="Add connection").first
    )  # the page's own (a page under it has one)
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
    expect(dialog.locator(".area-page-title")).to_contain_text(name, timeout=20000)  # its detail
    act.click(page.locator(".nav-rail [data-area='grids']"))


def open_blades(act: Actions, page: Page) -> Page:
    """The Scripts page's Blades pane (the blades page went, 2026-11-21; no rail icon, 2026-11-22: the rail's
    Scripts, then the status bar's Blades when it is hidden), in the Scripts page's window or this tab."""
    pages = len(page.context.pages)
    act.click(page.locator(".nav-rail [data-area='scripts']"))
    for _ in range(50):
        if len(page.context.pages) > pages:
            break
        if "/scripts" in page.url:
            break
        page.wait_for_timeout(100)
    blades = page.context.pages[-1] if len(page.context.pages) > pages else page
    toggle = blades.locator(".wb-status .side-toggle", has_text="Blades")
    expect(toggle).to_be_visible(timeout=LONG)
    if toggle.get_attribute("aria-pressed") != "true":
        act.click(toggle)
    expect(blades.locator(".wb-blades-side .blade-list")).to_be_visible(timeout=LONG)
    return blades


def open_catalog(act: Actions, page: Page) -> Page:
    """A connection's tables are on the Catalog page (the rail's Catalog: the one place to browse tables), in
    the same window; choose_catalog unfolds a connection there."""
    return page


_chosen: dict[str, str] = {}


def _unfold(act: Actions, node: Locator) -> None:
    """A tree node of the Catalog page opened (its caret), when it is not."""
    if node.get_attribute("aria-expanded") != "true":
        act.click(node.locator(":scope > .db-line .db-caret"))
    expect(node).to_have_attribute("aria-expanded", "true", timeout=LONG)


def choose_catalog(act: Actions, page: Page, name: str) -> None:
    """The Catalog page, a connection unfolded to its tables (loaded first when it is not)."""
    act.click(page.locator(".nav-rail [data-area='data']"))
    node = page.locator(f".db-tree li.kind-connection[aria-label='{name}']")
    expect(node).to_be_visible(timeout=LONG)
    load = node.locator(":scope > .db-line").get_by_role("button", name="Load")
    if load.count():
        act.click(load)
    _unfold(act, node)
    expect(node.locator("li.kind-table, li.kind-group").first).to_be_attached(timeout=LONG)
    _chosen[str(id(page))] = name


def tree_of(act: Actions, page: Page) -> Locator:
    """The connection chosen last (the first one listed when none was), shown again when an Open took the
    page to the grids."""
    name = _chosen.get(str(id(page)))
    if name is None:
        act.click(page.locator(".nav-rail [data-area='data']"))
        first = page.locator(".db-tree li.kind-connection").first
        expect(first).to_be_visible(timeout=LONG)
        name = str(first.get_attribute("aria-label"))
        choose_catalog(act, page, name)
    node = page.locator(f".db-tree li.kind-connection[aria-label='{name}']")
    if not node.count() or not node.first.is_visible():
        choose_catalog(act, page, name)
    return node.first


def _open_row(act: Actions, page: Page, within: Locator, table: str) -> None:
    row = within.locator(f"li.kind-table[aria-label='{table}']").first
    expect(row).to_be_attached(timeout=LONG)
    act.click(row.locator(":scope > .db-line").get_by_role("button", name="Open as grid"))


def open_as_grid(act: Actions, catalog: Page, table: str, schema: str | None = None) -> None:
    """A table of the connection's tree: its Open as grid."""
    tree = tree_of(act, catalog)
    within = tree
    if schema is not None:
        within = tree.locator(f"li.kind-group[aria-label='{schema}']").first
        _unfold(act, within)
    _open_row(act, catalog, within, table)
    expect(catalog.locator(".toast", has_text="is open as a grid").last).to_be_visible(timeout=LONG)
    back_to_grids(act, catalog)


def back_to_grids(act: Actions, page: Page) -> None:
    """The Catalog page is over the grids: the rail's Grids, when it is still in front (not counted: the old
    tree was in a window of its own, and going back to the app's window was not counted either)."""
    if page.locator(".area-page[data-page='data']").is_visible():
        page.locator(".nav-rail [data-area='grids']").click()


def open_workbench(act: Actions, page: Page) -> Page:
    with page.context.expect_page() as opened:
        page.evaluate("window.open('/workbench', 'swissarmybench-workbench')")
    workbench = opened.value
    workbench.set_viewport_size({"width": 1600, "height": 950})
    expect(workbench.locator(".wb-welcome")).to_be_visible(timeout=20000)
    return workbench


def save_as(act: Actions, workbench: Page, name: str) -> None:
    """Save as… (Ctrl+Shift+S: the page has no top bar since 2026-11-21), the file's name, Save here (the
    chooser opens in the app's own folder)."""
    act.press(workbench, "Control+Shift+S")
    chooser = workbench.locator(".file-chooser")
    act.fill(chooser.get_by_label("File name"), name)
    act.click(chooser.get_by_role("button", name="Save here"))
    expect(chooser).to_be_hidden(timeout=20000)
    # The chooser closes before the save is answered (use cases 5 and 10 sometimes copied or read the
    # file before it was there; the sweep, 2026-11-22): saved is the tab under the file's name, its dot gone.
    tab = workbench.locator(".wb-tab.active", has=workbench.locator(".tab-label", has_text=name))
    expect(tab.locator(".wb-tab-dirty")).to_have_text("", timeout=20000)


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
    catalog = open_blades(act, page)
    act.click(catalog.locator(".blade-item", has_text="Shop").locator(".blade-name, .blade-text").first)
    act.click(catalog.locator(".code-ide:visible").get_by_role("button", name="More"))  # its tab's IDE menu
    with catalog.expect_download() as downloaded:
        act.click(catalog.get_by_role("menuitem", name="Export"))
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


# ===== helpers for use cases 4 to 11 =====

PASTE = """text => {
  const data = new DataTransfer();
  data.setData("text/plain", text);
  document.activeElement.dispatchEvent(
    new ClipboardEvent("paste", {clipboardData: data, bubbles: true, cancelable: true}));
}"""


def paste_code(act: Actions, page: Page, code: str) -> None:
    """Code pasted into the editor that has the cursor (one typed value). Typed key by key, Monaco would
    indent each new line after the last: a person pastes code of more than one line."""
    page.evaluate(PASTE, code)
    act._note("type")


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


def blade_list(act: Actions, workbench: Page, family: str) -> Locator:
    """The Notebooks page's blade list (the Data Explorer pane's + Blade: the pane opened with Ctrl+Shift+E
    when it is folded), opened when it is not, with a family of starters open. On the Scripts page the
    blades are the Blades pane under the files."""
    if not workbench.locator(".wb-flyout:not([hidden])").count():
        add = workbench.get_by_role("button", name="Add a blade")
        if not add.is_visible():
            act.press(workbench, "Control+Shift+E")
            expect(add).to_be_visible(timeout=20000)
        act.click(add)
    listed = workbench.locator(".wb-flyout .blade-list")
    toggle = listed.locator(".starter-family", has_text=family)
    if toggle.get_attribute("aria-expanded") != "true":
        act.click(toggle)
    return listed


def drop_below(act: Actions, item: Locator, editor: Locator) -> None:
    """A blade dragged onto a cell's editor, under its last line (right of the blade list, which
    covers the editor's left edge while it is open)."""
    box = editor.bounding_box()
    assert box is not None
    act.drag(item, editor, target_position={"x": box["width"] - 60, "y": box["height"] - 4})


def cell_sources(bench: dict[str, Any]) -> list[str]:
    """The front Workbench document's cells, as the agent reads them."""
    read = call(bench, "POST", "/workbench/window", {"command": "doc.read", "args": {}}, agent=True)
    return [c["source"] for c in read["result"]["cells"]]


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


# ===== 4. Excel statements: one workbook per customer, from a template =====

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


def test_4_excel_statements_one_workbook_per_customer_from_a_template(
    browser: Browser, bench: dict[str, Any], company: Company
) -> None:
    act = Actions("4. Excel statements, one workbook per customer")
    ensure_shop(bench)
    close_tables(bench)
    assert STATE is not None
    page = app_page(browser, bench)
    catalog = open_catalog(act, page)
    choose_catalog(act, catalog, "Shop")
    open_as_grid(act, catalog, "invoices")
    open_as_grid(act, catalog, "customers")
    act.click(page.locator(".tab-item[data-grid]", has_text="invoices"))
    page.bring_to_front()
    expect(page.locator("#status")).to_contain_text(f"of {len(company.invoices):,}", timeout=LONG)
    # The open invoices only: a filter on the paid date.
    act.click(page.locator(".ag-header-cell[col-id='paid_date'] .sab-header-name"))
    expect(page.get_by_role("button", name="Filter…")).to_be_enabled()
    act.click(page.get_by_role("button", name="Filter…"))
    dialog = page.locator("dialog[open]")
    act.select(dialog.get_by_label("Condition"), label="is blank")
    act.click(dialog.get_by_role("button", name="Add step"))
    unpaid = [i for i in company.invoices if i["paid_date"] is None]
    expect(page.locator("#status")).to_contain_text(f"of {len(unpaid):,}", timeout=20000)

    # The notebook: the starter pack's three Excel blades dragged onto a cell, each its own line, and the
    # loop under them.
    workbench = open_workbench(act, page)
    act.click(workbench.get_by_role("button", name="Start a notebook"))
    editor = workbench.locator(".wb-cell").first.locator(".monaco-editor")
    expect(editor).to_be_visible(timeout=20000)
    for name in STARTERS:
        listed = blade_list(act, workbench, "Excel")
        drop_below(act, listed.locator(".starter-item", has_text=name), editor)
    act.click(editor.locator(".view-lines"))
    act.press(workbench, "Control+End")
    paste_code(act, workbench, statements_code(STATE["files"]["invoice_template"]))
    act.click(workbench.get_by_role("button", name="Run all"))
    folder = Path(bench["variables"]["SWISSARMYBENCH_WORKBENCH_DIR"]) / "statements"
    customers = {i["customer_id"] for i in unpaid}
    wait_until(lambda: folder.is_dir() and len(list(folder.glob("*.xlsx"))) == len(customers), 180)
    shot(workbench, "4-statements-written-from-the-template")
    save_as(act, workbench, "statements.ipynb")
    act.done(ceiling=30)

    saved = json.loads((folder.parent / "statements.ipynb").read_text(encoding="utf-8"))
    source = "".join(saved["cells"][-1]["source"])
    assert "$0" not in source
    for name, variable in zip(STARTERS, VARIABLES, strict=True):
        assert f'{variable} = sab.blade("{name}")\n' in source  # each on a line of its own
    check_statements(folder, company)


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


# ===== 5. a daily CSV export =====

DAILY_CODE = (
    "from pathlib import Path\n\n"
    'day = orders["order_date"].max()  # the newest day in the table: yesterday\'s, run each morning\n'
    'Path("exports").mkdir(exist_ok=True)\n'
    'orders[orders["order_date"] == day].to_csv(f"exports/orders_{day:%Y-%m-%d}.csv", index=False)\n'
)


def test_5_a_daily_csv_export_saved_and_run_as_the_scheduled_task_runs_it(
    browser: Browser, bench: dict[str, Any], company: Company, plain_python: Path, tmp_path: Path
) -> None:
    act = Actions("5. a daily CSV export")
    ensure_shop(bench)
    close_tables(bench)
    page = app_page(browser, bench)
    catalog = open_catalog(act, page)
    choose_catalog(act, catalog, "Shop")
    open_as_grid(act, catalog, "orders")
    page.bring_to_front()
    workbench = open_workbench(act, page)
    act.click(workbench.get_by_role("button", name="Start a notebook"))
    editor = workbench.locator(".wb-cell").first.locator(".monaco-editor")
    expect(editor).to_be_visible(timeout=20000)
    act.click(editor.locator(".view-lines"))
    paste_code(act, workbench, DAILY_CODE)
    act.click(workbench.get_by_role("button", name="Run all"))
    folder = Path(bench["variables"]["SWISSARMYBENCH_WORKBENCH_DIR"])
    last = max(o["order_date"] for o in company.orders)
    written = folder / "exports" / f"orders_{last.isoformat()}.csv"
    wait_until(lambda: written.exists(), 120)
    save_as(act, workbench, "daily_export.ipynb")
    shot(workbench, "5-the-daily-export-saved")

    # The scheduled task: the saved notebook run with the app closed, the password the keyring's.
    work = tmp_path / "scheduled"
    work.mkdir()
    shutil.copy(folder / "daily_export.ipynb", work)
    variables = plain_environment(
        tmp_path / "home",
        SWISSARMYBENCH_STATE=bench["variables"]["SWISSARMYBENCH_STATE"],
        XDG_DATA_HOME=bench["variables"]["XDG_DATA_HOME"],
        **{k: v for k, v in bench["variables"].items() if k == "PYTHON_KEYRING_BACKEND"},
    )
    command = [str(plain_python.parent / "jupyter"), "nbconvert", "--to", "notebook", "--execute"]
    act.outside("the scheduled command")
    ran = subprocess.run(
        [*command, "daily_export.ipynb", "--output", "ran.ipynb"],
        cwd=work,
        env=variables,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert ran.returncode == 0, ran.stderr[-3000:]
    act.done(ceiling=14)

    import pandas as pd

    for csv in (written, work / "exports" / written.name):
        day = pd.read_csv(csv)
        assert set(day["order_date"]) == {last.isoformat()}
        assert len(day) == sum(1 for o in company.orders if o["order_date"] == last)


# ===== 6. a CSV folder, workbook sheets and a database table combined, joins found =====


def test_6_a_csv_folder_workbook_sheets_and_a_database_table_are_combined_and_their_joins_found(
    browser: Browser, bench: dict[str, Any], company: Company
) -> None:
    act = Actions("6. files and a database combined, joins found")
    close_tables(bench)
    call(bench, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
    assert STATE is not None
    page = app_page(browser, bench)
    # The warehouse's MariaDB: its customers.
    if not any(c["name"] == "Warehouse" for c in call(bench, "GET", "/connections")["connections"]):
        add_database(act, page, "MariaDB", "Warehouse", STATE["mariadb"])
    catalog = open_catalog(act, page)
    choose_catalog(act, catalog, "Warehouse")
    open_as_grid(act, catalog, "customers")
    page.bring_to_front()
    # The buyers' workbook: both sheets (Open file…, the folder, the file, the second sheet ticked).
    act.click(page.get_by_role("button", name="Open file…"))
    where = page.locator(".file-chooser input[aria-label=Folder]")
    act.fill(where, STATE["files"]["folder"])
    act.press(page, "Enter")
    act.click(page.locator(".file-chooser .file-row.file", has_text="catalogue.xlsx"), click_count=2)
    sheets = page.locator("dialog", has_text="Open catalogue.xlsx")
    act.click(sheets.get_by_role("checkbox", name="Categories"))
    act.click(sheets.get_by_role("button", name="Open"))
    tabs = page.locator(".tab-item[data-grid]")
    expect(tabs.filter(has_text="catalogue_Categories")).to_have_count(1, timeout=LONG)
    # The web shop's daily CSV files, one table: the Files starter in a notebook, its result a grid.
    workbench = open_workbench(act, page)
    act.click(workbench.get_by_role("button", name="Start a notebook"))
    editor = workbench.locator(".wb-cell").first.locator(".monaco-editor")
    expect(editor).to_be_visible(timeout=20000)
    listed = blade_list(act, workbench, "Files")
    drop_below(act, listed.locator(".starter-item", has_text="Files combine CSVs"), editor)
    act.click(editor.locator(".view-lines"))
    act.press(workbench, "Control+End")
    paste_code(act, workbench, f'\ndaily = combine_csvs(r"{STATE["files"]["daily_orders"]}")\ndaily')
    act.click(workbench.get_by_role("button", name="Run all"))
    act.click(workbench.locator(".wb-to-grid:visible").last)
    expect(tabs.filter(has_text="daily")).to_have_count(1, timeout=LONG)
    # The joins: Find relationships in the ERD; the likely ones are added at once and drawn.
    page.bring_to_front()
    act.click(page.locator(".nav-rail [data-area='erd']"))
    act.click(page.locator("#erd-view").get_by_role("button", name="Find relationships"))
    found = page.locator("dialog[open] .suggestion-list")
    expect(found).to_be_visible(timeout=LONG)
    shot(page, "6-the-joins-found")
    for join in (
        "daily → customers on customer_id",
        "daily → catalogue_Products on sku",
        "catalogue_Products → catalogue_Categories on category_id",
    ):
        expect(found).to_contain_text(join)
    wait_until(lambda: len(call(bench, "GET", "/relationships")["relationships"]) >= 3, 30)
    act.done(ceiling=40)
    joins = {(j["from"], j["to"]) for j in call(bench, "GET", "/relationships")["relationships"]}
    assert {
        ("daily", "customers"),
        ("daily", "catalogue_Products"),
        ("catalogue_Products", "catalogue_Categories"),
    } <= joins
    daily = next(d for d in call(bench, "GET", "/datasets")["datasets"] if d["name"] == "daily")
    files = testbed.daily_exports(company, company.orders[-1]["order_date"])
    assert daily["rows"] == sum(len(rows) for rows in files.values())  # every file's rows, once


# ===== 7. a Power BI dataset's tables and relationships read in =====

COMPANY_TABLES = ("Customers", "Products", "Orders", "Order Lines", "Invoices")


def add_finance(act: Actions, page: Page) -> None:
    """The Power BI workspace, its app registration from the team's vault (the stand-in)."""
    from tests import powerbi_standin as made_up

    dialog = page.locator(".area-page[data-page='connections']")
    act.click(page.locator(".nav-rail [data-area='connections']"))
    act.click(dialog.get_by_role("button", name="Add connection").first)
    act.click(page.locator(".connection-type", has_text="Power BI workspace"))
    act.fill(dialog.get_by_role("textbox", name="Name"), "Finance")
    act.fill(dialog.get_by_role("textbox", name="Workspace id"), made_up.WORKSPACE)
    act.press(page, "Tab")  # the code takes the id when the box is left
    for label, entry in (
        ("Tenant id", "powerbi-tenant-id"),
        ("Client id", "powerbi-client-id"),
        ("Client secret", "powerbi-client-secret"),
    ):
        # One box (12.7): the vault's secret by its variable's name.
        box = dialog.locator(".connection-password").get_by_label(label, exact=True)
        act.fill(box, "${" + entry.replace("-", "_") + "}")
        box.press("Tab")
    act.click(dialog.get_by_role("button", name="Test connection"))
    expect(dialog.locator(".connection-result")).to_contain_text("It works", timeout=LONG)
    act.click(dialog.get_by_role("button", name="Save"))
    expect(dialog.locator(".area-page-title")).to_contain_text("Finance", timeout=20000)  # its detail
    act.click(page.locator(".nav-rail [data-area='grids']"))


def team_vault(bench: dict[str, Any]) -> None:
    """The team's key vault, already a connection (made once, long before; not counted)."""
    from tools.testbed.standins import KEYVAULT_CODE

    if any(c["name"] == "Team vault" for c in call(bench, "GET", "/connections")["connections"]):
        return
    vault = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault", "variable": "get"}
    call(
        bench, "POST", "/connections", vault | {"code": KEYVAULT_CODE, "vault_all": True, "vault_mapping": []}
    )


def dataset_item(catalog: Page, label: str, level: int = 1) -> Locator:
    """A Power BI dataset in the connection's tree on the Catalog page (its name kept: the page may be gone by
    the time a table of it is opened)."""
    found = catalog.locator(f".db-tree li.kind-group[aria-label='{label}']").first
    _datasets[id(found)] = label
    return found


_datasets: dict[int, str] = {}


def open_from_dataset(act: Actions, catalog: Page, dataset: Locator, table: str) -> None:
    """A dataset's table, its Open in the tree."""
    label = _datasets[id(dataset)]
    group = tree_of(act, catalog).locator(f"li.kind-group[aria-label='{label}']").first
    _unfold(act, group)
    _open_row(act, catalog, group, table)
    grid = table.replace(" ", "_")
    expect(catalog.locator(".toast", has_text=f"{grid} is open as a grid.")).to_have_count(1, timeout=LONG)


def test_7_a_power_bi_datasets_tables_and_relationships_are_read_in(
    browser: Browser, bench: dict[str, Any], company: Company
) -> None:
    act = Actions("7. a Power BI dataset's tables and relationships read in")
    close_tables(bench)
    call(bench, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
    team_vault(bench)
    page = app_page(browser, bench)
    add_finance(act, page)
    wait_until(lambda: any(c["name"] == "Finance" for c in call(bench, "GET", "/catalogs")["catalogs"]))
    catalog = open_catalog(act, page)
    choose_catalog(act, catalog, "Finance")
    model = dataset_item(catalog, "Company model")
    act.click(model.get_by_role("button", name="Import its relationships").first)
    expect(catalog.locator(".toast", has_text="5 relationships from Company model")).to_be_visible(
        timeout=LONG
    )
    # Its diagram is there before any table opens (it once said "No relationships yet").
    page.bring_to_front()
    act.click(page.locator(".nav-rail [data-area='erd']"))
    drawn = page.locator("#erd-view .erd-diagram svg")
    expect(drawn).to_be_visible(timeout=LONG)
    for table in ("Customers", "Order_Lines", "Invoices"):
        expect(drawn.get_by_text(table, exact=True).first).to_be_visible()
    shot(page, "7-the-power-bi-model-read-in")
    # Its tables, each opened from the dataset.
    catalog.bring_to_front()
    for table in COMPANY_TABLES:
        open_from_dataset(act, catalog, model, table)
    act.done(ceiling=30)
    last = max(i["invoice_date"] for i in company.invoices)
    opened = {d["name"]: d["rows"] for d in call(bench, "GET", "/datasets")["datasets"]}
    assert opened == {
        "Customers": len(company.customers),
        "Products": len(company.products),
        "Orders": len(company.clean_orders()),
        "Order_Lines": len(company.order_lines),
        "Invoices": sum(1 for i in company.invoices if i["invoice_date"] < last),
    }
    model_now = call(bench, "GET", "/relationships")
    assert len(model_now["relationships"]) == 5
    assert model_now["tables"]["Invoices"]["source"] == "Finance/Company model (Power BI)"


# ===== 8. a Power BI dataset tied out against its PostgreSQL source =====


def test_8_power_bi_ties_out_against_its_postgresql_source(
    browser: Browser, bench: dict[str, Any], company: Company
) -> None:
    act = Actions("8. Power BI tied out against PostgreSQL")
    ensure_shop(bench)
    close_tables(bench)
    team_vault(bench)
    page = app_page(browser, bench)
    if not any(c["name"] == "Finance" for c in call(bench, "GET", "/connections")["connections"]):
        add_finance(act, page)
    catalog = open_catalog(act, page)
    choose_catalog(act, catalog, "Finance")
    model = dataset_item(catalog, "Company model")
    open_from_dataset(act, catalog, model, "Invoices")
    choose_catalog(act, catalog, "Shop")
    open_as_grid(act, catalog, "invoices")
    page.bring_to_front()
    tabs = page.locator(".tab-item")
    # PostgreSQL's invoices open beside Power BI's Invoices (once refused: the names differ only in case).
    expect(tabs.filter(has_text="Shop_invoices")).to_have_count(1, timeout=LONG)
    # The tie-out is on the Analyze page (the owner, 2026-11-19: every analysis there, none on the grid's
    # Compare row): the open table, the other open one picked already, its result on the board by itself.
    act.click(page.locator(".nav-rail [data-area='analyze']"))
    act.click(page.locator("#ai-panel .analyze-btn[data-analysis='tie_out']"))
    form = page.locator("#ai-panel .analyze-side .analyze-form")
    expect(form.get_by_role("button", name="Run", exact=True)).to_be_enabled(timeout=LONG)
    act.click(form.get_by_role("button", name="Run", exact=True))
    board = page.locator("#ai-panel .analyze-board")
    note = board.locator(".card", has_text="Tie-out:").first
    last = max(i["invoice_date"] for i in company.invoices)
    off = sorted({i["region"] for i in company.invoices if i["invoice_date"] == last})
    verb = "is" if len(off) == 1 else "are"
    expect(note).to_contain_text(f"{len(off)} of 4 groups {verb} off.", timeout=LONG)
    table = board.locator(".card", has_text="Tie-out by").first
    rows = table.locator("tbody tr")
    expect(rows).to_have_count(4, timeout=LONG)
    for region in off:
        expect(rows.filter(has_text=region)).to_contain_text("off")
    expect(table.locator("tbody")).not_to_contain_text("-0")  # a group that ties shows 0, never -0
    shot(page, "8-power-bi-tied-out-against-postgresql")
    act.done(ceiling=22)


# ===== 9. a forecast as an Analyze report, printed to PDF =====

# window.print noted with the page's classes then (and each change of them, to say what went wrong if
# the print view was not on: once seen in a full run, not again).
PRINT_STUB = """() => {
  window.__log = [];
  window.print = () => {
    window.__printed = document.body.className;
    window.__log.push("print " + document.body.className);
  };
  new MutationObserver(() => window.__log.push("class " + document.body.className))
    .observe(document.body, {attributes: true, attributeFilter: ["class"]});
}"""


def test_9_a_forecast_becomes_a_sandbox_report_printed_to_pdf(
    browser: Browser, bench: dict[str, Any], tmp_path: Path
) -> None:
    act = Actions("9. a forecast as an Analyze report, printed to PDF")
    ensure_shop(bench)
    close_tables(bench)
    for card in call(bench, "GET", "/cards")["cards"]:
        call(bench, "DELETE", f"/cards/{card['id']}")
    page = app_page(browser, bench)
    # The browser's print dialog cannot be answered headless: noted, then printed below as Save as PDF.
    page.evaluate(PRINT_STUB)
    catalog = open_catalog(act, page)
    choose_catalog(act, catalog, "Shop")
    open_as_grid(act, catalog, "invoices")
    page.bring_to_front()
    act.click(page.locator(".tab-item[data-grid]", has_text="invoices"))
    # The Analyze page (2026-11-19): the forecast's form has the table and the columns picked already, and
    # its result lands on the board by itself (the rail, the analysis, the period, Run).
    act.click(page.locator(".nav-rail [data-area='analyze']"))
    act.click(page.locator("#ai-panel .analyze-btn[data-analysis='forecast']"))
    form = page.locator("#ai-panel .analyze-side .analyze-form")
    date = form.locator(".analyze-chip-row[data-slot='date'] select.chip-select")
    expect(date).to_have_value("invoice_date", timeout=LONG)
    expect(form.locator(".analyze-chip-row[data-slot='metric'] select.chip-select")).to_have_value("amount")
    # A year of invoices is picked as weeks from the dates (domain/analyze.py period_for: a few dozen
    # points); the report is by month, chosen under More options.
    act.click(form.locator("details.analyze-more > summary"))
    act.select(form.locator(".analyze-option[data-option='period'] select"), value="month")
    expect(form.locator(".analyze-option[data-option='period'] select")).to_have_value("month", timeout=LONG)
    act.click(form.get_by_role("button", name="Run", exact=True))
    cards = page.locator("#ai-panel .analyze-board .card")
    expect(cards).to_have_count(2, timeout=LONG)  # the note and its chart (once only the note came)
    words = cards.first
    # November has one day of invoices: left out, and said so (it once counted as a month: a 99% fall).
    expect(words).to_contain_text("Left out 2026-11-01: its rows stop on 2026-11-01", timeout=LONG)
    expect(words).not_to_contain_text("e+0")  # 73,771, never 7.377e+04
    expect(page.locator("#ai-panel .figure .main-svg").first).to_be_visible(timeout=LONG)
    act.click(page.get_by_role("button", name="Page view"))
    expect(page.locator(".page").first).to_be_visible(timeout=20000)
    shot(page, "9-the-forecast-report-on-a-page")
    act.click(page.get_by_role("button", name="Print to PDF"))
    page.wait_for_function("window.__printed !== undefined", timeout=20000)
    assert "sandbox-printing" in page.evaluate("window.__printed"), page.evaluate("window.__log")
    act.done(ceiling=16)
    # What Save as PDF writes: the page as printed (Chromium's own PDF of the print view).
    page.evaluate("document.body.classList.add('sandbox-printing')")
    page.emulate_media(media="print")
    pdf = page.pdf(prefer_css_page_size=True, print_background=True)
    assert pdf.startswith(b"%PDF") and len(pdf) > 20_000
    (tmp_path / "forecast.pdf").write_bytes(pdf)
    if SHOTS:
        (Path(SHOTS) / "9-the-forecast-report.pdf").write_bytes(pdf)


# ===== 10. a story notebook: HTML cells, Markdown's live values and a Mermaid diagram =====

FIGURES = (
    'total = round(float(invoices["amount"].sum()), 2)\n'
    'open_invoices = int(invoices["paid_date"].isna().sum())\n'
    'by_region = invoices.groupby("region", as_index=False)["amount"].sum().round(2)\n'
)
STORY = (
    "# The year in invoices\n\n"
    "Invoiced in all: **{{ total }}**, with {{ open_invoices }} invoices still open.\n\n"
    "{{ by_region }}\n\n"
    "```mermaid\nflowchart LR\n  Order --> Invoice --> Payment\n```\n"
)
KPI = (
    '<div style="display:flex;gap:12px;font-family:sans-serif">\n'
    '  <div style="padding:12px;border-radius:8px;background:#0b6e4f;color:#fff">Invoiced<br>'
    '<b class="kpi-total">{{ total }}</b></div>\n'
    '  <div style="padding:12px;border-radius:8px;background:#8a1c1c;color:#fff">Open<br>'
    '<b class="kpi-open">{{ open_invoices }}</b></div>\n'
    "</div>"
)


def test_10_a_story_notebook_with_html_cells_live_markdown_and_a_mermaid_diagram(
    browser: Browser, bench: dict[str, Any], company: Company
) -> None:
    act = Actions("10. a story notebook")
    ensure_shop(bench)
    close_tables(bench)
    page = app_page(browser, bench)
    catalog = open_catalog(act, page)
    choose_catalog(act, catalog, "Shop")
    open_as_grid(act, catalog, "invoices")
    page.bring_to_front()
    workbench = open_workbench(act, page)
    act.click(workbench.get_by_role("button", name="Start a notebook"))
    cells = workbench.locator(".wb-cell")
    expect(cells.first.locator(".monaco-editor")).to_be_visible(timeout=20000)
    act.click(cells.first.locator(".monaco-editor .view-lines"))
    paste_code(act, workbench, FIGURES)
    for kind, text in (("Markdown", STORY), ("HTML", KPI)):
        act.click(workbench.get_by_role("button", name="Add cell"))
        act.click(workbench.get_by_role("menuitem", name=kind))
        editor = cells.last.locator(".monaco-editor")
        expect(editor).to_be_visible(timeout=20000)
        act.click(editor.locator(".view-lines"))
        paste_code(act, workbench, text)
    act.click(workbench.get_by_role("button", name="Run all"))
    total = round(sum(float(i["amount"]) for i in company.invoices), 2)
    open_count = sum(1 for i in company.invoices if i["paid_date"] is None)
    story = cells.nth(1).locator(".wb-markdown-view")
    expect(story.locator("strong")).to_have_text(str(total), timeout=LONG)
    expect(story).to_contain_text(f"with {open_count} invoices still open")
    expect(story.locator("table tbody tr")).to_have_count(4)  # by region, as a table
    expect(story.locator(".md-mermaid svg g.node")).to_have_count(3, timeout=LONG)
    design = cells.nth(2).frame_locator(".wb-design-frame")
    expect(design.locator(".kpi-total")).to_have_text(str(total), timeout=LONG)
    expect(design.locator(".kpi-open")).to_have_text(str(open_count))
    save_as(act, workbench, "story.ipynb")
    shot(workbench, "10-the-story-notebook")
    act.done(ceiling=22)
    saved = json.loads(
        (Path(bench["variables"]["SWISSARMYBENCH_WORKBENCH_DIR"]) / "story.ipynb").read_text(encoding="utf-8")
    )
    firsts = ["".join(c["source"]).split("\n", 1)[0] for c in saved["cells"] if c["cell_type"] == "code"]
    assert any(line.startswith("%%html") for line in firsts)
    assert any("```mermaid" in "".join(c["source"]) for c in saved["cells"] if c["cell_type"] == "markdown")


# ===== 11. a widget made in its window, placed on a canvas in both layouts, played, exported =====

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
APP_TEST = """import json
import sys

from streamlit.testing.v1 import AppTest

page = AppTest.from_file(sys.argv[1], default_timeout=300).run()
print(json.dumps({
    "exceptions": [str(e.value) for e in page.exception],
    "errors": [str(e.value) for e in page.error],
    "metrics": [m.value for m in page.metric],
}))
"""


def streamlit_python() -> str:
    from tests.streamlit_helpers import STREAMLIT_PYTHON

    if STREAMLIT_PYTHON is None:
        pytest.skip("no Python with Streamlit here (set SWISSARMYBENCH_STREAMLIT_PYTHON to one)")
    return STREAMLIT_PYTHON


def run_exported(folder: Path, plain_python: Path, tmp_path: Path) -> dict[str, Any]:
    """The exported app run by Streamlit's AppTest in a plain Python with no app (as a hosted Streamlit app
    runs it): its own app.py, its pages, sab_canvas.py and sab_widgets.py, the invoices as Parquet."""
    (folder / "apptest.py").write_text(APP_TEST, encoding="utf-8")
    ran = subprocess.run(
        [str(plain_python), "apptest.py", "app.py"],
        cwd=folder,
        env=plain_environment(tmp_path / "home", PYTHONPATH=str(folder)),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert ran.returncode == 0, ran.stderr[-3000:]
    shown: dict[str, Any] = json.loads(ran.stdout.strip().splitlines()[-1])
    return shown


def test_11_a_widget_made_in_its_window_on_a_canvas_in_both_layouts_played_and_exported(
    browser: Browser, bench: dict[str, Any], company: Company, plain_python: Path, tmp_path: Path
) -> None:
    act = Actions("11. a widget on a canvas, both layouts, played, exported")
    streamlit_python()
    ensure_shop(bench)
    close_tables(bench)
    for gone in ("invoice_total",):
        try:
            call(bench, "DELETE", f"/streamlit/widgets/{gone}")
        except Exception:  # noqa: S110 (none yet)
            pass
    page = app_page(browser, bench)
    catalog = open_catalog(act, page)
    choose_catalog(act, catalog, "Shop")
    open_as_grid(act, catalog, "invoices")
    page.bring_to_front()
    # A Streamlit project: its canvas comes with it.
    act.click(page.locator('.nav-rail [data-area="projects"]'))
    act.click(
        page.locator('.area-page[data-page="projects"]').get_by_role("button", name="New project").first
    )
    dialog = page.locator("dialog.new-project")
    act.fill(dialog.get_by_label("Name"), "quillmere app")
    act.click(dialog.locator(".new-project-type[data-type='streamlit']"))
    act.click(dialog.get_by_role("button", name="Create"))
    expect(page.locator(".project-group .project-name")).to_have_text(
        re.compile("quillmere app"), timeout=LONG
    )
    project = Path(call(bench, "GET", "/project")["project"]["folder"])
    # The Widgets window (the rail's Widgets: a window of its own): New widget, its code, its name.
    with page.context.expect_page(timeout=LONG) as opened:
        act.click(page.locator('.nav-rail [data-area="widgets"]'))
    widgets = opened.value
    expect(widgets.locator(".wg-new")).to_be_visible(timeout=LONG)
    act.click(widgets.locator(".wg-new"))
    editor = widgets.locator(".ide-editor .monaco-editor")
    expect(editor).to_be_visible(timeout=LONG)
    act.click(editor.locator(".view-lines"))
    act.press(widgets, "Control+a")
    paste_code(act, widgets, WIDGET)
    props = widgets.locator(".wg-props")
    expect(props.locator(".wg-prop[data-property='table_name']")).to_have_attribute(
        "data-mask", "table", timeout=20000
    )
    expect(props.locator(".wg-prop[data-property='colour']")).to_have_attribute("data-mask", "colour")
    act.fill(props.locator(".wg-name"), "invoice_total")
    act.press(widgets, "Enter")
    wait_until(
        lambda: "invoice_total" in {w["name"] for w in call(bench, "GET", "/streamlit/widgets")["widgets"]}
    )
    wait_until(lambda: "len(rows)" in call(bench, "GET", "/streamlit/widgets/invoice_total")["code"])
    # Preview (F5): the widget in the editor's place, the invoices counted.
    act.click(editor.locator(".view-lines"))
    act.press(widgets, "F5")
    frame = widgets.frame_locator(".wg-frame")
    expect(frame.locator('[data-testid="stMetricValue"]')).to_have_text(
        f"{len(company.invoices):,}", timeout=LONG
    )
    shot(widgets, "11-the-widget-previewed")
    # The Canvas (the rail's Canvas): the project's canvas, a container drawn, the widget inserted.
    page.bring_to_front()
    act.click(page.locator('.nav-rail [data-area="canvas"]'))
    act.click(page.locator(".cvs-landing-item").first)
    board = page.locator(".cvs-board")
    expect(board).to_be_visible(timeout=LONG)
    page.wait_for_function("document.querySelector('.cvs-board').offsetWidth >= 390", timeout=LONG)
    box = board.bounding_box()
    assert box
    page.mouse.move(box["x"] + 24, box["y"] + 24)
    page.mouse.down()
    page.mouse.move(box["x"] + 300, box["y"] + 150, steps=4)
    page.mouse.move(box["x"] + 520, box["y"] + 240, steps=6)
    page.mouse.up()
    act._note("drag")
    container = page.locator(".cvs-container").first
    expect(container).to_be_visible(timeout=20000)
    act.click(container, button="right", position={"x": 40, "y": 40})
    act.click(page.locator(".cvs-menu-item", has_text="Insert widget"))
    act.fill(page.locator(".cvs-widget-menu .cvs-menu-search"), "invoice")
    act.click(page.locator(".cvs-widget-menu .cvs-menu-item[data-widget='invoice_total']"))
    expect(page.locator(".cvs-widget[data-widget='invoice_total']")).to_have_count(1, timeout=20000)
    # Both layouts: the Phone layout has it too, stacked at the full width (nothing more to do).
    act.click(page.locator(".cvs-bottom [data-layout='phone']"))
    expect(page.locator(".cvs-widget[data-widget='invoice_total']")).to_be_visible()
    canvas_file = next(project.glob("*.canvas.json"))
    saved = json.loads(canvas_file.read_text(encoding="utf-8"))
    placed = saved["pages"][0]["children"][0]["children"][0]
    assert placed["widget"] == "invoice_total" and set(placed["at"]) == {"desktop", "phone"}
    shot(page, "11-the-canvas-phone")
    act.click(page.locator(".cvs-bottom [data-layout='desktop']"))
    # Play (F5): the page live in place, the invoices counted.
    act.click(board)
    act.press(page, "F5")
    live = page.frame_locator(".cvs-live-frame")
    expect(live.locator('[data-testid="stMetricValue"]')).to_have_text(
        f"{len(company.invoices):,}", timeout=LONG
    )
    shot(page, "11-the-canvas-played")
    act.click(page.locator(".cvs-top .cvs-play"))  # Stop
    # Export (Ctrl+Shift+E): an app that runs alone, into a folder.
    out = tmp_path / "exported"
    out.mkdir()
    act.press(page, "Control+Shift+E")
    chooser = page.locator("dialog.file-chooser")
    where = chooser.get_by_role("textbox", name="Folder")
    act.fill(where, str(out))
    act.press(page, "Enter")
    act.click(chooser.get_by_role("button", name="Choose this folder"))
    wait_until(lambda: (out / "app.py").exists() and (out / "data" / "invoices.parquet").exists())
    act.done(ceiling=34)
    shown = run_exported(out, plain_python, tmp_path)
    assert shown["exceptions"] == [] and shown["errors"] == [], shown
    assert shown["metrics"] == [f"{len(company.invoices):,}"], shown
    widgets.close()


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


# ===== agent parity: use case 1 through the agent's MCP commands only =====


def test_1a_the_agent_cleans_the_orders_and_saves_the_notebook_through_its_commands_only(
    bench: dict[str, Any], company: Company, tmp_path: Path
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
    book = tmp_path / "clean_orders.ipynb"
    agent(
        "workbench_save",
        path=str(book),
        cells=[{"kind": "code", "source": table["loaded"]}, {"kind": "code", "source": EXPORT_CELL}],
    )
    ran = agent("workbench_run_notebook", path=str(book))
    assert ran["cells_run"] == 2 and "Error" not in json.dumps(ran["results"]), ran
    import pandas as pd

    assert len(pd.read_parquet(tmp_path / "clean_orders.parquet")) == len(company.clean_orders())
