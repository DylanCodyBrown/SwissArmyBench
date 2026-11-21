"""The canvas's wiring (the owner, 2026-11-21): each widget instance's Ins given a source, its Events given
actions, kept in the canvas file beside its values (`"wires": {port: wire}`, byte-stable with the rest).

    an In's wire        {"table": "orders"}            an open, data.ipynb or connection table ([Conn].t;
                                                       the project's sandbox: [Sandbox].orders)
                        {"out": "w3.filtered"}         another instance's Out (or an Event's last payload),
                                                       on its page or another one (an app-wide value: the
                                                       Out's last value is kept across pages)
                        {"out": "app.viewer"}          who is viewing (the app's own Out: their sign-in
                                                       name, this computer's user name in Play, else
                                                       "unknown")
                        {"page": "last_visit"}         a page value an Event's action set (or an older widget)
                        {"endpoint": "GET /orders"}    the local sandbox API's answer
                        {"variable": "REGION"}         a variable of this computer
                        {"value": "West"}              a typed constant
                        {"tables": [wire, ...]}        a list[Table] In: tables or Outs, in order
    an Event's wire     {"actions": [{"do": "call", "endpoint": "POST /visits",
                         "body": "values" | {field: path}, "params": {name: path}},
                         {"do": "set", "key": "last_visit", "value": "values"}, {"do": "rerun"}]}

An In with no wire takes the one Out of the same name and a fitting type on its page, when there is exactly
one (an automatic wire, said as such; an In[str] called viewer takes app.viewer); else its own starting
value. A wire that no longer holds (its widget or
Out deleted, a type changed) is broken: marked on both ends, listed before Play, and said in its place on the
page while the In takes its starting value.

Pure rules: no I/O, standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from swissarmybench_streamlit.domain import canvas_layouts as model
from swissarmybench_streamlit.domain import widget_contract as contract
from swissarmybench_streamlit.domain.widget_contract import ContractError, Port

KINDS: tuple[str, ...] = ("table", "out", "page", "endpoint", "variable", "value", "tables")
ACTIONS: tuple[str, ...] = ("call", "set", "rerun")
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,80}$")
_REF = re.compile(r"^([a-z][0-9]+|app)\.([A-Za-z_][A-Za-z0-9_]{0,80})$")
_PATH = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]{0,80}(?:\.[A-Za-z_][A-Za-z0-9_]{0,80}){0,8})?$")
_ENDPOINT = re.compile(r"^(GET|POST|PUT|PATCH|DELETE) /\S*$")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
MAX_ACTIONS = 8
OUT_KEY = "sab:"  # an Out's session state key: sab:<instance>.<port>
VIEWER = "app.viewer"  # the app's own Out: who is viewing (the runtime's viewer())
# The viewer's other claims (the owner approved, 2026-11-21): only what the host's sign-in gives (Azure App
# Service's, Streamlit's st.user); empty when it does not, never this computer's on a shared run.
VIEWER_OUTS = {
    VIEWER: "str",
    "app.viewer_email": "str",
    "app.viewer_id": "str",
    "app.viewer_roles": "list[str]",
}
APP_OUTS: dict[str, dict[str, Any]] = {
    ref: {
        "type": kind,
        "instance": "app",
        "widget": "app",
        "port": ref.split(".", 1)[1],
        "direction": "out",
        "page": "",
    }
    for ref, kind in VIEWER_OUTS.items()
}


@dataclass(frozen=True)
class Context:
    """What a wire is checked against: the page's Outs ("w3.filtered" -> type), the endpoints, variables and
    tables there are (None: not known here)."""

    outs: Mapping[str, str] = field(default_factory=dict)
    endpoints: set[str] | None = None
    variables: set[str] | None = None
    tables: set[str] | None = None


def _source_type(wire: Mapping[str, Any], context: Context) -> str | None:
    """The type a source gives (None: any, not known until it runs)."""
    if "table" in wire:
        return "Table"
    if "out" in wire:
        return context.outs.get(str(wire["out"]))
    if "variable" in wire:
        return "str"
    return None


def check_in(port: Port, wire: Any, context: Context) -> None:
    """An In's wire, checked: its shape, its source there, its type fitting the In's. Raises ContractError
    with the reason in one sentence."""
    if not isinstance(wire, dict) or len(wire) != 1 or next(iter(wire)) not in KINDS:
        raise ContractError(
            f"{port.name}'s source is one of: a table, another widget's Out, a page value, an endpoint, a "
            "variable or a value.",
            "Pick its source from the list.",
        )
    kind, value = next(iter(wire.items()))
    wanted = port.type
    if kind == "tables":
        if not wanted.startswith("list[Table"):
            raise ContractError(f"{port.name} takes {contract.words(wanted)}, not a list of tables.")
        if not isinstance(value, list) or not 1 <= len(value) <= 20:
            raise ContractError(f"{port.name} takes 1 to 20 tables.", "Add a table, or take some out.")
        for item in value:
            if not isinstance(item, dict) or next(iter(item), "") not in ("table", "out", "page"):
                raise ContractError(f"Each of {port.name}'s tables is a table, an Out or a page value.")
            check_in(Port(port.name, "in", "Table"), item, context)
        return
    if kind == "table":
        if not isinstance(value, str) or not value:
            raise ContractError(f"{port.name}'s table has a name.", "Pick a table.")
        if context.tables is not None and value not in context.tables and not value.startswith("["):
            raise ContractError(f"There is no table called {value[:60]} here.", "Pick a table from the list.")
    elif kind == "out":
        if not isinstance(value, str) or not _REF.match(value):
            raise ContractError(f"{port.name} reads an Out as <widget id>.<name>, as w3.filtered.")
        if value not in context.outs:
            raise ContractError(
                f"No widget of this app has an Out {value}.",
                "Pick one of the app's Outs, or wire it again.",
            )
    elif kind == "page":
        if not isinstance(value, str) or not _KEY.match(value):
            raise ContractError(
                f"{str(value)[:40]!r} is not a page value's key.", "Type a key, as last_visit."
            )
    elif kind == "endpoint":
        if not isinstance(value, str) or not value.startswith("GET ") or not _ENDPOINT.match(value):
            raise ContractError(f"{port.name} reads a GET endpoint's answer, as GET /orders.")
        if context.endpoints is not None and value not in context.endpoints:
            raise ContractError(f"API.py has no endpoint {value}.", "Pick one of its endpoints, or add it.")
        if wanted not in ("Table", "dict", "list") and not wanted.startswith("list"):
            raise ContractError(f"{port.name} takes {contract.words(wanted)}: an endpoint answers JSON.")
    elif kind == "variable":
        if not isinstance(value, str) or not _ENV.match(value):
            raise ContractError(f"{str(value)[:40]!r} is not a variable's name.", "Pick a variable.")
        if context.variables is not None and value not in context.variables:
            raise ContractError(
                f"{value} is not set on this computer.", f"Set {value} on the Variables page."
            )
        if wanted not in ("str", "int", "float", "bool", "date", "datetime"):
            raise ContractError(f"{port.name} takes {contract.words(wanted)}: a variable is text.")
        return
    elif kind == "value":
        if not contract.fits_value(wanted, value):
            raise ContractError(f"{port.name} takes {contract.words(wanted)}: that value is not.")
        return
    given = _source_type(wire, context)
    if given is not None and not contract.fits(given, wanted):
        raise ContractError(
            f"{port.name} takes {contract.words(wanted)}: {value} gives {contract.words(given)}.",
            "Pick a source of the same type.",
        )


def check_event(port: Port, wire: Any, endpoints: set[str] | None = None) -> None:
    """An Event's wire: its actions, each checked."""
    if not isinstance(wire, dict) or set(wire) != {"actions"} or not isinstance(wire["actions"], list):
        raise ContractError(f'{port.name}\'s wiring is its actions: {{"actions": [...]}}.')
    if len(wire["actions"]) > MAX_ACTIONS:
        raise ContractError(f"{port.name} takes {MAX_ACTIONS} actions at most.")
    for action in wire["actions"]:
        do = action.get("do") if isinstance(action, dict) else None
        if do not in ACTIONS:
            raise ContractError(f"An action does one of: {', '.join(ACTIONS)}.", "Pick what it does.")
        if do == "call":
            endpoint = action.get("endpoint")
            if not isinstance(endpoint, str) or not _ENDPOINT.match(endpoint):
                raise ContractError(f"{port.name} calls an endpoint, as POST /orders.", "Pick an endpoint.")
            if endpoints is not None and endpoint not in endpoints:
                raise ContractError(f"API.py has no endpoint {endpoint}.", "Pick one of its endpoints.")
            body = action.get("body", "")
            paths = list(body.values()) if isinstance(body, dict) else [body]
            params = action.get("params") or {}
            if not isinstance(body, (str, dict)) or not isinstance(params, dict):
                raise ContractError(f"{port.name}'s body is a part of the payload, or a field each.")
            if not all(isinstance(p, str) and _PATH.match(p) for p in [*paths, *params.values()]):
                raise ContractError(
                    f"{port.name}'s body names parts of the payload, as values.store.",
                    "Pick them from the list.",
                )
        elif do == "set":
            if not isinstance(action.get("key"), str) or not _KEY.match(action["key"]):
                raise ContractError(
                    f"{port.name} sets a page value: give its key.", "Type a key, as last_saved."
                )
            if not isinstance(action.get("value", ""), str) or not _PATH.match(action.get("value", "")):
                raise ContractError(f"{port.name}'s value is a part of the payload.")


