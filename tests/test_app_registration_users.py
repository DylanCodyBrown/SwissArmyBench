"""An app registration's users (services/app_registrations.py AppRegistrations over its ports): the
connections whose code reads its three variables, each read as the kind its check takes. The rule that was the
composition root's closure. Made-up names only."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from swissarmybench.domain import app_registrations as rules
from swissarmybench.domain.blades import Blade
from swissarmybench.services.app_registrations import AppRegistrations

FINANCE = rules.Registration("Finance app", "FIN_TENANT", "FIN_CLIENT", "FIN_SECRET")
SIGNS_IN = "tenant = FIN_TENANT; client = FIN_CLIENT; secret = FIN_SECRET"


class Files:
    def all(self) -> list[rules.Registration]:
        return [FINANCE]

    def report(self, name: str) -> rules.Report | None:
        return None


BLADES = {
    "Sales model": Blade("Sales model", "sql", code=SIGNS_IN, dialect="dax"),
    "Ledger": Blade("Ledger", "sql", code=SIGNS_IN, template="azuresql"),
    "Notes": Blade("Notes", "other", code=SIGNS_IN),
    "Orders": Blade("Orders", "sql", code="no sign-in here", template="postgres"),
}


def blade(name: str) -> Blade:
    if name not in BLADES:
        raise LookupError(name)
    return BLADES[name]


def registrations() -> AppRegistrations:
    rows = [{"name": "Sales model"}, {"name": "Ledger"}, {"name": "Notes", "connection": "python"}]
    rows += [{"name": "Orders"}, {"name": "Gone"}]  # a connection that cannot be read is not counted
    ws: Any = SimpleNamespace()
    files: Any = Files()
    probe: Any = None
    return AppRegistrations(ws, files, probe, lambda names: {}, lambda: rows, blade)


def test_the_kind_a_registration_s_check_reads_a_connection_as() -> None:
    assert rules.connection_kind("dax", "powerbi_workspace", "database") == "powerbi"
    assert rules.connection_kind("tsql", "azuresql", "database") == "sqlserver"
    assert rules.connection_kind(None, "dataverse", "database") == "dataverse"
    assert rules.connection_kind(None, None, "python") == "python"
    assert rules.connection_kind(None, None, None) == ""


def test_a_registration_s_users_are_the_connections_that_read_its_variables() -> None:
    made = registrations()
    assert made._connections() == [
        ("Sales model", "powerbi", SIGNS_IN),
        ("Ledger", "sqlserver", SIGNS_IN),
        ("Notes", "python", SIGNS_IN),
        ("Orders", "postgres", "no sign-in here"),
    ]
    assert made.listing()["registrations"][0]["used_by"] == ["Sales model", "Ledger", "Notes"]
