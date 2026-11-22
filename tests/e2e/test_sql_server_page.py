# ruff: noqa: F811
"""SQL Server and Azure SQL in the page (domain/sql_server.py), on mssql-python: the form's ways to sign in
(a portable one first; this machine's only ones say so, amber), its folded Options (encryption; no driver to
choose), a server read from an environment variable; a failing card's plain error; Import relationships
putting a database's foreign keys into the model; an older connection's card and Update to the new driver;
the export's warning. The connections at the seam are tests/test_sql_server.py's stand-in (made-up rows, no
driver). Pictures go to SAB_SHOTS when it is set."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.sync_api import Browser, Page, expect

from swissarmybench.domain import sql_server
from tests.e2e.asks import answer_ask
from tests.e2e.test_ui import browser, call, not_now, open_grid, orders_url, server  # noqa: F401
from tests.test_sql_server import MSSQL_SAID, _stand_in

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
    page.locator(".area-page[data-page='connections']").get_by_role(
        "button", name="Add connection"
    ).first.click()
    page.locator(".connection-type", has_text="SQL Server").first.click()
    not_now(page)
    sign_in = dialog.get_by_role("combobox", name="Sign in")
    # A way that runs on a Function App or a hosted Streamlit app first (the owner, 2026-11-17).
    expect(sign_in.locator("option:checked")).to_have_text("User name and password (SQL login)")
    expect(sign_in.locator("option")).to_have_count(9)
    expect(dialog.locator(".local-only")).to_have_count(0)
    expect(code_box(dialog)).not_to_have_value(re.compile("pyodbc"))
    server_box = dialog.get_by_role("textbox", name="Server", exact=True)
    server_box.fill("sql01.shop.local")
    server_box.press("Tab")
    expect(code_box(dialog)).to_have_value(re.compile(r'server="sql01\.shop\.local"'))
    # Windows sign-in: this machine's only, said beside it in amber; no password.
    sign_in.select_option(label="Windows sign-in")
    note = dialog.locator(".sign-in-local .local-only")
    expect(note).to_contain_text("Only works on your machine: Windows sign-in uses this computer's own")
    expect(note).to_contain_text("On a Function App or hosted Streamlit app use")
    expect(dialog.locator(".connection-passwords")).to_have_count(0)
    shot(page, "sql-server-windows-warning")
    # The Entra password cannot do MFA: one line names the way that can, which is this machine's only.
    sign_in.select_option(label="Microsoft Entra: user name and password")
    expect(dialog.locator(".sign-in-note")).to_contain_text("This sign-in cannot do multi-factor sign-in")
    sign_in.select_option(
        label="Username, with multi-factor sign-in (a browser window, or a code on another device)"
    )
    expect(dialog.locator(".sign-in-note")).to_have_count(0)
    expect(note).to_contain_text("Only works on your machine: it needs you to approve the sign-in.")
    expect(code_box(dialog)).to_have_value(re.compile(r"MultiFactorSignIn\(tenant_id="))
    expect(dialog.get_by_role("textbox", name="Tenant id", exact=True)).to_be_visible()  # its own boxes
    shot(page, "sql-server-mfa")
    # A user name and password: the server typed stays, a Password box appears, from a variable at first.
    sign_in.select_option(label="User name and password (SQL login)")
    expect(dialog.locator(".sign-in-local .local-only")).to_have_count(0)
    expect(code_box(dialog)).to_have_value(re.compile(r'password=secret\("password"\)'))
    expect(code_box(dialog)).to_have_value(re.compile(r'server="sql01\.shop\.local"'))
    passwords = dialog.locator(".connection-passwords")
    expect(passwords).to_be_visible()
    # One box (12.7): a typed password is kept in this computer's keyring, said in amber while it is typed.
    expect(passwords.get_by_role("combobox", name=re.compile("comes from"))).to_have_count(0)
    password = passwords.get_by_label("Password", exact=True)
    password.fill("made-up-typed")
    expect(passwords.locator(".local-only")).to_contain_text(
        "its password is saved in this computer's keyring"
    )
    shot(page, "sql-server-keyring-warning")
    password.fill("${SQL_SERVER_PASSWORD}")
    expect(passwords.locator(".local-only")).to_have_count(0)
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
    expect(options.get_by_role("combobox", name="Driver")).to_have_count(0)  # mssql-python: none to choose
    # The server from an environment variable (a function app's setting), this computer's as its default.
    server_box.fill("${SQL_SERVER_SERVER:-sql01.shop.local}")
    server_box.press("Tab")
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
    words = sql_server.explain(MSSQL_SAID["40615"])
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
        expect(works.locator(".connection-card-about")).to_contain_text("mssql-python")
        shot(page, "sql-server-cards")
        failing.click()
        expect(dialog.locator(".error-note", has_text="Networking").first).to_be_visible()
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


def test_an_odbc_connection_says_it_works_only_here_and_an_older_one_updates_to_the_new_driver(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    golden = Path(__file__).parents[1] / "golden" / "sql_server"
    old = (golden / "old_sql_login.txt").read_text(encoding="utf-8")
    saved = {"kind": "sql", "dialect": "sqlserver"}
    call(server, "POST", "/connections", saved | {"name": "Ledger", "template": "sqlserver", "code": old})
    own = 'import pyodbc\n\nconn = pyodbc.connect("DSN=made_up_shop")\n'
    call(server, "POST", "/connections", saved | {"name": "Shop DSN", "template": "odbc", "code": own})
    try:
        page, dialog = connections(browser, orders_url)
        # The kind's own warning, on its card.
        odbc = dialog.locator(".connection-card[data-connection='Shop DSN']")
        expect(odbc.locator(".connection-card-local")).to_contain_text(
            "Only works on your machine: it needs an ODBC driver installed on this computer"
        )
        ledger = dialog.locator(".connection-card[data-connection='Ledger']")
        expect(ledger.locator(".connection-card-local")).to_have_count(0)  # a SQL login runs anywhere
        shot(page, "connections-local-card")
        # An older SQL Server connection (pyodbc): Update to the new driver, its settings kept.
        ledger.click()
        update = dialog.get_by_role("button", name="Update to the new driver")
        expect(update).to_be_visible()
        shot(page, "sql-server-update-offer")
        update.click()
        expect(page.locator(".toast").last).to_contain_text("Ledger now uses mssql-python")
        expect(dialog.get_by_role("button", name="Update to the new driver")).to_have_count(0)
        code = call(server, "GET", "/connections/Ledger")["code"]
        assert "pyodbc" not in code and code == (golden / "new_sql_login.txt").read_text(encoding="utf-8")
        # The ODBC one's detail says it too, amber.
        page.get_by_role("button", name="Back to Connections").first.click()
        odbc.click()
        expect(dialog.locator(".connection-local")).to_contain_text(
            "mssql-python for SQL Server and Azure SQL"
        )
        expect(dialog.get_by_role("button", name="Update to the new driver")).to_have_count(0)  # its own code
        shot(page, "connections-local-detail")
        # The form for the kind: its note before anything is typed.
        page.get_by_role("button", name="Back to Connections").first.click()
        page.locator(".area-page[data-page='connections']").get_by_role(
            "button", name="Add connection"
        ).first.click()
        dialog.locator(".connection-type", has_text="Any ODBC data source").first.click()
        not_now(page)
        expect(dialog.locator(".form-local")).to_contain_text("it needs an ODBC driver installed")
        page.close()
    finally:
        for name in ("Ledger", "Shop DSN"):
            try:
                call(server, "DELETE", f"/blades/{quote(name)}")
            except Exception:  # noqa: S110 (not saved: the test failed earlier)
                pass


def test_the_script_export_asks_before_it_writes_when_a_connection_runs_only_here(
    browser: Browser, orders_url: str, server: dict[str, Any], tmp_path: Path
) -> None:
    from tests.e2e.test_workbench_page import menu, new_script, open_workbench

    made = {"kind": "sql", "template": "sqlserver", "dialect": "sqlserver", "name": "Warehouse"}
    call(server, "POST", "/connections", made | {"code": sql_server.code("windows")})
    try:
        workbench = open_workbench(open_grid(browser, orders_url))
        new_script(workbench, 'import swissarmybench as sab\n\nconn = sab.connection("Warehouse")\n')
        folder = tmp_path / "jobs"
        folder.mkdir()
        asked: list[str] = []
        for attempt in (1, 2):
            menu(workbench, "Document menu", "Export as one Python script…")
            chooser = workbench.locator(".file-chooser")
            where = chooser.locator("input[aria-label=Folder]")
            where.fill(str(folder))
            where.press("Enter")
            # The chooser is in that folder (its breadcrumb ends with it), then its listing has said so.
            expect(chooser.locator(".file-crumb.current")).to_have_text(folder.name)
            expect(chooser.locator("[role=status]")).to_contain_text("folder")
            chooser.get_by_label("File name").fill("warehouse_automation.py")
            chooser.get_by_role("button", name="Save here").click()
            asked.append(answer_ask(workbench, yes=attempt == 2))  # the app's own question
            if attempt == 1:  # declined: nothing written
                expect(workbench.locator(".toast").last).to_contain_text("Nothing was exported.")
                assert not (folder / "warehouse_automation.py").exists()
        expect(workbench.locator(".toast").last).to_contain_text(
            "Exported warehouse_automation.py", timeout=20000
        )
        assert asked[0].startswith(
            "Only works on your machine, not on a Function App or a hosted Streamlit app"
        )
        assert "Warehouse: Windows sign-in" in asked[0] and asked[0].endswith("Export it anyway?")
        assert (folder / "warehouse_automation.py").exists()
        workbench.close()
    finally:
        call(server, "DELETE", "/blades/Warehouse")
