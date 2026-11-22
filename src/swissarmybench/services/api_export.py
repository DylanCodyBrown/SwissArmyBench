"""A local sandbox API exported for its framework target (domain/api_targets.py).

targets  the framework targets: the base's three and each extension's (its API_TARGETS)
export   {"target"?: its header's, "folder"?: exports/api/<target>/ in the project, "rows"?: bundle the
sandbox
         (only when an endpoint uses connection("Sandbox")), "replace"?: [files edited by hand to write
         over]}:
         API.py, sab_api.py, connections.py (each connection the endpoints use, as its own code: nothing here
         runs it), the target's files, README.md. A made folder: each file written only when its bytes change,
         a file the export no longer makes removed, a file edited by hand kept (said: Replace, Compare). The
         agent's export with rows waits for the user's Allow; no secret goes in any file.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.domain import api_targets as targets
from swissarmybench.domain import local_api as rules
from swissarmybench.domain import project_paths
from swissarmybench.domain.api_targets import Bundle, Registry, Route
from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Conflict, NotFound, Workspace


class Folder(Protocol):
    """The export's folder (adapters/sandbox.py ExportFolder)."""

    def write(self, folder: str, files: dict[str, str]) -> dict[str, list[str]]: ...

    def existing(self, folder: str) -> dict[str, str]: ...

    def remove(self, folder: str, names: list[str]) -> None: ...

    def copy_sandbox(self, folder: str) -> None: ...


class Connections(Protocol):
    def connections_code(self, wanted: list[str]) -> dict[str, Any]: ...


class ApiExport:
    def __init__(
        self,
        ws: Workspace,
        project: Callable[[], str | None],
        read_api: Callable[[str], str | None],
        runtime_text: Callable[[], str],
        connections: Connections,
        folder: Folder,
        edited: Callable[[str], set[str]],
        approvals: Approvals,
        registry: Registry | None = None,
        adapter_text: Callable[[], str] = str,  # adapter.py, beside sab_api.py in every export
        api_adapter_text: Callable[[], str] = str,  # api_adapter.py beside it (Plans/api-adapter.plan.md)
    ) -> None:
        self.ws = ws
        self._project = project
        self._read_api = read_api
        self._runtime = runtime_text
        self._adapter = adapter_text
        self._api_adapter = api_adapter_text
        self._connections = connections
        self._folder = folder
        self._edited = edited  # the project's made files edited by hand (services/project_scope.py)
        self._approvals = approvals
        self.registry = registry or Registry()

    def targets(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        return {"targets": [t.to_json() for t in self.registry.targets.values()]}

    def bundle(self, rows: bool) -> tuple[Bundle, rules.Api]:
        folder = self._project()
        if folder is None:
            raise Conflict("Open a project first: its local sandbox API is its API.py.")
        text = self._read_api(folder)
        if text is None:
            raise NotFound("The project has no API.py yet: New local sandbox API… makes it.")
        api = rules.parse(text)
        if api.problems:
            first = api.problems[0]
            raise Conflict(f"API.py line {first['line']}: {first['message']} Fix it, then export.")
        used = list(dict.fromkeys(n for e in api.endpoints for n in e.connections))
        real = [n for n in used if n.casefold() != "sandbox"]
        code = self._connections.connections_code(real)
        uses_sandbox = len(real) != len(used)
        connections_py = targets.connections_module(str(code["text"]), uses_sandbox, real)
        routes = tuple(
            Route(e.name, e.method, api.settings.base_path + e.path, e.summary) for e in api.endpoints
        )
        return (
            Bundle(
                api.settings.name,
                api.settings.description,
                text,
                self._runtime(),
                connections_py,
                rules.openapi(api),
                routes,
                api.settings.base_path,
                tuple(code["requirements"]),
                tuple(code["variables"]),
                tuple(code["notes"]),
                rows and uses_sandbox,
                uses_sandbox,
                self._adapter(),
                self._api_adapter(),
            ),
            api,
        )

    async def export(self, body: Any, who: str = "user") -> dict[str, Any]:
        given = body if isinstance(body, dict) else {}
        rows = bool(given.get("rows"))
        bundle, api = await asyncio.to_thread(self.bundle, rows)
        target = self.registry.get(str(given.get("target") or api.settings.target))
        project = self._project() or ""
        relative = f"{targets.EXPORT_FOLDER}/{target.id}"
        place = str(given.get("folder") or "").strip() or f"{project.rstrip('/')}/{relative}"
        if bundle.sandbox:
            await self._approvals.allowed(
                who,
                subject=rules.FILE,
                action="export with rows",
                detail=f"Export the local sandbox API for {target.label} into {place}, "
                "with the sandbox's rows",
                otherwise="nothing was exported",
            )
        files = target.render(bundle)
        inside = project_paths.inside(place, project)
        prefix = relative + "/" if inside and not given.get("folder") else ""
        edited = {p[len(prefix) :] for p in self._edited(project) if prefix and p.startswith(prefix)}
        replace = {str(p) for p in given.get("replace") or []}
        kept = sorted(n for n in files if n in edited and n not in replace)
        existing = await asyncio.to_thread(self._folder.existing, place)
        compare = {n: existing.get(n, "") for n in kept}
        written = await asyncio.to_thread(
            self._folder.write, place, {n: t for n, t in files.items() if n not in kept}
        )
        stale = sorted(
            n for n in existing if n not in files and n not in edited and n != targets.SANDBOX_FILE
        )
        await asyncio.to_thread(self._folder.remove, place, stale)
        if bundle.sandbox:
            await asyncio.to_thread(self._folder.copy_sandbox, place)
        self.ws.audit.write(who, "local_api_export", target.id, files=len(files), rows=bundle.sandbox)
        return {
            "target": target.to_json(),
            "folder": place,
            "files": sorted(files),
            "written": written["written"],
            "unchanged": written["unchanged"],
            "removed": stale,
            "kept": [{"file": n, "theirs": files[n], "yours": compare[n]} for n in kept],
            "variables": list(bundle.variables),
            "notes": list(bundle.notes),
            "warnings": targets.warnings(bundle),
            "sandbox": bundle.sandbox,
        }
