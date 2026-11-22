"""The Scripts page as a Python IDE over HTTP (services/script_ide.py, services/code_files.py): the tree of a
made-up project (packages, pages, made files, never a notebook), outlines, go to definition and references
across modules, a rename's preview that skips a made file, search and replace, format, Fine-tune as a script,
a made file edited by hand kept from a regenerate, and the file_changed notice on each kind of change."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.conftest import AGENT, AUTH, PORT, make_client

HOST = {"Host": f"127.0.0.1:{PORT}"}
FUNCTIONS = 'def tidy(name: str) -> str:\n    """Trim a made-up name."""\n    return name.strip()\n'
LOAD = (
    "from functions import tidy\n\nORDERS = 'orders'\n\n\n"
    "class Loader:\n    def run(self):\n        return tidy(ORDERS)\n"
)


def ok(answer: Any) -> Any:
    assert answer.status_code == 200, answer.text
    return answer.json()


def project(client: TestClient, tmp_path: Path) -> Path:
    state = ok(client.post("/project/new", json={"path": str(tmp_path / "work" / "shop")}, headers=AUTH))
    folder = Path(state.get("folder") or state["project"]["folder"])
    (folder / "functions.py").write_text(FUNCTIONS, encoding="utf-8")
    (folder / "scripts" / "etl").mkdir(parents=True, exist_ok=True)
    (folder / "scripts" / "etl" / "__init__.py").write_text("", encoding="utf-8")
    (folder / "scripts" / "etl" / "load.py").write_text(LOAD, encoding="utf-8")
    (folder / "pages").mkdir(exist_ok=True)
    (folder / "pages" / "home.py").write_text(
        "import streamlit as st\nst.write('made-up')\n", encoding="utf-8"
    )
    (folder / "data.py").write_text("from functions import tidy\nname = tidy(' a ')\n", encoding="utf-8")
    return folder


def next_of(page: Any, kind: str) -> dict[str, Any]:
    """The next notice of that type (a Session entry and others come between)."""
    for _ in range(20):
        said = page.receive_json()
        if said.get("type") == kind:
            return dict(said)
    raise AssertionError(f"no {kind} notice")


def files_of(tree: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["path"]: f | {"group": g["id"]} for g in tree["groups"] for f in g["files"]}


def test_the_tree_is_every_py_by_module_with_its_outline_and_never_a_notebook(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        tree = ok(client.get("/scripts/tree", headers=AUTH))
        found = files_of(tree)
        assert not any(p.endswith(".ipynb") for p in found)  # data.ipynb is the Notebooks page's
        load = found["scripts/etl/load.py"]
        assert load["group"] == "scripts" and load["module"] == "etl.load"
        assert [(s["name"], s["kind"]) for s in load["outline"]] == [
            ("ORDERS", "constant"),
            ("Loader", "class"),
        ]
        assert load["outline"][1]["children"][0]["name"] == "run"
        assert found["scripts/etl/__init__.py"]["module"] == "etl"
        data = found["data.py"]
        assert data["group"] == "project" and data["made_from"] == "data.ipynb" and data["read_only"]
        assert found["pages/home.py"]["made_from"] == "the app's canvas"
        assert found["functions.py"]["read_only"] is False
        assert {g["id"] for g in tree["groups"]} >= {"scripts", "project", "library-connections", "generated"}
        notebooks = ok(client.get("/project/tree?page=notebooks", headers=AUTH))
        assert [f["name"] for g in notebooks["groups"] for f in g["files"]] == ["data.ipynb"]
        # The outline as typed; a syntax error says where (the page keeps its last one).
        typed = ok(
            client.post("/project/module-outline", json={"text": "def f():\n    pass\n"}, headers=AUTH)
        )
        assert typed["symbols"][0]["name"] == "f"
        broken = ok(client.post("/project/module-outline", json={"text": "def f(:\n"}, headers=AUTH))
        assert broken["symbols"] == [] and broken["error"]["line"] == 1
        assert folder.is_dir()


def test_definition_and_references_cross_modules(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        load = str(folder / "scripts" / "etl" / "load.py")
        # sys.path: the project's top and scripts/ (functions imported from a script).
        at = {"text": LOAD, "line": 8, "column": 17, "path": load}  # tidy(ORDERS) in run()
        said = ok(client.post("/scripts/definition", json=at, headers=AGENT))["definitions"]
        assert said and said[0]["path"].endswith("functions.py") and said[0]["line"] == 1
        refs = ok(client.post("/scripts/references", json=at, headers=AGENT))["references"]
        assert {Path(r["path"]).name for r in refs} >= {"load.py", "functions.py"}


def test_rename_previews_skips_a_made_file_and_applies(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        functions = str(folder / "functions.py")
        at = {"text": FUNCTIONS, "line": 1, "column": 5, "path": functions, "to": "neat"}
        plan = ok(client.post("/scripts/rename", json=at, headers=AGENT))
        assert plan["applied"] is False
        changed = {Path(p).name for p in plan["changes"]}
        assert "functions.py" in changed and "load.py" in changed
        assert [Path(s["path"]).name for s in plan["skipped"]] == [
            "data.py"
        ]  # made: its source is data.ipynb
        assert "Edit by hand" in plan["skipped"][0]["why"]
        with client.websocket_connect("/ws?workspace=1", headers=AUTH | HOST) as page:
            done = ok(client.post("/scripts/rename", json=at | {"apply": True}, headers=AGENT))
            notices = [next_of(page, "file_changed") for _ in range(len(done["written"]))]
        assert "def neat(" in (folder / "functions.py").read_text(encoding="utf-8")
        assert "import neat" in (folder / "scripts" / "etl" / "load.py").read_text(encoding="utf-8")
        assert "tidy" in (folder / "data.py").read_text(encoding="utf-8")  # never touched
        assert {n["type"] for n in notices} == {"file_changed"} and all(n["hash"] for n in notices)
        bad = client.post("/scripts/rename", json=at | {"to": "class"}, headers=AGENT)
        assert bad.status_code == 400
        # The change log hears each script the rename wrote (the sweep, 2026-11-22: only a document's own
        # Save was heard), by the functions it changed and whose doing it was.
        asked = {"action": "last", "object": "script:functions.py"}
        change = ok(client.get("/changes", params=asked, headers=AUTH))["change"]
        assert change["who"] == "agent" and "neat" in change["words"] and "tidy" in change["words"]
        loaded = ok(
            client.get("/changes", params={"action": "last", "object": "script:load.py"}, headers=AUTH)
        )
        assert loaded["change"]["who"] == "agent"


def test_search_and_replace_across_the_scripts(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        found = ok(client.post("/scripts/search", json={"query": "tidy"}, headers=AGENT))
        assert {Path(r["path"]).name for r in found["results"]} == {"functions.py", "load.py", "data.py"}
        regex = {"query": r"ORD\w+", "regex": True, "case": True}
        assert ok(client.post("/scripts/search", json=regex, headers=AGENT))["count"] == 2
        plan = ok(
            client.post(
                "/scripts/replace", json={"query": "ORDERS", "to": "LINES", "case": True}, headers=AGENT
            )
        )
        assert plan["applied"] is False and plan["count"] == 2
        ok(
            client.post(
                "/scripts/replace",
                json={"query": "ORDERS", "to": "LINES", "case": True, "apply": True},
                headers=AGENT,
            )
        )
        assert "LINES = 'orders'" in (folder / "scripts" / "etl" / "load.py").read_text(encoding="utf-8")
        # A made file is never replaced in.
        plan = ok(client.post("/scripts/replace", json={"query": "name", "to": "who"}, headers=AGENT))
        assert any(Path(s["path"]).name == "data.py" for s in plan["skipped"])


def test_a_duplicate_and_a_replace_are_in_the_change_log(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        copied = ok(
            client.post("/scripts/files/duplicate", json={"path": str(folder / "functions.py")}, headers=AUTH)
        )
        name = Path(copied["path"]).name
        made = ok(client.get("/changes", params={"action": "last", "object": f"script:{name}"}, headers=AUTH))
        assert made["change"]["words"] == f"Added the script {name}"
        body = {"query": "tidy", "to": "neat", "case": True, "apply": True}
        done = ok(client.post("/scripts/replace", json=body, headers=AUTH))
        assert done["written"]
        changed = ok(
            client.get("/changes", params={"action": "last", "object": "script:functions.py"}, headers=AUTH)
        )
        assert changed["change"]["who"] == "user" and "neat" in changed["change"]["words"]


def test_format_needs_ruff_in_the_scripts_python(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        project(client, tmp_path)
        said = ok(
            client.post("/scripts/format", json={"text": "x=1\n", "python": "/no/such/python"}, headers=AGENT)
        )
        assert said["formatted"] is False and "Ruff" in said["why"]
        ruff = shutil.which("ruff")
        if ruff is None:
            pytest.skip("Ruff is not installed beside this Python")


def test_fine_tune_makes_a_working_script(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        made_table = ok(
            client.post(
                "/datasets/plums/query",
                json={"sql": "SELECT 1 AS id, 7 AS plums UNION ALL SELECT 2, 3"},
                headers=AUTH,
            )
        )
        grid = made_table["grid"]
        ok(
            client.post(
                f"/grids/{grid}/steps",
                json={"steps": [{"kind": "filter", "params": {"column": "plums", "op": "gt", "value": 5}}]},
                headers=AUTH,
            )
        )
        tree = ok(client.get("/scripts/tree", headers=AUTH))
        generated = next(g for g in tree["groups"] if g["id"] == "generated")
        assert generated["files"][0]["name"] == "plums" and generated["files"][0]["read_only"]
        made = ok(client.post("/scripts/fine-tune", json={"table": "plums"}, headers=AGENT))
        path = Path(made["path"])
        assert path.parent == folder / "scripts" and path.name == "plums_tuned.py"
        text = path.read_text(encoding="utf-8")
        compile(text, path.name, "exec")
        assert "plums" in text and "duckdb" in text
        refused = client.post("/scripts/fine-tune", json={"table": "pears"}, headers=AGENT)
        assert refused.status_code == 403 and "not open" in refused.text


def test_data_py_edited_by_hand_is_kept_and_a_regenerate_asks(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        data = folder / "data.py"
        edited = "# tuned by hand\nname = 'kept'\n"
        ok(
            client.post(
                "/workbench/save", json={"path": str(data), "text": edited, "force": True}, headers=AUTH
            )
        )
        tree = files_of(ok(client.get("/scripts/tree", headers=AUTH)))
        assert tree["data.py"]["edited"] is True and tree["data.py"]["read_only"] is False
        asked = client.post("/projects/export-data", json={"folder": str(folder)}, headers=AUTH)
        assert asked.status_code == 409 and "edited by hand" in asked.text
        assert data.read_text(encoding="utf-8") == edited
        ok(client.post("/projects/export-data", json={"folder": str(folder), "replace": True}, headers=AUTH))
        assert data.read_text(encoding="utf-8") != edited


def test_file_changed_on_a_save_and_an_outside_edit(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        load = folder / "scripts" / "etl" / "load.py"
        ctx = client.app.state.ctx  # type: ignore[attr-defined]
        portal = client.portal
        assert portal is not None
        portal.call(ctx.code_files.look)  # the first look learns what is there
        with client.websocket_connect("/ws?workspace=1", headers=AUTH | HOST) as page:
            saved = ok(
                client.post(
                    "/workbench/save",
                    json={"path": str(load), "text": "x = 2\n", "force": True},
                    headers=AUTH,
                )
            )
            said = next_of(page, "file_changed")
            assert said == {
                "type": "file_changed",
                "path": str(load.resolve()),
                "hash": saved["hash"],
                "by": "user",
            }
            opened = ok(client.post("/workbench/open", json={"path": str(load)}, headers=AUTH))
            assert opened["hash"] == saved["hash"] and opened["page"] == "scripts"
            load.write_text("x = 3\n", encoding="utf-8")  # an editor outside the app
            assert portal.call(ctx.code_files.look) == [str(load.resolve())]
            outside = next_of(page, "file_changed")
            assert outside["by"] == "outside" and outside["hash"] != saved["hash"]
            load.unlink()
            portal.call(ctx.code_files.look)
            assert next_of(page, "file_changed")["hash"] is None  # gone: the tab says so
