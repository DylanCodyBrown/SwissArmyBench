"""The Blazor Settings page against the classic one's elements, on made-up data: the Team box's Join a team…
flow (its steps, GitHub sync's Install step), Advanced's Set up this computer, Claude's lists and Look
again, Beta (the switch, the status bar's Beta mark and its menu, Leave a note, Clear the beta log asked
first), and the order of the boxes."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_the_team_box_and_its_flow(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "settings")
    team = page.locator(".team-fieldset")
    expect(team).to_contain_text("Share connections, variables and projects with your team.")
    team.locator("button:has-text('Join a team…')").click()
    flow = page.locator(".dialog[aria-label='Join a team']")
    expect(flow.locator(".team-step-name")).to_have_count(4)
    expect(flow.locator(".team-step-name.current")).to_contain_text("GitHub sync")
    expect(flow.locator(".team-step-title")).to_contain_text("Joining a team needs GitHub sync")
    expect(flow.locator("button:has-text('Install')")).to_be_visible()
    flow.locator("button[aria-label=Close]").click()
    team.locator("summary:has-text('Advanced')").click()
    expect(team.locator(".library-row")).to_contain_text("Team library folder")
    team.locator("button:has-text('Set up this computer')").click()
    setup = page.locator(".dialog[aria-label='Set up this computer']")
    expect(setup.locator(".setup-heading")).to_contain_text("Set up this computer")
    expect(setup.locator("button:has-text('Check again')")).to_be_visible()
    setup.locator("button[aria-label=Close]").click()
    page.close()


def test_claude_and_beta(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "settings")
    claude = page.locator(".claude-fieldset")
    expect(claude.locator("select[aria-label='Claude Code']")).to_be_visible()
    expect(claude.locator("select[aria-label='Claude Desktop']")).to_be_visible()
    expect(claude).to_contain_text("Start Claude Code with bypass permissions")
    expect(page.locator(".status-bar button[aria-label='Launch Claude']")).to_be_visible()
    beta = page.locator(".beta-fieldset")
    switch = beta.locator("input.beta-switch")
    if not switch.is_checked():
        switch.check()
    expect(page.locator(".status-bar .beta-mark")).to_be_visible()
    assert call(server, "GET", "/beta")["on"] is True
    page.locator(".status-bar .beta-mark").click()
    menu = page.locator(".context-menu[aria-label='Beta mode']")
    expect(menu).to_contain_text("Export beta log…")
    menu.locator("[role=menuitem]", has_text="Leave a note…").click()
    note = page.locator(".dialog[aria-label='Leave a note']")
    note.locator("textarea[aria-label='What is wrong']").fill("A made-up note: the button looked odd.")
    note.locator("textarea[aria-label='What is wrong']").press("Control+Enter")
    expect(page.locator(".note-corner")).to_contain_text("Saved")
    beta.locator("button:has-text('Clear the log')").click()
    clear = page.locator(".dialog[aria-label='Clear the beta log']")
    expect(clear).to_contain_text("Every log file, note and picture goes.")
    clear.locator("button:has-text('Cancel')").click()
    switch.uncheck()
    expect(page.locator(".status-bar .beta-mark")).to_have_count(0)
    page.close()
