"""The browser tests (the front end, blazor/): a real server per module with its own state folder and
made-up data only, and Chromium driven by Playwright. Each test leaves no project open behind it. Skipped
when the front end is not built here (`python blazor/publish.py` writes blazor/publish/wwwroot; a wheel
carries swissarmybench/web_blazor)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from swissarmybench.settings import Settings

# The Chromium these tests drive.
CHROMIUM = os.environ.get("SAB_CHROMIUM", "/opt/pw-browsers/chromium")
# The app's first load (its .NET runtime) is slow on a busy machine.
FIRST_LOAD_MS = 60_000
# What a browser test's expect waits for at most (Playwright's own five seconds failed on a busy machine).
expect.set_options(timeout=15_000)

if not (Settings().blazor_root / "index.html").is_file():
    pytest.skip("The Blazor front end is not built here (python blazor/publish.py).", allow_module_level=True)


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """A server of its own: its state, projects and Workbench folders in a temporary folder."""
    yield from serve(tmp_path_factory.mktemp("blazor"))


def serve(tmp: Path) -> Iterator[dict[str, Any]]:
    """A server over `tmp` (its state folder `tmp/state`, which a test may fill first), stopped after."""
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(tmp / "projects"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "workbench"),
        "SWISSARMYBENCH_NO_BROWSER": "1",
        # The file chooser falls back to the page's own picker (no system dialog opens during a test).
        "SWISSARMYBENCH_SYSTEM_DIALOGS": "off",
        "SWISSARMYBENCH_PROJECT_VENV": "off",
        "SWISSARMYBENCH_AUTO_INSTALL": "off",
    }
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    info: dict[str, Any] | None = None
    for _ in range(150):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    if info is None:
        process.kill()
        raise AssertionError("the server did not start")
    try:
        yield info | {"tmp": tmp}
    finally:
        process.terminate()
        process.wait(timeout=20)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        launched = playwright.chromium.launch(executable_path=CHROMIUM)
        yield launched
        launched.close()


@pytest.fixture(autouse=True)
def no_project_left_open(request: pytest.FixtureRequest) -> Iterator[None]:
    """A project opened by a test is THE open project of the module's server: closed after it (its unsaved
    changes let go), so the next test's pages do not show it."""
    yield
    if "server" not in request.fixturenames:
        return
    server: dict[str, Any] = request.getfixturevalue("server")
    try:
        if call(server, "GET", "/project")["project"]:
            call(server, "POST", "/project/close", {"discard": True})
    except Exception:  # noqa: S110 (a server that stopped: nothing is open)
        pass


def call(info: dict[str, Any], method: str, path: str, body: Any = None) -> Any:
    """The server's route, as the agent or a test calls it (the token in its header)."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}",
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (127.0.0.1)
        return json.loads(response.read() or b"null")


def open_page(browser: Browser, info: dict[str, Any], path: str = "", dark: bool = False) -> Page:
    """A page of the Blazor app, opened as the launcher opens it (the token in the address's fragment)."""
    page = browser.new_page(viewport={"width": 1360, "height": 860}, color_scheme="dark" if dark else "light")
    page.set_default_timeout(15_000)
    page.goto(f"http://127.0.0.1:{info['port']}/blazor/{path}#token={info['token']}")
    page.wait_for_selector(".nav-rail", timeout=FIRST_LOAD_MS)
    return page


def loose_file(info: dict[str, Any], name: str, kind: str = "python", text: str | None = None) -> Path:
    """A named file in the server's Workbench folder (no project open), made as New file makes one (the
    server writes its starter); with `text`, holding that instead. Its path."""
    folder = Path(info["tmp"]) / "workbench"
    folder.mkdir(exist_ok=True)
    made = call(info, "POST", "/scripts/files/new", {"type": kind, "name": name, "folder": str(folder)})
    path = Path(made["path"])
    if text is not None:
        path.write_text(text, encoding="utf-8")
    return path


def name_new_file(page: Page, name: str, folder: Any = None) -> None:
    """The New file dialog answered: its name typed (its folder too), then Create; the dialog goes."""
    dialog = page.locator(".dialog.new-file")
    dialog.get_by_label("Name").fill(name)
    if folder is not None:
        dialog.get_by_label("Folder", exact=True).fill(str(folder))
    expect(dialog.locator(".new-file-check")).to_contain_text("Makes")
    dialog.locator(".new-file-create").click()
    expect(dialog).to_have_count(0)


def choose_path(page: Page, path: Any, folder: bool = False, save: bool = False) -> None:
    """A pick in the page's own file picker (no system dialog opens in a test: the classic fileChooser.ts
    choosePage): the folder typed in its path box and Enter, then the file's row opened, Choose this
    folder, or (Save as) the file's name typed and Save here."""
    picker = page.locator(".dialog.file-chooser")
    where = Path(path)
    picker.get_by_label("Folder", exact=True).fill(str(where if folder else where.parent))
    picker.get_by_label("Folder", exact=True).press("Enter")
    expect(picker.locator(".file-crumb.current")).to_have_text(where.name if folder else where.parent.name)
    if folder:
        picker.get_by_role("button", name="Choose this folder").click()
    elif save:
        picker.get_by_label("File name").fill(where.name)
        picker.get_by_role("button", name="Save here").click()
    else:
        picker.locator(".file-row", has_text=where.name).dblclick()


# The accessibility check run in the page (axe-core is not among our npm packages, so it is our own): every
# visible button, link, field and menu line has an accessible name (aria-label, aria-labelledby, its words, a
# <label>, a title, a field's placeholder). AG Grid's, Monaco's and Plotly's own insides are theirs.
UNNAMED = """() => {
  const theirs = '.ag-root-wrapper, .monaco-editor, .js-plotly-plot, .mermaid-host';
  const named = (el) => {
    if ((el.getAttribute('aria-label') || '').trim()) return true;
    const by = el.getAttribute('aria-labelledby');
    const text = (id) => (document.getElementById(id)?.textContent || '').trim();
    if (by && by.split(' ').some(text)) return true;
    if ((el.textContent || '').trim() && !['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) return true;
    if (el.id && document.querySelector(`label[for="${el.id}"]`)) return true;
    if (el.closest('label') && (el.closest('label').textContent || '').trim()) return true;
    if ((el.getAttribute('title') || '').trim()) return true;
    if ((el.getAttribute('placeholder') || '').trim()) return true;
    return false;
  };
  const shown = (el) => el.offsetParent !== null || el.getClientRects().length > 0;
  const controls = document.querySelectorAll(
    'button, a[href], input:not([type=hidden]), select, textarea, '
      + '[role=menuitem], [role=tab], [role=treeitem]'
  );
  return [...controls]
    .filter((el) => shown(el) && !el.closest(theirs) && !named(el))
    .map((el) => el.outerHTML.slice(0, 160));
}"""


def unnamed_controls(page: Page) -> list[str]:
    """The visible controls on the page with no accessible name (empty when all are named)."""
    found: list[str] = page.evaluate(UNNAMED)
    return found


@pytest.fixture
def page_errors() -> list[str]:
    """The page's own errors (an exception in its C# shows #blazor-error-ui), collected by each test."""
    return []
