# ruff: noqa: F811
"""The code app's data notebook in a real browser (the Power Apps extension, phase 2), with Deno and its
Jupyter kernel stood in by tests/deno_fake.py and the Power Platform tools by tests/powerapps_fakes.py: the
Code App page's Data notebook opens data.ipynb in the Workbench, a SQL cell over an open table and a
TypeScript cell run in the one kernel with their tables drawn, Open as grid, an error in the panel, a TSX cell
drawn in the HTML cells' frame with its props from the notebook, and Use in app writes src/shared/data.ts. Made-up
data only.

With SWISSARMYBENCH_CODEAPP_SHOTS set to a folder, the test also saves screenshots there (2x)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from playwright.sync_api import Browser, expect

from swissarmybench.domain import notebooks
from tests import deno_fake
from tests import powerapps_fakes as fakes
from tests.e2e.test_codeapp_page import new_page, shot, start
from tests.e2e.test_ui import browser, call  # noqa: F401

TSX = (
    '// props: { rows: byRegion, title: "Sales by region" }\n'
    "export default function Totals({ rows, title }) {\n"
    "  return <section><h2>{title}</h2></section>;\n"
    "}\n"
)


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("codeapp-notebook-e2e")
    tools = deno_fake.install(fakes.install(tmp / "fake-tools"))
    process, info = start(tmp, "powerapps", tools)
    (tmp / "apps").mkdir()
    yield info | {"tmp": tmp, "tools": tools}
    process.terminate()
    process.wait(timeout=20)


def _app(server: dict[str, Any]) -> Path:
    body = {
        "name": "Sales Desk",
        "environment_id": fakes.ENVIRONMENT_ID,
        "parent": str(server["tmp"] / "apps"),
    }
    folder = Path(call(server, "POST", "/powerapps/project/new", body)["folder"])
    for name in ("react", "react-dom"):  # the project's own React (what npm install puts there)
        (folder / "node_modules" / name).mkdir(parents=True, exist_ok=True)
        (folder / "node_modules" / name / "package.json").write_text(json.dumps({"name": name}))
    return folder


def test_the_data_notebook_from_the_code_app_page(browser: Browser, server: dict[str, Any]) -> None:
    folder = _app(server)
    call(server, "POST", "/powerapps/sources", {"kind": "dataverse", "table": "account"})
    # An open table (a tab in the grid): a view by its name in the notebook's DuckDB.
    request_paste(server, "sales", "region\ttotal\nWest\t5\nEast\t9\n")
    # The data notebook made by the page; a TSX cell added to it as a user would.
    page = new_page(browser, server)
    expect(page.locator(".ca-data-notebook")).to_be_visible(timeout=20000)
    expect(page.locator(".ca-sources tr[data-source='accounts'] .ca-open-grid")).to_be_visible()
    shot(page, "codeapp-notebook-section")
    path = Path(call(server, "POST", "/powerapps/notebook/open", {})["path"])
    cells = notebooks.read_notebook(path.read_text())
    cells.append(notebooks.Cell("tsx", TSX))
    path.write_text(notebooks.write_notebook(cells))

    wb = page.context.new_page()
    wb.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}&open={quote(str(path))}")
    expect(wb.locator(".wb-cell.kind-typescript")).to_have_count(1, timeout=30000)
    expect(wb.locator(".wb-cell.kind-tsx")).to_have_count(1)
    # The SQL cell, over the open table: run in the kernel's DuckDB, its table drawn.
    sql = wb.locator(".wb-cell.kind-sql").first
    sql.locator(".monaco-editor").click()
    wb.keyboard.press("Control+a")
    wb.keyboard.type("SELECT region, total FROM sales ORDER BY total")
    sql.get_by_role("button", name="Run cell").click()
    expect(sql.locator(".wb-result-table tbody tr")).to_have_count(2, timeout=60000)
    expect(sql.locator(".wb-result-table")).to_contain_text("West")
    # The TypeScript cell: its result, and Open as grid.
    ts = wb.locator(".wb-cell.kind-typescript")
    ts.get_by_role("button", name="Run cell").click()
    expect(ts.locator(".wb-result-table")).to_contain_text("North", timeout=60000)
    expect(ts.locator(".wb-result-foot")).to_contain_text("2 rows, 2 columns")
    shot(wb, "codeapp-notebook-cells")
    ts.locator(".wb-result .wb-to-grid").click()
    expect(wb.locator(".toast").filter(has_text="is open as a grid")).to_be_visible(timeout=20000)
    # The TSX cell: drawn in the HTML cells' frame, its props from the notebook's values.
    tsx = wb.locator(".wb-cell.kind-tsx")
    tsx.get_by_role("button", name="Run cell").click()
    frame = tsx.frame_locator(".wb-design-frame")
    expect(frame.locator("h2")).to_have_text("Sales by region", timeout=60000)
    expect(frame.locator("li")).to_have_count(2)
    expect(tsx).to_have_class(re.compile(r"\bpreviewed\b"))
    tsx.scroll_into_view_if_needed()
    expect(wb.locator(".wb-tcell")).to_have_count(0)  # no Python Tables group in this mode
    shot(wb, "codeapp-notebook-tsx")
    # An error: the panel's words.
    ts.locator(".monaco-editor").click()
    wb.keyboard.press("Control+a")
    wb.keyboard.type("nope + 1")
    ts.get_by_role("button", name="Run cell").click()
    expect(ts.locator(".wb-outputs")).to_contain_text("TypeScript has no `nope` here", timeout=60000)
    shot(wb, "codeapp-notebook-error")

    # Use in app: data.ts written into the code app's src/.
    page.bring_to_front()
    page.locator(".ca-use-in-app").click()
    expect(page.locator(".ca-data-ts .ca-file")).to_have_text("src/shared/data.ts", timeout=20000)
    written = (folder / "src" / "shared" / "data.ts").read_text()
    assert written.startswith("// data.ts: made from the data notebook's TypeScript cells")
    shot(page, "codeapp-use-in-app")


def request_paste(server: dict[str, Any], name: str, text: str) -> None:
    import urllib.request

    request = urllib.request.Request(
        f"http://127.0.0.1:{server['port']}/datasets/{name}/paste",
        data=text.encode(),
        method="POST",
        headers={"Authorization": f"Bearer {server['token']}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        response.read()
