"""Add API (docs/ideas.md, "Add API", the owner 2026-11-15): an OpenAPI document or a short form, made
into API_<name>.py and a "Python (your own code)" connection in one step. For the page and the agent
alike (the golden rule); writing a file of code asks nothing (it holds no rows and no secret).

  choices   the auth types with their settings, and the presets (Azure Function App, AWS Lambda, Google)
  preview   what Add would do: the operations, the tables, the variables the client reads, where the
            file goes and, when it is there already, what changes (nothing is written)
  add       the file written (or written again, only when Add API made it) and the connection saved
            (or changed, only when it is the one that loads this file; its variables' sources kept)
  try_it    one operation's first rows before Add: the client pasted into a draft connection, run in a
            child process (nothing written; a typed value used for that run only)
  inline    the made clients a notebook's code imports, from beside it, as code to paste into an
            exported script or notebook (the exporter calls this: an API_<name>.py travels inline)

The rules are domain/apis.py and domain/api_clients.py; files and fetches adapters/apis.py.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from swissarmybench.domain import api_clients, api_explorer, apis, web_calls
from swissarmybench.domain.apis import ApiError, Names, Spec
from swissarmybench.services.workspace import Conflict, NotFound, Workspace


class SpecSource(Protocol):
    def read_file(self, path: str) -> tuple[str, str]: ...

    def fetch(self, url: str) -> tuple[str, str]: ...

    def document(self, text: str) -> dict[str, Any]: ...


class Files(Protocol):
    def folder(self, folder: str) -> str: ...

    def path(self, folder: str, name: str) -> str: ...

    def read(self, path: str) -> str | None: ...

    def write(self, path: str, text: str) -> None: ...

    def clients(self, folder: str) -> dict[str, str]: ...


class Library(Protocol):
    """This computer's library of APIs (adapters/apis.py ApiLibrary): one folder each."""

    def folder_for(self, name: str) -> str: ...

    def path(self, folder: str, name: str) -> str: ...

    def read(self, path: str) -> str | None: ...

    def write(self, path: str, text: str) -> None: ...

    def remove(self, folder: str) -> None: ...


class Blades(Protocol):
    """The blades (services/blades.py): an API's web call blades are saved and removed there."""

    def get(self, name: str) -> Any: ...

    def save(self, body: Any, previous: str | None, who: str = ...) -> Awaitable[dict[str, Any]]: ...

    def remove(self, name: str, who: str = ...) -> Awaitable[dict[str, Any]]: ...


class Connections(Protocol):
    """The connections (services/connections.py): a saved one's form, and saving one."""

    def details(self, name: str) -> dict[str, Any]: ...

    def save(self, body: Any, previous: str | None, who: str = ...) -> Awaitable[dict[str, Any]]: ...

    def read_draft(self, body: Any, place: dict[str, str], limit: int) -> Awaitable[dict[str, Any]]: ...


@dataclass(frozen=True)
class _Plan:
    spec: Spec
    names: Names
    folder: str
    path: str
    text: str
    old: str | None
    old_mark: dict[str, Any] | None
    existing: dict[str, Any] | None  # the connection of that name, when it is this file's
    taken: str  # why the file or the name cannot be used ("": they can)
    document: dict[str, Any] | None = None  # the OpenAPI document read (None: a form's)
    source: dict[str, Any] | None = None  # where it was read from: {"kind", "address"}

    def to_json(self) -> dict[str, Any]:
        changes = None
        if self.old is not None and self.old_mark is not None:
            changes = apis.changes(
                api_clients.methods(self.old),
                api_clients.methods(self.text),
                self.old_mark,
                api_clients.mark(self.spec, self.names),
            ).to_json()
        url = apis.url_variable(self.names.prefix)
        reads = [{"name": url, "argument": "base_url", "required": False, "secret": False}]
        reads += [v.to_json() for v in apis.variables(self.spec.auth, self.names.prefix)]
        return {
            **self.names.to_json(),
            "file": self.names.file,
            "folder": self.folder,
            "path": self.path,
            "spec": self.spec.to_json(),
            "variables": reads,
            "exists": self.old is not None,
            "changes": changes,
            "connection_exists": self.existing is not None,
            "taken": self.taken or None,
            "lines": self.text.count("\n"),
        }


