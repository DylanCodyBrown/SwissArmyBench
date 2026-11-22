"""What the project uses, one answer (services/project_scope.py ProjectUse) and shared projects
(services/library_setup.py SharedProjects), on fakes: no file, no server (craft review 2026-11-22, item 8)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain.blades import Blade
from swissarmybench.services.library_setup import SharedProjects
from swissarmybench.services.project_scope import ProjectUse, UseSources

FOLDER = "/work/shop"


@dataclass
class Ref:
    kind: str
    document: str
    title: str = ""


def _blade(name: str, kind: str = "sql", template: str = "postgres", **more: Any) -> Blade:
    return Blade(name=name, kind=kind, template=template, code="", **more)


def _use(project: dict[str, Any] | None = None, **given: Any) -> ProjectUse:
    refs: dict[str, list[Ref]] = given.pop("refs", {})
    files = given.pop("files", {})
    sources = {
        "project": lambda: project,
        "documents": lambda: list(files),
        "read": lambda path: (files[path], path, None),
        "open_tables": lambda: {"orders"},
        "connections": lambda: [_blade("Warehouse"), _blade("Lake"), _blade("Api db")],
        "references": lambda name: (refs.get(name, []), []),
        "api_text": lambda folder: None,
        "inside": lambda path, folder: path.startswith(folder + "/"),
    } | given
    return ProjectUse(UseSources(**sources))


def test_no_project_open_uses_nothing() -> None:
    refs = {"Warehouse": [Ref("grid", "", "orders"), Ref("notebook", f"{FOLDER}/data.ipynb")]}
    use = _use(None, refs=refs)
    assert use.documents() is None
    assert use.catalog_use() is None
    # No project folder: an open grid still uses it, a document never does.
    assert use.places("Warehouse") == [("grid", "orders")]
    assert use.connections() == ["Warehouse"]


def test_the_project_s_tables_and_documents() -> None:
    files = {f"{FOLDER}/data.ipynb": "x = 1", f"{FOLDER}/load.py": "y = 2"}
    project = {"folder": FOLDER, "name": "Shop", "tables": [{"name": "customers"}]}
    use = _use(project, files=files)
    assert use.documents() == (
        {"customers"},
        [(f"{FOLDER}/data.ipynb", "x = 1"), (f"{FOLDER}/load.py", "y = 2")],
    )
    name, tables, texts = use.catalog_use() or ("", set(), [])
    assert name == "shop"  # the folder's name, not the saved one
    assert tables == {"customers", "orders"}
    assert len(texts) == 2


def test_a_document_that_cannot_be_read_is_skipped() -> None:
    def read(path: str) -> tuple[str, str, Any]:
        raise OSError("gone")

    use = _use({"folder": FOLDER, "tables": []}, files={f"{FOLDER}/a.py": ""}, read=read)
    assert use.documents() == (set(), [])


def test_places_are_the_project_s_documents_and_the_open_grids() -> None:
    refs = {
        "Warehouse": [
            Ref("grid", "", "orders"),
            Ref("notebook", f"{FOLDER}/data.ipynb"),
            Ref("script", "/elsewhere/other.py"),
        ]
    }
    use = _use({"folder": FOLDER, "tables": []}, refs=refs)
    assert use.places("Warehouse") == [("grid", "orders"), ("notebook", f"{FOLDER}/data.ipynb")]


def test_the_connections_used_in_the_library_s_order() -> None:
    refs = {
        "Lake": [Ref("script", f"{FOLDER}/load.py")],
        "Warehouse": [Ref("grid", "", "orders")],
        "Api db": [Ref("script", "/elsewhere/x.py")],
    }
    api = (
        "# /// swissarmybench-api\n# name = 'Shop'\n# ///\n"
        "from sab_api import endpoint, connection\n\n"
        "@endpoint('GET', '/orders')\n"
        "def orders():\n    return connection('Api db').read('orders')\n"
    )
    use = _use({"folder": FOLDER, "tables": []}, refs=refs, api_text=lambda folder: api)
    assert use.connections() == ["Warehouse", "Lake", "Api db"]
    without = _use({"folder": FOLDER, "tables": []}, refs=refs)
    assert without.connections() == ["Warehouse", "Lake"]


def test_an_api_py_that_does_not_parse_names_nothing() -> None:
    use = _use({"folder": FOLDER, "tables": []}, api_text=lambda folder: "def (")
    assert use.api_connections() == []


def test_the_connections_a_folder_names() -> None:
    texts = [(f"{FOLDER}/load.py", "load.py", "import swissarmybench as sab\nsab.sql('Lake', 'SELECT 1')\n")]
    use = _use(None, code_texts=lambda folder: texts, known=lambda: ["Warehouse", "Lake", "Lake"])
    assert use.named_in(FOLDER) == ["Lake"]


def test_shared_projects_listing_and_the_once_only_notice() -> None:
    said: list[str] = []

    async def notice(words: str) -> None:
        said.append(words)

    local = Blade(
        name="Lake",
        kind="sql",
        template="sqlserver",
        code='conn = pyodbc.connect("DRIVER={ODBC Driver 18 for SQL Server};Trusted_Connection=yes")',
    )
    shared = SharedProjects(
        shared_folder=lambda: "/team/projects",
        where=lambda folder: "shared" if folder.startswith("/team/") else "local",
        scan=lambda folder: ["/team/projects/shop"],
        named_in=lambda folder: ["Lake", "Missing"],
        here=lambda: ["Lake"],
        blade=lambda name: {"Lake": local}[name],
        secret_status=lambda blade: {},
        notice=notice,
    )
    listed = asyncio.run(shared.listing(set()))
    assert [(p.name, p.connections) for p in listed] == [("shop", ("Missing",))]
    asyncio.run(shared.opened("/work/mine"))
    assert said == []
    asyncio.run(shared.opened("/team/projects/shop"))
    assert len(said) == 1 and "only works on your machine" in said[0]
