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
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from swissarmybench.domain import api_clients, apis
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
        default_folder: Callable[[], str],
    ) -> None:
        self.ws = ws
        self._files = files
        self._sources = sources
        self._connections = connections
        self._default_folder = default_folder  # the Workbench's own folder, when no project is open

    def choices(self) -> dict[str, Any]:
        return apis.choices()

    async def _spec(self, body: dict[str, Any]) -> Spec:
        given = [k for k in ("spec", "spec_path", "spec_url", "form") if body.get(k) not in (None, "")]
        if len(given) != 1:
            raise ApiError(
                'Give the API one way: "spec" (an OpenAPI document\'s text), "spec_path" (its file), '
                '"spec_url" (its address) or "form" (a base URL and endpoints).'
            )
        way = given[0]
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
        if body.get("base_url"):
            spec = replace(spec, base_url=apis.check_url(body["base_url"]))
        if not spec.base_url.startswith(("http://", "https://")):
            raise ApiError("The API's address is not known: give its base URL (https://...).")
        if "auth" in body:
            spec = replace(spec, auth=apis.check_auth(body.get("auth")))
        return spec

    async def _plan(self, body: Any) -> _Plan:
        if not isinstance(body, dict):
            raise ApiError('Send {"spec_url": "https://.../openapi.json"} (or spec, spec_path, form).')
        spec = await self._spec(body)
        names = apis.names_for(str(body.get("name") or spec.title))
        try:
            folder = self._files.folder(str(body.get("folder") or self._default_folder()))
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
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
        return _Plan(spec, names, folder, path, text, old, old_mark, existing, taken)

    async def preview(self, body: Any) -> dict[str, Any]:
        """What Add would do, written nowhere."""
        return (await self._plan(body)).to_json()

    async def add(self, body: Any, who: str = "user") -> dict[str, Any]:
        """API_<name>.py written and its connection saved, in one step."""
        plan = await self._plan(body)
        if plan.taken:
            raise Conflict(plan.taken)
        answer = plan.to_json()
        self._files.write(plan.path, plan.text)
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
        saved = await self._connections.save(connection, previous, who)
        self.ws.audit.write(
            who, "add_api", f"{plan.names.connection}: {plan.path}", connection=plan.names.connection
        )
        return answer | {"saved": saved, "written": plan.path}

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
        return [
            {"module": module, "code": api_clients.inline(module, found[module])}
            for module in wanted
            if module in found and api_clients.is_made(found[module])
        ]
