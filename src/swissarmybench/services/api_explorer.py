"""The APIs page (the owner, 2026-11-17: "Apis need thier own page so they can be imported managed,
refreshed when the api changes and searchable"; "from the ApI page to quickly open a screen, Author an
API call using an apis payload, then the results will show up in the structure page retaining their
lineage"). APIs are this computer's library, never a project's; they are not on the Connections page.

  cards      every API in the library (apis/<name>/): its title, base address, sign-in type (never a
             secret's value), operations, tables (its web calls with Return as table on), calls this
             session, where it was read from and when, the check-for-changes switch; and an older API
             connection (API_<name>.py beside a project, before the library) marked for Make into blades
  explore    an API's operations (inputs, outputs, examples), its schemas (domain/api_explorer.py)
  search     one box across every API and operation
  send       an authored call (inputs and body) run through its web call blade's code, after its API
             blade (secrets resolved as the blade resolves them, never shown): the answer opens in
             Structures, its origin the call; Run again sends the same call
  save       an authored call saved as its web call blade; Return as table on or off (the one gate to
             DuckDB SQL), its records or rows path, header, columns and DuckDB's conversion
  refresh    the source read again (an address or a file the user gave): what changed, said before it is
             applied; apply writes it (domain/apis.py re-import)
  manage     rename (the blades renamed; the file and its variables stay), delete (asks; the agent's
             waits for the user's Allow; the code that uses it listed first)
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import api_clients, api_explorer, apis, web_calls
from swissarmybench.domain import write_rows as write_rules
from swissarmybench.domain.apis import ApiError
from swissarmybench.domain.structures import get as structure_get
from swissarmybench.services.apis import Apis
from swissarmybench.services.ports import BACKGROUND
from swissarmybench.services.workspace import NotFound, Refused, Workspace

_SECRETISH = ("key", "token", "secret", "password", "authorization", "signature", "cookie")


class Library(Protocol):
    def folders(self) -> list[str]: ...

    def path(self, folder: str, name: str) -> str: ...

    def read(self, path: str) -> str | None: ...

    def write(self, path: str, text: str) -> None: ...

    def find(self, folder: str, pattern: str) -> list[str]: ...

    def remove(self, folder: str) -> None: ...


class SpecSource(Protocol):
    def read_file(self, path: str) -> tuple[str, str]: ...

    def fetch(self, url: str) -> tuple[str, str]: ...

    def document(self, text: str) -> dict[str, Any]: ...


class Approvals(Protocol):
    async def ask(self, dataset: str, action: str, detail: str) -> bool: ...


class Explorer:
    def __init__(
        self,
        ws: Workspace,
        add: Apis,
        library: Library,
        sources: SpecSource,
        blades: Any,  # services/blades.py BladeService: get, save, remove, listing, run_read
        connections: Any,  # services/connections.py ConnectionService: details, save
        usage: Any,  # services/connection_usage.py ConnectionUsage: calls, references
        structures: Any,  # services/structures.py Structures: from_api, show, describe
        approvals: Approvals,
        now: Callable[[], str],
        to_thread: Callable[..., Awaitable[Any]],
        reader: Any = None,  # adapters/datasets.py: query_table(cursor, sql), an open table's rows
    ) -> None:
        self._reader = reader
        self.ws = ws
        self._add = add
        self._library = library
        self._sources = sources
        self._blades = blades
        self._connections = connections
        self._usage = usage
        self._structures = structures
        self._approvals = approvals
        self._now = now
        self._thread = to_thread
        self._refreshed: dict[str, dict[str, Any]] = {}  # an API's re-read document, until applied
        self._answers: dict[tuple[str, str], Any] = {}  # (api, operation) -> the last answer's schema
        # The Variables page (services/variables.py, set once built): a typed input's variable (12.7).
        self.variables: Any = None

    # ===== the library =====

    def _json(self, path: str) -> Any:
        text = self._library.read(path)
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    def _apis(self) -> list[dict[str, Any]]:
        found = []
        for folder in self._library.folders():
            made = self._library.find(folder, "API_*.py")
            mark = api_clients.read_mark(self._library.read(made[0]) or "") if made else None
            source = self._json(self._library.path(folder, "source.json")) or {}
            name = str(source.get("api") or (mark or {}).get("name") or "")
            if not name:
                continue
            found.append(
                {
                    "name": name,
                    "folder": folder,
                    "file": made[0] if made else None,
                    "mark": mark or {},
                    "source": source,
                }
            )
        return found

    def _api(self, name: str) -> dict[str, Any]:
        for api in self._apis():
            if api["name"].casefold() == str(name).casefold():
                return api
        raise NotFound(f"There is no API called {name} in the library: apis_list names them.")

    def _document(self, api: Mapping[str, Any]) -> dict[str, Any]:
        doc = self._json(self._library.path(str(api["folder"]), "openapi.json"))
        if not isinstance(doc, dict):
            raise NotFound(f"{api['name']} has no openapi.json: Refresh it, or add it again.")
        return doc

    def _calls(self, name: str) -> dict[str, dict[str, Any]]:
        """Its web call blades by operation: {operation: the blade's JSON}."""
        found: dict[str, dict[str, Any]] = {}
        for blade in self._blades.listing()["blades"]:
            call = blade.get("web_call") or {}
            if str(call.get("api") or "").casefold() == name.casefold():
                found[str(call.get("operation"))] = self._blades.get(str(blade["name"])).to_json()
        return found

    def _explored(self, name: str) -> dict[str, Any]:
        api = self._api(name)
        doc = self._document(api)
        spec = apis.parse_spec(doc, "")
        explored = api_explorer.explore(doc, spec)
        calls = self._calls(api["name"])
        for op in explored["operations"]:
            blade = calls.get(op["id"])
            call = (blade or {}).get("web_call") or {}
            said = web_calls.values_of(str((blade or {}).get("code") or ""))
            op["blade"] = blade.get("name") if blade else None
            op["as_table"] = bool(call.get("as_table"))
            op["table"] = (
                {
                    k: call.get(k)
                    for k in ("shape", "records", "header", "flatten", "paging", "columns", "conversion")
                }
                if call
                else None
            )
            op["inputs"] = said.get("inputs") or {}
            op["body_saved"] = said.get("body")
            op["sql_name"] = f"[{api['name']}].{op['id']}" if call.get("as_table") else None
            answered = self._answers.get((api["name"].casefold(), op["id"]))
            if answered is not None and not any(
                r.get("schema") for r in op["responses"] if r["status"].startswith("2")
            ):
                op["responses"].append(
                    {
                        "status": "last answer",
                        "description": "The shape of the last answer",
                        "media": "application/json",
                        "schema": answered,
                        "example": None,
                    }
                )
        base = api["mark"].get("base_url") or explored["base_url"]
        explored["auth"] = (api["mark"].get("auth") or {}).get("type") or explored["auth"]
        return explored | {
            "name": api["name"],
            "source": api["source"],
            "folder": api["folder"],
            "base_url": base,
        }

    # ===== the cards =====

    def listing(self) -> dict[str, Any]:
        cards = []
        for api in self._apis():
            try:
                doc = self._document(api)
                spec = apis.parse_spec(doc, "")
                operations, title, version, problem = len(spec.operations), spec.title, spec.version, None
            except (NotFound, ApiError) as error:
                operations, title, version, problem = 0, api["name"], "", str(error)
            calls = self._calls(api["name"])
            counted = self._usage.calls(api["name"])
            cards.append(
                {
                    "name": api["name"],
                    "title": title,
                    "version": version,
                    "base_url": api["mark"].get("base_url") or "",
                    "auth": (api["mark"].get("auth") or {}).get("type", "none"),
                    "operations": operations,
                    "tables": sorted(
                        op for op, b in calls.items() if (b.get("web_call") or {}).get("as_table")
                    ),
                    "calls": counted.to_json() if counted else {"total": 0},
                    "source": {k: api["source"].get(k) for k in ("kind", "address", "read_at", "check")},
                    "file": api["file"],
                    "problem": problem,
                }
            )
        older = []
        for blade in self._blades.listing()["blades"]:
            if blade.get("template") != "python":
                continue
            if any(c["name"].casefold() == str(blade["name"]).casefold() for c in cards):
                continue
            code = str(self._blades.get(str(blade["name"])).code or "")  # the listing carries no code
            if "spec_from_file_location(" in code and "API_" in code:
                older.append({"name": blade["name"], "older": True})
        return {"apis": cards, "older": older}

    def document_of(self, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """An API's OpenAPI document and its sign-in's settings (its type and names, never a secret):
        what an extension makes a custom connector of."""
        api = self._api(name)
        return self._document(api), dict(api["mark"].get("auth") or {"type": "none"})

    def describe(self, name: str, operation: str | None = None) -> dict[str, Any]:
        explored = self._explored(name)
        if not operation:
            return explored
        op = next((o for o in explored["operations"] if o["id"] == operation), None)
        if op is None:
            raise NotFound(f"{name} has no operation {operation}.")
        return {"name": explored["name"], "base_url": explored["base_url"], "operation": op}

    def search(self, query: str) -> dict[str, Any]:
        explored = []
        for api in self._apis():
            try:
                explored.append((api["name"], self._explored(api["name"])))
            except (NotFound, ApiError):
                continue
        return {"query": query, "results": api_explorer.search(explored, query)}

    # ===== sending a call =====

    def _api_blade(self, name: str) -> Any:
        try:
            return self._blades.get(name)
        except (KeyError, LookupError, ValueError):
            raise NotFound(f"{name}'s API blade is not here: add the API again.") from None

    def _operation(self, explored: Mapping[str, Any], operation: str) -> dict[str, Any]:
        op = next((o for o in explored["operations"] if o["id"] == operation), None)
        if op is None:
            raise NotFound(f"{explored['name']} has no operation {operation}.")
        return dict(op)

    def _inputs(self, op: Mapping[str, Any], values: Any) -> tuple[dict[str, Any], Any]:
        """The typed inputs, checked against the operation (a required one missing says so), by place."""
        checked = api_explorer.call(op, values)
        inputs: dict[str, Any] = {}
        for place, key in (
            ("path", "params"),
            ("query", "query"),
            ("header", "headers"),
            ("cookie", "cookies"),
        ):
            if checked.get(key):
                inputs[place] = checked[key]
        return inputs, checked.get("body")

    async def send(self, name: str, operation: str, body: Any, who: str = "user") -> dict[str, Any]:
        """{"inputs": {...} | flat values, "body"?}: the call run, its answer opened in Structures."""
        given = body if isinstance(body, dict) else {}
        explored = self._explored(name)
        op = self._operation(explored, operation)
        values = dict(given.get("inputs") or {}) | ({"body": given["body"]} if "body" in given else {})
        typed, _ = self._inputs(op, values)
        if self.variables is not None:  # an input's ${NAME} (12.7): its value sent, the typed text kept
            values = await self.variables.resolve_all(values, f"{explored['name']} {op['id']}")
        inputs, sent_body = self._inputs(op, values)
        value, origin = await self._run(explored["name"], op, inputs, sent_body, who, shown=typed)
        title = str(given.get("name") or f"{explored['name']} {op['id']}")
        opened = await self._structures.from_api(title, value, origin, who)
        self.ws.audit.write(
            who, "api_call", None, api=explored["name"], operation=op["id"], status=origin["status"]
        )
        return {
            "status": origin["status"],
            "ms": origin["ms"],
            "headers": origin["headers"],
            "said": origin.get("said") or "",
            "structure": opened["id"],
            "name": opened["name"],
            "suggest_table": web_calls.detect(value),
        }

    async def _run(
        self,
        api: str,
        op: Mapping[str, Any],
        inputs: dict[str, Any],
        body: Any,
        who: str,
        shown: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        source = web_calls.code(api, op["method"], op["path"], "", inputs, body, None)
        command = "api = conn\n" + web_calls.send_command(source)
        answer = await self._blades.run_read(self._api_blade(api), command, "", {})
        rows = answer["table"].to_pylist()
        said = api_explorer.answer(rows[0] if rows else {})
        value = said["body"]
        if said["ok"] and value is not None:
            self._answers[(api.casefold(), op["id"])] = api_explorer.response_schema(value)
        origin = {
            "kind": "api",
            "api": api,
            "operation": op["id"],
            "method": op["method"],
            "path": op["path"],
            "inputs": _shown_inputs(inputs if shown is None else shown),
            "body": body,
            "at": self._now(),
            "status": said["status"],
            "ms": said["ms"],
            "headers": said["headers"],
            "said": said["said"],
        }
        return value, origin

    async def run_again(self, origin: dict[str, Any], who: str) -> tuple[Any, dict[str, Any]]:
        """Structures' Run again: the same call (its inputs and body as sent) sent again."""
        explored = self._explored(str(origin.get("api")))
        op = self._operation(explored, str(origin.get("operation")))
        inputs = {k: dict(v) for k, v in (origin.get("inputs") or {}).items() if isinstance(v, dict)}
        if any(v == "(hidden)" for place in inputs.values() for v in place.values()):
            raise Refused("A sign-in input was hidden when it was sent: send it again from the APIs page.")
        return await self._run(explored["name"], op, inputs, origin.get("body"), who)

    # ===== saving a web call =====

    async def save_call(self, name: str, operation: str, body: Any, who: str = "user") -> dict[str, Any]:
        """The authored call as its web call blade: {"inputs"?, "body"?, "as_table"?, "records"?, "shape"?,
        "header"?, "columns"?, "flatten"?, "paging"?, "conversion"?, "structure"? (a response read for the
        table's settings)}. Return as table is on only when the user (or the agent) says so."""
        given = body if isinstance(body, dict) else {}
        explored = self._explored(name)
        op = self._operation(explored, operation)
        blade_name = op.get("blade") or web_calls.name_of(explored["name"], op["id"])
        try:
            before = self._blades.get(blade_name).to_json()
        except (KeyError, LookupError, ValueError):
            before = None
        call = dict((before or {}).get("web_call") or {}) or {
            "api": explored["name"],
            "operation": op["id"],
            "method": op["method"],
            "path": op["path"],
        }
        if "inputs" in given or "body" in given:
            values = dict(given.get("inputs") or {}) | ({"body": given["body"]} if "body" in given else {})
            inputs, sent_body = _all_inputs(op, values)
        else:
            said = web_calls.values_of(str((before or {}).get("code") or ""))
            inputs, sent_body = said["inputs"] or {}, said["body"]
        for key in ("as_table", "records", "shape", "header", "columns", "flatten", "paging", "conversion"):
            if key in given:
                call[key] = given[key]
        if given.get("as_table") and given.get("structure"):
            # Return as table... on a Structures result: its settings found in that answer (the list
            # clicked: `at`), the user's own words winning.
            found = self._structures.node(str(given["structure"]), "$")
            at = str(given.get("at") or "$")
            guessed = web_calls.detect(structure_get(found, at) if at != "$" else found) or {}
            if guessed and at != "$" and guessed.get("records", "$") != "$":
                guessed["records"] = at + guessed["records"][1:]
            elif guessed and at != "$":
                guessed["records"] = at
            call |= {
                k: v
                for k, v in guessed.items()
                if k in ("shape", "records", "header", "columns") and k not in given
            }
        if "records" in given or "shape" in given or "columns" in given or "header" in given:
            call["conversion"] = given.get("conversion") or ""  # made again from the settings
        call = web_calls.check_web_call(call)
        blade = {
            "name": blade_name,
            "kind": "other",
            "code": web_calls.code(
                explored["name"], op["method"], op["path"], op.get("summary") or "", inputs, sent_body, call
            ),
            "variable": "result",
            "description": (op.get("summary") or f"{op['method']} {op['path']}")[:300],
            "tags": [web_calls.API_TAG, web_calls.TAG],
            "web_call": call,
        }
        if before is None:
            blade["library_folder"] = (
                "apis/" + str(explored["folder"]).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
            )
        saved = await self._blades.save(blade, blade_name if before else None, who)  # its API's tables follow
        return {
            "blade": saved.get("name", blade_name),
            "web_call": call,
            "sql_name": f"[{explored['name']}].{op['id']}" if call["as_table"] else None,
        }

    def _form(self, name: str) -> dict[str, Any]:
        """The API blade as the connections form saves it (its own fields, its variables' sources)."""
        saved = self._blades.get(name).to_json()
        keys = (
            "name",
            "kind",
            "template",
            "variable",
            "code",
            "description",
            "tags",
            "row_limit",
            "variables",
        )
        return {k: saved[k] for k in keys if saved.get(k) is not None}

    async def tables_changed(self, name: str, who: str = "app") -> None:
        """The API blade's List the tables and Read a table, made again from its Return-as-table calls
        (none: it has no tables, and no boxes)."""
        if name.casefold() in self._add.busy:
            return  # Add API makes them once, when it saves the API blade
        try:
            form = self._form(name)
        except (KeyError, LookupError, ValueError):
            return  # not an API blade (yet)
        listed = [b for b in self._calls(name).values()]
        found = web_calls.table_calls(listed, name)
        if found:
            catalog, read = web_calls.tables_boxes(found)
            form["catalog"] = {"language": "python", "command": "api = conn\n" + catalog}
            form["read"] = {"command": "api = conn\n" + read}
        await self._connections.save(form, name, who)

    # ===== Write rows with this call =====

    async def _input_rows(self, given: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str]:
        """The rows to write: an open table's (a grid's dataset), or a Structures document's list."""
        if given.get("table"):
            name = str(given["table"])
            info = self.ws.store.get(name)
            if info is None or self._reader is None:
                raise NotFound(f"{name} is not an open table.")
            table = await self.ws.workers.run(
                BACKGROUND,
                self._reader.query_table,
                self.ws.store.cursor(),
                f"SELECT * FROM {info.table}",  # noqa: S608 (a quoted name)
            )
            return [dict(r) for r in table.to_pylist()], name
        if given.get("structure"):
            node = self._structures.node(str(given["structure"]), str(given.get("path") or "$"))
            if not isinstance(node, list) or not all(isinstance(r, dict) for r in node):
                raise ApiError("That is not a list of records: point at one (path).")
            return [dict(r) for r in node], str(given["structure"])
        raise ApiError('Name the rows: {"table": an open table} or {"structure": an id, "path": "$.items"}.')

    async def write_rows(self, name: str, operation: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Write a table's rows with this call: {"table" | "structure"+"path", "mapping"? (else matched by
        name), "batch"?, "batch_size"?, "key_columns"?, "response_field"?, "dry_run"? (true by default),
        "retry"? (a results structure: its failed rows only)}. A dry run sends nothing."""
        given = dict(body) if isinstance(body, dict) else {}
        explored = self._explored(name)
        op = self._operation(explored, operation)
        if op["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            raise ApiError(
                f"{op['method']} {op['path']} does not write: rows go to a POST, PUT, PATCH or DELETE."
            )
        retried: list[int] | None = None
        if given.get("retry"):
            earlier = self._structures.describe(str(given["retry"]))
            origin = earlier.get("origin") or {}
            write = origin.get("write") or {}
            if origin.get("operation") != op["id"] or not write:
                raise ApiError("That is not this call's results: Retry the failed rows from its results.")
            retried = write_rules.failed(self._structures.node(str(given["retry"]), "$"))
            given = {**write.get("request", {}), "dry_run": given.get("dry_run", False)}
        rows, source = await self._input_rows(given)
        columns = list(dict.fromkeys(k for r in rows[:500] for k in r))
        body_tree = (op.get("body") or {}).get("schema")
        mapping = (
            write_rules.check_mapping(given["mapping"], columns)
            if given.get("mapping")
            else write_rules.auto_map(columns, body_tree, op.get("parameters") or [])
        )
        settings = write_rules.check_settings(given)
        lacking = write_rules.missing(mapping, body_tree, op.get("parameters") or [])
        chosen = rows if retried is None else [rows[n] for n in retried if n < len(rows)]
        answer: dict[str, Any] = {
            "mapping": mapping,
            "missing": lacking,
            "columns": columns,
            "settings": settings,
        }
        if given.get("dry_run", True) is not False:
            return answer | {"dry_run": True} | write_rules.dry_run(chosen, mapping, settings)
        if lacking:
            raise ApiError(f"Map every required field first: {', '.join(lacking)}.")
        command = "\n".join(
            [
                "api = conn",
                "import json as _json",
                f"_rows = _json.loads({json.dumps(json.dumps(chosen, default=str))})",
                f"_answers = api.write_rows({json.dumps(op['method'])}, {json.dumps(op['path'])}, _rows, "
                f"_json.loads({json.dumps(json.dumps(mapping))}),",
                f"    _json.loads({json.dumps(json.dumps(settings))}), False)",
                "[{'answers': _json.dumps(_answers, default=str)}]",
            ]
        )
        started = self._now()
        ran = await self._blades.run_read(self._api_blade(explored["name"]), command, "", {})
        answers = json.loads(ran["table"].to_pylist()[0]["answers"])
        result_rows = write_rules.results(chosen, answers, settings)
        if retried is not None:
            for r in result_rows:
                r["row"] = retried[r["row"]]
        good = sum(1 for r in result_rows if 200 <= int(r["status"]) < 300)
        origin = {
            "kind": "api",
            "api": explored["name"],
            "operation": op["id"],
            "method": op["method"],
            "path": op["path"],
            "at": started,
            "status": 200 if good == len(result_rows) else 207,
            "said": f"{good} of {len(result_rows)} rows written",
            "input": source,
            "write": {
                "rows": len(chosen),
                "calls": len(answers),
                "request": {
                    k: v
                    for k, v in given.items()
                    if k
                    in (
                        "table",
                        "structure",
                        "path",
                        "mapping",
                        "batch",
                        "batch_size",
                        "key_columns",
                        "response_field",
                    )
                }
                | {"mapping": mapping},
            },
        }
        title = f"{explored['name']} {op['id']} results"
        opened = await self._structures.from_api(title, result_rows, origin, who)
        grid = await self._structures.open_as_grid(opened["id"], {"path": "$"}, who)
        self.ws.audit.write(
            who, "api_write_rows", None, api=explored["name"], operation=op["id"], rows=len(chosen)
        )
        return {
            "written": good,
            "failed": len(result_rows) - good,
            "rows": len(chosen),
            "calls": len(answers),
            "structure": opened["id"],
            "grid": grid.get("grid"),
            "dataset": grid.get("dataset"),
        }

    async def save_write(self, name: str, operation: str, body: Any, who: str = "user") -> dict[str, Any]:
        """The write saved as its web call blade, mode "write rows" (its mapping in the header)."""
        given = dict(body) if isinstance(body, dict) else {}
        explored = self._explored(name)
        op = self._operation(explored, operation)
        blade_name = web_calls.name_of(explored["name"], f"write_{op['id']}")[:64]
        settings = write_rules.check_settings(given)
        mapping = write_rules.check_mapping(given.get("mapping") or {})
        call = web_calls.check_web_call(
            {
                "api": explored["name"],
                "operation": op["id"],
                "method": op["method"],
                "path": op["path"],
                "mode": "write rows",
                "mapping": mapping,
                **settings,
            }
        )
        try:
            before = self._blades.get(blade_name)
        except (KeyError, LookupError, ValueError):
            before = None
        blade = {
            "name": blade_name,
            "kind": "other",
            "code": write_rules.code(
                explored["name"],
                op["method"],
                op["path"],
                mapping,
                settings,
                str(given.get("table") or "rows"),
            ),
            "variable": "result",
            "description": f"Write rows with {op['method']} {op['path']}",
            "tags": [web_calls.API_TAG, web_calls.TAG],
            "web_call": call,
        }
        if before is None:
            blade["library_folder"] = (
                "apis/" + str(explored["folder"]).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
            )
        saved = await self._blades.save(blade, blade_name if before is not None else None, who)
        return {"blade": saved.get("name", blade_name), "web_call": call}

    # ===== refresh =====

    async def refresh(self, name: str, who: str = "user") -> dict[str, Any]:
        """The source read again: what changed (operations added, removed, changed; their parameters and
        fields), nothing written until apply."""
        api = self._api(name)
        source = api["source"]
        kind, address = source.get("kind"), str(source.get("address") or "")
        if kind not in ("address", "file") or not address:
            raise ApiError(
                f"{api['name']} was {'made with the form' if kind == 'form' else 'pasted'}: "
                "Refresh reads an address or a file it was added from."
            )
        if kind == "address":
            text, where = await self._thread(self._sources.fetch, address)
        else:
            text, where = await self._thread(self._sources.read_file, address)
        new_doc = self._sources.document(text)
        new_spec = apis.parse_spec(new_doc, where or address)
        old_doc = self._document(api)
        old = api_explorer.explore(old_doc, apis.parse_spec(old_doc, where or address))
        new = api_explorer.explore(new_doc, new_spec)
        diff = api_explorer.diff(old, new)
        self._refreshed[api["name"].casefold()] = {"kind": kind, "address": address}
        self.ws.audit.write(who, "api_refresh", None, api=api["name"], changed=diff["any"])
        return {"name": api["name"], "diff": diff, "read_at": self._now()}

    async def apply_refresh(self, name: str, who: str = "user") -> dict[str, Any]:
        api = self._api(name)
        source = self._refreshed.pop(api["name"].casefold(), None) or {}
        if not source:
            raise ApiError("Refresh it first: apply writes what Refresh showed.")
        key = "spec_url" if source["kind"] == "address" else "spec_path"
        body = {
            key: source["address"],
            "name": api["name"],
            "auth": api["mark"].get("auth") or {"type": "none"},
        }
        done = await self._add.add(body, who)
        return {"name": api["name"], "applied": True, "web_calls": done.get("web_calls", [])}

    async def set_check(self, name: str, on: bool) -> dict[str, Any]:
        api = self._api(name)
        source = dict(api["source"]) | {"check": bool(on)}
        self._library.write(
            self._library.path(api["folder"], "source.json"), json.dumps(source, indent=2) + "\n"
        )
        return {"name": api["name"], "check": bool(on)}

    # ===== rename, delete =====

    def references(self, name: str) -> list[dict[str, Any]]:
        found, _ = self._usage.references(name)
        refs = [r.to_json() for r in found]
        for blade in self._calls(name).values():
            more, _ = self._usage.references(str(blade["name"]))
            refs += [r.to_json() for r in more]
        return refs

    async def rename(self, name: str, to: str, who: str = "user") -> dict[str, Any]:
        """The API blade and its web call blades renamed (their code names the new one); the made file
        and its variables stay. Code that named the old name is listed: it needs the new one."""
        api = self._api(name)
        new = " ".join(str(to or "").split())
        if not new:
            raise ApiError("Give the API a new name.")
        refs = self.references(api["name"])
        form = self._form(api["name"]) | {"name": new}
        await self._connections.save(form, api["name"], who)
        for operation, blade in self._calls(api["name"]).items():
            call = dict(blade["web_call"]) | {"api": new}
            code = str(blade["code"]).replace(
                f"sab.blade({json.dumps(api['name'])})", f"sab.blade({json.dumps(new)})"
            )
            renamed = {k: blade[k] for k in ("kind", "variable", "description", "tags")} | {
                "name": web_calls.name_of(new, operation),
                "code": code,
                "web_call": call,
            }
            await self._blades.save(renamed, blade["name"], who)
        source = dict(api["source"]) | {"api": new}
        self._library.write(
            self._library.path(api["folder"], "source.json"), json.dumps(source, indent=2) + "\n"
        )
        await self.tables_changed(new, who)
        return {"name": new, "was": api["name"], "references": refs}

    async def delete(self, name: str, body: Any, who: str = "user") -> dict[str, Any]:
        """{"confirm": true}: the API blade, its web call blades and its folder removed. Without it, the
        code that uses it (to say before asking). The agent's waits for the user's Allow."""
        api = self._api(name)
        refs = self.references(api["name"])
        if not (isinstance(body, dict) and body.get("confirm") is True):
            return {"name": api["name"], "references": refs, "deleted": False}
        if who == "agent":
            detail = f"{len(refs)} reference(s) in code" if refs else "no code uses it"
            if not await self._approvals.ask(api["name"], "delete the API", detail):
                raise Refused("The user did not allow deleting it.")
        for blade in self._calls(api["name"]).values():
            await self._blades.remove(str(blade["name"]), who)
        try:
            await self._blades.remove(api["name"], who)
        except (KeyError, LookupError, ValueError):
            pass
        await self._thread(self._library.remove, api["folder"])
        self.ws.audit.write(who, "api_delete", None, api=api["name"])
        return {"name": api["name"], "references": refs, "deleted": True}


def _shown_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """The inputs as the lineage keeps them: a sign-in one (a key, a token) hidden."""
    out: dict[str, Any] = {}
    for place, values in inputs.items():
        if isinstance(values, Mapping):
            out[place] = {
                k: ("(hidden)" if any(w in str(k).lower() for w in _SECRETISH) else v)
                for k, v in values.items()
            }
    return out


def _all_inputs(op: Mapping[str, Any], values: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
    """Every input of the operation by place (one not given: None), for a saved web call."""
    inputs: dict[str, Any] = {}
    flat = {k: v for k, v in values.items() if k not in (*apis.PLACES, "body")}
    for p in op.get("parameters") or []:
        place = values.get(p["in"]) if isinstance(values.get(p["in"]), Mapping) else {}
        given = place.get(p["name"], flat.get(p["name"]))  # type: ignore[union-attr]
        if given not in ("", None) or p["required"]:  # a required one with no value: named when read
            inputs.setdefault(p["in"], {})[p["name"]] = None if given in ("", None) else given
    body = values.get("body")
    if isinstance(body, str) and body.strip():
        try:
            body = json.loads(body)
        except ValueError as error:
            raise ApiError(f"The body is not JSON ({error}).") from None
    return inputs, body if body not in ("",) else None
