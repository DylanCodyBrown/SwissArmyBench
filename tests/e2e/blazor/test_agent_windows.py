"""The agent's windows on the Blazor front end: a page says which window it is, so app_navigate (POST
/navigate) with window notebooks or scripts reaches the open one, refused only when none is open."""

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


def test_the_agents_navigate_reaches_the_open_notebooks_page(browser: Browser, server: dict[str, Any]) -> None:
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
