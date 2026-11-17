# ruff: noqa: F811
"""SQL Server and Azure SQL in the page (domain/sql_server.py): the form's ways to sign in, its folded
Options (encryption, the driver), a server read from an environment variable; a failing card's plain error;
Import relationships putting a database's foreign keys into the model. The connections at the seam are
tests/test_sql_server.py's stand-in (made-up rows, no driver). Pictures go to SAB_SHOTS when it is set."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.sync_api import Browser, Page, expect

from swissarmybench.domain import sql_server
from tests.e2e.test_ui import browser, call, not_now, open_grid, orders_url, server  # noqa: F401
from tests.test_sql_server import PYODBC_SAID, _stand_in

SHOTS = Path(os.environ.get("SAB_SHOTS") or tempfile.mkdtemp(prefix="sab-sqlserver-shots-"))


def code_box(page: Any) -> Any:
    return page.locator(".connection-code")


def shot(page: Page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"))


def connections(browser: Browser, url: str) -> tuple[Page, Any]:
    page = open_grid(browser, url, width=1440, height=1000, device_scale_factor=2)
    page.locator(".nav-rail [data-area='connections']").click()
    return page, page.locator(".area-page[data-page='connections']")


def test_sql_server_signs_in_every_way_with_its_options_folded(browser: Browser, orders_url: str) -> None:
    page, dialog = connections(browser, orders_url)
    page.get_by_role("button", name="Add connection").click()
    page.locator(".connection-type", has_text="SQL Server").first.click()
    not_now(page)
    sign_in = dialog.get_by_role("combobox", name="Sign in")
    expect(sign_in.locator("option:checked")).to_have_text("Windows sign-in")
    expect(sign_in.locator("option")).to_have_count(8)
    expect(dialog.locator(".connection-passwords")).to_have_count(0)  # Windows: no password
    server_box = dialog.get_by_role("textbox", name="Server", exact=True)
    server_box.fill("sql01.shop.local")
    server_box.press("Tab")
    expect(code_box(dialog)).to_have_value(re.compile(r'server="sql01\.shop\.local"'))
    # A user name and password: the server typed stays, a Password box appears.
    sign_in.select_option(label="User name and password (SQL login)")
    expect(code_box(dialog)).to_have_value(re.compile(r'password=secret\("password"\)'))
    expect(code_box(dialog)).to_have_value(re.compile(r'server="sql01\.shop\.local"'))
    expect(dialog.locator(".connection-passwords")).to_be_visible()
    # The options are folded: encryption a choice, Trust server certificate a tick, off by default.
    options = dialog.locator("details.connection-options")
    expect(options).not_to_have_attribute("open", "")
    options.locator("summary").click()
    encryption = options.get_by_role("combobox", name="Encryption")
    expect(encryption.locator("option:checked")).to_have_text("mandatory")
    encryption.select_option("strict")
    expect(code_box(dialog)).to_have_value(re.compile(r'encrypt="strict"'))
    trust = options.get_by_role("checkbox", name="Trust server certificate")
    expect(trust).not_to_be_checked()
    trust.check()
    expect(code_box(dialog)).to_have_value(re.compile(r"trust_server_certificate=True"))
    expect(options.get_by_role("combobox", name="Driver")).to_be_visible()
    # The server from an environment variable (a function app's setting), this computer's as its default.
    dialog.get_by_role("combobox", name="Server from").select_option(label="From an environment variable")
    variable = dialog.get_by_role("textbox", name="Server variable")
    expect(variable).to_have_value("SQL_SERVER_SERVER")
    expect(code_box(dialog)).to_have_value(
        re.compile(r'server=os\.environ\.get\("SQL_SERVER_SERVER", "sql01\.shop\.local"\)')
    )
    shot(page, "sql-server-form")
    # A managed identity: no password; the tick, the encryption and the variable kept.
    sign_in.select_option(label="Microsoft Entra: managed identity (in Azure)")
    expect(code_box(dialog)).to_have_value(re.compile(r'sign_in="managed_identity"'))
    expect(code_box(dialog)).to_have_value(re.compile(r"trust_server_certificate=True"))
    expect(code_box(dialog)).to_have_value(re.compile(r'os\.environ\.get\("SQL_SERVER_SERVER"'))
    expect(dialog.locator(".connection-passwords")).to_have_count(0)
    page.close()


def test_a_failing_card_says_why_and_import_relationships_fills_the_model(
    browser: Browser,
    orders_url: str,
    server: dict[str, Any],
) -> None:
    words = sql_server.explain(PYODBC_SAID["40615"])
    call(server, "POST", "/connections", _stand_in("Shop warehouse", fail=words))
    call(server, "POST", "/connections", _stand_in("Sales warehouse"))
    try:
        for name in ("Shop warehouse", "Sales warehouse"):
            try:
                call(server, "POST", f"/blades/{quote(name)}/test")
            except Exception:  # noqa: S110 (the failing one fails: that is the point)
                pass
        page, dialog = connections(browser, orders_url)
        failing = dialog.locator(".connection-card[data-connection='Shop warehouse']")
        expect(failing.locator(".connection-status")).to_have_text("Failing")
        expect(failing.locator(".connection-status")).to_have_attribute("title", re.compile("203.0.113.7"))
        works = dialog.locator(".connection-card[data-connection='Sales warehouse']")
        expect(works.locator(".connection-card-about")).to_contain_text("ODBC Driver 18 for SQL Server")
        shot(page, "sql-server-cards")
        failing.click()
        expect(dialog.locator(".connection-error")).to_contain_text("Networking")
        shot(page, "sql-server-failing")
        page.get_by_role("button", name="Back to Connections").first.click()
        works.click()
        expect(dialog.locator(".connection-about")).to_contain_text("GP_S_Gen5_1")
        dialog.get_by_role("button", name="Import relationships").click()
        expect(page.locator(".toast").last).to_contain_text("4 relationships from Sales warehouse")
        model = call(server, "GET", "/relationships")
        assert any(r["from"] == "Order_Lines" and r["to"] == "stock" for r in model["relationships"])
        shot(page, "sql-server-detail")
        page.close()
    finally:
        for name in ("Shop warehouse", "Sales warehouse"):
            try:
                call(server, "DELETE", f"/blades/{quote(name)}")
            except Exception:  # noqa: S110 (not saved: the test failed earlier)
                pass
