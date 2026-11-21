"""The Scripts page as a Python IDE (the owner, 2026-11-17: "this is the IDE workbench for all the scripts
it should
have everything a python ide needs to develop including code completion for everything in the app already").

Completion, signatures, hovers and the lint stay services/intellisense.py's (one intelligence, never a
second);
this adds what an IDE needs across the project's modules: go to definition (into another module: its file;
into
a library: read-only), find all references, rename a symbol across the project's modules (a preview of each
change; a made or read-only file is never written: said instead), search and replace across the scripts, and
Format document (Ruff's, in the document's own Python; none said when it is not there). Every write is said
with
the file_changed notice (services/code_files.py), so every window follows. The agent does the same (golden
rule).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import script_ide as rules
from swissarmybench.services.workspace import Refused, Workspace


class Code(Protocol):
    def definition(
        self, text: str, line: int, column: int, path: str | None, project: Any, root: str | None
    ) -> list[dict[str, Any]]: ...

    def references(
        self, text: str, line: int, column: int, path: str | None, project: Any, root: str | None
    ) -> list[dict[str, Any]]: ...

    def rename(
        self, text: str, line: int, column: int, path: str | None, project: Any, new_name: str
    ) -> dict[str, str]: ...

    def read(self, path: str) -> str: ...

    def write(self, path: str, text: str) -> bool: ...

    def exists(self, path: str) -> bool: ...

    def format(self, text: str, ruff: str, folder: str | None) -> str | None: ...


class World(Protocol):
    def project(self, folder: str | None, extra: tuple[str, ...] = ()) -> Any: ...


class Ruff(Protocol):
    def ruff_command(self, python: str | None) -> str | None: ...


def _int(body: Mapping[str, Any], key: str) -> int:
    value = body.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{key} is a number from 1.")
    return value


class ScriptIde:
    def __init__(
        self,
        ws: Workspace,
        code: Code,
        world: World,
        ruff: Ruff,
        *,
        tree: Callable[[], dict[str, Any]],
        touched: Callable[[str, str], Awaitable[Any]],
    ) -> None:
        self.ws = ws
        self._code = code
        self._world = world
        self._ruff = ruff
        self._tree = tree  # the Scripts page's tree (services/project_scope.py tree("scripts"))
        self._touched = touched

    # ===== the project's scripts =====

    def _files(self) -> tuple[dict[str, dict[str, Any]], str | None]:
        """Every listed .py of the tree by its whole path, and the project's folder."""
        said = self._tree()
        files = {f["full"]: f for g in said.get("groups", []) for f in g.get("files", []) if f.get("full")}
        return files, said.get("folder")

    def _texts(self, files: Mapping[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for path in files:
            try:
                out[path] = self._code.read(path)
            except (OSError, ValueError):
                continue
        return out

    def _read_only(self, files: Mapping[str, Mapping[str, Any]]) -> set[str]:
        return {p for p, f in files.items() if f.get("read_only")}

    def _where(self, body: Any) -> tuple[str, int, int, str | None]:
        if not isinstance(body, dict) or not isinstance(body.get("text"), str):
            raise ValueError('Send {"text", "line", "column", "path"?}.')
        path = body.get("path") if isinstance(body.get("path"), str) else None
        return body["text"], _int(body, "line"), _int(body, "column"), path

    async def _jedi(self, job: Callable[[], Any]) -> Any:
        return await asyncio.to_thread(job)

    # ===== go to definition, references =====

    async def definition(self, body: Any) -> dict[str, Any]:
        """Where the name at the cursor is defined (F12): [{path, line, column, module, in_project,
        builtin}]."""
        text, line, column, path = self._where(body)
        _, folder = self._files()
        project = self._world.project(folder)
        found = await self._jedi(lambda: self._code.definition(text, line, column, path, project, folder))
        return {"definitions": found}

    async def references(self, body: Any) -> dict[str, Any]:
        """Every use of the name at the cursor across the project (Shift+F12), with each line's text."""
        text, line, column, path = self._where(body)
        _, folder = self._files()
        project = self._world.project(folder)
        found = await self._jedi(lambda: self._code.references(text, line, column, path, project, folder))
        for ref in found:
            try:
                lines = (text if ref["path"] == path else self._code.read(ref["path"])).split("\n")
                ref["text"] = lines[ref["line"] - 1].strip() if 0 < ref["line"] <= len(lines) else ""
            except (OSError, ValueError, TypeError):
                ref["text"] = ""
        return {"references": found}

    # ===== rename =====

    async def rename(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Rename the symbol at the cursor across the project's modules (F2): {text, line, column, path, to,
        apply?}. Without apply: the plan (each change previewed, what it skips and why). With it: written."""
        text, line, column, path = self._where(body)
        to = body.get("to")
        if not rules.valid_identifier(to):
            raise ValueError(f"{to!r} is not a Python name.")
        files, folder = self._files()
        project = self._world.project(folder)
        try:
            changed = await self._jedi(lambda: self._code.rename(text, line, column, path, project, str(to)))
        except Exception as error:  # Jedi's own words: nothing to rename there
            raise Refused(f"Nothing to rename there: {error}") from None
        outside = sorted(p for p in changed if p not in files and p != path)
        before = self._texts({p: None for p in changed if p != path}) | ({path: text} if path else {})
        read_only = self._read_only(files) | set(outside)
        plan = rules.rename_plan(changed, before, read_only)
        for skip in plan["skipped"]:
            if skip["path"] in outside:
                skip["why"] = "not one of the project's scripts"
        if not body.get("apply"):
            return plan | {"applied": False}
        written = []
        for changed_path, new_text in plan["changes"].items():
            if changed_path == path and body.get("unsaved"):
                continue  # the page puts the open document's change in its editor (unsaved)
            if self._code.write(changed_path, new_text):
                written.append(changed_path)
                await self._touched(changed_path, who)
        self.ws.audit.write(who, "script_rename", path, to=str(to), files=len(written))
        return plan | {"applied": True, "written": written}

    # ===== search and replace =====

    def search(self, body: Any) -> dict[str, Any]:
        """{query, regex?, case?, word?}: every match across the project's scripts, by file."""
        if not isinstance(body, dict):
            raise ValueError('Send {"query", "regex"?, "case"?, "word"?}.')
        files, _ = self._files()
        return rules.search(
            self._texts(files),
            body.get("query"),
            bool(body.get("regex")),
            bool(body.get("case")),
            bool(body.get("word")),
        )

    async def replace(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{query, to, regex?, case?, word?, apply?}: the plan (each file's count, the made ones skipped), or
        applied (written, each file said)."""
        if not isinstance(body, dict):
            raise ValueError('Send {"query", "to", "apply"?}.')
        files, _ = self._files()
        texts = self._texts(files)
        plan = rules.replace(
            texts,
            body.get("query"),
            body.get("to"),
            bool(body.get("regex")),
            bool(body.get("case")),
            bool(body.get("word")),
            self._read_only(files),
        )
        preview = [
            {"path": p, "lines": rules.rename_plan({p: t}, texts)["preview"][0]["lines"]}
            for p, t in plan["changes"].items()
        ]
        if not body.get("apply"):
            return {"count": plan["count"], "skipped": plan["skipped"], "preview": preview, "applied": False}
        written = []
        for changed_path, new_text in plan["changes"].items():
            if self._code.write(changed_path, new_text):
                written.append(changed_path)
                await self._touched(changed_path, who)
        self.ws.audit.write(who, "script_replace", None, files=len(written), count=plan["count"])
        return {
            "count": plan["count"],
            "skipped": plan["skipped"],
            "preview": preview,
            "applied": True,
            "written": written,
        }

    # ===== format =====

    async def format(self, body: Any) -> dict[str, Any]:
        """{text, python?}: Ruff's format of the text in the document's own Python; {"formatted": false,
        "why"} when Ruff is not there (the missing-package prompt offers it for that Python, never the
        app's)."""
        if not isinstance(body, dict) or not isinstance(body.get("text"), str):
            raise ValueError('Send {"text", "python"?}.')
        python = body.get("python") if isinstance(body.get("python"), str) else None
        ruff = await asyncio.to_thread(self._ruff.ruff_command, python)
        if ruff is None:
            return {
                "formatted": False,
                "why": "Format needs Ruff in this script's Python.",
                "missing": {"feature": "Format document", "packages": ["ruff"], "python": python or "app"},
            }
        _, folder = self._files()
        text = await asyncio.to_thread(self._code.format, body["text"], ruff, folder)
        if text is None:
            return {"formatted": False, "why": "Ruff could not format it: fix the syntax error first."}
        return {"formatted": True, "text": text, "changed": text != body["text"]}
