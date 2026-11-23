"""The stylesheet's braces balance: a merge that drops one leaves every rule after it unstyled
(2026-11-17: the connection colours and connection SQL merges lost a `}`, and the Structures and
APIs pages came out unstyled)."""

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "blazor" / "SwissArmyBench.Web" / "wwwroot" / "css"


def test_every_stylesheet_closes_every_brace() -> None:
    sheets = sorted(CSS.glob("*.css"))
    assert len(sheets) > 5
    for sheet in sheets:
        text = re.sub(r"/\*.*?\*/", "", sheet.read_text(encoding="utf-8"), flags=re.S)
        depth = 0
        for line_number, line in enumerate(text.splitlines(), 1):
            for ch in line:
                depth += (ch == "{") - (ch == "}")
                assert depth >= 0, f"{sheet.name}: a `}}` with no `{{` by line {line_number}"
        assert depth == 0, f"{sheet.name}: {depth} rule(s) never closed"
