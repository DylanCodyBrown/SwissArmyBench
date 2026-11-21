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

import asyncio
import json
import re
import secrets
import time
from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.domain import api_scaffold as scaffold_rules
from swissarmybench.domain import local_api as rules
from swissarmybench.domain import sandbox_dialects as dialects
from swissarmybench.domain.local_api import ApiFileError
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
        self.catalog: Any = None
        # Where it runs, put in this server's environment while it runs (SAB_API_URL, SAB_API_KEY,
        # SAB_API_BASE), so an app Play or Launch starts afterwards reaches it; {} when it stops.
        self.publish: Callable[[dict[str, str]], None] = lambda values: None
        # The canvases' widget instances that name an endpoint (the Streamlit extension's; none without it).
        self.api_uses: Callable[[], list[dict[str, Any]]] = lambda: []

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

    async def state(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        folder = self._project()
        if folder is None:
            return {"project": None, "exists": False, "running": None}
        path = self.path()
        text = self._text()
        if text is None:
            return {"project": folder, "file": path, "exists": False, "running": None}
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
        examples = self._examples()
        endpoints = []
        for e in api.endpoints:
            words = [data_words(n, mocks.get(n.casefold())) for n in e.connections]
            kept = examples.get(rules.endpoint_key(e.method, e.path))
            # Its contract, read by every door from the one definition (domain/local_api.py): the body's
            # fields, and the made-up request Try it starts from (the kept example's body first).
            start = rules.made_up(e, api.models)
            if kept is not None:
                start["body"] = kept
            endpoints.append(
                e.to_json()
                | {"data": words, "example": kept, "fields": rules.body_fields(e, api.models), "try": start}
            )
        return {
            "project": folder,
            "file": path,
            "exists": True,
            "settings": api.settings.to_json(),
            "endpoints": endpoints,
            "models": api.to_json()["models"],
            "problems": api.problems,
            "openapi": rules.with_examples(rules.openapi(api), examples, api.settings.base_path),
            "examples_file": rules.EXAMPLES_FILE,
            "targets": self.targets(),
            "running": self._running_json(),
            "failed": self._failed,
        }

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

    # ===== an endpoint's kept example =====

    def _examples_path(self) -> str:
        folder = self._project()
        if folder is None:
            raise Conflict("Open a project first: its local sandbox API is its API.py.")
        return self._files.join(folder, rules.EXAMPLES_FILE)

    def _examples(self) -> dict[str, Any]:
        return rules.read_examples(self._files.read(self._examples_path()))

    async def keep_example(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Keep as its example: {"endpoint": "POST /orders", "body": {...}}: Try it's edited body kept as the
        endpoint's example payload (Try it starts from it; the OpenAPI document shows it), in the project's
        .sab/api_examples.json beside API.py (API.py itself is never written). {"body": null}: forgotten."""
        given = body if isinstance(body, dict) else {}
        key = str(given.get("endpoint") or "").strip()
        text = self._text()
        if text is None:
            raise NotFound("The project has no API.py yet: New local sandbox API… makes it.")
        method, _, path = key.partition(" ")
        key = rules.endpoint_key(method, path)
        examples = self._examples()
        if given.get("body") is None:
            if examples.pop(key, None) is None:
                raise NotFound(f"{key} has no kept example.")
        else:
            examples[key] = rules.check_example(rules.parse(text), key, given["body"])
        self._files.write(self._examples_path(), rules.examples_text(examples))
        await self._told(who, "local_api_example")
        return {"endpoint": key, "example": examples.get(key), "file": rules.EXAMPLES_FILE}

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

    # ===== New endpoint from a table =====

    async def scaffold(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"table", "key"?}: the CRUD set over a sandbox table appended to API.py, in its source's own style
        (domain/api_scaffold.py); API.py made first when the project has none."""
        given = body if isinstance(body, dict) else {}
        wanted = str(given.get("table") or "").strip()
        listed = await self._sandbox_tables()
        table = next((t for t in listed if t["name"].casefold() == wanted.casefold()), None)
        if table is None:
            raise NotFound(f"The sandbox has no table named {wanted}: Add to sandbox first.")
        if self._text() is None:
            await self.new(None, who)
        text = self._text() or ""
        api = rules.parse(text)
        client = table.get("client") or {}
        place = (table.get("source") or {}).get("place") or {}
        kind = str(client.get("kind") or "duckdb")
        source = scaffold_rules.Source(
            kind if kind in ("duckdb", "dataverse", "sharepoint") else "database",
            str(client.get("connection") or "Sandbox") if kind != "duckdb" else "Sandbox",
            str(client.get("dialect") or "duckdb"),
            str(place.get("schema") or ""),
        )
        taken = [e.name for e in api.endpoints] + list(api.models) + _defined(text)
        block = scaffold_rules.crud(
            table["name"],
            table["columns"],
            source,
            given.get("key") or None,
            taken,
            [e.path for e in api.endpoints],
        )
        text, needs = scaffold_rules.with_imports(text, scaffold_rules.imports_missing(text, block))
        written = text.rstrip("\n") + "\n" + ("\n" + needs if needs else "") + block
        self._files.write(self.path(), written)
        await self._told(who, "local_api_scaffold", table=table["name"])
        state = await self.state()
        made = [
            e
            for e in state.get("endpoints") or []
            if e["name"].endswith("_" + scaffold_rules.stem(table["name"]))
        ]
        return state | {"added": [e["name"] for e in made], "line": text.count("\n") + 2}

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
                stamp = self._files.stamp(path)
                if stamp != self._stamp:
                    async with self._lock:
                        await self._stop_quietly()
                        await self._begin()
                    await self._told("app", "local_api_restart", failed=bool(self._failed))
        except asyncio.CancelledError:
            pass

    # ===== calls =====

    async def call(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"method", "path", "query"?, "body"?}: one request through the running API."""
        given = body if isinstance(body, dict) else {}
        method = str(given.get("method") or "GET").upper()
        path = str(given.get("path") or "/")
        if method not in rules.METHODS or not path.startswith("/"):
            raise ApiFileError("A call is {method: GET|POST|PUT|PATCH|DELETE, path: /...}.")
        query = given.get("query") if isinstance(given.get("query"), dict) else {}
        payload = given.get("body")
        if not self.running() or self._runner is None:
            raise Conflict("The local sandbox API is not running: Run it first.")
        if who == "agent" and method != "GET":
            detail = f"{method} {path} on the local sandbox API (it writes the project's sandbox only)"
            if not await self._approvals.ask(rules.FILE, "call the local sandbox API", detail):
                raise Refused("The user declined (or did not answer): nothing was sent.")
        sent = None if payload is None else json.dumps(payload).encode()
        started = time.perf_counter()
        status, answer, headers = await self._runner.request(method, path, dict(query or {}), sent)
        ms = round((time.perf_counter() - started) * 1000, 1)
        try:
            parsed = json.loads(answer) if answer else None
        except ValueError:
            parsed = answer.decode("utf-8", "replace")
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
        return done

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
