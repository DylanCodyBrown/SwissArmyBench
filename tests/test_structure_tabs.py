"""A structure's tab beside the code (2026-11-22, the owner: "When we open a json or yaml or xml file is it
possible to open a collapsable navigation tree of nodes" / "I want it beside the ide so you can search and
explore" / "Does structures open as an ide? Or is it read only"): which page a structure's file opens on, the
Files pane's Structures group, the desktop app's file kinds, a node as code (shared with the page:
tests/golden/structure_code.json), the search, the tree's edits on the file itself, and the IDE's text over
HTTP (kept as typed, Format, Save of only changed bytes, a file changed on disk never written over).
Made-up data only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import code_tree, workbench_pages
from swissarmybench.domain import desktop as desktop_rules
from swissarmybench.domain import structures as rules
from swissarmybench.domain.structures import StructureError
from tests.conftest import AGENT, AUTH

GOLDEN = Path(__file__).resolve().parent / "golden" / "structure_code.json"
ORDERS = {
    "orders": [
        {"id": 1, "status": "open", "lines": [{"sku": "A-1", "qty": 2}]},
        {"id": 2, "status": "shipped", "lines": [{"sku": "B-7", "qty": 1}, {"sku": "A-1", "qty": 5}]},
    ],
    "source": {"name": "Made-up shop"},
}


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


# ===== which page, which pane, which kind =====


@pytest.mark.parametrize(
    ("path", "structure"),
    [
        ("orders.json", True),
        ("config.yaml", True),
        ("config.YML", True),
        ("feed.xml", True),
        ("pyproject.toml", True),
        ("structures/gates.json", True),
        (r"C:\work\shop\orders.json", True),
        ("sales.canvas.json", False),  # the Canvas page's
        ("workbook.design.json", False),  # the Excel canvas's
        ("old.stapp.json", False),  # the old app canvas: its one line
        (".sab/project.json", False),  # the app's own state
        ("/home/me/shop/.sab/model.json", False),
        (".hidden.json", False),
        ("load.py", False),
        ("data.ipynb", False),
        ("orders.jsonl", False),
        ("", False),
        (None, False),
    ],
)
def test_a_structures_file_is_told_apart(path: Any, structure: bool) -> None:
    assert workbench_pages.is_structure_path(path) is structure


def test_a_structure_opens_where_it_was_asked_from_else_on_the_scripts_page() -> None:
    # No page of its own: the page it was opened from keeps it (the window's own open()).
    assert workbench_pages.page_of_path("orders.json") is None
    # From outside (the desktop app, an old address, the agent with no page): the Scripts page.
    assert workbench_pages.home_of_path("orders.json") == "scripts"
    assert workbench_pages.home_of_path("data.ipynb") == "notebooks"
    assert workbench_pages.home_of_path("load.py") == "scripts"
    assert workbench_pages.home_of_path("sales.canvas.json") is None
    assert workbench_pages.old_address({"open": "orders.json"})[0] == "scripts"
    assert workbench_pages.page_for_command(None, {"path": "orders.json"}, "structure.open") == "scripts"
    assert (
        workbench_pages.page_for_command("notebooks", {"path": "orders.json"}, "structure.open")
        == "notebooks"
    )
    # Any other command on a structure: the window the user was last in.
    assert workbench_pages.page_for_command(None, {"path": "orders.json"}, "file.open") is None


def test_the_desktop_app_opens_a_structures_file_as_a_tab() -> None:
    assert desktop_rules.file_kind("orders.json", False, False) == desktop_rules.STRUCTURE
    assert desktop_rules.file_kind("config.yaml", False, False) == desktop_rules.STRUCTURE
    assert desktop_rules.file_kind("feed.xml", False, False) == desktop_rules.STRUCTURE
    assert desktop_rules.file_kind("events.jsonl", False, False) == desktop_rules.TABLE  # rows: a grid
    assert desktop_rules.file_kind("sales.canvas.json", False, False) == ""
    # A file an on extension claims stays the extension's.
    assert desktop_rules.file_kind("model.json", False, False, (".json",)) == desktop_rules.EXTENSION


def test_the_files_pane_lists_the_projects_structures_at_its_top_and_in_structures() -> None:
    files = [
        "orders.json",
        "config.yaml",
        "structures/feed.xml",
        "structures/deep/gates.toml",
        "scripts/settings.json",  # inside a folder that is not structures/: not listed
        "sales.canvas.json",
        "workbook.design.json",
        ".sab/project.json",
        "load.py",
        "builds/app/1/canvas.json",
    ]
    group = code_tree.structure_group(files)
    assert group is not None and group["name"] == "Structures"
    assert [f["path"] for f in group["files"]] == [
        "config.yaml",
        "orders.json",
        "structures/feed.xml",
        "structures/deep/gates.toml",
    ]
    assert code_tree.structure_group(["load.py", ".sab/project.json"]) is None


# ===== a node as code, the search, the tree's edits =====


def test_a_nodes_code_is_the_python_that_reaches_it() -> None:
    for case in json.loads(GOLDEN.read_text(encoding="utf-8")):
        parts = tuple(case["parts"])
        assert rules.format_path(parts) == case["path"], case
        assert rules.code_of(parts) == case["code"], case
        assert rules.code_of(case["path"]) == case["code"], case
        if case["code"] != "data":
            # The code is Python that runs: it reaches the same node.
            compile(case["code"], "<golden>", "eval")
    assert rules.code_of("$.orders[0]", "orders") == 'orders["orders"][0]'
    with pytest.raises(StructureError, match="many nodes"):
        rules.code_of("$.orders[*]")
    assert eval(rules.code_of("$.orders[1].lines[0].sku"), {"data": ORDERS}) == "B-7"  # noqa: S307 (our own text)


def test_search_finds_keys_and_values_in_the_documents_order() -> None:
    found = rules.search(ORDERS, "A-1")
    assert [f["path"] for f in found["found"]] == ["$.orders[0].lines[0].sku", "$.orders[1].lines[1].sku"]
    assert found["found"][0]["code"] == 'data["orders"][0]["lines"][0]["sku"]' and found["count"] == 2
    keys = rules.search(ORDERS, "STATUS")  # any case
    assert [(f["path"], f["where"]) for f in keys["found"]] == [
        ("$.orders[0].status", "key"),
        ("$.orders[1].status", "key"),
    ]
    assert rules.search(ORDERS, "5")["found"][-1]["path"] == "$.orders[1].lines[1].qty"
    assert rules.search(ORDERS, "  ")["found"] == []
    capped = rules.search({"items": list(range(30))}, "1", limit=3)
    assert len(capped["found"]) == 3 and capped["more"] is True and capped["count"] > 3


def test_the_trees_edits_change_the_file_and_leave_the_given_value_alone() -> None:
    before = json.loads(json.dumps(ORDERS))
    set_ = rules.edit(ORDERS, {"op": "set", "path": "$.orders[0].status", "value": "closed"})
    assert set_["orders"][0]["status"] == "closed" and ORDERS == before
    renamed = rules.edit(ORDERS, {"op": "rename", "path": "$.source", "key": "name", "to": "title"})
    assert list(renamed["source"]) == ["title"]
    added = rules.edit(ORDERS, {"op": "add", "path": "$.source", "key": "city", "value": "Leeds"})
    assert added["source"] == {"name": "Made-up shop", "city": "Leeds"}
    removed = rules.edit(ORDERS, {"op": "remove", "path": "$.orders[0]"})
    assert [o["id"] for o in removed["orders"]] == [2]
    twice = rules.edit(ORDERS, {"op": "duplicate", "path": "$.orders[0]"})
    assert [o["id"] for o in twice["orders"]] == [1, 1, 2]
    copied = rules.edit(ORDERS, {"op": "duplicate", "path": "$.source"})
    assert list(copied) == ["orders", "source", "source copy"]
    again = rules.edit(copied, {"op": "duplicate", "path": "$.source"})
    assert list(again) == ["orders", "source", "source copy 2", "source copy"]
    moved = rules.edit(ORDERS, {"op": "move", "path": "$.orders[1]", "to": 0})
    assert [o["id"] for o in moved["orders"]] == [2, 1]
    assert ORDERS == before
    with pytest.raises(StructureError, match="only a list's items move"):
        rules.edit(ORDERS, {"op": "move", "path": "$.source", "to": 0})
    with pytest.raises(StructureError, match="to is 0 to 1"):
        rules.edit(ORDERS, {"op": "move", "path": "$.orders[0]", "to": 5})
    with pytest.raises(StructureError, match="many nodes"):
        rules.edit(ORDERS, {"op": "set", "path": "$.orders[*].status", "value": "x"})
    with pytest.raises(StructureError, match="op is one of"):
        rules.edit(ORDERS, {"op": "pick", "path": "$.orders"})


# ===== the tab's IDE over HTTP =====


def test_the_text_is_kept_as_typed_and_the_tree_follows_it_once_it_parses(
    client: TestClient, tmp_path: Path
) -> None:
    file = tmp_path / "orders.json"
    text = json.dumps(ORDERS, indent=4) + "\n"
    file.write_text(text, encoding="utf-8")
    opened = ok(client.post("/structures/open", json={"path": str(file), "view": "file"}, headers=AUTH))
    sid = opened["id"]
    assert opened["text"] == text and opened["text_dirty"] is False and opened["hash"]
    # A step is a view of the file: the text stays the file's.
    ok(client.post(f"/structures/{sid}/steps", json={"op": "pick", "path": "$.orders"}, headers=AUTH))
    shown = ok(client.get(f"/structures/{sid}?view=file", headers=AUTH))
    assert shown["text"] == text and shown["value"] == ORDERS
    assert isinstance(ok(client.get(f"/structures/{sid}", headers=AUTH))["value"], list)
    # A broken text is kept (an IDE keeps what is typed); the tree keeps its last good value.
    broken = ok(client.put(f"/structures/{sid}", json={"text": text[:-10], "view": "file"}, headers=AUTH))
    assert broken["text_error"].startswith("Not JSON: line") and broken["value"] == ORDERS
    # Format refuses it until it parses.
    refused = client.post(f"/structures/{sid}/format", json={}, headers=AUTH)
    assert refused.status_code == 400 and "does not parse" in refused.text
    # Mended: the tree follows; Format writes it again with an indent of 2, the keys in their order.
    ok(client.put(f"/structures/{sid}", json={"text": json.dumps(ORDERS)}, headers=AUTH))
    formatted = ok(client.post(f"/structures/{sid}/format", json={"view": "file"}, headers=AUTH))
    assert formatted["text"] == json.dumps(ORDERS, indent=2, ensure_ascii=False) + "\n"
    assert list(json.loads(formatted["text"])) == ["orders", "source"]
    # Nothing written outside Save.
    assert file.read_text(encoding="utf-8") == text


def test_an_edit_in_the_tree_writes_the_text_again(client: TestClient, tmp_path: Path) -> None:
    file = tmp_path / "orders.json"
    file.write_text(json.dumps(ORDERS), encoding="utf-8")
    sid = ok(client.post("/structures/open", json={"path": str(file)}, headers=AUTH))["id"]
    edited = ok(
        client.post(
            f"/structures/{sid}/edit",
            json={"op": "set", "path": "$.orders[1].status", "value": "returned", "view": "file"},
            headers=AUTH,
        )
    )
    assert edited["value"]["orders"][1]["status"] == "returned"
    assert json.loads(edited["text"])["orders"][1]["status"] == "returned" and edited["text_dirty"] is True
    moved = ok(
        client.post(
            f"/structures/{sid}/edit", json={"op": "move", "path": "$.orders[1]", "to": 0}, headers=AGENT
        )
    )
    assert [o["id"] for o in json.loads(moved["text"])["orders"]] == [2, 1]
    found = ok(client.get(f"/structures/{sid}/search?words=returned", headers=AGENT))
    assert found["found"] == [
        {"path": "$.orders[0].status", "where": "value", "code": 'data["orders"][0]["status"]'}
    ]


def test_save_writes_only_changed_bytes_and_never_over_a_file_changed_on_disk(
    client: TestClient, tmp_path: Path
) -> None:
    file = tmp_path / "config.json"
    file.write_text('{"retries": 3}\n', encoding="utf-8")
    opened = ok(client.post("/structures/open", json={"path": str(file)}, headers=AUTH))
    sid, hash_ = opened["id"], opened["hash"]
    # The same bytes: nothing written.
    same = ok(
        client.post(f"/structures/{sid}/save", json={"text": '{"retries": 3}\n', "hash": hash_}, headers=AUTH)
    )
    assert same["written"] is None and same["text_dirty"] is False
    # Changed here: written as typed (its own spacing kept), the new hash said.
    text = '{"retries":   5}\n'
    saved = ok(client.post(f"/structures/{sid}/save", json={"text": text, "hash": hash_}, headers=AUTH))
    assert saved["written"] and file.read_text(encoding="utf-8") == text and saved["hash"] != hash_
    # Changed outside since: refused (Reload or Keep mine), never written over.
    file.write_text('{"retries": 9}\n', encoding="utf-8")
    conflict = client.post(
        f"/structures/{sid}/save", json={"text": '{"retries": 6}\n', "hash": saved["hash"]}, headers=AUTH
    )
    assert conflict.status_code == 409 and "changed on disk" in conflict.text
    assert file.read_text(encoding="utf-8") == '{"retries": 9}\n'
    # Keep mine: the next Save writes over it.
    kept = ok(client.post(f"/structures/{sid}/keep-mine", json={}, headers=AUTH))
    ok(
        client.post(
            f"/structures/{sid}/save", json={"text": '{"retries": 6}\n', "hash": kept["hash"]}, headers=AUTH
        )
    )
    assert file.read_text(encoding="utf-8") == '{"retries": 6}\n'
    # Reload: the file as it is on disk now.
    file.write_text('{"retries": 7}\n', encoding="utf-8")
    reloaded = ok(client.post(f"/structures/{sid}/reload", json={}, headers=AUTH))
    assert reloaded["text"] == '{"retries": 7}\n' and reloaded["value"] == {"retries": 7}
    # A text that does not parse is saved all the same, with a warning naming the line.
    warned = ok(
        client.post(
            f"/structures/{sid}/save", json={"text": '{"retries": \n', "hash": reloaded["hash"]}, headers=AUTH
        )
    )
    assert warned["warning"].startswith("Saved, but it does not parse: Not JSON: line")
    assert file.read_text(encoding="utf-8") == '{"retries": \n'


def test_save_as_text_keeps_the_steps_as_the_view(client: TestClient, tmp_path: Path) -> None:
    file = tmp_path / "orders.json"
    file.write_text(json.dumps(ORDERS, indent=4), encoding="utf-8")
    sid = ok(client.post("/structures/open", json={"path": str(file)}, headers=AUTH))["id"]
    ok(client.post(f"/structures/{sid}/steps", json={"op": "pick", "path": "$.source"}, headers=AUTH))
    copy = tmp_path / "copy.json"
    saved = ok(
        client.post(f"/structures/{sid}/save-as", json={"path": str(copy), "as_text": True}, headers=AUTH)
    )
    assert copy.read_text(encoding="utf-8") == json.dumps(ORDERS, indent=4) and len(saved["steps"]) == 1
