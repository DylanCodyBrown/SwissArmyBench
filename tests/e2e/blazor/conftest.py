"""The Blazor front end's browser tests (blazor/): a real server per module with its own state folder and
made-up data only, and Chromium driven by Playwright. Skipped when the Blazor front end is not built here
(`python blazor/publish.py` writes blazor/publish/wwwroot; a wheel carries swissarmybench/web_blazor)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

from swissarmybench.settings import Settings

# The Chromium these tests drive (not the classic suite's Edge).
CHROMIUM = os.environ.get("SAB_CHROMIUM", "/opt/pw-browsers/chromium")
# The Blazor app's first load (its .NET runtime) is slower than a classic page's.
FIRST_LOAD_MS = 60_000

if not (Settings().blazor_root / "index.html").is_file():
    pytest.skip("The Blazor front end is not built here (python blazor/publish.py).", allow_module_level=True)


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """A server of its own: its state, projects and Workbench folders in a temporary folder."""
    tmp = tmp_path_factory.mktemp("blazor")
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(tmp / "projects"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "workbench"),
        "SWISSARMYBENCH_NO_BROWSER": "1",
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
    # This branch's server, not another checkout's installed one (run the tests with
    # PYTHONPATH=<checkout>/src): only this branch answers GET /app/frontend and serves /blazor/.
    assert call(info, "GET", "/app/frontend")["frontend"] == "classic", "a server without the Blazor switch"
    yield info | {"tmp": tmp}
    process.terminate()
    process.wait(timeout=20)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        launched = playwright.chromium.launch(executable_path=CHROMIUM)
        yield launched
        launched.close()


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


@pytest.fixture
def page_errors() -> list[str]:
    """The page's own errors (an exception in its C# shows #blazor-error-ui), collected by each test."""
    return []