# ===== the canvas's wiring as a whole =====


def _instances(canvas: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(page["id"], node) for page, node in _walk(canvas) if node["kind"] == "widget"]


def _walk(canvas: Mapping[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    found: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def inside(page: dict[str, Any], children: list[dict[str, Any]]) -> None:
        for child in children:
            found.append((page, child))
            if child["kind"] == "container":
                inside(page, child["children"])

    for page in canvas["pages"]:
        inside(page, page["children"])
    return found


def page_outs(
    canvas: Mapping[str, Any], page_id: str, contracts: Mapping[str, list[Port]]
) -> dict[str, dict[str, Any]]:
    """The Outs (and Events' payloads) of a page's instances: "w3.filtered" -> {type, instance, widget, port,
    direction}."""
    found: dict[str, dict[str, Any]] = {}
    for page, node in _instances(canvas):
        if page != page_id:
            continue
        for port in contracts.get(node["widget"], []):
            if port.direction in ("out", "event") and port.problem is None:
                found[f"{node['id']}.{port.name}"] = {
                    "type": port.type,
                    "instance": node["id"],
                    "widget": node["widget"],
                    "port": port.name,
                    "direction": port.direction,
                    "page": page,
                }
    return found


def every_out(canvas: Mapping[str, Any], contracts: Mapping[str, list[Port]]) -> dict[str, dict[str, Any]]:
    """Every Out of the app (each page's instances', and the app's own app.viewer): an In reads one from any
    page."""
    found: dict[str, dict[str, Any]] = {}
    for page in canvas["pages"]:
        found |= page_outs(canvas, page["id"], contracts)
    return found | APP_OUTS


def analyse(
    canvas: Mapping[str, Any],
    contracts: Mapping[str, list[Port]],
    endpoints: set[str] | None = None,
    variables: set[str] | None = None,
    tables: set[str] | None = None,
    seen: Mapping[str, list[str]] | None = None,
) -> dict[str, Any]:
    """The whole wiring: each instance's sources (its wires, automatic ones, broken ones), each Out's readers,
    the wires to draw (a wire from another page marked `cross`, with its page), the broken list (both ends),
    each Out[Table]'s columns (declared as Table[Row], else as its last run had them: `seen`), in the
    canvas's order."""
    sources: dict[str, dict[str, Any]] = {}
    readers: dict[str, list[str]] = {}
    wires: list[dict[str, Any]] = []
    broken: list[dict[str, Any]] = []
    outs_by_page = {page["id"]: page_outs(canvas, page["id"], contracts) for page in canvas["pages"]}
    every = every_out(canvas, contracts)
    for page_id, node in _instances(canvas):
        ports = {p.name: p for p in contracts.get(node["widget"], [])}
        mine: dict[str, Any] = {}
        outs = outs_by_page[page_id] | APP_OUTS
        context = Context(
            {k: v["type"] for k, v in every.items() if v["instance"] != node["id"]},
            endpoints,
            variables,
            tables,
        )
        given = node.get("wires") or {}
        for name, wire in sorted(given.items()):
            port = ports.get(name)
            if port is None:
                reason = f"{node['widget']} has no In or Event {name} any more."
                broken.append({"instance": node["id"], "port": name, "reason": reason, "source": _ref(wire)})
                continue
            try:
                if port.direction == "event":
                    check_event(port, wire, endpoints)
                else:
                    check_in(port, wire, context)
            except ContractError as error:
                reason = _gone(wire, every) or str(error)
                broken.append({"instance": node["id"], "port": name, "reason": reason, "source": _ref(wire)})
                mine[name] = {"broken": reason}
                continue
            mine[name] = wire
            for ref in _refs(wire):
                readers.setdefault(ref, []).append(f"{node['id']}.{name}")
                wires.append(_line(ref, f"{node['id']}.{name}", False, every, page_id))
        for port in ports.values():
            if port.direction != "in" or port.name in given or port.problem:
                continue
            same = [
                k
                for k, v in outs.items()
                if v["port"] == port.name
                and v["instance"] != node["id"]
                and contract.fits(v["type"], port.type)
            ]
            if len(same) == 1:
                mine[port.name] = {"out": same[0]}
                readers.setdefault(same[0], []).append(f"{node['id']}.{port.name}")
                wires.append(_line(same[0], f"{node['id']}.{port.name}", True, every, page_id))
        sources[node["id"]] = mine
    return {
        "sources": sources,
        "readers": readers,
        "wires": wires,
        "broken": broken,
        "outs": every,
        "columns": out_columns(every, contracts, seen),
    }


def _line(ref: str, to: str, auto: bool, every: Mapping[str, Any], page_id: str) -> dict[str, Any]:
    """A wire to draw: from an Out to an In; one from another page (or the app's own) said as `cross`."""
    source_page = str((every.get(ref) or {}).get("page", ""))
    made: dict[str, Any] = {"from": ref, "to": to, "auto": auto}
    if source_page != page_id:
        made |= {"cross": True, "page": source_page}
    return made


def out_columns(
    every: Mapping[str, Any], contracts: Mapping[str, list[Port]], seen: Mapping[str, list[str]] | None = None
) -> dict[str, list[str]]:
    """Each Out holding a table's columns: declared (Out[Table[Row]]: Row's fields), else the last run's
    (seen); an Out whose columns are not known yet is left out (its column properties are typed)."""
    found: dict[str, list[str]] = {}
    for ref, out in every.items():
        if out["type"] != "Table":
            continue
        port = next((p for p in contracts.get(out["widget"], []) if p.name == out["port"]), None)
        if port is not None and port.fields:
            found[ref] = [name for name, _type in port.fields]
        elif seen and isinstance(seen.get(ref), list):
            found[ref] = [str(c) for c in seen[ref]][:500]
    return found


def _refs(wire: Mapping[str, Any]) -> list[str]:
    if "out" in wire:
        return [str(wire["out"])]
    if "tables" in wire:
        return [str(i["out"]) for i in wire["tables"] if isinstance(i, dict) and "out" in i]
    return []


def _ref(wire: Any) -> str | None:
    refs = _refs(wire) if isinstance(wire, dict) else []
    return refs[0] if refs else None


def _gone(wire: Any, every_out: Mapping[str, Any]) -> str | None:
    """Why an Out a wire reads is gone, in words (None: it is there)."""
    for ref in _refs(wire) if isinstance(wire, dict) else []:
        if ref in every_out:
            continue
        instance = ref.split(".", 1)[0]
        if any(k.split(".", 1)[0] == instance for k in every_out):
            return f"{instance} has no Out {ref.split('.', 1)[1]} any more."
        return f"The widget {instance} it read from was deleted."
    return None


def order(children: list[dict[str, Any]], needs: Mapping[str, set[str]]) -> list[dict[str, Any]]:
    """Siblings in the order they run: each after the instances its Ins read (a container after what any of
    its widgets read), else the page's order (top to bottom, left to right); a cycle keeps the page's
    order."""
    placed = sorted(children, key=lambda c: (c["at"]["desktop"]["y"], c["at"]["desktop"]["x"]))

    def inside(node: dict[str, Any]) -> set[str]:
        if node["kind"] == "widget":
            return {node["id"]}
        return set().union(*[inside(c) for c in node["children"]]) if node["children"] else set()

    held = {c["id"]: inside(c) for c in placed}
    wants = {c["id"]: {r for i in held[c["id"]] for r in needs.get(i, set())} - held[c["id"]] for c in placed}
    done: list[dict[str, Any]] = []
    left = list(placed)
    while left:
        ready = next(
            (c for c in left if not any(wants[c["id"]] & held[o["id"]] for o in left if o is not c)),
            None,
        )
        if ready is None:  # a cycle: the rest in the page's order
            done += left
            break
        done.append(ready)
        left.remove(ready)
    return done


def needs(sources: Mapping[str, Mapping[str, Any]]) -> dict[str, set[str]]:
    """Each instance's sources' instances (what it reads from)."""
    return {
        instance: {
            ref.split(".", 1)[0] for wire in wires.values() if isinstance(wire, dict) for ref in _refs(wire)
        }
        for instance, wires in sources.items()
    }


def api_calls(canvas: Mapping[str, Any]) -> list[str]:
    """The local sandbox API endpoints the canvas reads or calls ("POST /visits"), sorted, each once."""
    found: set[str] = set()
    for _page, node in _instances(canvas):
        for wire in (node.get("wires") or {}).values():
            if not isinstance(wire, dict):
                continue
            if isinstance(wire.get("endpoint"), str):
                found.add(wire["endpoint"])
            for action in wire.get("actions") or []:
                if (
                    isinstance(action, dict)
                    and action.get("do") == "call"
                    and isinstance(action.get("endpoint"), str)
                ):
                    found.add(action["endpoint"])
    return sorted(found)


def tables(canvas: Mapping[str, Any]) -> set[str]:
    """The tables the canvas's wires read (each to be written beside the app as data/<stem>.parquet)."""
    found: set[str] = set()
    for _page, node in _instances(canvas):
        for wire in (node.get("wires") or {}).values():
            if not isinstance(wire, dict):
                continue
            listed = wire.get("tables")
            items: list[Any] = listed if isinstance(listed, list) else [wire]
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("table"), str) and item["table"]:
                    found.add(item["table"])
    return found


def set_wire(
    canvas: dict[str, Any], body: Mapping[str, Any], ports: set[str] | None = None
) -> dict[str, Any]:
    """An instance's wire set (None takes it away). The wire's own check is the caller's (it knows the
    page)."""
    import copy

    canvas = copy.deepcopy(canvas)
    _, _, node = model.find(canvas, str(body.get("id")))
    if node["kind"] != "widget":
        raise model.CanvasError(f"{node['id']} is a container: it has no Ins or Events.")
    name = body.get("port")
    if not isinstance(name, str) or (ports is not None and name not in ports):
        raise model.CanvasError(f"{node['widget']} has no In or Event {str(name)[:40]}.")
    wires = dict(node.get("wires") or {})
    if body.get("wire") is None:
        wires.pop(name, None)
    else:
        wires[name] = body["wire"]
    if wires:
        node["wires"] = wires
    else:
        node.pop("wires", None)
    return canvas
