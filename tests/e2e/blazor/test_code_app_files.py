"""A code app's files and its data notebook in this front end (the classic workbenchCodeFile.ts and
routedCells.ts): a file opened from the Code App page as a tab of the Scripts page, TypeScript's own
language service in its editor, typed and saved back; the data notebook on the Notebooks page, its SQL and
TypeScript cells run on the mode's routes (Deno stood in by tests/deno_fake.py), a table result with Open as
grid. Made-up data only."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from tests import deno_fake
from tests import powerapps_fakes as fakes
from tests.e2e.blazor.conftest import call, open_page
from tests.e2e.blazor.extension_server import extension_server


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("blazor-codeapp-files")
    tools = deno_fake.install(fakes.install(tmp / "fake-tools"))
    path = str(tools) + os.pathsep + os.environ.get("PATH", "")
    with extension_server(tmp, ["streamlit", "powerapps"], {"PATH": path}) as info:
        parent = tmp / "apps"
        parent.mkdir()
        made = call(
            info,
            "POST",
            "/powerapps/project/new",
            {"name": "Made Up Expenses", "environment_id": fakes.ENVIRONMENT_ID, "parent": str(parent)},
        )
        # The code app's folder is the open project: the pages take its mode (the TypeScript cells' routes).
        call(info, "POST", "/project/open", {"path": made["folder"]})
        yield info | {"folder": made["folder"]}


def test_a_code_file_opens_as_a_scripts_tab_and_saves(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "scripts?codefile=src/App.tsx")
    expect(page.locator(".wb-tab.active")).to_contain_text("App.tsx")
    view = page.locator(".wb-codefile[data-path='src/App.tsx']")
    expect(view).to_have_attribute("data-language", "tsx")
    expect(view.locator(".monaco-editor")).to_be_visible()
    view.locator(".monaco-editor .view-lines").click()
    page.keyboard.press("Control+End")
    page.keyboard.type("\n// made-up note\n")
    expect(page.locator(".wb-tab.active")).to_contain_text("●")
    page.keyboard.press("Control+s")
    expect(page.locator(".note-corner")).to_contain_text("Saved App.tsx")
    saved = call(server, "GET", "/powerapps/project/file?path=src/App.tsx")["text"]
    assert "// made-up note" in saved
    page.close()


def test_the_data_notebooks_cells_run_on_their_routes(browser: Browser, server: dict[str, Any]) -> None:
    # The last window closing closes the project (the server's life): it is opened again.
    if call(server, "GET", "/project")["project"] is None:
        call(server, "POST", "/project/open", {"path": server["folder"]})
    path = call(server, "POST", "/powerapps/notebook/open", {})["path"]
    page = open_page(browser, server, f"notebooks?path={path}")
    sql = page.locator(".wb-cell.kind-sql")
    script = page.locator(".wb-cell.kind-typescript")
    expect(script.locator(".wb-cell-kind")).to_have_value("typescript")
    expect(page.locator(".wb-status")).to_be_visible()
    # The mode's kinds join the picker (a TSX cell is drawn by its route).
    offered = script.locator(".wb-cell-kind").evaluate("e => [...e.options].map(o => o.value)")
    assert "tsx" in offered
    sql.locator("button[aria-label='Run cell']").click()
    expect(sql.locator(".wb-result-table")).to_contain_text("region", timeout=60_000)
    script.locator("button[aria-label='Run cell']").click()
    result = script.locator(".wb-result")
    expect(result).to_contain_text("North", timeout=60_000)
    result.locator(".wb-to-grid").click()
    expect(page.locator(".note-corner")).to_contain_text("open on the Tables page")
    page.close()
