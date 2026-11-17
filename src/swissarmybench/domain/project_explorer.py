"""The Project Explorer: the home page's every project in one place (the owner, 2026-11-17: "Make the project
page sortable by card with explanations of project types for beginners"). Pure rules, no I/O.

  projects.json   the projects folder (Settings: Projects folder; None: the default), the custom order (folder
                  paths), the chosen sort, the projects taken off the list, whether the type explanations
                  were put away
  cards           each project's card from its facts: name (its folder's), type (an off extension's said as
                  "needs the <Name> extension"), last opened, last changed, created, its folder, what it
                  holds (notebooks, scripts, apps, tables), Git (a repository, its branch from .git/HEAD:
                  never running git), moved or deleted
  sort            Last opened, Name, Type, Last changed, Created (ascending or descending), or Custom (the
                  cards' own order, dragged or moved left and right)
  filter          by type, and words in the name, the folder or a notebook's name
  kinds           the project types for beginners: each one's title, for whom, what you get, an example (the
                  modes' words: the base's, each on extension's; Streamlit's is the base's until its extension
                  brings its own)
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

SORTS: tuple[str, ...] = ("opened", "name", "type", "changed", "created", "custom")
DEFAULT_SORT: dict[str, Any] = {"by": "opened", "descending": True}
MAX_ORDER: int = 2_000
MAX_QUERY: int = 200
MAX_DOCUMENT_NAMES: int = 200
# A Streamlit app (until the Streamlit extension brings its own type): a base project with its app's canvas.
STREAMLIT: str = "streamlit"
_SHA = re.compile(r"^[0-9a-f]{7,64}$")
_EXPLAIN_FIELDS = ("title", "for_whom", "explain", "example", "deliverable")


class ExplorerError(ValueError):
    """A request about the Project Explorer that cannot be done (why, in words)."""


# ===== projects.json =====


def read_settings(raw: Any) -> dict[str, Any]:
    """projects.json leniently: what does not read is the default."""
    raw = raw if isinstance(raw, dict) else {}
    folder = raw.get("folder")
    order = raw.get("order")
    hidden = raw.get("hidden")
    return {
        "folder": folder if isinstance(folder, str) and folder.strip() else None,
        "order": [p for p in order if isinstance(p, str)][:MAX_ORDER] if isinstance(order, list) else [],
        "sort": check_sort(raw.get("sort"), lenient=True),
        "hidden": [p for p in hidden if isinstance(p, str)][:MAX_ORDER] if isinstance(hidden, list) else [],
        "explained": raw.get("explained") is True,
    }


def write_settings(settings: Mapping[str, Any]) -> str:
    """projects.json's text (sorted, stable)."""
    return json.dumps(dict(settings), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def check_sort(raw: Any, lenient: bool = False) -> dict[str, Any]:
    """{"by": one of SORTS, "descending": bool}."""
    if isinstance(raw, dict) and raw.get("by") in SORTS:
        return {"by": raw["by"], "descending": raw.get("descending") is True}
    if lenient:
        return dict(DEFAULT_SORT)
    raise ExplorerError(f'Sort by one of {", ".join(SORTS)}: {{"by": "name", "descending": false}}.')


def check_order(raw: Any) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw) or len(raw) > MAX_ORDER:
        raise ExplorerError("order is the projects' folders, in the order wanted.")
    return list(dict.fromkeys(raw))


def moved(order: Sequence[str], shown: Sequence[str], path: str, by: int) -> list[str]:
    """Move left or right (by -1 or 1) in the custom order: the shown cards' order, with the projects that
    are not shown kept after them."""
    if by not in (-1, 1):
        raise ExplorerError("by is -1 (left) or 1 (right).")
    listed = [p for p in order if p in shown] + [p for p in shown if p not in order]
    if path not in listed:
        raise ExplorerError("That project is not on the page.")
    at = listed.index(path)
    to = max(0, min(len(listed) - 1, at + by))
    listed.insert(to, listed.pop(at))
    return listed + [p for p in order if p not in listed]


# ===== a project's card =====


def branch_of(head: str | None) -> str | None:
    """The branch .git/HEAD names ("ref: refs/heads/main" -> main); a detached head as its short id."""
    if not head:
        return None
    said = head.strip()
    if said.startswith("ref:"):
        ref = said[4:].strip()
        return ref.removeprefix("refs/heads/") or None
    return said[:7] if _SHA.match(said) else None


def counts(documents: Iterable[Mapping[str, Any]], tables: int) -> dict[str, int]:
    """What a project holds: its notebooks, scripts and apps (not the made exports), and its tables."""
    found = {"notebooks": 0, "scripts": 0, "apps": 0, "tables": tables}
    for document in documents:
        if document.get("made"):
            continue
        key = {"notebook": "notebooks", "script": "scripts", "app": "apps"}.get(str(document.get("kind")))
        if key:
            found[key] += 1
    return found


def kind_of(project_type: str, documents: Iterable[Mapping[str, Any]]) -> str:
    """The card's kind: the project's type, a base project with an app's canvas shown as a Streamlit app."""
    if project_type == "bi" and any(str(d.get("path", "")).endswith(".stapp.json") for d in documents):
        return STREAMLIT
    return project_type