class Apis:
    def __init__(
        self,
        ws: Workspace,
        files: Files,
        sources: SpecSource,
        connections: Connections,
        library: Library,
        blades: Blades,
        now: Callable[[], str],
    ) -> None:
        self.ws = ws
        self._files = files
        self._sources = sources
        self._connections = connections
        # This computer's library (the owner, 2026-11-17): every API's folder, whatever project is open.
        self._library = library
        self._blades = blades
        self._now = now  # the time a source was read, as text
        self.busy: set[str] = set()  # APIs being added: their tables are made once, at the end

    def choices(self) -> dict[str, Any]:
        return apis.choices()

    async def _spec(self, body: dict[str, Any]) -> Spec:
        return (await self._read(body))[0]

    async def _read(self, body: dict[str, Any]) -> tuple[Spec, dict[str, Any] | None, dict[str, Any]]:
        """The spec, the document it was read from (None: a form) and where that came from."""
        given = [k for k in ("spec", "spec_path", "spec_url", "form") if body.get(k) not in (None, "")]
        if len(given) != 1:
            raise ApiError(
                'Give the API one way: "spec" (an OpenAPI document\'s text), "spec_path" (its file), '
                '"spec_url" (its address) or "form" (a base URL and endpoints).'
            )
        way = given[0]
        document: dict[str, Any] | None = None
        where: dict[str, Any] = {"kind": "form", "address": ""}
        if way == "form":
            spec = apis.parse_form(body["form"])
        else:
            source = ""
            if way == "spec":
                if not isinstance(body["spec"], str | dict):
                    raise ApiError("spec is the OpenAPI document's text.")
                text = body["spec"]
            elif way == "spec_path":
                try:
                    text, source = await asyncio.to_thread(self._sources.read_file, str(body["spec_path"]))
                except FileNotFoundError as error:
                    raise NotFound(str(error)) from None
            else:
                text, source = await asyncio.to_thread(self._sources.fetch, str(body["spec_url"]))
            document = text if isinstance(text, dict) else self._sources.document(text)
            spec = apis.parse_spec(document, source)
            kinds = {"spec": "text", "spec_path": "file", "spec_url": "address"}
            address = str(body.get(way)) if way in ("spec_path", "spec_url") else ""
            where = {"kind": kinds[way], "address": address}
        if body.get("base_url"):
            spec = replace(spec, base_url=apis.check_url(body["base_url"]))
        if not spec.base_url.startswith(("http://", "https://")):
            raise ApiError("The API's address is not known: give its base URL (https://...).")
        if "auth" in body:
            spec = replace(spec, auth=apis.check_auth(body.get("auth")))
        return spec, document, where

    async def _plan(self, body: Any) -> _Plan:
        if not isinstance(body, dict):
            raise ApiError('Send {"spec_url": "https://.../openapi.json"} (or spec, spec_path, form).')
        spec, document, where = await self._read(body)
        names = apis.names_for(str(body.get("name") or spec.title))
        folder = self._library.folder_for(names.module.removeprefix("API_"))  # the library's apis/<name>/
        path = self._files.path(folder, names.file)
        text = api_clients.write(spec, names)
        old = self._files.read(path)
        old_mark = api_clients.read_mark(old) if old is not None else None
        taken = ""
        if old is not None and old_mark is None:
            taken = (
                f"{names.file} is in {folder} already, and Add API did not make it: name the API "
                "something else."
            )
        existing: dict[str, Any] | None = None
        try:
            found = self._connections.details(names.connection)
        except LookupError:
            found = None
        except ValueError:  # a blade of that name, not a connection
            found, taken = None, taken or f"A blade is named {names.connection}: name the API something else."
        if found is not None:
            if apis.is_connection_for(str(found.get("code") or ""), names.module):
                existing = found
            else:
                taken = taken or f"A connection is named {names.connection}: name the API something else."
        return _Plan(spec, names, folder, path, text, old, old_mark, existing, taken, document, where)

    async def preview(self, body: Any) -> dict[str, Any]:
        """What Add would do, written nowhere."""
        return (await self._plan(body)).to_json()

    async def make_into_blades(self, name: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Make into blades: an older API connection (API_<name>.py beside a project, before the library)
        made into this computer's library (its API blade, a web call blade per operation), from the
        document it was made from: the address it was read from, an openapi.json beside it, or the one the
        user gives ({"spec_path" | "spec_url" | "spec"}). Only when asked; the old file is left as it is,
        and the connection keeps its name and its variables' sources."""
        given = body if isinstance(body, dict) else {}
        try:
            found = self._connections.details(name)
        except (LookupError, ValueError):
            raise NotFound(f"There is no connection called {name}.") from None
        made = apis.made_file_of(str(found.get("code") or ""))
        if made is None:
            raise ApiError(f"{name} is not an API connection Add API made.")
        _, path = made
        mark = api_clients.read_mark(self._files.read(path) or "")
        if mark is None:
            raise NotFound(f"{name}'s made file is not where its code says ({path}).")
        beside = self._files.path(apis.folder_of(path), "openapi.json")
        way = {k: given[k] for k in ("spec_path", "spec_url", "spec") if given.get(k)}
        if not way:
            way = (
                apis.make_into_blades_source(mark, beside if self._files.read(beside) is not None else None)
                or {}
            )
        if not way:
            raise ApiError(
                f"{name} was made from a document Add API did not keep: give its OpenAPI document "
                "(spec_path or spec_url) to make it into blades."
            )
        request: dict[str, Any] = {"name": str(found.get("name") or name)} | way
        if mark.get("auth"):
            request["auth"] = mark["auth"]
        if str(mark.get("base_url") or "").startswith(("http://", "https://")):
            request["base_url"] = mark["base_url"]  # as it was made (a document's relative one was resolved)
        added = await self.add(request, who)
        return added | {"made_into_blades": request["name"], "left": path}

    async def add(self, body: Any, who: str = "user") -> dict[str, Any]:
        """API_<name>.py written and its connection saved, in one step."""
        plan = await self._plan(body)
        if plan.taken:
            raise Conflict(plan.taken)
        answer = plan.to_json()
        try:
            return answer | await self._added(plan, body, who)
        except Exception:
            if plan.existing is None:  # a new API that did not go through leaves nothing of itself
                await self._undo(plan, who)
            raise

    async def _undo(self, plan: _Plan, who: str) -> None:
        """A new API's add that failed part way: its web call blades, its connection and its folder go."""
        api = plan.names.connection
        names = [web_calls.name_of(api, op.name) for op in plan.spec.operations]
        for name in (*names, api):
            try:
                await self._blades.remove(name, who)
            except Exception:  # noqa: S110 (not made yet: nothing to take away)
                pass
        self._library.remove(plan.folder)

    async def _added(self, plan: _Plan, body: Any, who: str) -> dict[str, Any]:
        self._library.write(plan.path, plan.text)  # the library's apis/<name>/
        tables = len(plan.spec.tables())
        count = len(plan.spec.operations)
        description = f"{plan.names.file}: {count} operations, {tables} table{'' if tables == 1 else 's'}"
        connection = apis.connection_body(
            plan.names,
            plan.path,
            plan.spec.auth,
            description,
            sources=body.get("variables") if "variables" in body or plan.existing is None else None,
            secrets=body.get("secrets"),
            row_limit=body.get("row_limit"),
        )
        previous = plan.names.connection if plan.existing is not None else None
        connection["tags"] = [web_calls.API_TAG]
        self.busy.add(plan.names.connection.casefold())
        try:
            calls = await self._web_calls(plan, who)
        finally:
            self.busy.discard(plan.names.connection.casefold())
        switched_on = web_calls.table_calls(calls, plan.names.connection)
        connection.pop("catalog", None)  # an API's tables are its Return-as-table web calls: none yet
        connection.pop("read", None)
        if switched_on:
            catalog, read = web_calls.tables_boxes(switched_on)
            connection["catalog"] = {"language": "python", "command": "api = conn\n" + catalog}
            connection["read"] = {"command": "api = conn\n" + read}
        if previous is None:
            connection["library_folder"] = self._library_relative(plan.folder)
        saved = await self._connections.save(connection, previous, who)
        self._write_description(plan, body.get("check") is True)
        self.ws.audit.write(
            who, "add_api", f"{plan.names.connection}: {plan.path}", connection=plan.names.connection
        )
        return {"saved": saved, "written": plan.path, "web_calls": [c["name"] for c in calls]}

    def _library_relative(self, folder: str) -> str:
        return "apis/" + folder.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]

    def _write_description(self, plan: _Plan, check: bool) -> None:
        """openapi.json (the document as read, or a form's operations as one) and source.json (where it
        came from, when, and the check-for-changes switch): text only, no secret, no response."""
        document = plan.document if plan.document is not None else api_explorer.openapi_of(plan.spec)
        text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        self._library.write(self._library.path(plan.folder, "openapi.json"), text)
        where = dict(plan.source or {"kind": "form", "address": ""})
        earlier = self._library.read(self._library.path(plan.folder, "source.json"))
        try:
            kept = json.loads(earlier) if earlier else {}
        except ValueError:
            kept = {}
        source = {
            "api": plan.names.connection,
            "kind": where.get("kind", "form"),
            "address": where.get("address", ""),
            "check": bool(kept.get("check")) if not check else True,
            "read_at": self._now(),
        }
        self._library.write(
            self._library.path(plan.folder, "source.json"), json.dumps(source, indent=2) + "\n"
        )

    async def _web_calls(self, plan: _Plan, who: str) -> list[dict[str, Any]]:
        """One web call blade per operation (Return as table off), each in the API's folder; a web call
        made before keeps its inputs, body and table settings; one whose operation is gone goes."""
        api = plan.names.connection
        made: list[dict[str, Any]] = []
        wanted = {web_calls.name_of(api, op.name): op for op in plan.spec.operations}
        for name, op in wanted.items():
            try:
                before = self._blades.get(name)
            except (KeyError, LookupError, ValueError):
                before = None
            call: dict[str, Any] = {
                "api": api,
                "operation": op.name,
                "method": op.method,
                "path": op.path,
                "as_table": False,
                "paging_by": op.paging(),
            }
            inputs: dict[str, Any] = {}
            for p in op.parameters:  # nothing typed yet: a required one left empty is named when read
                if p.required:
                    inputs.setdefault(p.place, {})[p.name] = None
            body: Any = None
            if before is not None and getattr(before, "web_call", None):
                kept = dict(before.web_call)
                call |= {k: kept[k] for k in kept if k not in ("api", "operation", "method", "path")}
                said = web_calls.values_of(before.code)
                inputs = said["inputs"] or inputs
                body = said["body"]
            blade = {
                "name": name,
                "kind": "other",
                "code": web_calls.code(api, op.method, op.path, op.summary, inputs, body, call),
                "variable": "result",
                "description": (op.summary or f"{op.method} {op.path}")[:300],
                "tags": [web_calls.API_TAG, web_calls.TAG],
                "web_call": call,
            }
            if before is None:
                blade["library_folder"] = self._library_relative(plan.folder)
            await self._blades.save(blade, name if before is not None else None, who)
            made.append(blade)
        if plan.old is not None:
            for module_method in api_clients.methods(plan.old):
                gone = web_calls.name_of(api, module_method)
                if gone not in wanted:
                    try:
                        await self._blades.remove(gone, who)
                    except (KeyError, LookupError, ValueError):
                        pass
        return made

    async def try_it(self, body: Any) -> dict[str, Any]:
        """Try it: one operation's first rows (`"try": "list_orders"`), before Add. The client is run
        pasted into a draft connection (written nowhere); `"values"` are typed for this run only, any
        other variable is read from this computer's environment. Nothing is saved, no value comes back."""
        plan = await self._plan(body)
        operation = body.get("try")
        if not isinstance(operation, str) or not operation:
            raise ApiError('Name the operation to try: {"try": "list_orders"}.')
        schema, table = apis.tried_table(plan.spec, operation)
        inlined = api_clients.inline(plan.names.module, plan.text)
        draft = apis.try_connection(plan.names, inlined, plan.spec.auth, body.get("values"))
        place = {"database": "", "schema": schema, "table": table}
        try:
            read = await self._connections.read_draft(draft, place, apis.TRY_ROWS)
        except RuntimeError as error:  # the run's own refusal (no key, a 401): the API's answer, said
            said = str(error).replace(  # Add API's form has no Environment variables: its Sign in has
                "choose where it comes from under Environment variables.",
                "type it under Sign in to try it (or set it on this computer).",
            )
            raise ApiError(said) from None
        return {"operation": operation, "table": table, **read}

    def inline(self, folder: str, codes: Iterable[str]) -> list[dict[str, str]]:
        """The made API clients the code imports (import API_Orders), found beside it in `folder`, each
        as code to paste into an exported script or notebook: [{"module", "code"}], in the order first
        imported. A file Add API did not make, or one not there, is left out (the import stays as it is)."""
        wanted: list[str] = []
        for code in codes:
            wanted += [m for m in api_clients.imported(code) if m not in wanted]
        if not wanted:
            return []
        found = self._files.clients(folder)
        for module in wanted:  # the library's own (apis/<name>/API_<name>.py), whatever folder the code is in
            if module not in found:
                found |= self._files.clients(self._library.folder_for(module.removeprefix("API_")))
        return [
            {"module": module, "code": api_clients.inline(module, found[module])}
            for module in wanted
            if module in found and api_clients.is_made(found[module])
        ]
