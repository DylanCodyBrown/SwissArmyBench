"""A code app project: its folder as the Power Apps CLI makes it, read.

The CLI owns the project. `power.config.json` (written by `pa app init`, changed by `pa app add/remove
data-source`) holds the app's name, its environment, its local address and its data sources; the CLI's
generated TypeScript lives in `src/generated/models/*Model.ts` and `src/generated/services/*Service.ts`;
each connector's downloaded schema in `.power/schemas/`. The app adds one small file of its own,
`.sab/project.json`, recording the project's type (`codeapp`), so the app's mode follows it; nothing else.

Read here (docs/verified.md): power.config.json's fields as the Power Apps CLI 1.4.2 writes them (version,
appId, appDisplayName, appType, description, environmentId, buildPath, buildEntryPoint, localAppUrl,
region, appSettings, connectionReferences: {id: {id, displayName, dataSources, dataSets: {dataset:
{dataSources: {name: {tableName}}}}}}, databaseReferences: {key: {dataSources: {name: {entitySetName,
logicalName}}, environmentVariableName}}). Pure rules over text the caller read.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

PROJECT_TYPE = "codeapp"
CONFIG = "power.config.json"
MARKER = ".sab/project.json"
GENERATED = "src/generated"
SCHEMAS = ".power/schemas"
# The folders a code app's file tree leaves out (packages, builds, Git's own).
HIDDEN = frozenset({"node_modules", "dist", ".git", ".vite", ".turbo"})
_NAME = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,80}$")


class ProjectError(ValueError):
    """A folder that is not a code app, or a name a folder cannot have."""


def folder_name(display_name: Any) -> str:
    """A new app's folder, from its name ("Expense Tracker" -> "expense-tracker")."""
    text = str(display_name or "").strip()
    if not text or not _NAME.match(text):
        raise ProjectError("An app's name is a short line of text, without \\ / : * ? \" < > |.")
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "code-app"


def marker(existing: str | None, extras: Mapping[str, Any] | None = None) -> str:
    """`.sab/project.json` with the type set (any other field it holds kept)."""
    data: dict[str, Any] = {}
    if existing:
        try:
            loaded = json.loads(existing)
            if isinstance(loaded, dict):
                data = loaded
        except ValueError:
            data = {}
    data["type"] = PROJECT_TYPE
    data.update(extras or {})
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def project_type(marker_text: str | None) -> str | None:
    if not marker_text:
        return None
    try:
        data = json.loads(marker_text)
    except ValueError:
        return None
    kind = data.get("type") if isinstance(data, dict) else None
    return kind if isinstance(kind, str) else None


def config(text: str | None) -> dict[str, Any]:
    """power.config.json, read (a folder without one is not a code app yet)."""
    if text is None:
        raise ProjectError(f"This folder has no {CONFIG}: it is not a code app (New code app makes one).")
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ProjectError(f"{CONFIG} is not JSON: {error}") from None
    if not isinstance(data, dict):
        raise ProjectError(f"{CONFIG} is not an object.")
    return data


def summary(cfg: Mapping[str, Any]) -> dict[str, Any]:
    """The app as its page shows it: name, environment, local address, its id once pushed."""
    return {
        "name": str(cfg.get("appDisplayName") or ""),
        "description": str(cfg.get("description") or ""),
        "app_id": cfg.get("appId") or None,
        "environment_id": str(cfg.get("environmentId") or ""),
        "local_url": str(cfg.get("localAppUrl") or "http://localhost:3000"),
        "app_type": str(cfg.get("appType") or "CodeApp"),
        "build_path": str(cfg.get("buildPath") or "./dist"),
    }


