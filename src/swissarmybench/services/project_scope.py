"""What belongs to the open project, and bringing things into it (the owner, 2026-11-16: "now objects are
project scoped any notebooks scripts or apps will have to be imported from another project"; rules in
domain/project_scope.py).

  documents   the open project's notebooks, scripts and apps (the Workbench's Notebooks, Scripts and Apps
              pages list them)
  sources     what another place offers to import: a project's folder, a loose notebook, script or app (an
              older project's own connections and blades among them)
  import      documents copied into the open project (a name it has gets the next free one); connections
              and blades into the library (Plans/library.plan.md: shared by every project; the same one
              skipped, a different one of that name kept as "<name> from <project>", and said). A
              connection's password is never copied: it comes from this computer's keyring, environment or
              vault, by the connection's name, and a connection with none here says "needs a password" with
              the fix
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.domain import code_tree
from swissarmybench.domain import project_scope as rules
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.library import saved_json
from swissarmybench.domain.sab_files import SabError
from swissarmybench.services.connections import ConnectionService
from swissarmybench.services.sab_projects import SabProjects
from swissarmybench.services.workspace import NotFound, Refused


class ScopeFiles(Protocol):
    """Project folders and loose files (adapters/sab_files.py)."""

    def full(self, path: str) -> str: ...

    def exists(self, path: str) -> bool: ...

    def is_folder(self, path: str) -> bool: ...

    def files(self, folder: str) -> list[tuple[str, int, float]]: ...

    def app_files(self, folder: str) -> list[tuple[str, int, float]]: ...

    def read_file(self, folder: str, relative: str) -> bytes: ...

    def read_loose(self, path: str) -> bytes: ...

    def write_into(self, folder: str, relative: str, body: bytes) -> str: ...


class Library(Protocol):
    """The library (services/library.py): blades from a project taken in."""

    def take(self, blades: list[Blade], project: str, who: str = "user") -> dict[str, Any]: ...


def _blade(raw: bytes) -> Blade | None:
    try:
        return saved_json(json.loads(raw.decode("utf-8-sig")))
    except (UnicodeDecodeError, ValueError):
        return None


class ProjectScope:
    def __init__(
        self,
        projects: SabProjects,
        files: ScopeFiles,
        library: Library,
        connections: ConnectionService,
        on_saved: Callable[[str], None] = lambda name: None,
    ) -> None:
        self._projects = projects
        self.ws = projects.ws
        self._files = files
        self._library = library
        self._connections = connections
        self._on_saved = on_saved  # an imported connection's catalog loads itself

    def _folder(self) -> str:
        current = self._projects.current
        if current is None:
            raise NotFound("No project is open: open or start one first.")
        return current.folder

    # ===== the open project's documents =====

    def documents(self, kind: Any = None) -> dict[str, Any]:
        """The open project's notebooks, scripts and apps ({"kind"?: one of them}), with whole paths."""
        current = self._projects.current
        if kind is not None and not isinstance(kind, str):
            raise ValueError("kind is notebook, script or app.")
        if current is None:
            rules.documents([], kind or None)  # the kind checked all the same
            return {"project": None, "documents": []}
        files = self._files.files(current.folder)
        listed = rules.documents(files, kind or None)
        # THE data notebook's role (its icon and word): data.ipynb; every other notebook is plain.
        roles = rules.notebook_roles(listed)
        return {
            "project": current.name,
            "folder": current.folder,
            "documents": [
                d
                | {"full": rules.inside(current.folder, d["path"])}
                | ({"role": roles[d["path"]]} if d["path"] in roles else {})
                for d in listed
            ],
        }

    # ===== the explorer of the Notebooks and Scripts pages (domain/code_tree.py) =====

    def tree(self, page: Any) -> dict[str, Any]:
        """The explorer's groups for a page: {"page": "scripts"} every .py of the open project by module, each
        with its outline; {"page": "notebooks"} its notebooks, the data notebook first. No project: none."""
        if page not in ("notebooks", "scripts"):
            raise ValueError("page is notebooks or scripts.")
        current = self._projects.current
        if current is None:
            return {"project": None, "page": page, "groups": []}
        files = [f[0].replace("\\", "/") for f in self._files.files(current.folder)]
        if page == "notebooks":
            groups = code_tree.notebook_tree(files)
        else:
            texts: list[tuple[str, str | None]] = []
            for relative in files:
                if not relative.endswith(".py") or not code_tree.listed(relative):
                    continue
                try:
                    body = self._files.read_file(current.folder, relative)
                    texts.append((relative, body[:2_000_000].decode("utf-8", "replace")))
                except OSError:
                    texts.append((relative, None))
            groups = code_tree.script_tree(texts, self.edited_by_hand())
        for group in groups:
            for item in group["files"]:
                item["full"] = rules.inside(current.folder, item["path"])
        return {"project": current.name, "folder": current.folder, "page": page, "groups": groups}

    HAND = ".sab/hand-edited.json"

    def edited_in(self, folder: str) -> set[str]:
        """A project's made files (data.py, pages/*.py) edited by hand: never overwritten silently."""
        try:
            found = json.loads(self._files.read_file(folder, self.HAND).decode("utf-8"))
        except (OSError, ValueError):
            return set()
        return {str(p) for p in found if isinstance(p, str)} if isinstance(found, list) else set()

    def edited_by_hand(self) -> list[str]:
        current = self._projects.current
        return sorted(self.edited_in(current.folder)) if current is not None else []

    def saw(self, path: str, who: str) -> None:
        """A save of the user's or the agent's (code_files.touched): a made file of the open project is edited
        by hand from now on (its tree's pencil; a regenerate asks)."""
        current = self._projects.current
        if current is None or who not in ("user", "agent"):
            return
        root = current.folder.replace("\\", "/").rstrip("/") + "/"
        full = path.replace("\\", "/")
        if not full.startswith(root):
            return
        relative = full[len(root) :]
        if not code_tree.made_from(relative):
            return
        edited = self.edited_in(current.folder)
        if relative in edited:
            return
        body = json.dumps(sorted(edited | {relative}), indent=1) + "\n"
        self._files.write_into(current.folder, self.HAND, body.encode("utf-8"))

    @staticmethod
    def outline(body: Any) -> dict[str, Any]:
        """A module's outline as typed ({"text"}): its classes, methods, functions and constants."""
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str):
            raise ValueError('Send {"text": "the module\'s text"}.')
        return code_tree.outline(text)

    # ===== what a place offers =====

    def _place(self, raw: Any) -> tuple[str, str]:
        """(kind, where): folder or file, and its whole path."""
        if raw == "computer":
            raise ValueError(
                "This computer's connections and blades are the library's: every project has them."
            )
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError('Send {"from": a project\'s folder, or a notebook, script or app}.')
        try:
            full = self._files.full(raw.strip())
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        if self._files.is_folder(full):
            return "folder", full
        if not self._files.exists(full):
            raise NotFound(f"{full} is not there.")
        if rules.kind_of(full):
            return "file", full
        raise ValueError("Import from a project's folder, or a notebook, script or app.")

    def _offered(
        self, kind: str, where: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, bytes]]:
        """A place's documents and saved blades, and each blade file's JSON (by its entry)."""
        if kind == "file":
            return (
                [{"path": where.replace("\\", "/").rsplit("/", 1)[-1], "kind": rules.kind_of(where)}],
                [],
                {},
            )
        documents = rules.documents(self._files.files(where))
        names = [n for n, _, _ in self._files.app_files(where) if rules.blade_entry(n)]
        raw = {n: self._files.read_file(where, n) for n in names}
        listed = [{"path": d["path"], "kind": d["kind"], "made": d["made"]} for d in documents]
        return listed, self._records(raw), raw

    @staticmethod
    def _records(raw: dict[str, bytes]) -> list[dict[str, Any]]:
        found = [r for entry, body in raw.items() if (r := rules.blade_record(entry, body)) is not None]
        return sorted(found, key=lambda r: str(r["name"]).casefold())

    async def sources(self, body: Any) -> dict[str, Any]:
        """What a place offers to import: {"from": a folder or a file}."""
        raw = body.get("from") if isinstance(body, dict) else None
        kind, where = self._place(raw)
        try:
            documents, blades, _ = await asyncio.to_thread(self._offered, kind, where)
        except SabError as error:
            raise ValueError(str(error)) from None
        return {
            "from": where,
            "kind": kind,
            "documents": documents,
            "connections": [_listed(b) for b in blades if b["connection"]],
            "blades": [_listed(b) for b in blades if not b["connection"]],
        }

    # ===== import =====

    async def import_(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Copy into the open project: {"from", "documents"?: [paths there], "connections"?: [names],
        "blades"?: [names]} (connections and blades go into the library). A loose notebook, script or app
        needs no list: it is the one imported."""
        if not isinstance(body, dict):
            raise ValueError('Send {"from": ..., "documents": [...], "connections": [...], "blades": [...]}.')
        current = self._projects.current
        kind, where = self._place(body.get("from"))
        try:
            wanted_documents = rules.chosen(body.get("documents"), "documents")
            wanted_connections = rules.chosen(body.get("connections"), "connections")
            wanted_blades = rules.chosen(body.get("blades"), "blades")
        except rules.ScopeError as error:
            raise ValueError(str(error)) from None
        if kind == "file" and wanted_documents is None:
            wanted_documents = []
            loose = True
        else:
            loose = False
        if not loose and not any((wanted_documents, wanted_connections, wanted_blades)):
            raise ValueError("Name what to import: documents, connections or blades.")
        # Documents go into the open project; connections and blades into the library (no project needed).
        folder = self._folder() if loose or wanted_documents else ""
        if folder and current is not None and current.read_only:
            raise Refused(current.read_only)
        try:
            done = await asyncio.to_thread(
                self._copy, folder, kind, where, loose, wanted_documents or [], wanted_connections or [],
                wanted_blades or [], who,
            )  # fmt: skip
        except (SabError, rules.ScopeError) as error:
            raise ValueError(str(error)) from None
        for name in done["connections"]:
            self._on_saved(name)
        if done["connections"] or done["blades"]:
            await self.ws.live.broadcast({"type": "blades_changed"})
        if done["documents"]:
            await self.ws.live.broadcast({"type": "project_documents_changed"})
        await self.ws.live.broadcast({"type": "project_changed"})
        self.ws.audit.write(
            who,
            "project_import",
            None,
            documents=len(done["documents"]),
            connections=len(done["connections"]),
            blades=len(done["blades"]),
        )
        needs = {}
        for name in done["connections"]:
            missing = self._connections.needs_passwords(name)
            if missing:
                needs[name] = rules.password_fix(name, missing)
        return done | {"needs_password": needs}

    def _copy(
        self,
        folder: str,
        kind: str,
        where: str,
        loose: bool,
        documents: list[str],
        connections: list[str],
        blades: list[str],
        who: str,
    ) -> dict[str, Any]:
        offered, records, raw = self._offered(kind, where)
        taken = [relative for relative, _, _ in self._files.files(folder)] if folder else []
        copied: list[dict[str, str]] = []
        if loose:
            name = offered[0]["path"]
            relative = rules.free_name(name, taken)
            full = self._files.write_into(folder, relative, self._files.read_loose(where))
            copied.append({"from": where, "path": relative, "full": full})
        else:
            paths = rules.pick([d["path"] for d in offered], documents, "document") if documents else []
            bodies = {p: self._files.read_file(where, p) for p in paths}
            for path in paths:
                relative = rules.free_name(path, taken)
                taken.append(relative)
                full = self._files.write_into(folder, relative, bodies[path])
                copied.append({"from": path, "path": relative, "full": full})
        # Connections and blades: into the library (the same one skipped, a different one kept under a
        # name of its own, never overwritten).
        added: dict[str, list[str]] = {"connections": [], "blades": []}
        skipped: list[str] = []
        renamed: dict[str, str] = {}
        source = rules.name_of(where)
        for group, wanted in (("connections", connections), ("blades", blades)):
            if not wanted:
                continue
            pool = [r for r in records if bool(r["connection"]) == (group == "connections")]
            names = rules.pick([str(r["name"]) for r in pool], wanted, group[:-1])
            files = {str(r["name"]): str(r["file"]) for r in pool}
            chosen = [b for n in names if (b := _blade(raw[files[n]])) is not None]
            took = self._library.take(chosen, source, who)
            kept = [*took["added"], *took["renamed"]]
            added[group] += [took["renamed"].get(n, n) for n in names if n in kept]
            skipped += took["skipped"]
            renamed |= took["renamed"]
        return {"documents": copied, **added, "skipped": skipped, "renamed": renamed}


def _listed(record: dict[str, Any]) -> dict[str, Any]:
    return {k: record[k] for k in ("name", "kind", "template", "connection", "description")}
