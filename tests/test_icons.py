"""The one icon set (web/src/dom.ts ICONS; the owner, 2026-11-16: "it needs a glow up with icons. For
example our connection panel has no icons on the connection types"): every connection type the server
offers has an icon of its own, no two databases share one, Add API's presets have theirs, and every icon
name the page asks for is in the set (none drawn blank)."""

from __future__ import annotations

import re
from pathlib import Path

from swissarmybench.domain import apis
from tests.conftest import AUTH, make_client

WEB = Path(__file__).resolve().parents[1] / "web" / "src"


def icon_set() -> dict[str, str]:
    """The set's names and each one's markup, as written (a part's name kept: CYL + '...')."""
    text = (WEB / "dom.ts").read_text(encoding="utf-8")
    body = text.split("const ICONS: Record<string, string> = {", 1)[1].split("\n};", 1)[0]
    found: dict[str, str] = {}
    for line in body.splitlines():
        match = re.match(r'\s{2}"?([\w-]+)"?:\s*(.+),$', line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def names_used() -> set[str]:
    """Every icon name web/src asks for: icon("x"), { icon: "x" }, a menu entry ["x", "Label", ...],
    registerAnalysis("x", ...), and the values of each *_ICONS map."""
    used: set[str] = set()
    for path in WEB.rglob("*.ts"):
        text = path.read_text(encoding="utf-8")
        used |= set(re.findall(r'\bicon\(\s*"([\w-]+)"', text))
        used |= set(re.findall(r'\bicon:\s*"([\w-]+)"', text))
        used |= set(re.findall(r'registerAnalysis\(\s*"([\w-]+)"', text))
        used |= set(re.findall(r'\[\s*"([\w-]+)",\s*"[^"]+",\s*\(\)\s*=>', text))
        for block in re.findall(r"const \w*ICONS\b[^=]*=\s*\{([^}]*)\}", text):
            used |= set(re.findall(r':\s*"([\w-]+)"', block))
    return used


def test_every_icon_the_page_asks_for_is_in_the_set() -> None:
    icons = icon_set()
    assert len(icons) > 120
    missing = sorted(name for name in names_used() if name not in icons)
    assert missing == []


def test_every_connection_type_and_preset_has_its_own_icon(tmp_path: Path) -> None:
    icons = icon_set()
    with make_client(tmp_path) as client:
        types = client.get("/connections/types", headers=AUTH).json()["types"]
    assert len(types) > 30
    without = [t["id"] for t in types if t["id"] not in icons]
    assert without == []  # by its type's id (connectionsWindow.ts connectionIcon)
    databases = [icons[t["id"]] for t in types if t["connection"] == "database"]
    assert len(set(databases)) == len(databases)  # no two databases look the same
    every = [icons[t["id"]] for t in types]
    assert len(set(every)) == len(every)
    for preset in apis.PRESETS:
        assert f"api-{preset}" in icons
    assert {"api-openapi", "api-form"} <= set(icons)
