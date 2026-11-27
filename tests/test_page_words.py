"""The pages' names in the words a person or the agent reads: the Data page is the Catalog page (the rail's
name since 2026-11-21), in the commands' descriptions, the MCP guide and index, the docstrings, README.md and
the user guide. Release notes keep the words of their day."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = "Data page"
READ = (".py", ".md", ".cs", ".razor", ".js")
# This test and the browser test that say the old name on purpose.
SAYS_IT = {"tests/test_page_words.py", "tests/e2e/blazor/test_erd_catalog_environment.py"}


def texts() -> list[Path]:
    names = ("src", "extensions", "plugin", "tests", "blazor/SwissArmyBench.Web", "blazor/interop")
    folders = [ROOT / n for n in names]
    found = [p for folder in folders for p in folder.rglob("*") if p.suffix in READ and p.is_file()]
    kept = [p for p in found if not {"obj", "bin", "node_modules", "wwwroot"} & set(p.parts)]
    return [*kept, ROOT / "README.md"]


def test_the_data_page_is_called_the_catalog_page() -> None:
    said = sorted(
        str(p.relative_to(ROOT))
        for p in texts()
        if str(p.relative_to(ROOT)).replace("\\", "/") not in SAYS_IT and OLD in p.read_text(encoding="utf-8")
    )
    assert said == []
