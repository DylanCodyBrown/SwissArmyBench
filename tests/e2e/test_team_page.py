# ruff: noqa: F811, E501
"""Settings' Team box in a real browser (the owner, 2026-11-19: "you have made linking a meta store and shared
project folder way too difficult; the settings menu makes no sense"), against GitHub stood in for on 127.0.0.1
(tests/github_standin.py; real GitHub is never reached): one Team box (no Meta store folder, Projects folders or
GitHub section); without GitHub sync, Join a team… starts at its Install; a step kept over Install's restart
opens Settings on the flow again; Join walks Sign in with GitHub (the device flow), the repository (search), the
local copy and Set up this computer; the Joined row's words, Push and Pull; the Advanced fold; Leave; Start a
team (a token, the owner and name, the repository made). Made-up data only.

With SWISSARMYBENCH_TEAM_SHOTS set to a folder, the tests also save screenshots there (2x, light and dark)."""

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

from tests.e2e.test_ui import browser, call  # noqa: F401
from tests.github_standin import TOKEN, GitHubStandin

SHOTS = os.environ.get("SWISSARMYBENCH_TEAM_SHOTS")
ROOT = Path(__file__).resolve().parents[2]
TEAM = "made-up-team/team-library"
CONNECTION = (
    b'# /// swissarmybench-blade\n# format = 1\n# name = "Warehouse"\n# kind = "sql"\n# template = "sqlite"\n'
    b'# dialect = "sqlite"\n# ///\nimport sqlite3\nconn = sqlite3.connect(":memory:")\n'
)
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
        "SWISSARMYBENCH_GITHUB_CLIENT_ID": "made-up-client-id",
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
        standin.repository("made-up-team/old-notes", {"README.md": b"# Old notes\n"})
        standin.repository("made-up-analyst/scratch", {"README.md": b"# Scratch\n"})
        standin.repository(
            TEAM,
            {
                "README.md": b"# Team library\n",
                ".gitignore": b"local/\n.sab/data/\n",
                "connections/Warehouse.blade.py": CONNECTION,
                "variables.toml": b'format = 1\n\n[variables.SHOP_TOKEN]\nfrom = "keyring"\n',
                "projects/Close/.sab/project.json": MANIFEST,
                "projects/Close/plan.md": b"alpha\nbeta\n",
            },
        )
        yield standin


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory, hub: GitHubStandin) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("team-e2e")
    process, info = start(tmp, "streamlit," + "g" + "it", hub)
    yield info | {"tmp": tmp}
    process.terminate()
    process.wait(timeout=20)


def shot(page: Page, name: str, element: Any = None) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        (element or page).screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def open_page(browser: Browser, server: dict[str, Any], dark: bool = False) -> Page:
    context = browser.new_context(
        viewport={"width": 1300, "height": 900},
        device_scale_factor=2,
        color_scheme="dark" if dark else "light",
    )
    # Sign in with GitHub opens github.com: never reached from a test.
    context.route("https://github.com/**", lambda route: route.abort())
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace#token={server['token']}")
    expect(page.locator(".nav-rail")).to_be_visible(timeout=20000)
    return page


def settings(page: Page) -> Any:
    page.locator('.nav-rail [data-area="settings"]').click()
    box = page.locator(".team-fieldset")
    expect(box).to_be_visible()
    return box


def test_one_team_box_and_join_starts_at_installing_github_sync(browser: Browser, tmp_path: Path) -> None:
    process, info = start(tmp_path, "streamlit", None)
    try:
        for dark in (False, True):
            page = open_page(browser, info, dark)
            box = settings(page)
            legends = page.locator(".settings-page legend").all_inner_texts()
            assert "Team" in legends and legends.index("Team") == 1  # first after Theme
            assert not {"Meta store folder", "Projects folders", "GitHub"} & set(legends)
            expect(box.locator(".team-none")).to_have_text(
                "Share connections, variables and projects with your team."
            )
            expect(box.get_by_role("button", name="Join a team…")).to_be_visible()
            expect(box.get_by_role("button", name="Start a team…")).to_be_visible()
            expect(box.locator(".team-local-projects")).to_contain_text("New projects go in")
            expect(box.locator(".team-advanced")).not_to_have_attribute("open", "")
            expect(box.locator(".team-advanced .library-row")).not_to_be_visible()
            theme = "dark" if dark else "light"
            shot(page, f"team-box-no-team-{theme}", box)
            box.get_by_role("button", name="Join a team…").click()
            flow = page.locator("dialog.team-flow")
            expect(flow).to_have_attribute("data-step", "install")
            expect(flow.locator(".team-step-title")).to_have_text("Joining a team needs GitHub sync")
            expect(flow.locator(".team-step-name.current")).to_have_text("1GitHub sync")
            shot(page, f"team-join-install-{theme}", flow)
            # A development checkout cannot install: it says what to run, and nothing is kept for a restart.
            flow.get_by_role("button", name="Install").click()
            expect(flow.locator(".team-install-error")).to_be_visible(timeout=10000)
            assert call(info, "GET", "/team")["pending"] is None
            page.context.close()
    finally:
        process.terminate()
        process.wait(timeout=20)


