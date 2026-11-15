# ruff: noqa: F811
"""Add API in a real browser, against a made-up orders service on 127.0.0.1 (tests/api_standins.py;
made-up rows, a made-up key in a made-up vault): from an OpenAPI file, then from the form with the
AWS Lambda preset. Each writes its API_<name>.py and opens its connection's form, where the key is
pointed at the vault, tested and saved."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from swissarmybench.client import push_client
from swissarmybench.domain import api_clients
from tests import api_standins as standin
from tests.api_standins import Service
from tests.e2e.test_ui import browser, call, demo_frame, grid_of, open_grid, server  # noqa: F401
from tests.e2e.test_workbench_page import seen_by_server

SHOTS = Path(os.environ.get("SAB_SHOTS", Path(__file__).resolve().parents[2] / "docs" / "screenshots"))
VAULT = {
    "name": "Team vault",
    "kind": "vault",
    "template": "azure_key_vault",
    "variable": "get",
    "code": f'values = {{"orders-api-key": "{standin.API_KEY}", "other": "made-up"}}\n\n\n'
    "def names():\n    return list(values)\n\n\ndef get(name):\n    return values[name]\n",
    "vault_mapping": [{"env": "OTHER", "secret": "other"}],
}


@pytest.fixture(scope="module")
def service() -> Iterator[Service]:
    running = Service("api_key_header").start()
    running.key_name = "x-functions-key"
    yield running
    running.stop()


@pytest.fixture
def january_url(server: dict[str, Any]) -> Iterator[str]:
    url = push_client.push(demo_frame(40), name="january", new_grid=True)
    yield url
    call(server, "DELETE", f"/grids/{grid_of(url)}")


def shot(page: Page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.locator("dialog").screenshot(path=str(SHOTS / name))


def choose(page: Page, folder: Path, file: str | None = None) -> None:
    chooser = page.locator(".file-chooser")
    where = chooser.locator("input[aria-label=Folder]")
    where.fill(str(folder))
    where.press("Enter")
    if file:
        chooser.locator(".file-row.file", has_text=file).click()
    else:
        chooser.get_by_role("button", name="Choose this folder").click()


def key_from_the_vault(dialog: Locator, variable: str) -> None:
    """The connection's form, after Add: the key the client reads comes from the made-up vault."""
    row = dialog.locator(".python-variable", has_text=variable)
    expect(row).to_contain_text("Not set on this computer", timeout=30000)
    dialog.get_by_role("combobox", name=f"Where {variable} comes from").select_option("vault")
    entry = dialog.get_by_role("combobox", name=f"{variable}: the entry in the vault")
    expect(entry.locator("option", has_text="orders-api-key")).to_have_count(1, timeout=30000)
    entry.select_option("orders-api-key")


