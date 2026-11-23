"""Share… in a real browser (shareApp.ts; the owner, 2026-11-21): Share, the install prompt, signing in with a
device code (the stand-in devtunnel: tests/devtunnel_standin.py), the link with Copy and Open, the amber note,
the Shared mark beside where the app runs, then Stop sharing. Its own server in this process, with a made-up
app on a port of its own as the share target. Made-up names only; nothing leaves the computer."""

from __future__ import annotations

import os
import re
import socket
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from swissarmybench.server.app import create_app
from swissarmybench.services.sharing import Opened
from swissarmybench.settings import Settings
from tests.e2e.test_canvas_page import open_canvas
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.live_server import running
from tests.streamlit_helpers import needs_streamlit

SHOTS = os.environ.get("SWISSARMYBENCH_SHARE_SHOTS")


class MadeUpApp:
    def __init__(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = int(probe.getsockname()[1])
        self.closed: list[str] = []

    async def open(self, app: str) -> Opened:
        return Opened(self.port, "Regional sales POC · build 4")

    async def close(self, app: str) -> None:
        self.closed.append(app)


@pytest.fixture(scope="module")
def own_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp: Path = tmp_path_factory.mktemp("share")
    settings = Settings(
        state_dir=tmp / "state",
        export_dir=tmp / "exports",
        workbench_dir=tmp / "home" / "SwissArmyBench",
        projects_dir=tmp / "home" / "Projects",
        auto_load_catalogs=False,
        auto_read_vaults=False,
    )
    made: dict[str, Any] = {}

    def make(port: int) -> Any:
        made["app"] = create_app(port, "share-token", settings)
        return made["app"]

    with running(make) as (port, _server):
        target = MadeUpApp()
        made["app"].state.ctx.hooks.share_targets["streamlit"] = target
        yield {"port": port, "token": "share-token", "target": target}


def test_share_install_sign_in_link_copy_and_stop(browser: Browser, own_server: dict[str, Any]) -> None:  # noqa: F811
    context = browser.new_context(viewport={"width": 1280, "height": 860}, device_scale_factor=2)
    context.grant_permissions(
        ["clipboard-read", "clipboard-write"], origin=f"http://127.0.0.1:{own_server['port']}"
    )
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{own_server['port']}/workspace#token={own_server['token']}")
    page.wait_for_function("() => !!globalThis.sabShare")
    app = "{kind: 'streamlit', id: 'regional-sales', title: 'Regional sales POC'}"
    # Where the app's Launch / Stop shows: the mark, hidden while not shared.
    page.evaluate(
        f"() => {{ const m = sabShare.shareMark({app}); m.id = 'mark'; document.body.prepend(m); }}"
    )
    expect(page.locator("#mark")).to_be_hidden()
    page.evaluate(f"() => sabShare.openShareDialog({app})")
    dialog = page.locator("dialog.share-dialog")
    expect(dialog.locator(".share-sentence")).to_have_text(
        "People in your organization can open this app after signing in with their work account. It runs on "
        "this computer while it is shared."
    )
    expect(dialog.locator(".share-needs")).to_contain_text("Sharing needs devtunnel")
    dialog.locator(".share-install").click()
    # Installed (the stand-in's bytes, their checksum checked): the sign-in, the user's own.
    dialog.locator(".share-device-code").click()
    expect(dialog.locator(".share-code")).to_have_text("MADEUP42")
    expect(dialog.locator(".share-start")).to_be_visible()
    expect(dialog.locator(".share-account")).to_contain_text("dana.lee@contoso-made-up.example")
    dialog.locator(".share-start").click()
    link = dialog.locator(".share-link")
    expect(dialog).to_have_attribute("data-state", "sharing", timeout=20_000)
    url = link.input_value()
    assert url.startswith("https://made-up-") and url.endswith(
        f"-{own_server['target'].port}.usw2.devtunnels.ms/"
    )
    assert f"-{own_server['port']}." not in url  # never the server's own port
    expect(dialog.locator(".share-who")).to_have_text("Your organization")
    expect(dialog.locator(".share-note")).to_have_text(
        "Shared: anyone in your organization with the link can use this app. Its queries run on this "
        "computer with your connections."
    )
    expect(dialog.locator(".share-open")).to_be_visible()
    dialog.locator(".share-copy").click()
    assert page.evaluate("() => navigator.clipboard.readText()") == url
    expect(page.locator("#mark")).to_be_visible()
    expect(page.locator("#mark .share-mark-label")).to_have_attribute(
        "title", f"Shared with your organization: {url}"
    )
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(400)
        dialog.screenshot(path=str(Path(SHOTS) / "share-dialog-sharing.png"))
        page.screenshot(path=str(Path(SHOTS) / "share-dialog-page.png"))
    dialog.locator(".share-stop").click()
    expect(dialog).to_have_attribute("data-state", "ready")
    expect(page.locator("#mark")).to_be_hidden()
    assert own_server["target"].closed == ["regional-sales"]
    context.close()


@needs_streamlit
def test_share_a_launched_canvas_app_from_plays_menu(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    tmp_path: Path,
) -> None:
    """The new Canvas: Launch, then Play's ▾ has Share…; the link's port is a shared run of the launch at
    the root of its own 127.0.0.1 port (never the server's); the Shared mark beside Play; the launch's stop
    ends it."""
    project = tmp_path / "shop"
    project.mkdir()
    made = call(server, "POST", "/streamlit/canvases", {"name": "Regional sales", "folder": str(project)})
    canvas = made["canvas"]
    page = open_canvas(browser, server, Path(made["path"]))
    with page.context.expect_page(timeout=180_000):
        page.locator(".cvs-top .cvs-play-more").click()
        page.locator(".cvs-menu .cvs-menu-item").filter(has=page.get_by_text("Launch", exact=True)).click()
    expect(page.locator(".cvs-top .cvs-play")).to_have_text("Stop", timeout=180_000)
    page.bring_to_front()
    page.locator(".cvs-top .cvs-play-more").click()
    items = page.locator(".cvs-menu .cvs-menu-item")
    # While launched: Stop, the Performance Analyzer, Share…, Builds… (the canvas-rest2 branch's merge).
    expect(items).to_have_count(4)
    share = items.filter(has_text="Share…")
    expect(share).to_have_count(1)
    share.click()
    dialog = page.locator("dialog.share-dialog")
    expect(dialog.locator("h2")).to_have_text("Share regional_sales")
    # The dialog draws its state once devtunnel's status answers: Install now, a sign-in, or Share. Wait for
    # one of them before choosing (a slow machine's status came after a look that saw none of them).
    ready = dialog.locator(".share-install, .share-device-code, .share-start")
    expect(ready.first).to_be_visible(timeout=20_000)
    if dialog.locator(".share-install").is_visible():
        dialog.locator(".share-install").click()
    # Signed in already when the test before it signed in to the same stand-in (its sign-in is devtunnel's,
    # kept beside it): then Share comes straight away, as it does for a person who signed in earlier.
    signed_in_or_not = dialog.locator(".share-device-code, .share-start")
    expect(signed_in_or_not.first).to_be_visible(timeout=20_000)
    if dialog.locator(".share-device-code").is_visible():
        dialog.locator(".share-device-code").click()
    expect(dialog.locator(".share-start")).to_be_visible(timeout=20_000)
    dialog.locator(".share-start").click()
    expect(dialog).to_have_attribute("data-state", "sharing", timeout=120_000)
    url = dialog.locator(".share-link").input_value()
    port = int(re.search(r"-(\d+)\.usw2\.devtunnels\.ms/$", url).group(1))  # type: ignore[union-attr]
    assert port != server["port"]
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=10) as answer:
        assert answer.status == 200  # a Streamlit at the root of its own port: the shared run
    page.keyboard.press("Escape")
    expect(page.locator(".cvs-top .cvs-share .share-mark")).to_be_visible()
    if SHOTS:
        page.wait_for_timeout(400)
        page.locator(".cvs-top").screenshot(path=str(Path(SHOTS) / "canvas-shared-mark.png"))
    # The launch's stop ends the share: the link ends with its app.
    page.locator(".cvs-top .cvs-play").click()
    expect(page.locator(".cvs-top .cvs-share .share-mark")).to_be_hidden(timeout=20_000)
    assert call(server, "GET", f"/sharing?kind=streamlit&app={canvas}")["shares"] == []
    page.context.close()
