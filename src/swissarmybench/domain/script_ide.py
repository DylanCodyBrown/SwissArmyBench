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


# ===== the explorer's tree actions: New package, Rename, Duplicate (2026-11-21) =====
# A module renamed (or a package) takes every import of it in the project's other modules with it, the same
# plan and preview as F2's rename: `import etl.load`, `from etl.load import x`, `from etl import load` (then
# `load` stays its name there: `from etl import loader as load`).


def valid_file_name(name: Any) -> bool:
    """A module's file name: an identifier then `.py` (`load_orders.py`), or a package's folder name."""
    if not isinstance(name, str):
        return False
    stem = name[: -len(".py")] if name.endswith(".py") else name
    return valid_identifier(stem)


def _module_ref(old: str) -> re.Pattern[str]:
    """`old` as a dotted module name standing alone or as a prefix (`etl.load`, `etl.load.helpers`)."""
    return re.compile(rf"(?<![\w.]){re.escape(old)}(?=$|[^\w])")


def import_rewrite(text: str, old: str, new: str) -> str:
    """`text` with each import of the module `old` (or of a module under it) naming `new` instead. Only the
    import statements' own lines change; code that does not parse is left as it is."""
    import ast

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    lines = text.split("\n")
    pattern = _module_ref(old)
    old_parent, _, old_last = old.rpartition(".")
    new_parent, _, new_last = new.rpartition(".")
    edits: dict[int, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        first, last = node.lineno - 1, (node.end_lineno or node.lineno) - 1
        segment = "\n".join(edits.get(i, lines[i]) for i in range(first, last + 1))
        changed = segment
        if isinstance(node, ast.Import):
            if any(a.name == old or a.name.startswith(old + ".") for a in node.names):
                changed = pattern.sub(new, segment)
        elif node.level == 0 and node.module:
            if node.module == old or node.module.startswith(old + "."):
                head, sep, rest = segment.partition(" import ")
                changed = pattern.sub(new, head) + sep + rest
            elif node.module == old_parent and any(a.name == old_last for a in node.names):
                # `from etl import load`: the module's own name in the list (kept as its old name there)
                head, sep, rest = segment.partition(" import ")
                own = next(a for a in node.names if a.name == old_last)
                alias = (
                    f" as {own.asname}" if own.asname else "" if new_last == old_last else f" as {old_last}"
                )
                name = rf"(?<![\w.]){re.escape(old_last)}(?![\w])(\s+as\s+\w+)?"
                if new_parent != old_parent and len(node.names) > 1:
                    # The others stay where they come from; the module gets an import line of its own.
                    rest = (
                        re.sub(name + r"\s*,\s*", "", rest, count=1)
                        if re.search(name + r"\s*,", rest)
                        else re.sub(r",\s*" + name, "", rest, count=1)
                    )
                    indent = re.match(r"\s*", lines[first]).group(0)  # type: ignore[union-attr]
                    line = (
                        f"{indent}from {new_parent} import {new_last}{alias}"
                        if new_parent
                        else f"{indent}import {new_last}{alias}"
                    )
                    changed = head + sep + rest + "\n" + line
                else:
                    if new_parent != old_parent:
                        head = re.sub(
                            rf"(?<![\w.]){re.escape(old_parent)}(?![\w.])", new_parent, head, count=1
                        )
                    rest = re.sub(name, new_last + alias, rest, count=1)
                    changed = head + sep + rest
                    if not new_parent:  # a module at the top: `import loader as load`
                        indent = re.match(r"\s*", lines[first]).group(0)  # type: ignore[union-attr]
                        changed = f"{indent}import {new_last}{alias}"
        if changed != segment:
            parts = changed.split("\n")
            span = last - first + 1
            if len(parts) > span:  # an added line goes with the statement's last line
                parts = [*parts[: span - 1], "\n".join(parts[span - 1 :])]
            for offset, i in enumerate(range(first, last + 1)):
                edits[i] = parts[offset] if offset < len(parts) else ""
    if not edits:
        return text
    return "\n".join(edits.get(i, line) for i, line in enumerate(lines))


def move_plan(
    texts: Mapping[str, str],
    moved: str,
    old_module: str,
    new_module: str,
    read_only: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """A module's rename across the project: the other files' imports changed ({path: new text}, the moved
    file's own imports too), previewed and skipped as rename_plan does."""
    changed: dict[str, str] = {}
    for path, text in texts.items():
        after = import_rewrite(text, old_module, new_module)
        if after != text:
            changed[path] = after
    plan = rename_plan(changed, texts, read_only)
    return plan | {"moved": moved}


def free_copy_name(relative: str, taken: set[str]) -> str:
    """`scripts/load.py` -> `scripts/load_copy.py`, then `_copy_2`... the first not taken."""
    folder, _, name = relative.rpartition("/")
    stem = name[: -len(".py")] if name.endswith(".py") else name
    n = 1
    while True:
        candidate = f"{stem}_copy{'' if n == 1 else f'_{n}'}.py"
        full = f"{folder}/{candidate}" if folder else candidate
        if full not in taken:
            return full
        n += 1


# ===== a library's source, read-only (2026-11-21): where go to definition leads outside the project =====

LIBRARY_SUFFIXES: tuple[str, ...] = (".py", ".pyi")
_LIBRARY_PARTS: frozenset[str] = frozenset({"site-packages", "dist-packages", "typeshed"})


def library_file(path: Any, roots: tuple[str, ...]) -> bool:
    """Whether `path` is a library's source the Scripts page may show read-only: a .py or .pyi inside one of
    Python's own folders (`roots`: the standard library's, site-packages) or a site-packages folder of any
    Python (a script's own environment). Never another file of the computer's."""
    if not isinstance(path, str) or not path.endswith(LIBRARY_SUFFIXES):
        return False
    given = path.replace("\\", "/")
    parts = given.split("/")
    if ".." in parts:
        return False
    if _LIBRARY_PARTS & set(parts[:-1]):
        return True
    return any(given.startswith(r.replace("\\", "/").rstrip("/") + "/") for r in roots if r)
