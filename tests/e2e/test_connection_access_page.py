# ruff: noqa: F811
"""A connection's Access section on the Connections page, in a real browser: an app registration signs a
made-up SQL Server connection in, its access report is made against tests/powerbi_standin.py, and the card's
detail shows what it reaches, when that was checked and by which registration, and Check again. Made-up data
only.

With SWISSARMYBENCH_SHOTS set to a folder, the test also saves screenshots there (2x, light and dark)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from swissarmybench.domain import sql_server
from tests import powerbi_standin as made_up
from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_SHOTS", "") or None
ROOT = Path(__file__).resolve().parents[2]
REG = {"name": "Contoso BI", "tenant": "BI_TENANT", "client": "BI_CLIENT", "secret": "BI_SECRET"}


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("connection_access")
    standin = made_up.StandIn().start()
    env_ = (
        os.environ
        | standin.environment()
        | {
            "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
            "SWISSARMYBENCH_STATE": str(tmp / "state"),
            "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
            "SWISSARMYBENCH_EXTENSIONS": "streamlit",
            "PYTHON_KEYRING_BACKEND": "tests.file_keyring.FileKeyring",
            "SAB_TEST_KEYRING_FILE": str(tmp / "keyring.json"),
            "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]).strip(os.pathsep),
        }
    )
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env_)
    for _ in range(150):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    else:
        process.kill()
        standin.stop()
        raise AssertionError("server did not start")
    yield info | {"tmp": tmp}
    process.terminate()
    process.wait(timeout=20)
    standin.stop()


def _warehouse_code() -> str:
    code = sql_server.code("app_secret", "sql01.contoso.example")
    code = code.replace('"my-tenant-id"', 'os.environ["BI_TENANT"]').replace(
        '"my-client-id"', 'os.environ["BI_CLIENT"]'
    )
    return "import os\n" + code.replace('secret("client secret")', 'os.environ["BI_SECRET"]')


def test_a_connections_access_section(browser: Browser, server: dict[str, Any]) -> None:
    for name, value, where in (
        ("BI_TENANT", made_up.TENANT, "value"),
        ("BI_CLIENT", made_up.CLIENT, "value"),
        ("BI_SECRET", "wrong", "keyring"),
    ):
        call(server, "PUT", "/variables", {"name": name, "value": value, "from": where})
    call(server, "POST", "/app-registrations", REG)
    body = {"name": "Warehouse", "kind": "sql", "template": "sqlserver", "dialect": "sqlserver"}
    call(server, "POST", "/connections", body | {"code": _warehouse_code()})
    call(server, "POST", "/app-registrations/Contoso%20BI/check", {})  # a wrong secret: refused, in words
    base = f"http://127.0.0.1:{server['port']}"
    for scheme in ("light", "dark"):
        context = browser.new_context(
            viewport={"width": 1400, "height": 900}, device_scale_factor=2, color_scheme=scheme
        )
        page = context.new_page()
        page.goto(f"{base}/workspace?open=connections&at=detail&name=Warehouse#token={server['token']}")
        section = page.locator("section.connection-access")
        expect(section).to_be_visible(timeout=20000)
        expect(section.locator(".connection-access-line")).to_contain_text("Contoso BI")
        expect(section.locator(".connection-access-when")).to_contain_text("Last checked")
        if scheme == "light":
            expect(section.locator(".access-refused").first).to_contain_text("client secret")
            # The right secret, then Check again: the sign-in now reaches, without leaving the page.
            secret = {"name": "BI_SECRET", "value": made_up.SECRET, "from": "keyring"}
            call(server, "PUT", "/variables", secret)
            section.get_by_role("button", name="Check again").click()
            expect(section.locator(".access-ok").first).to_contain_text("Contoso BI", timeout=20000)
        if SHOTS:
            Path(SHOTS).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(SHOTS) / f"connection-access-{scheme}.png"))
        context.close()
    context_md = call(server, "GET", "/claude/context", None, agent=True)
    assert "access: `Contoso BI`" in json.dumps(context_md)
