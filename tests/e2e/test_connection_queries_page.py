# ruff: noqa: F811
"""Each connection's slots in a real browser (the owner, 2026-11-21: "throttle how many queries an agent can
run in parallel per connection" and "a robust standalone popout panel in the connection to show queries that
are in progress"). A made-up SQLite connection that takes a few seconds to connect stands in for a slow
server, with one query at once: its card's live count, the Queries window (a query Running with its time
ticking, another Waiting with its place, the SQL formatted and highlighted when a row is opened, Cancel and
the Finished list), and the "+" draft's query waiting in line with its place and Cancel. Made-up data only.

With SAB_QUERIES_SHOTS set to a folder, the tests save screenshots there (2x)."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser, call, open_grid, orders_url, server, until  # noqa: F401

SHOTS = os.environ.get("SAB_QUERIES_SHOTS")
NAME = "Slow Depot"
LONG_SQL = (
    "select stock_id, region, units, units * 2 as doubled from stock where region in ('North', 'East') "
    "and units > 1 order by units desc, region"
)


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def slow(server: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Slow Depot: a made-up stock table behind a connect that takes three seconds; one query at once."""
    file = tmp_path_factory.mktemp("slow_depot") / "depot.sqlite"
    with sqlite3.connect(file) as db:
        db.execute("CREATE TABLE stock (stock_id INTEGER, region TEXT, units INTEGER)")
        rows = [(1, "North", 3), (2, "East", 9), (3, "South", 5), (4, "West", 7)]
        db.executemany("INSERT INTO stock VALUES (?, ?, ?)", rows)
    names = {c["name"] for c in call(server, "GET", "/connections")["connections"]}
    if NAME not in names:
        call(
            server,
            "POST",
            "/connections",
            {
                "name": NAME,
                "kind": "sql",
                "template": "sqlite",
                "dialect": "sqlite",
                "code": (
                    "import sqlite3\nimport time\nfrom pathlib import Path\n\ntime.sleep(3)\n"
                    f'path = Path(r"{file}")\n'
                    'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
                ),
            },
        )
    call(server, "PUT", f"/connections/{NAME.replace(' ', '%20')}/limits", {"total": 1})
    call(server, "POST", "/connections/queries/clear", {})
    return {"file": file}


def background(
    server: dict[str, Any], table: str, sql: str = LONG_SQL, agent: bool = False
) -> threading.Thread:
    """A query on Slow Depot from outside the page (the user's or the agent's), left running."""

    def run() -> None:
        try:
            call(
                server,
                "POST",
                f"/datasets/{table}/connection-query",
                {"connection": NAME, "sql": sql},
                agent=agent,
            )
        except Exception:  # noqa: S110 (a cancelled one answers 408: what the test looks at is the page)
            pass

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def queries(server: dict[str, Any]) -> list[dict[str, Any]]:
    return list(call(server, "GET", "/connections/queries")["queries"])


def test_the_card_counts_live_and_the_queries_window_shows_cancels_and_finishes(
    browser: Browser, server: dict[str, Any], slow: dict[str, Any]
) -> None:
    context = browser.new_context(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace?open=connections#token={server['token']}")
    card = page.locator(f".connection-card[data-connection='{NAME}']")
    expect(card).to_be_visible(timeout=20000)
    line = card.locator(".connection-slots")
    expect(line).to_be_hidden()  # nothing runs: nothing said
    first = background(server, "slow_first")
    assert until(lambda: any(q["state"] == "running" for q in queries(server)), 10)
    second = background(server, "slow_second", agent=True)
    expect(line).to_have_text("Running 1 of 1 · 1 waiting", timeout=10000)
    shot(page, "1-card-running")

    with context.expect_page() as opened:
        line.click()
    window = opened.value
    expect(window).to_have_title(f"{NAME} · Queries", timeout=20000)
    rows = window.locator(".queries-row")
    expect(rows).to_have_count(2, timeout=10000)
    running = window.locator(".queries-row.st-running")
    waiting = window.locator(".queries-row.st-waiting")
    expect(running.locator(".queries-state")).to_have_text("Running")
    expect(waiting.locator(".queries-state")).to_have_text("Waiting · 1st in line")
    expect(window.locator(".queries-counts")).to_contain_text("Running 1 of 1 · 1 waiting · agent ")
    # The time ticks.
    elapsed = running.locator(".queries-elapsed")
    before = elapsed.inner_text()
    window.wait_for_function(
        "([el, was]) => document.querySelector(el)?.textContent !== was",
        arg=[".queries-row.st-running .queries-elapsed", before],
        timeout=5000,
    )
    # Opened: its SQL formatted for reading, in the highlighted box (Monaco's SQL, read-only).
    running.click()
    box = window.locator(".queries-sql .queries-sql-box")
    expect(box.locator(".monaco-editor")).to_be_visible(timeout=20000)
    expect(box).to_contain_text("SELECT")
    expect(box).to_contain_text("ORDER BY")
    expect(box.locator(".view-line")).not_to_have_count(1)  # one clause a line, not the one long line
    shot(window, "2-queries-window")

    # Cancel the running one: it ends, the agent's starts, and Finished says Cancelled.
    running.get_by_role("button", name="Cancel").click()
    done = window.locator(".queries-done")
    expect(done.first.locator(".queries-outcome")).to_contain_text("Cancelled", timeout=15000)
    first.join(30)
    second.join(30)
    expect(window.locator(".queries-row")).to_have_count(0, timeout=20000)
    expect(window.locator(".queries-done.out-ok").first).to_be_visible(timeout=10000)
    expect(line).to_be_hidden(timeout=10000)
    shot(window, "3-finished")
    window.close()
    context.close()


def test_a_draft_query_waits_in_line_with_its_place_and_cancel(
    browser: Browser, server: dict[str, Any], slow: dict[str, Any], orders_url: str
) -> None:
    page = open_grid(browser, orders_url, 1500, 900, device_scale_factor=2)
    holder = background(server, "slow_holder")
    assert until(lambda: any(q["state"] == "running" for q in queries(server)), 10)
    page.get_by_role("button", name="New query").click()
    page.locator(".new-query-choice", has_text=NAME).click()
    view = page.locator("#query-view")
    expect(view.get_by_role("combobox", name="Query from")).to_have_value(NAME, timeout=10000)
    view.get_by_role("textbox", name="Name of the new table").fill("slow_draft")
    editor = view.locator(".sql-editor .monaco-editor, .sql-editor textarea").first
    expect(editor).to_be_visible(timeout=20000)
    editor.click()
    page.keyboard.press("Control+A")
    page.keyboard.type("SELECT region, units FROM stock")
    view.get_by_role("button", name="Run", exact=True).click()
    cover = page.locator(".busy-cover")
    expect(cover.locator(".busy-words")).to_have_text(
        f"Waiting: 1st in line for {NAME} (1 query running)", timeout=10000
    )
    shot(page, "4-draft-waiting")
    cover.get_by_role("button", name="Cancel").first.click()
    expect(cover).to_have_count(0, timeout=10000)
    expect(view.locator(".sql-status")).to_have_text("Cancelled.", timeout=10000)
    assert until(lambda: not any(q.get("client") and q["state"] == "waiting" for q in queries(server)), 10)
    holder.join(30)
    page.context.close()
