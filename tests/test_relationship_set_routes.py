"""Relationship sets (tangs until 2026-11-17), managing the joins in use, and the relationship finder
over HTTP, on the made-up nine-table store.

The finder is scored on examples/sample_store.py's answer key: every true relationship found (the
two-column key, the text-to-number join, both calendar paths with ship_date inactive) and none of
its decoys. Then running a set, saving one where coworkers see it, and moving one between people;
deleting, editing and undoing joins in use; renaming and deleting saved sets; the old names.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from examples.sample_store import DECOYS, TRUE_RELATIONSHIPS, make_store
from starlette.testclient import TestClient

from swissarmybench.domain.relationships import read_set
from tests.conftest import AGENT, AUTH, make_client, push


@pytest.fixture(scope="module")
def store() -> dict[str, pa.Table]:
    return {name: pa.Table.from_pandas(frame, preserve_index=False) for name, frame in make_store().items()}


@pytest.fixture
def client(tmp_path: Path, store: dict[str, pa.Table]) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        for name, table in store.items():
            assert push(test_client, name, table).status_code == 200
        yield test_client


def answer_key() -> set[tuple[str, tuple[str, ...], str, tuple[str, ...]]]:
    return {(r.from_table, r.from_columns, r.to_table, r.to_columns) for r in TRUE_RELATIONSHIPS}


def found(suggestions: list[dict[str, Any]]) -> set[tuple[str, tuple[str, ...], str, tuple[str, ...]]]:
    return {(s["from"], tuple(s["from_columns"]), s["to"], tuple(s["to_columns"])) for s in suggestions}


def test_the_finder_finds_every_true_relationship_and_no_decoy(client: TestClient) -> None:
    answer = client.post("/relationships/find", json={}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert found(body["suggestions"]) == answer_key()
    for a, ac, b, bc in DECOYS:
        assert not any(
            {(s["from"], s["from_columns"][0]), (s["to"], s["to_columns"][0])} == {(a, ac), (b, bc)}
            for s in body["suggestions"]
        )
    by = {(s["from"], tuple(s["from_columns"])): s for s in body["suggestions"]}
    assert by[("orders", ("ship_date",))].get("active") is False  # the second path to calendar
    assert by[("orders", ("order_date",))].get("active", True) is True
    assert by[("customers", ("home_store",))]["note"] == "text on one side, a number on the other"
    orphans = by[("orders", ("customer_id",))]
    assert orphans["orphans"] > 0 and "orphans" in orphans["evidence"]
    assert body["keys"]["order_lines"] == ["order_id", "line_no"]  # the two-column key


def test_accepting_suggestions_runs_clean_and_a_rejected_one_stays_away(client: TestClient) -> None:
    suggestions = client.post("/relationships/find", json={}, headers=AUTH).json()["suggestions"]
    model = {"name": "Sample store", "relationships": suggestions}
    assert client.post("/relationships", json={"model": model}, headers=AUTH).status_code == 200
    ran = client.post("/relationships/check", json={}, headers=AUTH).json()
    statuses = {(r["from"], tuple(r["from_columns"])): r["status"] for r in ran["results"]}
    assert statuses[("orders", ("customer_id",))] == "orphans"  # about 1% of orders: deleted accounts
    assert set(statuses.values()) <= {"holds", "orphans"} and ran["counts"]["holds"] >= 8
    customer = next(r for r in ran["results"] if r["from_columns"] == ["customer_id"])
    assert customer["orphan_samples"] and customer["actual_kind"] == "many-to-one"
    # Known joins are marked; a rejected one is not offered again, and undo brings it back.
    again = client.post("/relationships/find", json={}, headers=AUTH).json()["suggestions"]
    assert all(s["known"] for s in again)
    sku = {"from": "order_lines", "from_columns": ["sku"], "to": "products", "to_columns": ["sku"]}
    client.post("/relationships/reject", json=sku, headers=AUTH)
    assert ("order_lines", ("sku",), "products", ("sku",)) not in found(
        client.post("/relationships/find", json={}, headers=AUTH).json()["suggestions"]
    )
    client.post("/relationships/reject", json=sku | {"undo": True}, headers=AUTH)
    path = client.get(
        "/relationships/path", params={"from": "returns", "to": "categories"}, headers=AUTH
    ).json()
    assert [(j["from"], j["to"]) for j in path["joins"]] == [
        ("returns", "order_lines"),
        ("order_lines", "products"),
        ("products", "categories"),
    ]


def test_a_run_says_what_broke(client: TestClient) -> None:
    broken = {
        "name": "Broken",
        "relationships": [
            {
                "from": "orders",
                "from_columns": ["status_code"],
                "to": "customers",
                "to_columns": ["status_code"],
            },
            {
                "from": "orders",
                "from_columns": ["customer_id"],
                "to": "customers",
                "to_columns": ["gone_column"],
            },
            {"from": "orders", "from_columns": ["order_id"], "to": "warehouse", "to_columns": ["order_id"]},
        ],
    }
    client.post("/relationships", json={"model": broken, "replace": True}, headers=AUTH)
    results = client.post("/relationships/check", json={}, headers=AUTH).json()["results"]
    assert [r["status"] for r in results] == ["broken", "broken", "not open"]
    assert "repeat" in results[0]["detail"]  # customers.status_code is no key
    assert "customers.gone_column is no longer in the table" in results[1]["detail"]
    assert "Push warehouse" in results[2]["detail"]


def test_a_set_saved_in_a_shared_folder_is_in_a_coworkers_list(client: TestClient, tmp_path: Path) -> None:
    team = tmp_path / "team share"
    (team / "finance").mkdir(parents=True)
    assert client.put("/blades/folders", json={"folders": [str(team)]}, headers=AUTH).status_code == 200
    suggestions = client.post("/relationships/find", json={}, headers=AUTH).json()["suggestions"]
    client.post("/relationships", json={"model": {"relationships": suggestions}}, headers=AUTH)
    named = {
        "name": "Sample store",
        "description": "The made-up store's joins",
        "tags": ["sales"],
        "author": "Avery",
    }
    saved = client.post("/relationships/sets", json=named | {"folder": str(team)}, headers=AUTH).json()
    assert saved["where"] == "shared" and Path(saved["file"]).name == "sample_store.relationships.json"
    on_disk = read_set(Path(saved["file"]).read_text(encoding="utf-8"))
    assert on_disk.author == "Avery" and on_disk.saved_at and len(on_disk.relationships) == 10
    assert ("orders", "order_id") in {(t, c) for t, cols in on_disk.columns.items() for c, _ in cols}
    # A coworker: another server with the same shared folder lists it and applies it.
    with make_client(tmp_path / "coworker") as other:
        other.put("/blades/folders", json={"folders": [str(team)]}, headers=AUTH)
        listed = other.get("/relationships/library", headers=AUTH).json()
        entry = next(m for m in listed["models"] if m["name"] == "Sample store")
        assert entry["where"] == "shared" and entry["set"] and entry["author"] == "Avery"
        assert entry["tags"] == ["sales"] and entry["relationships"] == 10
        applied = other.post("/relationships/library/Sample%20store", headers=AUTH).json()
        assert len(applied["relationships"]) == 10 and applied["changed"] == []
    # Only the person's own sets or a shared folder: nowhere else on disk.
    elsewhere = client.post("/relationships/sets", json=named | {"folder": str(tmp_path)}, headers=AUTH)
    assert elsewhere.status_code == 400 and "shared folders" in elsewhere.text


def test_export_review_and_import_a_set_file(client: TestClient) -> None:
    suggestions = client.post("/relationships/find", json={}, headers=AUTH).json()["suggestions"]
    client.post(
        "/relationships", json={"model": {"name": "Sample store", "relationships": suggestions}}, headers=AUTH
    )
    exported = client.get("/relationships/set", headers=AUTH)
    assert exported.status_code == 200
    assert 'filename="sample_store.relationships.json"' in exported.headers["content-disposition"]
    text = exported.text
    assert json.loads(text)["swissarmybench"] == "relationship-set"
    # Someone else's current relationships say order_lines -> orders is one-to-one: the review says
    # what importing would change, and applying does it.
    other = {
        "relationships": [
            {
                "from": "order_lines",
                "from_columns": ["order_id"],
                "to": "orders",
                "to_columns": ["order_id"],
                "kind": "one-to-one",
            }
        ]
    }
    client.post("/relationships", json={"model": other, "replace": True}, headers=AUTH)
    review = client.post("/relationships/import", json={"text": text}, headers=AUTH).json()
    assert review["changes"] == ["order_lines -> orders: one-to-one becomes many-to-one"]
    assert review["missing_tables"] == [] and "orders" in review["open_tables"]
    applied = client.post(
        "/relationships/import", json={"text": text, "apply": True, "save": True}, headers=AUTH
    ).json()
    assert applied["where"] == "mine" and len(applied["relationships"]) == 10
    plain = client.post("/relationships/import", json={"text": json.dumps({"name": "x"})}, headers=AUTH)
    assert plain.status_code == 400 and "not a relationship set" in plain.text


def test_the_agent_finds_runs_and_files_sets(client: TestClient) -> None:
    assert (
        client.post(
            "/relationships/find", json={"tables": ["orders", "customers"]}, headers=AGENT
        ).status_code
        == 200
    )
    assert client.post("/relationships/check", json={}, headers=AGENT).status_code in (200, 400)
    # The golden rule: set files are the agent's to save, export and import too.
    assert client.post("/relationships/sets", json={"name": "x"}, headers=AGENT).status_code != 403
    assert client.get("/relationships/set", headers=AGENT).status_code != 403
    assert client.post("/relationships/import", json={"text": "{}"}, headers=AGENT).status_code != 403
    one = client.post("/relationships/find", json={"tables": ["orders"]}, headers=AUTH)
    assert one.status_code == 400 and "two tables" in one.text


def test_the_finder_searches_open_tabs_and_names_a_one_to_one_join_once(client: TestClient) -> None:
    from tests.conftest import grid_id

    # Two copies of one table: their id columns join one to one, which is one join, not two.
    copy = pa.table({"customer_id": list(range(1, 51)), "tier": ["gold"] * 50})
    assert push(client, "tiers_a", copy).status_code == 200
    closing = grid_id(push(client, "tiers_b", copy))
    suggestions = client.post("/relationships/find", json={}, headers=AUTH).json()["suggestions"]
    pairs = [(s["from"], s["to"]) for s in suggestions if {s["from"], s["to"]} == {"tiers_a", "tiers_b"}]
    assert len(pairs) == 1, pairs
    # A closed tab's table stays in memory but is not searched (unless named).
    assert client.delete(f"/grids/{closing}", headers=AUTH).status_code == 200
    answer = client.post("/relationships/find", json={}, headers=AUTH).json()
    assert "tiers_b" not in answer["tables"]
    named = client.post("/relationships/find", json={"tables": ["tiers_a", "tiers_b"]}, headers=AUTH)
    assert named.json()["tables"] == ["tiers_a", "tiers_b"]


# ===== the joins in use: delete, change, undo (the owner, 2026-11-17: "I cant mass delete anything") =====


def forty_joins() -> dict[str, Any]:
    """About 40 made-up foreign keys, as a database's import brings them."""
    return {
        "name": "Made-up ledger",
        "relationships": [
            {
                "from": f"fact_{i:02d}",
                "from_columns": ["account_key"],
                "to": "dim_account",
                "to_columns": ["key"],
            }
            for i in range(40)
        ],
    }


