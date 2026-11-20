"""One name, one variable (the owner, 2026-11-20: "make sure that we handle env variable collisions by not
allowing duplicate variables, and if any overlap in the vault then they get prefixed by the vault name").
Made-up vaults only (tests/test_vault_names.py's: names() reads a made-up file)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from starlette.testclient import TestClient

from swissarmybench.domain import vault_names as rules
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_vault_names import MADE_UP_VALUE, every_vault, from_vaults, no_value_written, vault_code


def test_names_are_given_once_a_taken_one_prefixed_with_its_vault() -> None:
    team = rules.VaultIn("Team Vault", {}, True, ["warehouse-password", "api-key"])
    finance = rules.VaultIn("Finance", {}, True, ["warehouse-password", "SHOP_TOKEN"])
    mapped = rules.VaultIn("Ops", {"SHOP_TOKEN": "shop-token"}, False)
    reserved = rules.reserved(["api_key"], [team, finance, mapped])
    assert reserved == {"api_key": rules.YOURS, "SHOP_TOKEN": "Ops"}
    given = rules.assign([team, finance, mapped], reserved)
    # Finance sorts first: it keeps warehouse_password, Team Vault's is prefixed, and so is its api_key (your
    # variable keeps the plain name); Ops's own entry is its own, so Finance's SHOP_TOKEN is prefixed.
    assert given["Finance"].mapping == {
        "FINANCE_SHOP_TOKEN": "SHOP_TOKEN",
        "warehouse_password": "warehouse-password",
    }
    assert given["Team Vault"].mapping == {
        "TEAM_VAULT_api_key": "api-key",
        "TEAM_VAULT_warehouse_password": "warehouse-password",
    }
    assert given["Team Vault"].notes["TEAM_VAULT_api_key"] == ("api_key", rules.YOURS)
    assert given["Team Vault"].notes["TEAM_VAULT_warehouse_password"] == ("warehouse_password", "Finance")
    assert given["Ops"].mapping == {"SHOP_TOKEN": "shop-token"}
    assert rules.assign([mapped, finance, team], reserved) == given  # any order: the same names
    # A name given before is kept while free: a new vault sorting first does not take it.
    kept = rules.VaultIn("Team Vault", {}, True, ["x-key"], {"x-key": "x_key"})
    again = rules.assign([kept, rules.VaultIn("Alpha", {}, True, ["x-key"])], {})
    assert again["Team Vault"].mapping == {"x_key": "x-key"}
    assert again["Alpha"].mapping == {"ALPHA_x_key": "x-key"}
    # Prefixed and taken too: a number after it.
    taken = {"TEAM_VAULT_k": rules.YOURS, "k": rules.YOURS}
    one = rules.assign([rules.VaultIn("Team Vault", {}, True, ["k"])], taken)
    assert one["Team Vault"].mapping == {"TEAM_VAULT_k_2": "k"}
    # Already given out, a name stays with its vault when another arrives (it never jumps), even one that
    # sorts first: that one is prefixed.
    arrived = rules.assign(
        [
            rules.VaultIn("Team Vault", {}, True, ["k"], {"k": "k"}),
            rules.VaultIn("Finance", {}, True, ["k"]),
        ],
        {},
    )
    assert arrived["Team Vault"].mapping == {"k": "k"} and arrived["Finance"].mapping == {"FINANCE_k": "k"}
    assert rules.prefix_of("Team Vault") == "TEAM_VAULT" and rules.prefix_of("2024 keys") == "_2024_KEYS"


def variables_of(client: TestClient) -> dict[str, dict[str, Any]]:
    return {v["name"]: v for v in client.get("/variables", headers=AUTH).json()["variables"]}


def test_two_vaults_and_a_keyring_variable_never_share_a_name(tmp_path: Path) -> None:
    team_names, finance_names = tmp_path / "team.json", tmp_path / "finance.json"
    team_names.write_text(json.dumps(["warehouse-password", "SHOP_API_TOKEN"]))
    finance_names.write_text(json.dumps(["warehouse-password"]))
    with memory_keyring(), make_client(tmp_path) as client:
        body = {"name": "SHOP_API_TOKEN", "value": MADE_UP_VALUE, "from": "keyring"}
        assert client.put("/variables", json=body, headers=AUTH).status_code == 200
        for path, name in ((finance_names, "Finance"), (team_names, "Team Vault")):
            assert client.post("/connections", json=every_vault(path, name), headers=AUTH).status_code == 200
            client.post("/connections/vaults/secrets", json={"name": name}, headers=AUTH)
        found = variables_of(client)
        assert found["warehouse_password"]["vault"] == "Finance"
        prefixed = found["TEAM_VAULT_warehouse_password"]
        assert prefixed["vault"] == "Team Vault" and prefixed["vault_secret"] == "warehouse-password"
        assert prefixed["note"] == (
            "named TEAM_VAULT_warehouse_password: warehouse_password was taken by Finance"
        )
        assert found["SHOP_API_TOKEN"]["from"] == "keyring"  # yours keeps it
        assert found["TEAM_VAULT_SHOP_API_TOKEN"]["vault"] == "Team Vault"
        # Adding or renaming to a name a vault gives: refused, the one sentence, the agent alike.
        clash = client.put("/variables", json={"name": "warehouse_password", "value": "x"}, headers=AGENT)
        assert clash.status_code == 400
        assert "warehouse_password is already a variable (from Finance). Pick another name." in clash.text
        rename = {"name": "SHOP_API_TOKEN", "to": "warehouse_password"}
        renamed = client.post("/variables/rename", json=rename, headers=AUTH)
        assert renamed.status_code == 400 and "already a variable (from Finance)" in renamed.text
        # A vault's own entry that another source gives: refused before it is saved.
        mapped = every_vault(team_names, "Ops") | {
            "vault_all": False,
            "vault_mapping": [{"env": "SHOP_API_TOKEN", "secret": "shop-token"}],
        }
        refused = client.post("/connections", json=mapped, headers=AGENT)
        assert refused.status_code == 400
        assert (
            "SHOP_API_TOKEN is already a variable (from your variables). Pick another name." in refused.text
        )
        before = from_vaults(client)
    with memory_keyring(), make_client(tmp_path) as client:  # a restart, then both read again: the same names
        assert from_vaults(client) == before
        client.post("/connections/vaults/secrets", json={"name": "Team Vault"}, headers=AUTH)
        client.post("/connections/vaults/secrets", json={"name": "Finance"}, headers=AUTH)
        assert from_vaults(client) == before
    no_value_written(tmp_path)


def test_a_kernels_load_gives_the_same_names_as_the_page(tmp_path: Path) -> None:
    from swissarmybench.server.blade_runner import _load

    one, two = tmp_path / "one.json", tmp_path / "two.json"
    one.write_text(json.dumps(["warehouse-password"]))
    two.write_text(json.dumps(["warehouse-password", "api-key"]))
    base = {"variable": "get", "mapping": {}, "secrets": {}, "every": True}
    vaults = [
        base | {"code": vault_code(two), "label": "Team Vault"},
        base | {"code": vault_code(one), "label": "Finance"},
    ]
    answer = _load({"vaults": vaults, "yours": ["api_key"]})
    assert set(answer["values"]) == {
        "warehouse_password",
        "TEAM_VAULT_warehouse_password",
        "TEAM_VAULT_api_key",
    }
    assert answer["values"]["warehouse_password"].endswith("-warehouse-password")


def test_the_form_save_carries_the_read_names(tmp_path: Path) -> None:
    listed = tmp_path / "names.json"
    listed.write_text(json.dumps(["sales-key", "ops-key"]))
    with make_client(tmp_path) as client:
        body = every_vault(listed, "Sales vault") | {"vault_names": ["sales-key", "ops-key"]}
        assert client.post("/connections", json=body, headers=AUTH).status_code == 200
        assert from_vaults(client) == {"ops_key": "Sales vault", "sales_key": "Sales vault"}
        blade = tmp_path / "state" / "library" / "vaults" / "sales_vault.blade.py"
        assert "ops-key" not in blade.read_text()