def test_a_step_kept_over_the_restart_opens_settings_on_the_flow(
    browser: Browser, tmp_path: Path, hub: GitHubStandin
) -> None:
    process, info = start(tmp_path, "streamlit", None)
    try:
        call(info, "POST", "/team/pending", {"action": "join"})
    finally:
        process.terminate()
        process.wait(timeout=20)
    (tmp_path / "server.json").unlink()
    # The app comes back with GitHub sync installed: Settings opens on its own and the flow goes on.
    process, info = start(tmp_path, "streamlit," + "g" + "it", hub)
    try:
        page = open_page(browser, info)
        flow = page.locator("dialog.team-flow")
        expect(flow).to_have_attribute("data-step", "sign_in", timeout=20000)
        expect(page.locator(".team-fieldset")).to_be_attached()
        expect(flow.locator(".team-step-name.done")).to_have_text(["GitHub sync"])
        page.context.close()
    finally:
        process.terminate()
        process.wait(timeout=20)


def test_join_walks_its_steps_then_the_joined_row(
    browser: Browser, server: dict[str, Any], hub: GitHubStandin
) -> None:
    page = open_page(browser, server)
    box = settings(page)
    box.get_by_role("button", name="Join a team…").click()
    flow = page.locator("dialog.team-flow")
    expect(flow).to_have_attribute("data-step", "sign_in", timeout=20000)
    shot(page, "team-join-sign-in-light", flow)
    # Sign in with GitHub: the code shown; typed on GitHub (stood in for), the flow goes on.
    flow.get_by_role("button", name="Sign in with GitHub").click()
    expect(flow.locator(".team-device-code")).to_contain_text("WDJB-MJHT")
    shot(page, "team-join-device-code-light", flow)
    hub.device_ready = True
    expect(flow).to_have_attribute("data-step", "pick", timeout=20000)
    expect(flow.locator(".team-repo")).to_have_count(3)
    # Newest first: the team's repository was made last.
    expect(flow.locator(".team-repo").first).to_have_attribute("data-repository", TEAM)
    flow.locator(".team-search").fill("old")
    expect(flow.locator(".team-repo")).to_have_count(1)
    flow.locator(".team-search").fill("team lib")
    expect(flow.locator(".team-repo")).to_have_count(1)
    shot(page, "team-join-pick-light", flow)
    flow.locator(f'.team-repo[data-repository="{TEAM}"]').click()
    expect(flow).to_have_attribute("data-step", "setup", timeout=30000)
    expect(flow.locator(".team-joined-title")).to_have_text(f"Team: {TEAM}")
    expect(flow.locator(".setup-heading")).to_contain_text("Set up this computer", timeout=30000)
    expect(flow.locator(".setup-item", has_text="SHOP_TOKEN")).to_be_visible()
    shot(page, "team-join-setup-light", flow)
    flow.get_by_role("button", name="Done").click()
    expect(flow).to_have_count(0)

    # The Joined row: no words while up to date.
    row = box.locator(".team-joined")
    expect(row).to_contain_text(f"Team: {TEAM}")
    expect(row.locator(".team-sync")).to_have_count(0)
    copy = Path(call(server, "GET", "/team")["team"]["folder"])
    assert copy.name == "made-up-team-team-library" and copy.parent.name == "team"
    # A change here: the row says so; Push sends it and the words go.
    (copy / "projects" / "Close" / "plan.md").write_text("alpha\nbeta\ngamma\n")
    page.locator('.nav-rail [data-area="session"]').click()
    box = settings(page)
    row = box.locator(".team-joined")
    expect(row.locator(".team-sync")).to_contain_text("to push", timeout=20000)
    library = next(f for f in call(server, "GET", "/git")["folders"] if f["which"] == "library")
    assert "projects/Close/plan.md" in library["changed"]
    shot(page, "team-joined-row-light", box)
    row.get_by_role("button", name="Push").click()
    expect(row.locator(".team-sync")).to_have_count(0, timeout=20000)
    assert hub.files(TEAM)["projects/Close/plan.md"] == b"alpha\nbeta\ngamma\n"
    # A teammate's change: Pull brings it.
    hub.teammate(TEAM, {"projects/Close/plan.md": b"alpha\nbeta\ngamma\ndelta\n"})
    row.get_by_role("button", name="Pull").click()
    expect(page.locator(".toast", has_text="1 file updated")).to_be_visible(timeout=20000)
    assert (copy / "projects" / "Close" / "plan.md").read_text() == "alpha\nbeta\ngamma\ndelta\n"
    # The Advanced fold: the two folders, closed until opened.
    advanced = box.locator(".team-advanced")
    advanced.locator("summary").click()
    expect(advanced.locator(".library-folder-path")).to_have_text(str(copy))
    expect(advanced.locator(".projects-shared")).to_have_text(str(copy / "projects"))
    shot(page, "team-joined-advanced-light", box)
    # The shared project is on the Projects page, marked Shared.
    shared = call(server, "GET", "/projects/explorer")["projects"]
    assert any(c["name"] == "Close" and c["where"] == "shared" for c in shared)
    # "…": its menu; Leave asks first, then the box is back to no team.
    row.get_by_role("button", name="More").click()
    menu = page.locator(".menu.context-menu")
    expect(menu.get_by_role("menuitem")).to_have_text(
        ["Open on GitHub", "Set up this computer", "Show its folder", "Leave the team"]
    )
    shot(page, "team-joined-menu-light")
    menu.get_by_role("menuitem", name="Leave the team").click()
    page.get_by_role("button", name="Leave without a copy").click()
    expect(page.locator(".toast", has_text="Its local copy stays in")).to_be_visible(timeout=20000)
    expect(box.get_by_role("button", name="Join a team…")).to_be_visible()
    assert call(server, "GET", "/library")["is_default"] is True
    page.context.close()


