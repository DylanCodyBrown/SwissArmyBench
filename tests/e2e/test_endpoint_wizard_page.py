"""New endpoint, the one wizard (the owner, 2026-11-21: "one uniform wizard for creating a sandbox api" /
"Steps are different depending on the API"), in a real browser: a sandbox table, the patterns ranked by its
shape with one sentence why, THAT pattern's own steps, the code previewed and kept current, Add to API.py;
the endpoint labelled by its pattern on the APIs page, run and tried; Reconcile asking for its second table;
the same wizard from the sandbox's row and from API.py's Endpoints pane on the Scripts page.

Made-up data only."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.sync_api import Browser, expect

from tests.e2e.test_local_apis_page import open_workspace, shop, shot  # noqa: F401
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_widgets_shared import until

ORDERS = (
    "order_id,customer,region,status,order_date,amount\n"
    "1,Ada Fenn,North,open,2026-01-05,120.5\n"
    "2,Bo Larch,East,open,2026-01-20,80.0\n"
    "3,Cy Moss,North,closed,2026-02-03,40.0\n"
    "4,Di Reed,South,open,2026-02-14,200.0\n"
)
LEDGER = "order_id,amount,posted\n1,120.5,2026-01-06\n2,85.0,2026-01-21\n9,10.0,2026-03-09\n"


def test_the_wizard_ranks_asks_that_patterns_steps_previews_and_adds(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    shop: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    for name, text in (("sales", ORDERS), ("ledger", LEDGER)):
        file = tmp_path / f"{name}.csv"
        file.write_text(text, encoding="utf-8")
        call(server, "POST", "/sandbox/tables", {"from": "file", "path": str(file)})
    page = open_workspace(browser, server)
    page.locator(".nav-rail [data-area='apis']").click()
    apis = page.locator(".local-apis")
    bar = apis.locator(".local-api-bar")
    expect(bar.get_by_role("button", name="Run")).to_be_visible(timeout=30000)

    # ----- the wizard, from the bar's "…": the table, then the patterns ranked by its shape -----
    bar.get_by_role("button", name="More").click()
    page.get_by_role("menuitem", name="New endpoint…").click()
    wizard = page.get_by_role("dialog", name="New endpoint")
    wizard.get_by_label("Table", exact=True).select_option("sales")
    ranked = wizard.locator(".wizard-pattern")
    expect(ranked).to_have_count(9, timeout=20000)
    expect(ranked.first).to_have_attribute("data-pattern", "table")  # the best fit first, and picked
    expect(ranked.first.locator("input")).to_be_checked()
    expect(wizard.locator(".wizard-pattern[data-pattern='action'] .wizard-pattern-why")).to_have_text(
        "sales has status: an action sets it on the rows whose keys you send, all or none."
    )
    # What does not fit is last, says what it needs and cannot be picked.
    expect(ranked.last).to_have_attribute("data-pattern", "versions")
    expect(ranked.last).to_contain_text("sales has no version number column")
    expect(ranked.last.locator("input")).to_be_disabled()
    # Table's own step is one: its key.
    expect(wizard.locator(".wizard-step")).to_have_count(1)
    expect(wizard.locator(".wizard-code")).to_contain_text("def list_sales(", timeout=20000)

    # ----- Summary: ITS steps (group by, totals, a date column, a period), the code kept current -----
    wizard.locator(".wizard-pattern[data-pattern='summary'] input").check()
    steps = wizard.locator(".wizard-step")
    expect(steps).to_have_count(4, timeout=20000)
    assert [s.get_attribute("data-step") for s in steps.all()] == ["group", "totals", "date", "period"]
    group = wizard.get_by_role("group", name="Group by")
    expect(group.get_by_label("region")).to_be_checked()  # what the table's shape suggests
    code = wizard.locator(".wizard-code")
    expect(code).to_contain_text("def summary_sales_by_region(", timeout=20000)
    expect(code).to_contain_text("# pattern: summary of sales")
    expect(wizard.locator(".wizard-said")).to_have_text("1 endpoint for API.py.")
    expect(wizard.locator(".wizard-pairs")).to_contain_text("A bar chart draws the totals.")
    shot(page, "endpoint-wizard-summary", "dialog[open]")
    group.get_by_label("status").check()
    expect(code).to_contain_text("def summary_sales_by_region_status(", timeout=20000)
    # The one thing still missing is said in the code's place; Add waits for it.
    totals = wizard.get_by_role("group", name="Totals")
    totals.get_by_role("button", name="Remove").first.click()
    totals.get_by_role("button", name="Remove").first.click()
    expect(wizard.locator(".wizard-said")).to_have_text(
        "Pick at least one total (count is one).", timeout=20000
    )
    expect(wizard.get_by_role("button", name="Add to API.py")).to_be_disabled()
    totals.get_by_role("button", name="Add a total").click()
    totals.get_by_label("Total 1", exact=True).select_option("avg")
    totals.get_by_label("Column of total 1").select_option("amount")
    expect(code).to_contain_text("avg_amount: float", timeout=20000)
    # A period: only the date column is offered; it is the read's plan (the adapter's Period, 1.8.0), `since`
    # a date sent as a date.
    wizard.get_by_label("Date column (for a period)").select_option("order_date")
    wizard.get_by_label("Period", exact=True).select_option("month")
    expect(code).to_contain_text("def summary_sales_by_month_region_status(", timeout=20000)
    expect(code).to_contain_text("since: date | None = None,")
    expect(code).to_contain_text('"periods": [{"column": "order_date", "unit": "month", "name": "period"}],')
    wizard.get_by_role("button", name="Add to API.py").click()
    expect(wizard).to_be_hidden(timeout=20000)
    text = (shop / "API.py").read_text(encoding="utf-8")
    assert "def summary_sales_by_month_region_status(" in text and "# pattern: summary of sales" in text

    # ----- the APIs page labels the endpoint by its pattern; it runs and answers -----
    row = apis.locator(".local-api-endpoint[data-endpoint='summary_sales_by_month_region_status']")
    expect(row.locator(".local-api-pattern")).to_have_text("Summary", timeout=20000)
    expect(row.locator(".local-api-data")).to_have_text("The sandbox (plain DuckDB)")
    apis.get_by_role("button", name="Run").click()
    expect(apis.locator(".local-api-status.on")).to_contain_text("Running on", timeout=30000)
    row.get_by_role("button", name="Try it").click()
    row.get_by_role("button", name="Send").click()
    expect(row.locator(".local-api-said")).to_contain_text("200", timeout=20000)
    expect(row.locator(".local-api-said")).to_contain_text(" rows")
    shot(page, "endpoint-wizard-pattern-label", ".local-apis")

    # ----- from the sandbox's row: Reconcile asks for the second table among its own steps -----
    page.locator(".sandbox-panel tr[data-table='sales']").get_by_role("button", name="New endpoint").click()
    wizard = page.get_by_role("dialog", name="New endpoint")
    expect(wizard.get_by_label("Table", exact=True)).to_have_value("sales")
    expect(wizard.locator(".wizard-pattern[data-pattern='reconcile'] .wizard-pattern-why")).to_have_text(
        "sales and ledger share order_id and amount: matched, missing, differing.", timeout=20000
    )
    wizard.locator(".wizard-pattern[data-pattern='reconcile'] input").check()
    expect(wizard.get_by_label("Compared with")).to_have_value("ledger", timeout=20000)
    assert [s.get_attribute("data-step") for s in wizard.locator(".wizard-step").all()] == [
        "other",
        "key",
        "compare",
    ]
    expect(wizard.get_by_role("group", name="The key both share").get_by_label("order_id")).to_be_checked()
    expect(wizard.locator(".wizard-code")).to_contain_text('FULL OUTER JOIN "ledger" AS r', timeout=20000)
    expect(wizard.locator(".wizard-said")).to_have_text("2 endpoints for API.py.")
    shot(page, "endpoint-wizard-reconcile", "dialog[open]")
    wizard.get_by_role("button", name="Add to API.py").click()
    expect(wizard).to_be_hidden(timeout=20000)
    counts = apis.locator(".local-api-endpoint[data-endpoint='reconcile_sales_ledger']")
    expect(counts.locator(".local-api-pattern")).to_have_text("Reconcile", timeout=20000)
    expect(apis.locator(".local-api-status.on")).to_contain_text("Running on", timeout=30000)  # started again

    def counted() -> Any:  # the running API starts again by itself once API.py changes
        try:
            asked = {"method": "GET", "path": "/reconcile/sales-ledger"}
            return call(server, "POST", "/local-api/call", asked)["body"]
        except Exception as error:
            return str(error)

    until(counted, {"matched": 1, "differing": 1, "missing_in_sales": 1, "missing_in_ledger": 2}, 30)

    # ----- the same wizard from API.py's Endpoints pane on the Scripts page -----
    scripts = page.context.new_page()
    api_py = quote(str(shop / "API.py"))
    scripts.goto(f"http://127.0.0.1:{server['port']}/scripts?path={api_py}#token={server['token']}")
    expect(scripts.get_by_role("button", name="Run API")).to_be_visible(timeout=30000)
    scripts.locator(".wb-mode-toggle-endpoints").click()
    pane = scripts.locator(".wb-mode-endpoints")
    expect(pane.locator(".local-api-endpoint .local-api-pattern").first).to_have_text(
        "Summary", timeout=20000
    )
    pane.get_by_role("button", name="New endpoint…").click()
    again = scripts.get_by_role("dialog", name="New endpoint")
    expect(again.locator(".wizard-pattern")).to_have_count(9, timeout=20000)
    again.get_by_role("button", name="Cancel").click()
