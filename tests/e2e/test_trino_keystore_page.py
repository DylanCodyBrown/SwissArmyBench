# ruff: noqa: F811
"""Trino's client certificate in a real browser, against a made-up Trino on this computer that lets no
one in without one (tests/trino_standin.py; made-up keys, certificates and keystores): the form's Sign
in offers the keystore, its path is typed as a plain path or a variable (this
computer's path its default), the password is a secret, and Test signs in with the certificate."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from tests import trino_standin as made_up
from tests.e2e.test_ui import browser, call, open_grid, orders_url, server  # noqa: F401

pytest.importorskip("trino", reason="the trino client is not installed in this Python")
SHOTS = os.environ.get("SAB_SHOTS")  # a folder: the screenshots are written there too


@pytest.fixture(scope="module")
def standin(tmp_path_factory: pytest.TempPathFactory) -> Iterator[made_up.StandIn]:
    running = made_up.StandIn(made_up.material(), tmp_path_factory.mktemp("trino")).start()
    yield running
    running.stop()


def test_the_keystore_sign_in_maps_its_path_to_a_variable_and_signs_in(
    browser: Browser, orders_url: str, server: dict[str, Any], standin: made_up.StandIn
) -> None:
    keystore = standin.folder / "lake.keystore"
    keystore.write_bytes(made_up.pkcs12_bytes(standin.m))  # the bytes say PKCS#12, not the name
    page = open_grid(browser, orders_url, width=1400, height=1300, device_scale_factor=2)
    dialog = page.locator(".area-page[data-page='connections']")
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").click()
    page.locator(".connection-type", has_text="Trino").click()
    sign_in = dialog.get_by_role("combobox", name="Sign in")
    expect(sign_in.locator("option")).to_have_text(["Username and password", "Client certificate (keystore)"])
    sign_in.select_option(label="Client certificate (keystore)")
    code = dialog.locator("textarea.connection-code")
    expect(code).to_have_value(re.compile(r"CertificateAuthentication"))
    dialog.get_by_role("textbox", name="Name", exact=True).fill("Lake")
    for label, value in (
        ("Server", "127.0.0.1"),
        ("Port", str(standin.port)),
        ("User", "lake_reader"),
        ("Keystore", str(keystore)),
        ("Certificate file", str(standin.ca_file)),
    ):
        box = dialog.get_by_label(label, exact=True)
        box.fill(value)
        box.press("Tab")
        expect(code).to_have_value(re.compile(re.escape(value)))
    keystore_field = dialog.locator(".field").filter(has=page.get_by_label("Keystore", exact=True))
    expect(keystore_field.get_by_role("button", name="Browse…")).to_be_visible()  # the file chooser
    # One box each (12.7): a path, or a variable with this computer's path as its default; no "from" pickers.
    expect(dialog.get_by_role("combobox", name="Keystore from")).to_have_count(0)
    keystore_box = dialog.get_by_label("Keystore", exact=True)
    keystore_box.fill("${TRINO_KEYSTORE_PATH:-" + str(keystore) + "}")
    keystore_box.press("Tab")
    expect(code).to_have_value(
        re.compile(re.escape(f'keystore = os.environ.get("TRINO_KEYSTORE_PATH", r"{keystore}")'))
    )
    # The password: typed for a test, never in the code.
    expect(dialog.get_by_role("combobox", name=re.compile("Where .* comes from"))).to_have_count(0)
    password = dialog.get_by_label("Password", exact=True)
    password.fill(made_up.PASSWORD)
    dialog.get_by_role("button", name="Test connection").click()
    expect(dialog.locator(".connection-result .status-ok")).to_contain_text("It works", timeout=60000)
    assert {s["client"] for s in standin.seen} == {made_up.CLIENT}
    assert made_up.PASSWORD not in code.input_value()
    if SHOTS:
        dialog.screenshot(path=str(Path(SHOTS) / "trino-keystore-form.png"))
    # Back to a plain path: the code says the path again.
    keystore_box.fill(str(keystore))
    keystore_box.press("Tab")
    expect(code).to_have_value(re.compile(re.escape(f'keystore = r"{keystore}"')))
    page.close()