def test_add_api_from_a_file_and_from_the_form(
    browser: Browser, january_url: str, server: dict[str, Any], service: Service, tmp_path: Path
) -> None:
    call(server, "POST", "/connections", VAULT)
    project = tmp_path / "shop"
    project.mkdir()
    document = service.openapi() | {"servers": [{"url": service.url + "/v1"}]}
    (project / "orders.openapi.json").write_text(json.dumps(document), encoding="utf-8")
    seen_by_server(server, project)
    page = open_grid(browser, january_url, width=1500, height=1000, device_scale_factor=2)
    dialog = page.locator("dialog")

    # ===== from an OpenAPI file =====
    page.locator(".app-row").get_by_role("button", name="Connections").click()
    page.get_by_role("button", name="Add API").click()
    expect(dialog.locator("h3")).to_have_text("Add API")
    dialog.get_by_role("button", name="File…").click()
    choose(page, project, "orders.openapi.json")
    dialog.get_by_role("textbox", name="Folder").fill(str(project))
    dialog.get_by_role("textbox", name="Folder").press("Tab")
    preview = dialog.locator(".add-api-preview")
    expect(preview.locator(".add-api-operations li")).to_have_count(5, timeout=30000)
    expect(preview.locator(".add-api-file code")).to_have_text(str(project / "API_Orders.py"))
    expect(
        preview.locator(".add-api-operations li", has_text="list_orders()").locator(".badge")
    ).to_have_text("Table")
    expect(dialog.get_by_role("textbox", name="Name", exact=True)).to_have_value("Orders")
    # The document's own sign-in: its function key, in the header it names.
    expect(dialog.get_by_role("combobox", name="Sign in").locator("option:checked")).to_have_text("API key")
    expect(dialog.locator(".add-api-auth input[aria-label='Key name']")).to_have_value("x-functions-key")
    expect(preview.locator(".add-api-variables code")).to_have_text(["ORDERS_API_KEY"])
    shot(page, "add-api-from-a-file.png")
    dialog.get_by_role("button", name="Add", exact=True).click()

    # One step: the file is written, and the connection's own form opens.
    expect(dialog.locator("h3")).to_have_text("Edit Orders", timeout=30000)
    made = (project / "API_Orders.py").read_text(encoding="utf-8")
    assert api_clients.is_made(made) and standin.API_KEY not in made
    key_from_the_vault(dialog, "ORDERS_API_KEY")
    dialog.get_by_role("button", name="Test connection").click()
    result = dialog.locator(".connection-result")
    expect(result.locator(".status-ok")).to_have_text("It works: 3 tables, 6 columns.", timeout=60000)
    expect(result.locator(".connection-preview th")).to_have_text(["order_id", "amount", "status"])
    shot(page, "add-api-its-connection.png")
    dialog.get_by_role("button", name="Save").click()
    row = dialog.locator(".connection-row", has_text="Orders")
    expect(row.locator(".badge")).to_have_text("Python (your own code)")
    assert standin.API_KEY not in dialog.inner_text()

    # ===== from the form, with the AWS Lambda preset =====
    service.key_name = "x-api-key"
    page.get_by_role("button", name="Add API").click()
    dialog.get_by_role("combobox", name="Preset").select_option(label="AWS Lambda")
    base = dialog.get_by_role("textbox", name="Base URL")
    expect(base).to_have_value("https://<url id>.lambda-url.<region>.on.aws")
    expect(dialog.get_by_role("button", name="Endpoints")).to_have_attribute("aria-pressed", "true")
    base.fill(service.url + "/v1")
    dialog.get_by_role("textbox", name="Name", exact=True).fill("Shop")
    dialog.get_by_role("combobox", name="Sign in").select_option(value="preset:1")  # its API key
    expect(dialog.locator(".add-api-auth input[aria-label='Key name']")).to_have_value("x-api-key")
    dialog.get_by_role("textbox", name="Path").fill("/products")
    dialog.get_by_role("button", name="Endpoint", exact=True).click()
    dialog.get_by_role("textbox", name="Path").last.fill("/orders/{order_id}")
    dialog.get_by_role("checkbox", name="Table").last.uncheck()
    expect(preview.locator(".add-api-operations li")).to_have_count(2, timeout=30000)
    expect(preview.locator(".add-api-operations li").nth(1)).to_contain_text("get_orders_by_order_id()")
    expect(preview.locator(".add-api-file code")).to_contain_text("API_Shop.py")
    shot(page, "add-api-from-the-form.png")
    dialog.get_by_role("button", name="Add", exact=True).click()
    expect(dialog.locator("h3")).to_have_text("Edit Shop", timeout=30000)
    key_from_the_vault(dialog, "SHOP_API_KEY")
    dialog.get_by_role("button", name="Test connection").click()
    expect(result.locator(".status-ok")).to_have_text("It works: 1 table, 2 columns.", timeout=60000)
    dialog.get_by_role("button", name="Save").click()
    expect(dialog.locator(".connection-row", has_text="Shop")).to_have_count(1)
    opened = call(
        server, "POST", "/connections/Shop/open", {"schema": "api", "table": "products"}, agent=True
    )
    assert opened["shown"] == 2