def key(i: int) -> dict[str, Any]:
    return {
        "from": f"fact_{i:02d}",
        "from_columns": ["account_key"],
        "to": "dim_account",
        "to_columns": ["key"],
    }


def test_delete_selected_joins_then_one_undo_brings_them_all_back(client: TestClient) -> None:
    client.post("/relationships", json={"model": forty_joins(), "replace": True}, headers=AUTH)
    gone = client.post("/relationships/delete", json={"joins": [key(i) for i in range(12)]}, headers=AUTH)
    assert gone.status_code == 200, gone.text
    body = gone.json()
    assert body["removed"] == 12 and len(body["relationships"]) == 28 and body["can_undo"]
    back = client.post("/relationships/undo", headers=AUTH).json()
    assert len(back["relationships"]) == 40 and back["undone"]
    assert [r["from"] for r in back["relationships"]][:2] == ["fact_00", "fact_01"]  # in their order
    bad = client.post("/relationships/delete", json={"joins": []}, headers=AUTH)
    assert bad.status_code == 400


def test_kind_and_run_are_changed_in_place_and_undone(client: TestClient) -> None:
    client.post("/relationships", json={"model": forty_joins(), "replace": True}, headers=AUTH)
    off = client.post(
        "/relationships/update", json={"joins": [key(1), key(2)], "active": False}, headers=AUTH
    ).json()
    assert off["changed"] == 2
    assert [r.get("active", True) for r in off["relationships"][:4]] == [True, False, False, True]
    one = client.post("/relationships/update", json={"joins": [key(0)], "kind": "one-to-one"}, headers=AUTH)
    assert one.json()["relationships"][0]["kind"] == "one-to-one"
    wrong = client.post("/relationships/update", json={"joins": [key(0)], "kind": "sideways"}, headers=AUTH)
    assert wrong.status_code == 400 and "kind must be one of" in wrong.text
    client.post("/relationships/undo", headers=AUTH)
    current = client.get("/relationships", headers=AUTH).json()
    assert current["relationships"][0]["kind"] == "many-to-one"  # the kind's change undone
    assert current["relationships"][1].get("active") is False  # the Run's change stays (one step back)


