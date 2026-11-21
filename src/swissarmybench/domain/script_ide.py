"""The Scripts page as a Python IDE (the owner, 2026-11-17: "the scripts rail page should simply be a
navigation
for the project files with our robust IDE for python we can use to edit and tweak and save these files").

Its rules beside the editor's intelligence (services/intellisense.py stays the one completion, signature,
hover and lint): search and replace across the project's scripts (regex, case, whole word), a symbol rename's
plan (Jedi's changes, previewed line by line) that never writes a made or read-only file, and the names it
checks. Pure: the files come in as {path: text}.
"""

from __future__ import annotations

import keyword
import re
from collections.abc import Mapping
from typing import Any

MAX_MATCHES = 2000
MADE_WHY = "made by the app: edit its source, or Edit by hand"


class IdeError(ValueError):
    """A request the IDE cannot take: what to send instead."""


def _pattern(query: Any, regex: bool, case: bool, word: bool) -> re.Pattern[str]:
    if not isinstance(query, str) or not query:
        raise IdeError("Send the text to find.")
    body = query if regex else re.escape(query)
    if word:
        body = rf"\b(?:{body})\b"
    try:
        return re.compile(body, 0 if case else re.IGNORECASE)
    except re.error as error:
        raise IdeError(f"{query!r} is not a regular expression: {error}.") from None


def search(
    files: Mapping[str, str], query: Any, regex: bool = False, case: bool = False, word: bool = False
) -> dict[str, Any]:
    """Every match in the files, by file then line: {results: [{path, matches: [{line, column (from 1),
    length, text (the line)}]}], count, cut (more than MAX_MATCHES)}."""
    pattern = _pattern(query, regex, case, word)
    results: list[dict[str, Any]] = []
    count = 0
    for path in sorted(files):
        matches = []
        for number, line in enumerate(files[path].split("\n"), 1):
            for found in pattern.finditer(line):
                if count >= MAX_MATCHES:
                    break
                if found.end() == found.start():
                    continue
                matches.append(
                    {
                        "line": number,
                        "column": found.start() + 1,
                        "length": found.end() - found.start(),
                        "text": line,
                    }
                )
                count += 1
        if matches:
            results.append({"path": path, "matches": matches})
    return {"results": results, "count": count, "cut": count >= MAX_MATCHES}


def replace(
    files: Mapping[str, str],
    query: Any,
    to: Any,
    regex: bool = False,
    case: bool = False,
    word: bool = False,
    read_only: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Replace's plan: {changes: {path: its new text}, skipped: [{path, why}], count}; a read-only (made)
    file is never changed."""
    if not isinstance(to, str):
        raise IdeError("Send what to replace it with (to).")
    pattern = _pattern(query, regex, case, word)
    changes: dict[str, str] = {}
    skipped: list[dict[str, str]] = []
    count = 0
    for path in sorted(files):
        try:
            text, n = pattern.subn(to if regex else to.replace("\\", "\\\\"), files[path])
        except (re.error, IndexError) as error:
            raise IdeError(f"The replacement does not fit the expression: {error}.") from None
        if not n:
            continue
        if path in read_only:
            skipped.append({"path": path, "why": MADE_WHY})
            continue
        changes[path] = text
        count += n
    return {"changes": changes, "skipped": skipped, "count": count}


def _lines(before: str, after: str) -> list[dict[str, Any]]:
    old, new = before.split("\n"), after.split("\n")
    out = []
    for number in range(max(len(old), len(new))):
        a = old[number] if number < len(old) else ""
        b = new[number] if number < len(new) else ""
        if a != b:
            out.append({"line": number + 1, "before": a, "after": b})
    return out


def rename_plan(
    changed: Mapping[str, str], before: Mapping[str, str], read_only: set[str] | frozenset[str] = frozenset()
) -> dict[str, Any]:
    """A rename's plan from its changed files ({path: new text}): the changes it may write, what it skips (a
    made or read-only file: its source would need the change), and a preview of each changed line."""
    changes: dict[str, str] = {}
    skipped: list[dict[str, str]] = []
    preview: list[dict[str, Any]] = []
    for path in sorted(changed):
        if path in read_only:
            skipped.append({"path": path, "why": MADE_WHY})
            continue
        changes[path] = changed[path]
        preview.append({"path": path, "lines": _lines(before.get(path, ""), changed[path])})
    return {"changes": changes, "skipped": skipped, "preview": preview}


def valid_identifier(name: Any) -> bool:
    return isinstance(name, str) and name.isidentifier() and not keyword.iskeyword(name)
