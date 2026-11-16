# ruff: noqa: F811
"""Launch Claude in a real browser (the owner, 2026-11-16: "a launch claude command on the home page in the
bottom footer use a claude icon"; "with a setting in the settings go launch it with bypass permissions";
"checks the machine for the installed claude desktop app and launch it the same way"): the button in the
home page's and the Workbench's status bars with its icon, a click that opens the terminal (a stand-in
records it: no terminal opens), the menu when both Claudes are found, the plain message when none is,
the one question before Claude Desktop's config is written, and Settings' Claude. Made-up data only.

With SWISSARMYBENCH_CLAUDE_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_CLAUDE_SHOTS")


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("claude-e2e")
    standin = tmp / "claude-standin.json"
    standin.write_text("{}")
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_CLAUDE_STANDIN": str(standin),
    }
    saved = {key: os.environ.get(key) for key in ("SWISSARMYBENCH_INFO", "SWISSARMYBENCH_STATE")}
    for key in saved:
        os.environ[key] = env[key]
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    for _ in range(150):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    else:
        process.kill()
        raise AssertionError("server did not start")
    yield info | {"tmp": tmp, "standin": standin}
    process.terminate()
    process.wait(timeout=20)
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def found(server: dict[str, Any], installs: list[dict[str, Any]]) -> Path:
    """What the stand-in finds from now on (each test says its own), and its launches cleared."""
    server["standin"].write_text(
        json.dumps(
            {
                "platform": "linux",
                "installs": installs,
                "terminals": {"gnome-terminal": "/usr/bin/gnome-terminal"},
            }
        )
    )
    launches = server["standin"].with_suffix(".launches.jsonl")
    launches.unlink(missing_ok=True)
    return launches


def launches(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def home(browser: Browser, server: dict[str, Any]) -> Page:
    push_client.push(
        pd.DataFrame({"orchard": ["North", "South"], "plums": [14, 9]}), name="claude_plums", new_grid=True
    )
    page = browser.new_context(
        viewport={"width": 1400, "height": 820}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace#token={server['token']}")
    expect(page.locator(".statusbar .claude-launch")).to_be_visible(timeout=20000)
    return page


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def test_the_footer_button_opens_claude_code_in_a_terminal(browser: Browser, server: dict[str, Any]) -> None:
    record = found(server, [{"kind": "code", "path": "/usr/local/bin/claude"}])
    page = home(browser, server)
    launch = page.locator(".statusbar .claude-launch")
    expect(launch).to_have_text("Launch Claude")
    expect(launch.locator("svg[data-icon='claude']")).to_be_attached()
    shot(page, "footer")
    launch.click()
    expect(page.locator(".toast").filter(has_text="Claude Code started in gnome-terminal")).to_be_visible()
    (opened,) = launches(record)
    folder = server["tmp"] / "state" / "claude" / "no-project"
    assert opened["argv"] == [
        "/usr/bin/gnome-terminal",
        f"--working-directory={folder}",
        "--",
        "/usr/local/bin/claude",
    ]
    text = (folder / "CLAUDE.md").read_text()
    assert "`claude_plums`" in text and "North" not in text
    page.context.close()


def test_both_found_is_a_small_menu(browser: Browser, server: dict[str, Any]) -> None:
    config = server["tmp"] / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir(exist_ok=True)
    config.write_text(json.dumps({"mcpServers": {"notes": {"command": "notes-mcp"}}}))
    record = found(
        server,
        [
            {"kind": "code", "path": "/usr/local/bin/claude"},
            {"kind": "desktop", "path": "/opt/Claude/claude", "name": "Claude", "config": str(config)},
        ],
    )
    page = home(browser, server)
    page.evaluate("fetch('/claude?refresh=1')")
    page.locator(".statusbar .claude-launch").click()
    menu = page.locator(".context-menu[aria-label='Launch Claude']")
    expect(menu).to_be_visible()
    shot(page, "menu")
    menu.get_by_text("Claude Desktop").click()
    # Asked once before another app's config file is written.
    dialog = page.locator("dialog.claude-confirm")
    expect(dialog).to_be_visible()
    expect(dialog.locator(".claude-config-path")).to_have_text(str(config))
    shot(page, "desktop-question")
    assert launches(record) == []
    dialog.get_by_role("button", name="Add and start").click()
    expect(page.locator(".toast").filter(has_text="Claude Desktop started")).to_be_visible()
    assert launches(record)[-1]["argv"] == ["/opt/Claude/claude"]
    data = json.loads(config.read_text())
    assert data["mcpServers"]["notes"] == {"command": "notes-mcp"} and "swissarmybench" in data["mcpServers"]
    page.context.close()


def test_none_found_says_how_to_install(browser: Browser, server: dict[str, Any]) -> None:
    record = found(server, [])
    page = home(browser, server)
    page.evaluate("fetch('/claude?refresh=1')")
    page.locator(".statusbar .claude-launch").click()
    dialog = page.locator("dialog.claude-missing")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2")).to_have_text("Claude is not installed")
    expect(dialog.locator(".claude-help[data-kind='code'] code").first).to_have_text(
        "curl -fsSL https://claude.ai/install.sh | bash"
    )
    expect(dialog.locator(".claude-help[data-kind='desktop'] a")).to_have_attribute(
        "href", "https://claude.ai/download"
    )
    expect(dialog.get_by_role("button", name="Choose its file…")).to_be_visible()
    shot(page, "missing")
    assert launches(record) == []
    page.context.close()


def test_settings_lists_what_was_found_and_the_bypass_switch(
    browser: Browser, server: dict[str, Any]
) -> None:
    record = found(
        server,
        [
            {"kind": "code", "path": "/usr/local/bin/claude", "source": "PATH"},
            {"kind": "code", "path": "/home/pat/.claude/local/claude", "source": "Claude Code's own folder"},
        ],
    )
    page = home(browser, server)
    page.evaluate("fetch('/claude?refresh=1')")
    page.locator(".nav-rail [data-area='settings']").click()
    section = page.locator(".claude-fieldset")
    expect(section).to_be_visible()
    choice = section.locator("select[data-kind='code']")
    expect(choice.locator("option")).to_have_count(2)
    choice.select_option("/home/pat/.claude/local/claude")
    section.locator(".claude-bypass").check()
    expect(section.locator(".claude-bypass")).to_be_checked()
    section.scroll_into_view_if_needed()
    shot(page, "settings")
    page.go_back()
    page.locator(".statusbar .claude-launch").click()
    expect(page.locator(".toast").filter(has_text="bypass permissions")).to_be_visible()
    argv = launches(record)[-1]["argv"]
    assert argv[3] == "/home/pat/.claude/local/claude" and argv[-1] == "--dangerously-skip-permissions"
    page.context.close()


def test_the_workbench_status_bar_has_it_too(browser: Browser, server: dict[str, Any]) -> None:
    found(server, [{"kind": "code", "path": "/usr/local/bin/claude"}])
    page = browser.new_context(viewport={"width": 1400, "height": 820}).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
    expect(page.locator(".claude-launch")).to_be_visible(timeout=20000)
    expect(page.locator(".claude-launch svg[data-icon='claude']")).to_be_attached()
    page.context.close()
