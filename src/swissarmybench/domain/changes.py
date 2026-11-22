"""The change log (the owner, 2026-11-22; Plans/changes.plan.md): "a change tracking, event based tracker that
would write to a per project change log, so when a table structure, an API, or anything is modified the agent
could quickly run an MCP tool that would return the last recorded change on an object."

It reads top to bottom in the order a change is kept:

  1. One change   change(kind, name, before, after, words): the object, what changed as a structural
                  difference (each part's names added, removed, changed; a column's or a field's type, the
                  only thing shown, since a type is not a value), plain words, the fingerprints before and
                  after; None when nothing changed. A service raises it on its audit entry (`change=`), so
                  the Session page and the log hear the same event; the log stamps when and who (stamped)
  2. The file     .sab/changes.jsonl (Git-ignored, everything kept): one sorted JSON line a change (line),
                  read back skipping a line that is not one (parse)
  3. The views    the agent's changes(action): last(object), history(object, n), since(time), search by
                  kind, who or a word (view)

Never a value: a part's values are fingerprinted, never kept (a setting's host, a variable's value, a step's
filter value); names and types only. Pure rules: no I/O, no clock.
"""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from swissarmybench.domain.notebooks import read_notebook

KINDS = (
    "table",
    "connection",
    "api",
    "endpoint",
    "widget",
    "canvas",
    "notebook",
    "script",
    "setting",
    "variable",
    "library",
)
WHO = ("user", "agent", "app")
SHOWN = ("columns", "fields")  # parts whose descriptions are types, said as they changed
VIEWS = ("last", "history", "since", "search")
MAX_NAMES = 40  # names listed per part (the rest counted)

Change = dict[str, Any]


class ChangesError(ValueError):
    """A kind or a view that is not one, said in one sentence."""


# ===== 1. One change =====


def fingerprint(value: Any) -> str:
    """A value's 12-character fingerprint (canonical JSON, hashed): the same for the same thing."""
    if value is None:
        return ""
    text = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()[:12]


