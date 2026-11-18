"""The Project Explorer (domain/project_explorer.py, services/project_explorer.py; the owner, 2026-11-17:
"Make the project page sortable by card with explanations of project types for beginners"): cards from a
made-up projects folder (types, counts, the Git branch from a made-up .git/HEAD), every sort order and the
custom order kept, filters, a missing folder, rename, remove from the list, the types explained (the
base's, and an extension's when it is on), the agent's commands (Show in folder and Delete are the
user's only). Made-up data only."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks
from swissarmybench.domain import project_explorer as rules
from tests.conftest import AGENT, AUTH, make_client


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def _project(
    folder: Path, kind: str | None = None, notebooks_: tuple[str, ...] = (), tables: int = 0
) -> Path:
    """A made-up project folder: data.ipynb, notebooks, and .sab/project.json with its type and tables."""
    folder.mkdir(parents=True)
    (folder / "data.ipynb").write_text(notebooks.write_notebook([]), encoding="utf-8")
    for name in notebooks_:
        (folder / name).write_text(notebooks.write_notebook([]), encoding="utf-8")
    manifest: dict[str, Any] = {"swissarmybench": "project", "format": 1, "tables": [
        {"name": f"t{i}", "source": {"kind": "pasted"}} for i in range(tables)
    ]}  # fmt: skip
    if kind:
        manifest["type"] = kind
    (folder / ".sab").mkdir()
    (folder / ".sab" / "project.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


def _projects_folder(tmp_path: Path) -> Path:
    return tmp_path / "home" / "Swiss Army Bench Projects"


# ===== the rules =====


def test_the_branch_comes_from_head_and_git_never_runs() -> None:
    assert rules.branch_of("ref: refs/heads/main\n") == "main"
    assert rules.branch_of("ref: refs/heads/feature/q3-close") == "feature/q3-close"
    assert rules.branch_of("3f2a9c1d0e8b7a6f5e4d3c2b1a0f9e8d7c6b5a49") == "3f2a9c1"  # detached
    assert rules.branch_of(None) is None and rules.branch_of("garbage") is None


def test_every_sort_and_the_custom_order() -> None:
    cards: list[dict[str, Any]] = [
        {
            "path": "/p/b",
            "name": "Beta",
            "type_name": "Analysis",
            "opened": 3.0,
            "changed": 1.0,
            "created": 2.0,
        },
        {
            "path": "/p/a",
            "name": "alpha",
            "type_name": "Streamlit app",
            "opened": None,
            "changed": 3.0,
            "created": 1.0,
        },
        {
            "path": "/p/c",
            "name": "Gamma",
            "type_name": "Analysis",
            "opened": 1.0,
            "changed": 2.0,
            "created": 3.0,
        },
        {"path": "/p/gone", "name": "Gone", "missing": True, "opened": 9.0},
    ]

    def names(sort: dict[str, Any], order: list[str] = []) -> list[str]:  # noqa: B006
        return [c["name"] for c in rules.sorted_cards(cards, sort, order)]

    assert names({"by": "name"}) == ["alpha", "Beta", "Gamma", "Gone"]
    assert names({"by": "name", "descending": True}) == ["Gamma", "Beta", "alpha", "Gone"]  # missing: last
    assert names({"by": "opened", "descending": True}) == ["Beta", "Gamma", "alpha", "Gone"]
    assert names({"by": "changed"}) == ["Beta", "Gamma", "alpha", "Gone"]
    assert names({"by": "created", "descending": True}) == ["Gamma", "Beta", "alpha", "Gone"]
    assert names({"by": "type"}) == ["Beta", "Gamma", "alpha", "Gone"]
    assert names({"by": "custom"}, ["/p/c", "/p/a"]) == ["Gamma", "alpha", "Beta", "Gone"]
    moved = rules.moved(["/p/c", "/p/a", "/p/b"], ["/p/c", "/p/a", "/p/b"], "/p/b", -1)
    assert moved == ["/p/c", "/p/b", "/p/a"]
    assert rules.moved(["/p/c"], ["/p/c", "/p/a"], "/p/c", -1) == ["/p/c", "/p/a"]  # the edge: stays
    with pytest.raises(rules.ExplorerError):
        rules.check_sort({"by": "colour"})
    assert rules.read_settings({"sort": {"by": "nonsense"}})["sort"] == rules.DEFAULT_SORT


def test_filters_by_type_and_words_in_name_folder_or_notebook() -> None:
    cards = [
        {"path": "/w/sales", "name": "sales", "type": "bi", "documents": ["data.ipynb", "regions.ipynb"]},
        {"path": "/w/books", "name": "books", "type": "accounting", "documents": ["data.ipynb"]},
    ]
    assert [c["name"] for c in rules.filtered(cards, "accounting")] == ["books"]
    assert [c["name"] for c in rules.filtered(cards, None, "REGIONS")] == ["sales"]
    assert [c["name"] for c in rules.filtered(cards, None, "w data")] == ["sales", "books"]


def test_the_types_are_explained_for_beginners_and_an_extension_brings_its_own() -> None:
    from swissarmybench import extensions

    base = rules.kinds(extensions.modes(), extensions.STREAMLIT_KIND)
    assert [k["type"] for k in base] == ["bi", "streamlit"]
    assert all(k["title"] and k["for_whom"] and k["explain"] and k["example"] for k in base)
    # The Streamlit extension's own project type when it is on; else a base project with its app's canvas.
    own_streamlit = any(m["type"] == "streamlit" for m in extensions.modes())
    assert base[1]["make"] == ({"type": "streamlit"} if own_streamlit else {"type": "bi", "app": True})
    with_accounting = rules.kinds(
        [*extensions.modes(), {"type": "accounting", "name": "Accounting", "title": "Accounting workbook",
                               "explain": "Made up."}], extensions.STREAMLIT_KIND,
    )  # fmt: skip
    assert [k["type"] for k in with_accounting] == ["bi", "streamlit", "accounting"]
    assert with_accounting[2]["make"] == {"type": "accounting"}
    # The Streamlit extension's own mode, once it has one, says it instead of the base's words.
    others = [m for m in extensions.modes() if m["type"] != "streamlit"]  # the real one left out here
    own = rules.kinds([*others, {"type": "streamlit", "title": "Its own"}], extensions.STREAMLIT_KIND)
    assert [k["title"] for k in own if k["type"] == "streamlit"] == ["Its own"]


# ===== on the running server =====


def test_cards_from_the_projects_folder_and_the_ones_opened_elsewhere(tmp_path: Path) -> None:
    folder = _projects_folder(tmp_path)
    sales = _project(folder / "Sales", notebooks_=("regions.ipynb",), tables=2)
    (sales / "pages").mkdir()
    (sales / "sales.stapp.json").write_text('{"pages": []}', encoding="utf-8")
    (sales / ".git").mkdir()
    (sales / ".git" / "HEAD").write_text("ref: refs/heads/q3-close\n", encoding="utf-8")
    _project(folder / "Books", kind="accounting")
    (folder / "not a project").mkdir()
    (folder / "not a project" / "notes.md").write_text("x", encoding="utf-8")
    elsewhere = _project(tmp_path / "elsewhere" / "Survey")
    with make_client(tmp_path) as client:
        ok(client.post("/project/open", json={"path": str(elsewhere)}, headers=AUTH))
        listed = ok(client.get("/projects/explorer?by=name", headers=AUTH))
        cards = {c["name"]: c for c in listed["projects"]}
        assert set(cards) == {"Sales", "Books", "Survey"} and listed["folder"] == str(folder)
        assert cards["Sales"]["type"] == "streamlit" and cards["Sales"]["type_name"] == "Streamlit app"
        assert cards["Sales"]["counts"] == {"notebooks": 2, "scripts": 0, "apps": 1, "tables": 2}
        assert cards["Sales"]["git"] == {"repository": True, "branch": "q3-close"}
        assert cards["Survey"]["open"] is True and cards["Survey"]["in_folder"] is False
        assert cards["Survey"]["opened"] is not None and cards["Sales"]["opened"] is None
        # Accounting is not on here: its project says what it needs.
        assert cards["Books"]["needs"] == {"extension": "accounting", "name": "Accounting"}
        assert [t["type"] for t in listed["types"]] == ["bi", "streamlit"]
        assert [
            c["name"] for c in ok(client.get("/projects/explorer?q=regions", headers=AUTH))["projects"]
        ] == ["Sales"]
        assert [
            c["name"] for c in ok(client.get("/projects/explorer?type=bi", headers=AUTH))["projects"]
        ] == ["Survey"]
        # A project opened from elsewhere, then moved away: missing, last, with Locate and Remove.
        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
        moved = elsewhere.with_name("Survey moved")
        elsewhere.rename(moved)
        cards = ok(client.get("/projects/explorer", headers=AUTH))["projects"]
        assert cards[-1]["name"] == "Survey" and cards[-1]["missing"] is True
        ok(client.post("/projects/locate", json={"path": str(elsewhere), "to": str(moved)}, headers=AUTH))
        names = [c["name"] for c in ok(client.get("/projects/explorer", headers=AUTH))["projects"]]
        assert "Survey moved" in names and "Survey" not in names


def test_the_sort_is_remembered_and_the_custom_order_kept_after_a_restart(tmp_path: Path) -> None:
    folder = _projects_folder(tmp_path)
    for name in ("Alpha", "Beta", "Gamma"):
        _project(folder / name)
    with make_client(tmp_path) as client:
        ok(client.post("/projects/sort", json={"by": "name", "descending": True}, headers=AUTH))
        assert [c["name"] for c in ok(client.get("/projects/explorer", headers=AUTH))["projects"]] == [
            "Gamma", "Beta", "Alpha",
        ]  # fmt: skip
        order = [str(folder / n) for n in ("Beta", "Alpha", "Gamma")]
        ok(client.post("/projects/sort", json={"order": order}, headers=AUTH))
        ok(client.post("/projects/sort", json={"move": str(folder / "Gamma"), "by": -1}, headers=AGENT))
        assert client.post("/projects/sort", json={"by": "colour"}, headers=AUTH).status_code == 400
    with make_client(tmp_path) as client:  # the server started again: projects.json kept it
        listed = ok(client.get("/projects/explorer", headers=AUTH))
        assert listed["sort"]["by"] == "custom"
        assert [c["name"] for c in listed["projects"]] == ["Beta", "Gamma", "Alpha"]
        ok(client.post("/projects/explained", json={"explained": True}, headers=AUTH))
        assert ok(client.get("/projects/explorer", headers=AUTH))["explained"] is True
    saved = json.loads((tmp_path / "state" / "projects.json").read_text(encoding="utf-8"))
    assert list(saved) == sorted(saved) and saved["explained"] is True


def test_rename_and_remove_from_the_list_touch_no_other_file(tmp_path: Path) -> None:
    folder = _projects_folder(tmp_path)
    alpha = _project(folder / "Alpha", notebooks_=("work.ipynb",))
    with make_client(tmp_path) as client:
        ok(client.post("/project/open", json={"path": str(alpha)}, headers=AUTH))
        refused = client.post("/projects/rename", json={"path": str(alpha), "name": "Omega"}, headers=AUTH)
        assert refused.status_code == 409  # the open one: close it first
        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
        done = ok(client.post("/projects/rename", json={"path": str(alpha), "name": "Omega"}, headers=AGENT))
        omega = Path(done["path"])
        assert omega == folder / "Omega" and (omega / "work.ipynb").is_file() and not alpha.exists()
        recent = [r["path"] for r in ok(client.get("/project", headers=AUTH))["recent"]]
        assert recent == [str(omega)]
        ok(client.post("/projects/remove", json={"path": str(omega)}, headers=AGENT))
        assert ok(client.get("/projects/explorer", headers=AUTH))["projects"] == []
        assert (omega / "work.ipynb").is_file()  # off the list, never deleted


def test_show_in_folder_and_delete_are_the_users_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from swissarmybench.server import file_manager

    shown: list[str] = []
    monkeypatch.setattr(file_manager, "show", shown.append)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    folder = _projects_folder(tmp_path)
    doomed = _project(folder / "Doomed")
    with make_client(tmp_path) as client:
        assert client.post("/projects/show", json={"path": str(doomed)}, headers=AGENT).status_code == 403
        ok(client.post("/projects/show", json={"path": str(doomed)}, headers=AUTH))
        assert shown == [str(doomed)]
        assert (
            client.post(
                "/projects/delete", json={"path": str(doomed), "confirm": "Doomed"}, headers=AGENT
            ).status_code
            == 403
        )
        wrong = client.post("/projects/delete", json={"path": str(doomed), "confirm": "doomed"}, headers=AUTH)
        assert wrong.status_code == 400 and doomed.is_dir()
        done = ok(
            client.post("/projects/delete", json={"path": str(doomed), "confirm": "Doomed"}, headers=AUTH)
        )
        assert done["to"] == "the Trash" and not doomed.exists()
        assert (tmp_path / "xdg" / "Trash" / "files" / "Doomed" / "data.ipynb").is_file()
        assert (tmp_path / "xdg" / "Trash" / "info" / "Doomed.trashinfo").is_file()


def test_the_projects_folder_is_where_new_goes_and_the_agents_change_waits_for_allow(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        mine = tmp_path / "my projects"
        answer: dict[str, Any] = {}

        def change() -> None:
            answer["response"] = client.post("/projects/folder", json={"folder": str(mine)}, headers=AGENT)

        waiting = threading.Thread(target=change)
        waiting.start()
        for _ in range(100):
            pending = ok(client.get("/agent/approvals", headers=AUTH))["pending"]
            if pending:
                break
            time.sleep(0.05)
        assert pending and str(mine) in pending[0]["detail"]
        ok(client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": True}, headers=AUTH))
        waiting.join(10)
        assert answer["response"].status_code == 200
        made = ok(client.post("/project/new", json={"name": "Fresh", "type": "bi"}, headers=AGENT))
        assert made["project"]["folder"] == str(mine / "Fresh")
        assert ok(client.get("/projects/types", headers=AUTH))["folder"] == str(mine)
        ok(client.post("/projects/folder", json={"default": True}, headers=AUTH))
        assert ok(client.get("/projects/types", headers=AUTH))["folder"] == str(_projects_folder(tmp_path))


def test_an_extensions_types_are_explained_when_it_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SWISSARMYBENCH_EXTENSIONS", "accounting")
    with make_client(tmp_path) as client:
        types = {t["type"]: t for t in ok(client.get("/projects/types", headers=AUTH))["types"]}
        assert list(types) == ["bi", "streamlit", "accounting"]
        assert types["accounting"]["title"] == "Accounting workbook" and types["accounting"]["explain"]
        made = ok(client.post("/project/new", json={"name": "Books", "type": "accounting"}, headers=AUTH))
        assert made["project"]["type"] == "accounting"
        card = ok(client.get("/projects/explorer", headers=AUTH))["projects"][0]
        assert card["type"] == "accounting" and "needs" not in card


def test_the_agents_commands(tmp_path: Path, client: TestClient) -> None:
    from swissarmybench.cli import commands

    names = set(commands.REGISTRY)
    assert {
        "projects_list",
        "projects_sort",
        "project_new",
        "project_open",
        "project_rename",
        "project_remove_from_list",
        "project_copy",
        "projects_folders",
        "project_share",
        "project_copy_local",
        "project_types",
    } <= names
    assert "project_import_sab" not in names  # the .sab conversion removed (2026-11-17)
    assert not {n for n in names if "delete" in n and n.startswith("project")}  # Delete is the user's
