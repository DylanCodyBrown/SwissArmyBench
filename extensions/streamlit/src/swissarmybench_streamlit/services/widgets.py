"""Widgets (the owner, 2026-11-21): the library's widgets and the extension's prebuilt ones, their properties,
the Widgets window's Run (the widget alone, through the Streamlit proxy, in the project's Python) and the
agent's widgets_* commands.

  listing        every widget of a framework: the library's, then the prebuilt (read-only) ones
  get            one widget: its header, its code, its properties (types and masks), where its file is
  new / save     a new widget from the template; its code written (the header kept)
  header         Name and Description (and group, tags, size) written into the header only; a new name
                 checked (available, taken, invalid) and every canvas's instances renamed (`renamed` hook)
  properties     the properties of a widget, or of code as the editor holds it now (live)
  set_property   a property's default written into ONLY its own characters, checked first
  copy           a prebuilt widget as your own (in the library, a free name)
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
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from swissarmybench.services.workspace import Conflict, NotFound, Refused
from swissarmybench_streamlit.domain import canvas_build as build_rules
from swissarmybench_streamlit.domain import canvas_model as model
from swissarmybench_streamlit.domain import widget_properties as props_rules
from swissarmybench_streamlit.domain import widgets as rules
from swissarmybench_streamlit.domain.widgets import Widget, WidgetError

FRAMEWORK = "streamlit"

Renamed = Callable[[str, str], Awaitable[int]]


class Widgets:
    def __init__(
        self,
        ws: Any,
        files: Any,
        live: Any,
        approvals: Any,
        tables: Callable[[], dict[str, list[str] | None]] = dict,
        table_data: Callable[[str], Awaitable[bytes]] | None = None,
        project_python: Callable[[], str | None] = lambda: None,
        previews: Any = None,
        renamed: Renamed | None = None,
        variables: Callable[[], set[str]] = set,
    ) -> None:
        self.ws = ws
        self._files = files  # adapters/widget_files.py WidgetFiles
        self.live = live
        self._approvals = approvals
        self._tables = tables  # the open tables: name -> its columns
        self._table_data = table_data  # an open table's rows as Parquet
        self._project_python = project_python
        self._previews = previews  # adapters/widget_files.py PreviewFiles
        self.renamed = renamed  # every canvas's instances follow a rename (services/canvas.py)
        self._variables = variables

    # ===== reading =====

    def _all(self) -> dict[str, tuple[Widget, str]]:
        """Every widget by name (the library's first: a library widget of a prebuilt one's name hides it)."""
        found: dict[str, tuple[Widget, str]] = {}
        for _file, text, prebuilt in self._files.all():
            try:
                widget = rules.read_widget(text, prebuilt=prebuilt)
            except WidgetError:
                continue
            found.setdefault(widget.name, (widget, text))
        return found

    def names(self) -> set[str]:
        return set(self._all())

    def _one(self, name: str) -> tuple[Widget, str]:
        found = self._files.read(name) if isinstance(name, str) and rules.NAME.match(name) else None
        if found is None:
            raise NotFound(f"There is no widget called {str(name)[:60]}.")
        text, prebuilt = found
        try:
            return rules.read_widget(text, prebuilt=prebuilt), text
        except WidgetError as error:
            raise ValueError(f"{name}'s file does not read: {error}") from None

    def context(self, values: Mapping[str, Any] | None = None) -> props_rules.Context:
        return props_rules.Context(
            tables=self._tables(), variables=self._variables(), values=dict(values or {})
        )

    def _properties(self, code: str) -> tuple[list[props_rules.Property], dict[str, Any] | None]:
        try:
            return props_rules.detect(code, frozenset(self._tables())), None
        except props_rules.PropertyError as error:
            return [], {"error": str(error), "fix": error.fix, "line": error.line}

    def _entry(self, widget: Widget, text: str) -> dict[str, Any]:
        found, problem = self._properties(widget.code)
        return widget.to_json() | {
            "properties": [p.to_json() for p in found],
            "problem": problem,
            "hash": _hash(text),
        }

    def listing(self, framework: str = FRAMEWORK, query: str = "") -> dict[str, Any]:
        words = query.lower().split()
        shown = []
        for widget, text in self._all().values():
            if widget.framework != framework:
                continue
            said = f"{widget.name} {widget.description} {widget.group} {' '.join(widget.tags)}".lower()
            if all(w in said for w in words):
                shown.append(self._entry(widget, text))
        shown.sort(
            key=lambda w: (
                w["prebuilt"],
                rules.GROUPS.index(w["group"]) if w["group"] in rules.GROUPS else 99,
                w["name"],
            )
        )
        return {
            "framework": framework,
            "widgets": shown,
            "groups": list(rules.GROUPS),
            "folder": str(self._files.folder() or ""),
        }

    def get(self, name: str) -> dict[str, Any]:
        widget, text = self._one(name)
        return self._entry(widget, text) | {
            "code": widget.code,
            "file": self._files.where(name) if not widget.prebuilt else "",
            "text": text,
        }

    def facts(self) -> dict[str, model.WidgetFacts]:
        made: dict[str, model.WidgetFacts] = {}
        for name, (widget, _text) in self._all().items():
            found, _ = self._properties(widget.code)
            made[name] = model.WidgetFacts(widget.size, widget.min_size, frozenset(p.name for p in found))
        return made

    def built(self) -> dict[str, build_rules.Built]:
        made: dict[str, build_rules.Built] = {}
        for name, (widget, _text) in self._all().items():
            found, problem = self._properties(widget.code)
            if problem is None:
                made[name] = build_rules.Built(widget.code, tuple(found))
            else:  # code that does not parse: its error shows in its place on the page
                made[name] = build_rules.Built(f"raise SyntaxError({problem['error']!r})", ())
        return made

    def properties(self, body: Any) -> dict[str, Any]:
        """The properties of a widget, or of `code` as the editor holds it (live as it changes)."""
        body = body if isinstance(body, dict) else {}
        code = body.get("code")
        if not isinstance(code, str):
            code = self._one(str(body.get("name")))[0].code
        found, problem = self._properties(code)
        return {"properties": [p.to_json() for p in found], "problem": problem}

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

    # ===== writing =====

    def _mine(self, name: str) -> tuple[Widget, str]:
        widget, text = self._one(name)
        if widget.prebuilt:
            raise Refused(
                f"{name} is a prebuilt widget: it is read-only.",
                fixes=[{"label": "Copy as your own", "action": "try_again", "command": "widgets_copy"}],
            )
        return widget, text

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
        self._files.write(name, rules.write_widget(widget))
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
            self._files.write(name, head + "\n" + rules._CLOSE + "\n" + code)
            self.ws.audit.write(who, "save_widget", name)
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
        if new_name != name:
            self._files.write(new_name, after)
            self._files.remove(name)
            if self.renamed is not None:
                renamed = await self.renamed(name, new_name)
            self.ws.audit.write(who, "rename_widget", f"{name} -> {new_name}")
        elif after != text:
            self._files.write(name, after)
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
        self._files.write(name, head + "\n" + rules._CLOSE + "\n" + after)
        self.ws.audit.write(who, "set_widget_property", f"{name}.{prop}")
        await self._changed(name)
        return self.get(name)

    async def copy(self, name: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        widget, text = self._one(name)
        wanted = (body or {}).get("name") if isinstance(body, dict) else None
        taken = frozenset(self.names())
        new_name = wanted or rules.free_name(f"my_{widget.name}", taken)
        said = rules.check_name(new_name, taken)
        if not said["ok"]:
            raise Conflict(said["said"]) if said["state"] == "taken" else ValueError(said["said"])
        self._files.write(new_name, rules.with_header(text, name=new_name))
        self.ws.audit.write(who, "copy_widget", f"{name} -> {new_name}")
        await self._changed(new_name)
        return self.get(new_name)

    async def delete(self, name: str, who: str = "user") -> dict[str, Any]:
        self._mine(name)
        if who == "agent" and not await self._approvals.ask(
            name, "delete_widget", f"Delete the widget {name} from the library"
        ):
            raise Refused(f"The user declined (or did not answer): {name} was not deleted.")
        self._files.remove(name)
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
        """The open tables a run names, as Parquet (its widgets read data/<name>.parquet)."""
        out: dict[str, bytes] = {}
        if self._table_data is None:
            return out
        open_tables = self._tables()
        for name in names:
            if name in open_tables:
                with contextlib.suppress(Exception):
                    out[name] = await self._table_data(name)
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
        return found

    def _one_app(self, name: str, body: Any) -> tuple[dict[str, str], Mapping[str, Any]]:
        body = body if isinstance(body, dict) else {}
        widget, _text = self._one(name)
        code: str = body.get("code") if isinstance(body.get("code"), str) else widget.code
        found, problem = self._properties(code)
        built = build_rules.Built(
            code if problem is None else f"raise SyntaxError({problem['error']!r})", tuple(found)
        )
        values = body.get("values") if isinstance(body.get("values"), dict) else {}
        canvas = build_rules.one_widget(name, built, values, widget.size)
        context = self.context(values)
        return build_rules.build(canvas, {name: built}, context), canvas

    async def run(self, name: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Run in place: the widget alone as a live page, with its properties' current values (the code as
        the editor holds it, saved or not)."""
        files, canvas = self._one_app(name, body)
        context = self.context((body or {}).get("values") if isinstance(body, dict) else None)
        tables = await self.tables_for(self.named_tables(canvas, self._built_one(name, body), context))
        key = f"widget{_key((body or {}).get('window') if isinstance(body, dict) else None)}"
        started = time.monotonic()
        answer: dict[str, Any] = await self.live.run(key, files, tables, self.python(body))
        self.ws.audit.write(who, "run_widget", name)
        return answer | {"widget": name, "seconds": round(time.monotonic() - started, 2), "key": key}

    def _built_one(self, name: str, body: Any) -> dict[str, build_rules.Built]:
        widget, _ = self._one(name)
        sent = body.get("code") if isinstance(body, dict) else None
        code = sent if isinstance(sent, str) else widget.code
        found, _problem = self._properties(code)
        return {name: build_rules.Built(code, tuple(found))}

    async def check(self, name: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """The widget run headless (AppTest): what it drew and its errors (the agent's widgets_run)."""
        files, canvas = self._one_app(name, body)
        tables = await self.tables_for(self.named_tables(canvas, self._built_one(name, body)))
        answer: dict[str, Any] = await self.live.check(
            f"check-{name}", files, tables, self.python(body), [p for p in files if p.startswith("pages/")]
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
