"""The library (Plans/library.plan.md; the owner, 2026-11-17: "Apis, Connections they live OUTSIDE of the
project" / "that library is the thing I wanted to push to a github repo"): connections, APIs, vaults,
blades, tangs, variables and colours as one folder of text files, whatever project is open. Made on first
use; one file per item; a save that changes nothing changes no byte; never a secret; a clone on another
computer opens with the same items and asks only for secrets and local values; this computer's older
stores and an older project's own blades move in once, said. Made-up data only."""

from __future__ import annotations

import json
import shutil
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import library as rules
from swissarmybench.domain.blades import Blade, read_blade
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring

KEYRING_SECRET = "made-up-keyring-pa55"
API_SECRET = "made-up-api-k3y"
VARIABLE_SECRET = "made-up-variable-t0ken"
SECRETS = (KEYRING_SECRET, API_SECRET, VARIABLE_SECRET)


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def warehouse(name: str = "Warehouse", database: str = ":memory:") -> dict[str, Any]:
    """A made-up SQLite connection whose password is saved in this computer's keyring."""
    return {
        "name": name,
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": f'import sqlite3\nassert secret("password")\nconn = sqlite3.connect({database!r})\n',
        "secrets": {"password": KEYRING_SECRET},
    }


def files_of(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def stamps(root: Path) -> dict[str, int]:
    return {p.relative_to(root).as_posix(): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}


def fill(client: TestClient) -> None:
    """A connection, a vault, a blade, an API, variables (shareable, local, keyring) and a colour."""
    ok(client.post("/connections", json=warehouse(), headers=AUTH))
    vault_blade = {
        "name": "Team vault",
        "kind": "vault",
        "code": "def get(name):\n    return 'made-up'",
        "variable": "get",
        "vault_mapping": [{"env": "ORDERS_PASSWORD", "secret": "orders-password"}],
    }
    ok(client.post("/blades", json=vault_blade, headers=AUTH))
    function = {"name": "Tidy", "kind": "other", "code": "def tidy(x):\n    return x\n", "variable": "tidy"}
    ok(client.post("/blades", json=function, headers=AUTH))
    form = {
        "title": "Shop",
        "base_url": "https://shop.example.com",
        "auth": {"type": "api_key", "in": "header", "name": "x-key"},
        "endpoints": [{"path": "/products", "table": True}],
    }
    api = {
        "form": form,
        "variables": [{"name": "SHOP_API_KEY", "from": "keyring"}],
        "secrets": {"SHOP_API_KEY": API_SECRET},
    }
    ok(client.post("/apis", json=api, headers=AUTH))
    ok(client.put("/variables", json={"name": "SALES_REGION", "value": "North"}, headers=AUTH))
    ok(
        client.put(
            "/variables", json={"name": "DATA_FOLDER", "value": "/made-up/data", "local": True}, headers=AUTH
        )
    )
    ok(
        client.put(
            "/variables",
            json={"name": "SHOP_TOKEN", "value": VARIABLE_SECRET, "from": "keyring"},
            headers=AUTH,
        )
    )
    ok(client.put("/connection-colours/Warehouse", json={"colour": "#0e7c7b"}, headers=AUTH))


# ===== the rules =====


def test_variables_toml_is_sorted_stable_and_reads_back() -> None:
    shared = {
        "format": 1,
        "variables": [
            {"name": "ZONE", "from": "value", "value": 'say "hi"\n\x7f'},
            {"name": "A_TOKEN", "from": "keyring"},
            {"name": "DATA", "from": "value", "local": "yes"},
        ],
    }
    text = rules.variables_toml(shared)
    assert text.index("[variables.A_TOKEN]") < text.index("[variables.DATA]") < text.index("[variables.ZONE]")
    assert rules.variables_toml(rules.read_variables_toml(text)) == text
    back = rules.read_variables_toml(text)
    assert back is not None and {r["name"]: r for r in back["variables"]}["ZONE"]["value"] == 'say "hi"\n\x7f'
    local = rules.local_toml({"values": {"DATA": "C:\\made-up"}})
    assert rules.read_local_toml(local) == {"format": 1, "values": {"DATA": "C:\\made-up"}}
    assert rules.read_variables_toml("") is None and rules.read_variables_toml("not = [toml") is None


def test_where_each_blade_goes_and_a_name_kept_beside_another() -> None:
    assert rules.folder_for("vault", None) == "vaults"
    assert rules.folder_for("sql", "sqlite") == "connections"
    assert rules.folder_for("other", "python") == "connections"
    assert rules.folder_for("other", None) == "blades" and rules.folder_for("snippet", None) == "blades"
    assert rules.migrated_name("Warehouse", "Q1 (draft)", []) == "Warehouse from Q1 draft"
    assert rules.migrated_name("Warehouse", "Q1", ["warehouse from q1"]) == "Warehouse from Q1 2"
    assert len(rules.migrated_name("W" * 64, "P" * 40, [])) <= 64
    words = rules.migration_words(["Tidy"], {"Warehouse": "Warehouse from Q1"}, ["Shop"], "Q1")
    assert words.startswith("Q1's connections and blades moved into your library")
    assert "Warehouse as Warehouse from Q1" in words and "1 already there" in words
    assert (
        rules.migration_words([], {}, ["Shop"], "Q1") != "" and rules.migration_words([], {}, [], "Q1") == ""
    )


def test_every_blade_kind_reads_back_from_its_library_file(tmp_path: Path) -> None:
    from swissarmybench.adapters.blades import BladeStore

    store = BladeStore(
        tmp_path / "library", starters=Path(__file__).resolve().parents[1] / "src/swissarmybench/starters"
    )
    starters = store.starters()
    assert len(starters) > 50
    for blade in starters:
        text = BladeStore.text_of(blade)
        again = BladeStore.text_of(store_parse(text))
        assert again == text, blade.name


def store_parse(text: str) -> Blade:
    from swissarmybench.adapters.blades import parse_blade

    return parse_blade(read_blade(text))


# ===== the library on disk =====


def test_made_on_first_use_one_file_each_no_secret_and_a_second_save_changes_nothing(tmp_path: Path) -> None:
    library = tmp_path / "state" / "library"
    with make_client(tmp_path) as client:
        assert not library.exists()  # nothing written until something is saved
        fill(client)
        info = ok(client.get("/library", headers=AGENT))
        assert info["folder"] == str(library) and info["is_default"] and not info["git"]
        assert info["counts"] == {
            "connections": 1,  # Warehouse (an API's blades are in its own apis/Shop folder)
            "vaults": 1,
            "blades": 1,
            "apis": 1,
            "tangs": 0,
            "local_files": 1,
        }
    names = set(files_of(library))
    assert {
        "README.md",
        ".gitignore",
        "connections/warehouse.blade.py",
        "vaults/team_vault.blade.py",
    } <= names
    assert {"blades/tidy.blade.py", "variables.toml", "local/variables.toml", "colours.toml"} <= names
    assert any(n.startswith("apis/Shop/") and n.endswith("API_Shop.py") for n in names)
    assert "local/" in (library / ".gitignore").read_text()
    # Never a secret, in any file.
    everything = b"".join(files_of(library).values())
    for value in SECRETS:
        assert value.encode() not in everything, value
    shared = (library / "variables.toml").read_text()
    assert "SALES_REGION" in shared and "North" in shared and "/made-up/data" not in shared
    assert "/made-up/data" in (library / "local" / "variables.toml").read_text()
    assert "Warehouse" in (library / "colours.toml").read_text()
    # The user's README stays theirs.
    (library / "README.md").write_text("# Our team's library\n", encoding="utf-8")

    before = (files_of(library), stamps(library))
    with make_client(tmp_path) as client:
        # Everything saved again as it is: not a byte, not a time changes.
        ok(client.put("/connections/Warehouse", json=warehouse() | {"secrets": {}}, headers=AUTH))
        ok(client.put("/variables", json={"name": "SALES_REGION", "value": "North"}, headers=AUTH))
        ok(client.put("/connection-colours/Warehouse", json={"colour": "#0e7c7b"}, headers=AUTH))
        names_now = {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        assert {"Warehouse", "Team vault", "Tidy"} <= names_now
    assert (files_of(library), stamps(library)) == before


def test_a_clone_on_another_computer_has_the_same_items_and_asks_only_for_secrets(tmp_path: Path) -> None:
    first = tmp_path / "first"
    with make_client(first) as client:
        fill(client)
        here = {c["name"]: c for c in ok(client.get("/connections", headers=AUTH))["connections"]}
        assert here["Warehouse"]["needs_password"] is None
    clone = tmp_path / "clone"
    shutil.copytree(first / "state" / "library", clone, ignore=shutil.ignore_patterns("local"))  # git clone
    # Another computer: its own keyring (empty), its own state folder, pointed at the clone.
    with memory_keyring(), make_client(tmp_path / "second") as client:
        ok(client.put("/library", json={"folder": str(clone)}, headers=AUTH))
        names = {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        assert {"Warehouse", "Team vault", "Tidy"} <= names
        listed = {c["name"]: c for c in ok(client.get("/connections", headers=AUTH))["connections"]}
        assert listed["Warehouse"]["needs_password"]["missing"] == ["password"]
        variables = {v["name"]: v for v in ok(client.get("/variables", headers=AUTH))["variables"]}
        assert variables["SALES_REGION"]["value"] == "North"  # shared, so it came along
        assert variables["DATA_FOLDER"].get("value", "") == ""  # this computer only: to be set here
        assert variables["SHOP_TOKEN"]["set"] is False  # a keyring secret: asked for here
        colours = ok(client.get("/connection-colours", headers=AUTH))
        assert "#0e7c7b" in json.dumps(colours)
        # Its own password, set here: it works, and still nothing lands in the folder.
        ok(client.put("/blades/Warehouse/secrets", json={"password": KEYRING_SECRET}, headers=AUTH))
        listed = {c["name"]: c for c in ok(client.get("/connections", headers=AUTH))["connections"]}
        assert listed["Warehouse"]["needs_password"] is None
        # Back to the default library: the clone's items are not there.
        ok(client.put("/library", json={"folder": None}, headers=AUTH))
        assert "Warehouse" not in {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
    assert KEYRING_SECRET.encode() not in b"".join(files_of(clone).values())


def test_the_agent_points_the_library_elsewhere_only_on_the_users_allow(tmp_path: Path) -> None:
    other = tmp_path / "team-library"
    other.mkdir()
    with make_client(tmp_path) as client:
        assert client.put("/library", json={"folder": "relative/path"}, headers=AUTH).status_code == 400
        (tmp_path / "a-file").write_text("x", encoding="utf-8")
        assert (
            client.put("/library", json={"folder": str(tmp_path / "a-file")}, headers=AUTH).status_code == 400
        )

        def answer(approve: bool) -> threading.Thread:
            def run() -> None:
                for _ in range(200):
                    pending = client.get("/agent/approvals", headers=AUTH).json()["pending"]
                    if pending:
                        client.post(
                            f"/agent/approvals/{pending[0]['id']}", json={"approve": approve}, headers=AUTH
                        )
                        return
                    time.sleep(0.05)

            thread = threading.Thread(target=run)
            thread.start()
            return thread

        thread = answer(False)
        refused = client.put("/library", json={"folder": str(other)}, headers=AGENT)
        thread.join()
        assert refused.status_code == 403
        assert ok(client.get("/library", headers=AGENT))["is_default"]
        thread = answer(True)
        moved = ok(client.put("/library", json={"folder": str(other)}, headers=AGENT))
        thread.join()
        assert moved["folder"] == str(other) and (other / "README.md").is_file()
    # Kept across restarts (the path only).
    with make_client(tmp_path) as client:
        assert ok(client.get("/library", headers=AUTH))["folder"] == str(other)


# ===== migration =====


def _old_blade(name: str, code: str) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": code,
        "variable": "conn",
        "catalog": None,
        "created_at": 1.0,
        "updated_at": 1.0,
    }


def test_this_computers_older_stores_move_in_once_with_a_backup_and_a_notice(tmp_path: Path) -> None:
    state = tmp_path / "state"
    (state / "blades").mkdir(parents=True)
    old = _old_blade(
        "Old warehouse", 'import sqlite3\nassert secret("password")\nconn = sqlite3.connect(":memory:")\n'
    )
    (state / "blades" / "old_warehouse-12345678.json").write_text(json.dumps(old), encoding="utf-8")
    (state / "variables.json").write_text(
        json.dumps({"format": 1, "variables": [{"name": "SALES_REGION", "from": "value", "value": "East"}]}),
        encoding="utf-8",
    )
    (state / "colours.toml").write_text('"Old warehouse" = "#0e7c7b"\n', encoding="utf-8")
    (state / "tangs").mkdir()
    (state / "tangs" / "store.tang").write_text("made-up tang\n", encoding="utf-8")
    with make_client(tmp_path) as client:
        assert "Old warehouse" in {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        variables = {v["name"]: v for v in ok(client.get("/variables", headers=AUTH))["variables"]}
        assert variables["SALES_REGION"]["value"] == "East"
        info = ok(client.get("/library", headers=AGENT))
        assert (
            info["notices"]
            and "Your connections and blades now live in your library" in info["notices"][0]["text"]
        )
        taken = ok(client.post("/library/notices", headers=AUTH))["notices"]
        assert taken and ok(client.post("/library/notices", headers=AUTH))["notices"] == []
    library = state / "library"
    assert (library / "connections" / "old_warehouse.blade.py").is_file()
    assert (library / "variables.toml").is_file() and (library / "colours.toml").is_file()
    assert (library / "tangs" / "store.tang").is_file()
    assert not (state / "blades").exists() and not (state / "variables.json").exists()
    backups = list((state / "backup").iterdir())
    assert len(backups) == 1 and backups[0].name.startswith("before-library-")
    assert (backups[0] / "blades" / "old_warehouse-12345678.json").is_file()
    # Once: a second start moves nothing and says nothing.
    with make_client(tmp_path) as client:
        assert ok(client.get("/library", headers=AGENT))["notices"] == []


def _with_own_blades(path: Path, blades: dict[str, dict[str, Any]]) -> None:
    """An older app's project: its own connections and blades in its .sab/blades."""
    (path / ".sab" / "blades").mkdir(parents=True, exist_ok=True)
    for file, blade in blades.items():
        (path / ".sab" / "blades" / file).write_text(json.dumps(blade), encoding="utf-8")


def test_an_older_projects_own_blades_move_into_the_library_and_its_next_save_leaves_them_out(
    tmp_path: Path,
) -> None:
    code = 'import sqlite3\nassert secret("password")\nconn = sqlite3.connect(":memory:")\n'
    with make_client(tmp_path) as client:
        ok(client.post("/connections", json=warehouse(), headers=AUTH))
        library_text = (tmp_path / "state" / "library" / "connections" / "warehouse.blade.py").read_text()
        target = tmp_path / "older"
        ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))
        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
        same = _old_blade("Warehouse", warehouse()["code"])
        differs = _old_blade("warehouse two", code) | {"name": "Shop"}
        ok(client.post("/connections", json=warehouse("Shop", "shop.db"), headers=AUTH))
        new = _old_blade("Orchard", code)
        _with_own_blades(target, {"warehouse-1.json": same, "shop-2.json": differs, "orchard-3.json": new})
        opened = ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))
        assert opened["project"]["name"] == "older"
        names = {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        assert {"Warehouse", "Shop", "Shop from older", "Orchard"} <= names
        notices = ok(client.get("/library", headers=AGENT))["notices"]
        assert any("Shop as Shop from older" in n["text"] and "Orchard" in n["text"] for n in notices)
        # The library's own Warehouse is untouched (the project's was the same one).
        assert (
            tmp_path / "state" / "library" / "connections" / "warehouse.blade.py"
        ).read_text() == library_text
        ok(client.post("/project/save", json={}, headers=AUTH))
        assert not list((target / ".sab" / "blades").glob("*.json"))
        # Closed, the library keeps them: every project has them.
        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
        assert "Orchard" in {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
