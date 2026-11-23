"""The one icon set (the front end's IconSet.cs; the owner, 2026-11-16: "it needs a glow up with icons. For
example our connection panel has no icons on the connection types"): every connection type the server
offers has an icon of its own, no two databases share one, Add API's presets have theirs, and every icon
name the page asks for is in the set (none drawn blank)."""

from __future__ import annotations

import re
from pathlib import Path

from swissarmybench.domain import apis
from tests.conftest import AUTH, make_client

WEB = Path(__file__).resolve().parents[1] / "blazor" / "SwissArmyBench.Web"


def icon_set() -> dict[str, str]:
    """The set's names and each one's markup, as written (IconSet.Paths: ["name"] = "markup",)."""
    text = (WEB / "Components" / "IconSet.cs").read_text(encoding="utf-8")
    return dict(re.findall(r'^\s+\["([\w-]+)"\] = (.+),$', text, re.M))


def names_used() -> set[str]:
    """Every icon name a page asks for by its literal name: <Icon Name="x" />."""
    used: set[str] = set()
    for path in WEB.rglob("*.razor"):
        if "bin" in path.parts or "obj" in path.parts:
            continue
        used |= set(re.findall(r'<Icon Name="([\w-]+)"', path.read_text(encoding="utf-8")))
    return used


def test_every_icon_the_page_asks_for_is_in_the_set() -> None:
    icons = icon_set()
    assert len(icons) > 120
    missing = sorted(name for name in names_used() if name not in icons)
    assert missing == []
    assert len(names_used()) > 50


def test_every_connection_type_and_preset_has_its_own_icon(tmp_path: Path) -> None:
    icons = icon_set()
    with make_client(tmp_path) as client:
        types = client.get("/connections/types", headers=AUTH).json()["types"]
    assert len(types) > 30
    without = [t["id"] for t in types if t["id"] not in icons]
    assert without == []  # by its type's id (the Connections page's card)
    databases = [icons[t["id"]] for t in types if t["connection"] == "database"]
    assert len(set(databases)) == len(databases)  # no two databases look the same
    every = [icons[t["id"]] for t in types]
    assert len(set(every)) == len(every)
    for preset in apis.PRESETS:
        assert f"api-{preset}" in icons
    assert {"api-openapi", "api-form"} <= set(icons)
