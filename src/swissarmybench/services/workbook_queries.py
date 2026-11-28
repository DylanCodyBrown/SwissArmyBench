"""Workbook queries: an Excel workbook's own Power Query edited as one linked .pq file and saved back (the
owner, 2026-11-28: ".m and .pq is more for editing powerbi files in place", then "I've changed my mind. I
don't want to edit power query in powerbi at all. I was the m and .pq features to be aimed at workbook
development"; asked which: "Excel's own Power Query"). domain/workbook_queries.py has the rules and the
format ([MS-QDEFF]); nothing here writes a Power BI file.

open_new  New file's maker for "Edit workbook queries…": the workbook's Section1.m as one new .pq file, its
          first line naming the workbook relative to the file. It lives where New file puts any file (the
          open project's scripts/, or the folder named), so the project's code stays in the project.
link      what a linked file's tab shows: its workbook's name, whether it is there, open in Excel, or
          changed on disk since the file was opened. Opening remembers the workbook's queries' hash.
preview   a save's dry run: each query changed, added, kept or the same; nothing is written.
save      the .pq written (when its text is sent), then ONLY the workbook's Data Mashup: never while Excel
          has it open, never over queries changed on disk since the file was opened (Reload or Keep mine:
          `force`), one backup copy before the first write. The agent's save into a workbook outside the
          open project waits for the user's Allow. A workbook with no Power Query yet: the save stops
          (WorkbookNeedsPowerQuery) and offers "Add Power Query to this workbook"; only `add: true`, the
          user's click or the agent's explicit argument, makes its first Data Mashup (the owner,
          2026-11-28: "Yea optional"). Never by itself, and the same lock, conflict, backup and Allow.
reload    the workbook's queries read again into the file (the conflict's Reload).

Run stays a preview (services/m_files.py): `table_path` gives it the linked workbook for
Excel.CurrentWorkbook().
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain import new_files, project_paths
from swissarmybench.domain import workbook_queries as rules
from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace


class Files(Protocol):
    """adapters/workbench.py's Documents."""

    def read(self, path: str) -> tuple[str, str, float]: ...

    def write(
        self, path: str, text: str, force: bool = False, make_folder: bool = False
    ) -> tuple[str, float]: ...

    def exists(self, path: str) -> bool: ...

    def workbooks(self) -> Any: ...


class Projects(Protocol):
    current: Any


class WorkbookConflict(Conflict):
    """The workbook's queries changed on disk since the file was opened: Reload, or Keep mine."""


class WorkbookLocked(Conflict):
    """Excel has the workbook open."""


class WorkbookNeedsPowerQuery(Conflict):
    """The workbook has no Power Query yet: the save stops and offers to add it (`add: true`)."""


class SectionRefused(ValueError):
    """The file's text cannot go into a workbook: one sentence and the file's line."""

    def __init__(self, message: str, line: int) -> None:
        super().__init__(message)
        self.line = line


