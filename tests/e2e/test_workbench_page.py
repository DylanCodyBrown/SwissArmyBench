# ruff: noqa: F811
"""The Connections window and the Workbench in a real browser (Plans/workbench-and-connections.plan.md).

Made-up data only: a CSV of three orders in the test's own folder. No test saves a password: on Windows
that would reach the real Credential Manager.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from playwright.sync_api import Browser, Page, expect

# The grid tests' fixtures (browser, server, orders_url), imported by name.
from tests.e2e.test_ui import browser, call, not_now, open_grid, orders_url, server  # noqa: F401


@pytest.fixture
def orders_csv(tmp_path: Path, server: dict[str, Any]) -> Iterator[Path]:
    csv = tmp_path / "shop" / "orders.csv"
    csv.parent.mkdir()
    csv.write_text("order_id,region,amount\n1,North,10.5\n2,South,7\n3,North,2.5\n", encoding="utf-8")
    seen_by_server(server, csv.parent)
    yield csv
    for name in ("orders", "Orders"):
        try:
            call(server, "DELETE", f"/blades/{quote(name)}")
        except Exception:  # noqa: S110 (not saved by this test)
            pass


def seen_by_server(server: dict[str, Any], folder: Path) -> None:
    """Wait until the server's own process lists a folder this test just made: in this sandbox a new
    folder under pytest's temporary folder was now and then not there yet for the server (a few
    seconds), and the chooser said so."""
    import time

    for _ in range(100):
        try:
            if call(server, "GET", f"/folders?path={quote(str(folder))}")["files"]:
                return
        except Exception:  # noqa: S110 (not there yet)
            pass
        time.sleep(0.1)


def wait_until(done: Any, seconds: float = 60) -> None:
    """Wait for something the page no longer says in words (a catalog that has loaded, say)."""
    import time

    for _ in range(int(seconds * 10)):
        if done():
            return
        time.sleep(0.1)
    raise AssertionError("It did not happen in time.")


def test_a_connection_is_added_with_a_form_tested_and_saved(
    browser: Browser, orders_url: str, server: dict[str, Any], orders_csv: Path
) -> None:
    page = open_grid(browser, orders_url)
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").click()
    page.locator(".connection-type", has_text="CSV file").click()
    # Browse… lists the folder through the server: a real path, which a browser's own picker hides.
    page.get_by_role("button", name="Browse…").click()
    folder = page.locator(".file-chooser input[aria-label=Folder]")
    folder.fill(str(orders_csv.parent))
    folder.press("Enter")
    page.locator(".file-chooser .file-row.file", has_text="orders.csv").dblclick()
    name = page.locator(".area-page").get_by_role("textbox", name="Name", exact=True)
    expect(name).to_have_value("orders")  # named after the file
    page.get_by_role("button", name="Test connection").click()
    expect(page.locator(".connection-result")).to_contain_text("It works: a file of", timeout=30000)
    # Test shows what is in the file: its columns and its first rows (decision 11).
    preview = page.locator(".connection-result .connection-preview")
    expect(preview.locator("th")).to_have_text(["order_id", "region", "amount"])
    expect(preview.locator("tbody tr")).to_have_count(3)
    expect(preview.locator("tbody tr").first.locator("td")).to_have_text(["1", "North", "10.5"])
    expect(page.locator(".connection-result")).to_contain_text("3 columns, the first 3 rows")
    page.locator(".area-page-foot").get_by_role("button", name="Save").click()
    # Saved: its detail (the Connections page, 2026-11-16), the name it has in code.
    expect(page.locator(".area-page-title")).to_contain_text("orders")
    expect(page.locator(".connection-config")).to_contain_text('sab.connection("orders")')
    # Its catalog loads itself in the background (no Refresh pressed); the cards are drawn again as it
    # lands, once: one card, one set of buttons.
    wait_until(lambda: call(server, "GET", "/connections")["connections"][0]["catalog_loaded"])
    page.locator(".nav-rail [data-area='connections']").click()
    card = page.locator(".connection-card", has_text="orders")
    expect(card).not_to_have_class(re.compile(r"st-failing"))
    expect(page.locator(".area-page-actions").get_by_role("button", name="Add connection")).to_have_count(1)
    expect(page.locator(".connection-card")).to_have_count(1)
    listed = call(server, "GET", "/connections")["connections"]
    assert [(c["name"], c["connection"]) for c in listed] == [("orders", "file")]


def test_a_file_connection_is_named_after_a_typed_path_and_tested_before_it_is_named(
    browser: Browser, orders_url: str, server: dict[str, Any], orders_csv: Path
) -> None:
    page = open_grid(browser, orders_url)
    dialog = page.locator(".area-page[data-page='connections']")
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").click()
    page.locator(".connection-type", has_text="CSV file").click()
    name = dialog.get_by_role("textbox", name="Name", exact=True)
    expect(name).to_have_value("")
    # The path typed (not picked): the name follows it, as it does a picked file.
    path = dialog.get_by_role("textbox", name="Path")
    path.fill(str(orders_csv))
    path.press("Tab")
    expect(name).to_have_value("orders")
    # With the Name box emptied, Test still runs, under the file's name, and puts it back.
    name.fill("")
    page.get_by_role("button", name="Test connection").click()
    expect(page.locator(".connection-result .connection-preview th")).to_have_text(
        ["order_id", "region", "amount"], timeout=30000
    )
    expect(name).to_have_value("orders")
    # A name the user typed is theirs: another path does not change it.
    name.fill("Shop orders")
    path.fill(str(orders_csv.parent / "other.csv"))
    path.press("Tab")
    expect(name).to_have_value("Shop orders")


MADE_UP = "made-up-trino-driver"


def stand_in_missing(page: Page, installed: dict[str, Any]) -> list[Any]:
    """The package check stood in for: the Trino form needs a made-up package until the stand-in
    installer has "installed" it (nothing is downloaded). An install of a broken one fails, once.
    Returns the installs asked for."""
    asked: list[Any] = []
    missing = {
        "feature": "Trino / Presto connections",
        "packages": [MADE_UP],
        "python": "app",
        "command": f"uv pip install {MADE_UP}",
    }

    def install(route: Any) -> None:
        asked.append(json.loads(route.request.post_data or "{}"))
        if installed.get("fail_once"):
            installed["fail_once"] = False
            route.fulfill(
                status=422,
                content_type="application/json",
                body='{"ok": false, "output": "error: a made-up failure"}',
            )
            return
        installed["done"] = True
        route.fulfill(status=200, content_type="application/json", body='{"ok": true, "output": ""}')

    def types(route: Any) -> None:
        answer = route.fetch()
        found = answer.json()
        for form in found["types"]:
            if form["id"] == "trino":
                form["missing"] = None if installed.get("done") else missing
        route.fulfill(response=answer, json=found)

    def inspect(route: Any) -> None:
        answer = route.fetch()
        found = answer.json()
        if (json.loads(route.request.post_data or "{}").get("template")) == "trino":
            found["missing"] = None if installed.get("done") else missing
        route.fulfill(response=answer, json=found)

    page.route("**/blades/install", install)
    page.route("**/connections/types", types)
    page.route("**/blades/inspect", inspect)
    return asked


def test_a_missing_package_is_asked_for_in_the_users_face_and_installed(
    browser: Browser, orders_url: str
) -> None:
    """The owner, 2026-11-16: "Install <package>?" at once, Install now and Not now. Install now
    shows its progress, says a failure plainly (Try again), and once it is in, reads the form again."""
    page = open_grid(browser, orders_url)
    installed: dict[str, Any] = {"fail_once": True}
    asked = stand_in_missing(page, installed)
    dialog = page.locator(".area-page[data-page='connections']")
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").click()
    page.locator(".connection-type", has_text="Trino").click()
    prompt = page.locator("dialog.missing-packages")
    expect(prompt.locator("h2")).to_have_text(f"Install {MADE_UP}?")
    expect(prompt.locator(".missing-sentence")).to_have_text(
        f"Trino / Presto connections will not work without {MADE_UP}."
    )
    expect(prompt.get_by_role("button", name="Not now")).to_be_visible()
    prompt.get_by_role("button", name="Install now").click()  # one action
    # The first install fails: said plainly, with what it printed, and it can be tried again.
    expect(prompt.locator(".missing-state")).to_have_text("The install failed.")
    expect(prompt.locator(".missing-error")).to_contain_text("a made-up failure")
    prompt.get_by_role("button", name="Try again").click()
    # In: the prompt goes, the form reads its code again, and there is nothing left to install.
    expect(prompt).to_have_count(0, timeout=15000)
    expect(page.locator(".toast", has_text=f"Installed {MADE_UP}.")).to_be_visible()
    expect(dialog.locator(".install-note")).to_have_count(0)
    assert [a["packages"] for a in asked] == [[MADE_UP], [MADE_UP]]


def test_not_now_leaves_a_reminder_and_does_not_ask_again(browser: Browser, orders_url: str) -> None:
    page = open_grid(browser, orders_url)
    installed: dict[str, Any] = {}
    asked = stand_in_missing(page, installed)
    dialog = page.locator(".area-page[data-page='connections']")
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").click()
    page.locator(".connection-type", has_text="Trino").click()
    prompt = page.locator("dialog.missing-packages")
    expect(prompt).to_be_visible()
    prompt.get_by_role("button", name="Not now").click()
    expect(prompt).to_have_count(0)
    # The small reminder where the feature is used, the command beside it (the user's own Python too).
    note = dialog.locator(".install-note")
    expect(note.get_by_role("button", name=f"Install {MADE_UP}")).to_be_visible()
    expect(note.locator("code")).to_have_text(f"uv pip install {MADE_UP}")
    # The same form again: no prompt this session.
    dialog.get_by_role("button", name="Back").click()
    page.locator(".connection-type", has_text="Trino").click()
    expect(dialog.locator(".install-note")).to_be_visible()
    expect(prompt).to_have_count(0)
    assert not asked
    # The reminder asks again, on the user's click; installed, the note goes.
    dialog.locator(".install-note").get_by_role("button", name=f"Install {MADE_UP}").click()
    prompt.get_by_role("button", name="Install now").click()
    expect(prompt).to_have_count(0, timeout=15000)
    expect(dialog.locator(".install-note")).to_have_count(0)
    assert [a["packages"] for a in asked] == [[MADE_UP]]


def test_every_database_form_reads_in_one_order_and_labels_its_password_box(
    browser: Browser, orders_url: str
) -> None:
    """Decision 14: server, port, catalog or database; then the user and the password; then the
    certificate file and Trust server certificate together."""
    page = open_grid(browser, orders_url)
    dialog = page.locator(".area-page[data-page='connections']")
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").click()

    def labels() -> list[str]:
        """The form's visible field labels, top to bottom then left to right."""
        found = dialog.locator(".area-page-body .field > span:not(.field-row)").evaluate_all(
            """spans => spans.filter(s => s.offsetParent).map(s => ({ text: s.firstChild.textContent.trim(),
                 box: s.getBoundingClientRect() }))
                 .sort((a, b) => Math.round(a.box.top) - Math.round(b.box.top) || a.box.left - b.box.left)
                 .map(s => s.text)"""
        )
        return [str(text) for text in found]

    def drawn() -> None:
        """The form settles in a moment: the password group and the certificate fields are drawn again
        once the connection's code has been checked in the background. Wait until it reads the same
        twice in a row."""
        expect(dialog.get_by_role("textbox", name="Server")).to_be_visible()
        expect(dialog.get_by_role("combobox", name="Password comes from")).to_be_visible()
        last: list[str] = []
        for _ in range(50):
            now = labels()
            if now == last and "Password comes from" in now:
                return
            last = now
            page.wait_for_timeout(100)

    page.locator(".connection-type", has_text="Trino").click()
    not_now(page)
    drawn()
    # A new password comes from a variable at first (the keyring runs only here: 2026-11-17); typed for
    # this computer, its box is labelled.
    dialog.get_by_role("combobox", name="Password comes from").select_option("keyring")
    drawn()
    assert labels() == [
        "Name",
        "Description",
        "Server",
        "Port",
        "Catalog",
        "Scheme",
        "Sign in",  # a password, or a client certificate from a keystore (2026-11-16)
        "User",
        "Password comes from",
        "Password",
        "Certificate file",
        "Trust server certificate",
        "Rows to open",
    ]
    # The password box has its own label, and the box is the one it names.
    box = dialog.locator(".password-box")
    expect(box.locator("> span").first).to_have_text("Password")
    expect(box.get_by_label("Password", exact=True)).to_have_attribute("type", "password")
    dialog.locator(".area-page-foot").get_by_role("button", name="Back to Add connection").click()

    page.locator(".connection-type", has_text="PostgreSQL").click()
    not_now(page)
    drawn()
    found = labels()
    assert found[2:7] == ["Server", "Port", "Database", "User", "Password comes from"], found
    dialog.locator(".area-page-foot").get_by_role("button", name="Back to Add connection").click()

    # SQL Server: the user arrives with another way to sign in, and lands in the same place; its options
    # (encryption, the certificate) are folded under Options, after the password.
    page.locator(".connection-type", has_text="SQL Server").first.click()
    not_now(page)
    dialog.get_by_role("combobox", name="Sign in").select_option(label="User name and password (SQL login)")
    expect(dialog.get_by_role("textbox", name="User")).to_be_visible()
    dialog.get_by_role("combobox", name="Password comes from").select_option("keyring")
    dialog.locator("details.connection-options > summary").click()
    found = labels()
    assert found[2:4] == ["Server", "Database"]
    assert found.index("Sign in") < found.index("User") < found.index("Password comes from")
    assert found.index("Password") < found.index("Encryption") and "Trust server certificate" in found


