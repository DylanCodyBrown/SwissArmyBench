"""Structures over HTTP (services/structures.py): open, paste, steps, the text view, Open as grid, Save and
Save as, a project's .sab with a structure in it, and where code uses one. Made-up data only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks
from tests.conftest import AGENT, AUTH, make_client

GATES = {
    "gates": [{"name": "release", "on": True, "rollout": 50}, {"name": "beta", "on": False, "rollout": 5}]
}
PAYLOAD = {
    "orders": [
        {"id": 1, "total": 120.5, "customer": {"name": "Acme Ltd", "region": "North"}, "tags": ["new"]},
        {"id": 2, "total": "n/a", "customer": {"name": "Birch Co", "region": "South"}, "tags": []},
    ]
}


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def test_a_file_opens_takes_steps_and_saves_with_the_original_untouched_until_then(
    client: TestClient, tmp_path: Path
) -> None:
    file = tmp_path / "gates.json"
    file.write_text(json.dumps(GATES), encoding="utf-8")
    opened = ok(client.post("/structures/open", json={"path": str(file)}, headers=AUTH))
    assert (opened["name"], opened["format"], opened["dirty"]) == ("gates", "json", False)
    assert opened["value"] == GATES and json.loads(opened["text"]) == GATES
    sid = opened["id"]
    # The same file again: the same tab.
    assert ok(client.post("/structures/open", json={"path": str(file)}, headers=AUTH))["id"] == sid

    step = {"op": "filter", "path": "$.gates", "field": "on", "value": "true"}
    after = ok(client.post(f"/structures/{sid}/steps", json=step, headers=AUTH))
    assert [g["name"] for g in after["value"]["gates"]] == ["release"]
    assert after["steps"][0]["words"] == "Keep $.gates where on = true" and after["dirty"] is True
    assert json.loads(file.read_text(encoding="utf-8")) == GATES  # nothing written outside Save
    # The text is the file's own, editable with steps too (2026-11-22): the steps replay on what it says.
    broken = ok(client.put(f"/structures/{sid}", json={"text": '{"gates": ['}, headers=AUTH))
    assert "line 1" in broken["text_error"] and broken["text_dirty"] is True  # kept as typed, said where
    mended = ok(
        client.put(f"/structures/{sid}", json={"text": json.dumps(GATES), "view": "result"}, headers=AUTH)
    )
    assert mended["text_error"] is None and [g["name"] for g in mended["value"]["gates"]] == ["release"]
    # A step that cannot apply is refused before it is kept.
    bad = client.post(f"/structures/{sid}/steps", json={"op": "pick", "path": "$.nope"}, headers=AUTH)
    assert bad.status_code == 400 and "not there" in bad.text
    undone = ok(client.post(f"/structures/{sid}/undo", json={}, headers=AUTH))
    assert len(undone["value"]["gates"]) == 2 and undone["can_redo"] is True
    ok(client.post(f"/structures/{sid}/redo", json={}, headers=AUTH))
    saved = ok(client.post(f"/structures/{sid}/save", json={}, headers=AUTH))
    assert saved["steps"] == [] and saved["dirty"] is False
    assert json.loads(file.read_text(encoding="utf-8")) == {"gates": [GATES["gates"][0]]}


def test_paste_finds_the_format_and_the_text_view_edits_the_original(client: TestClient) -> None:
    pasted = ok(client.post("/structures/paste", json={"text": "<map><amt>amount</amt></map>"}, headers=AUTH))
    assert pasted["format"] == "xml" and pasted["value"] == {"map": {"amt": "amount"}}
    edited = ok(
        client.put(f"/structures/{pasted['id']}", json={"text": '{"amt": "amount_usd"}', "format": "json"},
                   headers=AUTH)
    )  # fmt: skip
    assert edited["format"] == "json"
    toml = ok(client.put(f"/structures/{pasted['id']}", json={"format": "toml"}, headers=AUTH))
    assert toml["text"] == 'amt = "amount_usd"\n'
    broken = client.post("/structures/paste", json={"text": '{"a": ', "format": "json"}, headers=AUTH)
    assert broken.status_code == 400 and "line 1" in broken.text
    entity = client.post(
        "/structures/paste", json={"text": '<!DOCTYPE x [<!ENTITY y "z">]><x>&y;</x>'}, headers=AUTH
    )
    assert entity.status_code == 400 and "refused" in entity.text


def test_open_as_grid_gives_the_records_as_rows_with_their_origin(client: TestClient) -> None:
    sid = ok(client.post("/structures", json={"value": PAYLOAD, "name": "payload"}, headers=AUTH))["id"]
    grid = ok(client.post(f"/structures/{sid}/grid", json={"path": "$.orders"}, headers=AUTH))
    assert grid["dataset"] == "payload_orders" and grid["rows"] == 2
    rows = ok(client.get(f"/grids/{grid['grid']}/rows?start=0&end=10", headers=AUTH))
    assert rows["columns"][:5] == ["id", "total", "customer.name", "customer.region", "tags"] or {
        c if isinstance(c, str) else c["name"] for c in rows["columns"]
    } >= {"id", "total", "customer.name", "customer.region", "tags"}
    flat = json.dumps(rows)
    assert "Acme Ltd" in flat and "n/a" in flat  # a column of numbers and text: text
    not_records = client.post(f"/structures/{sid}/grid", json={"path": "$.orders[0].customer"}, headers=AUTH)
    assert not_records.status_code == 400 and "not a list" in not_records.text


def test_the_agent_reads_a_shape_and_a_capped_preview(client: TestClient) -> None:
    from swissarmybench.cli import commands

    sid = ok(client.post("/structures", json={"value": PAYLOAD, "name": "payload"}, headers=AGENT))["id"]
    seen = ok(client.get(f"/structures/{sid}/describe?path=$.orders", headers=AGENT))
    assert seen["shape"]["count"] == 2 and seen["record_lists"] == ["$"]
    assert seen["shape"]["items"]["keys"]["customer"]["keys"]["region"] == {"type": "text"}
    assert "structures" in {area for area, _ in commands.AREAS}


def test_save_as_writes_each_format_into_the_projects_folder(client: TestClient, tmp_path: Path) -> None:
    sid = ok(client.post("/structures", json={"value": GATES, "name": "gates"}, headers=AUTH))["id"]
    written = ok(client.post(f"/structures/{sid}/save-as", json={"format": "toml"}, headers=AUTH))["written"]
    assert written.endswith("gates.toml") and "[[gates]]" in Path(written).read_text(encoding="utf-8")
    xml = ok(client.post(f"/structures/{sid}/save-as", json={"path": str(tmp_path / "g.xml")}, headers=AUTH))
    assert xml["format"] == "xml" and Path(xml["written"]).read_text(encoding="utf-8").startswith("<?xml")
    with_null = ok(client.post("/structures", json={"value": {"a": None}, "name": "n"}, headers=AUTH))["id"]
    refused = client.post(f"/structures/{with_null}/save-as", json={"format": "toml"}, headers=AUTH)
    assert refused.status_code == 400 and "save as JSON or YAML" in refused.text


@pytest.mark.skipif(__import__("importlib").util.find_spec("yaml") is None, reason="PyYAML is not here")
def test_yaml_reads_and_writes(client: TestClient, tmp_path: Path) -> None:
    file = tmp_path / "mapping.yaml"
    file.write_text("fields:\n  cust_id: customer_id\n  amt: amount\n", encoding="utf-8")
    opened = ok(client.post("/structures/open", json={"path": str(file)}, headers=AUTH))
    assert opened["value"] == {"fields": {"cust_id": "customer_id", "amt": "amount"}}
    rename = {"op": "rename", "path": "$.fields", "key": "amt", "to": "amount"}
    ok(client.post(f"/structures/{opened['id']}/steps", json=rename, headers=AUTH))
    ok(client.post(f"/structures/{opened['id']}/save", json={}, headers=AUTH))
    assert "amount: amount" in file.read_text(encoding="utf-8")
    bad = client.post("/structures/paste", json={"text": "a: [1, 2", "format": "yaml"}, headers=AUTH)
    assert bad.status_code == 400 and "Not YAML: line" in bad.text


def test_a_project_keeps_its_structures_and_opens_them_again(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        (tmp_path / "work").mkdir()
        target = tmp_path / "work" / "flags"
        state = ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))
        folder = Path(state["project"]["folder"])
        sid = ok(client.post("/structures", json={"value": GATES, "name": "gates"}, headers=AUTH))["id"]
        saved = ok(client.post(f"/structures/{sid}/save-as", json={"format": "json"}, headers=AUTH))
        assert Path(saved["written"]) == (folder / "structures" / "gates.json").resolve()
        listed = ok(client.get("/structures", headers=AUTH))["files"]
        assert [(f["name"], f["format"], f["open"]) for f in listed] == [("gates", "json", sid)]
        documents = ok(client.get("/project/documents", headers=AUTH))["documents"]
        assert {"path": "structures/gates.json", "kind": "structure"}.items() <= next(
            d for d in documents if d["kind"] == "structure"
        ).items()
        # Code that uses it: its references, as a connection's.
        cell = notebooks.Cell("code", 'import swissarmybench as sab\ngates = sab.structure("gates")')
        (folder / "analysis.ipynb").write_text(notebooks.write_notebook([cell]), encoding="utf-8")
        used = ok(client.get("/structures/references?name=gates", headers=AUTH))["references"]
        assert [(r["title"], r["how"]) for r in used] == [("analysis.ipynb", "sab.structure")]
        # Its lineage ends at the notebook cell that reads it.
        chain = ok(client.get(f"/structures/{sid}/lineage", headers=AUTH))
        cell = next(n for n in chain["nodes"] if n["kind"] == "cell")
        assert cell["where"] == "analysis.ipynb @cell1" and cell["reads"] == ["gates"]
        assert any(e["target"] == cell["id"] for e in chain["edges"])
        # sab.structure reads the saved file.
        assert (
            ok(client.get("/structures/saved?name=gates&path=$.gates[1].name", headers=AUTH))["value"]
            == "beta"
        )
        ok(client.post("/project/save", json={}, headers=AUTH))
        assert (target / "structures" / "gates.json").is_file()
        manifest = json.loads((target / ".sab" / "project.json").read_text(encoding="utf-8"))
        assert manifest["structures"] == {"open": ["structures/gates.json"]}
        ok(client.post("/project/close", json={}, headers=AUTH))
        assert ok(client.get("/structures", headers=AUTH))["open"] == []
        ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))
        back = ok(client.get("/structures", headers=AUTH))["open"]
        assert [(s["name"], s["format"]) for s in back] == [("gates", "json")]
