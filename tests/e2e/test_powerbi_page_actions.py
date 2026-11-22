# ruff: noqa: F811
"""The Power BI page's actions, in a real browser: Edit in Power BI Desktop shows its dry run on the page
(each change listed, Apply), and Use another report's pages opens the report dialog right there.
A running Power BI Desktop and pbixray are stood in for. Made-up data only.

With SWISSARMYBENCH_SHOTS set to a folder, the test also saves screenshots there (2x, light and dark)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests import powerbi_pbix_fake as fake
from tests.e2e.test_powerbi_project_page import server  # noqa: F401
from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_SHOTS", "") or None


def test_edit_in_power_bi_desktop_and_another_reports_pages(browser: Browser, server: dict[str, Any]) -> None:
    tmp = Path(server["tmp"])
    pbix = fake.fake_pbix(tmp)
    body = {"path": str(pbix), "folder": str(tmp / "projects"), "dataset": {"none": True}}
    call(server, "POST", "/powerbi/import", body)
    call(server, "POST", "/app/gates", {"seen": True})
    assert call(server, "GET", "/powerbi/live?asked=1")["live"]
    base = f"http://127.0.0.1:{server['port']}"
    for scheme in ("light", "dark"):
        context = browser.new_context(
            viewport={"width": 1400, "height": 900}, device_scale_factor=2, color_scheme=scheme
        )
        page = context.new_page()
        page.goto(f"{base}/workspace?open=powerbi#token={server['token']}")
        panel = page.locator('.area-page[data-page="powerbi"] .extension-panel')
        panel.get_by_role("button", name="Edit in Power BI Desktop").click()
        review = panel.locator('[data-review="edit"]')
        expect(review).to_contain_text("Edit in Power BI Desktop: the dry run", timeout=20000)
        if scheme == "light":
            expect(review.locator("li")).to_have_count(2)
            expect(review).to_contain_text("Add the measure Sales[Total Sales]")
        else:  # applied in the light pass: the open model has them now
            expect(review).to_contain_text("Nothing to change")
        if SHOTS:
            page.screenshot(path=str(Path(SHOTS) / f"powerbi-edit-dry-run-{scheme}.png"))
        if scheme == "light":
            review.get_by_role("button", name="Apply").click()
            expect(panel).to_contain_text("Applied 2 changes to the open model", timeout=20000)
            expect(review).to_have_count(0)
            panel.get_by_role("button", name="Use another report's pages").click()
            dialog = page.locator("dialog.pbi-export")
            expect(dialog).to_be_visible(timeout=20000)
            expect(dialog.locator(".pbi-report-first")).to_contain_text("Use an existing report's pages")
            if SHOTS:
                page.screenshot(path=str(Path(SHOTS) / "powerbi-report-pages.png"))
        else:
            review.get_by_role("button", name="Cancel").click()
            expect(review).to_have_count(0)
        context.close()
