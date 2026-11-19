# ruff: noqa: F811
"""Every error looks and reads the same (design principle 9.5, the owner 2026-11-18: "Errors should be
presented to users in one uniform way as much as possible"), in a real browser: a refused connection Test
shows the one note in its form (what, where, Try again, Details with Copy, Send to the agent) and a good retry
clears it; a missing package's refusal brings Install now; background work that fails (Autosave) is the same
note in a toast with Show; a card that cannot be drawn says so in the card; the portability rule's amber line
is the same component as a warning. Screenshots light and dark into SAB_ERROR_SHOTS when set. Made-up data."""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pyarrow as pa
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_sab_projects import STEP, fresh, home  # noqa: F401
from tests.e2e.test_ui import browser, call, grid_of, open_grid, server  # noqa: F401


def shot(page: Page, name: str, target: Any = None) -> None:
    where = os.environ.get("SAB_ERROR_SHOTS")
    if not where:
        return
    Path(where).mkdir(parents=True, exist_ok=True)
    (target or page).screenshot(path=str(Path(where) / name))


def add_sqlite_form(page: Page, name: str, path: Path) -> Any:
    """The Connections page's Add connection, SQLite, its name and its file typed in."""
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").click()
    dialog = page.locator(".area-page[data-page='connections']")
    dialog.locator(".connection-type", has_text="SQLite").first.click()
    dialog.get_by_role("textbox", name="Name", exact=True).fill(name)
    box = dialog.get_by_role("textbox", name="Path", exact=True)
    box.fill(str(path))
    box.press("Tab")
    return dialog


def test_a_refused_test_is_the_note_in_its_form_and_a_good_retry_clears_it(
    browser: Browser, server: dict[str, Any]
) -> None:
    folder = Path(server["tmp"]) / "errors_shop"
    shutil.rmtree(folder, ignore_errors=True)
    database = folder / "shop.sqlite"  # not there yet: the Test is refused
    for dark in (False, True):
        page = home(browser, server, dark=dark)
        dialog = add_sqlite_form(page, "Made-up shop", database)
        dialog.get_by_role("button", name="Test connection").click()
        result = dialog.locator(".connection-result")
        note = result.locator(".error-note")
        expect(note).to_be_visible(timeout=60000)
        # What happened in one sentence, where, the fix, the source's words folded, Send to the agent.
        expect(note.locator(".error-note-word")).to_have_text("Error")
        expect(note.locator(".error-note-what")).to_contain_text("unable to open database file")
        expect(note.locator(".error-note-where")).to_have_text("Made-up shop")
        expect(note.get_by_role("button", name="Try again")).to_be_visible()
        expect(note.get_by_role("button", name="Send to the agent")).to_be_visible()
        details = note.locator(".error-note-details")
        expect(details.locator("summary")).to_have_text("Details")
        details.locator("summary").click()
        expect(details.locator(".error-note-text")).to_contain_text("OperationalError")
        expect(details.get_by_role("button", name="Copy")).to_be_visible()
        assert "OperationalError" not in (note.locator(".error-note-what").text_content() or "")
        shot(page, f"error-in-a-form-{'dark' if dark else 'light'}.png", dialog)
        if dark:
            # The cause gone, the retry works and the note goes with it.
            folder.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database) as made:
                made.execute("CREATE TABLE orders (order_id INTEGER, units INTEGER)")
            note.get_by_role("button", name="Try again").click()
            expect(result.locator(".status-ok")).to_contain_text("It works", timeout=60000)
            expect(result.locator(".error-note")).to_have_count(0)
        page.context.close()


def test_a_missing_package_brings_install_now(browser: Browser, server: dict[str, Any]) -> None:
    page = home(browser, server)
    dialog = add_sqlite_form(page, "Made-up warehouse", Path(server["tmp"]) / "nowhere.sqlite")
    # Its code needs a driver this Python does not have.
    dialog.locator(".connection-code-box > summary").click()  # Python code
    code = dialog.locator("textarea.connection-code")
    code.fill("import made_up_warehouse_driver\nconn = made_up_warehouse_driver.connect()\n")
    code.dispatch_event("change")
    prompt = page.locator("dialog.missing-packages")
    # Read from the code, the package is asked for in the user's face (missingPackages.ts): Not now.
    expect(prompt).to_be_visible(timeout=60000)
    prompt.get_by_role("button", name="Not now").click()
    expect(prompt).to_have_count(0)
    dialog.get_by_role("button", name="Test connection").click()
    note = dialog.locator(".connection-result .error-note")
    expect(note).to_contain_text("made_up_warehouse_driver", timeout=60000)
    if prompt.count():  # asked once more for the run: Not now again
        prompt.get_by_role("button", name="Not now").click()
    install = note.get_by_role("button", name="Install now")
    expect(install).to_be_visible()
    install.click()  # the fix: the prompt again, asked for
    expect(prompt).to_be_visible()
    prompt.get_by_role("button", name="Not now").click()
    page.context.close()


