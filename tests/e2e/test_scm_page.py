# ruff: noqa: F811, E501
"""The Git extension's pages in a real browser, against GitHub stood in for on 127.0.0.1 (tests/github_standin.py;
real GitHub is never reached): the rail's Source Control icon only while the extension is on; Settings' GitHub
section's replacement, the Team box, is tests/e2e/test_team_page.py's; the Source
Control page (the changes with VS Code's letters, Stage Changes, Commit with Ctrl+Enter, the graph's rows and
lanes, a commit's files, Monaco's diff editor, F7 to the next change, Inline View); the footer's mark when the
open project is out of sync and gone after Pull; a shared card's Pull and a conflict shown. Made-up data only.

With SWISSARMYBENCH_SCM_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser, call, until  # noqa: F401
from tests.github_standin import TOKEN, GitHubStandin

SHOTS = os.environ.get("SWISSARMYBENCH_SCM_SHOTS")
ROOT = Path(__file__).resolve().parents[2]
REPO = "made-up-team/meta-store"
SHARED = "made-up-team/shared-projects"
MANIFEST = json.dumps({"swissarmybench": "project", "format": 1, "tables": []}).encode()


def start(
    tmp: Path, extensions: str, hub: GitHubStandin | None
) -> tuple[subprocess.Popen[bytes], dict[str, Any]]:
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_EXTENSIONS": extensions,
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "home" / "SwissArmyBench"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(tmp / "home" / "Projects here"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "PYTHONPATH": os.pathsep.join(
            [str(ROOT / "extensions" / name / "src") for name in ("g" + "it", "streamlit")]
            + [str(ROOT), str(ROOT / "src")]
        ),
        "PYTHON_KEYRING_BACKEND": "tests.file_keyring.FileKeyring",
        "SAB_TEST_KEYRING_FILE": str(tmp / "keyring.json"),
        "SWISSARMYBENCH_NO_BROWSER": "1",
    }
    if hub is not None:
        env |= {"SWISSARMYBENCH_GITHUB_API": hub.url, "SWISSARMYBENCH_GITHUB_WEB": hub.url}
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    for _ in range(300):
        try:
            return process, json.loads((tmp / "server.json").read_text())
        except (OSError, ValueError):
            time.sleep(0.1)
    process.kill()
    raise AssertionError("server did not start")


@pytest.fixture(scope="module")
def hub() -> Iterator[GitHubStandin]:
    with GitHubStandin() as standin:
        standin.repository(
            REPO,
            {
                "README.md": b"# Meta store\n",
                ".gitignore": b"local/\n",
                "variables.toml": b'format = 1\n\n[variables.REGION]\nvalue = "north"\n',
                "notes/close.md": b"one\ntwo\nthree\nfour\n",
            },
        )
        standin.teammate(REPO, {"notes/q3.md": b"Q3 close\n"}, "Add the Q3 note")
        standin.teammate(REPO, {"notes/close.md": b"one\ntwo\nthree\nfour\nfive\n"}, "Five steps to close")
        standin.repository(
            SHARED,
            {
                "Close/.sab/project.json": MANIFEST,
                "Close/.gitignore": b".sab/data/\n",
                "Close/plan.md": b"alpha\nbeta\n",
            },
        )
        yield standin


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory, hub: GitHubStandin) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("scm-e2e")
    process, info = start(tmp, "streamlit," + "g" + "it", hub)
    yield info | {"tmp": tmp}
    process.terminate()
    process.wait(timeout=20)


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def open_page(browser: Browser, server: dict[str, Any], view: str = "", dark: bool = False) -> Page:
    context = browser.new_context(
        viewport={"width": 1400, "height": 900},
        device_scale_factor=2,
        color_scheme="dark" if dark else "light",
    )
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace{view}#token={server['token']}")
    expect(page.locator(".nav-rail")).to_be_visible(timeout=20000)
    return page


def test_the_rail_icon_shows_only_while_the_extension_is_on(browser: Browser, tmp_path: Path) -> None:
    process, info = start(tmp_path, "streamlit", None)
    try:
        page = open_page(browser, info | {"tmp": tmp_path})
        expect(page.locator('.nav-rail [data-area="connections"]')).to_be_visible()
        page.wait_for_timeout(500)
        expect(page.locator('.nav-rail [data-area="scm"]')).to_be_hidden()
        expect(page.locator(".area-mark")).to_have_count(0)
        page.context.close()
    finally:
        process.terminate()
        process.wait(timeout=20)


def test_settings_sign_in_clone_and_the_source_control_page(
    browser: Browser, server: dict[str, Any], hub: GitHubStandin
) -> None:
    tmp: Path = server["tmp"]
    meta = tmp / "team-meta"
    meta.mkdir()
    page = open_page(browser, server)
    expect(page.locator('.nav-rail [data-area="scm"]')).to_be_visible()
    # Signed in and cloned (Settings' Team box does it with one repository: tests/e2e/test_team_page.py).
    call(server, "POST", "/git/sign-in/token", {"token": TOKEN})
    call(server, "POST", "/git/clone", {"which": "library", "repository": REPO, "folder": str(meta)})
    assert (meta / "notes" / "q3.md").read_text() == "Q3 close\n"

    # The Source Control page: a change here, its letter, Stage Changes, Commit with Ctrl+Enter.
    (meta / "notes" / "close.md").write_text("one\nTWO\nthree\nfour\nfive\n")
    (meta / "notes" / "new.md").write_text("new\n")
    page.locator('.nav-rail [data-area="scm"]').click()
    view = page.locator(".scm-sidebar")
    row = view.locator('.monaco-list-row[data-path="notes/close.md"]')
    expect(row).to_have_attribute("data-letter", "M")
    expect(view.locator('.monaco-list-row[data-path="notes/new.md"]')).to_have_attribute("data-letter", "U")
    expect(view.locator('[data-group="workingTree"].monaco-list-row .monaco-count-badge')).to_have_text("2")
    expect(view.locator("textarea.scm-input-box")).to_have_attribute(
        "placeholder", 'Message (Ctrl+Enter to commit on "main")'
    )
    shot(page, "scm-changes")
    row.hover()
    row.get_by_role("button", name="Stage Changes").click()
    staged = view.locator('.monaco-list-row[data-group="index"][data-path="notes/close.md"]')
    expect(staged).to_have_attribute("data-letter", "M")
    expect(view.locator('[data-group="index"].monaco-list-row .resource-group .name')).to_have_text(
        "Staged Changes"
    )
    # Open Changes: Monaco's diff editor, F7 to the next change, Inline View.
    staged.click()
    diff = page.locator(".scm-editor-part .monaco-diff-editor")
    expect(diff).to_be_visible(timeout=20000)
    expect(page.locator(".scm-diff-title")).to_contain_text("close.md")
    page.locator(".scm-editor-part .modified-in-monaco-diff-editor .view-lines").click()
    page.keyboard.press("F7")
    expect(page.locator(".scm-diff-files .monaco-list-row.selected")).to_have_attribute(
        "data-diff-file", "notes/close.md"
    )
    shot(page, "scm-diff")
    page.locator('.scm-editor-part [data-codicon="ellipsis"]').click()
    page.locator(".scm-context-view").get_by_role("menuitem", name="Inline View").click()
    expect(page.locator(".scm-editor-part .monaco-diff-editor.side-by-side")).to_have_count(0)
    box = view.locator("textarea.scm-input-box")
    box.fill("Shout the second step")
    box.press("Control+Enter")
    expect(view.locator('.monaco-list-row[data-group="index"]')).to_have_count(0, timeout=20000)
    assert hub.files(REPO)["notes/close.md"] == b"one\nTWO\nthree\nfour\nfive\n"
    assert "notes/new.md" not in hub.files(REPO)
    assert hub.commits[hub.head(REPO)]["message"] == "Shout the second step"
    # The graph: its rows (newest first), the lanes' SVG, a commit's files and its diff.
    graph = view.locator(".scm-history-view")
    rows = graph.locator(".monaco-list-row[data-commit]")
    expect(rows).to_have_count(4)
    expect(rows.first.locator(".label-name")).to_have_text("Shout the second step")
    expect(rows.first.locator("svg.graph circle")).to_have_count(2)  # HEAD: a ring
    expect(rows.nth(1).locator("svg.graph path").first).to_be_attached()
    expect(rows.first.locator(".label-container .label")).to_have_count(2)  # main and origin/main
    shot(page, "scm-graph")
    rows.nth(1).click()
    changed = graph.locator('.monaco-list-row[data-commit-file="notes/close.md"]')
    expect(changed).to_be_visible()
    changed.click()
    expect(page.locator(".scm-diff-title")).to_contain_text("close.md")
    # Discard Changes on a new file: VS Code's question, then the file is gone.
    fresh = view.locator('.monaco-list-row[data-path="notes/new.md"]')
    fresh.hover()
    fresh.get_by_role("button", name="Discard Changes").click()
    expect(page.locator(".scm-dialog .dialog-message")).to_contain_text(
        "Are you sure you want to DELETE new.md?"
    )
    page.locator(".scm-dialog").get_by_role("button", name="Delete File").click()
    expect(fresh).to_have_count(0, timeout=20000)
    assert not (meta / "notes" / "new.md").exists()
    page.context.close()


def test_the_footer_mark_and_a_shared_card(
    browser: Browser, server: dict[str, Any], hub: GitHubStandin
) -> None:
    tmp: Path = server["tmp"]
    shared = tmp / "team-projects"
    call(server, "POST", "/git/sign-in/token", {"token": TOKEN})
    call(server, "POST", "/git/clone", {"which": "shared", "repository": SHARED, "folder": str(shared)})
    call(server, "POST", "/project/open", {"path": str(shared / "Close")})
    page = open_page(browser, server)
    footer = page.locator(".app-footer")
    # The footer ready: its mark asked for once (it listens for the save's notice from then on).
    page.wait_for_function(
        "() => performance.getEntriesByType('resource').some(e => e.name.includes('/git/mark'))",
        timeout=20000,
    )
    # And its live socket connected (the server counts it among the windows): the save's notice reaches it.
    assert until(lambda: call(server, "GET", "/lifecycle")["windows"] >= 1)
    expect(footer.locator(".area-mark")).to_have_count(0)  # up to date
    # A change here: the mark says so (no polling: the save's notice and the page's read).
    (shared / "Close" / "plan.md").write_text("alpha\nmine\n")
    call(server, "POST", "/project/save", {})
    mark = footer.locator(".area-mark")
    expect(mark).to_have_text(
        re.compile(r"↑\d+ to push"), timeout=20000
    )  # plan.md, and the save's .sab files
    shot(page, "footer-mark")
    # The teammate changes the same line: Pull leaves a conflict, the card and the page show it.
    hub.teammate(SHARED, {"Close/plan.md": b"alpha\ntheirs\n"})
    call(server, "GET", "/git?remote=1")
    call(server, "POST", "/project/close", {"discard": True})
    page.goto(f"http://127.0.0.1:{server['port']}/workspace?open=projects#token={server['token']}")
    card = page.locator('.explorer-card[aria-label="Close"]')
    expect(card.locator(".explorer-sync")).to_be_visible(timeout=20000)
    card.get_by_role("button", name="Close: more").click()
    card.get_by_role("menuitem", name="Pull").click()
    expect(card.locator(".explorer-sync")).to_have_text("Conflicts: 1", timeout=20000)
    assert (shared / "Close" / "plan.md.theirs").read_text() == "alpha\ntheirs\n"
    shot(page, "shared-card-conflict")
    call(server, "POST", "/project/open", {"path": str(shared / "Close")})
    page.locator('.nav-rail [data-area="scm"]').click()
    merge = page.locator('.scm-sidebar .monaco-list-row[data-group="merge"][data-path="Close/plan.md"]')
    expect(merge).to_have_attribute("data-letter", "!", timeout=20000)
    merge.click()
    expect(page.locator(".scm-diff-title")).to_contain_text("Yours ↔ Theirs")
    expect(footer.locator(".area-mark")).to_have_text("Conflicts: 1")
    shot(page, "scm-conflict")
    # Resolved and pushed: the mark goes.
    (shared / "Close" / "plan.md").write_text("alpha\nmine and theirs\n")
    (shared / "Close" / "plan.md.theirs").unlink()
    page.locator('.scm-sidebar .pane-header [data-codicon="refresh"]').first.click()
    # Refresh drawn: the file is a change now, no longer a merge change.
    expect(page.locator('.scm-sidebar .monaco-list-row[data-group="merge"]')).to_have_count(0)
    expect(page.locator('.scm-sidebar .monaco-list-row[data-path="Close/plan.md"]')).to_have_count(1)
    box = page.locator('.scm-sidebar textarea[data-which="shared"]')
    box.fill("Resolve the plan")
    # A redraw while typing (a notice, Refresh) keeps the words, the focus and the caret in the box.
    with page.expect_request(lambda r: "/git/history" in r.url):  # asked once the side bar is drawn again
        page.locator('.scm-sidebar .pane-header [data-codicon="refresh"]').first.evaluate("e => e.click()")
    assert box.evaluate("e => e === document.activeElement && e.value === 'Resolve the plan'")
    box.press("Control+Enter")
    # Nothing staged: VS Code's question, then every change is committed.
    page.locator(".scm-dialog").get_by_role("button", name="Yes").click()
    expect(page.locator('.scm-sidebar .monaco-list-row[data-path="Close/plan.md"]')).to_have_count(
        0, timeout=20000
    )
    expect(page.locator(".app-footer .area-mark")).to_have_count(0, timeout=20000)
    assert hub.files(SHARED)["Close/plan.md"] == b"alpha\nmine and theirs\n"
    call(server, "POST", "/project/close", {"discard": True})
    page.context.close()


def test_the_page_in_dark_modern(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "?open=scm", dark=True)
    expect(page.locator(".scm-sidebar")).to_be_visible(timeout=20000)
    expect(page.locator(".scm-history-view .monaco-list-row[data-commit]").first).to_be_visible(timeout=20000)
    background = page.locator(".scm-sidebar").evaluate("e => getComputedStyle(e).backgroundColor")
    assert background in ("rgb(24, 24, 24)", "rgb(248, 248, 248)")
    shot(page, "scm-dark")
    page.context.close()
