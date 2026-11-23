"""A connection's usage: the Connections page's cards and a card's detail (domain/connection_usage.py).

  overview   every connection: its type, its status word (a cheap check: never a run), its calls this
             session
  usage      one connection: where it is used (notebook and script cells, canvas blocks, open grids read
             from it), its configuration (type, settings, sign-in, each password's source by kind and
             name; never a value), its calls this session by kind
  record     a call through the app: a catalog load, a query, a table read, a test (counted where the
             app runs a connection: services/blades.py's child runs) or a Workbench kernel's report
             (POST /connections/{name}/used: client/connection_use.py; the user's own Jupyter outside
             the app is not counted)

Calls are kept in memory only, for this session.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import connection_usage as rules
from swissarmybench.domain import connections as connection_rules
from swissarmybench.domain import dataverse, portability, python_connections, sql_server
from swissarmybench.domain import projects as project_rules
from swissarmybench.domain.blades import Blade, BladeError
from swissarmybench.domain.notebooks import NotebookError
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.blades import BladeService
from swissarmybench.services.connections import ConnectionService
from swissarmybench.services.workspace import NotFound, Workspace

MAX_DOCUMENTS = 200


class FolderFiles(Protocol):
    """A project folder's own files (adapters/projects.py ProjectFiles)."""

    def names(self, folder: str) -> list[str]: ...

    def path(self, folder: str, name: str) -> str: ...


def documents_to_search(
    open_documents: Iterable[str],
    folder: str | None,
    files: FolderFiles,
    recent: Callable[[], Iterable[Mapping[str, Any]]],
    real: Callable[[str], str],
) -> list[str]:
    """Where the Connections page looks for a connection's references: with a project open, its own
    notebooks, scripts and apps (everything is the project's, 2026-11-16) and the documents open in a
    Workbench window; with none, the Workbench's recent files and the open documents. Each file once,
    by its real path (one notebook reached by two spellings was listed twice)."""
    paths = list(open_documents)
    if folder:
        try:
            names = files.names(folder)
        except OSError:
            names = []
        paths += [files.path(folder, n) for n in project_rules.project_files(names)]
    else:
        paths += [str(r["path"]) for r in recent() if r.get("exists")]
    seen: dict[str, str] = {}
    for path in paths:
        seen.setdefault(real(path), path)
    return list(seen.values())


