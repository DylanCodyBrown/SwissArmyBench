"""App registrations (domain/app_registrations.py, services/app_registrations.py): a library item of three
variable
names, and its access report against tests/powerbi_standin.py (service principal sign-in, workspaces seen or
not, the tenant setting's refusal). Made-up values only; no secret is ever answered or kept."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import app_registrations as rules
from swissarmybench.domain import sql_server
from tests import powerbi_standin as made_up
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture
def standin(monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def await_state(ctx: Any) -> Any:
    """context.md's facts as the app gathers them now."""
    import asyncio

    return asyncio.run(ctx.context_md.state())


REG = {"name": "Contoso BI", "tenant": "BI_TENANT", "client": "BI_CLIENT", "secret": "BI_SECRET"}


def test_a_registration_is_three_variable_names_in_a_stable_file() -> None:
    reg = rules.check(REG | {"secret": "${BI_SECRET}"})
    assert reg.variables() == ("BI_TENANT", "BI_CLIENT", "BI_SECRET")
    text = rules.write(reg)
    assert rules.read(text) == reg and rules.write(rules.read(text)) == text
    assert rules.file_name("Contoso BI") == "contoso-bi.toml"
    with pytest.raises(rules.RegistrationError, match="client secret"):
        rules.check(REG | {"secret": "not a name!"})


def test_refusals_in_plain_words_and_one_line() -> None:
    assert "client secret" in rules.sign_in_refused(401, "AADSTS7000215: Invalid client secret")
    reason, _fix = rules.powerbi_refused(401, "PowerBINotAuthorizedException", "Sales")
    assert "Service principals can call Fabric public APIs" in reason
    assert (
        rules.powerbi_refused(404, "PowerBIEntityNotFound", "Sales")[1]
        == "Add it to the Sales workspace as Viewer"
    )
    items = [rules.Access("Power BI", "Sales model", True), rules.Access("Power BI", "Budget", False)]
    assert rules.one_line(items) == "✓ 1, ✗ 1 (Budget)"
    report = rules.Report("Contoso BI", "2026-11-19T10:00:00Z", "pc", {}, tuple(items))
    assert rules.read_report(rules.write_report(report)) == report


def test_the_access_report_and_a_connections_access_section(tmp_path: Path, standin: made_up.StandIn) -> None:
    with make_client(tmp_path) as client:
        ctx: Any = client.app.state.ctx  # type: ignore[attr-defined]
        ctx.app_registrations.query_hints = lambda: {"Sales model": "Sales"}
        for name, value, where in (
            ("BI_TENANT", made_up.TENANT, "value"),
            ("BI_CLIENT", made_up.CLIENT, "value"),
            ("BI_SECRET", made_up.SECRET, "keyring"),
        ):
            ok(client.put("/variables", json={"name": name, "value": value, "from": where}, headers=AUTH))
        added = ok(client.post("/app-registrations", json=REG, headers=AGENT))
        file = Path(ctx.app_registrations._files.folder()) / "contoso-bi.toml"
        assert added["file"] == "app-registrations/contoso-bi.toml" and file.is_file()
        assert made_up.SECRET not in file.read_text()

        # A SQL Server connection signing in with its variables: one of its users.
        code = sql_server.code("app_secret", "sql01.contoso.example")
        code = code.replace('"my-tenant-id"', 'os.environ["BI_TENANT"]').replace(
            '"my-client-id"', 'os.environ["BI_CLIENT"]'
        )
        code = "import os\n" + code.replace('secret("client secret")', 'os.environ["BI_SECRET"]')
        body = {
            "name": "Warehouse",
            "kind": "sql",
            "template": "sqlserver",
            "dialect": "sqlserver",
            "code": code,
        }
        ok(client.post("/connections", json=body, headers=AUTH))
        assert ok(client.get("/app-registrations", headers=AGENT))["registrations"][0]["used_by"] == [
            "Warehouse"
        ]

        report = ok(client.post("/app-registrations/Contoso%20BI/check", headers=AGENT))["report"]
        marks = {(i["area"], i["target"]): i["mark"] for i in report["items"]}
        assert marks[("Sign-in", "Contoso BI")] == "✓"
        assert marks[("Power BI", "the Finance workspace")] == "✓"
        assert marks[("Power BI", "Sales model")] == "✓"  # one COUNTROWS, its answer not kept
        assert marks[("Connection", "Warehouse")] == "not checked"
        assert made_up.SECRET not in str(report) and made_up.TOKEN not in str(report)
        access = ok(client.get("/connections/Warehouse/access", headers=AGENT))["access"][0]
        assert access["registration"] == "Contoso BI" and access["line"] == "1 not checked"
        facts = await_state(ctx)
        warehouse = next(c for c in facts.connections if c.name == "Warehouse")
        assert warehouse.access and warehouse.access[0].startswith("`Contoso BI`: 1 not checked, checked 20")

        # The tenant setting off: the plain reason and the fix.
        standin.tenant_setting_off = True
        report = ok(client.post("/app-registrations/Contoso%20BI/check", headers=AGENT))["report"]
        sales = next(i for i in report["items"] if i["target"] == "Sales model")
        assert sales["mark"] == "✗" and "Service principals can call Fabric public APIs" in sales["reason"]
        # Not a member of any workspace.
        standin.tenant_setting_off, standin.not_a_member = False, True
        report = ok(client.post("/app-registrations/Contoso%20BI/check", headers=AGENT))["report"]
        assert any(i["mark"] == "✗" and "no workspace" in i["reason"] for i in report["items"])
        # A wrong secret: the sign-in refused in plain words.
        ok(
            client.put(
                "/variables", json={"name": "BI_SECRET", "value": "wrong", "from": "keyring"}, headers=AUTH
            )
        )
        report = ok(client.post("/app-registrations/Contoso%20BI/check", headers=AGENT))["report"]
        assert report["items"][0]["mark"] == "✗" and "client secret" in report["items"][0]["reason"]
        audit = (tmp_path / "state").rglob("audit*")
        assert any("app_registration_check" in p.read_text() for p in audit if p.is_file())
