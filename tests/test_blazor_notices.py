"""Every notice the server broadcasts is followed by a page of the front end, or is listed here with why not.

The swap to Blazor left notices with no listener (the agent's navigate and snapshot did nothing; a renamed
script's tab stayed behind). This reads the sources: each `broadcast({"type": "..."})` and `tell_workbench(
{"type": "..."})` of the server and its extensions must be named in blazor/ (its C#, Razor or interop), or in
NOT_FOLLOWED with its reason."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENT = re.compile(r'(?:broadcast|tell_workbench)\(\s*\{\s*"type":\s*"(\w+)"')
# Notices built before they are sent (a variable, a helper).
ALSO_SENT = ("navigate", "session_entry", "environment_changed")

# No page shows what these change: each with why (docs/ideas.md "Fix it all", 2026-11-27).
NOT_FOLLOWED: dict[str, str] = {
    "workbench_handoff": "the Blazor pages move a document to another window by its file (saved first), "
    "never through /workbench/handoffs: no page takes one",
    "inbox_changed": "no page shows how much waits for the agent; the prompt hook and agent_inbox read it",
    "powerbi_live": "the Power BI page is drawn from data and follows extension_panel_changed, sent beside it",
}


def server_sources() -> list[Path]:
    folders = [ROOT / "src" / "swissarmybench", *(ROOT / "extensions").glob("*/src")]
    return [p for folder in folders for p in folder.rglob("*.py")]


def sent() -> set[str]:
    found = set(ALSO_SENT)
    for path in server_sources():
        found.update(SENT.findall(path.read_text(encoding="utf-8")))
    return found


def front_end_text() -> str:
    web = ROOT / "blazor"
    files = [
        p
        for folder, endings in ((web / "SwissArmyBench.Web", (".cs", ".razor")), (web / "interop", (".js",)))
        for p in folder.rglob("*")
        if p.suffix in endings and not {"obj", "bin", "wwwroot"} & set(p.parts)
    ]
    return "\n".join(p.read_text(encoding="utf-8") for p in files)


def test_every_notice_is_followed_or_said_why_not() -> None:
    text = front_end_text()
    unfollowed = sorted(n for n in sent() if f'"{n}"' not in text and n not in NOT_FOLLOWED)
    assert unfollowed == [], f"No page follows: {unfollowed} (follow it, or say why in NOT_FOLLOWED)"


def test_the_reasons_name_only_notices_still_sent_and_not_followed() -> None:
    text = front_end_text()
    assert sorted(n for n in NOT_FOLLOWED if n not in sent()) == []
    assert sorted(n for n in NOT_FOLLOWED if f'"{n}"' in text) == []