def sources(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every data source power.config.json holds: Dataverse tables (databaseReferences) and connectors'
    tables and actions (connectionReferences), each with the connector its remove needs."""
    found: list[dict[str, Any]] = []
    databases = _dict(cfg.get("databaseReferences"))
    for ref in databases.values():
        if not isinstance(ref, dict):
            continue
        for name, ds in (ref.get("dataSources") or {}).items():
            ds = ds if isinstance(ds, dict) else {}
            found.append(
                {
                    "name": str(name),
                    "kind": "dataverse",
                    "connector": "dataverse",
                    "table": str(ds.get("logicalName") or name),
                    "entity_set": str(ds.get("entitySetName") or ""),
                    "connection": None,
                }
            )
    connections = _dict(cfg.get("connectionReferences"))
    for key, ref in connections.items():
        if not isinstance(ref, dict):
            continue
        api = str(ref.get("id") or "").rstrip("/").split("/")[-1] or str(key)
        tables: dict[str, dict[str, str]] = {}
        for dataset, ds in (ref.get("dataSets") or {}).items():
            for name, t in ((ds or {}).get("dataSources") or {}).items():
                tables[str(name)] = {
                    "dataset": str(dataset),
                    "table": str((t or {}).get("tableName") or name),
                }
        for name in ref.get("dataSources") or []:
            where = tables.get(str(name))
            found.append(
                {
                    "name": str(name),
                    "kind": "table" if where else "connector",
                    "connector": api,
                    "display_name": str(ref.get("displayName") or api),
                    "dataset": where["dataset"] if where else None,
                    "table": where["table"] if where else None,
                    "connection": str(ref.get("sharedConnectionId") or "") or None,
                    "reference": str(ref.get("xrmConnectionReferenceLogicalName") or "") or None,
                }
            )
    return sorted(found, key=lambda s: (s["kind"] != "dataverse", s["name"].casefold()))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def generated(paths: Iterable[str]) -> list[dict[str, Any]]:
    """The CLI's generated files (relative paths under src/generated), as models and services."""
    found = []
    for path in sorted(paths):
        rel = path.replace("\\", "/")
        if not rel.startswith(GENERATED + "/") or not rel.endswith((".ts", ".tsx")):
            continue
        part = "service" if "/services/" in rel else "model" if "/models/" in rel else "other"
        found.append({"path": rel, "kind": part, "name": rel.rsplit("/", 1)[-1]})
    return found


def tree(paths: Iterable[str]) -> dict[str, Any]:
    """The project's files as a tree ({name, path, children}), its packages and builds left out."""
    root: dict[str, Any] = {"name": "", "path": "", "children": {}}
    for path in sorted(p.replace("\\", "/") for p in paths):
        parts = [p for p in path.split("/") if p]
        if not parts or any(p in HIDDEN for p in parts):
            continue
        node = root
        for depth, part in enumerate(parts):
            node = node["children"].setdefault(
                part, {"name": part, "path": "/".join(parts[: depth + 1]), "children": {}}
            )

    def listed(node: dict[str, Any]) -> dict[str, Any]:
        children = sorted(node["children"].values(), key=lambda n: (not n["children"], n["name"].casefold()))
        out: dict[str, Any] = {"name": node["name"], "path": node["path"]}
        if children:
            out["children"] = [listed(c) for c in children]
        return out

    return listed(root)


def uses_vite_plugin(vite_config: str | None) -> bool:
    """The template's dev server serves the app's configuration itself (the Power Apps Vite plugin)."""
    return bool(vite_config and "@microsoft/power-apps-vite" in vite_config)


def language_of(path: str) -> str:
    """The Workbench editor's language for a project file."""
    lower = path.lower()
    if lower.endswith((".ts", ".mts", ".cts")):
        return "typescript"
    if lower.endswith(".tsx"):
        return "tsx"
    if lower.endswith((".js", ".mjs", ".cjs", ".jsx")):
        return "javascript"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith((".css", ".scss")):
        return "css"
    if lower.endswith((".html", ".htm")):
        return "html"
    if lower.endswith(".md"):
        return "markdown"
    return "plaintext"
