"""The agent's windows on the Blazor front end: a page says which window it is, so workbench_window (POST
/workbench/window) runs a command of the open Notebooks or Scripts page's palette as the user's own, and
app_navigate (POST /navigate) with window notebooks or scripts reaches the open one; both are refused only
when none is open."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import open_page


def ask(server: dict[str, Any], path: str, body: dict[str, Any]) -> tuple[int, Any]:
    """A POST as the agent sends it: the status and the answer (a refusal's JSON too)."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{server['port']}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {server['token']}",
            "Content-Type": "application/json",
            "X-Actor": "agent",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (127.0.0.1)
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as refused:
        return refused.code, json.loads(refused.read() or b"null")


def test_the_agents_window_command_runs_on_the_open_scripts_page(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = open_page(browser, server, "")
    expect(page.locator("h1.area-page-title")).to_be_visible()
    status, said = ask(server, "/workbench/window", {"command": "documents"})
    assert status == 409 and "Neither the Notebooks nor the Scripts page is open" in said["error"]

    page.locator(".nav-rail-item[data-area=scripts]").click()
    expect(page).to_have_url(re.compile(r"/blazor/scripts"))
    expect(page.locator(".wb-landing, .empty-state").first).to_be_visible()
    for _ in range(40):  # the page says it is the Scripts window as it lands
        status, said = ask(server, "/workbench/window", {"command": "documents"})
        if status == 200:
            break
        page.wait_for_timeout(250)
    assert status == 200 and said["result"]["page"] == "scripts" and said["result"]["documents"] == []

    status, said = ask(server, "/workbench/window", {"command": "commands"})
    listed = {c["id"]: c for c in said["result"]["commands"]}
    assert "file.new" in listed and listed["file.close"]["why_not"] == "Open a notebook or a script first"

    # A palette command, as the user's own: a new script's tab.
    status, said = ask(server, "/workbench/window", {"command": "file.new"})
    assert status == 200 and said["result"] == {"ran": "file.new"}
    expect(page.locator(".monaco-editor").first).to_be_visible()
    status, said = ask(server, "/workbench/window", {"command": "documents", "page": "scripts"})
    assert [d["kind"] for d in said["result"]["documents"]] == ["script"]

    # One it cannot run, and one it does not have: the reason, at once.
    status, said = ask(server, "/workbench/window", {"command": "kitchen.sink"})
    assert status == 409 and "no command" in said["error"]
    status, said = ask(server, "/workbench/window", {"command": "documents", "page": "notebooks"})
    assert status == 409 and "The Notebooks page is not open" in said["error"]
    page.close()


def test_the_agents_navigate_reaches_the_open_notebooks_page(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = open_page(browser, server, "notebooks")
    expect(page.locator(".wb-landing, .empty-state").first).to_be_visible()
    for _ in range(40):
        status, said = ask(server, "/navigate", {"window": "notebooks", "to": "connections"})
        if status == 200:
            break
        page.wait_for_timeout(250)
    assert status == 200, said
    expect(page).to_have_url(re.compile(r"/blazor/connections$"))
    # It moved on: no Notebooks page is open any more.
    for _ in range(40):
        status, said = ask(server, "/navigate", {"window": "notebooks", "to": "back"})
        if status == 409:
            break
        page.wait_for_timeout(250)
    assert status == 409 and "No Notebooks page is open" in said["error"]
    page.close()
