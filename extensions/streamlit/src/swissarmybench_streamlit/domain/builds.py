"""Launch and build history (the owner, 2026-11-19: "build a way to launch the app canvas in a new tab ...
along with a build version history every time we launch, think Visual Studio"; "we just have apps in
folders").

Every launch is a build: `builds/<app>/<number>/` at the project's top (shared in Git, never under .sab/),
holding the exported code exactly as launched (app.py, app_pages/*.py, sab_queries.py and data.py as made,
requirements.txt), the canvas's file and each linked cell's code (`cells.json`, for Restore), and
`build.json`: its number, time, the canvas's hash, what changed since the build before, the launch's result,
the first load's time and the analyzer sessions saved into it. Never rows (data/ is not kept), never a
secret (a connection's password is read from the environment by name). Every file byte-stable: sorted JSON.
Pure rules: no I/O, no clock.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

BUILDS: str = "builds"
BUILD_FILE: str = "build.json"
CELLS_FILE: str = "cells.json"
APP_FILE: str = "app.stapp.json"  # an old app notebook's build (before widgets): read, never written
CANVAS_FILE: str = "canvas.json"  # the canvas's file as launched (format 2): Restore's
WIDGETS_FILE: str = "sab_widgets.py"  # the library's widgets as launched, inlined
PERF_HELPER: str = "sab_perf.py"  # beside a launch's pages only, never in a build
PERF_PREFIX: str = "perf-"
MAX_KEEP: int = 10_000  # every build, unless a setting trims to the last N


class BuildError(ValueError):
    """A build that cannot be taken as named (the message says why)."""


def folder_name(app: str) -> str:
    """The app's folder under builds/: its name, as a folder may be called (`Sales overview` stays)."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", app).strip(" .") or "app"
    return name[:80]


def stable(data: Any) -> str:
    """JSON as a build keeps it: sorted, one indent, a newline at the end (the same bytes, the same thing)."""
    return json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def titled(app_py: str, title: str, number: int) -> str:
    """A build's app.py as its run shows it: the window's title "<app> · build <n>" (the build keeps the
    app's own, so two builds compare by their code)."""
    words = f"{title} · build {number}"
    return re.sub(r"page_title=(['\"]).*?\1", lambda _: f"page_title={words!r}", app_py, count=1)


def next_number(taken: Iterable[str]) -> int:
    """The next build's number: one past the highest folder that is a number."""
    numbers = [int(n) for n in taken if n.isdigit()]
    return max(numbers, default=0) + 1


def trimmed(taken: Iterable[str], keep: int) -> list[str]:
    """The builds a setting of `keep` takes away: all but the newest `keep` (numbers only)."""
    numbers = sorted((int(n) for n in taken if n.isdigit()), reverse=True)
    return [str(n) for n in numbers[max(keep, 1) :]]


@dataclass(frozen=True)
class CellCode:
    """A linked cell as the build kept it: its file (as the app's file links it), number, kind and code."""

    document: str
    cell: int
    kind: str
    name: str | None
    code: str

    def to_json(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "cell": self.cell,
            "kind": self.kind,
            "name": self.name,
            "code": self.code,
        }


def cells_text(cells: Sequence[CellCode]) -> str:
    return stable([c.to_json() for c in sorted(cells, key=lambda c: (c.document, c.cell))])


def read_cells(text: str) -> list[CellCode]:
    try:
        raw = json.loads(text)
    except ValueError as error:
        raise BuildError(f"{CELLS_FILE} is not readable: {error}") from None
    return [
        CellCode(
            str(c["document"]), int(c["cell"]), str(c.get("kind", "code")), c.get("name"), str(c["code"])
        )
        for c in raw
        if isinstance(c, dict) and "document" in c and "cell" in c and "code" in c
    ]


def changes(
    before: Sequence[CellCode] | None, now: Sequence[CellCode], pages_before: str | None, pages_now: str
) -> list[str]:
    """What changed since the build before, in words: each cell changed, added or gone (by its name or
    place), and the layout. The first build: "The first build"."""
    if before is None:
        return ["The first build."]
    said: list[str] = []
    old = {(c.document, c.cell): c for c in before}
    new = {(c.document, c.cell): c for c in now}

    def named(c: CellCode) -> str:
        file = re.split(r"[\\/]", c.document)[-1]
        return f"{c.name} ({file} @cell{c.cell})" if c.name else f"{file} @cell{c.cell}"

    for key, cell in new.items():
        if key not in old:
            said.append(f"{named(cell)} added.")
        elif old[key].code != cell.code:
            said.append(f"{named(cell)} changed.")
    for key, cell in old.items():
        if key not in new:
            said.append(f"{named(cell)} taken off.")
    if pages_before is not None and digest(pages_before) != digest(pages_now):
        said.append("The layout changed.")
    return said or ["Nothing changed."]


def widget_code(module: str) -> dict[str, str]:
    """Each widget's code in a build's sab_widgets.py (its `CODE['name'] = "..."` lines, read with ast: never
    run)."""
    import ast

    try:
        tree = ast.parse(module or "")
    except SyntaxError:
        return {}
    found: dict[str, str] = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "CODE"
            and isinstance(target.slice, ast.Constant)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found[str(target.slice.value)] = node.value.value
    return found


def _instances(canvas: Mapping[str, Any]) -> dict[str, tuple[str, str, dict[str, Any]]]:
    """Each widget instance by its id: its page, widget and values (containers are the layout's)."""
    out: dict[str, tuple[str, str, dict[str, Any]]] = {}

    def walk(children: Iterable[Mapping[str, Any]], page: str) -> None:
        for child in children:
            if child.get("kind") == "widget":
                out[str(child.get("id"))] = (page, str(child.get("widget")), dict(child.get("values") or {}))
            walk(child.get("children") or [], page)

    for page in canvas.get("pages") or []:
        walk(page.get("children") or [], str(page.get("name")))
    return out


