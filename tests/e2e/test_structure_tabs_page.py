"""A structure's tab beside the code in a real browser (2026-11-22, the owner: "When we open a json or yaml or
xml file is it possible to open a collapsable navigation tree of nodes" / "I want it beside the ide so you can
search and explore" / "Does structures open as an ide? Or is it read only"): a made-up project's orders.json,
config.yaml, feed.xml and a script; each opened from the Files pane beside the script, searched (Next and
Previous), folded, a path copied as code, edited in the tree and in the text (the linter's squiggle, the tree
following), saved (only on Save), an edit made outside noticed (Reload / Keep mine). YAML needs PyYAML, which
the app does not depend on: without it, the app's one missing-package prompt. Pictures (light and dark,
1600x950) when SWISSARMYBENCH_STRUCTURE_SHOTS names a folder."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser, call, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_STRUCTURE_SHOTS")
HAS_YAML = importlib.util.find_spec("yaml") is not None

ORDERS = {
    "shop": {"name": "Made-up Bakery", "city": "Nowhere"},
    "orders": [
        {"id": 1001, "status": "open", "customer": {"name": "Ada Example", "tier": "gold"},
         "lines": [{"sku": "LOAF-1", "qty": 2, "price": 3.5}, {"sku": "BUN-6", "qty": 1, "price": 4.0}]},
        {"id": 1002, "status": "shipped", "customer": {"name": "Bo Sample", "tier": "silver"},
         "lines": [{"sku": "CAKE-2", "qty": 1, "price": 18.0}]},
        {"id": 1003, "status": "open", "customer": {"name": "Cy Madeup", "tier": "gold"},
         "lines": [{"sku": "LOAF-1", "qty": 5, "price": 3.5}, {"sku": "TART-3", "qty": 2, "price": 6.25}]},
        {"id": 1004, "status": "returned", "customer": {"name": "Di Placeholder", "tier": "bronze"},
         "lines": [{"sku": "BUN-6", "qty": 3, "price": 4.0}]},
    ],
}  # fmt: skip
CONFIG = "bakery:\n  name: Made-up Bakery\n  ovens: 3\nschedule:\n  - day: monday\n    bake: [loaf, bun]\n"
FEED = (
    '<?xml version="1.0"?>\n<feed><title>Made-up news</title>'
    '<entry id="1"><title>New loaf</title></entry><entry id="2"><title>Tart week</title></entry></feed>\n'
)
SCRIPT = 'import json\n\ndata = json.load(open("orders.json"))\nprint(len(data["orders"]))\n'


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def bakery(server: dict[str, Any], tmp_path: Path) -> Any:  # noqa: F811
    state = call(server, "POST", "/project/new", {"path": str(tmp_path / "work" / "bakery")})
    folder = Path(state.get("folder") or state["project"]["folder"])
    (folder / "orders.json").write_text(json.dumps(ORDERS, indent=2) + "\n", encoding="utf-8")
    (folder / "config.yaml").write_text(CONFIG, encoding="utf-8")
    (folder / "structures").mkdir(exist_ok=True)
    (folder / "structures" / "feed.xml").write_text(FEED, encoding="utf-8")
    (folder / "scripts").mkdir(exist_ok=True)
    (folder / "scripts" / "count.py").write_text(SCRIPT, encoding="utf-8")
    yield folder
    try:
        call(server, "POST", "/project/close", {"force": True})
    except Exception:  # noqa: S110 (the next test opens its own)
        pass


def scripts_page(browser: Browser, server: dict[str, Any], dark: bool = False) -> Page:  # noqa: F811
    context = browser.new_context(
        viewport={"width": 1600, "height": 950},
        color_scheme="dark" if dark else "light",
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    page.on("dialog", lambda d: d.accept())
    page.goto(f"http://127.0.0.1:{server['port']}/scripts#token={server['token']}")
    expect(page.locator(".wb-codex")).to_be_visible(timeout=20000)
    return page


def tree_file(page: Page, path: str) -> Any:
    return page.locator(f".wb-codex-file[data-path='{path}']")


def open_beside_the_script(page: Page) -> Any:
    """count.py, then orders.json split to its right: the structure's tab beside the code."""
    page.wait_for_timeout(800)  # the project's own documents come back meanwhile (its last layout)
    tree_file(page, "scripts/count.py").click()
    expect(page.locator(".wb-tab", has_text="count.py").first).to_be_visible(timeout=20000)
    tree_file(page, "orders.json").click()
    tab = page.locator(".wb-tab[data-kind='structure']", has_text="orders.json")
    expect(tab).to_be_visible(timeout=20000)
    return page.locator(".wb-doc-body.kind-structure:visible")


