"""`${NAME}` in a connection's boxes (design principle 12.7), in a real browser: one box a field, typing `${`
offers the variables (their source in words, never a value), the line under the box says what it reads here
(a secret masked), a variable not set is the one error with Set it, and a PostgreSQL connection made with
references in its Server and Password boxes tests, saves and opens a table. Its own server, a keyring kept in
a temporary file, and this computer's own PostgreSQL on a free port (skipped when it is not installed).
Made-up names, values and rows only."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect
from tools.testbed import testbed
from tools.testbed.company import make_company

from swissarmybench.client import push_client
from tests.e2e.environment_helpers import open_settings, setting_row
from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_VARIABLE_REFS_SHOTS")
LONG = 30_000
HOST = "${WAREHOUSE_HOST}"
PASSWORD = "${WAREHOUSE_PASSWORD}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def postgres() -> Iterator[dict[str, Any]]:
    if testbed._pg_bin() is None:
        pytest.skip("PostgreSQL is not installed here")
    # A folder the postgres user can reach (pytest's own are the runner's only).
    data = Path(tempfile.mkdtemp(prefix="sab-variable-refs-")) / "data"
    try:
        info = testbed.start_postgres(make_company(), data, free_port())
    except (OSError, subprocess.CalledProcessError, SystemExit) as error:
        pytest.skip(f"PostgreSQL did not start here: {error}")
    try:
        yield info
    finally:
        testbed.stop_postgres(info)
        shutil.rmtree(data.parent, ignore_errors=True)


@pytest.fixture(scope="module")
def own_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("variable_refs")
    variables = {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "home" / "SwissArmyBench"),
        "PYTHON_KEYRING_BACKEND": "tests.file_keyring.FileKeyring",
        "SAB_TEST_KEYRING_FILE": str(tmp / "keyring.json"),
    }
    before = {name: os.environ.get(name) for name in variables}
    os.environ.update(variables)
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"])
    try:
        for _ in range(200):
            try:
                info = json.loads((tmp / "server.json").read_text())
                break
            except (OSError, ValueError):
                time.sleep(0.1)
        else:
            raise AssertionError("server did not start")
        yield info | {"tmp": tmp}
    finally:
        process.terminate()
        process.wait(timeout=20)
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def open_app(browser: Browser, server: dict[str, Any], dark: bool = False) -> Page:  # noqa: F811
    url = push_client.push(pd.DataFrame({"region": ["North", "South"], "sales": [12, 30]}), name="regions")
    page = browser.new_context(
        viewport={"width": 1300, "height": 900},
        device_scale_factor=2 if SHOTS else 1,
        color_scheme="dark" if dark else "light",
    ).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    return page


def postgres_form(page: Page) -> Any:
    dialog = page.locator(".area-page[data-page='connections']")
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").first.click()
    page.locator(".connection-type", has_text="PostgreSQL").click()
    expect(dialog.get_by_label("Server", exact=True)).to_be_visible()
    # Without psycopg in the server's Python the form asks for it at once (missingPackages.ts); Not now
    # here (the boxes are this file's subject; a test of the connection itself still needs the driver).
    if dialog.locator(".install-note").count():
        page.locator("dialog.missing-packages").get_by_role("button", name="Not now").click()
    return dialog


def test_a_connection_made_of_references_tests_saves_and_opens_a_table(
    browser: Browser,  # noqa: F811
    own_server: dict[str, Any],
    postgres: dict[str, Any],
) -> None:
    server = own_server
    call(server, "PUT", "/variables", {"name": "WAREHOUSE_HOST", "value": postgres["host"], "from": "value"})
    secret = {"name": "WAREHOUSE_PASSWORD", "value": postgres["password"], "from": "keyring"}
    call(server, "PUT", "/variables", secret, agent=True)
    page = open_app(browser, server)
    dialog = postgres_form(page)
    # No source pickers beside a box, and no insert button on it (the owner, 2026-11-19): one box each.
    expect(dialog.get_by_role("combobox", name="Password comes from")).to_have_count(0)
    expect(dialog.get_by_role("combobox", name="Server from")).to_have_count(0)
    expect(dialog.get_by_role("button", name="Insert a variable")).to_have_count(0)
    dialog.get_by_label("Name", exact=True).fill("Warehouse")

    # Typing ${ offers the variables: their names and where each comes from, never a value.
    host = dialog.get_by_label("Server", exact=True)
    host.click()
    host.press_sequentially("${WARE")
    offered = dialog.get_by_role("listbox", name="Variables")
    expect(offered).to_be_visible()
    expect(offered.get_by_role("option").first).to_contain_text("WAREHOUSE_HOST")
    expect(offered.get_by_role("option", name="WAREHOUSE_HOST Plain value")).to_be_visible()
    expect(offered.get_by_role("option").last).to_have_text("New variable WARE…")
    assert postgres["password"] not in offered.inner_text()
    shot(page, "variable-refs-list-light")
    host.press("Enter")
    expect(host).to_have_value(HOST)
    expect(offered).to_be_hidden()
    preview = host.locator("xpath=ancestor::span[contains(@class,'variable-box')]").locator(
        ".variable-preview"
    )
    expect(preview).to_have_text(postgres["host"])

    dialog.get_by_label("Port", exact=True).fill(str(postgres["port"]))
    dialog.get_by_label("Database", exact=True).fill(postgres["database"])
    dialog.get_by_label("User", exact=True).fill(postgres["user"])

    # The password: the same list from its right-click, Insert variable…; the line masked, never the value.
    password = dialog.get_by_label("Password", exact=True)
    box = password.locator("xpath=ancestor::span[contains(@class,'variable-box')]")
    password.click(button="right")
    page.locator(".context-menu").get_by_role("menuitem", name="Insert variable…").click()
    listed = page.get_by_role("listbox", name="Variables")
    expect(listed).to_be_visible()
    listed.get_by_role("option", name="WAREHOUSE_PASSWORD This computer's keyring").click()
    expect(password).to_have_value(PASSWORD)
    expect(password).to_have_attribute("type", "text")  # a reference reads as text, never as dots
    expect(box.locator(".variable-preview")).to_have_text("••••••••")
    shot(page, "variable-refs-preview-light")
    assert postgres["password"] not in page.content()

    dialog.get_by_role("button", name="Test connection").click()
    expect(dialog.locator(".connection-result")).to_contain_text("It works", timeout=LONG)
    dialog.get_by_role("button", name="Save").click()
    expect(dialog.locator(".area-page-title")).to_contain_text("Warehouse", timeout=20000)

    # Saved as references: the library holds the names, never the values.
    library = Path(server["tmp"]) / "state" / "library"
    saved = "\n".join(p.read_text(encoding="utf-8") for p in library.rglob("*.py"))
    assert 'os.environ["WAREHOUSE_HOST"]' in saved and "WAREHOUSE_PASSWORD" in saved
    assert postgres["password"] not in saved
    uses = call(server, "GET", "/variables/uses?name=WAREHOUSE_HOST", agent=True)["uses"]
    assert any(u["name"] == "Warehouse" for u in uses), uses

    # Its tables are read through the references, and one opens as a grid.
    tables = dialog.locator(".connection-tables .conn-tree-table")
    expect(tables.first).to_be_attached(timeout=LONG)
    dialog.locator(".conn-tree-table[data-table='customers']").first.get_by_role(
        "button", name="Open"
    ).click()
    expect(page.locator(".toast", has_text="is open as a grid").last).to_be_visible(timeout=LONG)

    # The Settings and secrets tab shows each setting's uses in fields: the connection and the box.
    found = open_settings(page)
    setting_row(page, "WAREHOUSE_HOST").click()
    expect(found.locator(".env-side .env-used")).to_contain_text("Warehouse · Server")
    page.context.close()


def test_a_variable_not_set_is_the_one_error_with_set_it(
    browser: Browser,  # noqa: F811
    own_server: dict[str, Any],
) -> None:
    call(own_server, "PUT", "/variables", {"name": "WAREHOUSE_HOST", "value": "127.0.0.1", "from": "value"})
    for dark in (False, True):
        if any(v["name"] == "SHOP_PORT" for v in call(own_server, "GET", "/variables")["variables"]):
            call(own_server, "DELETE", "/variables/SHOP_PORT")
        page = open_app(browser, own_server, dark)
        dialog = postgres_form(page)
        port = dialog.get_by_label("Port", exact=True)
        port.fill("${SHOP_PORT}")
        box = port.locator("xpath=ancestor::span[contains(@class,'variable-box')]")
        note = box.locator(".variable-preview .error-note")
        expect(note).to_contain_text("SHOP_PORT is not set on this computer")
        expect(note.get_by_role("button", name="Set it")).to_be_visible()
        theme = "dark" if dark else "light"
        shot(page, f"variable-refs-missing-{theme}")
        if dark:
            # The list and the preview in the dark theme too.
            host = dialog.get_by_label("Server", exact=True)
            host.click()
            host.press_sequentially("${WAREHOUSE_H")
            expect(dialog.get_by_role("listbox", name="Variables")).to_be_visible()
            shot(page, "variable-refs-list-dark")
            host.press("Enter")
            line = host.locator("xpath=ancestor::span[contains(@class,'variable-box')]").locator(
                ".variable-preview"
            )
            expect(line).to_have_text("127.0.0.1")
            shot(page, "variable-refs-preview-dark")
            page.context.close()
            continue
        # Set it: the Add variable form with its name; once added the line reads the value.
        note.get_by_role("button", name="Set it").click()
        form = page.locator("dialog .variables-form")
        expect(form.get_by_label("Name")).to_have_value("SHOP_PORT")
        form.get_by_label("Value").fill("5433")
        page.locator("dialog").get_by_role("button", name="Add").click()
        expect(box.locator(".variable-preview")).to_have_text("5433")
        expect(box.locator(".error-note")).to_have_count(0)
        # The escape: $${NAME} is the text, and reads nothing.
        port.fill("$${SHOP_PORT}")
        port.press("Tab")
        expect(box.locator(".variable-preview")).to_be_hidden()
        page.context.close()
