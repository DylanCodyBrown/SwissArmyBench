"""Structures: nested data (JSON, YAML, XML, TOML) open as documents, as grids are tables
(domain/structures.py has the rules; the owner, 2026-11-17).

  open       a file (the file chooser), pasted text (its format found or chosen), New (an empty object
             or list), an API's response (services/apis.py), a Workbench kernel's value (sab.show_structure)
             or a value the agent sends; each a tab of the Structures page, kept in memory
  text       the text view's edit: the original replaced (only while there are no steps: with steps the
             text is the steps' result, read-only)
  steps      added, removed, undone, redone; replayed on the original, which is never changed until Save
  grid       a list of records at any path as a grid (a table in DuckDB), its origin the structure and path
  save       to its file, or Save as (JSON, YAML, XML, TOML) into the open project's structures/ folder
             (else the Workbench's own folder); nothing is written outside Save
  project    the project's structures/ files are its own: listed with the project (domain/sab_files.py),
             and the ones open when it was saved open again with it
  use        `sab.structure("gates")` answers the saved file's value; where code names it (the references)

Every action is the agent's too (cli/commands.py structures_*); the agent reads shapes and capped previews.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import connection_usage as usage
from swissarmybench.domain import datasets as dataset_rules
from swissarmybench.domain import structures as rules
from swissarmybench.domain.structures import Step, StructureError
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.workspace import NotFound, Workspace

FOLDER = "structures"  # inside a project's working folder
MAX_OPEN = 100
MAX_VALUE_CHARS = rules.MAX_CHARS


class Files(Protocol):
    def read(self, path: str) -> str: ...

    def write(self, path: str, text: str) -> None: ...

    def full(self, path: str) -> str: ...

    def join(self, folder: str, name: str) -> str: ...

    def listing(self, folder: str) -> list[tuple[str, int, float]]: ...

    def exists(self, path: str) -> bool: ...

    def inside(self, path: str, folder: str) -> bool: ...

    def relative(self, path: str, folder: str) -> str: ...


class Codecs(Protocol):
    """JSON, XML and TOML by the domain's rules; YAML by PyYAML (the missing-package answer without it)."""

    def parse(self, text: str, fmt: str) -> Any: ...

    def dump(self, value: Any, fmt: str) -> str: ...


class Datasets(Protocol):
    async def store_table(
        self,
        name: str,
        table: Any,
        source_kind: str,
        new_grid: bool,
        who: str,
        *,
        origin: Origin | None = ...,
    ) -> dict[str, Any]: ...


@dataclass
class Opened:
    id: str
    name: str
    format: str
    original: Any
    path: str | None = None
    origin: dict[str, Any] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    redo: list[Step] = field(default_factory=list)
    edited: bool = False  # the original changed since it was read (a paste, New, the text view)
    version: int = 0
    grids: list[tuple[str, str]] = field(default_factory=list)  # (table, path): made with Open as grid

    @property
    def dirty(self) -> bool:
        return self.edited or bool(self.steps)