def test_a_structure_opens_beside_the_script_to_search_explore_edit_and_save(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    bakery: Path,
) -> None:
    for dark in (False, True):
        page = scripts_page(browser, server, dark)
        # The Files pane lists the project's structures (its top and structures/), never .sab/.
        group = page.locator(".wb-codex-group[data-group='structures']")
        expect(group).to_be_visible(timeout=20000)
        expect(group.locator(".wb-codex-file")).to_have_count(3)
        expect(page.locator(".wb-codex-file[data-path^='.sab']")).to_have_count(0)
        body = open_beside_the_script(page)
        # Beside the script: split right (Ctrl+\), both on show.
        call(
            server,
            "POST",
            "/workbench/window",
            {"command": "group.splitRight", "args": {}, "page": "scripts"},
        )
        expect(page.locator(".wb-group")).to_have_count(2, timeout=10000)
        page.locator(".wb-tab", has_text="count.py").first.click()  # the script in front on the left
        expect(page.locator(".wb-script-editor:visible")).to_have_count(1)
        expect(page.locator(".wb-script-editor:visible")).to_contain_text("json.load", timeout=10000)
        page.locator(".wb-tab[data-kind='structure']").click()
        tree = body.locator(".structure-tree")
        expect(tree).to_be_visible(timeout=20000)
        expect(tree.locator(".structure-row[data-path='$.orders']")).to_be_visible()
        # Search and explore: the matches marked, Next and Previous, the path shown.
        search = body.get_by_label("Search the structure")
        search.fill("LOAF-1")
        expect(body.locator(".sd-count")).to_have_text("1 of 2", timeout=10000)
        expect(tree.locator(".structure-row.found")).to_have_attribute(
            "data-path", "$.orders[0].lines[0].sku"
        )
        search.press("Enter")
        expect(body.locator(".sd-count")).to_have_text("2 of 2")
        expect(body.locator(".sd-path-text")).to_have_text("$.orders[2].lines[0].sku")
        search.press("Shift+Enter")
        expect(body.locator(".sd-count")).to_have_text("1 of 2")
        # Copy as code beside a Python file.
        body.get_by_role("button", name="Copy as code").click()
        assert page.evaluate("navigator.clipboard.readText()") == 'data["orders"][0]["lines"][0]["sku"]'
        shot(page, f"structure-beside-script-{'dark' if dark else 'light'}")
        # Fold: a caret folds a branch.
        search.fill("")
        row = tree.locator(".structure-row[data-path='$.shop']")
        row.locator(".structure-caret").click()
        expect(tree.locator(".structure-row[data-path='$.shop'][aria-expanded='false']")).to_have_count(1)
        if dark:
            # Both: the tree beside the file's text.
            body.get_by_role("button", name="Both").click()
            expect(body.locator(".ide-editor .monaco-editor")).to_be_visible(timeout=20000)
            shot(page, "structure-both-dark")
            body.get_by_role("button", name="Tree").click()  # as the next window finds it (remembered)
            page.context.close()
            continue
        # An edit in the tree: double-click a value; the text follows, the tab is dirty, the file not yet.
        row = tree.locator(".structure-row[data-path='$.orders[0].status']")
        expect(row).to_be_visible()
        row.locator(".structure-value").dblclick()
        row.locator("input.structure-edit").fill("closed")
        row.locator("input.structure-edit").press("Enter")
        expect(page.locator(".wb-tab[data-kind='structure'].dirty")).to_have_count(1, timeout=10000)
        assert (
            json.loads((bakery / "orders.json").read_text(encoding="utf-8"))["orders"][0]["status"] == "open"
        )
        # The text: Both shows it beside the tree; a broken edit is squiggled, the tree keeps its last value.
        body.get_by_role("button", name="Both").click()
        editor = body.locator(".ide-editor .monaco-editor")
        expect(editor).to_be_visible(timeout=20000)
        expect(editor).to_contain_text('"closed"', timeout=10000)
        editor.locator(".view-lines").click()
        page.keyboard.press("Control+End")
        page.keyboard.type("oops")
        expect(body.locator(".sd-error")).to_contain_text("Not JSON: line", timeout=10000)
        # The linter: listed in Problems (its squiggle at its line in the editor), the tree as it last parsed.
        expect(body.locator(".ide-tab", has_text="Problems")).to_contain_text("1", timeout=10000)
        expect(
            tree.locator(".structure-row[data-path='$.orders[0].status'] .structure-value")
        ).to_contain_text("closed")
        body.locator(".ide-problem").first.click()  # to its line: the squiggle under it
        expect(body.locator(".monaco-editor .squiggly-error").first).to_be_attached(timeout=10000)
        shot(page, "structure-text-error-light")
        editor.locator(".view-lines").click()
        page.keyboard.press("Control+End")
        for _ in range(4):
            page.keyboard.press("Backspace")
        expect(body.locator(".sd-error")).to_be_hidden(timeout=10000)
        # Save writes the file (Ctrl+S in the IDE).
        editor.locator(".view-lines").click()
        page.keyboard.press("Control+s")
        expect(page.locator(".wb-tab[data-kind='structure'].dirty")).to_have_count(0, timeout=10000)
        assert (
            json.loads((bakery / "orders.json").read_text(encoding="utf-8"))["orders"][0]["status"]
            == "closed"
        )
        # An edit made outside: taken at once while nothing is unsaved (the tree and the text follow).
        tree.locator(".structure-row[data-path='$.shop'] .structure-caret").click()  # unfolded again
        changed = json.loads((bakery / "orders.json").read_text(encoding="utf-8"))
        changed["shop"]["city"] = "Elsewhere"
        (bakery / "orders.json").write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
        city = tree.locator(".structure-row[data-path='$.shop.city'] .structure-value")
        expect(city).to_contain_text("Elsewhere", timeout=20000)
        expect(page.locator(".wb-tab[data-kind='structure'].dirty")).to_have_count(0)
        # With unsaved edits: Reload / Keep mine.
        body.get_by_role("button", name="Tree").click()
        row = tree.locator(".structure-row[data-path='$.shop.name']")
        row.locator(".structure-value").dblclick()
        row.locator("input.structure-edit").fill("Mine")
        row.locator("input.structure-edit").press("Enter")
        page.wait_for_timeout(300)
        changed["shop"]["name"] = "Theirs"
        (bakery / "orders.json").write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
        note = body.locator(".sd-elsewhere")
        expect(note).to_be_visible(timeout=20000)
        shot(page, "structure-changed-elsewhere-light")
        note.get_by_role("button", name="Reload").click()
        expect(tree.locator(".structure-row[data-path='$.shop.name'] .structure-value")).to_contain_text(
            "Theirs", timeout=10000
        )
        # The XML file in the same pane: its tree.
        tree_file(page, "structures/feed.xml").click()
        xml = page.locator(".wb-doc-body.kind-structure:visible .structure-tree")
        expect(xml.locator(".structure-row[data-path='$.feed.entry']")).to_be_visible(timeout=20000)
        shot(page, "structure-xml-light")
        # YAML: PyYAML is the app's optional package; without it, the one missing-package prompt.
        tree_file(page, "config.yaml").click()
        if HAS_YAML:
            expect(page.locator(".wb-tab[data-kind='structure']", has_text="config.yaml")).to_be_visible(
                timeout=20000
            )
        else:
            prompt = page.locator("dialog.missing-packages")
            expect(prompt).to_be_visible(timeout=20000)
            expect(prompt).to_contain_text("PyYAML")
            shot(page, "structure-yaml-missing-light")
            prompt.get_by_role("button", name="Not now").click()
        page.context.close()