class ConnectionUsage:
    def __init__(
        self,
        ws: Workspace,
        blades: BladeService,
        connections: ConnectionService,
        *,
        documents: Callable[[], Iterable[str]],
        read: Callable[[str], tuple[str, str, float]],
        origin_of: Callable[[str], Origin],
        environ: Mapping[str, str],
        now: Callable[[], float],
        figures_of: Callable[[str], dict[str, Any] | None] = lambda name: None,
        extra_cards: Callable[[], list[dict[str, Any]]] = lambda: [],
    ) -> None:
        self.ws = ws
        self._blades = blades
        self._connections = connections
        # SEAM (project-scope): the documents a connection's references are looked for in. Today: the
        # Workbench's recent files, the open documents and the open project's files (bootstrap.py).
        self._documents = documents
        self._read = read  # a document's text and its full path (the Workbench's documents)
        self._origin_of = origin_of  # where an open table came from (services/datasets.py)
        self._environ = environ
        self._now = now
        self._calls: dict[str, rules.Calls] = {}  # by name, case folded
        # The last run's words (memory only): its error, in plain words, and what the server said it is
        # (SQL Server's about(): driver, sign-in, version, collation; never a value).
        self._errors: dict[str, str] = {}
        self._about: dict[str, dict[str, Any]] = {}
        # More cards than the library's: the open project's Sandbox (services/sandbox.py card).
        self.extra_cards: Callable[[], list[dict[str, Any]]] = extra_cards
        # A connection's running figures (services/call_stats.py figures_of), None while it has none.
        self.figures_of: Callable[[str], dict[str, Any] | None] = figures_of

    # ===== the calls =====

    def _connection(self, name: str) -> Blade | None:
        try:
            blade = self._blades.get(name)
        except (BladeError, KeyError, LookupError):
            return None
        return blade if connection_rules.connection_kind(blade.kind, blade.template) else None

    def record(
        self, name: str, kind: str, ok: bool = True, error: str = "", about: Mapping[str, Any] | None = None
    ) -> None:
        """One call of a connection's through the app (a blade that is not a connection is not counted),
        with its error's words when it failed and what the server said it is when it told."""
        try:
            said = rules.call_kind(kind)
        except ValueError:
            return
        blade = self._connection(name)
        if blade is None:
            return
        key = blade.name.casefold()
        self._calls[key] = rules.record(self._calls.get(key), said, ok, self._now())
        if ok:
            self._errors.pop(key, None)
        elif error:
            self._errors[key] = error[:2000]
        if about:
            self._about[key] = {str(k): v for k, v in about.items() if isinstance(v, str | bool)}

    def report(self, name: str, body: Any) -> dict[str, Any]:
        """A Workbench kernel's report of a call: {"kind": "query" | "read" | "connect", "ok"?}."""
        if not isinstance(body, dict):
            raise ValueError('Send {"kind": "query"}.')
        kind = rules.call_kind(body.get("kind"))
        if self._connection(name) is None:
            raise NotFound(f"There is no connection called {name}.")
        self.record(name, kind, body.get("ok") is not False)
        return {"ok": True}

    def calls(self, name: str) -> rules.Calls | None:
        return self._calls.get(name.casefold())

    # ===== the cards =====

    def _missing(self, summary: Mapping[str, Any]) -> list[str]:
        """The passwords a connection asks for that are in none of its places (keyring, a vault, this
        computer's environment)."""
        vaults = [self._blades.get(v) for v in summary.get("vaults", [])]
        missing = []
        for secret, saved in dict(summary.get("secrets") or {}).items():
            in_vault = any(v.vault_all or secret in v.vault_mapping for v in vaults)
            if not saved and not in_vault and not self._environ.get(secret):
                missing.append(str(secret))
        return missing

    def _keyring(self, summary: Mapping[str, Any]) -> list[str]:
        """Each password's source as far as what runs elsewhere goes: "keyring" for one saved on this
        computer and in no vault it reads (the card's Only works on your machine)."""
        vaults = [self._blades.get(v) for v in summary.get("vaults", [])]
        sources = []
        for secret, saved in dict(summary.get("secrets") or {}).items():
            in_vault = any(v.vault_all or secret in v.vault_mapping for v in vaults)
            sources.append("keyring" if saved and not in_vault else "elsewhere")
        return sources

    def _portability(self, name: str, entry: Mapping[str, Any]) -> tuple[list[dict[str, str]], bool]:
        """What the connection leans on that only this computer has (domain/portability.py), and whether
        its code is the earlier SQL Server code on pyodbc (the card's Update to the new driver)."""
        try:
            blade = self._blades.get(name)
        except Exception:  # a connection the listing has and the library lost: nothing to say of it
            return [], False
        found = portability.check(blade.code, blade.template, self._keyring(entry))
        return portability.as_json(found), sql_server.is_old(blade.code)

    def _card(self, entry: Mapping[str, Any]) -> dict[str, Any]:
        name = str(entry["name"])
        local, old_driver = self._portability(name, entry)
        calls = self.calls(name)
        failed = (entry.get("catalog_state") or {}).get("state") == "failed"
        missing = self._missing(entry)
        error = self._errors.get(name.casefold(), "")
        about = self._about.get(name.casefold(), {})
        return {
            "name": name,
            "connection": entry.get("connection"),
            "type": entry.get("type") or "",
            "template": entry.get("template"),
            "writes": entry.get("writes"),  # "Writes: <the starters>" or "Read-only: <why>"
            "dialect": entry.get("dialect"),
            "description": entry.get("description") or "",
            "source": entry.get("source"),
            "status": rules.status(calls, missing, failed, error),
            "missing": missing,
            "error": error,  # the last run's, in plain words (SQL Server's say the fix)
            # What the server is, when it said (SQL Server's Test): the card's lines.
            "about": sql_server.card_words(about) if about else [],
            "catalog_state": entry.get("catalog_state"),
            "catalog_loaded": bool(entry.get("catalog_loaded")),
            # Its calls this session by kind, and the project's running figures (services/call_stats.py:
            # times, typical rows, errors; never a value), when there are any.
            "calls": (calls or rules.Calls()).to_json() | {"figures": self.figures_of(name)},
            "tables_kind": entry.get("tables_kind"),
            "facts": entry.get("facts"),  # what the page draws for its kind (rules.kind_facts)
            # A Dataverse connection saved for its Web API: its card offers the SQL endpoint.
            "reads": dataverse.WEB_API_WORDS if entry.get("tables_kind") == "dataverse_web" else "",
            # What only this computer has (an ODBC driver, Windows sign-in, a file on this disk, the
            # keyring...): the card's amber "Only works on your machine" (the owner, 2026-11-17).
            "local": local,
            # The earlier SQL Server code on pyodbc: the card offers Update to the new driver.
            "update_driver": old_driver,
        }

    def overview(self) -> dict[str, Any]:
        """Every connection as a card: its type, its status word, its calls this session; then the open
        project's Sandbox (local test data, never live)."""
        cards = [self._card(c) for c in self._connections.listing()["connections"]]
        return {"connections": cards + list(self.extra_cards())}

    # ===== one connection =====

    def _configuration(self, blade: Blade, details: Mapping[str, Any]) -> dict[str, Any]:
        """Its type, settings and sign-in, each password's source by kind and name (never a value)."""
        summary = details.get("summary") or {}
        secrets = dict(summary.get("secrets") or {})
        vaults = [self._blades.get(v) for v in summary.get("vaults", [])]
        sources = []
        for secret in details.get("secrets") or []:
            vault = next((v for v in vaults if secret in v.vault_mapping), None)
            every = next((v for v in vaults if v.vault_all), None)
            if secrets.get(secret):
                sources.append({"name": secret, "from": "keyring"})
            elif vault is not None:
                sources.append(
                    {
                        "name": secret,
                        "from": "vault",
                        "vault": vault.name,
                        "secret": vault.vault_mapping[secret],
                    }
                )
            elif every is not None:
                sources.append({"name": secret, "from": "vault", "vault": every.name})
            elif self._environ.get(secret):
                sources.append({"name": secret, "from": "environment"})
            else:
                sources.append({"name": secret, "from": "missing"})
        variables = [
            {k: v for k, v in source.items() if k in ("name", "from", "vault", "secret")}
            for source in python_connections.sources_json(blade.variables)
        ]
        kind = connection_rules.connection_kind(blade.kind, blade.template)
        return {
            "kind": kind,
            "type": details.get("label") or "",
            "template": blade.template,
            "dialect": blade.dialect,
            "description": blade.description,
            "settings": rules.shown_settings(details.get("fields") or []),
            "sign_in": rules.sign_in_of(blade.code, details.get("sign_ins") or []),
            "passwords": sources,
            "variables": variables,
            "vault_entries": [{"variable": e, "secret": s} for e, s in blade.vault_mapping.items()],
            "vault_all": blade.vault_all,
            "catalog": bool(blade.has_catalog),
            "row_limit": blade.row_limit,
            "source": blade.source,
            "pack": blade.pack,
        }

    def references(self, name: str) -> tuple[list[rules.Reference], list[str]]:
        """Every cell and block that uses it in the documents, and the open grids read from it; the
        documents that could not be read."""
        found: list[rules.Reference] = []
        unread: list[str] = []
        seen: set[str] = set()
        for path in list(dict.fromkeys(self._documents()))[:MAX_DOCUMENTS]:
            try:
                text, full, _ = self._read(path)
            except (FileNotFoundError, OSError, ValueError):
                unread.append(path)
                continue
            key = full.replace("\\", "/").casefold()
            if key in seen:
                continue
            seen.add(key)
            title = full.replace("\\", "/").rsplit("/", 1)[-1]
            if full.lower().endswith(".stapp.json"):  # an old app canvas: nothing reads it any more
                continue
            try:
                found += rules.document_references(full, title, text, name)
            except (NotebookError, ValueError):
                unread.append(full)
        for grid in self.ws.grids.all():
            origin = self._origin_of(grid.dataset)
            if origin.kind == "connection" and origin.connection and rules.same_name(origin.connection, name):
                how = (
                    "sab.dax"
                    if origin.dax
                    else "sab.sql"
                    if origin.sql
                    else "sab.read"
                    if origin.code
                    else "open"
                )
                line = ".".join(p for p in (origin.place or ()) if p) or grid.dataset
                found.append(rules.Reference("", grid.dataset, "grid", how, line, grid=grid.id))
        return found[: rules.MAX_REFERENCES], unread

    def usage(self, name: str) -> dict[str, Any]:
        """Where it is used, its configuration and its calls this session."""
        blade = self._connection(name)
        if blade is None:
            raise NotFound(f"There is no connection called {name}.")
        details = self._connections.details(blade.name)
        card = next((c for c in self._connections.listing()["connections"] if c["name"] == blade.name), None)
        references, unread = self.references(blade.name)
        return {
            **(self._card(card) if card else {"name": blade.name}),
            "configuration": self._configuration(blade, details),
            "references": [r.to_json() for r in references],
            "unread": unread,
        }
