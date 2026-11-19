# ruff: noqa: F811
"""Gates everywhere, in a real browser (the owner's F): in a Power BI project (a made-up .pbix imported,
pbixray stood in for), an address on a closed area covers its page with the one line (the page not seen
behind it), the Workbench's palette and its New entries show the line instead of running, and the tour is the
mode's own short list. Made-up data only.

With SWISSARMYBENCH_SHOTS set to a folder, the test also saves screenshots there (2x, light and dark)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from swissarmybench.renamed import env
from tests import powerbi_pbix_fake as fake
from tests.e2e.test_powerbi_project_page import server  # noqa: F401
from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = env("SWISSARMYBENCH_SHOTS") or None


def test_gates_reach_the_palette_new_entries_an_address_and_the_tour(
    browser: Browser, server: dict[str, Any]
) -> None:
    tmp = Path(server["tmp"])
    pbix = fake.fake_pbix(tmp)
    body = {"path": str(pbix), "folder": str(tmp / "projects"), "dataset": {"none": True}}
    assert call(server, "POST", "/powerbi/import", body)["type"] == "powerbi"
    call(server, "POST", "/app/gates", {"seen": True})  # the first-open pop-up: its own test
    base = f"http://127.0.0.1:{server['port']}"
    for scheme in ("light", "dark"):
        context = browser.new_context(
            viewport={"width": 1400, "height": 900}, device_scale_factor=2, color_scheme=scheme
        )
        page = context.new_page()
        # An address on a closed area: the page is covered, the line in its middle, the rail beside it.
        page.goto(f"{base}/workspace?open=apis#token={server['token']}")
        cover = page.locator(".gate-cover")
        expect(cover).to_be_visible(timeout=20000)
        expect(cover.locator(".gate-line")).to_contain_text("This Power BI project keeps APIs closed.")
        middle = page.evaluate(
            "() => document.elementFromPoint(innerWidth / 2, 120)?.closest('.gate-cover') !== null"
        )
        assert middle, "the closed page shows through"
        expect(page.locator('.nav-rail-item[data-area="powerbi"]')).to_be_visible()
        if SHOTS:
            page.screenshot(path=str(Path(SHOTS) / f"powerbi-gate-cover-{scheme}.png"))
        # Moving to an open area takes the cover away.
        page.locator('.nav-rail-item[data-area="connections"]').click()
        expect(cover).to_have_count(0)

        if scheme == "light":
            # The Workbench: the palette's New script and the New menu's New script show the line instead.
            work = context.new_page()
            work.goto(f"{base}/workbench#token={server['token']}")
            expect(work.locator(".nav-rail")).to_be_visible(timeout=20000)
            expect(work.locator('.nav-rail-item[data-area="scripts"]')).to_be_hidden()  # the gates are known
            work.keyboard.press("Control+Shift+P")
            work.locator(".wb-palette-input").fill("New script")
            work.keyboard.press("Enter")
            line = work.locator(".gate-line")
            expect(line).to_contain_text("This Power BI project keeps Scripts closed.", timeout=15000)
            scripts = work.locator(".wb-tab", has_text=re.compile(r"\.py\b|script", re.I))
            expect(scripts).to_have_count(0)  # nothing was made
            assert "kind=script" not in work.url
            line.get_by_role("button", name="Close").click()
            expect(line).to_have_count(0)
            work.get_by_role("button", name="Workbench menu").first.click()
            work.get_by_role("menuitem", name="New script").click()
            expect(line).to_contain_text("keeps Scripts closed", timeout=15000)
            expect(scripts).to_have_count(0)
            if SHOTS:
                work.screenshot(path=str(Path(SHOTS) / "powerbi-gate-new-entry.png"))
            work.close()

            # The tour: the mode's own short list after its greeting.
            page.goto(f"{base}/workspace?open=projects#token={server['token']}")
            page.locator('.area-page[data-page="projects"] .tour-slot').locator(
                ".tour-bubble-go:visible, .tour-btn:visible"
            ).first.click()
            card = page.locator(".tour-card")
            expect(card).to_be_visible(timeout=15000)
            expect(card.locator(".tour-dots")).to_have_attribute("aria-label", "1 of 5")
            card.get_by_role("button", name="Next").click()
            expect(card).to_contain_text("Your report: what it reads", timeout=15000)
            if SHOTS:
                page.screenshot(path=str(Path(SHOTS) / "powerbi-tour.png"))
            page.keyboard.press("Escape")
        context.close()
