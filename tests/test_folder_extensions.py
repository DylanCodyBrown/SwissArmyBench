"""Folder extensions (Plans/folder-extensions.plan.md) and the project contract (domain/project_contract.py).

The made-up Stockroom extension (tests/folder_extension_example/stockroom/: a project type with one
deliverable file, one route and one agent command) is copied into a test's library and proved end to end:
found, its project type in New project, its command among the agent's tools, its route answering, removed to
the trash.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench import extensions as loader
from swissarmybench.domain import extension_folders as folder_rules
from swissarmybench.domain import project_contract as contract_rules
from swissarmybench.domain.project_contract import ContractError
from tests.conftest import AGENT, AUTH, make_client

EXAMPLE = Path(__file__).parent / "folder_extension_example" / "stockroom"
EXTENSIONS = Path(__file__).resolve().parents[1] / "extensions"
PACKAGED = {
    "streamlit": "swissarmybench_streamlit",
    "accounting": "swissarmybench_accounting",
    "powerapps": "swissarmybench_powerapps",
    "powerbi": "swissarmybench_powerbi",
}


def good() -> dict[str, Any]:
    return {
        "format": 1,
        "type": "stockroom",
        "name": "Stockroom",
        "deliverable": "a stock report",
        "files": [{"path": "stock_report.md", "starter": "# {name}\n"}],
    }


# ===== the contract: one shape, one checker =====


def test_a_contract_is_read_into_its_one_shape() -> None:
    said = contract_rules.check(
        good() | {"languages": {"*.md": "markdown", "*.py": "python"}, "cells": ["SQL"]}
    )
    assert said["format"] == 1 and said["type"] == "stockroom" and said["core"] == "base"
    assert said["files"] == [
        {
            "path": "stock_report.md",
            "owner": "user",
            "about": "",
            "starter": "# {name}\n",
            "made_from": None,
            "grows_on": [],
            "section": "",
        }
    ]
    assert said["cells"] == ["sql"] and said["canvas"] is None and said["requirements"] == []
    assert contract_rules.languages(said) == ["markdown", "python"]
    assert contract_rules.languages(contract_rules.check(good())) == ["python"]  # none named: Python
    # Its text is byte-stable: written, read, written again.
    text = contract_rules.write(said)
    assert contract_rules.write(contract_rules.read(text)) == text and text.endswith("}\n")


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ({"format": 2}, "format 2, made for a newer Swiss Army Bench"),
        ({"format": "1"}, "format is a number"),
        ({"colour": "red"}, "a key it does not know: colour"),
        ({"type": "Stock Room"}, "type 'Stock Room' is not a name"),
        ({"name": ""}, "name is required"),
        ({"files": [{"path": "../outside.md"}]}, "is not a path inside the project"),
        ({"files": [{"path": "/etc/passwd"}]}, "is not a path inside the project"),
        ({"files": [{"path": "C:/x.md"}]}, "is not a path inside the project"),
        ({"files": [{"path": "data.py"}]}, "is a core file of every project"),
        ({"files": [{"path": "a.md"}, {"path": "a.md"}]}, "a path is in files twice"),
        ({"files": [{"path": "a.md", "owner": "them"}]}, "owner is user or app"),
        ({"files": [{"path": "out/", "starter": "x"}]}, "is a folder: it has no starter"),
        ({"files": [{"path": "a.md", "size": 1}]}, "files[0] has a key it does not know: size"),
        ({"languages": ["python"]}, "languages is"),
        ({"core": "mine"}, "core is base"),
    ],
)
def test_the_checker_names_what_is_wrong_in_one_sentence(change: dict[str, Any], words: str) -> None:
    with pytest.raises(ContractError) as said:
        contract_rules.check(good() | change)
    assert words in str(said.value)


def test_broken_json_is_said_with_its_line() -> None:
    with pytest.raises(ContractError, match="not JSON \\(line 2\\)"):
        contract_rules.read('{"format": 1,\n oops}')


def test_new_project_files_and_the_mode_come_from_the_contract() -> None:
    said = contract_rules.check(
        good()
        | {
            "files": [
                {"path": "stock_report.md", "starter": "# {name}\n"},
                {"path": "{slug}.notes.md", "starter": "notes"},
                {"path": "exports/", "about": "What Export writes."},
                {"path": "made.json", "owner": "app"},  # no starter: made later, never by New project
            ],
            "requirements": ["openpyxl>=3.1"],
            "cells": ["python", "sql", "tsx"],
            "canvas": "shelves",
            "words": {"title": "Stock report", "for_whom": "For counters."},
        }
    )
    made = contract_rules.scaffold(said, "Spring Count")
    assert made == {
        "app": False,
        "files": {
            "stock_report.md": "# Spring Count\n",
            "spring_count.notes.md": "notes",
            "exports/README.md": "What Export writes.\n",
        },
        "requirements": ["openpyxl>=3.1"],
    }
    mode = contract_rules.as_mode(said)
    assert mode["type"] == "stockroom" and mode["canvases"] == ["shelves"] and mode["cell_kinds"] == ["tsx"]
    assert mode["title"] == "Stock report" and mode["for_whom"] == "For counters." and mode["example"] == ""
    assert contract_rules.matches("spring_count.notes.md", "{slug}.notes.md")
    assert contract_rules.matches("exports/a.csv", "exports/")
    assert not contract_rules.matches("other.md", "stock_report.md")


# ===== the packaged extensions carry theirs, read by the same checker =====


@pytest.mark.parametrize("ident", sorted(PACKAGED))
def test_each_packaged_extension_has_a_contract_describing_what_it_has(ident: str, monkeypatch: Any) -> None:
    package = PACKAGED[ident]
    file = EXTENSIONS / ident / "src" / package / contract_rules.FILE
    said = contract_rules.read(file.read_text(encoding="utf-8"))
    assert contract_rules.write(said) == file.read_text(encoding="utf-8")  # written as the checker writes it
    import importlib

    module = importlib.import_module(f"{package}.extension")
    mode = module.MODE
    assert said["type"] == mode["type"] and said["name"] == mode["name"]
    assert said["deliverable"] == mode["deliverable"] and said["export"] == mode["export"]
    assert set(contract_rules.languages(said)) >= set(mode["languages"])
    assert [c for c in said["cells"] if c not in contract_rules.BASE_CELLS] == mode["cell_kinds"]
    assert (said["canvas"] or None) == (mode["canvases"][0] if mode["canvases"] else None)
    assert loader.contract(module) == said  # the loader reads the package root's
    # Every file its New project writes is one the contract lists.
    scaffold = getattr(module, "scaffold", None)
    if scaffold is not None:
        written = scaffold("Spring Count", [])["files"]
        listed = contract_rules.deliverable_files(said)
        assert all(any(contract_rules.matches(path, entry) for entry in listed) for path in written), written


def test_an_extension_with_no_project_type_has_no_contract() -> None:
    for ident in ("copilot", "git"):
        assert not list((EXTENSIONS / ident / "src").glob(f"*/{contract_rules.FILE}"))


# ===== a folder extension's rules =====


def test_a_folder_extensions_requires_are_read_without_running_it() -> None:
    assert folder_rules.requires_of('REQUIRES = ["openpyxl>=3.1", "psycopg[binary]"]\nraise SystemExit') == [
        "openpyxl>=3.1",
        "psycopg[binary]",
    ]
    assert folder_rules.requires_of('REQUIRES: list[str] = ["a"]') == ["a"]
    assert folder_rules.requires_of("REQUIRES = make()") == [] == folder_rules.requires_of("def (")
    assert folder_rules.dist_name("psycopg[binary]>=3") == "psycopg"
    assert folder_rules.dist_name("openpyxl>=3.1") == "openpyxl"


def test_a_new_extensions_id_is_a_python_name_never_a_word_of_the_bases() -> None:
    assert folder_rules.check_id(" Stockroom ", set()) == "stockroom"
    for bad, words in (
        ("1st", "is not a folder extension's id"),
        ("stock-room", "is not a folder extension's id"),
        ("grids", "a word of Swiss Army Bench's own"),
        ("stockroom", "There is an extension stockroom already"),
        (None, "Send"),
    ):
        with pytest.raises(folder_rules.FolderError, match=words):
            folder_rules.check_id(bad, {"stockroom"})


def test_new_extensions_skeleton_is_working_python_and_a_valid_contract() -> None:
    files = folder_rules.scaffold("shelves", "Shelf counts", "shelves")
    assert sorted(files) == ["README.md", "commands.py", "contract.json", "extension.py"]
    for name in ("extension.py", "commands.py"):
        compile(files[name], name, "exec")
    assert 'ID = "shelves"' in files["extension.py"] and 'Route("/shelves/status"' in files["extension.py"]
    assert '@command("shelves_status"' in files["commands.py"]
    said = contract_rules.read(files["contract.json"])
    assert said["type"] == "shelves" and contract_rules.deliverable_files(said) == ["shelves.md"]
    assert "contract.json" not in folder_rules.scaffold("shelves", "Shelves")  # no project type: none


# ===== the loader: found, loaded, listed with why not =====


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """An empty folder of folder extensions, the loader pointed at it; everything put back after."""
    from swissarmybench.cli import commands

    root = tmp_path / "library" / folder_rules.FOLDER
    root.mkdir(parents=True)
    monkeypatch.setenv(loader.FOLDERS_VARIABLE, str(root))
    registry, areas = dict(commands.REGISTRY), commands.AREAS
    loader.forget_folders()
    yield root
    loader.forget_folders()
    commands.REGISTRY.clear()
    commands.REGISTRY.update(registry)
    commands.AREAS = areas


def test_a_folder_extension_is_found_loaded_and_its_project_type_listed(library: Path) -> None:
    shutil.copytree(EXAMPLE, library / "stockroom")
    found = loader.folders()["stockroom"]
    assert found.error == "" and found.missing == [] and found.module is not None
    module = found.module
    assert module.__name__ == "sab_ext_stockroom.extension" and module.FOLDER == str(library / "stockroom")
    assert loader.extension_on("stockroom") and loader.load("stockroom") is module
    assert module in loader.enabled()
    # Its MODE and its New project files from its contract.json (extension.py declares neither).
    mode = loader.mode_of("stockroom")
    assert mode["type"] == "stockroom" and mode["title"] == "Stock report" and mode["tools"] == ["stockroom_"]
    assert module.scaffold("Spring Count", [])["files"] == {
        "stock_report.md": "# Spring Count\n\nShelf counts, checked.\n"
    }
    assert loader.contract(module) == module.CONTRACT
    # Its own files import each other inside its package, never as top-level modules.
    assert "sab_ext_stockroom.commands" in __import__("sys").modules or module.commands()
    assert set(module.commands()) == {"stockroom_count"}


def test_a_broken_folder_is_listed_with_its_error_and_line_and_the_rest_load(library: Path) -> None:
    shutil.copytree(EXAMPLE, library / "stockroom")
    (library / "broken").mkdir()
    (library / "broken" / "extension.py").write_text(
        'ID = "broken"\n\nraise RuntimeError("made-up failure")\n'
    )
    (library / "badcontract").mkdir()
    (library / "badcontract" / "extension.py").write_text("")
    (library / "badcontract" / "contract.json").write_text('{"format": 1, "type": "x"}')
    (library / "needs").mkdir()
    (library / "needs" / "extension.py").write_text(
        'REQUIRES = ["made-up-package-nobody-has>=1"]\nimport nope\n'
    )
    (library / "wrong").mkdir()
    (library / "wrong" / "extension.py").write_text('ID = "other"\n')
    (library / "Not An Id").mkdir()
    (library / "Not An Id" / "extension.py").write_text("")
    found = loader.folders()
    assert sorted(found) == ["badcontract", "broken", "needs", "stockroom", "wrong"]
    assert found["broken"].module is None
    assert found["broken"].error == "It did not load: RuntimeError: made-up failure (extension.py, line 3)."
    assert found["badcontract"].error == "It did not load: contract.json: name is required as text."
    assert found["needs"].module is None and found["needs"].missing == ["made-up-package-nobody-has>=1"]
    assert (
        found["wrong"].error == "It did not load: extension.py's ID 'other' is not its folder's name 'wrong'."
    )
    assert found["stockroom"].module is not None
    assert [getattr(m, "ID", "") for m in loader.enabled() if getattr(m, "FOLDER", None)] == ["stockroom"]


def test_a_missing_import_is_offered_as_a_package(library: Path) -> None:
    (library / "plots").mkdir()
    (library / "plots" / "extension.py").write_text("import made_up_module_nobody_has\n")
    assert loader.folders()["plots"].missing == ["made_up_module_nobody_has"]  # pip's name for it


def test_a_folder_with_a_packages_id_loses_to_the_package(library: Path) -> None:
    (library / "streamlit").mkdir()  # the Streamlit extension is on in every test (conftest)
    (library / "streamlit" / "extension.py").write_text('raise SystemExit("never run")\n')
    found = loader.folders()["streamlit"]
    assert found.shadowed and found.module is None and "the installed package streamlit wins" in found.error
    assert loader.load("streamlit").__name__ == "swissarmybench_streamlit.extension"  # type: ignore[union-attr]


def test_its_commands_join_the_agents_tools_and_one_in_no_area_is_left_out(library: Path) -> None:
    from swissarmybench.cli import commands

    shutil.copytree(EXAMPLE, library / "stockroom")
    (library / "stray").mkdir()
    (library / "stray" / "extension.py").write_text(
        "from swissarmybench.cli.commands import Command, Registrar\n"
        "AREAS = ()\n"
        "MINE: dict[str, Command] = {}\n"
        "command = Registrar(MINE)\n"
        "@command('elsewhere_go', 'A made-up command in no area')\n"
        "def go(a): return {}\n"
        "def commands(): return MINE\n"
    )
    commands._add_extensions()
    assert "stockroom_count" in commands.REGISTRY and commands.area_of("stockroom_count") == "stockroom"
    assert "elsewhere_go" not in commands.REGISTRY  # its prefix names no area: the registry stays whole


# ===== end to end: a server with the extension in its library =====


@pytest.fixture
def server_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """The server's own library (tmp/state/library), as an installed app has it: no folder override."""
    monkeypatch.delenv(loader.FOLDERS_VARIABLE)
    root = tmp_path / "state" / "library" / folder_rules.FOLDER
    root.mkdir(parents=True)
    yield root
    loader.use_library(None)


