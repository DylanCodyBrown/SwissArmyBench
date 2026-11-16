"""What belongs to the open project, and bringing things into it (the owner, 2026-11-16: "now objects are
project scoped any notebooks scripts or apps will have to be imported from another project"; rules in
domain/project_scope.py).

  documents   the open project's notebooks, scripts and apps (the Workbench's Notebooks, Scripts and Apps
              pages list them)
  sources     what another place offers to import: a .sab, a project's folder, a loose notebook, script or
              app, or "computer" (this computer's saved connections and blades, the ones saved before
              projects held their own)
  import      copies into the open project: documents (a name it has gets the next free one), connections
              and blades (a name it has is skipped, and said). A connection's password is never copied:
              it comes from this computer's keyring, environment or vault, by the connection's name, and a
              connection with none here says "needs a password" with the fix
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.domain import project_scope as rules
from swissarmybench.domain.sab_files import SUFFIX, SabError
from swissarmybench.services.connections import ConnectionService
from swissarmybench.services.sab_projects import SabProjects
from swissarmybench.services.workspace import NotFound, Refused

COMPUTER: str = "computer"


class ScopeFiles(Protocol):
    """The .sab files and working folders (adapters/sab_files.py)."""

    def full(self, path: str) -> str: ...

    def exists(self, path: str) -> bool: ...

    def is_folder(self, path: str) -> bool: ...

    def files(self, folder: str) -> list[tuple[str, int, float]]: ...

    def app_files(self, folder: str) -> list[tuple[str, int, float]]: ...

    def read_file(self, folder: str, relative: str) -> bytes: ...

    def entry_names(self, path: str) -> list[str]: ...

    def read_entries(self, path: str, names: list[str]) -> dict[str, bytes]: ...

    def read_loose(self, path: str) -> bytes: ...

    def write_into(self, folder: str, relative: str, body: bytes) -> str: ...


class ComputerBlades(Protocol):
    """This computer's saved connections and blades (adapters/blades.py), and a blade's file name."""

    def saved_files(self) -> list[tuple[str, bytes]]: ...

    def file_name(self, name: str) -> str: ...


class ProjectScope:
    def __init__(
        self,
        projects: SabProjects,
        files: ScopeFiles,
        computer: ComputerBlades,
        connections: ConnectionService,
        on_saved: Callable[[str], None] = lambda name: None,
    ) -> None:
        self._projects = projects
        self.ws = projects.ws
        self._files = files
        self._computer = computer
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
        listed = rules.documents(self._files.files(current.folder), kind or None)
        return {
            "project": current.name,
            "folder": current.folder,
            "documents": [d | {"full": rules.inside(current.folder, d["path"])} for d in listed],
        }

    # ===== what a place offers =====

    def _place(self, raw: Any) -> tuple[str, str]:
        """(kind, where): computer, sab, folder or file, and its whole path."""
        if raw == COMPUTER:
            return COMPUTER, COMPUTER
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(
                'Send {"from": a .sab, a project\'s folder, a notebook, script or app, or "computer"}.'
            )
        try:
            full = self._files.full(raw.strip())
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        if self._files.is_folder(full):
            return "folder", full
        if not self._files.exists(full):
            raise NotFound(f"{full} is not there.")
        if full.lower().endswith(SUFFIX):
            return "sab", full
        if rules.kind_of(full):
            return "file", full
        raise ValueError("Import from a .sab, a project's folder, or a notebook, script or app.")

    def _offered(
        self, kind: str, where: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, bytes]]:
        """A place's documents and saved blades, and each blade file's JSON (by its entry)."""
        if kind == COMPUTER:
            raw = {f"{rules.BLADES}/{name}": body for name, body in self._computer.saved_files()}
            return [], self._records(raw), raw
        if kind == "file":
            return (
                [{"path": where.replace("\\", "/").rsplit("/", 1)[-1], "kind": rules.kind_of(where)}],
                [],
                {},
            )
        if kind == "folder":
            documents = rules.documents(self._files.files(where))
            names = [n for n, _, _ in self._files.app_files(where) if rules.blade_entry(n)]
            raw = {n: self._files.read_file(where, n) for n in names}
        else:
            entries = self._files.entry_names(where)
            documents = rules.documents((n, 0, 0.0) for n in entries)
            raw = self._files.read_entries(where, [n for n in entries if rules.blade_entry(n)])
        listed = [{"path": d["path"], "kind": d["kind"], "made": d["made"]} for d in documents]
        return listed, self._records(raw), raw

    @staticmethod
    def _records(raw: dict[str, bytes]) -> list[dict[str, Any]]:
        found = [r for entry, body in raw.items() if (r := rules.blade_record(entry, body)) is not None]
        return sorted(found, key=lambda r: str(r["name"]).casefold())

    async def sources(self, body: Any) -> dict[str, Any]:
        """What a place offers to import: {"from": a .sab, a folder, a file, or "computer"}."""
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
        "blades"?: [names]}. A loose notebook, script or app needs no list: it is the one imported."""
        if not isinstance(body, dict):
            raise ValueError('Send {"from": ..., "documents": [...], "connections": [...], "blades": [...]}.')
        folder = self._folder()
        current = self._projects.current
        if current is not None and current.read_only:
            raise Refused(current.read_only)
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
        try:
            done = await asyncio.to_thread(
                self._copy, folder, kind, where, loose, wanted_documents or [], wanted_connections or [],
                wanted_blades or [],
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
    ) -> dict[str, Any]:
        offered, records, raw = self._offered(kind, where)
        taken = [relative for relative, _, _ in self._files.files(folder)]
        copied: list[dict[str, str]] = []
        if loose:
            name = offered[0]["path"]
            relative = rules.free_name(name, taken)
            full = self._files.write_into(folder, relative, self._files.read_loose(where))
            copied.append({"from": where, "path": relative, "full": full})
        else:
            paths = rules.pick([d["path"] for d in offered], documents, "document") if documents else []
            bodies = (
                self._files.read_entries(where, paths)
                if kind == "sab"
                else {p: self._files.read_file(where, p) for p in paths}
            )
            for path in paths:
                relative = rules.free_name(path, taken)
                taken.append(relative)
                full = self._files.write_into(folder, relative, bodies[path])
                copied.append({"from": path, "path": relative, "full": full})
        # Connections and blades: the project's own names are never overwritten.
        own = {
            str(r["name"]).casefold()
            for r in self._records(
                {
                    n: self._files.read_file(folder, n)
                    for n, _, _ in self._files.app_files(folder)
                    if rules.blade_entry(n)
                }
            )
        }
        added: dict[str, list[str]] = {"connections": [], "blades": []}
        skipped: list[str] = []
        for group, wanted in (("connections", connections), ("blades", blades)):
            if not wanted:
                continue
            pool = [r for r in records if bool(r["connection"]) == (group == "connections")]
            names = rules.pick([str(r["name"]) for r in pool], wanted, group[:-1])
            for name in names:
                record = next(r for r in pool if r["name"] == name)
                if name.casefold() in own:
                    skipped.append(name)
                    continue
                entry = f"{rules.BLADES}/{self._computer.file_name(name)}"
                self._files.write_into(folder, entry, raw[str(record["file"])])
                own.add(name.casefold())
                added[group].append(name)
        return {"documents": copied, **added, "skipped": skipped}


def _listed(record: dict[str, Any]) -> dict[str, Any]:
    return {k: record[k] for k in ("name", "kind", "template", "connection", "description")}
