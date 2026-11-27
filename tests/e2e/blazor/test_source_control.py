"""The Blazor Source Control page (the Git extension's), against GitHub stood in for on 127.0.0.1
(tests/github_standin.py; real GitHub is never reached), made-up files only: signed out, VS Code's welcome
and a token's sign-in; Connect Folder to Repository through the quick picks; a change's letter, Stage
Changes, Monaco's diff editor with the files beside it and Inline View; More Actions... with the greyed-out
commands that need a local Git; Commit with Ctrl+Enter (GitHub gets the commit); the graph's rows and a
commit's files; Discard Changes asked in VS Code's words."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import FIRST_LOAD_MS
from tests.github_standin import TOKEN, GitHubStandin

ROOT = Path(__file__).resolve().parents[3]
REPO = "made-up-team/meta-store"


@pytest.fixture(scope="module")
def hub() -> Iterator[GitHubStandin]:
    with GitHubStandin() as standin:
        standin.repository(
            REPO, {"README.md": b"# Meta store\n", ".gitignore": b"local/\n", "notes/close.md": b"one\ntwo\n"}
        )
        standin.teammate(REPO, {"notes/q3.md": b"Q3 close\n"}, "Add the Q3 note")
        yield standin


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory, hub: GitHubStandin) -> Iterator[dict[str, Any]]:
    """A server of its own with the Git extension on and GitHub stood in for."""
    tmp = tmp_path_factory.mktemp("blazor-scm")
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(tmp / "projects"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "workbench"),
        "SWISSARMYBENCH_NO_BROWSER": "1",
        "SWISSARMYBENCH_SYSTEM_DIALOGS": "off",
        "SWISSARMYBENCH_PROJECT_VENV": "off",
        "SWISSARMYBENCH_GITHUB_API": hub.url,
        "SWISSARMYBENCH_GITHUB_WEB": hub.url,
        "PYTHON_KEYRING_BACKEND": "tests.file_keyring.FileKeyring",
        "SAB_TEST_KEYRING_FILE": str(tmp / "keyring.json"),
        "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "src")]),
    }
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    info: dict[str, Any] | None = None
    for _ in range(300):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    assert info is not None, "the server did not start"
    yield info | {"tmp": tmp}
    process.terminate()
    process.wait(timeout=20)


def open_scm(browser: Browser, server: dict[str, Any]) -> Page:
    page = browser.new_page(viewport={"width": 1500, "height": 900})
    page.set_default_timeout(15_000)
    page.goto(f"http://127.0.0.1:{server['port']}/blazor/x-scm#token={server['token']}")
    page.wait_for_selector(".scm-sidebar", timeout=FIRST_LOAD_MS)
    return page


def pick(page: Page, words: str) -> None:
    page.locator(".scm-quick-input .quick-input-list-entry", has_text=words).first.dispatch_event("mousedown")


def test_sign_in_connect_stage_diff_commit_and_the_graph(
    browser: Browser, server: dict[str, Any], hub: GitHubStandin
) -> None:
    library = server["tmp"] / "state" / "library"
    library.mkdir(parents=True, exist_ok=True)
    (library / "notes").mkdir(exist_ok=True)
    (library / "notes" / "plan.md").write_text("A made-up plan\n")
    page = open_scm(browser, server)
    view = page.locator(".scm-sidebar")
    expect(view.locator(".welcome-view-content")).to_contain_text("In order to use Git features")
    expect(view.locator(".scm-token-steps li").first).to_be_visible()
    view.locator(".scm-token").fill(TOKEN)
    view.get_by_role("button", name="Use Token").click()
    expect(view.locator(".welcome-view-content")).to_contain_text("Signed in to GitHub as made-up-analyst")

    view.get_by_role("button", name="Connect Folder to Repository").click()
    pick(page, "Team library folder")
    pick(page, REPO)
    rows = view.locator(".monaco-list-row[data-path]")
    expect(rows.first).to_be_visible(timeout=20_000)
    # Pulled first (GitHub's files come here: the folder has never been synced).
    view.hover()
    view.locator('[data-pane="graph"] [data-codicon="repo-pull"]').click()
    expect(view.locator('.monaco-list-row[data-path="README.md"]')).to_have_count(0, timeout=20_000)
    readme = view.locator('.monaco-list-row[data-path="notes/plan.md"]')
    expect(readme).to_have_attribute("data-letter", "U")  # only here: untracked
    expect(view.locator("textarea.scm-input-box")).to_have_attribute(
        "placeholder", 'Message (Ctrl+Enter to commit on "main")'
    )

    readme.hover()
    readme.get_by_role("button", name="Stage Changes").click()
    staged = view.locator('.monaco-list-row[data-group="index"][data-path="notes/plan.md"]')
    expect(staged).to_be_visible()
    expect(view.locator('[data-group="index"].monaco-list-row .resource-group .name')).to_have_text(
        "Staged Changes"
    )
    staged.click()
    expect(page.locator(".scm-editor-part .monaco-diff-editor")).to_be_visible(timeout=20_000)
    expect(page.locator(".scm-diff-title")).to_contain_text("plan.md")
    expect(page.locator(".scm-diff-files .monaco-list-row.selected")).to_have_attribute(
        "data-diff-file", "notes/plan.md"
    )
    page.locator('.scm-editor-part [data-codicon="ellipsis"]').click()
    page.locator(".scm-context-view").get_by_role("menuitem", name="Inline View").click()
    expect(page.locator(".scm-editor-part .monaco-diff-editor.side-by-side")).to_have_count(0)

    view.hover()
    view.locator('[data-pane="scm"] [data-codicon="ellipsis"]').click()
    menu = page.locator(".scm-context-view").first
    menu.locator(".action-menu-item[aria-haspopup=true]", has_text="Commit").first.hover()
    expect(
        page.locator(".scm-context-view .action-menu-item.disabled", has_text="Commit (Amend)").first
    ).to_be_visible()
    page.keyboard.press("Escape")

    box = view.locator("textarea.scm-input-box")
    box.fill("Add the made-up plan")
    box.press("Control+Enter")
    expect(view.locator('.monaco-list-row[data-group="index"]')).to_have_count(0, timeout=20_000)
    assert hub.commits[hub.head(REPO)]["message"] == "Add the made-up plan"

    graph = view.locator(".scm-history-view")
    commits = graph.locator(".monaco-list-row[data-commit]")
    expect(commits.first.locator(".label-name")).to_have_text("Add the made-up plan", timeout=20_000)
    expect(commits.first.locator("svg.graph circle")).to_have_count(2)  # HEAD: a ring
    commits.first.click()
    changed = graph.locator('.monaco-list-row[data-commit-file="notes/plan.md"]')
    expect(changed).to_be_visible()
    changed.click()
    expect(page.locator(".scm-diff-title")).to_contain_text("plan.md")

    (library / "notes" / "new.md").write_text("A made-up note\n")
    view.locator('[data-pane="scm"] [data-codicon="refresh"]').click()
    fresh = view.locator('.monaco-list-row[data-path="notes/new.md"]')
    fresh.hover()
    fresh.get_by_role("button", name="Discard Changes").click()
    expect(page.locator(".scm-dialog .dialog-message")).to_contain_text(
        "Are you sure you want to DELETE new.md?"
    )
    page.locator(".scm-dialog").get_by_role("button", name="Cancel").click()
    expect(page.locator(".scm-dialog")).to_have_count(0)
    page.close()
