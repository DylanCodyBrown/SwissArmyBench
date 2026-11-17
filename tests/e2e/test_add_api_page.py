# ruff: noqa: F811
"""Add API in a real browser, against a made-up orders service on 127.0.0.1 (tests/api_standins.py;
made-up rows, a made-up key in a made-up vault): from an OpenAPI file, then from the form with the
AWS Lambda preset. Each writes its API_<name>.py and opens its connection's form, where the key is
pointed at the vault, tested and saved."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Locator, Page, Route, expect

from swissarmybench.client import push_client
from swissarmybench.domain import api_clients
from tests import api_standins as standin
from tests.api_standins import Service
from tests.e2e.test_ui import browser, call, demo_frame, grid_of, open_grid, server  # noqa: F401
from tests.e2e.test_workbench_page import seen_by_server

# The docs' pictures only when asked (SAB_SHOTS); otherwise a temporary folder, so a test run never writes
# into docs/screenshots.
SHOTS = Path(os.environ.get("SAB_SHOTS") or tempfile.mkdtemp(prefix="sab-add-api-shots-"))
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
    page.locator(".area-page").screenshot(path=str(SHOTS / name))


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


def open_add_api(page: Page) -> Locator:
    dialog = page.locator(".area-page[data-page='apis']")  # the APIs page (2026-11-17)
    page.locator(".nav-rail [data-area='apis']").click()
    page.get_by_role("button", name="Add API").click()
    expect(dialog.get_by_role("heading", name="Add API", exact=True)).to_be_visible()
    return dialog


def test_add_api_from_a_file_and_from_the_form(
    browser: Browser, january_url: str, server: dict[str, Any], service: Service, tmp_path: Path
) -> None:
    call(server, "POST", "/connections", VAULT)
    project = tmp_path / "shop"
    project.mkdir()
    document = service.openapi() | {"servers": [{"url": service.url + "/v1"}]}
    (project / "orders.openapi.json").write_text(json.dumps(document), encoding="utf-8")
    seen_by_server(server, project)
    page = open_grid(browser, january_url, width=1500, height=1400, device_scale_factor=2)

    # ===== from an OpenAPI file =====
    dialog = open_add_api(page)
    start = dialog.get_by_role("radiogroup", name="Start from")
    expect(start.get_by_role("radio")).to_have_text(
        ["I have an OpenAPI document", "I'll list the endpoints myself"]
    )
    start.get_by_role("radio", name="I have an OpenAPI document").click()
    expect(start.get_by_role("radio", name="I have an OpenAPI document")).to_have_attribute(
        "aria-checked", "true"
    )
    dialog.get_by_role("button", name="File…").click()
    choose(page, project, "orders.openapi.json")
    preview = dialog.locator(".add-api-preview")
    expect(preview.locator(".add-api-operations li")).to_have_count(5, timeout=30000)
    # This computer's library, whatever project is open (2026-11-17).
    expect(preview.locator(".add-api-file code")).to_contain_text("library/apis/Orders/API_Orders.py")
    made_at = Path(preview.locator(".add-api-file code").inner_text())
    expect(
        preview.locator(".add-api-operations li", has_text="list_orders()").locator(".badge")
    ).to_have_text("Table")
    expect(dialog.get_by_label("Name", exact=True)).to_have_value("Orders")
    # The document's own sign-in: its function key, in the header it names.
    expect(dialog.get_by_role("combobox", name="Sign in", exact=True).locator("option:checked")).to_have_text(
        "API key"
    )
    expect(dialog.get_by_label("Key name")).to_have_value("x-functions-key")
    expect(preview.locator(".add-api-variables code")).to_have_text(["ORDERS_API_KEY"])
    # Try it on a document's table: with no key typed and none on this computer, said by its name.
    expect(dialog.get_by_label("ORDERS_API_KEY")).to_have_attribute("type", "password")
    preview.get_by_role("button", name="Try list_orders").click()
    expect(preview.locator(".add-api-try .status-error")).to_contain_text("ORDERS_API_KEY", timeout=60000)
    shot(page, "add-api-from-a-file.png")
    dialog.get_by_role("button", name="Add", exact=True).click()

    # One step: the files are written in the library, and the API's explorer opens.
    expect(dialog.locator(".api-op[data-operation]")).to_have_count(5, timeout=30000)
    made = made_at.read_text(encoding="utf-8")
    assert api_clients.is_made(made) and standin.API_KEY not in made
    assert (made_at.parent / "openapi.json").is_file()
    assert standin.API_KEY not in dialog.inner_text()
    shot(page, "add-api-its-explorer.png")
    # Not on the Connections page: its one line points to the APIs page.
    page.locator(".nav-rail [data-area='connections']").click()
    connections = page.locator(".area-page[data-page='connections']")
    expect(connections.locator(".connections-apis-link")).to_be_visible()
    expect(connections.locator(".connection-card[data-connection='Orders']")).to_have_count(0)
    # An API is not on the Connections page (the owner, 2026-11-17: "APIs are connections but they dont get
    # the connection treatment here"); its tables are in SQL all the same.
    assert any(c["name"] == "Orders" for c in call(server, "GET", "/connections")["connections"])
    page.locator(".nav-rail [data-area='apis']").click()

    # ===== from the form, with the AWS Lambda preset: every field labelled, Try it, the key kept =====
    service.key_name = "x-api-key"
    page.get_by_role("button", name="Add API").click()
    dialog.get_by_role("radio", name="I'll list the endpoints myself").click()
    dialog.get_by_role("combobox", name="Hosted on").select_option(label="AWS Lambda")
    base = dialog.get_by_label("Base address")
    expect(base).to_have_value("https://<url id>.lambda-url.<region>.on.aws")
    base.fill(service.url + "/v1")
    dialog.get_by_label("Name", exact=True).fill("Shop")
    dialog.get_by_role("combobox", name="Sign in", exact=True).select_option(value="preset:1")  # its API key
    expect(dialog.get_by_label("Key name")).to_have_value("x-api-key")
    first = dialog.get_by_role("group", name="Endpoint 1")
    expect(first.get_by_role("combobox", name="Method")).to_have_value("GET")
    first.get_by_label("Path").fill("/products")
    expect(first.get_by_label("Columns to keep")).to_be_visible()
    dialog.get_by_role("button", name="Add an endpoint").click()
    second = dialog.get_by_role("group", name="Endpoint 2")
    second.get_by_label("Path").fill("/orders/{order_id}")
    second.get_by_label("Parameters").fill("fields")
    needed = second.get_by_role("group", name="Needed")
    expect(needed.get_by_role("checkbox", name="order_id")).to_be_checked()
    expect(needed.get_by_role("checkbox", name="order_id")).to_be_disabled()
    needed.get_by_role("checkbox", name="fields").check()
    second.get_by_role("checkbox", name="Read as a table").uncheck()
    expect(second.get_by_label("Columns to keep")).to_be_hidden()
    expect(second.get_by_role("button", name="Try it")).to_be_disabled()
    expect(preview.locator(".add-api-operations li")).to_have_count(2, timeout=30000)
    expect(preview.locator(".add-api-operations li").nth(1)).to_contain_text("get_orders_by_order_id()")
    expect(preview.locator(".add-api-file code")).to_contain_text("API_Shop.py")
    # The key typed once: Try it reads the first rows with it, and Add keeps it on this computer.
    dialog.get_by_label("SHOP_API_KEY").fill(standin.API_KEY)
    first.get_by_role("button", name="Try it").click()
    tried = first.locator(".add-api-try")
    expect(tried.locator(".status-ok")).to_have_text("It works: products, the first 2 rows.", timeout=60000)
    expect(tried.locator("th")).to_have_text(["sku", "price"])
    assert standin.API_KEY not in dialog.inner_text()
    shot(page, "add-api-from-the-form.png")
    path = Path(preview.locator(".add-api-file code").inner_text())
    # Add sends the typed key for the keyring. This sandbox has no keyring, so the test takes it out on
    # its way (and points the variable at the vault after): what the page sent is what is checked.
    sent: list[dict[str, Any]] = []

    def without_the_keyring(route: Route) -> None:
        body = json.loads(route.request.post_data or "{}")
        sent.append(body)
        rest = {k: v for k, v in body.items() if k not in ("variables", "secrets")}
        route.continue_(post_data=json.dumps(rest))

    page.route("**/apis", without_the_keyring)
    dialog.get_by_role("button", name="Add", exact=True).click()
    expect(dialog.locator(".api-op[data-operation]")).to_have_count(2, timeout=30000)
    page.unroute("**/apis")
    assert sent[0]["variables"] == [{"name": "SHOP_API_KEY", "from": "keyring"}]
    assert sent[0]["secrets"] == {"SHOP_API_KEY": standin.API_KEY}
    made = path.read_text(encoding="utf-8")
    assert "fields: str" in made and standin.API_KEY not in made  # needed: not Optional


UNLABELLED = """(root) => [...root.querySelectorAll('input, select, textarea')]
  .filter((e) => e.offsetParent !== null)
  .filter((e) => !(e.labels && e.labels.length))
  .filter((e) => !e.getAttribute('aria-label') && !e.getAttribute('aria-labelledby'))
  .map((e) => e.outerHTML.slice(0, 120))"""


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_field_of_add_api_is_labelled_in_light_and_dark(
    browser: Browser, january_url: str, dark: bool
) -> None:
    page = browser.new_context(
        viewport={"width": 1500, "height": 1400},
        device_scale_factor=2,
        color_scheme="dark" if dark else "light",
    ).new_page()
    page.goto(january_url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    theme = "dark" if dark else "light"
    dialog = open_add_api(page)
    form = dialog.locator(".add-api")
    shot(page, f"add-api-start-{theme}.png")
    dialog.get_by_role("radio", name="I have an OpenAPI document").click()
    assert form.evaluate(UNLABELLED) == []
    dialog.get_by_role("radio", name="I'll list the endpoints myself").click()
    dialog.get_by_role("combobox", name="Hosted on").select_option(label="Azure Function App")
    dialog.get_by_label("Base address").fill("https://orders-made-up.azurewebsites.net/api")
    dialog.get_by_label("Name", exact=True).fill("Stock")  # a name the library has not (one per computer)
    dialog.get_by_role("group", name="Endpoint 1").get_by_label("Path").fill("/orders")
    dialog.get_by_role("group", name="Endpoint 1").get_by_label("Parameters").fill("status, limit")
    expect(dialog.locator(".add-api-preview .add-api-operations li")).to_have_count(1, timeout=30000)
    assert form.evaluate(UNLABELLED) == []
    shot(page, f"add-api-one-endpoint-{theme}.png")
    for path, parameters in (("/orders/{order_id}", "fields"), ("/clients", "")):
        dialog.get_by_role("button", name="Add an endpoint").click()
        card = dialog.locator(".add-api-endpoint").last
        card.get_by_label("Path").fill(path)
        card.get_by_label("Parameters").fill(parameters)
    dialog.locator(".add-api-endpoint").nth(1).get_by_role("combobox", name="Method").select_option("POST")
    expect(dialog.locator(".add-api-preview .add-api-operations li")).to_have_count(3, timeout=30000)
    assert form.evaluate(UNLABELLED) == []
    shot(page, f"add-api-three-endpoints-{theme}.png")
    # A narrow window: nothing runs off the side.
    page.set_viewport_size({"width": 560, "height": 1400})
    body = dialog.locator(".add-api")
    assert body.evaluate("(e) => e.scrollWidth <= e.clientWidth + 1")
    shot(page, f"add-api-narrow-{theme}.png")
