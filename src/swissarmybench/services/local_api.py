"""The project's local sandbox API (domain/local_api.py; the owner, 2026-11-21: "build api's here that could
host
locally inside the app so the streamlit could use our API as a testing ground" / "No never run against live
data
ever").

  state     API.py read (never run): its settings, endpoints (each one's data words: "Mock of Warehouse
            (sqlserver)"), models, problems with their lines, the OpenAPI document; whether it runs, where
  new       API.py made at the project's top when it has none (New local sandbox API…), its settings written
  settings  the header's name, description, target, base path (every other byte of the file kept)
  run/stop  hosted on 127.0.0.1 in a process of its own (server/api_runs.py), with a key of its own; it gets
            only the sandbox (its mock clients' route, by a data key) and no connection's code, variable or
            secret; started again when API.py changes on disk (looked at every second while it runs)
  call      one request through it, timed (Try it, the kernel's sab.api, the agent's api(call): a write waits
            for the user's Allow); its answer's rows counted, never logged with a value
  log       its requests: method, path, status, milliseconds, rows (a refusal's words and API.py line), and
            the last lines API.py printed
  address   where it runs and its key, for this computer's own callers (Play and Launch pass them to the app)

Each change is told to the pages (`local_api_changed`).
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, Protocol

from swissarmybench.domain import api_actions
from swissarmybench.domain import api_patterns as pattern_rules
from swissarmybench.domain import api_scaffold as scaffold_rules
from swissarmybench.domain import local_api as rules
from swissarmybench.domain import sandbox_dialects as dialects
from swissarmybench.domain.local_api import ApiFileError
from swissarmybench.services.changes import raised
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace

WATCH_SECONDS = 1.0
LINE_HEADER = "X-Sab-Error-Line"  # server/api_host.py's: a failed request's API.py line


class Runner(Protocol):
    """A running local sandbox API's process (server/api_runs.py)."""

    port: int
    endpoints: list[dict[str, Any]]

    def alive(self) -> bool: ...

    async def stop(self) -> None: ...

    async def request(
        self, method: str, path: str, query: dict[str, Any], body: bytes | None
    ) -> tuple[int, bytes, dict[str, str]]: ...

    async def log(self) -> list[dict[str, Any]]: ...

    def output(self) -> list[str]: ...


class Start(Protocol):
    async def __call__(self, file: str, base: str, key: str, data_url: str) -> Runner: ...


class Files(Protocol):
    def read(self, path: str) -> str | None: ...

    def write(self, path: str, text: str) -> None: ...

    def stamp(self, path: str) -> float | None: ...

    def join(self, folder: str, name: str) -> str: ...


class Mocks(Protocol):
    """The sandbox (services/sandbox.py): what each connection is mocked as, its tables."""

    async def client(self, connection: Any) -> dict[str, Any]: ...

    async def listing(self) -> dict[str, Any]: ...

    async def set_key(self, body: Any, who: str = "user") -> dict[str, Any]: ...


STREAM_WORDS = "DuckDB does part of it over the stream (its source cannot)"


def data_words(name: str, client: dict[str, Any] | None) -> str:
    """An endpoint's data in words: "Mock of Warehouse (sqlserver)", or why there is none yet."""
    if client is None:
        return f"{name}: no table of it in the sandbox yet (Add to sandbox)"
    if client.get("kind") == "duckdb":
        return "The sandbox (plain DuckDB)"
    what = client.get("template") or client.get("dialect") or client.get("kind")
    return f"Mock of {client.get('connection') or name} ({what})"