def _name(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


class WorkbookQueries:
    def __init__(
        self,
        ws: Workspace,
        files: Files,
        projects: Projects,
        touched: Callable[[str, str], Awaitable[Any]],
        approvals: Approvals,
    ) -> None:
        self.ws = ws
        self._files = files
        self._projects = projects
        self._touched = touched
        self._approvals = approvals
        self._store = files.workbooks()
        # Each linked file's workbook as it was when the file was opened: the hash of its queries' text.
        self._opened: dict[str, str] = {}

    # ===== the linked file and its workbook =====

    def _project(self) -> str | None:
        current = self._projects.current
        return str(current.folder) if current is not None and current.folder else None

    def _text(self, body: Any) -> tuple[str, str]:
        if not isinstance(body, dict) or not isinstance(body.get("path"), str) or not body["path"].strip():
            raise ValueError('Send the linked file\'s "path" (and its unsaved "text").')
        path = str(body["path"]).strip()
        text = body.get("text")
        try:
            saved, full, _ = self._files.read(path)
        except FileNotFoundError as error:
            if not isinstance(text, str):
                raise NotFound(str(error)) from None
            full = path
            saved = ""
        return (text if isinstance(text, str) else saved), full

    def table_path(self, text: str, path: str | None) -> str | None:
        """The workbook a file's text is linked to, as a whole path (None: not linked, or not saved yet)."""
        named = rules.linked_to(text)
        return rules.workbook_path(path, named) if named and path else None

    def _workbook(self, text: str, path: str) -> str:
        workbook = self.table_path(text, path)
        if workbook is None:
            raise Refused(
                f"{_name(path)} is not linked to a workbook: its first line is `{rules.HEADER} <its file>`."
            )
        return workbook

    async def _read(self, workbook: str) -> tuple[bytes, rules.Read]:
        try:
            data = await asyncio.to_thread(self._store.read, workbook)
            return data, await asyncio.to_thread(rules.read, data, _name(workbook))
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except rules.Unreadable as error:
            raise Refused(str(error)) from None

    def _key(self, path: str) -> str:
        return project_paths.key(path)

    # ===== open: New file's maker =====

    async def open_new(self, body: dict[str, Any], who: str = "user") -> dict[str, Any]:
        """{name, folder, source, check}: the workbook at `source` opened as one new linked .pq file, named
        and placed as New file places any file. With `check`, only where it would go."""
        kind = new_files.type_of(rules.TYPE, (), True)
        folder = self._project()
        try:
            if folder:
                root = folder.replace("\\", "/").rstrip("/")
                relative = new_files.place(
                    kind,
                    body.get("name"),
                    body.get("folder"),
                    lambda inside: self._files.exists(f"{root}/{inside}"),
                )
                full = f"{root}/{relative}"
            else:
                full = new_files.loose_place(kind, body.get("name"), body.get("folder"), self._files.exists)
                relative = _name(full)
        except new_files.NameTaken as error:
            raise Conflict(str(error)) from None
        made = {"path": full, "relative": relative}
        if body.get("check"):
            return made
        source = body.get("source")
        if not isinstance(source, str) or not source.strip():
            raise Refused("Pick the Excel workbook whose queries to edit: an .xlsx or an .xlsm.")
        workbook = source.strip().replace("\\", "/")
        _, found = await self._read(workbook)
        text = rules.linked_text(rules.relative_to(full, workbook), found.text)
        full = (await asyncio.to_thread(self._files.write, full, text, False, True))[0]
        self._opened[self._key(full)] = found.stamp
        await self._touched(full, who)
        queries = len(rules.split(found.text).members)
        self.ws.audit.write(who, "workbook_queries_opened", relative, workbook=found.name, queries=queries)
        return made | {
            "path": full,
            "workbook": found.name,
            "queries": queries if found.part else 0,
            "starter": found.part is None,
        }

    # ===== what the tab shows =====

    async def link(self, body: Any) -> dict[str, Any]:
        """{path, text?}: {linked, workbook (its name), workbook_path, there, queries, open_in_excel,
        changed, why}. `why`: one sentence when the workbook cannot be read or saved into. The first look
        remembers the workbook's queries as they are now (what a later conflict compares)."""
        text, path = self._text(body)
        workbook = self.table_path(text, path)
        if workbook is None:
            return {"linked": False}
        answer: dict[str, Any] = {
            "linked": True, "workbook": _name(workbook), "workbook_path": workbook, "there": True,
            "queries": 0, "open_in_excel": False, "changed": False, "why": None, "can_add": False,
        }  # fmt: skip
        try:
            _, found = await self._read(workbook)
        except NotFound as error:
            return answer | {"there": False, "why": str(error)}
        except Refused as error:
            return answer | {"why": str(error)}
        was = self._opened.setdefault(self._key(path), found.stamp)
        answer["queries"] = len(rules.split(found.section).members) if found.part else 0
        answer["open_in_excel"] = await asyncio.to_thread(self._store.locked, workbook)
        answer["changed"] = was != found.stamp
        if found.part is None:
            answer["can_add"] = True
            answer["why"] = f"{found.name} has no Power Query yet."
        return answer

    # ===== preview and save =====

    def _plan(self, found: rules.Read, text: str, add: bool = False) -> rules.Plan:
        try:
            return rules.plan(found, text, add)
        except rules.SectionError as error:
            raise SectionRefused(str(error), error.line) from None
        except rules.NoPowerQuery as error:
            raise WorkbookNeedsPowerQuery(str(error)) from None
        except rules.Unreadable as error:
            raise Refused(str(error)) from None

    def _answer(self, found: rules.Read, planned: rules.Plan, workbook: str) -> dict[str, Any]:
        return {
            "workbook": found.name,
            "workbook_path": workbook,
            "writes": planned.writes,
            "changes": [c.to_json() for c in planned.changes],
            "changed": planned.count(rules.CHANGED),
            "added": planned.count(rules.ADDED),
            "kept": planned.count(rules.KEPT),
            "adds_power_query": bool(planned.adds),
            "new_parts": list(planned.adds),
        }

    async def preview(self, body: Any) -> dict[str, Any]:
        """{path, text?}: what a save would change, each query by name; nothing is written. `conflict`,
        `open_in_excel` and `needs_add` (the workbook has no Power Query yet: a save needs `add`) say what
        would stop the save."""
        text, path = self._text(body)
        workbook = self._workbook(text, path)
        _, found = await self._read(workbook)
        planned = self._plan(found, text, found.part is None)
        was = self._opened.get(self._key(path), found.stamp)
        counts = ", ".join(f"{planned.count(w)} {w}" for w in (rules.CHANGED, rules.ADDED, rules.KEPT))
        if planned.adds:
            words = (
                f"{found.name} has no Power Query yet. With add, a save would add it ({planned.adds[0]}, its "
                f"properties part and the two entries that name them) and write {counts}, connection only."
            )
        elif planned.writes:
            words = f"A save would write into {found.name}: {counts}."
        else:
            words = planned.words(found.name)
        return self._answer(found, planned, workbook) | {
            "written": False,
            "needs_add": bool(planned.adds),
            "words": words,
            "conflict": was != found.stamp,
            "open_in_excel": await asyncio.to_thread(self._store.locked, workbook),
        }

    async def save(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{path, text?, force?, add?}: the file saved (its `text`, when sent), then its queries written into
        its workbook. {workbook, written, changes, words, backup}. `add` true (exactly): Power Query added to
        a workbook that has none; without it that save stops with WorkbookNeedsPowerQuery."""
        text, path = self._text(body)
        workbook = self._workbook(text, path)
        if isinstance(body.get("text"), str):
            path = await self._save_file(path, text, who)
        data, found = await self._read(workbook)
        planned = self._plan(found, text, body.get("add") is True)
        key = self._key(path)
        answer = self._answer(found, planned, workbook) | {"written": False, "backup": None}
        if not planned.writes:
            self._opened[key] = found.stamp
            return answer | {"words": planned.words(found.name)}
        if await asyncio.to_thread(self._store.locked, workbook):
            raise WorkbookLocked(rules.locked_words(found.name))
        if not body.get("force") and self._opened.get(key, found.stamp) != found.stamp:
            raise WorkbookConflict(rules.conflict_words(found.name))
        project = self._project()
        inside = project is not None and project_paths.inside(workbook, project)
        if not inside:
            await self._approvals.allowed(
                who,
                subject=found.name,
                action=(
                    f"Add Power Query to {found.name}"
                    if planned.adds
                    else f"Save the queries into {found.name}"
                ),
                detail=f"{workbook} is outside the open project. " + planned.words(found.name),
                otherwise=f"{found.name} was not changed",
            )
        try:
            new = await asyncio.to_thread(rules.written, data, found, planned)
            again = await asyncio.to_thread(rules.read, new, found.name)  # what was made is read back first
        except rules.Unreadable as error:
            raise Refused(str(error)) from None
        if again.section != planned.section:
            raise Refused(f"{found.name} was not changed: the queries written did not read back the same.")
        backup = await asyncio.to_thread(self._store.backup, workbook, project if inside else None)
        await asyncio.to_thread(self._store.write, workbook, new)
        self._opened[key] = again.stamp
        self.ws.audit.write(
            who, "workbook_queries_saved", found.name,
            changed=answer["changed"], added=answer["added"], kept=answer["kept"],
            power_query_added=bool(planned.adds),
        )  # fmt: skip
        return answer | {"written": True, "backup": backup, "words": planned.words(found.name)}

    async def _save_file(self, path: str, text: str, who: str) -> str:
        try:
            same = self._files.read(path)[0] == text
        except FileNotFoundError:
            same = False
        if same:
            return path
        full = (await asyncio.to_thread(self._files.write, path, text))[0]
        await self._touched(full, who)
        return full

    async def reload(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{path}: the workbook's queries read again into the linked file (what was in it is replaced):
        {text, workbook, queries}."""
        text, path = self._text(body)
        workbook = self._workbook(text, path)
        _, found = await self._read(workbook)
        fresh = rules.linked_text(str(rules.linked_to(text)), found.text)
        full = await self._save_file(path, fresh, who)
        self._opened[self._key(full)] = found.stamp
        self.ws.audit.write(who, "workbook_queries_reloaded", _name(full), workbook=found.name)
        return {"path": full, "text": fresh, "workbook": found.name}
