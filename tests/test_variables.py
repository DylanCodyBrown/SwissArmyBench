"""The Variables page (the owner, 2026-11-16: "a workspace Variable page for the rail to help manage project
variables ... add new local env variables from the page easily and browse what is there and for variables
that are not from the key vault you can see their current values"). This computer's, whether or not a
project is open (2026-11-17), split into what may be shared and what stays on this computer. Made-up names
and values only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.adapters.variables import ProcessEnvironment, VariableFiles
from swissarmybench.domain import variables as rules
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring

KEYRING_SECRET = "made-up-keyring-Zx81"
VAULT_SECRET_NAME = "warehouse-password"


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


# ===== the rules =====


def test_a_plain_value_a_local_value_and_a_keyring_secret_are_kept_apart() -> None:
    defined, made, secret = rules.put([], {"name": "SALES_REGION", "value": "North"}, {})
    assert made == rules.Defined("SALES_REGION", "value", "North") and secret is None
    defined, made, secret = rules.put(
        defined, {"name": "EXPORT_FOLDER", "value": "/made/up/exports", "local": True}, {}
    )
    assert made.local and secret is None
    defined, made, secret = rules.put(
        defined, {"name": "SHOP_API_TOKEN", "value": KEYRING_SECRET, "from": "keyring"}, {}
    )
    assert made == rules.Defined("SHOP_API_TOKEN", "keyring") and secret == KEYRING_SECRET
    shared, local = rules.shared_json(defined), rules.local_json(defined)
    # The shareable file: names and sources, the region's value; never the local path, never the secret.
    assert shared["variables"] == [
        {"name": "EXPORT_FOLDER", "from": "value", "local": "yes"},
        {"name": "SALES_REGION", "from": "value", "value": "North"},
        {"name": "SHOP_API_TOKEN", "from": "keyring"},
    ]
    assert local["values"] == {"EXPORT_FOLDER": "/made/up/exports"}
    assert KEYRING_SECRET not in json.dumps([shared, local])
    assert rules.read_defined(shared, local) == sorted(defined, key=lambda d: d.name)
    # Cloned to another computer (no local file): the local one is named, its value missing there.
    elsewhere = rules.read_defined(shared, None)
    found, _ = rules.listing(elsewhere, [], [], [], {}, [])
    assert {v.name: v.source for v in found} == {
        "EXPORT_FOLDER": "missing",
        "SALES_REGION": "value",
        "SHOP_API_TOKEN": "missing",
    }


def test_a_secret_name_is_never_a_plain_value_and_names_are_checked() -> None:
    with pytest.raises(rules.VariableError, match="reads like a secret"):
        rules.put([], {"name": "SHOP_PASSWORD", "value": "x", "from": "value"}, {})
    with pytest.raises(rules.VariableError, match="letters, digits"):
        rules.put([], {"name": "9 bad", "value": "x"}, {})
    with pytest.raises(rules.VariableError, match="comes from Team vault"):
        rules.put(
            [],
            {"name": "WAREHOUSE_PASSWORD", "value": "x", "from": "keyring"},
            {"WAREHOUSE_PASSWORD": "Team vault"},
        )
    # A secret name with no "from": the keyring.
    _, made, _ = rules.put([], {"name": "SHOP_API_TOKEN", "value": "x"}, {})
    assert made.origin == "keyring"


def test_each_source_and_its_uses_and_which_values_show() -> None:
    defined = [rules.Defined("SALES_REGION", "value", "North")]
    connections = [
        rules.ConnectionFacts(
            "Team vault", vault_mapping={"WAREHOUSE_PASSWORD": VAULT_SECRET_NAME}, vault=True
        ),
        rules.ConnectionFacts("Warehouse", secrets=("WAREHOUSE_PASSWORD",)),
        rules.ConnectionFacts("Trino", files=(("TRINO_KEYSTORE_PATH", "keystore", "/made/up/keystore.p12"),)),
    ]
    script = "import os\nregion = os.environ['SALES_REGION']\nhome = os.getenv('REPORT_HOME')\n"
    documents = [rules.document_uses("/work/daily.py", "daily.py", script)]
    runs = [rules.run_settings_uses("/work/daily.py", "daily.py", {"SALES_REGION": {"from": "env"}})]
    environ = {"REPORT_HOME": "/made/up/reports", "SALES_REGION": "South"}
    found, every = rules.listing(defined, connections, documents, runs, environ, [])
    by = {v["name"]: v for v in rules.shown(found, environ)}
    assert every == []
    vault = by["WAREHOUSE_PASSWORD"]
    assert vault["from"] == "vault" and vault["vault"] == "Team vault"
    assert vault["vault_secret"] == VAULT_SECRET_NAME and "value" not in vault and not vault["hidden"]
    assert [u["name"] for u in vault["uses"]] == ["Warehouse"]
    region = by["SALES_REGION"]
    assert region["from"] == "value" and region["value"] == "North" and region["replaces_env"]
    assert {u["kind"] for u in region["uses"]} == {"script", "run_settings"}
    assert by["REPORT_HOME"]["from"] == "env" and by["REPORT_HOME"]["value"] == "/made/up/reports"
    keystore = by["TRINO_KEYSTORE_PATH"]
    assert keystore["from"] == "missing" and keystore["default"] == "/made/up/keystore.p12"
    assert keystore["uses"][0] == {"kind": "connection", "name": "Trino", "how": "keystore"}
    # Search and one source.
    assert [v["name"] for v in rules.shown(found, environ, search="trino")] == ["TRINO_KEYSTORE_PATH"]
    assert [v["name"] for v in rules.shown(found, environ, source="vault")] == ["WAREHOUSE_PASSWORD"]


def test_a_secret_in_the_environment_is_behind_show() -> None:
    environ = {"SHOP_API_TOKEN": "made-up-env-token"}
    documents = [rules.document_uses("/w/a.py", "a.py", "import os\nt = os.environ['SHOP_API_TOKEN']\n")]
    found, _ = rules.listing([], [], documents, [], environ, [])
    shown = rules.shown(found, environ)[0]
    assert shown["from"] == "env" and shown["secret"] and shown["hidden"] and "value" not in shown


def test_rename_in_code_follows_each_way_of_reading_a_variable() -> None:
    code = (
        "pw = secret('OLD_PW')\na = os.environ['OLD_PW']\nb = os.environ.get(\"OLD_PW\", 'x')\n"
        "c = os.getenv('OLD_PW')\nd = 'OLD_PW_NOT'\n"
    )
    changed, count = rules.rename_in_code(code, "OLD_PW", "NEW_PW")
    assert count == 4 and "OLD_PW'" not in changed and "'OLD_PW_NOT'" in changed


def test_the_environment_gets_its_own_values_back() -> None:
    environ = {"KEEP": "mine"}
    env = ProcessEnvironment(environ)
    env.apply({"KEEP": "theirs", "NEW": "1"})
    assert environ == {"KEEP": "theirs", "NEW": "1"} and env.base() == {"KEEP": "mine"}
    env.apply({})
    assert environ == {"KEEP": "mine"}


def test_the_files_change_no_byte_when_nothing_changed(tmp_path: Path) -> None:
    files = VariableFiles(lambda: tmp_path)
    defined = [
        rules.Defined("SALES_REGION", "value", "North"),
        rules.Defined("DATA_FOLDER", "value", "C:\\made-up\\data", local=True),
        rules.Defined("SHOP_TOKEN", "keyring"),
    ]
    files.write(rules.shared_json(defined), rules.local_json(defined))
    shared, local = tmp_path / "variables.toml", tmp_path / "local" / "variables.toml"
    before = (shared.read_bytes(), shared.stat().st_mtime_ns, local.stat().st_mtime_ns)
    files.write(rules.shared_json(defined), rules.local_json(defined))
    assert (shared.read_bytes(), shared.stat().st_mtime_ns, local.stat().st_mtime_ns) == before
    assert sorted(rules.read_defined(*files.read()), key=lambda d: d.name) == sorted(
        defined, key=lambda d: d.name
    )
    # The shareable file holds names and sources; the local value only in local/.
    assert "made-up" not in shared.read_text() and "made-up" in local.read_text()
    assert "[variables.SHOP_TOKEN]" in shared.read_text()


# ===== over HTTP: add, show, the agent, rename, remove =====


def _ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def _by_name(client: Any, headers: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {v["name"]: v for v in _ok(client.get("/variables", headers=headers))["variables"]}


def test_the_page_over_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SALES_REGION", raising=False)
    monkeypatch.delenv("SHOP_API_TOKEN", raising=False)
    with make_client(tmp_path) as client:
        vault = {
            "name": "Team vault",
            "kind": "vault",
            "code": "def get(name):\n    return 'made-up'",
            "variable": "get",
            "vault_mapping": [{"env": "WAREHOUSE_PASSWORD", "secret": VAULT_SECRET_NAME}],
        }
        _ok(client.post("/blades", json=vault, headers=AUTH))
        warehouse = {
            "name": "Warehouse",
            "kind": "sql",
            "dialect": "sqlite",
            "code": "import sqlite3\npw = secret('SHOP_API_TOKEN')\nconn = sqlite3.connect(':memory:')\n",
        }
        _ok(client.post("/blades", json=warehouse, headers=AUTH))
        # Add a plain value: in this server's environment at once, so what it starts reads it.
        added = _ok(client.put("/variables", json={"name": "SALES_REGION", "value": "North"}, headers=AUTH))
        assert added["variable"]["value"] == "North"
        import os

        assert os.environ["SALES_REGION"] == "North"
        # The agent sets a keyring secret: saved, never answered back.
        secret = _ok(
            client.put(
                "/variables",
                json={"name": "SHOP_API_TOKEN", "value": KEYRING_SECRET, "from": "keyring"},
                headers=AGENT,
            )
        )
        assert KEYRING_SECRET not in json.dumps(secret)
        for headers in (AUTH, AGENT):
            listed = client.get("/variables", headers=headers)
            assert KEYRING_SECRET not in listed.text and "made-up" not in listed.text
        by = _by_name(client, AGENT)
        assert by["SHOP_API_TOKEN"]["from"] == "keyring" and by["SHOP_API_TOKEN"]["hidden"]
        assert [u["name"] for u in by["SHOP_API_TOKEN"]["uses"]] == ["Warehouse"]
        assert by["WAREHOUSE_PASSWORD"]["vault"] == "Team vault" and "value" not in by["WAREHOUSE_PASSWORD"]
        # Show: the user's click only.
        refused = client.post("/variables/reveal", json={"name": "SHOP_API_TOKEN"}, headers=AGENT)
        assert refused.status_code == 403 and KEYRING_SECRET not in refused.text
        shown = _ok(client.post("/variables/reveal", json={"name": "SHOP_API_TOKEN"}, headers=AUTH))
        assert shown["value"] == KEYRING_SECRET
        vault_show = client.post("/variables/reveal", json={"name": "WAREHOUSE_PASSWORD"}, headers=AUTH)
        assert vault_show.status_code == 400 and "stays in the vault" in vault_show.text
        # Never in a file: the library's variables.toml has names and sources, the secret is the keyring's.
        state = tmp_path / "state"
        written = (state / "library" / "variables.toml").read_text(encoding="utf-8")
        assert "SALES_REGION" in written and KEYRING_SECRET not in written
        # Rename: the connection's code follows.
        renamed = _ok(
            client.post(
                "/variables/rename", json={"name": "SHOP_API_TOKEN", "to": "SHOP_TOKEN"}, headers=AGENT
            )
        )
        assert renamed["connections"] == ["Warehouse"]
        code = _ok(client.get("/blades/Warehouse", headers=AUTH))
        assert "secret('SHOP_TOKEN')" in json.dumps(code)
        assert _ok(client.post("/variables/reveal", json={"name": "SHOP_TOKEN"}, headers=AUTH))["value"] == (
            KEYRING_SECRET
        )
        # Remove: what still uses it is answered; the environment lets go of it.
        removed = _ok(client.delete("/variables/SALES_REGION", headers=AUTH))
        assert removed["removed"] == "SALES_REGION"
        assert "SALES_REGION" not in os.environ
        # Not one of this computer's: said.
        assert client.delete("/variables/NOT_THERE", headers=AUTH).status_code == 400
        # The Session page names the variable, never a value.
        log = _ok(client.get("/session-log", params={"who": "both"}, headers=AUTH))
        words = json.dumps(log)
        assert "Added the variable SALES_REGION" in words and KEYRING_SECRET not in words
    assert "SHOP_TOKEN" not in os.environ  # the server stopped: its values went with it


def test_the_variables_are_the_computers_with_a_project_open(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _ok(client.put("/variables", json={"name": "SALES_REGION", "value": "North"}, headers=AUTH))
        target = tmp_path / "work" / "sales"
        _ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))
        assert _by_name(client, AUTH)["SALES_REGION"]["value"] == "North"
        _ok(client.put("/variables", json={"name": "REGION_TWO", "value": "West"}, headers=AUTH))
        _ok(client.post("/project/save", json={}, headers=AUTH))
    written = [p for p in target.rglob("*") if p.is_file()]
    assert not any("variables" in p.name for p in written)
    assert all(b"West" not in p.read_bytes() for p in written)
