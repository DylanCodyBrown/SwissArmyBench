"""The Accounting extension in the app (its routes, the project type and its mode, the agent's commands):
on through SWISSARMYBENCH_EXTENSIONS, and off (nothing of it shows). Made-up data only."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from openpyxl import load_workbook
from starlette.testclient import TestClient

from swissarmybench import extensions
from tests import accounting_data as made_up
from tests.conftest import AGENT, AUTH, grid_id, make_client, push
from tests.test_accounting_statements import BINDINGS, make_template


@pytest.fixture
def on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("SWISSARMYBENCH_EXTENSIONS", "accounting")
    with make_client(tmp_path) as test_client:
        yield test_client


def _table(frame: Any) -> pa.Table:
    return pa.Table.from_pandas(frame, preserve_index=False)


def test_the_capability_check() -> None:
    assert extensions.extension_on("accounting", {"SWISSARMYBENCH_EXTENSIONS": "accounting"})
    assert (
        not extensions.extension_on("accounting", {"SWISSARMYBENCH_EXTENSIONS": ""})
        or "accounting" in extensions.installed()
    )
    assert not extensions.extension_on("accounting", {"SWISSARMYBENCH_EXTENSIONS": "accounting,-accounting"})


def test_off_nothing_of_accounting_shows(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/accounting", headers=AUTH).status_code == 404
    assert [m["type"] for m in client.get("/app/modes", headers=AUTH).json()["modes"]] == ["bi"]
    answer = client.post(
        "/projects", json={"folder": str(tmp_path), "name": "books", "type": "accounting"}, headers=AUTH
    )
    assert answer.status_code == 400 and "No installed extension makes a accounting project" in answer.text
    from swissarmybench.cli.commands import REGISTRY

    assert not [n for n in REGISTRY if n.startswith(("workbook_", "template_", "statements_"))]


def test_an_accounting_project_sets_its_mode(on: TestClient, tmp_path: Path) -> None:
    about = on.get("/accounting", headers=AUTH).json()
    assert about["mode"]["canvases"] == ["excel"] and "pivot" in about["kinds"]
    assert [m["type"] for m in on.get("/app/modes", headers=AUTH).json()["modes"]] == ["bi", "accounting"]
    assert on.get("/app/mode", headers=AUTH).json()["mode"]["type"] == "bi"  # no project: the base's
    made = on.post(
        "/projects", json={"folder": str(tmp_path), "name": "books", "type": "accounting"}, headers=AUTH
    )
    assert made.status_code == 200, made.text
    folder = Path(made.json()["folder"])
    assert json.loads((folder / ".sab" / "project.json").read_text()) == {"type": "accounting"}
    assert (folder / "workbook.design.json").exists() and (folder / "workbook.py").exists()
    assert not list(folder.glob("*.stapp.json"))  # no Streamlit app in an Accounting project
    assert any(p.endswith("workbook.design.json") for p in made.json()["files"])
    mode = on.get("/app/mode", headers=AUTH).json()
    assert mode["project_type"] == "accounting"
    assert mode["mode"]["families"] == ["Excel", "Write", "Files"] and mode["mode"]["tools"][0] == "workbook_"
    # Another project (the base's type): the base's mode, the Excel canvas not offered.
    other = on.post("/projects", json={"folder": str(tmp_path), "name": "analysis"}, headers=AUTH).json()
    assert not (Path(other["folder"]) / ".sab" / "project.json").exists()  # the base's type: no file
    assert on.get("/app/mode", headers=AUTH).json()["mode"]["canvases"] == ["streamlit"]


def test_design_play_download_and_export(on: TestClient, tmp_path: Path) -> None:
    grid = grid_id(push(on, "cessions", _table(made_up.cessions())))
    # The grid's steps count: Play reads the table as it is shown.
    on.post(
        f"/grids/{grid}/steps",
        json={"steps": [{"kind": "filter", "params": {"column": "period", "op": "eq", "value": "2026-Q1"}}]},
        headers=AUTH,
    )
    opened = on.post("/accounting/designs", json={"title": "Cessions"}, headers=AUTH).json()
    wid = opened["id"]
    sheet = opened["design"]["sheets"][0]["id"]
    table = on.post(
        f"/accounting/designs/{wid}/sheets/{sheet}/blocks",
        json={
            "kind": "table",
            "cell": "A3",
            "source": {"table": "cessions"},
            "columns": [{"name": "cedant"}, {"name": "premium", "format": "currency", "total": "sum"}],
            "total_row": True,
        },
        headers=AUTH,
    ).json()
    assert table["tables"] == ["cessions"] and table["missing"] == []
    pivot = on.post(
        f"/accounting/designs/{wid}/sheets/{sheet}/blocks",
        json={
            "kind": "pivot",
            "cell": "E3",
            "source": {"query": "SELECT * FROM cessions"},
            "rows": ["treaty"],
            "values": [{"column": "claims", "agg": "sum"}],
        },
        headers=AUTH,
    ).json()
    chart = on.post(
        f"/accounting/designs/{wid}/sheets/{sheet}/blocks",
        json={"kind": "chart", "cell": "E10", "chart": "bar", "from": pivot["block"]},
        headers=AUTH,
    ).json()
    assert chart["block"]
    moved = on.patch(
        f"/accounting/designs/{wid}/blocks/{chart['block']}", json={"cell": "H10", "w": 7}, headers=AUTH
    ).json()
    assert (
        next(b for b in moved["design"]["sheets"][0]["blocks"] if b["id"] == chart["block"])["cell"] == "H10"
    )
    assert on.patch(f"/accounting/designs/{wid}/blocks/nope", json={}, headers=AUTH).status_code == 400
    played = on.post(f"/accounting/designs/{wid}/play", headers=AUTH).json()
    rows = played["preview"]["sheets"][0]["rows"]
    assert rows[2][0]["t"] == "cedant" and rows[2][1]["t"] == "premium"
    assert (
        len([r for r in rows[3:] if r and r[0] and r[0].get("t") in made_up.CEDANTS]) == 9
    )  # Q1 only: the grid's filter
    total = next(r for r in rows if r and r[0] and r[0].get("t") == "Total")
    assert total[1]["formula"].startswith("=SUM(B4:B12)") and total[1]["t"].startswith("$")
    assert played["preview"]["sheets"][0]["charts"][0]["kind"] == "bar"
    download = on.get(f"/accounting/designs/{wid}/download", headers=AUTH)
    assert download.status_code == 200 and download.headers["content-type"].startswith(
        "application/vnd.openxml"
    )
    assert load_workbook(io.BytesIO(download.content)).sheetnames == ["Summary"]
    assert on.get(f"/accounting/designs/{wid}", headers=AUTH).json()["out_of_date"] is False
    on.patch(f"/accounting/designs/{wid}/blocks/{table['block']}", json={"total_row": False}, headers=AUTH)
    assert on.get(f"/accounting/designs/{wid}", headers=AUTH).json()["out_of_date"] is True
    # Saved (no rows in the file), then exported beside it.
    path = tmp_path / "workbook.design.json"
    saved = on.post(f"/accounting/designs/{wid}/save", json={"path": str(path)}, headers=AUTH).json()
    assert saved["unsaved"] is False and "Ashgrove" not in path.read_text()
    exported = on.post(f"/accounting/designs/{wid}/export", json={}, headers=AUTH).json()
    assert Path(exported["path"]) == tmp_path / "workbook.py" and exported["tables"] == ["cessions"]
    # A table that is not open is said.
    on.delete("/datasets/cessions", headers=AUTH)
    missing = on.post(f"/accounting/designs/{wid}/play", headers=AUTH)
    assert missing.status_code == 404 and "cessions is not open" in missing.text


def test_templates_bind_and_build_dry_run_first(on: TestClient, tmp_path: Path) -> None:
    folder = Path(
        on.post(
            "/projects", json={"folder": str(tmp_path), "name": "books", "type": "accounting"}, headers=AUTH
        ).json()["folder"]
    )
    push(on, "statements", _table(made_up.statements()))
    push(on, "lines", _table(made_up.lines()))
    source = make_template(tmp_path / "Made-up statement.xlsx")
    imported = on.post(
        "/accounting/templates/import", json={"source": str(source), "name": "statement"}, headers=AUTH
    ).json()
    assert (folder / "templates" / "statement.xlsx").exists() and imported["bindings"] == []
    assert imported["preview"]["names"]["Cedant"] == "Statement!B3"
    assert "A15:E15" in imported["preview"]["sheets"][0]["merged"]
    for binding in BINDINGS:
        shown = on.post(
            "/accounting/templates/bind", json={"name": "statement", "binding": binding}, headers=AUTH
        ).json()
    assert len(shown["bindings"]) == 5 and shown["needs"]["data"] == ["cedant", "period"]
    wrong = on.post(
        "/accounting/templates/bind",
        json={"name": "statement", "binding": {"kind": "value", "place": "Nowhere", "value": {"text": "x"}}},
        headers=AUTH,
    )
    assert wrong.status_code == 400
    build = {
        "template": "statement",
        "data": "statements",
        "lines": "lines",
        "group_by": ["cedant", "period"],
        "name": "{cedant} {period}.xlsx",
        "number": {"start": 1, "pattern": "ST-{n:03d}"},
        "date": "2026-04-02",
    }
    # The real build without its dry run: refused, nothing written.
    early = on.post("/accounting/build", json=build | {"dry_run": False}, headers=AUTH)
    assert early.status_code == 409 and "Dry run first" in early.text
    plan = on.post("/accounting/build", json=build, headers=AUTH).json()
    assert plan["dry_run"] and plan["count"] == 6 and not (folder / "statements").exists()
    assert plan["files"][0]["file"] == "Ashgrove Mutual 2026-Q1.xlsx"
    # The agent's real build after the dry run waits for the user: here nobody answers in time... so the
    # test asks as the user instead, which needs no Allow.
    built = on.post("/accounting/build", json=build | {"dry_run": False}, headers=AUTH).json()
    assert not built["dry_run"] and len(list((folder / "statements").glob("*.xlsx"))) == 6
    register = on.post("/accounting/register", json={"open": True}, headers=AUTH).json()
    assert len(register["rows"]) == 6 and register["grid"]
    assert on.post("/accounting/build", json=build | {"dry_run": False}, headers=AGENT).status_code == 409


def test_the_agents_commands_are_the_extensions_when_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from swissarmybench_accounting import extension

    names = set(extension.commands())
    assert {
        "workbook_open",
        "workbook_block",
        "workbook_play",
        "template_import",
        "template_bind",
        "statements_build",
        "statements_register",
    } <= names
    assert all(n.startswith(tuple(extension.MODE["tools"])) for n in names)
    called: list[tuple[str, str, Any]] = []
    from swissarmybench.cli import api

    def fake(method: str, path: str, body: Any = None, **_: Any) -> Any:
        called.append((method, path, body))
        return {}

    monkeypatch.setattr(api, "call", fake)
    extension.commands()["statements_build"].run({"template": "statement", "data": "statements"})
    assert called[-1] == (
        "POST",
        "/accounting/build",
        {"template": "statement", "data": "statements", "dry_run": True},
    )


def test_the_package_declares_its_entry_point_on_the_bases_version() -> None:
    import tomllib

    import swissarmybench_accounting

    root = Path(__file__).resolve().parents[1]
    base = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    own = tomllib.loads((root / "extensions" / "accounting" / "pyproject.toml").read_text())
    assert own["project"]["name"] == "swissarmybench-accounting"
    assert own["project"]["version"] == base == swissarmybench_accounting.__version__
    assert own["project"]["dependencies"] == [f"swissarmybench[server]=={base}"]
    assert own["project"]["entry-points"]["swissarmybench.extensions"] == {
        "accounting": "swissarmybench_accounting.extension:describe"
    }


def test_the_mcp_lists_the_modes_tools_first(monkeypatch: pytest.MonkeyPatch) -> None:
    from swissarmybench.cli import api
    from swissarmybench.mcp import server as mcp_server

    manager = mcp_server.server._tool_manager
    monkeypatch.setattr(api, "call", lambda *a, **k: {"mode": {"tools": ["project_"]}})
    first = [t.name for t in manager.list_tools()]
    assert first[0].startswith("project_") and all(
        n.startswith("project_") for n in first[: sum(n.startswith("project_") for n in first)]
    )

    def down(*a: Any, **k: Any) -> Any:
        raise api.CommandError("no app")

    monkeypatch.setattr(api, "call", down)
    from swissarmybench.cli.commands import REGISTRY

    assert next(t.name for t in manager.list_tools()) == next(iter(REGISTRY))
