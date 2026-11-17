# ruff: noqa: F811
"""The Power Apps extension's Code App page in a real browser, with the Power Platform tools stood in by the
recorded fakes (tests/powerapps_fakes.py) and the environment's connectivity service by a made-up stand-in:
the rail's Code App area only while the extension is on, New code app, its sources and generated files, a
generated service in the Workbench's TypeScript editor, the connectors and one's operations, Run live in its
pane, Push, a custom connector's dry run, the runs; the code app mode in the Workbench (New makes a
TypeScript file, the TypeScript and TSX cells offered as coming) and the blade families. Made-up data only.

With SWISSARMYBENCH_CODEAPP_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests import powerapps_fakes as fakes
from tests.e2e.test_ui import browser, call  # noqa: F401
from tests.test_powerapps_rules import OPENAPI

SHOTS = os.environ.get("SWISSARMYBENCH_CODEAPP_SHOTS")
ROOT = Path(__file__).resolve().parents[2]


def start(
    tmp: Path, extensions: str, tools: Path | None = None, api: str = ""
) -> tuple[subprocess.Popen[bytes], dict[str, Any]]:
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_EXTENSIONS": extensions,
        "PYTHONPATH": os.pathsep.join([str(ROOT / "extensions" / "powerapps" / "src"), str(ROOT / "src")]),
        "SWISSARMYBENCH_POWERPLATFORM_API": api,
        "SWISSARMYBENCH_NO_BROWSER": "1",
    }
    if tools is not None:
        env["PATH"] = str(tools) + os.pathsep + os.environ.get("PATH", "")
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    for _ in range(200):
        try:
            return process, json.loads((tmp / "server.json").read_text())
        except (OSError, ValueError):
            time.sleep(0.1)
    process.kill()
    raise AssertionError("server did not start")


@pytest.fixture(scope="module")
def connectivity() -> Iterator[str]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            swagger = fakes.tasks_swagger() | {"info": {"title": "Northwind Orders", "version": "1.0"}}
            body = json.dumps(
                {"properties": {"displayName": "Northwind Orders", "swagger": swagger}}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory, connectivity: str) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("codeapp-e2e")
    tools = fakes.install(tmp / "fake-tools")
    process, info = start(tmp, "powerapps", tools, connectivity)
    (tmp / "apps").mkdir()
    yield info | {"tmp": tmp, "tools": tools}
    process.terminate()
    process.wait(timeout=20)


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def new_page(browser: Browser, info: dict[str, Any], path: str = "/workspace?open=codeapp") -> Page:
    page = browser.new_context(
        viewport={"width": 1440, "height": 900}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    page.goto(f"http://127.0.0.1:{info['port']}{path}#token={info['token']}")
    return page


def test_off_the_rail_has_no_code_app_area(browser: Browser, tmp_path: Path) -> None:
    process, info = start(tmp_path, "-powerapps")
    try:
        page = new_page(browser, info, "/workspace")
        expect(page.locator(".nav-rail-item[data-area='apis']")).to_be_visible(timeout=20000)
        page.wait_for_timeout(500)
        expect(page.locator(".nav-rail-item[data-area='codeapp']")).to_be_hidden()
    finally:
        process.terminate()
        process.wait(timeout=20)


def test_the_code_app_page_from_new_app_to_push(browser: Browser, server: dict[str, Any]) -> None:
    page = new_page(browser, server)
    area = page.locator(".nav-rail-item[data-area='codeapp']")
    expect(area).to_be_visible(timeout=20000)
    expect(area).to_have_attribute("aria-current", "page")
    expect(page.locator(".ca-tool[data-tool='pa']")).to_contain_text("1.4.2")
    expect(page.locator(".ca-tool[data-tool='deno']")).to_contain_text("phase 2")
    shot(page, "codeapp-empty")
    # New code app: its name, its environment (pac env list), its folder.
    page.locator(".ca-new").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("The app's name").fill("Expense Tracker")
    expect(dialog.get_by_label("The environment", exact=True)).to_contain_text("Contoso (default)")
    dialog.get_by_label("The folder it goes in").evaluate(
        "(el, v) => { el.removeAttribute('readonly'); el.value = v; }", str(server["tmp"] / "apps")
    )
    shot(page, "codeapp-new")
    dialog.locator(".ca-make").click()
    expect(page.locator(".area-page-title")).to_contain_text("Expense Tracker", timeout=30000)
    expect(page.locator(".ca-env")).to_contain_text("Contoso (default)")
    # A Dataverse table as a data source; its generated model and service listed.
    page.locator(".ca-add-table").click()
    page.locator("dialog[open]").get_by_label("The table's logical name").fill("account")
    page.locator("dialog[open]").get_by_role("button", name="Add").click()
    expect(page.locator(".ca-sources tr[data-source='accounts']")).to_be_visible(timeout=20000)
    expect(
        page.locator(".ca-generated .ca-file[data-path='src/generated/services/AccountsService.ts']")
    ).to_be_visible()
    page.locator(".ca-tree details.ca-folder").first.wait_for()
    shot(page, "codeapp-project")

    # The connectors, one explored as the APIs explorer draws an API, then added to the app.
    page.locator(".ca-tab[data-tab='connectors']").click()
    expect(page.locator(".ca-connector")).to_have_count(3, timeout=20000)
    page.locator(".ca-search").fill("tasks")
    expect(page.locator(".ca-connector")).to_have_count(1)
    page.locator(".ca-connector .ca-add-connector").click()
    add = page.locator("dialog[open]")
    expect(add.get_by_label("Its connection")).to_contain_text(fakes.ACCOUNT)
    add.locator(".ca-add").click()
    expect(page.locator("dialog[open]")).to_have_count(0, timeout=20000)
    page.locator(".ca-connector[data-connector='shared_contosotasks'] .api-card-open").click()
    expect(page.locator(".api-op[data-operation='ListTasks']")).to_be_visible(timeout=20000)
    expect(page.locator(".api-op[data-operation='Ping']")).to_have_count(0)  # internal: left out
    expect(page.locator(".ca-method")).to_contain_text("ContosotasksService.ListTasks")
    shot(page, "codeapp-connector")
    # One the app does not have: read from the environment's connectivity service.
    page.locator(".ca-tab[data-tab='connectors']").click()
    page.locator(".ca-connector[data-connector='shared_northwindorders'] .api-card-open").click()
    expect(page.locator(".ca-section-head")).to_contain_text(
        "the environment's connectivity service", timeout=20000
    )

    # Run live: the dev server in its pane, through this server; Local Play for the browser.
    page.locator(".ca-tab[data-tab='live']").click()
    page.locator(".ca-run-live").click()
    frame = page.frame_locator(".ca-live-frame")
    expect(frame.locator("h1")).to_have_text("Expense Tracker", timeout=30000)
    play = page.locator(".ca-play").get_attribute("data-href") or ""
    assert play.startswith(
        f"https://make.powerapps.com/play/e/{fakes.ENVIRONMENT_ID}/app/local?_localAppUrl=http://localhost:"
    )
    assert "/powerapps/live/" in play
    shot(page, "codeapp-run-live")
    page.locator(".ca-stop").click()
    expect(page.locator(".ca-live-empty")).to_be_visible(timeout=20000)

    # Push: what it runs, then the app's link.
    page.locator(".ca-tab[data-tab='push']").click()
    expect(page.locator(".ca-commands")).to_contain_text("pa app push", timeout=20000)
    page.locator(".ca-push-button").click()
    expect(page.locator(".ca-pushed a")).to_have_attribute(
        "href", f"https://apps.powerapps.com/play/e/{fakes.ENVIRONMENT_ID}/a/{fakes.APP_ID}", timeout=30000
    )
    page.locator(".ca-versions").click()
    expect(page.locator(".ca-this")).to_contain_text("Expense Tracker")
    shot(page, "codeapp-push")

    # Runs: each pa, pac and npm run of this session, with its lines.
    page.locator(".ca-tab[data-tab='runs']").click()
    expect(page.locator(".ca-run").filter(has_text="pa app push")).to_have_count(1, timeout=20000)
    page.locator(".ca-run").filter(has_text="pa app push").locator("summary").click()
    expect(page.locator(".ca-run").filter(has_text="pa app push").locator(".ca-output")).to_contain_text(
        "App pushed successfully"
    )
    shot(page, "codeapp-runs")


def test_a_custom_connector_from_an_api(browser: Browser, server: dict[str, Any]) -> None:
    added = call(
        server,
        "POST",
        "/apis",
        {
            "spec": json.dumps(OPENAPI),
            "name": "MadeUpOrders",
            "auth": {"type": "api_key", "in": "header", "name": "X-Orders-Key"},
        },
    )
    assert added
    page = new_page(browser, server)
    expect(page.locator(".ca-tab[data-tab='custom']")).to_be_visible(timeout=20000)
    page.locator(".ca-tab[data-tab='custom']").click()
    page.locator(".ca-dry-run").click()
    expect(page.locator(".ca-file-text")).to_have_count(2, timeout=20000)
    expect(page.locator(".ca-file-text[open] pre")).to_contain_text("securestring")
    shot(page, "codeapp-custom-connector")
    page.locator(".ca-make-connector").click()
    expect(page.locator(".toast").last).to_contain_text("custom connector is made", timeout=20000)
    assert any(c[:3] == ["pac", "connector", "create"] for c in fakes.calls(server["tools"]))


def test_the_workbench_in_the_code_app_mode(browser: Browser, server: dict[str, Any]) -> None:
    project = call(server, "GET", "/powerapps/project")
    if not project["open"]:
        call(
            server,
            "POST",
            "/powerapps/project/new",
            {
                "name": "Mode App",
                "environment_id": fakes.ENVIRONMENT_ID,
                "parent": str(server["tmp"] / "apps"),
            },
        )
    if not any(s["name"] == "accounts" for s in call(server, "GET", "/powerapps/project")["sources"]):
        call(server, "POST", "/powerapps/sources", {"kind": "dataverse", "table": "account"})
    # A generated service in the editor: TypeScript, with Monaco's own language service.
    page = new_page(browser, server, "/workspace")
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}&codefile=src/App.tsx")
    editor = page.locator(".wb-codefile[data-path='src/App.tsx'] .monaco-editor")
    expect(editor).to_be_visible(timeout=30000)
    editor.click()
    page.keyboard.press("Control+End")
    page.keyboard.type('\nconst total: number = "twelve";\n')
    expect(page.locator(".wb-codefile .squiggly-error").first).to_be_attached(timeout=30000)
    shot(page, "codeapp-workbench-typescript")
    page.keyboard.press("Control+s")
    expect(page.locator(".toast").last).to_contain_text("Saved App.tsx", timeout=20000)
    read = call(server, "GET", "/powerapps/project/file?path=src/App.tsx")
    assert 'const total: number = "twelve";' in read["text"]
    # The code app mode: New makes a TypeScript file.
    page.goto(f"http://127.0.0.1:{server['port']}/workbench?kind=script&view=list#token={server['token']}")
    new = page.locator("#wb-top button").filter(has_text="New TypeScript file")
    expect(new).to_be_visible(timeout=20000)
    shot(page, "codeapp-workbench-new-typescript")


def test_the_blades_page_shows_the_modes_families_first(browser: Browser, server: dict[str, Any]) -> None:
    project = call(server, "GET", "/powerapps/project")
    if not project["open"]:
        call(
            server,
            "POST",
            "/powerapps/project/new",
            {
                "name": "Family App",
                "environment_id": fakes.ENVIRONMENT_ID,
                "parent": str(server["tmp"] / "apps"),
            },
        )
    page = new_page(browser, server, "/catalog")
    families = page.locator(".starter-family-row")
    expect(families.first).to_be_visible(timeout=20000)
    expect(families).to_have_count(3)
    assert [families.nth(i).get_attribute("data-family") for i in range(3)] == [
        "TypeScript",
        "React",
        "Connectors",
    ]
    expect(page.locator(".starter-item[data-starter='React rows table']")).to_be_visible()
    shot(page, "codeapp-blades")
    page.locator(".starter-every").click()
    expect(page.locator(".starter-family-row[data-family='Excel']")).to_be_visible()
    # Closed, the base's mode: every family as before.
    call(server, "POST", "/powerapps/project/close", {})
    page.reload()
    expect(page.locator(".starter-family-row[data-family='Excel']")).to_be_visible(timeout=20000)
    expect(page.locator(".starter-every")).to_have_count(0)