def card(
    path: str,
    facts: Mapping[str, Any] | None,
    kinds: Mapping[str, Mapping[str, Any]],
    off: Mapping[str, Mapping[str, Any]],
    opened: float | None,
    open_now: str | None,
    in_folder: bool,
) -> dict[str, Any]:
    """One project's card. `facts` (None: the folder is not there): type, documents, tables, head (.git/HEAD's
    text, or None), repository, changed, created. `kinds`: the types on here, by id; `off`: an extension's
    type that is not on, by type id: its extension's id and name."""
    name = re.split(r"[\\/]", path.rstrip("\\/"))[-1] or path
    out: dict[str, Any] = {
        "path": path,
        "name": name,
        "opened": opened,
        "open": open_now == path,
        "in_folder": in_folder,
        "missing": facts is None,
    }
    if facts is None:
        return out | {
            "type": None,
            "type_name": None,
            "changed": None,
            "created": None,
            "counts": {},
            "git": None,
        }
    documents = list(facts.get("documents") or [])
    project_type = str(facts.get("type") or "bi")
    kind = kind_of(project_type, documents)
    known = kinds.get(kind) or kinds.get(project_type)
    out |= {
        "type": kind,
        "type_name": str((known or {}).get("title") or (known or {}).get("name") or kind),
        "changed": facts.get("changed"),
        "created": facts.get("created"),
        "counts": counts(documents, int(facts.get("tables") or 0)),
        "documents": [str(d.get("name")) for d in documents][:MAX_DOCUMENT_NAMES],
        "git": {"repository": bool(facts.get("repository")), "branch": branch_of(facts.get("head"))}
        if facts.get("repository")
        else {"repository": False, "branch": None},
    }
    if known is None and project_type in off:
        needed = off[project_type]
        out |= {
            "type_name": str(needed.get("title") or needed.get("name") or project_type),
            "needs": {"extension": needed["id"], "name": needed["name"]},
        }
    return out


# ===== sort and filter =====


def _key(card: Mapping[str, Any], by: str) -> Any:
    if by == "name":
        return str(card["name"]).casefold()
    if by == "type":
        return (str(card.get("type_name") or "~").casefold(), str(card["name"]).casefold())
    value = card.get(by)
    return float(value) if isinstance(value, int | float) else float("-inf")


def sorted_cards(
    cards: Sequence[Mapping[str, Any]], sort: Mapping[str, Any], order: Sequence[str]
) -> list[dict[str, Any]]:
    """The cards in the chosen order. Custom: the order kept, new projects after it (newest opened first);
    a missing project always last."""
    by = str(sort.get("by") or "opened")
    if by == "custom":
        place = {p: i for i, p in enumerate(order)}
        rest = sorted(
            (c for c in cards if c["path"] not in place), key=lambda c: _key(c, "opened"), reverse=True
        )
        kept = sorted((c for c in cards if c["path"] in place), key=lambda c: place[c["path"]])
        listed = [*kept, *rest]
    else:
        listed = sorted(cards, key=lambda c: (_key(c, by), str(c["name"]).casefold()))
        if sort.get("descending"):
            listed.reverse()
    return [dict(c) for c in sorted(listed, key=lambda c: bool(c.get("missing")))]


def filtered(cards: Sequence[Mapping[str, Any]], kind: Any = None, words: Any = None) -> list[dict[str, Any]]:
    """The cards of one type (None: all) whose name, folder or a notebook's name holds every word."""
    if kind is not None and not isinstance(kind, str):
        raise ExplorerError("type is a project type's id.")
    if words is not None and (not isinstance(words, str) or len(words) > MAX_QUERY):
        raise ExplorerError("q is a few words.")
    said = [w.casefold() for w in (words or "").split() if w]
    out = []
    for c in cards:
        if kind and c.get("type") != kind:
            continue
        haystack = " ".join([str(c["name"]), str(c["path"]), *map(str, c.get("documents") or [])]).casefold()
        if all(w in haystack for w in said):
            out.append(dict(c))
    return out


# ===== the project types, for beginners =====


def kinds(modes: Sequence[Mapping[str, Any]], streamlit: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every type New project can make, with its explanation: the base's (BI), Streamlit's (the base's words
    until a mode of that type brings its own), then each on extension's. `make`: what New project sends."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    listed = [*modes[:1], streamlit, *modes[1:]] if modes else [streamlit]
    for mode in listed:
        kind = str(mode.get("type") or "")
        if not kind or kind in seen:
            continue
        if mode is streamlit and any(m.get("type") == STREAMLIT for m in modes):
            continue  # the Streamlit extension's own mode says it
        seen.add(kind)
        entry: dict[str, Any] = {"type": kind, "name": str(mode.get("name") or kind)}
        entry |= {f: str(mode.get(f) or "") for f in _EXPLAIN_FIELDS}
        entry["title"] = entry["title"] or entry["name"]
        entry["make"] = dict(mode.get("make") or {"type": kind})
        out.append(entry)
    return out
