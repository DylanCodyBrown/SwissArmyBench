"""A key vault's secret names remembered on this computer (domain/vault_names.py, services/vault_names.py; the
owner, 2026-11-20: "Every time I update or reopen the app my Vault variables disappear"). Made-up vaults
only: names() reads a made-up file, get() makes a made-up value; nothing leaves this computer."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from starlette.testclient import TestClient

from swissarmybench.domain import vault_names as rules
from tests.conftest import AGENT, AUTH, make_client

MADE_UP_VALUE = "made-up-value-7f3q"


def vault_code(names_file: Path) -> str:
    """A made-up vault: its names from a file the test writes, each value made up (never a real secret)."""
    return (
        "import json\n"
        "from pathlib import Path\n\n\n"
        "def names():\n"
        f"    return json.loads(Path(r'{names_file}').read_text())\n\n\n"
        "def get(name):\n"
        f"    return {MADE_UP_VALUE[::-1]!r}[::-1] + '-' + name\n"  # the value is not in the code's text
    )


def every_vault(names_file: Path, name: str = "Team vault") -> dict[str, Any]:
    return {
        "name": name,
        "kind": "vault",
        "template": "azure_key_vault",
        "variable": "get",
        "code": vault_code(names_file),
        "vault_all": True,
        "vault_mapping": [],
    }


def from_vaults(client: TestClient) -> dict[str, str]:
    found = client.get("/variables", headers=AUTH).json()["variables"]
    return {v["name"]: v["vault"] for v in found if v["from"] == "vault"}


def names_files(tmp_path: Path) -> list[Path]:
    folder = tmp_path / "state" / "library" / rules.FOLDER
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def no_value_written(tmp_path: Path) -> None:
    for path in (tmp_path / "state").rglob("*"):
        if path.is_file():
            assert MADE_UP_VALUE.encode() not in path.read_bytes(), path


# ===== the rules =====


def test_the_file_is_names_only_sorted_and_byte_stable() -> None:
    found = [
        {"secret": "warehouse-password", "env": "warehouse_password"},
        "Api--Key",
        "api-key",
        "Api--Key",
        "",
    ]
    names = rules.rows(found)
    assert names == (
        ("Api--Key", "Api__Key"),
        ("api-key", "api_key"),
        ("warehouse-password", "warehouse_password"),
    )
    made = rules.Remembered("Team vault", names, "2026-11-20T09:00:00+00:00")
    text = rules.render(made)
    assert text == rules.render(rules.Remembered("Team vault", rules.rows(reversed(found)), made.read_at))
    assert rules.parse(text) == made
    assert json.loads(text)["names"][1] == {"env": "api_key", "secret": "api-key"}
    assert text.endswith("}\n") and rules.file_name("Team vault") == "team_vault.json"
    assert rules.parse("not json") is None and rules.parse('{"format": 99, "vault": "x"}') is None
    empty = rules.Remembered("Empty", (), "")
    assert rules.parse(rules.render(empty)) == empty


def test_a_kernel_loading_the_vaults_hands_back_their_names(tmp_path: Path) -> None:
    from swissarmybench.server.blade_runner import _load

    listed = tmp_path / "names.json"
    listed.write_text(json.dumps(["api-key", "warehouse-password"]))
    vault = {"code": vault_code(listed), "variable": "get", "mapping": {}, "secrets": {}}
    answer = _load({"vaults": [vault | {"label": "Team vault", "every": True}]})
    assert answer["names"] == {"Team vault": ["api-key", "warehouse-password"]}
    assert set(answer["values"]) == {"api_key", "warehouse_password"}


# ===== kept across a restart =====


def test_a_vault_that_loads_every_secret_keeps_its_variables_over_a_restart(tmp_path: Path) -> None:
    listed = tmp_path / "names.json"
    listed.write_text(json.dumps(["warehouse-password", "api-key"]))
    with make_client(tmp_path) as client:
        assert client.post("/connections", json=every_vault(listed), headers=AUTH).status_code == 200
        assert from_vaults(client) == {}  # not read yet: no names
        read = client.post("/connections/vaults/secrets", json={"name": "Team vault"}, headers=AUTH)
        assert read.status_code == 200, read.text
        assert from_vaults(client) == {"api_key": "Team vault", "warehouse_password": "Team vault"}
        [card] = client.get("/connections", headers=AUTH).json()["connections"]
        assert card["names"]["count"] == 2 and card["names"]["read_at"]
    [kept] = names_files(tmp_path)
    assert kept.name == "team_vault.json"
    first = kept.read_bytes()
    with make_client(tmp_path) as client:  # a restart (no start-up read here): there at once
        assert from_vaults(client) == {"api_key": "Team vault", "warehouse_password": "Team vault"}
        assert client.get("/variables", headers=AUTH).json()["variables"][0]["vault_secret"] == "api-key"
        # Set up this computer reads the vault again: the same names write nothing.
        checklist = client.get("/library/setup", headers=AUTH)
        assert checklist.status_code == 200 and "warehouse_password" in checklist.text
        assert kept.read_bytes() == first
    no_value_written(tmp_path)


def test_the_form_read_keeps_the_names_under_its_name(tmp_path: Path) -> None:
    listed = tmp_path / "names.json"
    listed.write_text(json.dumps(["sales-key"]))
    with make_client(tmp_path) as client:
        draft = every_vault(listed, "Sales vault")
        read = client.post("/connections/vaults/secrets", json=draft, headers=AGENT)
        assert read.status_code == 200 and read.json()["names"] == [
            {"secret": "sales-key", "env": "sales_key"}
        ]
        assert client.post("/connections", json=draft, headers=AUTH).status_code == 200
        assert from_vaults(client) == {"sales_key": "Sales vault"}
    no_value_written(tmp_path)


def test_a_deleted_or_renamed_vault_takes_its_names_file_along(tmp_path: Path) -> None:
    listed = tmp_path / "names.json"
    listed.write_text(json.dumps(["api-key"]))
    with make_client(tmp_path) as client:
        client.post("/connections", json=every_vault(listed), headers=AUTH)
        client.post("/connections/vaults/secrets", json={"name": "Team vault"}, headers=AUTH)
        renamed = every_vault(listed, "Finance vault")
        assert client.put("/connections/Team%20vault", json=renamed, headers=AUTH).status_code == 200
        assert [p.name for p in names_files(tmp_path)] == ["finance_vault.json"]
        assert from_vaults(client) == {"api_key": "Finance vault"}
        assert client.delete("/blades/Finance%20vault", headers=AUTH).status_code == 200
        assert names_files(tmp_path) == [] and from_vaults(client) == {}


# ===== read again at start =====


def wait_for(client: TestClient, wanted: dict[str, str]) -> dict[str, str]:
    deadline = time.monotonic() + 30
    found = from_vaults(client)
    while found != wanted and time.monotonic() < deadline:
        time.sleep(0.2)
        found = from_vaults(client)
    return found


def test_the_start_up_read_updates_the_names_and_a_failure_keeps_them(tmp_path: Path) -> None:
    listed = tmp_path / "names.json"
    listed.write_text(json.dumps(["api-key"]))
    with make_client(tmp_path) as client:
        client.post("/connections", json=every_vault(listed), headers=AUTH)
        client.post("/connections/vaults/secrets", json={"name": "Team vault"}, headers=AUTH)
    (names_files(tmp_path)[0].parent / "gone_vault.json").write_text(
        rules.render(rules.Remembered("Gone vault", (("x", "x"),), ""))
    )
    listed.write_text(json.dumps(["api-key", "new-key"]))
    quick = {"auto_read_vaults": True, "catalogs_start_wait_seconds": 0.2}
    with make_client(tmp_path, **quick) as client:
        assert wait_for(client, {"api_key": "Team vault", "new_key": "Team vault"}) == {
            "api_key": "Team vault",
            "new_key": "Team vault",
        }
        assert [p.name for p in names_files(tmp_path)] == ["team_vault.json"]  # a gone vault's file went
    listed.unlink()  # the vault cannot be read now
    with make_client(tmp_path, **quick) as client:
        deadline = time.monotonic() + 30
        card: dict[str, Any] = {}
        while time.monotonic() < deadline:
            [card] = client.get("/connections", headers=AUTH).json()["connections"]
            if card["names"].get("error"):
                break
            time.sleep(0.2)
        assert card["names"]["error"] and card["names"]["read_at"] and card["names"]["count"] == 2
        assert from_vaults(client) == {"api_key": "Team vault", "new_key": "Team vault"}
    no_value_written(tmp_path)