def test_the_agent_manages_joins_in_use_as_the_user_does(client: TestClient) -> None:
    from swissarmybench.cli import commands

    client.post("/relationships", json={"model": forty_joins(), "replace": True}, headers=AUTH)
    for path, body in (
        ("/relationships/delete", {"joins": [key(5)]}),
        ("/relationships/update", {"joins": [key(6)], "active": False}),
        ("/relationships/undo", None),
    ):
        assert client.post(path, json=body, headers=AGENT).status_code == 200, path
    for name in ("relationships_delete", "relationships_update", "relationships_undo"):
        assert name in commands.REGISTRY


# ===== saved sets: rename, delete, export; the old names =====


def save_one(client: TestClient, name: str = "Made-up ledger") -> dict[str, Any]:
    client.post("/relationships", json={"model": forty_joins(), "replace": True}, headers=AUTH)
    saved = client.post("/relationships/sets", json={"name": name}, headers=AUTH)
    assert saved.status_code == 200, saved.text
    return dict(saved.json())


def test_a_saved_set_is_one_stable_file_in_the_librarys_relationship_sets(
    client: TestClient, tmp_path: Path
) -> None:
    saved = save_one(client)
    path = Path(saved["file"])
    assert path.parent == tmp_path / "state" / "library" / "relationship-sets"
    assert path.name == "made-up_ledger.relationships.json"
    before = path.read_bytes()
    time.sleep(1.1)
    client.post("/relationships/sets", json={"name": "Made-up ledger"}, headers=AUTH)
    assert path.read_bytes() == before  # nothing but the time changed: no byte written


