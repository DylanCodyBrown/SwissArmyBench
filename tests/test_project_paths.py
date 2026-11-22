"""One rule for "is this path inside that folder?" (domain/project_paths.py), and every place that asked
the question its own way now asking it (the craft review of 2026-11-22). Made-up paths only."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

import swissarmybench
from swissarmybench.adapters.sab_files import SabArchive
from swissarmybench.domain import code_tree, project_paths, project_python, script_ide

PACKAGE = Path(swissarmybench.__file__).parent


@pytest.mark.parametrize(
    ("path", "folder", "relative"),
    [
        ("/work/sales/data.ipynb", "/work/sales", "data.ipynb"),
        ("/work/sales/scripts/etl/load.py", "/work/sales/", "scripts/etl/load.py"),
        ("C:\\Work\\Sales\\data.ipynb", "C:\\Work\\Sales", "data.ipynb"),
        ("C:\\Work\\Sales\\scripts\\load.py", "C:/Work/Sales/", "scripts/load.py"),
        # letters are compared without case; the answer keeps the path's own spelling
        ("c:\\work\\SALES\\Data.ipynb", "C:\\Work\\Sales", "Data.ipynb"),
        ("/Work/Sales/Notes.py", "/work/sales", "Notes.py"),
        ("/work/straße/a.py", "/work/STRASSE", None),  # a folded letter is never sliced into
        ("/work/STRASSE/a.py", "/work/STRASSE", "a.py"),
        # the folder itself, a neighbour that starts with its name, and outside
        ("/work/sales", "/work/sales", None),
        ("/work/sales/", "/work/sales", None),
        ("/work/sales-old/data.ipynb", "/work/sales", None),
        ("/work/other/data.ipynb", "/work/sales", None),
        # a path that climbs out is never inside
        ("/work/sales/../other/data.ipynb", "/work/sales", None),
        ("/work/sales/scripts/..\\..\\x.py", "/work/sales", None),
        ("/work/sales/a..b.py", "/work/sales", "a..b.py"),
        # not paths at all
        ("", "/work/sales", None),
        ("/work/sales/a.py", "", None),
        ("   ", "/work/sales", None),
        (None, "/work/sales", None),
        ("/work/sales/a.py", None, None),
        (7, "/work/sales", None),
    ],
)
def test_the_rule(path: object, folder: object, relative: str | None) -> None:
    assert project_paths.relative_in(path, folder) == relative
    assert project_paths.inside(path, folder) is (relative is not None)
    assert project_python.in_project(path, folder) is (relative is not None)


def test_a_link_is_asked_only_when_the_text_says_no() -> None:
    asked: list[str] = []
    links = {"/link/sales": "/disk/projects/sales", "/link/sales/a.py": "/disk/projects/sales/a.py"}

    def real(path: str) -> str:
        asked.append(path)
        return links.get(path, path)

    assert project_paths.relative_in("/link/sales/a.py", "/link/sales", real) == "a.py"
    assert asked == []  # inside as written: the disk is never asked
    # the project opened through a link, the file named by its real place (a watcher's path)
    assert (
        project_paths.relative_in("/disk/projects/sales/scripts/b.py", "/link/sales", real) == "scripts/b.py"
    )
    # and the other way round
    assert project_paths.inside("/link/sales/a.py", "/disk/projects/sales", real)
    assert not project_paths.inside("/disk/projects/other/a.py", "/link/sales", real)
    assert not project_paths.inside("/disk/projects/sales/a.py", "/link/sales")  # no port: the text alone


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="this system makes no links")
def test_a_real_link_on_disk(tmp_path: Path) -> None:
    project = tmp_path / "projects" / "Sales"
    (project / "scripts").mkdir(parents=True)
    (project / "scripts" / "load.py").write_text("x = 1\n", encoding="utf-8")
    link = tmp_path / "shortcut"
    try:
        link.symlink_to(project, target_is_directory=True)
    except OSError:
        pytest.skip("this account may not make links")
    by_link = str(link / "scripts" / "load.py")
    assert not project_paths.inside(by_link, str(project))
    assert project_paths.relative_in(by_link, str(project), SabArchive.real) == "scripts/load.py"
    assert project_paths.relative_in(str(project / "scripts" / "load.py"), str(link), SabArchive.real) == (
        "scripts/load.py"
    )
    assert project_paths.inside(by_link, str(project), os.path.realpath)  # the composition root's port


def test_the_library_tree_and_a_library_file_use_the_rule() -> None:
    tree = code_tree.library_tree(
        "C:\\Users\\dana\\Library", ["c:\\users\\dana\\library\\connections\\Warehouse.blade.py"]
    )
    files = [f["path"] for group in tree for f in group["files"]]
    assert files == ["connections/Warehouse.blade.py"]
    assert script_ide.library_file("C:\\Python\\Lib\\json\\decoder.py", ("c:\\python\\lib",))
    assert not script_ide.library_file("C:\\Python\\Lib-old\\json\\decoder.py", ("c:\\python\\lib",))
    assert not script_ide.library_file("/usr/lib/python3/../../etc/x.py", ("/usr/lib/python3",))


# The places that used to write the rule out themselves: each must ask project_paths now.
ASKERS = (
    "bootstrap.py",
    "services/project_outline.py",
    "services/context_md.py",
    "services/project_scope.py",
    "services/api_export.py",
    "domain/script_ide.py",
    "domain/code_tree.py",
    "domain/project_python.py",
)


@pytest.mark.parametrize("name", ASKERS)
def test_every_copy_asks_the_one_rule(name: str) -> None:
    tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "project_paths"
        and node.attr in ("inside", "relative_in")
    ]
    assert calls, f"{name} no longer asks project_paths"


def test_no_layer_writes_the_rule_out_again() -> None:
    """`x.startswith(folder.rstrip("/") + "/")` over a path: the shape every copy had. A new one belongs in
    project_paths (domain and services; the adapters walk real folders their own way)."""
    found = []
    for layer in ("domain", "services"):
        for path in sorted((PACKAGE / layer).glob("*.py")):
            if path.name == "project_paths.py":
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if ".startswith(" in line and '.rstrip("/") + "/"' in line and "replace(" in line:
                    found.append(f"{layer}/{path.name}:{number}")
    assert not found, found
