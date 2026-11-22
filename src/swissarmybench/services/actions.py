"""Every API's actions through api_adapter (Plans/api-adapter.plan.md; the owner, 2026-11-22: "every API,
yours or outside, goes through api_adapter"). The library's APIs (apis/<name>/) and the project's own local
sandbox API (`local`) are read from their specifications only; each call is api_adapter's run, one envelope.

  list      every action of every API: its method, path, whether it writes, its learned kind, its drift line
            and what it maps to
  describe  one action: its inputs and body fields, its learned contract (learn()), the last call this session
  run       one call (inputs checked first); a call that writes, by the agent, waits for the user's Allow; the
            endpoint's shape kept (apis/<name>/shapes/<action>.json, types only), its change said once
  shape     the kept shape and the contract; answer a rename offered (taken or declined, remembered)
  discover  the read-only probe, on the user's Allow, asked once per API and remembered with the API (the
            library's apis/<name>/discover.json; the local sandbox API's in the project's .sab), the agent's
            too, until it is taken back (allow): each read endpoint called once at its smallest page, the
            shapes kept, values not
  build     a notebook cell put into the project's data.ipynb, a script function put into a script the
            user picks (each opened there), or a widget on a canvas page (the Streamlit extension's,
            through hooks.canvas_put); nothing built until asked
  refs      every action as the canvas's one picker names it ("GET /orders": the local sandbox API's;
            "[Orders] GET /orders": a library API's), with its body fields
  carried   what a built app (Play, Launch, Export) carries beside its pages to call them: api_adapter.py,
            sab_actions.json (each action's definition and learned shape: types only), a library API's
            API_<name>.py

A library API's calls run in a child process through its API blade (its sign-in, its secrets resolved there);
the local sandbox API's through its running process (services/local_api.py: its own Allow for the agent's
writes). Values are never written anywhere: a shape holds paths and types only; the last call is memory only.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, Protocol

from swissarmybench.domain import api_actions as rules
from swissarmybench.domain import apis as api_rules
from swissarmybench.domain import notebooks
from swissarmybench.domain.api_actions import LOCAL, BuildError
from swissarmybench.services.changes import raised
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace

DISCOVER_CALLS = 20  # calls a discovery makes at most


class Files(Protocol):
    def read(self, path: str) -> str | None: ...

    def write(self, path: str, text: str) -> None: ...

    def forget(self, path: str) -> bool: ...


class Approvals(Protocol):
    async def ask(self, dataset: str, action: str, detail: str) -> bool: ...


def _join(folder: str, *parts: str) -> str:
    return "/".join([folder.rstrip("/\\"), *parts])


class Actions:
    def __init__(
        self,
        ws: Workspace,
        explorer: Any,  # services/api_explorer.py Explorer: the library's APIs, their blades, save_call
        local_api: Any,  # services/local_api.py LocalApi: state(full), call
        files: Files,  # the library's and the project's files (written whole, only when the bytes change)
        project: Callable[[], str | None],
        approvals: Approvals,
        today: Callable[[], str],
        to_thread: Callable[..., Awaitable[Any]] = asyncio.to_thread,
        hooks: Any = None,  # services/hooks.py Hooks: canvas_put (a widget on a canvas page)
        api_adapter: Any = None,  # adapters/api_adapter.py, the module (the composition root hands it in)
        adapter_text: Callable[[], str] | None = None,  # api_adapter.py's own text (a built app carries it)
        changed: Callable[[str, str], Awaitable[Any]] | None = None,  # a code file written: every window told
        show: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None,  # a document opened at a place
        stats: Any = None,  # services/call_stats.py CallStats: each envelope's facts (own(), api)
    ) -> None:
        self.ws = ws
        self._explorer = explorer
        self._local = local_api
        self._files = files
        self._project = project
        self._approvals = approvals
        self._today = today
        self._thread = to_thread
        self._hooks = hooks
        self._aa = api_adapter
        self._adapter_text = adapter_text
        self._changed = changed
        self._show = show
        # Discovery allowed with nowhere to keep it (the local sandbox API with no project open): memory.
        self._allowed: set[str] = set()
        self._stats = stats
        self._last: dict[tuple[str, str], dict[str, Any]] = {}  # the last call of each action (memory only)

    def _own(self) -> Any:
        """Runs said here from their envelopes: api_adapter's observe hook leaves them (call_stats.own)."""
        return self._stats.own() if self._stats is not None else contextlib.nullcontext()

    # ===== the actions, from each API's specification =====

    def _library_api(self, name: str) -> dict[str, Any] | None:
        for api in self._explorer._apis():
            if api["name"].casefold() == name.casefold():
                return dict(api)
        return None

    async def _spec(self, name: str) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
        """An API's name, its specification and its library entry (None: the local sandbox API)."""
        if name.casefold() == LOCAL:
            state = await self._local.state(full=True)
            if not state.get("exists"):
                raise NotFound(
                    "The project has no local sandbox API: New local sandbox API… makes its API.py."
                )
            return LOCAL, dict(state.get("openapi") or {}), None
        api = self._library_api(name)
        if api is None:
            raise NotFound(f"There is no API called {name}: actions(action=list) names them.")
        return str(api["name"]), self._explorer._document(api), api

    def _actions_of(self, name: str, doc: dict[str, Any]) -> dict[str, Any]:
        """The specification's actions, each named as the APIs page names its operation (a web call's)."""
        found = self._aa.actions(doc, name)
        try:
            named = {(o.method, o.path): o.name for o in api_rules.parse_spec(doc, "").operations}
        except api_rules.ApiError:
            named = {}
        return {(n := named.get((a.method, a.path), a.name)): replace(a, name=n) for a in found.values()}

    async def _action(self, api: str, action: str) -> tuple[str, Any, dict[str, Any], dict[str, Any] | None]:
        name, doc, entry = await self._spec(api)
        found = self._actions_of(name, doc)
        one = found.get(action) or next(
            (a for a in found.values() if a.name.casefold() == action.casefold()), None
        )
        if one is None:
            raise NotFound(f"{name} has no action {action}: actions(action=list, api={name}) names them.")
        return name, one, found, entry

    # ===== the canvas: one picker, and what a built app carries =====

    def _every(self) -> list[tuple[str, str, Any, dict[str, Any] | None]]:
        """Every action there is, read now from the files (no call): (its reference, its API, the action,
        the API's library entry or None for the local one). The local API's paths without its base path
        (a built app adds SAB_API_BASE)."""
        found: list[tuple[str, str, Any, dict[str, Any] | None]] = []
        local = self._local.document()
        if local is not None:
            doc, base = local
            for one in self._actions_of(LOCAL, doc).values():
                path = one.path[len(base) :] if base and one.path.startswith(base) else one.path
                found.append((rules.ref(LOCAL, one.method, path), LOCAL, replace(one, path=path), None))
        for api in self._explorer._apis():
            try:
                actions = self._actions_of(str(api["name"]), self._explorer._document(api))
            except (NotFound, ValueError):  # an API whose document does not read: none of its actions
                continue
            name = str(api["name"])
            found += [(rules.ref(name, a.method, a.path), name, a, dict(api)) for a in actions.values()]
        return found

    def refs(self) -> list[dict[str, Any]]:
        """Every API's actions as the canvas's one picker names them: {"ref", "api", "name", "method", "path",
        "writes", "fields": its body's field names}."""
        return [
            {
                "ref": ref,
                "api": api,
                "name": one.name,
                "method": one.method,
                "path": one.path,
                "writes": one.writes,
                "fields": [b.name for b in one.body],
            }
            for ref, api, one, _ in self._every()
        ]

    def local_learned(self) -> dict[str, dict[str, Any]]:
        """Each of the local sandbox API's endpoints ("POST /orders") with its learned contract and the shape
        of what it was last sent (paths and types, never a value): what Try it fills its form from."""
        found: dict[str, dict[str, Any]] = {}
        for ref, _api, one, entry in self._every():
            if entry is None:
                kept = self._shape(self._shape_path(LOCAL, None, one.name))
                found[ref] = {"contract": self._aa.learn(kept, one), "sent": kept.get("sent") or {}}
        return found

    def carried(self, used: str) -> dict[str, str]:
        """What a built app carries beside its pages: api_adapter.py (always), and sab_actions.json: the local
        sandbox API's actions and each library API's action that `used` (the app's canvas and code as text)
        names, each with its definition, its contract's boxes and its learned shape (types only, never a
        value); a library API's own client file, API_<name>.py (its sign-in from the host's variables)."""
        files: dict[str, str] = {}
        if self._adapter_text is not None:
            files["api_adapter.py"] = self._adapter_text()
        apis: dict[str, Any] = {}
        for ref, api, one, entry in self._every():
            if entry is not None and ref not in used:
                continue
            kept = self._shape(self._shape_path(api, entry, one.name))
            contract = self._aa.learn(kept, one)
            holder = apis.setdefault(api, {"actions": {}})
            holder["actions"][rules.ref(LOCAL, one.method, one.path)] = {
                "action": one.to_json(),
                "known": kept.get("returned"),
                "renames": kept.get("renames") or {},
                "inputs": contract["inputs"],
                "body": contract["body"],
                "kind": contract["kind"],
            }
            file = entry.get("file") if entry is not None else None
            if file and "module" not in holder:
                text = self._explorer._library.read(str(file))
                module = str(file).replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".py")
                if text:
                    holder["module"] = module
                    files[module + ".py"] = text
        files["sab_actions.json"] = json.dumps(apis, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        return files

    # ===== the kept shapes =====

    def _shape_path(self, api: str, entry: dict[str, Any] | None, action: str) -> str | None:
        file = self._aa.shape_file(action)
        if entry is not None:
            return _join(str(entry["folder"]), rules.SHAPES_FOLDER, file)
        folder = self._project()
        return _join(folder, rules.LOCAL_SHAPES, file) if folder else None

    def _shape(self, path: str | None) -> dict[str, Any]:
        text = self._files.read(path) if path else None
        try:
            found = json.loads(text) if text else {}
        except ValueError:
            return {}
        return found if isinstance(found, dict) else {}

    def _write_shape(self, path: str | None, shape: dict[str, Any]) -> None:
        if path is None:
            return
        text = self._aa.text(shape)
        if self._files.read(path) != text:  # only when its bytes change
            self._files.write(path, text)

    async def _kept(
        self, api: str, entry: dict[str, Any] | None, action: str, answer: dict[str, Any], who: str
    ) -> None:
        path = self._shape_path(api, entry, action)
        was = self._shape(path)
        kept, change = self._aa.keep(was, answer, self._today())
        if kept:
            self._write_shape(path, kept)
        if change:  # said once: the Session log, the pages, the agent's next read
            words = self._aa.drift_words(change, kept.get("changed", ""))
            # The change log: the endpoint's learned shape (its fields and their types), seen by the app.
            logged = raised("endpoint", f"{api} {action}", _fields(was), _fields(kept), words, by="app")
            self.ws.audit.write(who, "api_shape_changed", f"{api} {action}", words=words, **logged)
            await self.ws.live.broadcast(
                {"type": "api_shape_changed", "api": api, "action": action, "words": words}
            )

    # ===== Discover's Allow, remembered per API =====

    def _allow_path(self, entry: dict[str, Any] | None) -> str | None:
        if entry is not None:
            return _join(str(entry["folder"]), rules.ALLOW_FILE)
        folder = self._project()
        return _join(folder, rules.LOCAL_ALLOW) if folder else None

    def _allowed_since(self, name: str, entry: dict[str, Any] | None) -> str | None:
        """The day the user allowed this API's discovery (None: not allowed, or taken back)."""
        path = self._allow_path(entry)
        if path is None:
            return "this session" if name in self._allowed else None
        return rules.allowed_since(self._files.read(path))

    def _remember_allow(self, name: str, entry: dict[str, Any] | None) -> None:
        path = self._allow_path(entry)
        if path is None:
            self._allowed.add(name)
            return
        text = rules.allow_text(self._today())
        if rules.allowed_since(self._files.read(path)) is None:  # kept once: the day it was given
            self._files.write(path, text)

    async def allow(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"api", "allow": false}: Discover's Allow taken back (the user's, or the agent's: it only ever
        narrows). Giving it is the user's answer to Discover's own question, never this call."""
        given = body if isinstance(body, dict) else {}
        name, _doc, entry = await self._spec(str(given.get("api") or ""))
        if given.get("allow") is not False:
            raise Refused('Discover asks for its Allow itself: this only takes it back ({"allow": false}).')
        path = self._allow_path(entry)
        had = self._allowed_since(name, entry) is not None
        self._allowed.discard(name)
        if path is not None:
            self._files.forget(path)
        if had:
            self.ws.audit.write(who, "api_discover_allow", name, allowed=False)
            await self.ws.live.broadcast(
                {"type": "api_shape_changed", "api": name, "action": None, "words": ""}
            )
        return {"api": name, "allowed": False}

    # ===== list and describe =====

    async def list(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Every API's actions ({"api"?: one}): each with its learned kind, drift line and what it maps to."""
        given = body if isinstance(body, dict) else {}
        names = [str(given["api"])] if given.get("api") else [a["name"] for a in self._explorer._apis()]
        if not given.get("api"):
            state = await self._local.state()
            if state.get("exists"):
                names.append(LOCAL)
        apis: list[dict[str, Any]] = []
        for name in names:
            try:
                real, doc, entry = await self._spec(name)
                found = self._actions_of(real, doc)
            except (NotFound, self._aa.ActionError) as error:
                apis.append({"api": name, "problem": str(error), "actions": []})
                continue
            listed = []
            for one in found.values():
                learned = self._aa.learn(self._shape(self._shape_path(real, entry, one.name)), one)
                listed.append(
                    {
                        "name": one.name,
                        "method": one.method,
                        "path": one.path,
                        "summary": one.summary,
                        "writes": one.writes,
                        "kind": learned["kind"],
                        "learned": learned["learned"],
                        "drift": learned["drift"],
                        "maps_to": learned["maps_to"],
                        "offers": len(learned["offers"]),
                    }
                )
            since = self._allowed_since(real, entry)
            apis.append(
                {
                    "api": real,
                    "local": entry is None,
                    "allowed": since is not None,
                    "allowed_since": since,
                    "actions": listed,
                }
            )
        return {"apis": apis}

    async def describe(self, api: str, action: str, who: str = "user") -> dict[str, Any]:
        name, one, _, entry = await self._action(api, action)
        kept = self._shape(self._shape_path(name, entry, one.name))
        return {
            "api": name,
            "action": one.to_json(),
            "contract": self._aa.learn(kept, one),
            "shape": kept,
            "last": self._last.get((name, one.name)),
        }

    async def shape(self, api: str, action: str, who: str = "user") -> dict[str, Any]:
        """The kept shape (paths and types, both ways) and its contract: what the widgets read."""
        described = await self.describe(api, action, who)
        return {k: described[k] for k in ("api", "shape", "contract")}

    async def answer_offer(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"api", "action", "from", "to", "take": bool}: a rename offered once, answered and remembered."""
        given = body if isinstance(body, dict) else {}
        name, one, _, entry = await self._action(str(given.get("api") or ""), str(given.get("action") or ""))
        path = self._shape_path(name, entry, one.name)
        kept = self._shape(path)
        offer = next((o for o in kept.get("offers") or [] if o.get("from") == given.get("from")), None)
        if offer is None:
            raise NotFound(f"{name} {one.name} offers no rename of {given.get('from')}.")
        kept = self._aa.answered(kept, str(offer["from"]), str(offer["to"]), bool(given.get("take")))
        self._write_shape(path, kept)
        self.ws.audit.write(who, "api_rename_answered", f"{name} {one.name}", take=bool(given.get("take")))
        return {"api": name, "contract": self._aa.learn(kept, one)}

    # ===== run =====

    async def run(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"api", "action", "inputs"?, "required"?: [paths]}: one call, its one envelope. A call that writes,
        made by the agent, waits for the user's Allow (the local sandbox API asks itself)."""
        given = body if isinstance(body, dict) else {}
        name, one, _, entry = await self._action(str(given.get("api") or ""), str(given.get("action") or ""))
        inputs = dict(given.get("inputs") or {}) if isinstance(given.get("inputs"), dict) else {}
        if entry is not None and one.writes and who == "agent":
            detail = f"{one.method} {one.path} on {name}: it changes something outside the app."
            if not await self._approvals.ask(name, f"call {one.name}", detail):
                raise Refused("The user declined (or did not answer): nothing was sent.")
        path = self._shape_path(name, entry, one.name)
        kept = self._shape(path)
        options = {
            "known": kept.get("returned"),
            "renames": kept.get("renames") or {},
            "required": [str(p) for p in given.get("required") or []],
            "who": who,
        }
        with self._own():
            if entry is None:
                answer = await self._run_local(one, inputs, options, who)
            else:
                answer = await self._run_library(name, one, inputs, options)
        if self._stats is not None:  # its facts, and where it came from (a widget and its page, a cell)
            self._stats.api(answer, given.get("where") if isinstance(given.get("where"), dict) else {})
        await self._kept(name, entry, one.name, answer, who)
        self._last[(name, one.name)] = {
            "at": self._today(),
            "inputs": inputs,
            "status": answer["status"],
            "ok": answer["ok"],
            "kind": answer["kind"],
            "paging": answer["paging"],
            "sent": answer["sent"],
            "records": len(answer.get("records") or ()),
        }
        self.ws.audit.write(who, "api_action", f"{name} {one.name}", status=answer["status"])
        return answer

    async def _run_library(
        self, name: str, one: Any, inputs: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        """One run in a child process through the API blade (its sign-in), api_adapter's run there."""
        variables = getattr(self._explorer, "variables", None)
        if variables is not None:  # an input's ${NAME} (12.7): its value sent
            inputs = await variables.resolve_all(inputs, f"{name} {one.name}")
        command = _child_command(
            f"_aa.run(_aa.Action.from_json(_j.loads({json.dumps(json.dumps(one.to_json()))})), "
            f"_j.loads({json.dumps(json.dumps(inputs, default=str))}), api=_aa.from_client(conn), "
            f"**_j.loads({json.dumps(json.dumps(options, default=str))}))"
        )
        return await self._in_child(name, command)

    async def _in_child(self, name: str, command: str) -> dict[str, Any]:
        explorer = self._explorer
        done = await explorer._blades.run_read(explorer._api_blade(name), command, "", {})
        rows = done["table"].to_pylist()
        if not rows:
            raise Conflict(f"{name}'s API blade answered nothing.")
        found = json.loads(str(rows[0]["envelope"]))
        return found if isinstance(found, dict) else {}

    async def _run_local(
        self, one: Any, inputs: dict[str, Any], options: dict[str, Any], who: str
    ) -> dict[str, Any]:
        """One run through the running local sandbox API (its process; its own Allow for the agent's)."""
        loop = asyncio.get_running_loop()
        api = self._aa.Api("", _local_send(self._aa, self._local, loop, who), LOCAL)
        return dict(await self._thread(lambda: self._aa.run(one, inputs, api=api, retries=0, **options)))

    # ===== discover =====

    async def discover(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"api"}: the read-only probe on the user's Allow (asked once per API and remembered with it until
        taken back; the agent's too), each read endpoint once at its smallest page; the shapes kept, values
        not; what each maps to."""
        given = body if isinstance(body, dict) else {}
        name, doc, entry = await self._spec(str(given.get("api") or ""))
        found = self._actions_of(name, doc)
        reads = sum(1 for a in found.values() if not a.writes)
        if self._allowed_since(name, entry) is None:
            detail = (
                f"Discover {name}: up to {min(reads, DISCOVER_CALLS)} read-only calls (one GET per read "
                "endpoint, the smallest page). Nothing that writes is called; no value is kept. Your "
                "answer is remembered for this API until you take it back on the APIs page."
            )
            if not await self._approvals.ask(name, "discover the API", detail):
                raise Refused("The user declined (or did not answer): nothing was called.")
            self._remember_allow(name, entry)
            self.ws.audit.write(who, "api_discover_allow", name, allowed=True)
        known = {n: self._shape(self._shape_path(name, entry, n)) for n in found}
        if entry is None:
            loop = asyncio.get_running_loop()
            api = self._aa.Api("", _local_send(self._aa, self._local, loop, who), LOCAL)
            with self._own():
                learned = await self._thread(lambda: self._aa.discover(found, api, known, DISCOVER_CALLS))
        else:
            actions = {n: a.to_json() for n, a in found.items()}
            found_text, known_text = json.dumps(json.dumps(actions)), json.dumps(json.dumps(known))
            command = _child_command(
                "_aa.discover({n: _aa.Action.from_json(a) for n, a in _j.loads(" + found_text + ").items()}, "
                "api=_aa.from_client(conn), known=_j.loads(" + known_text + f"), max_calls={DISCOVER_CALLS})"
            )
            learned = await self._in_child(name, command)
        for action, answer in learned["answers"].items():
            if self._stats is not None:
                self._stats.api(answer, {})
            await self._kept(name, entry, action, answer, who)
        self.ws.audit.write(who, "api_discovered", name, calls=learned["calls"])
        await self.ws.live.broadcast({"type": "api_shape_changed", "api": name, "action": None, "words": ""})
        contracts = {
            n: self._aa.learn(self._shape(self._shape_path(name, entry, n)), a) for n, a in found.items()
        }
        return {
            "api": name,
            "calls": learned["calls"],
            "skipped": learned["skipped"],
            "pairs": learned["pairs"],
            "failed": {n: a["error"] for n, a in learned["answers"].items() if not a["ok"]},
            "contracts": contracts,
        }

    # ===== build =====

    async def build(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"api", "action", "as": cell | function | widget, "inputs"?, "path"?, "insert"?, "canvas"?,
        "page"?}: what the endpoint builds into, by its learned shape. A cell is put at the end of the open
        project's data.ipynb; a function at the end of the script `path` names (inside the project; made when
        it is not there): {"code", "path", "cell" | "line"}, the document opened there for the agent's (the
        page opens its own). With no project open, no `path` for a function, or "insert": false, the code
        alone is answered, to copy. A widget is put on a canvas page (the Streamlit extension's); with
        "insert": false its plan alone is answered (nothing placed, no Return as table switched on)."""
        given = body if isinstance(body, dict) else {}
        made = str(given.get("as") or "")
        if made not in rules.BUILDS:
            raise ValueError(f"Build as one of {', '.join(rules.BUILDS)}.")
        name, one, _, entry = await self._action(str(given.get("api") or ""), str(given.get("action") or ""))
        contract = self._aa.learn(self._shape(self._shape_path(name, entry, one.name)), one)
        kind = str(contract["kind"])
        api_name = name if entry is not None else LOCAL
        folder = self._project() if given.get("insert", True) is not False else None
        if made == "cell":
            inputs = dict(given.get("inputs") or {})
            code = rules.cell(api_name, one.to_json(), inputs, kind)
            if folder is None:
                return {"as": "cell", "code": code}
            path = _join(folder, rules.DATA_NOTEBOOK)
            try:
                written, number = rules.with_cell(
                    self._files.read(path) or notebooks.write_notebook([]), code
                )
            except notebooks.NotebookError as error:
                raise Conflict(f"{rules.DATA_NOTEBOOK} does not read as a notebook: {error}") from None
            return {"as": "cell", "code": code} | await self._put(
                path, written, {"cell": number}, who, name, one
            )
        if made == "function":
            code = rules.function(api_name, one.to_json(), kind)
            if folder is None or not given.get("path"):
                return {"as": "function", "code": code}
            function = rules.python_name(one.name)
            try:
                path = _join(folder, rules.script_path(given.get("path")))
                written, line = rules.with_function(self._files.read(path), code, function)
            except BuildError as error:
                raise Conflict(str(error)) from None
            placed = await self._put(path, written, {"line": line}, who, name, one)
            return {"as": "function", "code": code, "name": function} | placed
        try:
            plan = rules.widget(name, one.to_json(), kind, entry is None)
        except BuildError as error:
            raise Conflict(str(error)) from None
        if given.get("insert", True) is False:  # the plan alone: nothing placed, no table switched on
            return {"as": "widget", "widget": plan["widget"], "plan": plan}
        put = getattr(self._hooks, "canvas_put", None)
        if put is None:
            raise Conflict("A widget goes on a canvas page: the Streamlit extension makes canvases.")
        if plan.get("as_table"):  # another API's records: its web call with Return as table on, the one gate
            await self._explorer.table_call(name, one.name, str(contract.get("envelope") or "$"), who)
        placed = await put({k: given.get(k) for k in ("canvas", "page") if given.get(k)} | plan, who)
        return {"as": "widget", "widget": plan["widget"], **placed}

    async def _put(
        self, path: str, text: str, at: dict[str, Any], who: str, api: str, one: Any
    ) -> dict[str, Any]:
        """Build's code written into its document (whole, only when its bytes change), every window told,
        the Session log too; for the agent the document is shown at the place when its page is open."""
        if self._files.read(path) != text:
            self._files.write(path, text)
            if self._changed is not None:
                await self._changed(path, who)
        self.ws.audit.write(who, "api_built", f"{api} {one.name}", path=path, **at)
        opened = False
        if who == "agent" and self._show is not None:
            try:
                await self._show(path, at)
                opened = True
            except Exception:  # no Notebooks or Scripts page open: the answer says where it went
                opened = False
        return {"path": path, **at} | ({"opened": opened} if who == "agent" else {})


def _fields(shape: dict[str, Any] | None) -> dict[str, Any] | None:
    """A kept shape's answer as the change log names it: each field's path and type (never a value)."""
    fields = ((shape or {}).get("returned") or {}).get("fields")
    if not isinstance(fields, dict):
        return None
    return {"fields": {str(p): str((f or {}).get("type") or "") for p, f in fields.items()}}


def _child_command(expression: str) -> str:
    """The read box a library API's run is: api_adapter run in the child, its envelope as one row."""
    return (
        "import json as _j\n"
        "from swissarmybench.adapters import api_adapter as _aa\n"
        f"_answer = {expression}\n"
        "[{'envelope': _j.dumps(_answer, default=str)}]"
    )


def _local_send(aa: Any, local_api: Any, loop: asyncio.AbstractEventLoop, who: str) -> Any:
    """api_adapter's send for the local sandbox API: each request one call of its running process."""

    def send(request: Any) -> Any:
        path, query = request.parts()
        body = json.loads(request.body) if request.body else None
        sent = {"method": request.method, "path": path, "query": query, "body": body}
        try:
            done = asyncio.run_coroutine_threadsafe(local_api.call(sent, who, raw=True), loop).result(
                timeout=180
            )
        except (Conflict, Refused) as error:
            return aa.Response(0, {}, str(error).encode())
        status = int(done.get("status") or 0)
        if status >= 400 and done.get("error"):
            raw = json.dumps({"error": done["error"]}).encode()
            return aa.Response(status, {"content-type": "application/json"}, raw)
        # The answer as the API itself gave it (its bytes and its content type), so a file to save (the Export
        # pattern's CSV or workbook) is read here as a built app's own call reads it, not as Try it shows it.
        headers = {k: str(v) for k, v in (done.get("headers") or {}).items()}
        return aa.Response(status, headers or {"content-type": "application/json"}, done.get("raw") or b"")

    return send