def test_rename_export_and_delete_a_saved_set(client: TestClient, tmp_path: Path) -> None:
    saved = save_one(client)
    renamed = client.patch("/relationships/sets/Made-up%20ledger", json={"name": "Ledger 2026"}, headers=AUTH)
    assert renamed.status_code == 200, renamed.text
    assert Path(renamed.json()["file"]).name == "ledger_2026.relationships.json"
    assert not Path(saved["file"]).exists()
    names = [m["name"] for m in client.get("/relationships/library", headers=AUTH).json()["models"]]
    assert "Ledger 2026" in names and "Made-up ledger" not in names
    exported = client.get("/relationships/sets/Ledger%202026", headers=AUTH)
    assert 'filename="ledger_2026.relationships.json"' in exported.headers["content-disposition"]
    assert read_set(exported.text).name == "Ledger 2026"
    save_one(client, "Other")
    taken = client.patch("/relationships/sets/Other", json={"name": "ledger 2026"}, headers=AUTH)
    assert taken.status_code == 400 and "there already" in taken.text
    assert client.delete("/relationships/sets/Ledger%202026", headers=AUTH).status_code == 200
    assert client.delete("/relationships/sets/Ledger%202026", headers=AUTH).status_code == 404


def test_the_agents_delete_of_a_saved_set_waits_for_the_users_allow(client: TestClient) -> None:
    save_one(client)

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
    refused = client.delete("/relationships/sets/Made-up%20ledger", headers=AGENT)
    thread.join()
    assert refused.status_code == 403
    thread = answer(True)
    assert client.delete("/relationships/sets/Made-up%20ledger", headers=AGENT).status_code == 200
    thread.join()
    # Rename is the agent's at once.
    save_one(client)
    renamed = client.patch(
        "/relationships/sets/Made-up%20ledger", json={"name": "Agent ledger"}, headers=AGENT
    )
    assert renamed.status_code == 200


