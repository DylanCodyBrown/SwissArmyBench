"""One Python per project (the owner, 2026-11-21; Plans/environment.plan.md, step 4), in a real browser: a new
project's own Python made without holding the page (said in one line; the making stood in:
tests/libraries_standin.py, nothing downloaded), the Environment's Libraries tab saying what it is, and the
Scripts and Notebooks pages running their documents in the project's ONE session: the status bar says Python
session, a document opened later is in the session already, Restart asks first and tells the other window.
Its own server. Made-up names only."""

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
from urllib.parse import quote

import pytest
from playwright.sync_api import Browser, Page, expect

from tests import libraries_standin
from tests.e2e.asks import answer_ask
from tests.e2e.test_ui import browser, call  # noqa: F401

NOTEBOOK = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {},
    "cells": [
        {
            "cell_type": "code",
            "metadata": {},
            "source": "print(orders_loaded + 1)",
            "outputs": [],
            "execution_count": None,
        }
    ],
}


@pytest.fixture(scope="module")
def own_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("session")
    variables = {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "home" / "SwissArmyBench"),
        "SWISSARMYBENCH_PROJECT_VENV": "on",  # this test is about it; the making is stood in
        "SWISSARMYBENCH_LIBRARIES_STANDIN": str(Path(libraries_standin.__file__).resolve()),
    }
    before = {name: os.environ.get(name) for name in variables}
    os.environ.update(variables)
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"])
    try:
        for _ in range(200):
            try:
                info = json.loads((tmp / "server.json").read_text())
                break
            except (OSError, ValueError):
                time.sleep(0.1)
        else:
            raise AssertionError("server did not start")
        yield info | {"tmp": tmp}
    finally:
        try:
            call(info, "POST", "/project/close", {"discard": True})
        except Exception:  # noqa: S110 (the server is going anyway)
            pass
        process.terminate()
        process.wait(timeout=20)
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def workbench(context: Any, server: dict[str, Any], page: str, path: Path) -> Page:
    """A Workbench page (scripts or notebooks) by its address, with a file to open."""
    opened: Page = context.new_page()
    opened.goto(f"http://127.0.0.1:{server['port']}/{page}#token={server['token']}&open={quote(str(path))}")
    expect(opened.locator(".wb-tabs .tab-item").first).to_be_visible(timeout=20000)
    return opened


def test_a_project_has_its_own_python_and_one_session(browser: Browser, own_server: dict[str, Any]) -> None:  # noqa: F811
    server = own_server
    project = server["tmp"] / "work" / "month_end"
    context = browser.new_context(viewport={"width": 1400, "height": 860})
    home = context.new_page()
    home.goto(f"http://127.0.0.1:{server['port']}/workspace#token={server['token']}")
    expect(home.locator(".nav-rail")).to_be_visible(timeout=20000)

    # ----- a new project: its own Python is made in the background, said in one line -----
    call(server, "POST", "/project/new", {"path": str(project)})
    expect(home.locator(".toast", has_text="Making this project's Python").first).to_be_visible(timeout=15000)
    for _ in range(100):
        if call(server, "GET", "/environment/python")["status"] == "ready":
            break
        time.sleep(0.1)
    assert (project / ".venv").is_dir()
    home.locator('.nav-rail [data-area="environment"]').click()
    found = home.locator('.area-page[data-page="environment"]')
    found.get_by_role("tab", name=re.compile("^Libraries")).click()
    line = found.locator(".env-project-python")
    expect(line).to_contain_text("This project has its own Python (.venv in its folder).")
    expect(line.locator(".env-project-session")).to_have_text("One Python session for the whole project")
    expect(line.get_by_role("button", name="Make it now")).to_have_count(0)
    expect(found.locator(".env-python")).to_contain_text("the project's own (.venv)")

    # ----- the Scripts page: its document runs in the project's session -----
    (project / "load.py").write_text("orders_loaded = 3\nprint('loaded', orders_loaded)\n", encoding="utf-8")
    (project / "report.ipynb").write_text(json.dumps(NOTEBOOK), encoding="utf-8")
    scripts = workbench(context, server, "scripts", project / "load.py")
    knob = scripts.locator(".wb-kernel")
    expect(knob).to_contain_text("Python session")
    expect(knob).to_contain_text("not started")
    expect(scripts.locator(".wb-env-project")).to_be_visible()  # no Python to pick: the project's
    expect(scripts.locator(".wb-env-pick")).to_have_count(0)
    scripts.keyboard.press("F5")  # Run file
    expect(scripts.locator(".wb-output, .wb-console").first).to_contain_text("loaded 3", timeout=60000)
    kernel = call(server, "GET", "/environment/python")["kernel"]
    assert kernel

    # ----- the Notebooks page: a document opened later is in the same session already -----
    notebooks = workbench(context, server, "notebooks", project / "report.ipynb")
    other = notebooks.locator(".wb-kernel")
    expect(other).to_contain_text("Python session")
    expect(other.locator(".wb-state")).to_have_count(0)  # running already: nothing to start
    # (The project's data.ipynb opens with the page: the report is brought to the front.)
    notebooks.locator(".wb-tabs .tab-item", has_text="report.ipynb").click()
    expect(notebooks.locator(".wb-kernel")).to_contain_text("Python session")
    notebooks.keyboard.press("F5")  # Run all
    # What the script made, the notebook reads: one session, one set of variables.
    expect(notebooks.locator(".wb-cell").first).to_contain_text("4", timeout=60000)
    assert call(server, "GET", "/environment/python")["kernel"] == kernel
    listed = call(server, "GET", "/environment")["items"]
    assert [i["name"] for i in listed if i["kind"] == "variable"].count("orders_loaded") == 1

    # ----- Restart is the session's: asked first, and the other window is told -----
    asked: list[str] = []

    def accept(dialog: Any) -> None:
        asked.append(dialog.message)
        dialog.accept()

    scripts.on("dialog", accept)
    knob.click()
    scripts.get_by_role("menuitem", name="Restart the project's Python session").click()
    asked.append(answer_ask(scripts))  # the app's own question (dom.ts askYesNo)
    expect(notebooks.locator(".toast", has_text="The project's Python session was restarted")).to_be_visible(
        timeout=30000
    )
    assert asked and "every notebook and script of the project" in asked[0]
    # Closing a document leaves the session running for the others.
    scripts.close()
    time.sleep(0.5)
    assert call(server, "GET", "/environment/python")["kernel"] == kernel
    context.close()
