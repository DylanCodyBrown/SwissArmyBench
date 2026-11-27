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
from datetime import UTC, datetime
from typing import Any, Protocol

from swissarmybench.domain import changes as change_rules
from swissarmybench.domain import code_tree, new_files
from swissarmybench.domain import script_ide as rules
from swissarmybench.services.changes import raised
from swissarmybench.services.workspace import Conflict, Refused, Workspace

# An extension's own "new" path for a file type its project type adds: ({name, folder, check}, who) ->
# {path, relative, address?} (check: nothing written).
NewFileMaker = Callable[[dict[str, Any], str], Awaitable[dict[str, Any]]]


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

    def is_folder(self, path: str) -> bool: ...

    def move(self, source: str, target: str) -> None: ...

    def make_package(self, folder: str) -> str: ...

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
        library: Callable[[], tuple[str | None, list[str]]] = lambda: (None, []),
        tables: Callable[[], Awaitable[dict[str, Any]]] | None = None,
        trash: Callable[[str], str] | None = None,
        library_roots: Callable[[], tuple[str, ...]] = lambda: (),
    ) -> None:
        self.ws = ws
        self._code = code
        self._world = world
        self._ruff = ruff
        self._tree = tree  # the Scripts page's tree (services/project_scope.py tree("scripts"))
        self._touched = touched
        self._library = library  # the library's folder and its code files
        self._tables = tables  # the open tables as their read-only cells (services/table_cells.py listing)
        self._library_roots = library_roots  # Python's own folders: a library's source shown read-only
        self._trash = trash  # the system's trash (server/file_manager.py): Delete, the user's only
        # New file's project-type types (the open project's mode's `new_files`) and their makers, each an
        # extension's own "new" path (services/hooks.py new_file_makers); set by the composition root.
        self.extra_types: Callable[[], list[Any]] = list
        # The Workbench's own folder (where a loose file starts) and its maker: made the first time a file
        # goes in it.
        self.home: tuple[str, Callable[[], str]] | None = None
        self.makers: Mapping[str, NewFileMaker] = {}

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

    # ===== the tree: the project's code, the library's, what the app generates =====

    async def tree(self) -> dict[str, Any]:
        """The Scripts page's explorer (the owner, 2026-11-21: "expose the high level code of everything in
        the
        app for fine tuning"): Your scripts, Project code, the library's Connections, APIs, Key vaults (and
        Widgets), and Generated (each open table's transformations, read-only, with Fine-tune as a script)."""
        said = self._tree()
        root, paths = await asyncio.to_thread(self._library)
        groups = list(said.get("groups", [])) + code_tree.library_tree(root, paths)
        if self._tables is not None:
            listed = (await self._tables()).get("tables", [])
            groups.append(code_tree.generated_group(listed))
        return said | {"groups": groups, "library": root}

    async def fine_tune(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{table}: a new script in the project's scripts/ doing what the table's transformations do (its load
        and its steps as one DuckDB query), to fine-tune; its path (the page opens it)."""
        table = body.get("table") if isinstance(body, dict) else None
        if not isinstance(table, str) or not table:
            raise ValueError('Send {"table": "an open table\'s name"}.')
        if self._tables is None:
            raise Refused("No tables here.")
        listed = (await self._tables()).get("tables", [])
        found = next((t for t in listed if str(t.get("name")).casefold() == table.casefold()), None)
        if found is None:
            raise Refused(f"{table} is not open on the Tables page.")
        said = self._tree()
        folder = said.get("folder")
        if not folder:
            raise Refused("Open a project first: the script goes in its scripts/ folder.")
        taken = [f["path"] for g in said.get("groups", []) for f in g.get("files", [])]
        relative = code_tree.fine_tune_name(str(found["name"]), taken)
        full = f"{str(folder).rstrip('/')}/{relative}"
        head = f"# {found['name']}: its transformations as a script to fine-tune (from its steps).\n"
        self._code.write(full, head + str(found.get("loaded") or found.get("code") or ""))
        await self._touched(full, who)
        self.ws.audit.write(who, "script_fine_tune", full, table=str(found["name"]))
        return {"path": full, "table": found["name"]}

    # ===== go to definition, references =====

    async def definition(self, body: Any) -> dict[str, Any]:
        """Where the name at the cursor is defined (F12): [{path, line, column, module, in_project,
        builtin}]; with `source`, a library's file text too (read-only: library_file)."""
        text, line, column, path = self._where(body)
        _, folder = self._files()
        project = self._world.project(folder)
        found = await self._jedi(lambda: self._code.definition(text, line, column, path, project, folder))
        if body.get("source") and found and not found[0].get("in_project") and found[0].get("path"):
            found[0]["source"] = (await self.library_file({"path": found[0]["path"]}))["text"]
        return {"definitions": found}

    async def library_file(self, body: Any) -> dict[str, Any]:
        """{path}: a library's source, read-only (go to definition into an installed library: the owner's IDE
        shows it in a tab marked read-only). Only a .py or .pyi of Python's own folders or a site-packages."""
        path = body.get("path") if isinstance(body, dict) else None
        if not rules.library_file(path, self._library_roots()):
            raise Refused(
                "Only a library's own source opens here (a .py of the standard library or site-packages)."
            )
        try:
            text = await asyncio.to_thread(self._code.read, str(path))
        except (OSError, ValueError) as error:
            raise Refused(f"{path} could not be read: {error}") from None
        return {"path": path, "text": text, "read_only": True}

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

    def _changed(self, who: str, path: str, before: str | None, after: str | None) -> None:
        """The change log (services/changes.py): a script this page wrote, made or took away, by its
        functions and classes (their text fingerprinted), as a document's own Save says it."""
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        was = change_rules.document_shape("script", before) if before is not None else None
        now = change_rules.document_shape("script", after) if after is not None else None
        change = raised("script", name, was, now)
        if change:
            self.ws.audit.write(who, "changed", path, **change)

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
                self._changed(who, changed_path, before.get(changed_path), new_text)
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
                self._changed(who, changed_path, texts.get(changed_path), new_text)
        self.ws.audit.write(who, "script_replace", None, files=len(written), count=plan["count"])
        return {
            "count": plan["count"],
            "skipped": plan["skipped"],
            "preview": preview,
            "applied": True,
            "written": written,
        }

    # ===== the explorer's tree actions (2026-11-21): New package, Rename, Duplicate, Delete =====

    def _inside(self, path: Any, folder: str | None, what: str = "path") -> tuple[str, str]:
        """A path of the project's (whole, or inside it): (its whole path, its path inside the project)."""
        if not folder:
            raise Refused("Open a project first: its scripts are its own.")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"Send the {what}.")
        root = folder.replace("\\", "/").rstrip("/")
        given = path.replace("\\", "/")
        relative = given[len(root) + 1 :] if given.startswith(root + "/") else given.lstrip("/")
        parts = [p for p in relative.split("/") if p]
        if not parts or any(p in ("..", ".") for p in parts) or ":" in parts[0]:
            raise Refused(f"{path} is not inside the project.")
        relative = "/".join(parts)
        return f"{root}/{relative}", relative

    def _editable(self, relative: str, files: Mapping[str, Mapping[str, Any]], full: str) -> None:
        made = code_tree.made_from(relative)
        if made:
            raise Refused(f"{relative} is made from {made}: rename or delete its source instead.")
        listed = files.get(full)
        if listed is not None and listed.get("read_only"):
            raise Refused(f"{relative} is {rules.MADE_WHY}.")

    async def new_package(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{name, parent?}: a package in the project's scripts/ (or under `parent`, a folder of the
        project's): its folder and an empty __init__.py; the __init__.py's path (the page opens it)."""
        name = body.get("name") if isinstance(body, dict) else None
        if not rules.valid_file_name(name) or str(name).endswith(".py"):
            raise ValueError(
                f"{name!r} is not a package name: letters, digits and _, not starting with a digit."
            )
        _, folder = self._files()
        parent = body.get("parent") if isinstance(body.get("parent"), str) and body["parent"] else "scripts"
        full_parent, _ = self._inside(parent, folder, "parent")
        target = f"{full_parent}/{name}"
        if self._code.exists(target):
            raise Conflict(f"{name} is there already.")
        init = await asyncio.to_thread(self._code.make_package, target)
        await self._touched(init, who)
        self.ws.audit.write(who, "script_new_package", init)
        return {"path": init, "package": code_tree.module_name(self._inside(init, folder)[1])}

    # ===== New file (the owner, 2026-11-27): a type, a name, a folder; its starter written =====

    def _offer(self) -> tuple[list[Any], str | None, dict[str, dict[str, Any]]]:
        """(the open project's type's own file types, the project's folder, the tree's files)."""
        files, folder = self._files()
        return (list(self.extra_types()) if folder else []), folder, files

    def new_file_options(self) -> dict[str, Any]:
        """What every New file list and the one dialog draw: the types as data (the base's, then the open
        project's type's own; none open: only the ones made loose), the folders of the open project (none
        open: no folders; the dialog asks a folder of the disk instead)."""
        extra, folder, files = self._offer()
        inside = [self._inside(p, folder)[1] for p in files] if folder else []
        return {
            "project": bool(folder),
            "types": new_files.types(extra, bool(folder)),
            "default": new_files.DEFAULT_TYPE,
            "folders": new_files.folders(inside) if folder else [],
        }

    def _starter_options(self, kind: new_files.FileType, body: dict[str, Any], folder: str | None) -> Any:
        tables = sorted(self.ws.store.all(), key=lambda i: i.name.casefold())
        table = body.get("table") if isinstance(body.get("table"), str) and body["table"].strip() else None
        root = str(folder or "").replace("\\", "/").rstrip("/")
        return {
            "connection": body.get("connection"),
            "table": table or (tables[0].name if tables else None),
            "variant": new_files.variant_of(kind, body.get("variant")),
            "project": root.rsplit("/", 1)[-1],
            "date": datetime.now(UTC).date().isoformat(),
            "tables": [
                {"name": i.name, "columns": [{"name": c.name, "type": c.type} for c in i.columns]}
                for i in tables
            ],
        }

    def _loose_folder(self, folder: str, make: bool) -> None:
        """With no project open a new file's folder must be there; only the Workbench's own folder, where a
        loose file starts, is made (the first time a file goes in it)."""
        if self._code.is_folder(folder):
            return
        plain = folder.replace("\\", "/").rstrip("/")
        if self.home is not None and plain == self.home[0].replace("\\", "/").rstrip("/"):
            if make:
                self.home[1]()
            return
        raise Refused(f"There is no folder {folder}: pick one that is there.")

    async def new_file(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{type?, name, folder?, connection?, table?, variant?, check?}: a new file, named and written with
        its type's starter (domain/new_files.py) before any tab opens: in the open project (folder: inside
        it), else in any folder of the disk (folder: its whole path). No name, no file. A type the project's
        type adds is made by its extension's own "new" path. A name already taken is refused.
        {path, relative, type, kind, page, address?, made}; with `check`, only where it would go (or why
        not): nothing written."""
        if not isinstance(body, dict):
            raise ValueError('Send {"type": "sql", "name": "orders_by_month", "folder": "scripts"}.')
        extra, folder, _ = self._offer()
        kind = new_files.type_of(body.get("type"), extra, bool(folder))
        checking = bool(body.get("check"))
        new_files.variant_of(kind, body.get("variant"))
        if kind.maker:
            maker = self.makers.get(kind.maker)
            if maker is None:
                raise Refused(f"A {kind.label} cannot be made here: its extension is not on.")
            new_files.named(kind, body.get("name"))  # no name, no file: said the one way
            made = await maker(
                {"name": body.get("name"), "folder": body.get("folder"), "check": checking}, who
            )
            if not checking:
                self.ws.audit.write(who, "script_new_file", made.get("relative"), type=kind.id)
            return {"type": kind.id, "kind": kind.kind, "page": kind.page} | made | {"made": not checking}
        try:
            if folder:
                root = str(folder).replace("\\", "/").rstrip("/")
                relative = new_files.place(
                    kind,
                    body.get("name"),
                    body.get("folder"),
                    lambda inside: self._code.exists(f"{root}/{inside}"),
                )
                full = self._inside(relative, folder)[0]
            else:
                full = new_files.loose_place(kind, body.get("name"), body.get("folder"), self._code.exists)
                relative = full.rsplit("/", 1)[-1]
                self._loose_folder(full.rsplit("/", 1)[0], make=not checking)
        except new_files.NameTaken as error:
            raise Conflict(str(error)) from None
        made = {"path": full, "relative": relative, "type": kind.id, "kind": kind.kind, "page": kind.page}
        if checking:
            return made | {"made": False}  # the dialog's live check: where it would go, nothing written
        text = new_files.starter(kind, relative.rsplit("/", 1)[-1], self._starter_options(kind, body, folder))
        await asyncio.to_thread(self._code.write, full, text)
        await self._touched(full, who)
        if kind.id == "python":
            self._changed(who, full, None, text)
        self.ws.audit.write(who, "script_new_file", relative, type=kind.id)
        return made | {"made": True}

    async def move(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Rename (or move) a module or a package: {path, to, apply?}. `to` is the new name in the same folder
        (`loader.py`, a package's `clean`) or a path inside the project. Its imports in the project's modules
        follow, previewed as F2's rename is (a made file skipped with why); with apply: moved and written."""
        if not isinstance(body, dict):
            raise ValueError('Send {"path", "to", "apply"?}.')
        files, folder = self._files()
        full, relative = self._inside(body.get("path"), folder)
        self._editable(relative, files, full)
        if not self._code.exists(full):
            raise Refused(f"{relative} is not there.")
        to = body.get("to")
        if not isinstance(to, str) or not to.strip():
            raise ValueError("Send its new name: to.")
        is_file = relative.endswith(".py")
        if "/" not in to.strip("/"):
            last = to.strip()
            if is_file and not last.endswith(".py"):
                last += ".py"
            if not rules.valid_file_name(last) or (not is_file and last.endswith(".py")):
                raise ValueError(f"{to!r} is not a module's name: letters, digits and _, then .py.")
            target_relative = "/".join([*relative.split("/")[:-1], last])
        else:
            target_relative = self._inside(to, folder)[1]
        target_full = f"{str(folder).replace(chr(92), '/').rstrip('/')}/{target_relative}"
        if target_full == full:
            raise ValueError("That is its name already.")
        if self._code.exists(target_full):
            raise Conflict(f"{target_relative} is there already.")
        old_module, new_module = code_tree.module_name(relative), code_tree.module_name(target_relative)
        texts = self._texts(files)
        plan = rules.move_plan(texts, target_full, old_module, new_module, self._read_only(files))
        plan |= {"from": full, "to": target_full, "module": old_module, "new_module": new_module}
        if not body.get("apply"):
            return {k: v for k, v in plan.items() if k != "changes"} | {"applied": False}
        await asyncio.to_thread(self._code.move, full, target_full)
        written = []
        prefix = full if not is_file else None
        for changed_path, new_text in plan["changes"].items():
            path = changed_path
            if changed_path == full:
                path = target_full
            elif prefix and changed_path.startswith(prefix + "/"):
                path = target_full + changed_path[len(prefix) :]
            if self._code.write(path, new_text):
                written.append(path)
                await self._touched(path, who)
        await self._touched(target_full, who)
        await self.ws.live.broadcast({"type": "code_file_moved", "from": full, "to": target_full, "by": who})
        self.ws.audit.write(who, "script_move", relative, to=target_relative, files=len(written))
        return {k: v for k, v in plan.items() if k != "changes"} | {"applied": True, "written": written}

    async def duplicate(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{path}: a copy beside it (`load_copy.py`), its path (the page opens it)."""
        files, folder = self._files()
        full, relative = self._inside(body.get("path") if isinstance(body, dict) else None, folder)
        if not relative.endswith(".py"):
            raise ValueError("Duplicate takes a module (.py).")
        text = self._code.read(full)
        taken = {self._inside(p, folder)[1] for p in files} | {relative}
        copy_relative = rules.free_copy_name(relative, taken)
        while self._code.exists(f"{full[: -len(relative)]}{copy_relative}"):
            taken.add(copy_relative)
            copy_relative = rules.free_copy_name(relative, taken)
        copy_full = f"{full[: -len(relative)]}{copy_relative}"
        self._code.write(copy_full, text)
        await self._touched(copy_full, who)
        self._changed(who, copy_full, None, text)
        self.ws.audit.write(who, "script_duplicate", relative, to=copy_relative)
        return {"path": copy_full}

    async def delete(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{path}: a module or package to the system's trash, never deleted outright; the user's own (a
        project's Delete is too: the owner, 2026-11-17, "the agent cannot delete")."""
        if who == "agent":
            raise Refused("Delete is the user's own: the agent cannot delete (a module goes to the trash).")
        if self._trash is None:
            raise Refused("No trash here.")
        files, folder = self._files()
        full, relative = self._inside(body.get("path") if isinstance(body, dict) else None, folder)
        self._editable(relative, files, full)
        if not self._code.exists(full):
            raise Refused(f"{relative} is not there.")
        gone = self._code.read(full) if relative.endswith(".py") else None
        went = await asyncio.to_thread(self._trash, full)
        await self._touched(full, who)
        if gone is not None:
            self._changed(who, full, gone, None)
        await self.ws.live.broadcast({"type": "code_file_moved", "from": full, "to": None, "by": who})
        self.ws.audit.write(who, "script_delete", relative)
        return {"deleted": full, "to": went}

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