def test_the_agent_opens_a_structure_in_a_tab_and_searches_it(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    bakery: Path,
) -> None:
    page = scripts_page(browser, server)
    page.wait_for_timeout(500)
    opened = call(
        server,
        "POST",
        "/workbench/window",
        {
            "command": "structure.open",
            "args": {"path": str(bakery / "orders.json"), "at": "$.orders[1]"},
            "page": "scripts",
        },
        agent=True,
    )["result"]
    assert opened["selected"] == "$.orders[1]" and opened["code"] == 'data["orders"][1]'
    expect(page.locator(".wb-tab[data-kind='structure']", has_text="orders.json")).to_be_visible(
        timeout=20000
    )
    found = call(
        server,
        "POST",
        "/workbench/window",
        {"command": "structure.search", "args": {"words": "gold"}},
        agent=True,
    )["result"]
    assert found["matches"] == 2 and found["match"] == "$.orders[0].customer.tier"
    after = call(server, "POST", "/workbench/window", {"command": "structure.next", "args": {}}, agent=True)[
        "result"
    ]
    assert after["path"] == "$.orders[2].customer.tier"
    expect(page.locator(".wb-doc-body.kind-structure:visible .sd-count")).to_have_text("2 of 2")
    listed = call(server, "POST", "/workbench/window", {"command": "documents", "args": {}}, agent=True)[
        "result"
    ]
    assert any(d.get("structure", {}).get("search") == "gold" for d in listed["documents"])
    page.context.close()