def test_end_to_end_found_its_type_in_new_project_its_route_and_its_removal(
    server_library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copytree(EXAMPLE, server_library / "stockroom")
    trashed: list[str] = []

    def trash(folder: str, home: Path | None = None) -> str:
        trashed.append(folder)
        return "the trash"

    monkeypatch.setattr("swissarmybench.server.file_manager.trash", trash)
    with make_client(tmp_path) as client:
        listed = {e["id"]: e for e in client.get("/extensions", headers=AUTH).json()["extensions"]}
        card = listed["stockroom"]
        assert card["status"] == "installed" and card["source"] == "folder" and card["on"] is True
        assert card["path"] == str(server_library / "stockroom") and card["error"] is None
        assert card["project_type"] == "stockroom" and card["deliverable"] == ["stock_report.md"]
        assert card["name"] == "Stockroom" and card["version"] == "0.1.0"
        # Its route is mounted.
        assert client.get("/stockroom/count", headers=AUTH).json() == {
            "shelves": {"A1": 12, "A2": 0, "B1": 7},
            "total": 19,
        }
        # Its project type is one New project makes, with its deliverable written.
        types = client.get("/projects/types", headers=AUTH).json()
        assert "stockroom" in json.dumps(types)
        made = client.post(
            "/project/new",
            json={"name": "Spring Count", "type": "stockroom", "folder": str(tmp_path / "work")},
            headers=AUTH,
        )
        assert made.status_code == 200, made.text
        report = tmp_path / "work" / "Spring Count" / "stock_report.md"
        assert report.read_text(encoding="utf-8") == "# Spring Count\n\nShelf counts, checked.\n"
        # Show its folder is the user's own.
        assert client.post("/extensions/show", json={"id": "stockroom"}, headers=AGENT).status_code == 403
        # Remove: the user's is asked first, then its folder goes to the trash and its route stops.
        asked = client.post("/extensions/remove", json={"id": "stockroom"}, headers=AUTH).json()
        assert asked["confirm"].startswith("Stockroom's folder goes to the trash")
        gone = client.post("/extensions/remove", json={"id": "stockroom", "confirmed": True}, headers=AUTH)
        assert gone.json() == {"removed": "stockroom", "trash": "the trash"}
        assert trashed == [str(server_library / "stockroom")]
        assert client.get("/stockroom/count", headers=AUTH).status_code == 404


def test_new_extension_writes_a_working_folder_and_mounts_it(
    server_library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path) as client:
        made = client.post("/extensions/new", json={"id": "shelves", "project_type": "shelves"}, headers=AUTH)
        assert made.status_code == 200, made.text
        said = made.json()
        assert said["made"] == str(server_library / "shelves")
        assert said["files"] == ["README.md", "commands.py", "contract.json", "extension.py"]
        assert said["extension"]["on"] is True and said["extension"]["project_type"] == "shelves"
        assert client.get("/shelves/status", headers=AUTH).json() == {
            "id": "shelves",
            "name": "Shelves",
            "ok": True,
        }
        taken = client.post("/extensions/new", json={"id": "shelves"}, headers=AUTH)
        assert taken.status_code in (400, 409, 422) and "already" in taken.text
        # The agent's waits for the user's Allow: declined, nothing is written.
        monkeypatch.setattr(client.app.state.ctx.extensions._approvals, "ask", _declined)  # type: ignore[attr-defined]
        refused = client.post("/extensions/new", json={"id": "bins"}, headers=AGENT)
        assert refused.status_code == 403 and not (server_library / "bins").exists()
        assert client.post("/extensions/remove", json={"id": "shelves"}, headers=AGENT).status_code == 403
        # Allowed: the agent's Remove sends it to the trash with no question of its own.
        trashed: list[str] = []
        monkeypatch.setattr(client.app.state.ctx.extensions._approvals, "ask", _allowed)  # type: ignore[attr-defined]
        monkeypatch.setattr(client.app.state.ctx.extensions._folders, "_trasher", trashed.append)  # type: ignore[attr-defined]
        assert (
            client.post("/extensions/remove", json={"id": "shelves"}, headers=AGENT).json()["removed"]
            == "shelves"
        )
        assert trashed == [str(server_library / "shelves")]
        assert client.get("/shelves/status", headers=AUTH).status_code == 404


async def _declined(*_: Any) -> bool:
    return False


async def _allowed(*_: Any) -> bool:
    return True


def test_a_missing_package_is_installed_on_install_then_it_loads(
    server_library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (server_library / "plots").mkdir()
    (server_library / "plots" / "extension.py").write_text(
        'REQUIRES = ["made-up-plots>=1"]\nNAME = "Plots"\n'
        "from starlette.routing import Route\nfrom starlette.responses import JSONResponse\n"
        "async def ok(request): return JSONResponse({'ok': True})\n"
        "def routes(services): return [Route('/plots/ok', ok)]\n"
    )
    installed: list[list[str]] = []
    with make_client(tmp_path) as client:
        card = next(
            e for e in client.get("/extensions", headers=AUTH).json()["extensions"] if e["id"] == "plots"
        )
        assert card["on"] is False and card["missing"] == {
            "feature": "The Plots extension",
            "packages": ["made-up-plots>=1"],
            "python": "app",
            "command": "uv pip install 'made-up-plots>=1'",
        }
        assert client.get("/plots/ok", headers=AUTH).status_code == 404

        async def install(packages: list[str]) -> tuple[bool, dict[str, Any]]:
            installed.append(packages)
            monkeypatch.setattr(loader, "_missing", lambda requires: [])  # now it is there
            return True, {"ok": True}

        client.app.state.ctx.extensions._install_packages = install  # type: ignore[attr-defined]
        loaded = client.post("/extensions/install", json={"id": "plots"}, headers=AUTH)
        assert loaded.status_code == 200, loaded.text
        assert installed == [["made-up-plots>=1"]] and loaded.json()["loaded"]["on"] is True
        assert client.get("/plots/ok", headers=AUTH).json() == {"ok": True}


def test_nothing_in_web_names_a_folder_extension() -> None:
    web = Path(__file__).resolve().parents[1] / "web" / "src"
    text = "\n".join(p.read_text(encoding="utf-8") for p in web.rglob("*.ts"))
    assert "stockroom" not in text.lower() and "sab_ext_" not in text
