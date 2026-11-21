"""The Scripts explorer's tree actions (2026-11-21): New package, Rename (the module's imports following, a
preview first, as F2's rename), Duplicate, and Delete to the trash (the user's own: 403 for the agent).
Made-up project files only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain.script_ide import free_copy_name, import_rewrite, move_plan
from tests.conftest import AGENT, AUTH, make_client
from tests.test_script_ide import ok, project


def test_a_modules_imports_follow_its_new_name() -> None:
    text = (
        "import etl.load\nfrom etl.load import tidy\nfrom etl import load, other\n"
        "import etl.loaded\nfrom etl.load.parts import x\nnote = 'etl.load'\n"
    )
    same_package = import_rewrite(text, "etl.load", "etl.loader")
    assert same_package.split("\n")[:5] == [
        "import etl.loader",
        "from etl.loader import tidy",
        "from etl import loader as load, other",  # its name in this module stays
        "import etl.loaded",  # another module that only starts the same
        "from etl.loader.parts import x",
    ]
    assert "note = 'etl.load'" in same_package  # text, not an import
    moved = import_rewrite("from etl import load, other\n", "etl.load", "clean.load")
    assert moved == "from etl import other\nfrom clean import load\n"  # the others stay where they are
    assert import_rewrite("x = (\n", "etl.load", "etl.loader") == "x = (\n"  # not Python: as it was
    plan = move_plan(
        {"/p/a.py": "import etl.load\n", "/p/data.py": "import etl.load\n"},
        "/p/b.py",
        "etl.load",
        "etl.l2",
        {"/p/data.py"},
    )
    assert list(plan["changes"]) == ["/p/a.py"] and plan["skipped"][0]["path"] == "/p/data.py"
    assert free_copy_name("scripts/load.py", {"scripts/load_copy.py"}) == "scripts/load_copy_2.py"


def test_new_package_rename_duplicate_and_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))  # a made-up trash
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        (folder / "scripts" / "report.py").write_text(
            "from etl.load import Loader\nfrom etl import load\n", encoding="utf-8"
        )
        made = ok(client.post("/scripts/files/package", json={"name": "clean"}, headers=AGENT))
        assert made["package"] == "clean" and (folder / "scripts" / "clean" / "__init__.py").is_file()
        taken = client.post("/scripts/files/package", json={"name": "clean"}, headers=AUTH)
        assert taken.status_code == 409
        load = str(folder / "scripts" / "etl" / "load.py")
        plan = ok(client.post("/scripts/files/move", json={"path": load, "to": "loader"}, headers=AGENT))
        assert plan["applied"] is False and plan["new_module"] == "etl.loader"
        lines = [line for p in plan["preview"] for line in p["lines"]]
        assert {
            "line": 1,
            "before": "from etl.load import Loader",
            "after": "from etl.loader import Loader",
        } in lines
        assert (folder / "scripts" / "etl" / "load.py").is_file()  # a plan writes nothing
        done = ok(
            client.post(
                "/scripts/files/move", json={"path": load, "to": "loader", "apply": True}, headers=AGENT
            )
        )
        assert done["applied"] and not Path(load).exists()
        assert (folder / "scripts" / "report.py").read_text(encoding="utf-8") == (
            "from etl.loader import Loader\nfrom etl import loader as load\n"
        )
        # A package renamed: everything under it follows.
        ok(
            client.post(
                "/scripts/files/move",
                json={"path": str(folder / "scripts" / "etl"), "to": "pipeline", "apply": True},
                headers=AUTH,
            )
        )
        assert "from pipeline.loader import Loader" in (folder / "scripts" / "report.py").read_text(
            encoding="utf-8"
        )
        # A made file is never renamed or deleted here.
        refused = client.post(
            "/scripts/files/move", json={"path": str(folder / "data.py"), "to": "d2"}, headers=AUTH
        )
        assert refused.status_code == 403 and "data.ipynb" in refused.text
        outside = client.post("/scripts/files/move", json={"path": "../../x.py", "to": "y"}, headers=AUTH)
        assert outside.status_code == 403
        copy = ok(
            client.post(
                "/scripts/files/duplicate",
                json={"path": str(folder / "scripts" / "report.py")},
                headers=AGENT,
            )
        )
        assert copy["path"].endswith("scripts/report_copy.py") and Path(copy["path"]).is_file()
        # Delete: the user's own, to the trash.
        agent: Any = client.post("/scripts/files/delete", json={"path": copy["path"]}, headers=AGENT)
        assert agent.status_code == 403 and Path(copy["path"]).is_file()
        gone = ok(client.post("/scripts/files/delete", json={"path": copy["path"]}, headers=AUTH))
        assert gone["to"] == "the Trash" and not Path(copy["path"]).exists()
        assert (tmp_path / "share" / "Trash" / "files" / "report_copy.py").is_file()


# ===== go to definition into a library: its source, read-only =====


def test_a_librarys_source_opens_read_only_and_nothing_else_does(tmp_path: Path) -> None:
    from swissarmybench.domain.script_ide import library_file

    roots = ("/usr/lib/python3.12",)
    assert library_file("/usr/lib/python3.12/json/__init__.py", roots)
    assert library_file("/home/a/.venv/lib/python3.12/site-packages/pandas/core/frame.py", ())
    assert not library_file("/home/a/secrets.py", roots)  # another file of the computer's
    assert not library_file("/usr/lib/python3.12/../../etc/passwd.py", roots)
    assert not library_file("/usr/lib/python3.12/json/data.json", roots)
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        text = "import json\n\njson.dumps(1)\n"
        found = ok(
            client.post(
                "/scripts/definition",
                json={"text": text, "line": 3, "column": 7, "source": True},
                headers=AGENT,
            )
        )
        place = found["definitions"][0]
        assert (
            place["in_project"] is False and place["path"].endswith(".py") and "def dumps" in place["source"]
        )
        shown = ok(client.post("/scripts/library-file", json={"path": place["path"]}, headers=AUTH))
        assert shown["read_only"] is True and "def dumps" in shown["text"]
        refused = client.post(
            "/scripts/library-file", json={"path": str(folder / "functions.py")}, headers=AUTH
        )
        assert refused.status_code == 403