def _parts(structure: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Each part as {name: description}: a list is numbered ("2 sort"), a plain value is one part."""
    out: dict[str, dict[str, Any]] = {}
    for part, value in (structure or {}).items():
        if isinstance(value, Mapping):
            out[str(part)] = {str(k): v for k, v in value.items()}
        elif isinstance(value, list | tuple):
            out[str(part)] = {
                f"{i + 1} {item if isinstance(item, str) else ''}".strip(): item
                for i, item in enumerate(value)
            }
        else:
            out[str(part)] = {str(part): value}
    return out


def _cut(names: Sequence[str]) -> list[str]:
    listed = sorted(names)
    return (
        listed if len(listed) <= MAX_NAMES else [*listed[:MAX_NAMES], f"and {len(listed) - MAX_NAMES} more"]
    )


def diff(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The structural difference by part: names added, removed and changed (a column's types said)."""
    was, now = _parts(before), _parts(after)
    out: dict[str, dict[str, Any]] = {}
    for part in sorted(set(was) | set(now)):
        old, new = was.get(part, {}), now.get(part, {})
        changed = [n for n in old.keys() & new.keys() if fingerprint(old[n]) != fingerprint(new[n])]
        one: dict[str, Any] = {
            "added": _cut([n for n in new if n not in old]),
            "removed": _cut([n for n in old if n not in new]),
            "changed": _cut(changed),
        }
        if part in SHOWN and changed:
            one["types"] = {n: {"was": str(old[n])[:60], "now": str(new[n])[:60]} for n in sorted(changed)}
        if one["added"] or one["removed"] or one["changed"]:
            out[part] = one
    return out


def _part_words(part: str, one: Mapping[str, Any]) -> str:
    said = []
    if one["added"]:
        said.append(f"added {', '.join(one['added'])}")
    if one["removed"]:
        said.append(f"removed {', '.join(one['removed'])}")
    types = one.get("types") or {}
    if one["changed"] and types:
        said.append("retyped " + ", ".join(f"{n} ({t['was']} to {t['now']})" for n, t in types.items()))
    elif one["changed"]:
        said.append(f"changed {', '.join(one['changed'])}")
    return f"{part} " + "; ".join(said)


def words_of(name: str, found: Mapping[str, Mapping[str, Any]]) -> str:
    """'orders: columns added segment; removed region; steps added 2 sort'."""
    return f"{name}: " + "; ".join(_part_words(part, one) for part, one in found.items())


def change(
    kind: str, name: str, before: Mapping[str, Any] | None, after: Mapping[str, Any] | None, words: str = ""
) -> Change | None:
    """One change to an object, or None when its fingerprint did not move and no words were given. `before`
    and `after` are its structure by part ({"columns": {name: type}, "settings": {name: value}, "steps":
    [kind, ...]}): values are fingerprinted, never kept."""
    if kind not in KINDS:
        raise ChangesError(f"A change's object is one of {', '.join(KINDS)}.")
    was, now = fingerprint(before), fingerprint(after)
    if was == now and not words:  # words given: the caller knows it changed (a variable's value, unseen)
        return None
    found = diff(before, after)
    return {
        "object": {"kind": kind, "name": " ".join(str(name).split())[:200]},
        "words": words or (words_of(name, found) if found else f"{name}: changed"),
        "diff": found,
        "before": was,
        "after": now,
    }


def document_shape(kind: str, text: str) -> dict[str, Any]:
    """A notebook's cells by number (each one's kind and source), or a script's top-level functions and
    classes by name and the rest of its module: the parts a change names (their text fingerprinted)."""
    if kind == "notebook":
        try:
            cells = read_notebook(text)
        except ValueError:
            return {"cells": {"notebook": text}}
        return {
            "cells": {
                f"cell {c.number}" if c.number else f"cell at {i + 1}": [c.kind, c.source]
                for i, c in enumerate(cells)
            }
        }
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"code": {"module": text}}
    defined = {
        node.name: ast.get_source_segment(text, node) or ""
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }
    rest = [
        ast.dump(n)
        for n in tree.body
        if not isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    return {"definitions": defined, "code": {"module": rest}}


def stamped(made: Change, at: str, who: str) -> Change:
    """A change as the log keeps it: when, and who (the user, the agent, the app itself)."""
    return {"at": at, "who": who if who in WHO else "app"} | made


# ===== 2. The file =====


def line(event: Change) -> str:
    """One line of .sab/changes.jsonl: sorted keys, the same bytes for the same change."""
    return json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"


def parse(text: str) -> list[Change]:
    """The file's changes, oldest first; a line that is not one is skipped."""
    out = []
    for raw in text.splitlines():
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if isinstance(event, dict) and isinstance(event.get("object"), dict) and event.get("at"):
            out.append(event)
    return out


# ===== 3. The views =====


def _matches(event: Change, obj: str) -> bool:
    """`obj` as kind:name, or a name alone (any kind), in any case."""
    kind, _, name = obj.partition(":") if ":" in obj and obj.split(":", 1)[0] in KINDS else ("", "", obj)
    found = event["object"]
    return (not kind or found.get("kind") == kind) and str(
        found.get("name", "")
    ).casefold() == name.casefold()


def view(
    events: Sequence[Change],
    action: str,
    obj: str = "",
    n: int = 20,
    since: str = "",
    kind: str = "",
    who: str = "",
    word: str = "",
) -> dict[str, Any]:
    """The agent's changes(action): last and history of an object, since a time, a search by kind, who or a
    word in its words; newest first."""
    if action not in VIEWS:
        raise ChangesError(f"changes' action is one of {', '.join(VIEWS)}.")
    most = max(1, min(int(n or 20), 1000))
    newest = list(reversed(events))
    if action in ("last", "history"):
        if not obj:
            raise ChangesError(f"Name the object: changes {action} object=table:orders (or a name alone).")
        mine = [e for e in newest if _matches(e, obj)]
        if action == "last":
            return {"object": obj, "change": mine[0] if mine else None}
        return {"object": obj, "changes": mine[:most]}
    if action == "since":
        if not since:
            raise ChangesError("Say since when: changes since since=2026-11-22T09:00:00.")
        return {"since": since, "changes": [e for e in newest if str(e["at"]) > since][:most]}
    found = [
        e
        for e in newest
        if (not kind or e["object"].get("kind") == kind)
        and (not who or e.get("who") == who)
        and (not word or word.casefold() in str(e.get("words", "")).casefold())
    ]
    return {"changes": found[:most]}