def test_a_background_failure_is_the_same_note_in_a_toast_with_show(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    grid = call(server, "POST", "/datasets/orders/load", {"path": str(fresh / "orders.csv")})["grid"]
    target = fresh / "sales"
    call(server, "POST", "/project/save", {"path": str(target), "autosave": True})
    page = home(browser, server, "?view=grids")
    try:
        # The project's folder can no longer take its .sab/ (a file in its place): Autosave fails by itself.
        shutil.rmtree(target / ".sab")
        (target / ".sab").write_text("not a folder\n", encoding="utf-8")
        call(server, "POST", f"/grids/{grid}/steps", {"steps": [STEP]})
        toast = page.locator(".toast.toast-note .error-note")
        expect(toast).to_contain_text("Autosave could not save sales.", timeout=60000)
        expect(toast.get_by_role("button", name="Show")).to_be_visible()
        expect(toast.get_by_role("button", name="Save now")).to_be_visible()
        expect(toast.locator(".error-note-where")).to_have_text(str(target))
        shot(page, "error-toast-light.png")
        page.emulate_media(color_scheme="dark")
        shot(page, "error-toast-dark.png")
        toast.get_by_role("button", name="Show").click()
        expect(page.locator(".toast.toast-note")).to_have_count(0)
        expect(page.locator(".app-row").get_by_text("Autosave")).to_be_visible()  # the project's group
    finally:
        (target / ".sab").unlink(missing_ok=True)
        page.context.close()


def test_only_works_on_your_machine_is_the_warning(browser: Browser, server: dict[str, Any]) -> None:
    for dark in (False, True):
        page = home(browser, server, dark=dark)
        page.locator(".nav-rail [data-area='connections']").click()
        page.get_by_role("button", name="Add connection").click()
        dialog = page.locator(".area-page[data-page='connections']")
        dialog.locator(".connection-type", has_text="SQL Server").first.click()
        sign_in = dialog.get_by_role("combobox", name="Sign in")
        expect(sign_in).to_be_visible(timeout=30000)
        prompt = page.locator("dialog.missing-packages")
        page.wait_for_timeout(1000)
        if prompt.count():  # its driver is not in this Python: Not now
            prompt.get_by_role("button", name="Not now").click()
        # A sign-in that works only here (Windows integrated): the amber warning, its words kept.
        options = sign_in.locator("option").all_text_contents()
        local = next(i for i, words in enumerate(options) if "Windows" in words)
        sign_in.select_option(str(local))
        warning = dialog.locator(".sign-in-local .error-note.warning")
        expect(warning).to_contain_text("Only works on your machine")
        expect(warning.locator(".error-note-word")).to_have_text("Warning")
        expect(warning.get_by_role("button", name="Send to the agent")).to_have_count(0)
        shot(page, f"warning-{'dark' if dark else 'light'}.png", dialog)
        page.context.close()


def test_a_card_that_cannot_be_drawn_says_so_in_the_card(browser: Browser, server: dict[str, Any]) -> None:
    url = push_client.push(pa.table({"n": [1, 2]}), name="cards_table", new_grid=True)
    body = {"kind": "diagram", "title": "Made-up flow", "body": "graph LR\n  A --> (("}
    call(server, "POST", "/cards", body)
    try:
        for dark in (False, True):
            page = open_grid(
                browser,
                url,
                width=1300,
                height=900,
                color_scheme="dark" if dark else "light",
                device_scale_factor=2,
            )
            page.locator(".nav-rail [data-area='analyze']").click()
            card = page.locator(".card", has_text="Made-up flow")
            note = card.locator(".error-note")
            expect(note).to_contain_text("This diagram could not be drawn", timeout=30000)
            expect(note.locator(".error-note-where")).to_have_text("Made-up flow")
            shot(page, f"error-in-a-card-{'dark' if dark else 'light'}.png", card)
            page.context.close()
    finally:
        for card in call(server, "GET", "/cards").get("cards", []):
            if card.get("title") == "Made-up flow":
                call(server, "DELETE", f"/cards/{card['id']}")
        call(server, "DELETE", f"/grids/{grid_of(url)}")
