"""The Scripts IDE's rules (domain/script_ide.py): search and replace across the project's scripts, a rename's
plan that never touches a made or read-only file, made-up code only."""

from __future__ import annotations

import pytest

from swissarmybench.domain import script_ide as ide

FILES = {
    "/p/scripts/etl/load.py": (
        "from functions import tidy\n\nORDERS = 'orders'\n\ndef load():\n    return tidy(ORDERS)\n"
    ),
    "/p/functions.py": "def tidy(name):\n    return name.strip()\n",
    "/p/data.py": "import functions\nx = functions.tidy(' a ')\n",
}


def test_search_finds_each_match_with_its_line() -> None:
    found = ide.search(FILES, "tidy")
    assert [(r["path"], [m["line"] for m in r["matches"]]) for r in found["results"]] == [
        ("/p/data.py", [2]),
        ("/p/functions.py", [1]),
        ("/p/scripts/etl/load.py", [1, 6]),
    ]
    assert found["count"] == 4
    first = found["results"][0]["matches"][0]
    assert first == {"line": 2, "column": 15, "length": 4, "text": "x = functions.tidy(' a ')"}


def test_search_case_word_and_regex() -> None:
    assert ide.search(FILES, "TIDY")["count"] == 4
    assert ide.search(FILES, "TIDY", case=True)["count"] == 0
    assert ide.search({"/a.py": "tidy tidying\n"}, "tidy", word=True)["count"] == 1
    assert ide.search(FILES, r"def \w+\(", regex=True)["count"] == 2
    with pytest.raises(ide.IdeError, match="not a regular expression"):
        ide.search(FILES, "(", regex=True)


def test_replace_says_each_change_and_skips_read_only() -> None:
    plan = ide.replace(FILES, "tidy", "neat", read_only={"/p/data.py"})
    assert plan["changes"]["/p/functions.py"] == "def neat(name):\n    return name.strip()\n"
    assert "/p/data.py" not in plan["changes"]
    assert plan["skipped"] == [
        {"path": "/p/data.py", "why": "made by the app: edit its source, or Edit by hand"}
    ]
    assert plan["count"] == 3


def test_a_rename_plan_never_touches_a_made_file() -> None:
    changed = {"/p/functions.py": "def neat(name):\n    return name.strip()\n", "/p/data.py": "x = neat(1)\n"}
    plan = ide.rename_plan(changed, FILES, read_only={"/p/data.py"})
    assert list(plan["changes"]) == ["/p/functions.py"]
    assert plan["skipped"][0]["path"] == "/p/data.py"
    assert plan["preview"][0]["path"] == "/p/functions.py"
    assert plan["preview"][0]["lines"] == [
        {"line": 1, "before": "def tidy(name):", "after": "def neat(name):"}
    ]


def test_a_name_is_checked() -> None:
    assert ide.valid_identifier("neat_name")
    assert not ide.valid_identifier("class")
    assert not ide.valid_identifier("2x")