def test_the_old_tang_names_answer_for_one_release(client: TestClient, tmp_path: Path) -> None:
    from swissarmybench.cli import commands

    client.post("/relationships", json={"model": forty_joins(), "replace": True}, headers=AUTH)
    saved = client.post("/relationships/tangs", json={"name": "Old route"}, headers=AUTH).json()
    assert saved["file"].endswith(".relationships.json")  # written under the new name
    assert read_set(client.get("/relationships/tang", headers=AUTH).text).name == "Old route"
    # An old .tang file in a shared folder, and {"tang": name} for a run, still read.
    team = tmp_path / "team"
    team.mkdir()
    old = json.loads(client.get("/relationships/set", headers=AUTH).text) | {"swissarmybench": "tang"}
    (team / "old.tang").write_text(json.dumps(old | {"name": "Old file"}), encoding="utf-8")
    client.put("/blades/folders", json={"folders": [str(team)]}, headers=AUTH)
    entry = next(
        m
        for m in client.get("/relationships/library", headers=AUTH).json()["models"]
        if m["name"] == "Old file"
    )
    assert entry["set"] and entry["where"] == "shared"
    ran = client.post("/relationships/check", json={"tang": "Old file"}, headers=AUTH)
    assert ran.status_code == 200 and ran.json()["set"] == "Old file"
    # The old commands run as the new ones and are never listed.
    for old_name, new in (
        ("relationships_save_tang", "relationships_save_set"),
        ("relationships_export_tang", "relationships_export_set"),
        ("relationships_import_tang", "relationships_import_set"),
    ):
        assert commands.current_name(old_name) == new and old_name not in commands.REGISTRY
    assert commands.OLD_ARGS[("relationships_check", "tang")] == "set"


# ===== a deleted connection's relationships (the owner, 2026-11-17) =====


def test_deleting_a_connection_removes_the_relationships_it_brought(
    client: TestClient, tmp_path: Path
) -> None:
    csv = tmp_path / "made-up.csv"
    csv.write_text("a\n1\n", encoding="utf-8")
    created = client.post(
        "/connections",
        json={
            "name": "FI-Atlas",
            "kind": "other",
            "template": "csv",
            "code": f'from pathlib import Path\npath = Path(r"{csv}")',
        },
        headers=AUTH,
    )
    assert created.status_code == 200, created.text
    model = forty_joins() | {
        "tables": {f"fact_{i:02d}": {"source": "connection:FI-Atlas"} for i in range(40)}
        | {"dim_account": {"source": "connection:FI-Atlas"}}
    }
    keep = {"from": "orders", "from_columns": ["customer_id"], "to": "customers", "to_columns": ["cust_key"]}
    model["relationships"] = [*model["relationships"], keep]
    client.post("/relationships", json={"model": model, "replace": True}, headers=AUTH)
    client.post("/relationships/sets", json={"name": "Kept set"}, headers=AUTH)
    gone = client.delete("/blades/FI-Atlas", headers=AUTH)
    assert gone.status_code == 200, gone.text
    assert gone.json()["relationships_removed"] == 40
    left = client.get("/relationships", headers=AUTH).json()["relationships"]
    assert [(r["from"], r["to"]) for r in left] == [("orders", "customers")]
    # Saved sets are the user's files: left alone.
    entry = next(
        m
        for m in client.get("/relationships/library", headers=AUTH).json()["models"]
        if m["name"] == "Kept set"
    )
    assert entry["relationships"] == 41