MADE_UP_VAULT = """values = {"warehouse-password": "made-up-not-real", "api-key": "made-up", "3d-token": "x"}


def names():
    return list(values)


def get(name):
    return values[name]
"""


def test_a_key_vault_is_a_connection_made_from_a_password_and_mapped_to_variables(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    page = open_grid(browser, orders_url)
    dialog = page.locator(".area-page[data-page='connections']")
    try:
        page.locator(".nav-rail [data-area='connections']").click()
        page.get_by_role("button", name="Add connection").click()
        page.locator(".connection-type", has_text="PostgreSQL").click()
        dialog.get_by_role("combobox", name="Where Password comes from").select_option("vault")
        # No vault yet: make one here; the PostgreSQL form waits.
        dialog.get_by_role("button", name="New vault").click()
        expect(dialog.locator("h3")).to_have_text(["Key vaults"])  # only vaults from here
        page.locator(".connection-type", has_text="Azure Key Vault").click()
        not_now(page)
        dialog.locator("summary", has_text="Python code").click()
        code = dialog.get_by_role("textbox", name="The Python this connection runs")
        code.fill(MADE_UP_VAULT)
        code.dispatch_event("change")
        # The plain code needs no package: the Azure starter's "Not installed" note goes with it.
        expect(dialog).not_to_contain_text("Not installed")
        # The secrets are listed on their own, once the vault can be read (no button to press).
        secrets = dialog.locator(".vault-map tbody tr:not(.vault-new)")
        expect(secrets).to_have_count(3)
        # Left empty, a secret keeps the vault's own name (shown faintly); typed, it is mapped.
        expect(secrets.first.get_by_role("textbox")).to_have_value("")
        expect(secrets.first.get_by_role("textbox")).to_have_attribute("placeholder", "_3d_token")
        expect(dialog.locator(".vault-map")).not_to_contain_text("made-up")  # names only, never a value
        # Every secret is the default: nothing to tick; a box renames one.
        expect(dialog.get_by_role("checkbox", name="Every secret in the vault")).to_be_checked()
        dialog.get_by_role("textbox", name="api-key: the variable's name").fill("CRM_KEY")
        dialog.locator(".area-page-foot").get_by_role("button", name="Save").click()
        # Back on the PostgreSQL form: its password is a secret in the new vault, under its own name.
        expect(dialog.locator("h3")).to_have_text("New PostgreSQL connection")
        expect(dialog.get_by_role("combobox", name="Vault", exact=True)).to_have_value("Azure Key Vault")
        # Entry in the vault lists the vault's secrets by name, read in the background (decision 13):
        # nothing to type, and never a value.
        entry = dialog.get_by_role("combobox", name="Entry in the vault")
        expect(entry.locator("option")).to_have_text(
            [
                "Choose a secret",
                "api-key (as CRM_KEY)",
                "3d-token",
                "warehouse-password",
                "A secret by name…",
            ],
            timeout=30000,
        )
        expect(dialog).not_to_contain_text("made-up")
        expect(dialog.get_by_role("button", name="Use it")).to_be_hidden()
        # One action: picking the secret applies it. No box to fill, no Use it to press.
        entry.select_option("warehouse-password")
        expect(code_box(dialog)).to_have_value(re.compile(r'secret\("warehouse_password"\)'))
        # Drawn again as chosen: the vault, and the secret picked there.
        expect(dialog.get_by_role("combobox", name="Where Password comes from")).to_have_value("vault")
        expect(dialog.get_by_role("combobox", name="Entry in the vault")).to_have_value("warehouse-password")
        # A secret the vault does not list can still be named by hand.
        dialog.get_by_role("combobox", name="Entry in the vault").select_option(label="A secret by name…")
        typed = dialog.get_by_role("textbox", name="The secret's name in the vault")
        expect(typed).to_be_focused()
        typed.fill("reporting-password")
        dialog.get_by_role("button", name="Use it").click()
        expect(code_box(dialog)).to_have_value(re.compile(r'secret\("reporting_password"\)'))
        # The vault is not on the Connections page (it has no tables): the Variables page lists it.
        dialog.locator(".area-page-foot").get_by_role("button", name="Back to Add connection").click()
        dialog.locator(".area-page-foot").get_by_role("button", name="Back to Connections").click()
        expect(dialog.get_by_role("heading", name="Key vaults")).to_have_count(0)
        page.locator(".nav-rail [data-area='variables']").click()
        # Its card's detail: what it sets (the Connections page's detail, 2026-11-16).
        page.locator(".variables-vault-card", has_text="Azure Key Vault").click()
        config = dialog.locator(".connection-config")
        expect(config).to_contain_text("Every secret")
        expect(config).to_contain_text("CRM_KEY")
        expect(config).to_contain_text("api-key")
        # Opened to edit, it is read at once: the mapped one shows its name, the rest are left as is.
        dialog.locator(".connection-detail-tools").get_by_role("button", name="Edit").click()
        expect(dialog.locator(".vault-map tbody tr:not(.vault-new)")).to_have_count(3)
        expect(dialog.get_by_role("textbox", name="api-key: the variable's name")).to_have_value("CRM_KEY")
        expect(dialog.get_by_role("textbox", name="warehouse-password: the variable's name")).to_have_value(
            ""
        )
        dialog.locator(".area-page-foot").get_by_role("button", name="Back to Azure Key Vault").click()
        listed = call(server, "GET", "/connections")["connections"]
        assert [(c["name"], c["connection"], c["every"]) for c in listed] == [
            ("Azure Key Vault", "vault", True)
        ]
    finally:
        try:
            call(server, "DELETE", f"/blades/{quote('Azure Key Vault')}")
        except Exception:  # noqa: S110 (not saved: the test failed earlier)
            pass


def code_box(dialog: Any) -> Any:
    return dialog.locator(".connection-code")  # in the folded Python code box


def menu(workbench: Page, button: str, item: str) -> None:
    """Open a menu by its button's name and choose an entry (the redesign of 2026-11-15 put the old
    toolbar's actions in menus: the top bar's "Workbench menu", a group's "Document menu" and "Add cell")."""
    workbench.get_by_role("button", name=button, exact=True).first.click()
    workbench.get_by_role("menuitem", name=item, exact=True).click()


def start(workbench: Page, what: str = "New notebook") -> None:
    """New notebook or New script, from the top bar's menu."""
    menu(workbench, "Workbench menu", what)


def add_cell(workbench: Page, kind: str) -> None:
    """A cell of a kind, from the focused group's "+ Cell"."""
    menu(workbench, "Add cell", kind)


def status(workbench: Page, toggle: str) -> None:
    """The status bar's Console or Variables."""
    workbench.locator(".wb-status").get_by_role("button", name=toggle, exact=True).click()


def open_workbench(page: Page) -> Page:
    with page.context.expect_page() as opened:
        page.evaluate("window.open('/workbench', 'swissarmybench-workbench')")
    workbench = opened.value
    expect(workbench.locator(".wb-welcome")).to_be_visible(timeout=20000)
    return workbench


def test_the_first_save_on_a_fresh_home_folder_has_somewhere_to_go(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    """Decision 15: the app's own folder is made the first time it is needed. On a fresh home folder
    the first Save said "…/SwissArmyBench is not a folder this computer can open" and could not save."""
    import shutil

    own = Path(call(server, "GET", "/workbench/home")["folder"])
    assert "pytest" in str(own)  # the tests' own folder, never this machine's home
    shutil.rmtree(own, ignore_errors=True)
    workbench = open_workbench(open_grid(browser, orders_url))
    start(workbench, "New script")
    workbench.locator(".monaco-editor").first.click()
    workbench.keyboard.type("print('made-up')")
    # Three actions: Save, the name, Save here. The chooser opens in the app's folder, now there.
    workbench.get_by_role("button", name="Save", exact=True).click()
    chooser = workbench.locator(".file-chooser")
    expect(chooser.locator("input[aria-label=Folder]")).to_have_value(str(own.resolve()), timeout=15000)
    expect(chooser.locator("p[role=status]")).to_have_text("0 folders, 0 files")
    chooser.get_by_label("File name").fill("first.py")
    chooser.get_by_role("button", name="Save here").click()
    expect(workbench.locator(".wb-tabs .tab-label")).to_have_text(["first.py"])
    assert (own / "first.py").read_text(encoding="utf-8").startswith("print('made-up')")
    (own / "first.py").unlink()


def test_the_workbench_runs_a_notebook_with_a_sql_cell_saves_it_and_reopens_it(
    browser: Browser, orders_url: str, server: dict[str, Any], orders_csv: Path, tmp_path: Path
) -> None:
    call(
        server,
        "POST",
        "/connections",
        {
            "name": "Orders",
            "kind": "other",
            "template": "csv",
            "code": f'from pathlib import Path\npath = Path(r"{orders_csv}")',
        },
    )
    workbench = open_workbench(open_grid(browser, orders_url))
    # The left panel lists the connection apart from the blades.
    expect(workbench.locator(".blade-item", has_text="Orders").locator(".blade-kind")).to_have_text("File")
    start(workbench)
    editor = workbench.locator(".wb-cell .monaco-editor").first
    expect(editor).to_be_visible(timeout=20000)
    editor.click()
    workbench.keyboard.type("import pandas as pd\nprint('hello')\npd.DataFrame({'city': ['Springfield']})")
    workbench.keyboard.press("Shift+Enter")  # runs, and opens the next cell
    first = workbench.locator(".wb-cell").first
    expect(first.locator(".wb-stream")).to_have_text("hello\n", timeout=60000)
    expect(first.locator("iframe.wb-html")).to_be_visible()
    expect(first.locator(".wb-count")).to_have_text("[1]")
    # Every connection is there by its name: no sab.connection(...) line (opened when first used).
    add_cell(workbench, "Python")
    named = workbench.locator(".wb-cell").nth(1)
    expect(named.locator(".monaco-editor")).to_be_visible(timeout=20000)
    named.locator(".monaco-editor").click()
    workbench.keyboard.type("print(pd.read_csv(orders)['amount'].sum())")
    workbench.keyboard.press("Control+Enter")
    expect(named.locator(".wb-stream")).to_have_text("20.0\n", timeout=60000)
    named.get_by_role("button", name="Delete cell").click()
    second = workbench.locator(".wb-cell").nth(1)
    second.get_by_label("Cell kind").select_option("sql")
    # The box shows the connection the cell will run on, straight away (it once showed a placeholder).
    expect(second.get_by_label("Connection")).to_have_value("Orders")
    second.get_by_label("Connection").select_option("Orders")
    second.locator(".monaco-editor").click()
    workbench.keyboard.type("SELECT sum(amount) AS total FROM orders")
    workbench.keyboard.press("Control+Enter")
    frame = second.frame_locator("iframe.wb-html")
    expect(frame.locator("td").last).to_have_text("20.0", timeout=60000)
    expect(workbench.locator(".wb-status .wb-state")).to_have_count(0)  # a ready kernel says nothing
    # Save as… through the file chooser; the file is a notebook Jupyter reads.
    workbench.get_by_role("button", name="Save", exact=True).click()
    folder = workbench.locator(".file-chooser input[aria-label=Folder]")
    folder.fill(str(tmp_path))
    folder.press("Enter")
    workbench.get_by_label("File name").fill("orders.ipynb")
    workbench.get_by_role("button", name="Save here").click()
    expect(workbench.locator(".wb-tabs .tab-label")).to_have_text(["orders.ipynb"])
    saved = json.loads((tmp_path / "orders.ipynb").read_text(encoding="utf-8"))
    assert saved["nbformat"] == 4 and saved["cells"][1]["source"][0] == "%%sql Orders\n"
    # Closed and opened again: the cells and their outputs come back.
    workbench.locator(".wb-tabs").get_by_role("button", name="Close orders.ipynb").click()
    menu(workbench, "Workbench menu", "Open…")
    folder = workbench.locator(".file-chooser input[aria-label=Folder]")
    folder.fill(str(tmp_path))
    folder.press("Enter")
    workbench.locator(".file-chooser .file-row.file", has_text="orders.ipynb").dblclick()
    expect(workbench.locator(".wb-cell")).to_have_count(2)
    expect(workbench.locator(".wb-cell").nth(1).get_by_label("Connection")).to_have_value("Orders")
    expect(workbench.locator(".wb-cell").first.locator(".wb-stream")).to_have_text("hello\n")


def new_script(workbench: Page, code: str) -> None:
    """A new script with `code` in its editor (typed as one insert, so the editor adds no indent)."""
    start(workbench, "New script")
    editor = workbench.locator(".wb-script-editor .monaco-editor")
    expect(editor).to_be_visible(timeout=20000)
    editor.click()
    workbench.keyboard.insert_text(code)


def console_type(workbench: Page, text: str) -> None:
    workbench.locator(".wb-console-editor .monaco-editor").click()
    workbench.keyboard.insert_text(text)


def test_a_script_runs_in_its_console(browser: Browser, orders_url: str) -> None:
    workbench = open_workbench(open_grid(browser, orders_url))
    new_script(workbench, "total = sum(range(10))\nprint('total is', total)")
    workbench.get_by_role("button", name="Run file").click()
    log = workbench.locator(".wb-console-log")
    expect(log).to_contain_text("total is 45", timeout=60000)
    console_type(workbench, "total * 2")
    workbench.keyboard.press("Enter")
    expect(log).to_contain_text("90")
    workbench.keyboard.press("ArrowUp")
    expect(workbench.locator(".wb-console-editor .view-lines")).to_contain_text("total * 2")  # back again
    # Several lines: Enter after a block's first line adds a line; an empty line ends the block.
    workbench.keyboard.press("Control+a")
    workbench.keyboard.press("Delete")
    workbench.keyboard.insert_text("for i in range(2):")
    workbench.keyboard.press("Enter")
    workbench.keyboard.insert_text("print('row', i)")
    workbench.keyboard.press("Enter")
    expect(log).not_to_contain_text("row 1")
    workbench.keyboard.press("Enter")
    expect(log).to_contain_text("row 1")
    # F5 anywhere runs the file, never reloading the window (which would stop the kernel).
    workbench.locator(".wb-console-head").click()
    workbench.keyboard.press("F5")
    expect(log.locator(".wb-console-code", has_text="the script")).to_have_count(2)
    console_type(workbench, "total")
    workbench.keyboard.press("Enter")
    expect(log.locator(".wb-console-entry").last).to_contain_text("45")  # the same kernel, still there


def open_file(workbench: Page, path: Path) -> None:
    """Open a file as the window's address does (#open=...): its text exactly as written."""
    workbench.goto(workbench.url.split("#")[0] + "#open=" + quote(str(path)))
    workbench.reload()
    expect(workbench.locator(".wb-tabs .tab-item", has_text=path.name)).to_be_visible(timeout=20000)


def test_ctrl_enter_runs_the_whole_statement_then_the_next(
    browser: Browser, orders_url: str, tmp_path: Path
) -> None:
    script = tmp_path / "rates.py"
    script.write_text("for r in [1, 2]:\n    print('rate', r)\n\nprint('after')\n", encoding="utf-8")
    workbench = open_workbench(open_grid(browser, orders_url))
    open_file(workbench, script)
    workbench.locator(".wb-script-editor .monaco-editor").click()
    workbench.keyboard.press("Control+Home")
    workbench.keyboard.press("Control+Enter")
    log = workbench.locator(".wb-console-log")
    expect(log).to_contain_text("rate 2", timeout=60000)  # the whole for block, not its first line
    expect(log).not_to_contain_text("after")
    workbench.keyboard.press("Control+Enter")  # the cursor moved on to the next statement
    expect(log).to_contain_text("after")


def test_outputs_keep_up_with_many_prints_colours_and_progress_bars(
    browser: Browser, orders_url: str, tmp_path: Path
) -> None:
    script = tmp_path / "noisy.py"
    script.write_text(
        "import sys\n"
        "for i in range(6000):\n    print('line', i, flush=True)\n"
        "print('\\x1b[31mred\\x1b[0m plain')\n"
        "sys.stdout.write('10%\\r50%\\r100%\\n')\n",
        encoding="utf-8",
    )
    workbench = open_workbench(open_grid(browser, orders_url))
    open_file(workbench, script)
    workbench.get_by_role("button", name="Run file").click()
    log = workbench.locator(".wb-console-log")
    # The stress test froze the page for over 100 seconds at 5,000 prints; drawn as they come it keeps up.
    expect(log).to_contain_text("100%", timeout=30000)
    expect(log).to_contain_text("line 5999")
    expect(log.locator(".wb-cut")).to_contain_text("earlier lines hidden")
    expect(log.locator(".ansi-fg-1")).to_have_text("red")
    expect(log).not_to_contain_text("50%")  # each \\r wrote over its line


def test_input_is_answered_in_place_and_a_dead_kernel_says_so(browser: Browser, orders_url: str) -> None:
    workbench = open_workbench(open_grid(browser, orders_url))
    new_script(workbench, "name = input('Who? ')\nprint('hello', name)\n")
    workbench.get_by_role("button", name="Run file").click()
    box = workbench.locator(".wb-input-box")
    expect(box).to_be_visible(timeout=60000)
    box.fill("Ana")
    box.press("Enter")
    log = workbench.locator(".wb-console-log")
    expect(log).to_contain_text("hello Ana")
    console_type(workbench, "import os; os._exit(1)")
    workbench.keyboard.press("Enter")
    expect(log.locator(".wb-notice.error")).to_contain_text("The kernel stopped", timeout=30000)


def test_a_deleted_cell_comes_back_and_open_documents_survive_a_reload(
    browser: Browser, orders_url: str
) -> None:
    workbench = open_workbench(open_grid(browser, orders_url))
    workbench.on("dialog", lambda dialog: dialog.accept())  # the unsaved-changes warning on reload
    start(workbench)
    first = workbench.locator(".wb-cell .monaco-editor").first
    expect(first).to_be_visible(timeout=20000)
    first.click()
    workbench.keyboard.insert_text("kept = 'first cell'")
    add_cell(workbench, "Python")
    expect(workbench.locator(".wb-cell")).to_have_count(2)
    workbench.locator(".wb-cell").first.get_by_role("button", name="Delete cell").click()
    expect(workbench.locator(".wb-cell")).to_have_count(1)
    workbench.locator(".toast").get_by_role("button", name="Undo").click()
    expect(workbench.locator(".wb-cell")).to_have_count(2)
    expect(workbench.locator(".wb-cell").first).to_contain_text("first cell")
    new_script(workbench, "draft = 'not saved yet'")
    workbench.wait_for_timeout(1200)  # remembered a moment after the last change
    workbench.reload()
    expect(workbench.locator(".wb-tabs .tab-item")).to_have_count(2, timeout=20000)
    expect(workbench.locator(".wb-script-editor .view-lines")).to_contain_text("not saved yet", timeout=20000)
    workbench.locator(".wb-tabs .tab-item").first.click()
    expect(workbench.locator(".wb-cell").first).to_contain_text("first cell")


def test_completion_comes_from_the_catalog_and_the_kernel(
    browser: Browser, orders_url: str, server: dict[str, Any], orders_csv: Path
) -> None:
    call(
        server,
        "POST",
        "/connections",
        {
            "name": "Orders",
            "kind": "other",
            "template": "csv",
            "code": f'from pathlib import Path\npath = Path(r"{orders_csv}")',
        },
    )
    catalog = {
        "columns": ["TABLE_SCHEMA", "TABLE_NAME", "COLUMN_NAME", "DATA_TYPE"],
        "data": [
            ["sales", "orders", "order_id", "int"],
            ["sales", "orders", "region", "varchar"],
            ["sales", "orders", "amount", "decimal"],
        ],
    }
    request_catalog = call(server, "PUT", "/catalogs/Orders?dialect=duckdb", catalog)
    assert request_catalog["catalog"]["columns"] == 3
    try:
        workbench = open_workbench(open_grid(browser, orders_url))
        start(workbench)
        cell = workbench.locator(".wb-cell").first
        expect(cell.locator(".monaco-editor")).to_be_visible(timeout=20000)
        # A SQL cell before any kernel runs: the connection's catalog answers.
        cell.get_by_label("Cell kind").select_option("sql")
        cell.get_by_label("Connection").select_option("Orders")
        cell.locator(".monaco-editor").click()
        workbench.keyboard.type("SELECT * FROM ord")
        workbench.keyboard.press("Control+Space")  # suggestions now (typing fast can outrun the widget)
        suggest = workbench.locator(".suggest-widget .monaco-list-row")
        expect(suggest.filter(has_text="orders").first).to_be_visible(timeout=10000)
        workbench.keyboard.press("Escape")
        workbench.keyboard.type("ers WHERE orders.reg")
        workbench.keyboard.press("Control+Space")
        expect(suggest.filter(has_text="region").first).to_be_visible(timeout=10000)
        workbench.keyboard.press("Escape")
        # A Python cell once the kernel runs: the kernel's own names, a DataFrame's columns.
        add_cell(workbench, "Python")
        python = workbench.locator(".wb-cell").nth(1)
        expect(python.locator(".monaco-editor")).to_be_visible(timeout=20000)
        python.locator(".monaco-editor").click()
        workbench.keyboard.type("import pandas as pd\nrainfall = pd.DataFrame({'rain_mm': [3.5]})")
        workbench.keyboard.press("Control+Enter")
        expect(python.locator(".wb-count")).to_have_text("[1]", timeout=60000)
        workbench.keyboard.press("End")
        workbench.keyboard.press("Enter")
        workbench.keyboard.type("rainfall.rai")
        workbench.keyboard.press("Control+Space")
        expect(suggest.filter(has_text="rain_mm").first).to_be_visible(timeout=15000)
        workbench.keyboard.press("Escape")
        workbench.keyboard.press("Enter")
        workbench.keyboard.type('conn = sab.connection("Or')
        expect(suggest.filter(has_text="Orders").first).to_be_visible(timeout=10000)
    finally:
        call(server, "DELETE", "/catalogs/Orders")


def test_the_variables_pane_shows_what_the_kernel_holds(
    browser: Browser, orders_url: str, server: dict[str, Any], orders_csv: Path
) -> None:
    call(
        server,
        "POST",
        "/connections",
        {
            "name": "Orders",
            "kind": "other",
            "template": "csv",
            "code": f'from pathlib import Path\npath = Path(r"{orders_csv}")',
        },
    )
    workbench = open_workbench(open_grid(browser, orders_url))
    start(workbench)
    cell = workbench.locator(".wb-cell").first
    expect(cell.locator(".monaco-editor")).to_be_visible(timeout=20000)
    cell.locator(".monaco-editor").click()
    frame = "{'city': ['Springfield', 'Riverton'], 'rain_mm': [3.5, 0.0]}"
    workbench.keyboard.type(f"import pandas as pd\nrainfall = pd.DataFrame({frame})")
    workbench.keyboard.press("Control+Enter")
    expect(cell.locator(".wb-count")).to_have_text("[1]", timeout=60000)
    status(workbench, "Variables")  # closed until the status bar opens it (the redesign of 2026-11-15)
    overlay = workbench.get_by_role("region", name="Variables")
    row = overlay.locator("tr", has_text="rainfall")
    expect(row).to_contain_text("2 × 2", timeout=15000)  # rows by columns (the whole words on hover)
    expect(row).to_contain_text("columns: city, rain_mm")
    # A connection no cell has opened is not listed here (the side bar lists them), and there is no
    # Environment block when no variable of a vault or password is in play.
    expect(overlay.get_by_role("heading", name="Connections and blades")).to_have_count(0)
    expect(overlay.get_by_role("heading", name="Environment")).to_have_count(0)
    expect(overlay.locator("tr", has_text="Orders")).to_have_count(0)
    # A cell that uses the connection opens it; the overlay reads again when the run ends.
    cell.locator(".monaco-editor").click()
    workbench.keyboard.press("Control+End")
    workbench.keyboard.type("\nlen(pd.read_csv(orders))")
    workbench.keyboard.press("Control+Enter")
    expect(overlay.locator("tr", has_text="orders")).to_contain_text("orders.csv", timeout=30000)
    # A table opens as a grid in the grid page.
    row.get_by_role("button", name="Open rainfall as a grid").click()
    expect(workbench.locator(".toast")).to_contain_text("rainfall is open as a grid", timeout=30000)
    assert any(d["name"] == "rainfall" for d in call(server, "GET", "/datasets")["datasets"])


def test_four_panes_a_palette_and_jupyters_keys(browser: Browser, orders_url: str) -> None:
    workbench = open_workbench(open_grid(browser, orders_url))
    start(workbench)
    cell = workbench.locator(".wb-cell").first
    expect(cell.locator(".monaco-editor")).to_be_visible(timeout=20000)
    # RStudio's places: source, its console, Variables (pictures go to Visualizations, not a pane here);
    # the console and Variables closed until the status bar opens them.
    expect(workbench.locator(".wb-console-pane .wb-console")).to_be_hidden()
    expect(workbench.locator(".wb-env .wb-vars")).to_be_hidden()
    status(workbench, "Console")
    status(workbench, "Variables")
    expect(workbench.locator(".wb-status").get_by_role("button", name="Console")).to_have_attribute(
        "aria-pressed", "true"
    )
    for pane in (".wb-source .wb-cells", ".wb-console-pane .wb-console", ".wb-env .wb-vars"):
        expect(workbench.locator(pane)).to_be_visible()
    # The notebook's own console, on its kernel.
    workbench.locator(".wb-console-editor .monaco-editor").click()
    workbench.keyboard.insert_text("21 * 2")
    workbench.keyboard.press("Enter")
    expect(workbench.locator(".wb-console-log")).to_contain_text("42", timeout=60000)
    # The palette runs any command by its name.
    workbench.keyboard.press("Control+Shift+P")
    workbench.get_by_role("combobox", name="Command").fill("insert below")
    workbench.keyboard.press("Enter")
    expect(workbench.locator(".wb-cell")).to_have_count(2)
    # Command mode: Escape leaves the editor; B, D D, Z and M act on the cell.
    workbench.keyboard.press("Escape")
    workbench.keyboard.press("b")
    expect(workbench.locator(".wb-cell")).to_have_count(3)
    workbench.keyboard.press("Escape")
    workbench.keyboard.press("d")
    workbench.keyboard.press("d")
    expect(workbench.locator(".wb-cell")).to_have_count(2)
    workbench.keyboard.press("z")
    expect(workbench.locator(".wb-cell")).to_have_count(3)
    workbench.keyboard.press("m")
    expect(workbench.locator(".wb-cell.selected").get_by_label("Cell kind")).to_have_value("markdown")
    # A splitter moves by keyboard, and Focus shows the source alone.
    splitter = workbench.locator(".wb-split.vertical")
    before = int(splitter.get_attribute("aria-valuenow") or "0")
    splitter.focus()
    workbench.keyboard.press("ArrowLeft")
    expect(splitter).to_have_attribute("aria-valuenow", str(before - 2))
    workbench.keyboard.press("Control+Shift+1")
    expect(workbench.locator(".wb-col-right")).to_be_hidden()
    workbench.keyboard.press("Control+Shift+P")
    workbench.get_by_role("combobox", name="Command").fill("layout standard")
    workbench.keyboard.press("Enter")
    expect(workbench.locator(".wb-col-right")).to_be_visible()


def test_pictures_go_to_the_sandbox_f1_helps_and_code_goes_to_the_agent(
    browser: Browser, orders_url: str, server: dict[str, Any], tmp_path: Path
) -> None:
    script = tmp_path / "shapes.py"
    script.write_text(
        "from IPython.display import SVG, display\n"
        'display(SVG(\'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
        '<rect width="20" height="20" fill="teal"/></svg>\'))\n'
        "print(len('made up'))\n",
        encoding="utf-8",
    )
    workbench = open_workbench(open_grid(browser, orders_url))
    open_file(workbench, script)
    workbench.get_by_role("button", name="Run file").click()
    log = workbench.locator(".wb-console-log")
    expect(log).to_contain_text("7", timeout=60000)
    # A picture goes to Visualizations with one click.
    figure = log.locator(".wb-figure").first
    figure.hover()
    figure.get_by_role("button", name="Send to Visualizations").click()
    expect(workbench.locator(".toast")).to_contain_text("Sent to Visualizations")
    assert any(
        c["kind"] == "image" and c["title"] == "From shapes.py"
        for c in call(server, "GET", "/cards")["cards"]
    )
    # F1 on a name: its help in a card over the source.
    editor = workbench.locator(".wb-script-editor .monaco-editor")
    editor.click()
    workbench.keyboard.press("Control+End")
    workbench.keyboard.press("ArrowUp")
    workbench.keyboard.press("End")
    for _ in range(14):
        workbench.keyboard.press("ArrowLeft")  # into "len"
    workbench.keyboard.press("F1")
    expect(workbench.locator(".wb-help-card")).to_contain_text("Return the number of items", timeout=30000)
    workbench.keyboard.press("Escape")
    # Select code, right-click, Send to the agent: it waits in the agent's inbox for the next prompt.
    editor.click()
    workbench.keyboard.press("Control+End")
    workbench.keyboard.press("ArrowUp")
    workbench.keyboard.press("Home")
    workbench.keyboard.press("Shift+End")
    expect(workbench.locator(".wb-help-card")).to_be_hidden()  # Escape put the help away
    editor.locator(".view-line span", has_text="print").first.click(button="right")  # on the selection
    item = workbench.locator(".monaco-menu .action-label", has_text="Send to the agent").first
    expect(item).to_be_visible()
    workbench.wait_for_timeout(
        400
    )  # Monaco's menu ignores a click right as it opens (the right button's release)
    item.click()
    expect(workbench.locator(".toast", has_text="Sent to the agent")).to_be_visible()
    waiting = call(server, "GET", "/agent/inbox?take=1", agent=True)["items"]
    assert waiting[-1]["kind"] == "code" and "print(len('made up'))" in waiting[-1]["text"]
    assert waiting[-1]["title"] == "Code from shapes.py, line 3"


def test_the_agent_works_the_window_as_the_user_does(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    workbench = open_workbench(open_grid(browser, orders_url))

    def window(command: str, **args: Any) -> Any:
        return call(server, "POST", "/workbench/window", {"command": command, "args": args}, agent=True)[
            "result"
        ]

    window("file.newNotebook")
    expect(workbench.locator(".wb-cell")).to_have_count(1, timeout=20000)
    window("cell.insertBelow", kind="code", source="answer = 6 * 7\nanswer")
    expect(workbench.locator(".wb-cell")).to_have_count(2)
    assert window("run.cell", index=1) is True
    expect(workbench.locator(".wb-cell").nth(1).locator(".wb-text")).to_have_text("42")
    opened = window("documents")
    assert (
        opened["documents"][0]["kind"] == "notebook" and opened["documents"][0]["kernel"]["state"] == "idle"
    )
    assert window("doc.read")["cells"][1]["source"] == "answer = 6 * 7\nanswer"
    ids = {c["id"] for c in window("commands")}
    assert {"run.statement", "cell.delete", "view.focus", "console.run"} <= ids
    window("console.run", code="answer + 1")
    expect(workbench.locator(".wb-console-log")).to_contain_text("43", timeout=30000)


def test_an_error_is_explained_marked_in_the_code_and_fixed(
    browser: Browser, orders_url: str, server: dict[str, Any], tmp_path: Path
) -> None:
    script = tmp_path / "totals.py"
    script.write_text(
        "import pandas as pd\n"
        "orders = pd.DataFrame({'region': ['North', 'South'], 'amount': [10.5, 7.0]})\n"
        "total = orders['amont'].sum()\n",
        encoding="utf-8",
    )
    workbench = open_workbench(open_grid(browser, orders_url))
    open_file(workbench, script)
    workbench.get_by_role("button", name="Run file").click()
    panel = workbench.locator(".wb-console-log .wb-err")
    expect(panel).to_contain_text("The table has no column 'amont'", timeout=60000)
    expect(panel).to_contain_text("In your code: totals.py, line 3")
    expect(panel.locator(".wb-err-lib").first).to_contain_text("in pandas")  # library frames folded
    # The failing line is marked in the script, its message at the line's end.
    expect(workbench.locator(".wb-script-editor .wb-problem-lens")).to_contain_text("KeyError")
    panel.get_by_role("button", name="Use 'amount'").click()
    expect(workbench.locator(".wb-script-editor .view-lines")).to_contain_text("orders['amount'].sum()")
    expect(workbench.locator(".wb-script-editor .wb-problem-lens")).to_have_count(0)  # the edit clears it
    workbench.get_by_role("button", name="Run file").click()
    expect(workbench.locator(".wb-console-log .wb-console-entry").last).not_to_contain_text(
        "KeyError", timeout=30000
    )
    # In a notebook: a missing import, added with one click.
    start(workbench)
    cell = workbench.locator(".wb-cell").first
    expect(cell.locator(".monaco-editor")).to_be_visible(timeout=20000)
    cell.locator(".monaco-editor").click()
    workbench.keyboard.insert_text("np.arange(3).sum()")
    workbench.keyboard.press("Control+Enter")
    expect(cell.locator(".wb-err")).to_contain_text("import numpy as np", timeout=60000)
    # Right-click the error: Send to the agent, with its explanation and place.
    cell.locator(".wb-err .wb-err-explain").click(button="right")
    workbench.get_by_role("menuitem", name="Send this error to the agent").click()
    sent = call(server, "GET", "/agent/inbox?take=1", agent=True)["items"][-1]
    assert sent["kind"] == "error" and sent["text"].startswith("NameError: name 'np' is not defined")
    cell.locator(".wb-err").get_by_role("button", name="Add import numpy as np").click()
    expect(cell.locator(".view-lines")).to_contain_text("import numpy as np")
    workbench.keyboard.press("Control+Enter")
    expect(cell.locator(".wb-text")).to_contain_text("3", timeout=30000)  # np.int64(3) in numpy 2


def test_the_document_menu_exports_one_python_script_and_one_notebook_through_the_file_chooser(
    browser: Browser, orders_url: str, tmp_path: Path
) -> None:
    """Export as one Python script… and Export as one notebook…: the document as it stands (not saved),
    named after it, written where the file chooser says. Made-up code only."""
    workbench = open_workbench(open_grid(browser, orders_url))
    new_script(
        workbench, "import pandas as pd\n\nframe = pd.DataFrame({'region': ['North'], 'amount': [3]})\nframe"
    )
    folder = tmp_path / "jobs"
    folder.mkdir()
    for item, name in (
        ("Export as one Python script…", "untitled_automation.py"),
        ("Export as one notebook…", "untitled_automation.ipynb"),
    ):
        menu(workbench, "Document menu", item)
        chooser = workbench.locator(".file-chooser")
        where = chooser.locator("input[aria-label=Folder]")
        where.fill(str(folder))
        where.press("Enter")
        expect(chooser.locator("[role=status]")).to_contain_text("folder")
        assert (
            chooser.get_by_label("File name")
            .input_value()
            .endswith("_automation" + name.rsplit("_automation", 1)[1])
        )
        chooser.get_by_label("File name").fill(name)
        chooser.get_by_role("button", name="Save here").click()
        expect(workbench.locator(".toast").last).to_contain_text(f"Exported {name}", timeout=20000)
    script = (folder / "untitled_automation.py").read_text(encoding="utf-8")
    compile(script, "script", "exec")
    assert "frame = pd.DataFrame({'region': ['North'], 'amount': [3]})" in script
    assert "REQUIREMENTS: dict[str, str] = {\n    'pandas': 'pandas>=2.0',\n}" in script
    assert "# frame: shown in the notebook only" in script
    notebook = json.loads((folder / "untitled_automation.ipynb").read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4 and all(c.get("outputs", []) == [] for c in notebook["cells"])
