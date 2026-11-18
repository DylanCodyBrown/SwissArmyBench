"""Set up from the meta store (domain/library_setup.py; the owner, 2026-11-18: "Connections are shared and
the vault env vars are shared as well so minimal setup is required for new people"). A made-up team meta
store with two key vaults (one this computer can read, one it cannot), keyring and local variables with no
value here, and a connection whose password is in the teammate's keyring: the checklist's items and counts,
each fix, and Move to a vault so the next person needs nothing. Made-up data only."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring

OPEN_VAULT = """values = {"sales-db-password": "made-up-not-real", "report-key": "made-up"}


def names():
    return list(values)


def get(name):
    return values[name]
"""
LOCKED_VAULT = """def names():
    raise RuntimeError("DefaultAzureCredential failed: please run 'az login' to set up an account.")


def get(name):
    raise RuntimeError("not signed in")
"""


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def sqlite(name: str, secret: str) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": f'import sqlite3\nassert secret("{secret}")\nconn = sqlite3.connect(":memory:")\n',
    }


def team(client: TestClient) -> None:
    """The teammate's computer: what their meta store holds."""
    for name, code, mapping in (
        ("Finance Vault", OPEN_VAULT, [{"env": "SALES_DB_PASSWORD", "secret": "sales-db-password"}]),
        ("Locked Vault", LOCKED_VAULT, [{"env": "LEDGER_PASSWORD", "secret": "ledger-password"}]),
    ):
        body = {"name": name, "kind": "vault", "template": "azure_key_vault", "code": code, "variable": "get"}
        ok(client.post("/connections", json=body | {"vault_mapping": mapping}, headers=AUTH))
    ok(client.post("/connections", json=sqlite("Sales DB", "SALES_DB_PASSWORD"), headers=AUTH))
    ok(client.post("/connections", json=sqlite("Ledger", "LEDGER_PASSWORD"), headers=AUTH))
    warehouse = sqlite("Warehouse", "password") | {"secrets": {"password": "made-up-keyring-pa55"}}
    ok(client.post("/connections", json=warehouse, headers=AUTH))
    ok(
        client.put(
            "/variables",
            json={"name": "SHOP_TOKEN", "value": "made-up-t0ken", "from": "keyring"},
            headers=AUTH,
        )
    )
    local: dict[str, Any] = {"name": "DATA_FOLDER", "value": "/made-up/data", "local": True}
    ok(client.put("/variables", json=local, headers=AUTH))


def test_a_new_persons_checklist_its_fixes_and_move_to_a_vault(tmp_path: Path) -> None:
    with make_client(tmp_path / "teammate") as client:
        team(client)
        theirs = ok(client.get("/library/setup?check=1", headers=AUTH))
        warehouse = next(c for c in theirs["connections"] if c["name"] == "Warehouse")
        # Its password is in this computer's keyring: the owner of the meta store is offered a vault.
        assert warehouse["move_to_vault"] == [
            {"secret": "password", "vaults": ["Finance Vault"], "label": "Move to a vault"}
        ]
    clone = tmp_path / "clone"
    shutil.copytree(
        tmp_path / "teammate" / "state" / "library", clone, ignore=shutil.ignore_patterns("local")
    )

    with memory_keyring(), make_client(tmp_path / "newcomer") as client:
        ok(client.put("/library", json={"folder": str(clone)}, headers=AUTH))
        found = ok(client.get("/library/setup?check=1", headers=AGENT))
        assert found["heading"] == "Set up from the meta store"
        vaults = {v["name"]: v for v in found["vaults"]}
        assert vaults["Finance Vault"]["state"] == "ready" and vaults["Finance Vault"]["gives"].endswith(
            "1 variable"
        )
        locked = vaults["Locked Vault"]
        assert locked["state"] == "sign_in" and locked["fix"]["label"] == "Sign in to Azure"
        assert "az login" in locked["error"] and locked["gives"] == "Sign in to Azure gives 1 variable"
        values = {(v["kind"], v["name"]) for v in found["values"]}
        assert values == {("keyring", "SHOP_TOKEN"), ("local", "DATA_FOLDER"), ("password", "password")}
        states = {c["name"]: (c["state"], c["words"]) for c in found["connections"]}
        # Its password comes from a vault read here; SQLite is a file on this disk: the rule says so.
        assert states["Sales DB"][0] == "local" and states["Sales DB"][1].startswith(
            "Only works on your machine: "
        )
        assert states["Ledger"] == ("needs", "Needs a sign-in to Locked Vault")
        assert states["Warehouse"] == ("needs", "Needs its password password")
        assert (found["count"], found["words"]) == (4, "4 things to set up")
        assert "made-up" not in str(found)  # names and words only, never a value

        # Each fix, typed once: the password into the keyring, the variables through the Variables page.
        ok(client.put("/blades/Warehouse/secrets", json={"password": "made-up-keyring-pa55"}, headers=AUTH))
        body = {"name": "SHOP_TOKEN", "value": "made-up-t0ken", "from": "keyring"}
        ok(client.put("/variables", json=body, headers=AUTH))
        ok(
            client.put(
                "/variables",
                json={"name": "DATA_FOLDER", "value": "/made-up/here", "local": True},
                headers=AUTH,
            )
        )
        after = ok(client.get("/library/setup", headers=AUTH))
        assert (after["count"], after["words"]) == (1, "1 thing to set up")  # the Locked Vault's sign-in

    # The teammate moves Warehouse's password to the Finance Vault: the next person needs nothing for it.
    with make_client(tmp_path / "teammate") as client:
        moved = ok(
            client.post(
                "/library/setup/move-to-vault",
                json={
                    "connection": "Warehouse",
                    "secret": "password",
                    "vault": "Finance Vault",
                    "vault_secret": "warehouse-password",
                },
                headers=AGENT,
            )
        )
        assert moved["vault"] == "Finance Vault"
        vault = ok(client.get("/connections/Finance%20Vault", headers=AUTH))
        assert {"env": moved["secret"], "secret": "warehouse-password"} in vault["vault_mapping"]
        code = ok(client.get("/blades/Warehouse", headers=AUTH))["code"]
        assert f'secret("{moved["secret"]}")' in code
