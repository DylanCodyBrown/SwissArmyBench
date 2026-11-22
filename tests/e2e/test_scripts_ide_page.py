"""The Notebooks and Scripts pages in a real browser (the owner, 2026-11-21: "notebooks and scripts should not
reuse the same page they are seperate things"; the Scripts page a Python IDE). Made-up project files only."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser, call, server, until  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_SCRIPTS_SHOTS")
FUNCTIONS = 'def tidy(name: str) -> str:\n    """Trim a made-up name."""\n    return name.strip()\n'
LOAD = (
    "from functions import tidy\n\nORDERS = 'orders'\n\n\n"
    "class Loader:\n    def run(self):\n        return tidy(ORDERS)\n"
)


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def shop(server: dict[str, Any], tmp_path: Path) -> Any:  # noqa: F811
    """A made-up project: functions.py, a package of scripts, a page, data.py made from data.ipynb."""
    state = call(server, "POST", "/project/new", {"path": str(tmp_path / "work" / "shop")})
    folder = Path(state.get("folder") or state["project"]["folder"])
    (folder / "functions.py").write_text(FUNCTIONS, encoding="utf-8")
    (folder / "scripts" / "etl").mkdir(parents=True, exist_ok=True)
    (folder / "scripts" / "etl" / "load.py").write_text(LOAD, encoding="utf-8")
    (folder / "scripts" / "report.py").write_text("print('made-up report')\n", encoding="utf-8")
    yield folder
    try:
        call(server, "POST", "/project/close", {"force": True})
    except Exception:  # noqa: S110 (unsaved edits at the end of a test: the next one opens its own)
        pass


def page_of(browser: Browser, server: dict[str, Any], where: str, width: int = 1500) -> Page:  # noqa: F811
    context = browser.new_context(
        viewport={"width": width, "height": 900}, device_scale_factor=2 if SHOTS else 1
    )
    page = context.new_page()
    page.on("dialog", lambda d: d.accept())
    page.goto(f"http://127.0.0.1:{server['port']}/{where}#token={server['token']}")
    expect(page.locator(".wb-codex" if where != "workspace" else ".nav-rail")).to_be_visible(timeout=20000)
    return page


def front(page: Page) -> Any:
    """The editor on show (the front tab's)."""
    return page.locator(".wb-script-editor:visible .view-lines").first


def tree_file(page: Page, path: str) -> Any:
    return page.locator(f".wb-codex-file[data-path='{path}']")


def test_notebooks_and_scripts_are_two_pages_that_never_mix(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    shop: Path,
) -> None:
    page = page_of(browser, server, "workspace")
    # The rail's Notebooks: only notebooks (the data notebook first).
    page.locator(".nav-rail [data-area='notebooks']").click()
    expect(page).to_have_url(re.compile(r"/notebooks\?"), timeout=20000)
    explorer = page.locator(".wb-codex.page-notebooks")
    expect(explorer.locator(".wb-codex-file")).to_have_count(1, timeout=20000)
    expect(explorer.locator(".wb-codex-file").first).to_contain_text("data.ipynb")
    explorer.locator(".wb-codex-file").first.click()
    expect(page.locator(".wb-tab", has_text="data.ipynb")).to_be_visible(timeout=20000)
    shot(page, "notebooks-page")
    # The rail's Scripts: another window, no notebook tab there; a .py opens there.
    with page.context.expect_page() as opened:
        page.locator(".nav-rail [data-area='scripts']").click()
    scripts = opened.value
    expect(scripts).to_have_url(re.compile(r"/scripts\?"), timeout=20000)
    expect(scripts.locator(".wb-codex.page-scripts")).to_be_visible(timeout=20000)
    expect(scripts.locator(".wb-tab[data-kind$='otebook']")).to_have_count(0)  # never a notebook here
    tree_file(scripts, "scripts/report.py").click()
    expect(scripts.locator(".wb-tab", has_text="report.py")).to_be_visible(timeout=20000)
    expect(scripts.locator(".wb-tab", has_text="data.ipynb")).to_have_count(0)
    # The notebook cannot be put on the Scripts page: asked of the Scripts window, it opens on its own page.
    call(
        server,
        "POST",
        "/workbench/window",
        {"command": "file.open", "args": {"path": str(shop / "data.ipynb")}, "page": "scripts"},
        agent=True,
    )
    page.wait_for_timeout(500)
    expect(scripts.locator(".wb-tab", has_text="data.ipynb")).to_have_count(0)
    # A notebook handed to the Scripts window is refused in one line (a drop on the other page's groups).
    said = scripts.evaluate(
        """async () => {
            const json = {'Content-Type': 'application/json'};
            const doc = {kind: 'notebook', path: null, title: 'x', cells: []};
            const made = await fetch('/workbench/handoffs',
              {method: 'POST', headers: json, body: JSON.stringify({document: doc})}).then(r => r.json());
            const took = await fetch(`/workbench/handoffs/${made.id}/take`,
              {method: 'POST', headers: json, body: JSON.stringify({window: 'w', page: 'scripts'})});
            return [took.status, await took.text()];
        }"""
    )
    assert said[0] == 409 and "opens on the Notebooks page" in said[1]
    page.context.close()


def test_the_scripts_ide(browser: Browser, server: dict[str, Any], shop: Path) -> None:  # noqa: F811
    page = page_of(browser, server, "scripts")
    explorer = page.locator(".wb-codex.page-scripts")
    # The tree: Your scripts by module, Project code, the library's, never a notebook.
    expect(explorer.locator(".wb-codex-group[data-group='scripts']")).to_be_visible(timeout=20000)
    expect(tree_file(page, "scripts/etl/load.py")).to_contain_text("etl.load")
    expect(explorer.locator(".wb-codex-file", has_text="data.ipynb")).to_have_count(0)
    expect(explorer.locator(".wb-codex-group[data-group='library-connections']")).to_be_visible()
    # Two scripts from the explorer: two named tabs, each its code; switch between them.
    tree_file(page, "scripts/etl/load.py").click()
    load_tab = page.locator(".wb-tab", has_text="load.py")
    expect(load_tab).to_be_visible(timeout=20000)
    tree_file(page, "functions.py").click()
    functions_tab = page.locator(".wb-tab", has_text="functions.py")
    expect(functions_tab).to_be_visible(timeout=20000)
    expect(front(page)).to_contain_text("def tidy", timeout=20000)
    load_tab.click()
    expect(front(page)).to_contain_text("class Loader", timeout=20000)
    # Clicking an open file's tree item brings its tab forward.
    tree_file(page, "functions.py").click()
    expect(functions_tab).to_have_class(re.compile(r"\bactive\b"))
    load_tab.click()
    # The outline: the module's classes, functions and constants; a click goes to the line.
    file_row = tree_file(page, "scripts/etl/load.py").locator("xpath=..")
    file_row.locator(".wb-codex-fold").click()
    symbol = explorer.locator(".wb-codex-symbol[data-symbol='run']")
    expect(symbol).to_be_visible()
    symbol.click()
    expect(page.locator(".wb-status")).to_contain_text("Line 7,", timeout=10000)
    shot(page, "scripts-ide")
    # Go to definition (F12) across modules: tidy, in run(), is functions.py's.
    symbol.click()
    expect(page.locator(".wb-status")).to_contain_text("Line 7,", timeout=10000)
    page.wait_for_timeout(400)  # the reveal lands
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Home")  # the line's first word: return
    page.keyboard.press("Control+ArrowRight")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")  # inside tidy
    expect(page.locator(".wb-status")).to_contain_text("Line 8, column 17")
    page.keyboard.press("F12")
    expect(functions_tab).to_have_class(re.compile(r"\bactive\b"), timeout=20000)
    load_tab.click()
    # Completion across modules: a name of functions.py offered in load.py.
    editor = page.locator(".wb-script-editor:visible .monaco-editor").first
    editor.click()
    page.keyboard.press("Control+End")
    page.keyboard.press("Enter")
    page.keyboard.insert_text("from functions import ti")
    page.keyboard.press("Control+Space")
    expect(page.locator(".suggest-widget .monaco-list-row", has_text="tidy").first).to_be_visible(
        timeout=20000
    )
    page.keyboard.press("Escape")
    # A diagnostic as you type: an undefined name.
    page.keyboard.press("Enter")
    page.keyboard.insert_text("print(not_defined_here)")
    expect(page.locator(".wb-status")).to_contain_text(re.compile(r"\d+ error"), timeout=20000)
    # Run selection: the line in the script's console.
    page.keyboard.press("Control+Enter")  # run the line: the console says the error
    expect(page.locator(".wb-console")).to_contain_text("not_defined_here", timeout=60000)
    # Full screen: the rail and the explorer go; Escape brings them back.
    page.keyboard.press("F11")
    expect(page.locator(".nav-rail")).to_be_hidden()
    expect(explorer).to_be_hidden()
    shot(page, "scripts-ide-full-screen")
    page.mouse.click(700, 10)
    page.keyboard.press("Escape")
    expect(page.locator(".nav-rail")).to_be_visible()
    expect(explorer).to_be_visible()
    # The Files pane hides by its status bar button and comes back (Ctrl+B is the same command).
    files = page.locator(".wb-status .side-toggle", has_text="Files")
    files.click()
    expect(explorer).to_be_hidden()
    expect(files).to_have_attribute("aria-pressed", "false")
    shot(page, "scripts-ide-files-hidden")
    files.click()
    expect(explorer.locator(".wb-codex-search")).to_be_visible()
    page.context.close()


def box(locator: Any) -> dict[str, float]:
    found = locator.bounding_box()
    assert found is not None
    return dict(found)


def window_command(server: dict[str, Any], command: str, args: dict[str, Any] | None = None) -> Any:  # noqa: F811
    body = {"command": command, "args": args or {}, "page": "scripts"}
    return call(server, "POST", "/workbench/window", body, agent=True)["result"]


def test_files_and_blades_are_side_panes_on_the_right(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    shop: Path,
) -> None:
    """The owner, 2026-11-22: "make the blades and files panes function just like properties and widgets on
    canvas. On the right side with buttons to show and hide them and then go ahead and remove blades rail
    icon": two columns side by side on the right of the code, each its own toggle, resized by its edge,
    remembered over a reload; the rail has no Blades; every way to Blades lands on the pane shown."""
    page = page_of(browser, server, "scripts")
    files = page.locator(".wb-side.wb-codex")
    blades = page.locator(".wb-blades-side")
    files_toggle = page.locator(".wb-status .side-toggle", has_text="Files")
    blades_toggle = page.locator(".wb-status .side-toggle", has_text="Blades")
    expect(page.locator(".nav-rail [data-area='blades']")).to_have_count(0)
    expect(files).to_be_visible()
    expect(blades).to_be_hidden()  # Blades start hidden
    expect(files_toggle).to_have_attribute("aria-pressed", "true")
    expect(blades_toggle).to_have_attribute("aria-pressed", "false")
    assert box(files)["x"] > box(page.locator(".wb-body"))["x"] + 400  # on the right of the code
    blades_toggle.click()
    expect(blades).to_be_visible()
    expect(blades_toggle).to_have_attribute("aria-pressed", "true")
    # Side by side, not stacked: Blades its own column at the far right, level with Files.
    f, b = box(files), box(blades)
    assert b["x"] >= f["x"] + f["width"] and abs(b["y"] - f["y"]) < 2 and abs(b["height"] - f["height"]) < 2
    shot(page, "scripts-side-panes")
    # Resized by its left edge.
    grip = page.locator(".wb-siderow > .side-grip").first
    g = box(grip)
    page.mouse.move(g["x"] + 2, g["y"] + 200)
    page.mouse.down()
    page.mouse.move(g["x"] - 78, g["y"] + 200, steps=4)
    page.mouse.up()
    wider = box(files)["width"]
    assert wider > f["width"] + 60
    # Remembered over a reload: Blades shown, the width kept; then Files hidden, kept too.
    page.reload()
    expect(blades).to_be_visible(timeout=20000)
    assert abs(box(files)["width"] - wider) < 2
    files_toggle.click()
    expect(files).to_be_hidden()
    page.reload()
    expect(blades).to_be_visible(timeout=20000)
    expect(files).to_be_hidden()
    # The agent: the same buttons as commands (workbench_window).
    assert window_command(server, "view.files", {"show": True}) == {"open": True}
    expect(files).to_be_visible()
    assert window_command(server, "view.blades", {"show": False}) == {"open": False}
    expect(blades).to_be_hidden()
    # An address that names Blades (the old rail icon's, /catalog's, app_navigate's): the pane shown.
    page.goto(f"http://127.0.0.1:{server['port']}/catalog#token={server['token']}")
    expect(page).to_have_url(re.compile(r"/scripts\?.*pane=blades"), timeout=20000)
    expect(blades).to_be_visible(timeout=20000)
    window_command(server, "view.blades", {"show": False})
    expect(blades).to_be_hidden()
    call(server, "POST", "/navigate", {"to": "blades", "window": "scripts"}, agent=True)
    expect(blades).to_be_visible(timeout=20000)
    # A starter opens as a tab; its Save is refused with Copy as your own.
    starter = blades.locator(".starter-family").first
    expect(starter).to_be_visible(timeout=20000)
    starter.click()
    blades.locator(".starter-item .blade-name").first.click()
    expect(page.locator(".wb-tab[data-kind='blade']")).to_be_visible(timeout=20000)
    shot(page, "scripts-blades-pane")
    page.context.close()


def test_a_script_open_in_two_windows_follows_a_save_and_an_outside_edit(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    shop: Path,
) -> None:
    report = shop / "scripts" / "report.py"
    first = page_of(browser, server, "scripts")
    second = page_of(browser, server, "scripts")
    for p in (first, second):
        tree_file(p, "scripts/report.py").click()
        expect(front(p)).to_contain_text("made-up report", timeout=20000)
    # Edited and saved in one: the other, unchanged, follows in place.
    first.locator(".wb-script-editor:visible .monaco-editor").click()
    first.keyboard.press("Control+End")
    first.keyboard.insert_text("\nprint('second line')")
    first.keyboard.press("Control+S")
    expect(front(second)).to_contain_text("second line", timeout=20000)
    expect(second.locator(".wb-elsewhere")).to_have_count(0)
    # Edited here, then changed outside the app: never overwritten, the choice shown.
    second.locator(".wb-script-editor:visible .monaco-editor").click()
    second.keyboard.press("Control+End")
    second.keyboard.insert_text("\n# mine")
    report.write_text("print('changed outside')\n", encoding="utf-8")
    bar = second.locator(".wb-elsewhere")
    expect(bar).to_be_visible(timeout=20000)
    expect(bar).to_contain_text("Changed elsewhere.")
    expect(front(second)).to_contain_text("mine")
    bar.get_by_role("button", name="Reload").click()
    expect(front(second)).to_contain_text("changed outside", timeout=20000)
    first.context.close()
    second.context.close()