def _places(canvas: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def walk(children: Iterable[Mapping[str, Any]]) -> None:
        for child in children:
            out[str(child.get("id"))] = (child.get("at"), child.get("show"), child.get("props"))
            walk(child.get("children") or [])

    for page in canvas.get("pages") or []:
        walk(page.get("children") or [])
    return out


def canvas_changes(
    before: str | None, now: str, widgets_before: str | None = None, widgets_now: str = ""
) -> list[str]:
    """What changed since the build before, in words, on the widget canvas (format 2): pages added or gone,
    each widget instance added, taken off, given other values or another widget, the layout, and each
    widget whose code changed in the library. The first build: "The first build"."""
    if before is None:
        return ["The first build."]
    try:
        old, new = json.loads(before), json.loads(now)
    except ValueError:
        return ["The canvas changed."] if digest(before) != digest(now) else ["Nothing changed."]
    if not isinstance(old, dict) or "format" not in old:
        return ["The first build on the Canvas (the build before is an app notebook's)."]
    said: list[str] = []
    pages_old = [str(p.get("name")) for p in old.get("pages") or []]
    pages_new = [str(p.get("name")) for p in new.get("pages") or []]
    said += [f"Page {p} added." for p in pages_new if p not in pages_old]
    said += [f"Page {p} taken off." for p in pages_old if p not in pages_new]
    was, now_ = _instances(old), _instances(new)
    for key, (page, widget, values) in now_.items():
        if key not in was:
            said.append(f"{widget} ({key}) added on {page}.")
        elif was[key][1] != widget:
            said.append(f"{key} is {widget} now (was {was[key][1]}).")
        elif was[key][2] != values:
            changed = sorted(k for k in {*values, *was[key][2]} if values.get(k) != was[key][2].get(k))
            said.append(f"{widget} ({key}): {', '.join(changed)} changed.")
    said += [
        f"{widget} ({key}) taken off {page}." for key, (page, widget, _) in was.items() if key not in now_
    ]
    if _places(old) != _places(new) or old.get("sizing") != new.get("sizing"):
        said.append("The layout changed.")
    if widgets_before is not None:
        code_old, code_new = widget_code(widgets_before), widget_code(widgets_now)
        said += [
            f"The widget {name}'s code changed."
            for name in sorted(code_new)
            if name in code_old and code_old[name] != code_new[name]
        ]
    return said or ["Nothing changed."]


def build_json(
    number: int,
    time: str,
    app: str,
    canvas: str,
    changed: Sequence[str],
    result: str,
    first_load_ms: float | None,
    sessions: Sequence[str] = (),
    error: str | None = None,
) -> str:
    """build.json's text."""
    data: dict[str, Any] = {
        "number": number,
        "time": time,
        "app": app,
        "canvas": digest(canvas),
        "changed": list(changed),
        "result": result,
        "first_load_ms": None if first_load_ms is None else round(first_load_ms),
        "sessions": sorted(sessions),
    }
    if error:
        data["error"] = error
    return stable(data)


def read_build(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError as error:
        raise BuildError(f"{BUILD_FILE} is not readable: {error}") from None
    if not isinstance(data, dict) or not isinstance(data.get("number"), int):
        raise BuildError(f"{BUILD_FILE} has no build number.")
    return data


def with_session(text: str, session: str) -> str:
    """build.json with an analyzer session's file added."""
    data = read_build(text)
    data["sessions"] = sorted({*data.get("sessions", []), session})
    return stable(data)


def with_result(text: str, result: str, first_load_ms: float | None, error: str | None = None) -> str:
    data = read_build(text)
    data["result"] = result
    data["first_load_ms"] = None if first_load_ms is None else round(first_load_ms)
    if error:
        data["error"] = error
    else:
        data.pop("error", None)
    return stable(data)


def compare(a: Mapping[str, str], b: Mapping[str, str]) -> list[dict[str, Any]]:
    """Two builds' code file by file: added, removed, changed or same, with each side's text and the
    unified diff's line counts (build.json and the analyzer sessions are not code: left out)."""
    out: list[dict[str, Any]] = []
    for name in sorted({*a, *b}):
        if name == BUILD_FILE or name.startswith(PERF_PREFIX):
            continue
        left, right = a.get(name), b.get(name)
        status = (
            "added"
            if left is None
            else "removed"
            if right is None
            else "same"
            if left == right
            else "changed"
        )
        added = removed = 0
        if status == "changed":
            for line in difflib.unified_diff(
                (left or "").splitlines(), (right or "").splitlines(), lineterm="", n=0
            ):
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    removed += 1
        out.append(
            {
                "file": name,
                "status": status,
                "before": left,
                "after": right,
                "added": added,
                "removed": removed,
            }
        )
    order = {"changed": 0, "added": 1, "removed": 2, "same": 3}
    return sorted(out, key=lambda f: (order[f["status"]], f["file"]))


def restore_plans(kept: Sequence[CellCode], now: Mapping[tuple[str, int], str]) -> list[dict[str, Any]]:
    """Restore: each kept cell whose code differs now, as a plan the window makes like typing (its whole
    code replaced; the editor's Undo takes it back)."""
    plans = []
    for cell in kept:
        before = now.get((cell.document, cell.cell))
        if before is None or before == cell.code:
            continue
        plans.append(
            {
                "document": cell.document,
                "cell": cell.cell,
                "before": before,
                "code": cell.code,
                "changed": True,
                "edits": [{"start": 0, "end": len(before), "text": cell.code}],
                "line": None,
                "handler": None,
                "do": "restore",
            }
        )
    return plans
