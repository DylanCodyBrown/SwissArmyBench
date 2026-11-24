"""Home's summary of the open project (the owner, 2026-11-24: "The project home page should become a
summary of the current open project its confusing trying to figure out what project is actually open").
Pure rules, no I/O: the answers other services already give, joined into one.

  tables       the project's tables with their rows and columns (the store's) and where each came from
  documents    its notebooks (data.ipynb first), scripts, API.py, canvases and structures, each with the page
               it opens on
  connections  the connections it uses (ProjectUse), each with its card's status word and its colour
  recent       the Session page's last entries, as it words them
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# The page each kind of document opens on (domain/workbench_pages.py's rule: a notebook on Notebooks,
# every .py and a structure on Scripts, a canvas on the Canvas).
PAGES: dict[str, str] = {
    "notebook": "notebooks",
    "script": "scripts",
    "structure": "scripts",
    "app": "canvas",
}
DATA_NOTEBOOK = "data.ipynb"
API_FILE = "API.py"
RECENT = 6  # the Session entries shown; See all opens the Session page


def tables(kept: Iterable[Mapping[str, Any]], open_now: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The project's tables (.sab/project.json's, in its order), each with its rows and columns as the store
    has them now (None while it is not read)."""
    store = {str(d["name"]): d for d in open_now}
    out = []
    for table in kept:
        name = str(table["name"])
        held = store.get(name) or {}
        out.append(
            {
                "name": name,
                "from": str(table.get("from") or ""),
                "kind": str(table.get("kind") or ""),
                "rows": held.get("rows"),
                "columns": held.get("columns"),
            }
        )
    return out


def documents(listed: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The project's documents by kind (notebooks with data.ipynb first, scripts with API.py first,
    canvases, structures), each with its page; the made files (data.py, adapter.py, ...) left out: they are
    the app's."""
    order = {kind: at for at, kind in enumerate(("notebook", "script", "app", "structure"))}

    def first(document: Mapping[str, Any]) -> int:
        return 0 if str(document["path"]) in (DATA_NOTEBOOK, API_FILE) else 1

    shown = [d for d in listed if not d.get("made") and str(d.get("kind")) in PAGES]
    shown.sort(key=lambda d: (order[str(d["kind"])], first(d), str(d["path"]).casefold()))
    return [
        {
            "name": str(d["name"]),
            "path": str(d["path"]),
            "full": str(d.get("full") or d["path"]),
            "kind": str(d["kind"]),
            "page": PAGES[str(d["kind"])],
            "api": str(d["path"]) == API_FILE,
        }
        for d in shown
    ]


def connections(
    used: Sequence[str], cards: Iterable[Mapping[str, Any]], colours: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The connections the project uses, in that order, each with its type and status word (its card's) and
    its colour (this computer's)."""
    by_name = {str(c["name"]).casefold(): c for c in cards}
    colour_of = {str(c["name"]).casefold(): str(c.get("colour") or "") for c in colours}
    out = []
    for name in dict.fromkeys(used):
        card = by_name.get(name.casefold()) or {}
        out.append(
            {
                "name": name,
                "type": str(card.get("type") or ""),
                "status": str(card.get("status") or ""),
                "colour": colour_of.get(name.casefold(), ""),
            }
        )
    return out


def counts(answer: Mapping[str, Any]) -> dict[str, int]:
    """Each section's count, for its heading (and the agent's one line)."""
    docs = answer.get("documents") or []
    return {
        "tables": len(answer.get("tables") or []),
        "notebooks": sum(1 for d in docs if d["kind"] == "notebook"),
        "scripts": sum(1 for d in docs if d["kind"] == "script"),
        "apps": sum(1 for d in docs if d["kind"] == "app"),
        "structures": sum(1 for d in docs if d["kind"] == "structure"),
        "connections": len(answer.get("connections") or []),
    }