class Structures:
    def __init__(
        self,
        ws: Workspace,
        files: Files,
        codecs: Codecs,
        datasets: Datasets,
        to_table: Callable[[list[dict[str, Any]]], Any],
        project_folder: Callable[[], str | None],
        default_folder: Callable[[], str],
        documents: Callable[[], Iterable[str]],
        read_document: Callable[[str], tuple[str, str, float]],
    ) -> None:
        self.ws = ws
        self._files = files
        self._codecs = codecs
        self._datasets = datasets
        self._to_table = to_table
        self._project_folder = project_folder
        self._default_folder = default_folder
        self._documents = documents  # SEAM: the documents references are looked for in (as connections')
        self._read_document = read_document
        self._open: dict[str, Opened] = {}
        # Run again: an API call's origin sent again (services/api_explorer.py sets it): (value, origin).
        self.rerun: Callable[[dict[str, Any], str], Awaitable[tuple[Any, dict[str, Any]]]] | None = None
        # A grid's own steps in words, for the lineage (services/grids.py, by table).
        self.grid_steps: Callable[[str], list[str]] = lambda table: []
        self._project: str | None = None  # the project folder last told (project_changed)
        self._lock = asyncio.Lock()
        # The Variables page (services/variables.py, set once built): a path's ${NAME} (12.7).
        self.variables: Any = None

    # ===== what is open =====

    def _get(self, sid: str) -> Opened:
        found = self._open.get(str(sid))
        if found is None:
            by_name = [s for s in self._open.values() if s.name.casefold() == str(sid).casefold()]
            if len(by_name) == 1:
                return by_name[0]
            raise NotFound(f"There is no open structure {sid}: structures_list names them.")
        return found

    def value(self, s: Opened) -> Any:
        return rules.apply(s.original, s.steps)

    def _summary(self, s: Opened) -> dict[str, Any]:
        try:
            result: Any = self.value(s)
            problem = None
        except StructureError as error:
            result, problem = None, str(error)
        return {
            "id": s.id,
            "name": s.name,
            "format": s.format,
            "path": s.path,
            "origin": s.origin,
            "steps": [step.to_json() | {"words": rules.describe(step)} for step in s.steps],
            "can_redo": bool(s.redo),
            "dirty": s.dirty,
            "version": s.version,
            "type": rules.kind(result),
            "count": len(result) if isinstance(result, dict | list) else None,
            "nodes": rules.count_nodes(result),
            "error": problem,
        }

    def listing(self) -> dict[str, Any]:
        """The open structures (tabs), and the project's structure files (cards)."""
        return {"open": [self._summary(s) for s in self._open.values()], "files": self.files()}

    def show(self, sid: str, with_text: bool = True) -> dict[str, Any]:
        """One open structure for the page: its result and, written in its format, its text."""
        s = self._get(sid)
        out = self._summary(s)
        if out["error"] is None:
            result = self.value(s)
            out["value"] = result
            if with_text:
                try:
                    out["text"] = self._codecs.dump(result, s.format)
                except StructureError as error:
                    out["text"], out["text_error"] = self._codecs.dump(result, "json"), str(error)
        return out

    def node(self, sid: str, path: str = "$") -> Any:
        """The value at `path` of an open structure's result."""
        value = self.value(self._get(sid))
        return value if path in ("", "$") else rules.get(value, path)

    def describe(self, sid: str, path: str = "$") -> dict[str, Any]:
        """What the agent reads: the shape (types, counts, keys), the record lists, and the node at `path`
        cut down like a grid's rows."""
        s = self._get(sid)
        out = self._summary(s)
        if out["error"] is None:
            node = rules.get(self.value(s), path) if path not in ("", "$") else self.value(s)
            out |= {
                "path": rules.format_path(rules.parse_path(path)),
                "shape": rules.shape(node),
                "record_lists": rules.record_lists(node),
                "preview": rules.preview(node),
            }
            out["file"] = s.path
        return out

    async def _changed(self, s: Opened | None, who: str, action: str, **details: Any) -> None:
        if s is not None:
            s.version += 1
        if action:
            self.ws.audit.write(who, action, None, **({"structure": s.name if s else None} | details))
        await self.ws.live.broadcast({"type": "structures_changed", "id": s.id if s else None, "who": who})

    def _add(
        self, name: str, fmt: str, value: Any, path: str | None, origin: dict[str, Any], edited: bool
    ) -> Opened:
        if len(self._open) >= MAX_OPEN:
            raise StructureError(f"{MAX_OPEN} structures are open: close one first.")
        s = Opened(secrets.token_hex(4), rules.check_name(name), fmt, value, path, origin, edited=edited)
        self._open[s.id] = s
        return s

    # ===== opening =====

    def _free_name(self, name: str) -> str:
        taken = {s.name.casefold() for s in self._open.values()}
        base, n, found = name, 2, name
        while found.casefold() in taken:
            found = f"{base} {n}"
            n += 1
        return found

    async def open_file(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"path"} a .json, .yaml/.yml, .xml or .toml file (the same file again: its tab)."""
        path = body.get("path") if isinstance(body, dict) else None
        if not isinstance(path, str) or not path.strip():
            raise StructureError('Send {"path": "the file"}.')
        if "${" in path and self.variables is not None:  # a path's ${NAME} (12.7), read here
            path = await self.variables.resolve(path, "the file's path")
        try:
            full = self._files.full(path.strip())
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        fmt = rules.format_of(full)
        if fmt is None:
            raise StructureError("A structure is a .json, .yaml, .yml, .xml or .toml file.")
        for s in self._open.values():
            if s.path == full:
                return self.show(s.id)
        text = await asyncio.to_thread(self._files.read, full)
        value = await asyncio.to_thread(self._codecs.parse, text, fmt)
        s = self._add(self._free_name(rules.name_of(full)), fmt, value, full, {"kind": "file"}, False)
        await self._changed(s, who, "structure_open")
        return self.show(s.id)

    async def paste(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"text", "format"? (found when not given), "name"?}."""
        body = body if isinstance(body, dict) else {}
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            raise StructureError('Send {"text": "the JSON, YAML, XML or TOML"}.')
        fmt = rules.check_format(body["format"]) if body.get("format") else rules.detect(text)
        value = await asyncio.to_thread(self._codecs.parse, text, fmt)
        name = self._free_name(rules.check_name(body.get("name") or "Pasted"))
        s = self._add(name, fmt, value, None, {"kind": "paste"}, True)
        await self._changed(s, who, "structure_paste")
        return self.show(s.id)

    async def new(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"kind": "object" | "list", "name"?, "format"? (json), "value"? (the agent's own JSON value),
        "origin"?}: an empty structure, or one holding the value given."""
        body = body if isinstance(body, dict) else {}
        fmt = rules.check_format(body.get("format") or "json")
        if "value" in body:
            value = body["value"]
            if len(str(value)) > MAX_VALUE_CHARS:
                raise StructureError("The value is too big (50 MB at most).")
        else:
            value = [] if body.get("kind") == "list" else {}
        said = body.get("origin") if isinstance(body.get("origin"), dict) else None
        origin = {k: str(v)[:200] for k, v in (said or {"kind": "new"}).items() if isinstance(v, str | int)}
        if origin.get("kind") not in ("new", "kernel", "agent", "api"):
            origin["kind"] = "agent" if who == "agent" else "new"
        name = self._free_name(rules.check_name(body.get("name") or "Untitled"))
        s = self._add(name, fmt, value, None, origin, True)
        await self._changed(s, who, "structure_new")
        return self.show(s.id)

    async def from_api(self, name: str, value: Any, origin: dict[str, Any], who: str) -> dict[str, Any]:
        """An API's response, opened as a new tab (the APIs page's Send): its origin is the call."""
        s = self._add(self._free_name(rules.check_name(name)), "json", value, None, dict(origin), True)
        await self._changed(s, who, "structure_from_api")
        return self._summary(s)

    async def run_again(self, sid: str, who: str = "user") -> dict[str, Any]:
        """An API call's structure: the same call sent again, its answer the new original, the steps kept."""
        s = self._get(sid)
        if s.origin.get("kind") != "api" or self.rerun is None:
            raise StructureError(f"{s.name} did not come from an API call: there is nothing to run again.")
        value, origin = await self.rerun(dict(s.origin), who)
        s.original, s.origin, s.edited = value, dict(origin), True
        await self._changed(s, who, "structure_run_again")
        return self.show(s.id)

    def lineage(self, sid: str) -> dict[str, Any]:
        """Where it came from (the call, with its inputs and body; the file), each step, each grid made
        from it with the grid's own steps: as the Workbench's lineage (nodes, edges, Mermaid)."""
        s = self._get(sid)
        grids = [(table, path, self.grid_steps(table)) for table, path in s.grids if self.ws.store.get(table)]
        origin = dict(s.origin) | ({"file": s.path} if s.path else {})
        cells = self.references(s.name)["references"]  # the cells that read it by its name
        graph = rules.lineage(s.name, origin, [rules.describe(step) for step in s.steps], grids, cells)
        return {"id": s.id, "name": s.name, "origin": s.origin, **graph.to_json()}

    async def close(self, sid: str, who: str = "user") -> dict[str, Any]:
        s = self._get(sid)
        del self._open[s.id]
        await self._changed(None, who, "structure_close", structure=s.name)
        return {"closed": s.id}

    async def rename(self, sid: str, body: Any, who: str = "user") -> dict[str, Any]:
        s = self._get(sid)
        to = body.get("name") if isinstance(body, dict) else None
        s.name = self._free_name(rules.check_name(to))
        await self._changed(s, who, "structure_rename")
        return self._summary(s)

    # ===== the text view =====

    async def set_text(self, sid: str, body: Any, who: str = "user") -> dict[str, Any]:
        """{"text", "format"?}: the text view's edit (only while there are no steps)."""
        s = self._get(sid)
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str):
            raise StructureError('Send {"text": "..."}.')
        if s.steps:
            raise StructureError("The text is the steps' result: remove the steps (or Save) to edit it.")
        fmt = rules.check_format(body.get("format") or s.format)
        s.original = await asyncio.to_thread(self._codecs.parse, text, fmt)
        s.format, s.edited = fmt, True
        await self._changed(s, who, "")
        return self._summary(s)

    async def set_format(self, sid: str, body: Any, who: str = "user") -> dict[str, Any]:
        """{"format"}: the text view written in another format (Save writes that format)."""
        s = self._get(sid)
        s.format = rules.check_format(body.get("format") if isinstance(body, dict) else None)
        await self._changed(s, who, "")
        return self.show(s.id)

    # ===== steps =====

    async def add_step(self, sid: str, body: Any, who: str = "user") -> dict[str, Any]:
        """{"op", "path", ...} (domain/structures.py check_step): checked against the result first."""
        s = self._get(sid)
        if len(s.steps) >= rules.MAX_STEPS:
            raise StructureError(f"A structure has {rules.MAX_STEPS} steps at most.")
        raw = body.get("step") if isinstance(body, dict) and isinstance(body.get("step"), dict) else body
        step = rules.check_step(raw)
        rules.apply(s.original, [*s.steps, step])  # refused here when it cannot apply
        s.steps.append(step)
        s.redo.clear()
        await self._changed(s, who, "structure_step", step=step.op)
        return self.show(s.id)

    async def remove_step(self, sid: str, body: Any, who: str = "user") -> dict[str, Any]:
        """{"index"} (from 0; the last when not given): the steps after it stay when they still apply."""
        s = self._get(sid)
        if not s.steps:
            raise StructureError("There are no steps.")
        index = body.get("index") if isinstance(body, dict) else None
        at = len(s.steps) - 1 if index is None else index
        if isinstance(at, bool) or not isinstance(at, int) or not 0 <= at < len(s.steps):
            raise StructureError(f"index is 0 to {len(s.steps) - 1}.")
        rest = s.steps[:at] + s.steps[at + 1 :]
        rules.apply(s.original, rest)
        removed = s.steps[at]
        s.steps = rest
        s.redo = [removed] if at == len(rest) else []
        await self._changed(s, who, "structure_step_removed", step=removed.op)
        return self.show(s.id)

    async def undo(self, sid: str, who: str = "user") -> dict[str, Any]:
        s = self._get(sid)
        if not s.steps:
            raise StructureError("There is nothing to undo.")
        s.redo.append(s.steps.pop())
        await self._changed(s, who, "structure_undo")
        return self.show(s.id)

    async def redo(self, sid: str, who: str = "user") -> dict[str, Any]:
        s = self._get(sid)
        if not s.redo:
            raise StructureError("There is nothing to redo.")
        step = s.redo.pop()
        rules.apply(s.original, [*s.steps, step])
        s.steps.append(step)
        await self._changed(s, who, "structure_redo")
        return self.show(s.id)

    # ===== Open as grid =====

    async def open_as_grid(self, sid: str, body: Any, who: str = "user") -> dict[str, Any]:
        """{"path"? ($), "name"?}: the list of records there as a grid; its origin is this structure."""
        s = self._get(sid)
        body = body if isinstance(body, dict) else {}
        path = rules.format_path(rules.parse_path(body.get("path") or "$"))
        node = rules.get(self.value(s), path) if path != "$" else self.value(s)
        rows = rules.records(node, path)
        table = await asyncio.to_thread(self._to_table, rows)
        last = next((p for p in reversed(rules.parse_path(path)) if isinstance(p, str)), None)
        name = body.get("name") or _table_name(f"{s.name}_{last}" if last else s.name)
        dataset_rules.validate_name(str(name))
        code = f"sab.structure_table({s.name!r}, {path!r})" if s.path else None
        origin = Origin("structure", path=s.path, filename=s.name, code=code, sql=path)
        answer = await self._datasets.store_table(str(name), table, "structure", True, who, origin=origin)
        s.grids = [g for g in s.grids if g[0] != str(name)] + [(str(name), path)]
        self.ws.audit.write(who, "structure_to_grid", str(name), rows=len(rows), structure=s.name)
        return answer | {"rows": len(rows), "path": path}

    # ===== saving =====

    def folder(self) -> str:
        """Where Save as writes: the open project's structures/ folder, else the Workbench's own folder."""
        project = self._project_folder()
        return self._files.join(project, FOLDER) if project else self._default_folder()

    async def _write(self, s: Opened, path: str, fmt: str) -> None:
        text = await asyncio.to_thread(self._codecs.dump, self.value(s), fmt)
        await asyncio.to_thread(self._files.write, path, text)

    async def save(self, sid: str, who: str = "user") -> dict[str, Any]:
        """To its own file, in its format; the steps become the original (the file is the result)."""
        s = self._get(sid)
        if not s.path:
            raise StructureError(f"{s.name} has no file yet: Save as names one.")
        fmt = rules.format_of(s.path) or s.format
        await self._write(s, s.path, fmt)
        self._saved(s, s.path, fmt)
        await self._changed(s, who, "structure_save")
        return self._summary(s)

    def _saved(self, s: Opened, path: str, fmt: str) -> None:
        s.original = self.value(s)
        s.steps, s.redo, s.edited = [], [], False
        s.path, s.format = path, fmt
        s.name = (
            rules.name_of(path)
            if not any(
                o.name.casefold() == rules.name_of(path).casefold() and o is not s
                for o in self._open.values()
            )
            else s.name
        )

    async def save_as(self, sid: str, body: Any, who: str = "user") -> dict[str, Any]:
        """{"name"?, "format"?, "folder"? | "path"?}: written there (the project's structures/ folder by
        default). TOML that cannot hold the result (a null, a list at the top) says so: save as JSON or
        YAML."""
        s = self._get(sid)
        body = body if isinstance(body, dict) else {}
        fmt = rules.check_format(body.get("format") or s.format)
        if isinstance(body.get("path"), str) and body["path"].strip():
            path = body["path"].strip()
            if rules.format_of(path) is None:
                path += rules.SUFFIX_OF[fmt]
            fmt = rules.format_of(path) or fmt
        else:
            folder = str(body.get("folder") or self.folder())
            path = self._files.join(folder, rules.file_name(str(body.get("name") or s.name), fmt))
        await self._write(s, path, fmt)
        self._saved(s, self._files.full(path), fmt)
        await self._changed(s, who, "structure_save_as", format=fmt)
        return self._summary(s) | {"written": s.path}

    # ===== the project's own =====

    def files(self) -> list[dict[str, Any]]:
        """The open project's structure files (with none open, the Workbench folder's structures/ ones):
        name, format, size, and where code uses each."""
        project = self._project_folder()
        folder = (
            self._files.join(project, FOLDER) if project else self._files.join(self._default_folder(), FOLDER)
        )
        found = []
        for name, size, modified in self._files.listing(folder):
            fmt = rules.format_of(name)
            if fmt is None:
                continue
            path = self._files.join(folder, name)
            opened = next((s for s in self._open.values() if s.path == self._files.full(path)), None)
            found.append(
                {
                    "name": rules.name_of(name),
                    "file": name,
                    "path": path,
                    "format": fmt,
                    "size": size,
                    "modified": modified,
                    "open": opened.id if opened else None,
                    "steps": len(opened.steps) if opened else 0,
                }
            )
        return found

    def open_paths(self) -> list[str]:
        """The open structures inside the project, relative to it (project.json keeps them)."""
        project = self._project_folder()
        if not project:
            return []
        return [
            self._files.relative(s.path, project)
            for s in self._open.values()
            if s.path and self._files.inside(s.path, project)
        ]

    async def project_changed(self, folder: str | None, extra: Mapping[str, Any] | None = None) -> None:
        """A project opened (or closed): the structures of the one before close; the ones open when this
        one was saved open again."""
        before, self._project = self._project, folder
        if before and before != folder:
            for s in list(self._open.values()):
                if s.path and self._files.inside(s.path, before):
                    del self._open[s.id]  # the project's own: they go with it
        if folder and extra:
            said = extra.get("structures") if isinstance(extra.get("structures"), dict) else {}
            for relative in (said or {}).get("open") or []:
                if not isinstance(relative, str) or ".." in relative.replace("\\", "/").split("/"):
                    continue
                path = self._files.join(folder, relative)
                if self._files.exists(path):
                    try:
                        await self.open_file({"path": path}, "app")
                    except (StructureError, NotFound, ValueError):
                        continue  # a file edited into something else: the project opens without it
        await self.ws.live.broadcast({"type": "structures_changed", "id": None, "who": "app"})

    # ===== sab.structure("gates") =====

    def _file_of(self, name: str) -> str:
        wanted = rules.name_of(name).casefold()
        for s in self._open.values():
            if s.path and s.name.casefold() == wanted:
                return s.path
        for f in self.files():
            if f["name"].casefold() == wanted or f["file"].casefold() == name.casefold():
                return str(f["path"])
        raise NotFound(f"There is no saved structure {name}: save it from the Structures page first.")

    async def saved(self, name: str, path: str = "$") -> dict[str, Any]:
        """A saved structure's value (its file, as saved: never the unsaved steps), or the node at `path`."""
        file = self._file_of(name)
        fmt = rules.format_of(file) or "json"
        value = await asyncio.to_thread(
            self._codecs.parse, await asyncio.to_thread(self._files.read, file), fmt
        )
        if path not in ("", "$"):
            value = rules.get(value, path)
        return {"name": rules.name_of(file), "format": fmt, "path": file, "value": value}

    def references(self, name: str) -> dict[str, Any]:
        """Where the user's notebooks and scripts call sab.structure("<name>")."""
        found: list[dict[str, Any]] = []
        for path in self._documents():
            try:
                text, full, _ = self._read_document(path)
            except (OSError, ValueError, LookupError):
                continue
            title = full.replace("\\", "/").rsplit("/", 1)[-1]
            try:
                refs = usage.document_references(full, title, text, name, calls=rules.CALLS)
            except ValueError:
                continue
            found += [r.to_json() for r in refs]
        return {"name": name, "references": found[: usage.MAX_REFERENCES]}


def _table_name(text: str) -> str:
    out = "".join(c if c.isalnum() or c in "_-" else "_" for c in text).strip("_")[:64]
    return out or "structure"