class LocalApi:
    def __init__(
        self,
        ws: Workspace,
        project: Callable[[], str | None],
        files: Files,
        start: Start,
        mocks: Mocks,
        approvals: Any,
        data_url: Callable[[str], str],
        now: Callable[[], float] = time.time,
        catalog: Any = None,
        publish: Callable[[dict[str, str]], None] = lambda values: None,
    ) -> None:
        self.ws = ws
        self._project = project
        self._files = files
        self._start = start
        self._mocks = mocks
        self._approvals = approvals
        self._data_url = data_url  # the app's /sandbox/data/<key> address
        self._now = now
        self._runner: Runner | None = None
        self._running_for: str | None = None  # the API.py it runs
        self._stamp: float | None = None
        self._started_at: float | None = None
        self._key = ""
        self._data_key = ""
        self._failed: dict[str, Any] | None = None  # the last start's failure: {error, line}
        self._endpoints_seen: dict[str, Any] = {}  # API.py's endpoints as last read (the change log)
        self._endpoints_of: str | None = None  # the API.py they were read from
        # The project whose sandbox the agent may write through the API for the rest of this session (the
        # owner approved, 2026-11-21: one Allow, the sandbox only, never live; Reset undoes it); None: each
        # agent write asks.
        self._agent_writes: str | None = None
        self._watch: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        # The framework targets' ids (the export's registry fills it in: services/api_export.py).
        self.target_ids: Callable[[], list[str]] = lambda: ["fastapi", "azure_functions", "aws_lambda"]
        # The framework targets as the page's picker and the agent read them: [{id, label}] (the export's
        # registry, so an extension's target is offered like the base's three).
        self.targets: Callable[[], list[dict[str, Any]]] = lambda: [
            {"id": i, "label": i} for i in self.target_ids()
        ]
        # The loaded catalogs (services/catalogs.py): "Will this work for real?" reads them, never loads one.
        self.catalog: Any = catalog
        # Where it runs, put in this server's environment while it runs (SAB_API_URL, SAB_API_KEY,
        # SAB_API_BASE), so an app Play or Launch starts afterwards reaches it; {} when it stops.
        self.publish: Callable[[dict[str, str]], None] = publish
        # The canvases' widget instances that name an endpoint (the Streamlit extension's; none without it).
        self.api_uses: Callable[[], list[dict[str, Any]]] = lambda: []
        # The endpoint wizard's patterns: the base's nine and each extension's (its API_PATTERNS; bootstrap).
        self.patterns = pattern_rules.Registry()

    # ===== the file =====

    def path(self) -> str:
        folder = self._project()
        if folder is None:
            raise Conflict("Open a project first: its local sandbox API is its API.py.")
        return self._files.join(folder, rules.FILE)

    async def _sandbox_tables(self) -> list[dict[str, Any]]:
        return list((await self._mocks.listing()).get("tables") or [])

    def _text(self) -> str | None:
        return self._files.read(self.path())

    def endpoint_names(self) -> list[str]:
        """API.py's endpoints as a widget's endpoint property names them: "GET /orders/{region}" (no base
        path: the app adds SAB_API_BASE)."""
        if self._project() is None:
            return []
        text = self._text()
        return [] if text is None else [f"{e.method} {e.path}" for e in rules.parse(text).endpoints]

    def document(self) -> tuple[dict[str, Any], str] | None:
        """API.py's OpenAPI document and its base path as the file is now (None: no project, no API.py, or
        one that does not read): its actions for the canvas's picker and a built app (services/actions.py)."""
        text = self._text() if self._project() is not None else None
        if text is None:
            return None
        try:
            api = rules.parse(text)
        except Exception:  # API.py's own trouble: no actions to offer
            return None
        return rules.openapi(api), api.settings.base_path

    def endpoint_fields(self) -> dict[str, list[str]]:
        """Each endpoint whose body is one of API.py's models: its fields, in order ("POST /visits" -> [...]),
        for an Event's body mapping on the Canvas."""
        text = self._text() if self._project() is not None else None
        if text is None:
            return {}
        try:
            api = rules.parse(text)
        except Exception:  # API.py's own trouble: no fields to offer
            return {}
        found: dict[str, list[str]] = {}
        for e in api.endpoints:
            fields = rules.body_fields(e, api.models)
            if fields is not None:
                found[f"{e.method} {e.path}"] = list(fields)
        return found

    def data_keys(self) -> set[str]:
        """The keys the sandbox's data route takes: the running API's only."""
        return {self._data_key} if self._data_key and self.running() else set()

    def running(self) -> bool:
        return self._runner is not None and self._runner.alive()

    async def state(self, body: Any = None, who: str = "user", full: bool = False) -> dict[str, Any]:
        """API.py as every door reads it: its settings, endpoints (each one's data words, fields and made-up
        request), models, problems, targets, whether it runs. `full`: its OpenAPI document too (the agent's
        state is brief without it; the critic's proposal 11, approved 2026-11-21)."""
        folder = self._project()
        if folder is None:
            return {"project": None, "exists": False, "running": None}
        path = self.path()
        text = self._text()
        if text is None:
            return {"project": folder, "file": path, "exists": False, "running": None}
        self._endpoints_noted(text)  # a hand edit since the last read: the change log's
        try:
            api = rules.parse(text)
        except ApiFileError as error:
            problem = {"line": 1, "message": str(error)}
            return {"project": folder, "file": path, "exists": True, "problems": [problem],
                    "endpoints": [], "running": self._running_json()}  # fmt: skip
        mocks: dict[str, dict[str, Any] | None] = {}
        for e in api.endpoints:
            for name in e.connections:
                if name.casefold() not in mocks:
                    try:
                        mocks[name.casefold()] = await self._mocks.client(name)
                    except Exception:
                        mocks[name.casefold()] = None
        learned = self._learned()
        endpoints = []
        for e in api.endpoints:
            words = [data_words(n, mocks.get(n.casefold())) for n in e.connections]
            if e.streams:  # its source cannot do part of the work: said, never hidden
                words.append(STREAM_WORDS)
            made_by, of = pattern_rules.pattern_at(text, e.line)
            known_pattern = self.patterns.patterns.get(made_by)
            pattern = (
                {"id": made_by, "label": known_pattern.label if known_pattern else made_by, "of": of,
                 "role": self.patterns.role(made_by, e.name)}
                if made_by
                else None
            )  # fmt: skip
            # Its contract, read by every door from the one definition (domain/local_api.py): the body's
            # fields, and the made-up request Try it starts from, filled from the endpoint's learned shape
            # (what it was last sent: paths and types; made-up values, never a kept one).
            known = learned.get(f"{e.method} {e.path}") or {}
            start = api_actions.tried(rules.made_up(e, api.models), known.get("contract"), known.get("sent"))
            endpoints.append(
                e.to_json()
                | {
                    "data": words,
                    "fields": rules.body_fields(e, api.models),
                    "try": start,
                    "pattern": pattern,
                }
            )
        return {
            "project": folder,
            "file": path,
            "exists": True,
            "settings": api.settings.to_json(),
            "endpoints": endpoints,
            "models": api.to_json()["models"],
            "problems": api.problems,
            "targets": self.targets(),
            "running": self._running_json(),
            "failed": self._failed,
            "agent_writes": self.agent_writes(),
        } | ({"openapi": rules.openapi(api)} if full else {})

    def _running_json(self) -> dict[str, Any] | None:
        if not self.running() or self._runner is None:
            return None
        return {
            "port": self._runner.port,
            "url": f"http://127.0.0.1:{self._runner.port}",
            "since": time.strftime("%H:%M:%S", time.localtime(self._started_at or self._now())),
            "endpoints": len(self._runner.endpoints),
        }

    async def _told(self, who: str, action: str, **facts: Any) -> None:
        if action:
            self.ws.audit.write(who, action, rules.FILE, **facts)
        await self.ws.live.broadcast({"type": "local_api_changed"})

    async def new(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """API.py made at the project's top when it has none (an older project's first), its settings
        given."""
        path = self.path()
        if self._text() is None:
            folder = self._project() or ""
            name = folder.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
            self._files.write(path, rules.scaffold(name))
            await self._told(who, "local_api_new")
        if isinstance(body, dict) and body:
            return await self.set_settings(body, who)
        return await self.state()

    async def set_settings(self, body: Any, who: str = "user") -> dict[str, Any]:
        given = body if isinstance(body, dict) else {}
        text = self._text()
        if text is None:
            raise NotFound("The project has no API.py yet: New local sandbox API… makes it.")
        now = rules.read_settings(text)
        made = rules.Settings(
            str(given.get("name", now.name) or now.name).strip()[:120],
            str(given.get("description", now.description) or "").strip()[:500],
            str(given.get("target", now.target) or now.target),
            rules.check_base(given.get("base_path", now.base_path)),
        )
        if made.target not in self.target_ids():
            raise ApiFileError(f"The target is one of: {', '.join(self.target_ids())}.")
        written = rules.with_settings(text, made)
        if written != text:
            self._files.write(self.path(), written)
            await self._told(who, "local_api_settings")
        return await self.state()

    # ===== Try it: filled from the learned shape =====

    # Each endpoint's learned contract and the shape of what it was last sent ("POST /orders" -> {"contract",
    # "sent"}: services/actions.py local_learned, set once it is built). Types only: no value is kept.
    learned: Callable[[], dict[str, dict[str, Any]]] | None = None

    def _learned(self) -> dict[str, dict[str, Any]]:
        try:
            return dict(self.learned()) if self.learned is not None else {}
        except Exception:  # a shape file's own trouble: Try it starts from the definition alone
            return {}

    # ===== Payload shapes =====

    async def shapes(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Each canvas widget that uses an endpoint: what it expects beside what the endpoint answers, and
        each mismatch, before Play."""
        text = self._text()
        if text is None:
            return {"uses": [], "ok": True}
        found = rules.shapes(rules.parse(text), self.api_uses())
        return {"uses": found, "ok": not any(u["problems"] for u in found)}

    # ===== "Will this work for real?" =====

    async def check(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Each endpoint's SQL against its connection's catalog, as it is loaded here (never a query on the
        source, never a load): each table and column found or not, or why it could not be checked."""
        text = self._text()
        if text is None:
            raise NotFound("The project has no API.py yet: New local sandbox API… makes it.")
        api = rules.parse(text)
        out = []
        for e in api.endpoints:
            for sql in e.sql:
                for name in e.connections or ["Sandbox"]:
                    said = await self._checked(name, str(sql["text"]), bool(sql.get("formatted")))
                    out.append({"endpoint": e.name, "line": sql["line"], "connection": name} | said)
        return {"checks": out, "ok": all(c["state"] in ("works", "sandbox") for c in out)}

    async def _checked(self, name: str, sql: str, formatted: bool) -> dict[str, Any]:
        if name.casefold() == "sandbox":
            return {"state": "sandbox", "words": "The sandbox's own tables: nothing real to check."}
        if formatted:
            return {
                "state": "unknown",
                "words": "An f-string's SQL is made when it runs: it cannot be checked here.",
            }
        catalog = self.catalog
        if catalog is None or name.casefold() not in catalog.loaded_names():
            words = f"{name}'s catalog is not loaded here: load it on the Connections page, then check again."
            return {"state": "no_catalog", "words": words}
        try:
            client = await self._mocks.client(name)
        except Exception:
            client = {}
        try:
            named = dialects.names_in(sql, str(client.get("dialect") or ""))
        except Exception as error:
            return {
                "state": "unreadable",
                "words": f"The SQL could not be read: {str(error).splitlines()[0]}",
            }
        missing: list[str] = []
        tables: list[dict[str, Any]] = []
        places = await catalog.places(name) or []
        for n in named:
            place = next(
                (
                    p
                    for p in places
                    if p[2].casefold() == n.table.casefold()
                    and (not n.schema or p[1].casefold() == n.schema.casefold())
                ),
                None,
            )
            if place is None:
                missing.append(f"no table {'.'.join(x for x in (n.schema, n.table) if x)}")
                tables.append({"table": n.table, "found": False})
                continue
            try:
                described = await catalog.columns(name, place[1], place[2], place[0] or None)
                known = {str(c["column"]).casefold(): str(c.get("type") or "") for c in described["columns"]}
            except (LookupError, ValueError, KeyError):
                known = {}
            gone = [c for c in n.columns if c.casefold() not in known]
            missing += [f"{place[2]} has no column {c}" for c in gone]
            tables.append(
                {"table": place[2], "found": True, "columns": {c: known.get(c.casefold()) for c in n.columns}}
            )
        if missing:
            return {"state": "differs", "words": "; ".join(missing) + ".", "tables": tables}
        return {
            "state": "works",
            "words": f"Every table and column is in {name}'s catalog.",
            "tables": tables,
        }

    # ===== the endpoint wizard: a pattern over a sandbox table, appended to API.py =====

    @staticmethod
    def _target(table: dict[str, Any]) -> pattern_rules.Target:
        """A sandbox table as the patterns read it: its columns, its row count, how it is reached (the
        connection it is mocked as, its schema there)."""
        client = table.get("client") or {}
        place = (table.get("source") or {}).get("place") or {}
        kind = str(client.get("kind") or "duckdb")
        source = scaffold_rules.Source(
            kind if kind in ("duckdb", "dataverse", "sharepoint") else "database",
            str(client.get("connection") or "Sandbox") if kind != "duckdb" else "Sandbox",
            str(client.get("dialect") or "duckdb"),
            str(place.get("schema") or ""),
        )
        rows = table.get("rows")
        return pattern_rules.Target(
            str(table["name"]),
            tuple(table.get("columns") or ()),
            source,
            rows if isinstance(rows, int) else None,
        )

    @staticmethod
    def _named(listed: list[dict[str, Any]], wanted: Any) -> dict[str, Any] | None:
        name = str(wanted or "").strip().casefold()
        return next((t for t in listed if str(t["name"]).casefold() == name), None)

    def _taken(self, text: str) -> pattern_rules.Taken:
        api = rules.parse(text)
        names = [e.name for e in api.endpoints] + list(api.models) + _defined(text)
        return pattern_rules.Taken(tuple(names), tuple(e.path for e in api.endpoints))

    async def pattern_list(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """The patterns as data: each one's question, its own steps, the widgets that pair with it."""
        return {"patterns": self.patterns.listed()}

    async def plan(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """The wizard's one read (the agent's too): {"table"?, "pattern"?, "fields"?, "other"?}. With no
        table: the sandbox's tables. With a table: every pattern ranked by its shape, each with one sentence
        why. With a pattern too: that pattern's own steps (the columns each offers, its value: the one sent,
        else what the shape suggests), and the code as it would be added, or the one thing still missing.
        Nothing is written."""
        given = body if isinstance(body, dict) else {}
        listed = await self._sandbox_tables()
        tables = [
            {"name": t["name"], "rows": t.get("rows"), "columns": t.get("columns") or [],
             "data": data_words(str(t["name"]), t.get("client") or {"kind": "duckdb"})}
            for t in listed
        ]  # fmt: skip
        answer: dict[str, Any] = {"tables": tables, "patterns": self.patterns.listed()}
        if not str(given.get("table") or "").strip():
            return answer
        table = self._named(listed, given.get("table"))
        if table is None:
            raise NotFound(f"The sandbox has no table named {given.get('table')}: Add to sandbox first.")
        target = self._target(table)
        others = [self._target(t) for t in listed]
        answer |= {"table": target.name, "ranked": self.patterns.ranked(target, others)}
        if not str(given.get("pattern") or "").strip():
            return answer
        pattern = self.patterns.get(given.get("pattern"))
        other = None
        if pattern.tables == 2:
            second = self._named(listed, given.get("other"))
            other = self._target(second) if second is not None else pattern_rules.partner(target, others)
        elif given.get("other"):  # a second table a one-table pattern may take (an action's log)
            second = self._named(listed, given.get("other"))
            other = self._target(second) if second is not None else None
        fields = given.get("fields") if isinstance(given.get("fields"), dict) else {}
        answer["plan"] = self.patterns.planned(pattern.id, target, fields, other)
        answer["others"] = [t["name"] for t in tables if t["name"] != target.name]
        text = (self._text() if self._project() is not None else None) or rules.scaffold("api")
        try:
            made = self.patterns.make(pattern.id, target, fields, self._taken(text), other)
        except scaffold_rules.ScaffoldError as error:
            return answer | {"problem": str(error), "code": "", "added": []}
        made.text = scaffold_rules.fitted(text, made.text)
        needs = scaffold_rules.imports_missing(text, made.text)
        paired = [
            w | {"function": name} for name in made.added for w in self.patterns.pairings(pattern.id, name)
        ]
        code = {"problem": None, "code": made.text.lstrip("\n"), "imports": needs, "added": made.added}
        return answer | code | {"streams": made.streams, "words": made.words, "paired": paired}

    async def scaffold(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"table", "pattern"? (table), "fields"?, "other"? (Reconcile's second table), "dry_run"?}: a
        pattern's endpoints over a sandbox table appended to API.py (domain/api_patterns.py); API.py made
        first when the project has none. "dry_run": the code and its endpoints, nothing written. The older
        {"table", "key"} is the Table pattern with that key."""
        given = body if isinstance(body, dict) else {}
        wanted = str(given.get("table") or "").strip()
        listed = await self._sandbox_tables()
        table = self._named(listed, wanted)
        if table is None:
            raise NotFound(f"The sandbox has no table named {wanted}: Add to sandbox first.")
        pattern = self.patterns.get(given.get("pattern"))
        fields = dict(given.get("fields") or {}) if isinstance(given.get("fields"), dict) else {}
        if given.get("key") and "key" not in fields:
            fields["key"] = given["key"]
        target = self._target(table)
        other = None
        if pattern.tables == 2:
            second = self._named(listed, given.get("other"))
            if second is None:
                raise NotFound(f"{pattern.label} compares two sandbox tables: name the second one (other).")
            other = self._target(second)
        elif given.get("other"):  # a second table a one-table pattern may take (an action's log)
            second = self._named(listed, given.get("other"))
            if second is None:
                raise NotFound(f"The sandbox has no table {given.get('other')} for {pattern.label}.")
            other = self._target(second)
        dry = bool(given.get("dry_run"))
        if self._text() is None and not dry:
            await self.new(None, who)
        text = self._text() or rules.scaffold("api")
        made = self.patterns.make(pattern.id, target, fields, self._taken(text), other)
        block = scaffold_rules.fitted(text, made.text)
        needs = scaffold_rules.imports_missing(text, block)
        if dry:
            return {"dry_run": True, "pattern": pattern.id, "code": block.lstrip("\n"), "imports": needs,
                    "added": made.added, "streams": made.streams, "words": made.words}  # fmt: skip
        self._endpoints_noted(text)  # as it stood, so the log says what this write added, and who did
        text, needs = scaffold_rules.with_imports(text, needs)
        written = text.rstrip("\n") + "\n" + ("\n" + needs if needs else "") + block
        self._files.write(self.path(), written)
        self._endpoints_noted(written, who)
        await self._told(who, "local_api_scaffold", table=table["name"], pattern=pattern.id)
        note = ""
        if made.key and not any(c.get("key") for c in table["columns"]):
            try:  # the endpoint's key: the sandbox keeps it too
                await self._mocks.set_key({"table": table["name"], "key": made.key}, who)
            except (ValueError, LookupError, Conflict) as error:
                note = f"{table['name']} has no primary key in the sandbox: {error}"
        state = await self.state()
        by = {e["name"]: e for e in state.get("endpoints") or []}
        paired = [
            w | {"endpoint": f"{by[name]['method']} {by[name]['path']}"}
            for name in made.added
            if name in by
            for w in self.patterns.pairings(pattern.id, name)
        ]
        line = text.count("\n") + 2 + (needs.count("\n") + 1 if needs else 0)
        done = state | {"added": [n for n in made.added if n in by], "line": line, "pattern": pattern.id,
                        "paired": paired}  # fmt: skip
        return done | ({"note": note} if note else {})

    def paired(self) -> list[dict[str, Any]]:
        """Each endpoint a pattern made, with the widgets that pair with it ("GET /orders": api_table's
        endpoint): what a widget dropped on the Canvas wires itself to (the Streamlit extension reads it)."""
        text = self._text() if self._project() is not None else None
        if text is None:
            return []
        try:
            api = rules.parse(text)
        except Exception:  # API.py's own trouble: nothing to pair
            return []
        found: list[dict[str, Any]] = []
        for e in api.endpoints:
            made_by, of = pattern_rules.pattern_at(text, e.line)
            answer = rules.answer_fields(e, api.models)
            for w in self.patterns.pairings(made_by, e.name) if made_by else []:
                # A property the pairing sets to a field of the answer (a select's column: the label).
                places = dict(w.get("sets") or {})
                sets = {p: answer[i] for p, i in places.items() if 0 <= int(i) < len(answer)}
                w = {k: v for k, v in w.items() if k != "sets"} | ({"sets": sets} if sets else {})
                found.append(w | {"endpoint": f"{e.method} {e.path}", "pattern": made_by, "of": of})
        return found

    # ===== run, stop =====

    async def run(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        async with self._lock:
            await self._stop_quietly()
            await self._begin()
        await self._told(who, "local_api_run", failed=bool(self._failed))
        if self._watch is None or self._watch.done():
            self._watch = asyncio.create_task(self._watch_file())
        return await self.state()

    async def _begin(self) -> None:
        path = self.path()
        text = self._text()
        if text is None:
            raise NotFound("The project has no API.py yet: New local sandbox API… makes it.")
        settings = rules.read_settings(text)
        self._endpoints_noted(text)
        self._key = secrets.token_urlsafe(24)
        self._data_key = secrets.token_urlsafe(24)
        self._stamp = self._files.stamp(path)
        self._failed = None
        try:
            self._runner = await self._start(
                path, settings.base_path, self._key, self._data_url(self._data_key)
            )
            self._running_for = path
            self._started_at = self._now()
            self.publish(self.env_for_app() | {"SAB_API_BASE": settings.base_path})
        except StartFailed as failed:
            self._runner = None
            self._failed = {"error": failed.error, "line": failed.line}

    async def _stop_quietly(self) -> None:
        if self._runner is not None:
            await self._runner.stop()
            self.publish({})
        self._runner = None
        self._running_for = None
        self._data_key = ""

    async def stop(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        async with self._lock:
            was = self._runner is not None
            await self._stop_quietly()
            if self._watch is not None:
                self._watch.cancel()
                self._watch = None
        if was:
            await self._told(who, "local_api_stop")
        return await self.state()

    async def stop_all(self) -> None:
        await self.stop(None, "app")

    def _endpoints_noted(self, text: str | None, who: str = "app") -> None:
        """The change log (services/changes.py): each endpoint API.py added, changed or removed since it
        was last read here, one event each (its method and path; its parameters, answer and SQL
        fingerprinted). `who`: whoever wrote it (the wizard's caller), else the app, which saw a file edited
        by hand. The first read of a project's API.py is where it starts from (nothing said), and a file
        that does not parse for a moment is passed over (a half-typed line removes nothing)."""
        path = self.path()
        now = _endpoint_shapes(text) if text is not None else {}
        if now is None:
            return
        was = self._endpoints_seen if self._endpoints_of == path else None
        self._endpoints_of, self._endpoints_seen = path, now
        if was is None:
            return
        by = "app" if who == "app" else ""
        for key in sorted(set(was) | set(now)):
            before, after = was.get(key), now.get(key)
            words = (
                f"Added the endpoint {key} to {rules.FILE}" if before is None
                else f"Removed the endpoint {key} from {rules.FILE}" if after is None
                else ""
            )  # fmt: skip
            change = raised("endpoint", f"{rules.FILE} {key}", before, after, words, by=by)
            if change:
                self.ws.audit.write(who, "changed", rules.FILE, **change)

    async def _watch_file(self) -> None:
        """While it runs (or its last start failed), a change to API.py on disk starts it again."""
        try:
            while self._runner is not None or self._failed is not None:
                await asyncio.sleep(WATCH_SECONDS)
                if self._project() is None:
                    await self.stop(None, "app")
                    return
                path = self.path()
                if path != (self._running_for or path):
                    await self.stop(None, "app")
                    return
                await self._restart_if_changed()
        except asyncio.CancelledError:
            pass

    async def _restart_if_changed(self) -> None:
        """API.py changed on disk since the process started: it is started again (the watch's look, and a
        call's own: a call sent the moment after a save is answered by the code as saved, never the old)."""
        if self._runner is None and self._failed is None:
            return
        path = self.path()
        if path != (self._running_for or path) or self._files.stamp(path) == self._stamp:
            return
        async with self._lock:
            if self._files.stamp(path) == self._stamp:
                return  # another caller started it again meanwhile
            await self._stop_quietly()
            await self._begin()
        await self._told("app", "local_api_restart", failed=bool(self._failed))

    # ===== calls =====

    async def call(self, body: Any, who: str = "user", raw: bool = False) -> dict[str, Any]:
        """{"method", "path", "query"?, "body"?}: one request through the running API. `raw`: the answer's
        own bytes and headers too (`raw`, `headers`), for a caller that reads them itself (api_adapter)."""
        given = body if isinstance(body, dict) else {}
        method = str(given.get("method") or "GET").upper()
        path = str(given.get("path") or "/")
        if method not in rules.METHODS or not path.startswith("/"):
            raise ApiFileError("A call is {method: GET|POST|PUT|PATCH|DELETE, path: /...}.")
        asked = given.get("query")
        # An optional parameter left empty (None) is not sent.
        query = {k: v for k, v in asked.items() if v is not None} if isinstance(asked, dict) else {}
        payload = given.get("body")
        await self._restart_if_changed()
        if self._runner is None and self._failed is not None:
            raise Conflict(f"The local sandbox API did not start: {self._failed.get('error')}")
        if not self.running() or self._runner is None:
            raise Conflict("The local sandbox API is not running: Run it first.")
        if who == "agent" and method != "GET" and not self.agent_writes():
            if not await self._ask_agent_writes(f"{method} {path}"):
                raise Refused("The user declined (or did not answer): nothing was sent.")
        sent = None if payload is None else json.dumps(payload).encode()
        started = time.perf_counter()
        status, answer, headers = await self._runner.request(method, path, dict(query or {}), sent)
        ms = round((time.perf_counter() - started) * 1000, 1)
        kinds = {k.lower(): v for k, v in headers.items()}
        saved = re.search(r'filename="([^"]+)"', kinds.get("content-disposition", ""))
        try:
            parsed = json.loads(answer) if answer else None
        except ValueError:
            parsed = answer.decode("utf-8", "replace")
        if saved:  # a file to save (the Export pattern): said as one, its text only when it is text
            kind = kinds.get("content-type", "")
            parsed = {"download": saved.group(1), "type": kind, "bytes": len(answer)}
            if kind.startswith("text/"):
                parsed["text"] = answer.decode("utf-8", "replace")[:20000]
        rows = len(parsed) if isinstance(parsed, list) else None
        self.ws.audit.write(who, "local_api_call", f"{method} {path}", status=status, rows=rows)
        done: dict[str, Any] = {"status": status, "ms": ms, "rows": rows, "body": parsed}
        if status >= 400:
            # A refusal in the one shape (9.5): its sentence, and where in API.py when the endpoint itself
            # failed (the host's line header), for Try it's Go to line and the agent alike.
            said = parsed.get("error") if isinstance(parsed, dict) else None
            done["error"] = str(said or f"{method} {path} answered {status}.")
            line = next((v for k, v in headers.items() if k.lower() == LINE_HEADER.lower()), None)
            if line and str(line).isdigit():
                done["line"] = int(line)
                done["where"] = f"{rules.FILE} line {line}"
                # The mock's refusal names the line itself: said once, in `where`.
                done["error"] = done["error"].replace(f"{rules.FILE} line {line}: ", "", 1)
        if raw:
            done |= {"raw": answer, "headers": kinds}
        return done

    def agent_writes(self) -> bool:
        """Whether the agent may write through the API to the open project's sandbox without asking."""
        folder = self._project()
        return folder is not None and self._agent_writes == folder

    async def _ask_agent_writes(self, first: str) -> bool:
        detail = rules.agent_writes_words(first)
        if not await self._approvals.ask(rules.FILE, "write the sandbox through the local API", detail):
            return False
        self._agent_writes = self._project()
        self.ws.audit.write("agent", "local_api_agent_writes", rules.FILE, allowed=True)
        await self.ws.live.broadcast({"type": "local_api_changed"})
        return True

    async def set_agent_writes(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"allow": bool}: the agent's writes through the API for the rest of this session. Stopping is
        anyone's; the agent's own allow:true asks the user (an Allow covers the session); the user's is
        given."""
        given = body if isinstance(body, dict) else {}
        if self._project() is None:
            raise Conflict("Open a project first: its sandbox is what the API writes.")
        if given.get("allow") is True:
            if who == "agent" and not self.agent_writes():
                if not await self._ask_agent_writes("its writes"):
                    raise Refused("The user declined (or did not answer): each write still asks.")
            elif who != "agent":
                self._agent_writes = self._project()
                self.ws.audit.write(who, "local_api_agent_writes", rules.FILE, allowed=True)
        else:
            self._agent_writes = None
            self.ws.audit.write(who, "local_api_agent_writes", rules.FILE, allowed=False)
        await self.ws.live.broadcast({"type": "local_api_changed"})
        return {"agent_writes": self.agent_writes()}

    async def log(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        if not self.running() or self._runner is None:
            return {"log": [], "running": False}
        try:
            return {"log": await self._runner.log(), "output": self._runner.output(), "running": True}
        except OSError:  # it stopped as it was asked
            return {"log": [], "running": False}

    async def address(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Where it runs and its key (for this computer's own callers: the app it serves)."""
        if not self.running() or self._runner is None:
            return {"running": False}
        return {"running": True, "url": f"http://127.0.0.1:{self._runner.port}", "key": self._key}

    def env_for_app(self) -> dict[str, str]:
        """What Play and Launch give a Streamlit app: SAB_API_URL and SAB_API_KEY (none while it is not
        running)."""
        if not self.running() or self._runner is None:
            return {}
        return {"SAB_API_URL": f"http://127.0.0.1:{self._runner.port}", "SAB_API_KEY": self._key}


def _defined(text: str) -> list[str]:
    """The top-level names API.py defines (a CRUD set never takes one)."""
    return re.findall(r"^(?:def|class|async def)\s+([A-Za-z_]\w*)", text, re.M)


class StartFailed(Exception):
    """API.py did not import, or the process did not start: its words and API.py's line."""

    def __init__(self, error: str, line: int | None = None) -> None:
        super().__init__(error)
        self.error = error
        self.line = line


def _endpoint_shapes(text: str) -> dict[str, Any] | None:
    """API.py's endpoints by method and path, each as the change log fingerprints it (its parameters, answer,
    connections and SQL; not its lines, which move when code above it does). None: the file does not read
    as an API right now."""
    try:
        ast.parse(text)  # rules.parse answers no endpoints for a file Python cannot read: not "all removed"
        found = rules.parse(text).endpoints
    except (SyntaxError, ValueError):
        return None
    return {
        f"{e.method} {e.path}": {"endpoint": {k: v for k, v in asdict(e).items() if k not in ("line", "end")}}
        for e in found
    }