def test_start_a_team_in_dark(browser: Browser, server: dict[str, Any], hub: GitHubStandin) -> None:
    call(server, "POST", "/git/sign-out")
    page = open_page(browser, server, dark=True)
    box = settings(page)
    box.get_by_role("button", name="Start a team…").click()
    flow = page.locator("dialog.team-flow")
    expect(flow).to_have_attribute("data-step", "sign_in", timeout=20000)
    flow.locator(".team-token-part summary").click()
    flow.locator(".team-token").fill(TOKEN)
    shot(page, "team-start-token-dark", flow)
    flow.get_by_role("button", name="Use the token").click()
    expect(flow).to_have_attribute("data-step", "name", timeout=20000)
    expect(flow.locator(".team-owner option")).to_have_text(["made-up-analyst", "made-up-team"])
    flow.locator(".team-owner").select_option("made-up-team")
    flow.locator(".team-name").fill("finance team")
    shot(page, "team-start-name-dark", flow)
    flow.get_by_role("button", name="Start the team").click()
    expect(flow).to_have_attribute("data-step", "setup", timeout=30000)
    expect(flow.locator(".team-joined-title")).to_have_text("Team: made-up-team/finance-team")
    shot(page, "team-start-setup-dark", flow)
    flow.get_by_role("button", name="Done").click()
    assert "made-up-team/finance-team" in hub.created
    there = hub.files("made-up-team/finance-team")
    assert {"README.md", ".gitignore", "projects/README.md"} <= set(there)
    expect(box.locator(".team-joined")).to_contain_text("Team: made-up-team/finance-team")
    shot(page, "team-joined-row-dark", box)
    call(server, "POST", "/team/leave", {"keep": False})
    page.context.close()
