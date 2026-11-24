"""Home's summary of the open project (the owner, 2026-11-24; rules in domain/project_summary.py): one
answer from what the other services already say, so the page makes one call, and the agent's
`project_summary` reads the same.

  summary   {"project": None} with none open; else the project (its name, type and the type's words, Local
            or Shared, its folder, unsaved, Autosave, read-only), its Python (project_python's state), its
            tables, documents, the connections it uses, the Session's last entries, its type's deliverable
            and the counts
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from swissarmybench.domain import project_summary as rules


class Projects(Protocol):
    def state(self) -> dict[str, Any]: ...


class Explorer(Protocol):
    def types(self) -> dict[str, Any]: ...

    def where(self, path: str) -> str: ...


class Scope(Protocol):
    def documents(self, kind: Any = None) -> dict[str, Any]: ...


class Use(Protocol):
    def connections(self) -> list[str]: ...


class Datasets(Protocol):
    def listing(self) -> dict[str, Any]: ...


class Usage(Protocol):
    def overview(self) -> dict[str, Any]: ...


class Colours(Protocol):
    def get(self) -> dict[str, Any]: ...


class Log(Protocol):
    def listing(self, who: Any = None, limit: Any = None, changes: Any = None) -> dict[str, Any]: ...


class Deliverables(Protocol):
    def deliverable(self, folder: str) -> dict[str, Any]: ...


class Python(Protocol):
    def state(self) -> dict[str, Any]: ...


class Sources(Protocol):
    """What the summary reads: the services by their names in Services (server/app.py hands it that)."""

    @property
    def sab_projects(self) -> Projects: ...

    @property
    def project_explorer(self) -> Explorer: ...

    @property
    def project_scope(self) -> Scope: ...

    @property
    def project_use(self) -> Use: ...

    @property
    def datasets(self) -> Datasets: ...

    @property
    def connection_usage(self) -> Usage: ...

    @property
    def connection_colours(self) -> Colours: ...

    @property
    def session_log(self) -> Log: ...

    @property
    def scaffold(self) -> Deliverables: ...

    @property
    def project_python(self) -> Python: ...


class ProjectSummary:
    def __init__(self, sources: Sources) -> None:
        self._s = sources

    def _project(self, project: Mapping[str, Any]) -> dict[str, Any]:
        folder = str(project.get("folder") or project.get("path") or "")
        kind = str(project.get("type") or "")
        known = next((t for t in self._s.project_explorer.types()["types"] if t.get("type") == kind), None)
        return {
            "name": str(project.get("name") or ""),
            "path": folder,
            "type": kind,
            "type_name": str((known or {}).get("title") or (known or {}).get("name") or kind),
            "where": self._s.project_explorer.where(folder) if folder else "local",
            "dirty": bool(project.get("dirty")),
            "autosave": bool(project.get("autosave")),
            "autosave_error": project.get("autosave_error"),
            "read_only": project.get("read_only"),
            "private": bool(project.get("private")),
        }

    def summary(self) -> dict[str, Any]:
        project = self._s.sab_projects.state().get("project")
        if not project:
            return {"project": None}
        about = self._project(project)
        try:
            used = self._s.project_use.connections()
        except Exception:  # a library that cannot be read: the rest of the summary still says itself
            used = []
        answer: dict[str, Any] = {
            "project": about,
            "python": self._s.project_python.state(),
            "tables": rules.tables(project.get("tables") or [], self._s.datasets.listing()["datasets"]),
            "documents": rules.documents(self._s.project_scope.documents()["documents"]),
            "connections": rules.connections(
                used,
                self._s.connection_usage.overview()["connections"],
                self._s.connection_colours.get()["connections"],
            ),
            "recent": self._s.session_log.listing(limit=rules.RECENT)["entries"],
        }
        deliverable = self._s.scaffold.deliverable(about["path"]) if about["path"] else {"type": None}
        answer["deliverable"] = deliverable if deliverable.get("type") else None
        answer["counts"] = rules.counts(answer)
        return answer
