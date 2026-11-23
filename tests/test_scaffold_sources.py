"""What the project scaffold reads its made files from (services/scaffold.py Scaffold over its Sources), with
stand-ins for the app's services: the rules that were the composition root's closures (which documents use a
variable, data.py's structures, API.py's endpoints, the project type's contract). Made-up names only."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from swissarmybench.domain import scaffold as rules
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.scaffold import Scaffold, Sources


class Files:
    def __init__(self, files: dict[str, str] | None = None, names: list[str] | None = None) -> None:
        self.files = dict(files or {})
        self._names = names or []

    def read(self, folder: str, relative: str) -> str | None:
        return self.files.get(relative)

    def write(self, folder: str, relative: str, text: str) -> None:
        self.files[relative] = text

    def remove(self, folder: str, relative: str) -> None:
        self.files.pop(relative, None)

    def names(self, folder: str) -> list[str]:
        return self._names


FOLDER = "/work/projects/shop"


def scaffold(files: Files | None = None, **given: Any) -> Scaffold:
    sources = Sources(used=lambda: [], connections=lambda names: {}, adapter=lambda: "# adapter", **given)
    ws: Any = SimpleNamespace()
    return Scaffold(ws, lambda: (FOLDER, "Shop"), files or Files(), sources)


def test_a_variable_is_used_by_the_project_s_own_documents_never_a_made_file() -> None:
    uses = {
        "SHOP_KEY": (
            "This computer",
            [
                ("notebook data.ipynb", f"{FOLDER}/data.ipynb"),
                ("script connections.py", f"{FOLDER}/connections.py"),  # made by the scaffold
                ("script elsewhere.py", "/work/other/elsewhere.py"),  # not the project's
                ("connection Warehouse", None),  # a connection's field: said by its section
            ],
        )
    }
    made = scaffold(variable_uses=lambda: uses)
    assert made.documents_using("SHOP_KEY", FOLDER) == ["notebook data.ipynb"]
    assert made.documents_using("NOT_SET", FOLDER) == []
    assert made.variable_words() == {"SHOP_KEY": "This computer"}


def test_data_py_s_structures_are_the_open_grids_read_from_the_project_s_structure_files() -> None:
    tables = [
        ("orders", Origin("structure", path=f"{FOLDER}/structures/orders.json", sql="$.orders")),
        ("orders", Origin("structure", path=f"{FOLDER}/structures/orders.json", sql="$.orders")),  # two grids
        ("people", Origin("structure", path=f"{FOLDER}/people.yaml")),
        ("notes", Origin("structure", path=f"{FOLDER}/notes.txt")),  # not a structure's file
        ("far", Origin("structure", path="/work/other/far.json")),  # outside the project
        ("sales", Origin("file", path=f"{FOLDER}/sales.csv")),
        ("loose", None),
    ]
    made = scaffold(tables=lambda: tables)
    assert made.structures(FOLDER) == [
        rules.StructureGrid("orders", "structures/orders.json", "$.orders"),
        rules.StructureGrid("people", "people.yaml", "$"),
    ]


def test_a_link_into_the_project_counts_as_inside(tmp_path: Path) -> None:
    project = tmp_path / "shop"
    (project / "structures").mkdir(parents=True)
    (project / "structures" / "orders.json").write_text("{}", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(project)
    import os

    made = scaffold(
        tables=lambda: [("orders", Origin("structure", path=str(link / "structures" / "orders.json")))],
        real=os.path.realpath,
    )
    assert made.structures(str(project)) == [rules.StructureGrid("orders", "structures/orders.json", "$")]
    assert (
        scaffold(tables=lambda: [("orders", Origin("structure", path=str(link / "x.json")))]).structures(
            str(project)
        )
        == []
    )


def test_api_py_s_endpoints_are_counted_and_a_broken_file_has_none() -> None:
    text = (
        "from sab_api import endpoint\n\n\n"
        '@endpoint("GET", "/orders")\ndef orders() -> list[dict]:\n    return []\n'
    )
    assert Scaffold.endpoints(text) == 1
    assert Scaffold.endpoints("def (:\n") == 0
    assert Scaffold.endpoints("") == 0


def test_the_deliverable_is_the_contract_of_the_project_s_own_type() -> None:
    shelves = {
        "type": "shelves",
        "deliverable": "a shelf list",
        "files": [
            {"path": "shelves.csv", "owner": "user", "about": "the list", "made_from": "", "grows_on": []},
            {"path": "labels/", "owner": "app", "about": "tags", "made_from": "the list", "grows_on": ["x"]},
        ],
    }
    other = {**shelves, "type": "other"}
    made = scaffold(
        Files(names=["shelves.csv", "data.ipynb"]),
        type_of=lambda folder: "shelves",
        contracts=lambda: [other, shelves],
    )
    found = made.deliverable(FOLDER)
    assert found["type"] == "shelves" and found["deliverable"] == "a shelf list"
    assert [(f["path"], f["present"]) for f in found["files"]] == [("shelves.csv", True), ("labels/", False)]
    assert scaffold(type_of=lambda folder: "bi", contracts=lambda: [shelves]).deliverable(FOLDER) == {
        "type": None,
        "files": [],
    }


def test_readme_s_variables_list_the_documents_that_use_them() -> None:
    files = Files({rules.README: "# Shop\n"})
    uses = {"SHOP_KEY": ("This computer", [("notebook data.ipynb", f"{FOLDER}/data.ipynb")])}
    made = scaffold(files, variable_uses=lambda: uses)
    wanted, facts = asyncio.run(made.wanted(FOLDER, "Shop"))
    assert facts["variables"] == ["SHOP_KEY"]
    readme = wanted[rules.README] or ""
    assert "SHOP_KEY" in readme and "notebook data.ipynb" in readme
