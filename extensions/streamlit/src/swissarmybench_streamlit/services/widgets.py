"""Widgets (the owner, 2026-11-21): the library's widgets and the extension's prebuilt ones, their properties,
the Widgets window's Run (the widget alone, through the Streamlit proxy, in the project's Python) and the
agent's widgets_* commands.

  listing        every widget of a framework: the open project's own (its widgets/ folder, shared in Git with
                 it), the library's, then the prebuilt (read-only) ones, each starter pack's first (domain/
                 widget_packs.py: in its order, with its description), then by group; a project's widget of a
                 library's name wins, and says so (`hides`)
  get            one widget: its header, its code, its properties (types and masks), where its file is
  new / save     a new widget from the template; its code written (the header kept)
  header         Name and Description (and group, tags, size) written into the header only; a new name
                 checked (available, taken, invalid) and every canvas's instances renamed (`renamed` hook)
  properties     the properties of a widget, or of code as the editor holds it now (live)
  set_property   a property's default written into ONLY its own characters, checked first
  copy           a widget as your own: a prebuilt one into the library (a free name), Copy to project or Copy
                 to library (the same name, in the other place)
  delete         a library widget (the agent's waits for the user's Allow)
  run / stop     the widget alone as a live Streamlit page (Run in place); `check` the same headless
                 (AppTest): its errors, for the agent's widgets_run
  preview        a small PNG of the widget rendered with its defaults (cached by its file's hash and the
                 theme); the pane never waits on it

The live runs (server/live_runs.py LiveRuns) are shared with the Canvas's Play (services/canvas.py): one
process per key, its folder a temporary one of the app's, its address /streamlit/run/<key>-<secret>/.
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain import changes as change_rules
from swissarmybench.services.changes import raised
from swissarmybench.services.workspace import Conflict, NotFound, Refused
from swissarmybench_streamlit.domain import canvas_build as build_rules
from swissarmybench_streamlit.domain import canvas_model as model
from swissarmybench_streamlit.domain import canvas_wiring as wiring
from swissarmybench_streamlit.domain import widget_contract as contract
from swissarmybench_streamlit.domain import widget_packs as packs
from swissarmybench_streamlit.domain import widget_properties as props_rules
from swissarmybench_streamlit.domain import widget_upgrade as upgrade_rules
from swissarmybench_streamlit.domain import widgets as rules
from swissarmybench_streamlit.domain.widgets import Widget, WidgetError

FRAMEWORK = "streamlit"
PLACES: tuple[str, ...] = ("project", "library", "prebuilt")

Renamed = Callable[[str, str], Awaitable[int]]


@dataclass(frozen=True)
class WidgetProject:
    """The open project as the Widgets window reads it (the root's port): its folder, its Python, the tables
    its data.py makes, this server's environment's names and this computer's variables' names."""

    folder: Callable[[], str | None] = lambda: None
    python: Callable[[], str | None] = lambda: None
    data_tables: Callable[[], list[str]] = list
    variables: Callable[[], set[str]] = set
    variable_names: Callable[[], list[str]] = list


@dataclass(frozen=True)
class WidgetTables:
    """The tables a table property may name (the root's port): the open ones (each one's columns, its rows as
    Parquet), the connections' [Conn].table (their names, their listed tables, one read as Parquet)."""

    columns: Callable[[], dict[str, list[str] | None]] = dict
    data: Callable[[str], Awaitable[bytes]] | None = None
    connections: Callable[[], set[str]] | None = None
    connection_listing: Callable[[], Awaitable[dict[str, list[str] | None]]] | None = None
    read_connection: Callable[[str], Awaitable[bytes]] | None = None


@dataclass(frozen=True)
class WidgetApis:
    """What an endpoint property and a built app read of the APIs (the root's port): every action as the
    picker names it ("GET /orders"), each one's body fields, and the files a built app carries to call them
    (the base's services/actions.py) and to read and make workbooks (adapter.py, sab_excel.py). None: not
    known here."""

    endpoints: Callable[[], list[str]] | None = None
    endpoint_fields: Callable[[], dict[str, list[str]]] | None = None
    api_files: Callable[[str], dict[str, str]] | None = None
    excel_files: Callable[[str], dict[str, str]] | None = None


class Widgets:
    def __init__(
        self,
        ws: Any,
        files: Any,
        live: Any,
        approvals: Any,
        project: WidgetProject | None = None,
        tables: WidgetTables | None = None,
        apis: WidgetApis | None = None,
        previews: Any = None,
        renamed: Renamed | None = None,
    ) -> None:
        project, tables, apis = project or WidgetProject(), tables or WidgetTables(), apis or WidgetApis()
        self.ws = ws
        self._files = files  # adapters/widget_files.py WidgetFiles
        self.live = live
        self._approvals = approvals
        self._tables = tables.columns  # the open tables: name -> its columns
        self._table_data = tables.data  # an open table's rows as Parquet
        self._project_python = project.python
        self._previews = previews  # adapters/widget_files.py PreviewFiles
        self.renamed = renamed  # every canvas's instances follow a rename (services/canvas.py)
        self._variables = project.variables
        self._variable_names = project.variable_names  # the variables' names (a variable property's list)
        self._project_folder = project.folder
        self._data_tables = project.data_tables  # the tables the project's data.py makes (data.ipynb's)
        self._connections = tables.connections  # the saved connections' names ([Conn].table)
        self._connection_listing = tables.connection_listing  # each connection's tables, as far as listed
        self._read_connection_table = tables.read_connection  # [Conn].table as Parquet, through the contract
        # Every API's actions as the picker names them ("GET /orders": the base's services/actions.py), for
        # an endpoint property's picker and check, and each one's body fields (an Event's body mapping).
        self.endpoints = apis.endpoints
        self.endpoint_fields = apis.endpoint_fields
        # What a built app carries to call APIs' actions (the base's actions' carried: api_adapter.py,
        # sab_actions.json, a library API's client), given the app's canvas and code as text, and to read
        # and make workbooks (adapter.py, sab_excel.py: the Excel widgets call them).
        self.api_files = apis.api_files
        self.excel_files = apis.excel_files
        self._moved: dict[str, str] = {}  # a renamed widget's old name -> its name now (this session)

    # ===== reading =====

    def follow(self, name: str) -> str:
        """The name a request means: a widget renamed this session is still reached by its old name (a save
        or a second rename on its way when the rename landed), unless a widget of that name is there now."""
        if name not in self._moved or self._files.read(name) is not None:
            return name
        return self._moved[name]

    def _all(self) -> dict[str, tuple[Widget, str]]:
        """Every widget by name (the project's first, then the library's: a widget hides another of its name
        further down)."""
        found: dict[str, tuple[Widget, str]] = {}
        self._places: dict[str, list[str]] = {}
        for _file, text, place in self._files.all():
            try:
                widget = rules.read_widget(text, prebuilt=place == "prebuilt")
            except WidgetError:
                continue
            self._places.setdefault(widget.name, []).append(place)
            found.setdefault(widget.name, (widget, text))
        return found

    def _place(self, name: str) -> str:
        return str(self._files.place_of(name) or "library")

    def names(self) -> set[str]:
        return set(self._all())

    def _one(self, name: str) -> tuple[Widget, str]:
        found = self._files.read(name) if isinstance(name, str) and rules.NAME.match(name) else None
        if found is None:
            raise NotFound(f"There is no widget called {str(name)[:60]}.")
        text, place = found
        try:
            return rules.read_widget(text, prebuilt=place == "prebuilt"), text
        except WidgetError as error:
            raise ValueError(f"{name}'s file does not read: {error}") from None

    def _known_tables(self) -> dict[str, list[str] | None]:
        """The open tables with their columns, then data.ipynb's (from data.py; columns not known here)."""
        found = dict(self._tables())
        try:
            made = self._data_tables()
        except Exception:  # data.py's own trouble: the open tables still count
            made = []
        for name in made:
            found.setdefault(name, None)
        return found

    def _connection_names(self) -> set[str] | None:
        if self._connections is None:
            return None
        try:
            return set(self._connections())
        except Exception:
            return None

    def carried(self, canvas: Mapping[str, Any], built: Mapping[str, Any]) -> dict[str, str]:
        used = json.dumps(canvas, ensure_ascii=False) + "\n".join(str(b.code) for b in built.values())
        files = dict(self.excel_files(used)) if self.excel_files is not None else {}
        if self.api_files is None:
            return files
        try:
            return files | dict(self.api_files(used))
        except Exception:  # an API's own trouble: the app is built all the same (a call says what is missing)
            return files

    def _endpoints(self) -> list[str] | None:
        try:
            return list(self.endpoints()) if self.endpoints is not None else None
        except Exception:  # API.py's own trouble: the picker shows what it can
            return None

    def context(self, values: Mapping[str, Any] | None = None) -> props_rules.Context:
        endpoints = self._endpoints()
        return props_rules.Context(
            tables=self._known_tables(),
            variables=self._variables(),
            values=dict(values or {}),
            connections=self._connection_names(),
            endpoints=set(endpoints) if endpoints is not None else None,
        )

    def _properties(self, code: str) -> tuple[list[props_rules.Property], dict[str, Any] | None]:
        try:
            return props_rules.detect(code, frozenset(self._tables())), None
        except props_rules.PropertyError as error:
            return [], {"error": str(error), "fix": error.fix, "line": error.line}

    def _ports(self, code: str) -> list[contract.Port]:
        try:
            return contract.detect(code)
        except props_rules.PropertyError:
            return []

    def _contract(self, code: str) -> dict[str, list[dict[str, Any]]]:
        ports = self._ports(code)
        return {
            kind: [p.to_json() for p in ports if p.direction == direction]
            for kind, direction in (("ins", "in"), ("outs", "out"), ("events", "event"))
        }

    def _entry(self, widget: Widget, text: str, place: str | None = None) -> dict[str, Any]:
        found, problem = self._properties(widget.code)
        places = getattr(self, "_places", {}).get(widget.name) or [place or self._place(widget.name)]
        return widget.to_json() | {
            "where": places[0],
            # the places further down that hold a widget of this name (it wins over them)
            "hides": [p for p in places[1:] if p != places[0]],
            "properties": [p.to_json() for p in found],
            "contract": self._contract(widget.code),
            "problem": problem,
            "hash": _hash(text),
            "pack_description": packs.PACKS.get(widget.pack, ""),
        }

    def listing(self, framework: str = FRAMEWORK, query: str = "") -> dict[str, Any]:
        words = query.lower().split()
        shown = []
        for widget, text in self._all().values():
            if widget.framework != framework:
                continue
            words_of = [widget.name, widget.description, widget.group, widget.pack, *widget.tags]
            said = " ".join(words_of).lower()
            if all(w in said for w in words):
                shown.append(self._entry(widget, text))
        shown.sort(
            key=lambda w: (
                PLACES.index(w["where"]) if w["where"] in PLACES else 9,
                packs.order(w["pack"]) if w["prebuilt"] else 0,
                rules.GROUPS.index(w["group"]) if w["group"] in rules.GROUPS else 99,
                w["name"],
            )
        )
        return {
            "framework": framework,
            "widgets": shown,
            "groups": list(rules.GROUPS),
            "packs": packs.listing(),
            "folder": str(self._files.folder() or ""),
            "project_folder": str(self._files.folder("project") or ""),
        }

    def get(self, name: str) -> dict[str, Any]:
        widget, text = self._one(name)
        place = self._place(name)
        file = self._files.where(name, place) if not widget.prebuilt else ""
        folder = self._project_folder()
        # The editor's kernel runs in the open project's folder (its scripts import, its data.py too), else
        # beside the widget's file.
        kernel_path = f"{folder}/{rules.file_name(name)}" if folder else file or None
        self._all()  # its places (what it hides)
        return self._entry(widget, text, place) | {
            "code": widget.code,
            "file": file,
            "text": text,
            "kernel_path": kernel_path,
            "kernel_setup": build_rules.kernel_setup(),
            # Upgrade to In/Out is offered while its code hands values on by session state keys
            "upgradable": bool((self._upgrade_plan(widget.code) or {}).get("changes")),
        }

    async def context_info(self) -> dict[str, Any]:
        """What the Properties pane's pickers offer: the open tables with their columns, data.ipynb's
        tables, each connection's tables as DuckDB SQL names them (`[Conn].table`; None: its catalog is
        not listed yet, its table is typed), the variables."""
        try:
            names = sorted(set(self._variable_names()))
        except Exception:  # the Variables page's own trouble: the box still takes a name
            names = []
        listing: dict[str, list[str] | None] = {}
        if self._connection_listing is not None:
            try:
                listing = await self._connection_listing()
            except Exception:  # a connection's own trouble: the other tables are still offered
                listing = {}
        open_tables = self._tables()
        return {
            "tables": self._known_tables(),
            "open_tables": sorted(open_tables),
            "data_tables": [t for t in self._data_tables_safe() if t not in open_tables],
            "connection_tables": listing,
            "variables": names,
            "endpoints": self._endpoints() or [],
            "endpoint_fields": self._endpoint_fields(),
            "project": self._project_folder(),
        }

    def _endpoint_fields(self) -> dict[str, list[str]]:
        try:
            return dict(self.endpoint_fields()) if self.endpoint_fields is not None else {}
        except Exception:  # API.py's own trouble
            return {}

    def _data_tables_safe(self) -> list[str]:
        try:
            return list(self._data_tables())
        except Exception:
            return []

    def facts(self) -> dict[str, model.WidgetFacts]:
        made: dict[str, model.WidgetFacts] = {}
        for name, (widget, _text) in self._all().items():
            found, _ = self._properties(widget.code)
            made[name] = model.WidgetFacts(
                widget.size,
                widget.min_size,
                frozenset(p.name for p in found),
                frozenset(p.name for p in self._ports(widget.code) if p.direction != "out"),
                tuple((p.name, p.type) for p in self._ports(widget.code) if p.direction == "in"),
            )
        return made

    def _made(self, code: str) -> build_rules.Built:
        """A widget's code as the builder uses it, its properties typed as the Properties pane types them
        (a value naming an open table is a table: its rows go beside the run)."""
        found, problem = self._properties(code)
        return build_rules.made(code) if problem else build_rules.made(code, found)

    def built(self) -> dict[str, build_rules.Built]:
        made: dict[str, build_rules.Built] = {}
        for name, (widget, _text) in self._all().items():
            # code that does not parse: its error shows in its place on the page
            made[name] = self._made(widget.code)
        return made

    def properties(self, body: Any) -> dict[str, Any]:
        """The properties of a widget, or of `code` as the editor holds it (live as it changes)."""
        body = body if isinstance(body, dict) else {}
        code = body.get("code")
        if not isinstance(code, str):
            code = self._one(str(body.get("name")))[0].code
        found, problem = self._properties(code)
        return {
            "properties": [p.to_json() for p in found],
            "contract": self._contract(code),
            "problem": problem,
        }

    def check_name(self, name: Any, own: str | None = None) -> dict[str, Any]:
        return rules.check_name(name, frozenset(self.names()), own)

    def check_value(self, body: Any) -> dict[str, Any]:
        """A value for a property, checked against its type and mask (the pane says it in place, with the
        fix, before anything is kept)."""
        body = body if isinstance(body, dict) else {}
        code = body.get("code")
        if not isinstance(code, str):
            code = self._one(str(body.get("name")))[0].code
        found, problem = self._properties(code)
        prop = next((p for p in found if p.name == body.get("property")), None)
        port = next((p for p in self._ports(code) if p.name == body.get("property")), None)
        if prop is None and port is not None and port.direction != "out":
            return self.check_wire(port, body.get("wire", body.get("value")), body.get("values"))
        if prop is None:
            return {
                "ok": False,
                "said": problem["error"] if problem else "That property is not there.",
                "fix": "",
            }
        try:
            props_rules.check(prop, body.get("value"), self.context(body.get("values")))
        except props_rules.PropertyError as error:
            return {"ok": False, "said": str(error), "fix": error.fix}
        return {"ok": True}

    def check_wire(self, port: contract.Port, wire: Any, values: Any = None) -> dict[str, Any]:
        """An In's source or an Event's actions, checked as far as it can be without a page (a table's name:
        its connection; a typed value: its type). The canvas checks the page's Outs as it wires."""
        context = self.context(values)
        if isinstance(wire, str) and port.type == "Table":
            try:
                props_rules.check(props_rules.Property(port.name, "table", ""), wire, context)
            except props_rules.PropertyError as error:
                return {"ok": False, "said": str(error), "fix": error.fix}
            return {"ok": True}
        if not isinstance(wire, dict):
            wire = {"value": wire}
        try:
            if port.direction == "event":
                wiring.check_event(port, wire, context.endpoints)
            elif "out" not in wire:
                wiring.check_in(
                    port,
                    wire,
                    wiring.Context({}, context.endpoints, context.variables, None),
                )
        except contract.ContractError as error:
            return {"ok": False, "said": str(error), "fix": error.fix}
        return {"ok": True}

    # ===== writing =====

    def _mine(self, name: str) -> tuple[Widget, str]:
        widget, text = self._one(name)
        if widget.prebuilt:
            raise Refused(
                f"{name} is a prebuilt widget: it is read-only.",
                fixes=[{"label": "Copy as your own", "action": "try_again", "command": "widgets_copy"}],
            )
        return widget, text

    def _write(self, name: str, text: str, place: str) -> None:
        try:
            self._files.write(name, text, place)
        except PermissionError as error:
            raise Refused(str(error)) from None

    async def new(self, body: Any, who: str = "user") -> dict[str, Any]:
        body = body if isinstance(body, dict) else {}
        taken = frozenset(self.names())
        name = body.get("name") or rules.free_name("my_widget", taken)
        said = rules.check_name(name, taken)
        if not said["ok"]:
            raise Conflict(said["said"]) if said["state"] == "taken" else ValueError(said["said"])
        widget = rules.new_widget(
            name, str(body.get("framework") or FRAMEWORK), str(body.get("description") or "")
        )
        if isinstance(body.get("code"), str) and body["code"].strip():
            widget = Widget(**{**widget.__dict__, "code": body["code"]})
        place = str(body.get("where") or "library")
        if place not in ("project", "library"):
            raise ValueError("A new widget goes in the project or the library.")
        self._write(name, rules.write_widget(widget), place)
        self.ws.audit.write(who, "new_widget", name)
        await self._changed(name)
        return self.get(name)

    async def save(self, name: str, body: Any, who: str = "user") -> dict[str, Any]:
        """The widget's code as the editor holds it, written below its header (the header's bytes kept)."""
        code = body.get("code") if isinstance(body, dict) else None
        if not isinstance(code, str):
            raise ValueError('Send the widget\'s code: {"code": "..."}.')
        widget, text = self._mine(name)
        if code != widget.code:
            head, _, _ = text.partition("\n" + rules._CLOSE + "\n")
            self._write(name, head + "\n" + rules._CLOSE + "\n" + code, self._place(name))
            self.ws.audit.write(who, "save_widget", name, **_widget_change(name, widget.code, code))
            await self._changed(name)
        return self.get(name)

    async def header(self, name: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Name, Description (and group, tags, size, min_size) into the header only."""
        body = dict(body) if isinstance(body, dict) else {}
        _widget, text = self._mine(name)
        new_name = body.get("name", name)
        if new_name != name:
            said = rules.check_name(new_name, frozenset(self.names()), own=name)
            if not said["ok"]:
                raise Conflict(said["said"]) if said["state"] == "taken" else ValueError(said["said"])
        try:
            after = rules.with_header(
                text,
                **{
                    k: v
                    for k, v in body.items()
                    if k in ("name", "description", "group", "tags", "size", "min_size")
                },
            )
        except WidgetError as error:
            raise ValueError(str(error)) from None
        renamed = 0
        place = self._place(name)
        if new_name != name:
            self._write(new_name, after, place)
            self._files.remove(name, place)
            self._moved = {old: new_name if now == name else now for old, now in self._moved.items()}
            self._moved[name] = new_name
            self._moved.pop(new_name, None)
            if self.renamed is not None:
                renamed = await self.renamed(name, new_name)
            self.ws.audit.write(who, "rename_widget", f"{name} -> {new_name}")
        elif after != text:
            self._write(name, after, place)
            self.ws.audit.write(who, "change_widget", name)
        await self._changed(new_name, old=name if new_name != name else None)
        return self.get(new_name) | {"instances_renamed": renamed}

    async def set_property(self, name: str, body: Any, who: str = "user") -> dict[str, Any]:
        """A property's default written into its own characters (of the code sent, or the saved code)."""
        body = body if isinstance(body, dict) else {}
        prop = body.get("property")
        if not isinstance(prop, str):
            raise ValueError(
                'Send the property\'s name and its value: {"property": "colour", "value": "#d62728"}.'
            )
        widget, text = self._mine(name)
        code: str = body.get("code") if isinstance(body.get("code"), str) else widget.code
        try:
            after = props_rules.set_default(code, prop, body.get("value"), self.context(body.get("values")))
        except props_rules.PropertyError as error:
            raise _said(error) from None
        head, _, _ = text.partition("\n" + rules._CLOSE + "\n")
        self._write(name, head + "\n" + rules._CLOSE + "\n" + after, self._place(name))
        change = _widget_change(name, widget.code, after)
        self.ws.audit.write(who, "set_widget_property", f"{name}.{prop}", **change)
        await self._changed(name)
        return self.get(name)

    def _upgrade_plan(self, code: str) -> dict[str, Any] | None:
        try:
            return upgrade_rules.plan(code)
        except (props_rules.PropertyError, SyntaxError, ValueError):
            return None

    async def upgrade(self, name: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Upgrade to In/Out: its session state keys as the contract's declarations. A preview (the code, each
        key's In or Out, what is kept and why, the diff) until `apply`; applied, the code is saved (a
        prebuilt widget's is refused: Copy as your own)."""
        body = body if isinstance(body, dict) else {}
        widget, _text = self._one(name)
        code: str = body.get("code") if isinstance(body.get("code"), str) else widget.code
        found = self._upgrade_plan(code)
        if found is None:
            raise ValueError("The widget's code does not read: fix it first.")
        if not body.get("apply"):
            return found | {"widget": name, "applied": False}
        if not found["changes"]:
            return found | {"widget": name, "applied": False}
        self._mine(name)
        saved = await self.save(name, {"code": found["code"]}, who)
        self.ws.audit.write(who, "upgrade_widget", name)
        return found | {"widget": name, "applied": True, "saved": saved}

    async def copy(self, name: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """A copy of a widget: a prebuilt one into the library as your own (my_<name>), or Copy to project /
        Copy to library (`to`: the same name in the other place; the project's wins on its canvases)."""
        body = body if isinstance(body, dict) else {}
        widget, text = self._one(name)
        source = self._place(name)
        to = str(body.get("to") or "library")
        if to not in ("project", "library"):
            raise ValueError("A copy goes to the project or the library.")
        wanted = body.get("name")
        taken = frozenset(self.names())
        here = {n for f, _t, p in self._files.all() if p == to for n in [f[: -len(rules.SUFFIX)]]}
        if not wanted:
            wanted = name if source != "prebuilt" and source != to and name not in here else None
        new_name = wanted or rules.free_name(f"my_{widget.name}", taken | here)
        said = rules.check_name(new_name, frozenset(here) | (taken - {name}))
        if not said["ok"]:
            raise Conflict(said["said"]) if said["state"] == "taken" else ValueError(said["said"])
        self._write(new_name, rules.with_header(text, name=new_name), to)
        self.ws.audit.write(who, "copy_widget", f"{name} -> {new_name} ({to})")
        await self._changed(new_name)
        return self.get(new_name) | {"to": to}

    def project_widgets(self, names: set[str]) -> dict[str, str]:
        """The project's own widgets among `names`, as their files (an export carries them in widgets/)."""
        out: dict[str, str] = {}
        for name in sorted(names):
            found = self._files.read(name, "project") if self._place(name) == "project" else None
            if found is not None:
                out[f"{rules.FOLDER}/{rules.file_name(name)}"] = found[0]
        return out

    async def delete(self, name: str, who: str = "user") -> dict[str, Any]:
        self._mine(name)
        if who == "agent" and not await self._approvals.ask(
            name,
            "delete_widget",
            f"Delete the widget {name} from the {'project' if self._place(name) == 'project' else 'library'}",
        ):
            raise Refused(f"The user declined (or did not answer): {name} was not deleted.")
        self._files.remove(name, self._place(name))
        self.ws.audit.write(who, "delete_widget", name)
        await self._changed(name)
        return {"ok": True, "deleted": name}

    async def _changed(self, name: str, old: str | None = None) -> None:
        await self.ws.live.broadcast({"type": "widgets_changed", "name": name, "old": old})

    # ===== running =====

    def python(self, body: Any = None) -> str:
        chosen = body.get("python") if isinstance(body, dict) else None
        return str(chosen or self._project_python() or self.live.default_python())

    async def tables_for(self, names: set[str]) -> dict[str, bytes]:
        """The tables a run names, as Parquet (its widgets read data/<stem>.parquet): an open table after
        its grid's steps, a connection's `[Conn].table` read through the connection-tables contract (so
        through that connection's query limit, the one gate every connection run passes). A data.ipynb
        table is data.py's, beside the app. One that cannot be read is left out: the widget says so in
        its place."""
        out: dict[str, bytes] = {}
        open_tables = self._tables()
        for name in sorted(names):
            stem = build_rules.table_stem(name)
            if props_rules.connection_of(name) is not None:
                if self._read_connection_table is not None:
                    with contextlib.suppress(Exception):
                        out[stem] = await self._read_connection_table(name)
            elif name in open_tables and self._table_data is not None:
                with contextlib.suppress(Exception):
                    out[stem] = await self._table_data(name)
        return out

    @staticmethod
    def named_tables(
        canvas: Mapping[str, Any],
        built: Mapping[str, build_rules.Built],
        context: props_rules.Context | None = None,
    ) -> set[str]:
        """The table names a canvas's instances use (their table properties' values)."""
        found: set[str] = set()
        for _page, node in model.walk(canvas):
            if node["kind"] != "widget" or node["widget"] not in built:
                continue
            props = list(built[node["widget"]].properties)
            values = props_rules.values(props, node["values"], context)
            found |= {str(values[p.name]) for p in props if p.type == "table" and values.get(p.name)}
        return found | wiring.tables(canvas)

    def _one_app(self, name: str, body: Any) -> tuple[dict[str, str], Mapping[str, Any]]:
        body = body if isinstance(body, dict) else {}
        widget, _text = self._one(name)
        code: str = body.get("code") if isinstance(body.get("code"), str) else widget.code
        built = self._made(code)
        values = body.get("values") if isinstance(body.get("values"), dict) else {}
        canvas = build_rules.one_widget(name, built, values, widget.size)
        context = self.context(values)
        carried = self.carried(canvas, {name: built})
        return build_rules.build(canvas, {name: built}, context, carried=carried), canvas

    async def run(self, name: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Run in place: the widget alone as a live page, with its properties' current values (the code as
        the editor holds it, saved or not)."""
        files, canvas = self._one_app(name, body)
        context = self.context((body or {}).get("values") if isinstance(body, dict) else None)
        names = self.named_tables(canvas, self._built_one(name, body), context)
        tables = await self.tables_for(names)
        key = f"widget{_key((body or {}).get('window') if isinstance(body, dict) else None)}"
        started = time.monotonic()
        answer: dict[str, Any] = await self.live.run(key, files, tables, self.python(body), names=names)
        self.ws.audit.write(who, "run_widget", name)
        return answer | {"widget": name, "seconds": round(time.monotonic() - started, 2), "key": key}

    def _built_one(self, name: str, body: Any) -> dict[str, build_rules.Built]:
        widget, _ = self._one(name)
        sent = body.get("code") if isinstance(body, dict) else None
        code = sent if isinstance(sent, str) else widget.code
        return {name: self._made(code)}

    async def check(self, name: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """The widget run headless (AppTest): what it drew and its errors (the agent's widgets_run)."""
        files, canvas = self._one_app(name, body)
        tables = await self.tables_for(self.named_tables(canvas, self._built_one(name, body)))
        answer: dict[str, Any] = await self.live.check(
            f"check-{name}",
            files,
            tables,
            self.python(body),
            [p for p in files if p.startswith(build_rules.PAGES + "/")],
        )
        self.ws.audit.write(who, "check_widget", name)
        return answer | {"widget": name}

    async def stop(self, body: Any = None) -> dict[str, Any]:
        key = f"widget{_key((body or {}).get('window') if isinstance(body, dict) else None)}"
        return {"ok": await self.live.stop(key)}

    # ===== previews =====

    def preview_key(self, name: str, theme: str) -> str:
        _widget, text = self._one(name)
        return f"{name}-{_hash(text)}-{'dark' if theme == 'dark' else 'light'}"

    def preview(self, name: str, theme: str = "light") -> dict[str, Any]:
        """The preview's state: ready (its address), failed (why), or coming (asked for now)."""
        key = self.preview_key(name, theme)
        if self._previews is None:
            return {"state": "none"}
        if self._previews.get(key) is not None:
            return {"state": "ready", "url": f"/streamlit/widgets/{name}/preview.png?key={key}", "key": key}
        failed = self._previews.failed(key)
        if failed is not None:
            return {"state": "failed", "said": failed, "key": key}
        return {"state": "coming", "key": key}

    def preview_made(self, key: str, data: bytes) -> None:
        if self._previews is not None:
            self._previews.put(key, data)

    def preview_failed(self, name: str, theme: str, said: str) -> None:
        if self._previews is not None:
            self._previews.fail(self.preview_key(name, theme), said)

    def app_of(self, name: str, body: Any) -> tuple[dict[str, str], Mapping[str, Any]]:
        """The widget alone as an app's files (a Run, a preview) and its one-widget canvas."""
        return self._one_app(name, body)

    def preview_png(self, key: str) -> bytes | None:
        return None if self._previews is None else self._previews.get(key)


def _key(window: Any) -> str:
    text = str(window or "")
    return "-" + "".join(c for c in text if c.isalnum())[:24] if text else ""


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _said(error: props_rules.PropertyError) -> ValueError:
    return ValueError(f"{error} {error.fix}".strip())


def _widget_shape(code: str) -> dict[str, Any]:
    """A widget's properties by name and its code's definitions, as the change log names them (their
    values and text fingerprinted there, never kept)."""
    try:
        found = {p.name: p.default for p in props_rules.detect(code)}
    except (props_rules.PropertyError, SyntaxError):
        found = {}
    return {"properties": found} | change_rules.document_shape("script", code)


def _widget_change(name: str, before: str, after: str) -> dict[str, Any]:
    """The change log's event (the base's services/changes.py) for a widget's code or properties."""
    return raised("widget", name, _widget_shape(before), _widget_shape(after))
