"""The Canvas's two layouts (the owner, 2026-11-21: "Canvas should only have two layouts phone portrait and
desktop just like powerapps but the difference is our canvas is always resizable to fit the browser or the
phone").

THE FILE, `<app>.canvas.json` (format 2; sorted keys, two-space indent: the same canvas is the same bytes).
Every page holds the same containers and widget instances in both layouts; each keeps its own place in each:

    {"format": 2, "name": "Sales",
     "sizing": {"columns": 12, "row_height": 60, "gap": 8, "snap": true, "step": 1},
     "pages": [{"id": "p1", "name": "Overview", "children": [
         {"id": "c1", "kind": "container", "show": "both",
          "at": {"desktop": {"x": 0.0, "y": 0, "w": 0.496667, "h": 260},
                 "phone": {"x": 0.0, "y": 0, "w": 1.0, "h": 260}},
          "props": {...}, "children": [...]}]}]}

A place's x and w are FRACTIONS of its parent's width (the page's, or its container's), so the built page fits
any width; y and h are pixels. Six decimals round-trip to the same pixel at the design width (desktop 1200 px,
phone 390 px), so a 1 px placement stays. `show` is both, desktop or phone (an item hidden in one layout
only). A widget instance's `"hidden": true` is Hidden in the app: it runs and its Outs flow, but the played,
launched or exported page gives it no space (the canvas draws it faded, with an eye-off mark).

The rules (domain/canvas_model.py, in pixels) hold in each layout: a layout is VIEWED as a canvas of pixels at
its design width, a command runs on that view, and the result is folded back. An item made, or moved into
another container, in one layout is placed in the other by itself: in phone stacked in reading order at full
width, in desktop at the first free place at its size; the user adjusts it there. Columns, row height, gap,
snap and step are shared by both. A format 1 file (pixels, one layout) is read as the desktop layout, its
phone layout made.

Pure rules: no I/O, standard library only.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from swissarmybench_streamlit.domain import canvas_model as engine
from swissarmybench_streamlit.domain.canvas_model import Facts, Read

CanvasError = engine.CanvasError

FORMAT: int = 2
SUFFIX = engine.SUFFIX
OLD_SUFFIX = engine.OLD_SUFFIX
OLD_SAID = engine.OLD_SAID
LAYOUTS: tuple[str, ...] = ("desktop", "phone")
DESIGN: dict[str, int] = {"desktop": engine.WIDTHS["desktop"], "phone": engine.WIDTHS["phone"]}
SHOWS: tuple[str, ...] = ("both", "desktop", "phone")
BREAKPOINT: int = 768  # below it the built page shows the phone layout
DIGITS: int = 6
SIZING_DEFAULT: dict[str, Any] = {k: v for k, v in engine.SIZING_DEFAULT.items() if k != "width"}

walk = engine.walk
find = engine.find
page_of = engine.page_of
rename_widget = engine.rename_widget
prune = engine.prune


def other(layout: str) -> str:
    return "phone" if layout == "desktop" else "desktop"


def check_layout(layout: Any) -> str:
    if layout not in LAYOUTS:
        raise CanvasError("layout is phone or desktop.")
    return str(layout)


def shown(node: Mapping[str, Any], layout: str) -> bool:
    return node.get("show", "both") in ("both", layout)


def new_canvas(name: str) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "name": name[:80] or "App",
        "sizing": dict(SIZING_DEFAULT),
        "pages": [{"id": "p1", "name": "Page 1", "children": []}],
    }


def write(canvas: Mapping[str, Any]) -> str:
    return json.dumps(canvas, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ===== a canvas's card (the Canvas landing page) =====

CARD_BOXES: int = 24  # the most boxes a card's small picture draws


def card(text: str) -> dict[str, Any]:
    """What the landing page's card says of a canvas file, read loosely (a broken file still gets its card):
    how many pages and widgets, its layouts, and its first page's top boxes in the desktop layout (x
    and w fractions of the page's width, y and h pixels) for a small picture. Never a value of a widget."""
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list):
        return {"broken": True, "pages": 0, "widgets": 0, "layouts": [], "boxes": []}
    pages = [p for p in pages if isinstance(p, dict)]
    first = [c for c in (pages[0].get("children") or [] if pages else []) if isinstance(c, dict)]
    return {
        "broken": False,
        "pages": len(pages),
        "widgets": sum(_widgets_in(p.get("children")) for p in pages),
        "layouts": list(LAYOUTS),  # an older one-layout file gets its phone layout as it is read
        "boxes": [b for b in (_card_box(c) for c in first if shown(c, "desktop")) if b][:CARD_BOXES],
    }


def _widgets_in(children: Any) -> int:
    nodes = [c for c in children or [] if isinstance(c, dict)] if isinstance(children, list) else []
    return sum((0 if n.get("kind") == "container" else 1) + _widgets_in(n.get("children")) for n in nodes)


def _card_box(node: Mapping[str, Any]) -> dict[str, Any] | None:
    at = node.get("at")
    # Format 1 keeps pixels on the node itself.
    place: Any = at.get("desktop") if isinstance(at, dict) else node
    try:
        x, y, w, h = (float(place[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(at, dict):  # pixels at the design width
        x, w = x / DESIGN["desktop"], w / DESIGN["desktop"]
    kind = "container" if node.get("kind") == "container" else "widget"
    return {"kind": kind, "x": round(x, 4), "y": round(y), "w": round(w, 4), "h": round(h)}


# ===== fractions and pixels =====


def _px(place: Mapping[str, Any], width: int) -> dict[str, int]:
    w = max(1, round(float(place["w"]) * width))
    x = round(float(place["x"]) * width)
    return {"x": max(0, min(x, width - min(w, width))), "y": int(place["y"]), "w": w, "h": int(place["h"])}


def _frac(node: Mapping[str, Any], width: int) -> dict[str, Any]:
    return {
        "x": round(node["x"] / width, DIGITS),
        "y": int(node["y"]),
        "w": round(node["w"] / width, DIGITS),
        "h": int(node["h"]),
    }


_OWN = ("at", "children", "x", "y", "w", "h")


def view(canvas: Mapping[str, Any], layout: str, skip_missing: bool = False) -> dict[str, Any]:
    """One layout as a canvas of pixels at its design width (domain/canvas_model.py's shape): what its rules
    and commands work on. `skip_missing`: an item with no place in this layout yet is left out (with what it
    holds)."""

    def nodes(children: list[dict[str, Any]], width: int) -> list[dict[str, Any]]:
        made = []
        for child in children:
            place = (child.get("at") or {}).get(layout)
            if place is None:
                if skip_missing:
                    continue
                raise CanvasError(f"{child.get('id')} has no place in the {layout} layout.")
            node = {k: copy.deepcopy(v) for k, v in child.items() if k not in _OWN} | _px(place, width)
            if child["kind"] == "container":
                node["children"] = nodes(child.get("children") or [], node["w"])
            made.append(node)
        return made

    return {
        "format": engine.FORMAT,
        "name": canvas["name"],
        "sizing": {**SIZING_DEFAULT, **canvas["sizing"], "width": layout},
        "pages": [
            {
                **{k: v for k, v in p.items() if k != "children"},
                "children": nodes(p["children"], DESIGN[layout]),
            }
            for p in canvas["pages"]
        ],
    }


def views(canvas: Mapping[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Each page's items in pixels at each layout's design width (what the Canvas page draws)."""
    found: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for layout in LAYOUTS:
        for page in view(canvas, layout)["pages"]:
            found.setdefault(page["id"], {})[layout] = page["children"]
    return found


def _placed(
    view_a: Mapping[str, Any],
    layout: str,
    old: Mapping[str, Any] | None,
    view_b: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """A stored canvas whose structure and `layout` places are view_a's; the other layout's places come from
    view_b when given, else from `old` for each item still under the same parent (None: to be placed)."""
    b = other(layout)
    before: dict[str, tuple[str | None, dict[str, Any]]] = {}
    if old is not None:
        for page, node in walk(old):
            _, parent, _ = find(old, node["id"])
            before[node["id"]] = (parent["id"] if parent else f"page:{page['id']}", node)
    b_places: dict[str, dict[str, Any]] = {}
    if view_b is not None:
        for page in view_b["pages"]:

            def collect(children: list[dict[str, Any]], width: int) -> None:
                for child in children:
                    b_places[child["id"]] = _frac(child, width)
                    if child["kind"] == "container":
                        collect(child["children"], child["w"])

            collect(page["children"], DESIGN[b])

    def store(children: list[dict[str, Any]], width: int, parent_key: str) -> list[dict[str, Any]]:
        made = []
        for child in children:
            node = {k: copy.deepcopy(v) for k, v in child.items() if k not in _OWN}
            node.setdefault("show", "both")
            at = {layout: _frac(child, width)}
            if view_b is not None:
                if child["id"] in b_places:
                    at[b] = b_places[child["id"]]
            else:
                kept = before.get(child["id"])
                if (
                    kept is not None
                    and kept[0] == parent_key
                    and (kept[1].get("at") or {}).get(b) is not None
                ):
                    at[b] = copy.deepcopy(kept[1]["at"][b])
            node["at"] = at
            if child["kind"] == "container":
                node["children"] = store(child["children"], child["w"], child["id"])
            made.append(node)
        return made

    pages = [
        {
            **{k: v for k, v in p.items() if k != "children"},
            "children": store(p["children"], DESIGN[layout], f"page:{p['id']}"),
        }
        for p in view_a["pages"]
    ]
    sizing = {k: v for k, v in view_a["sizing"].items() if k != "width"}
    return {"format": FORMAT, "name": view_a["name"], "sizing": sizing, "pages": pages}


def _missing_ids(canvas: Mapping[str, Any], layout: str) -> list[str]:
    """Items with no place in `layout`, in reading order; an item that has none drops its contents' places
    too."""
    found: list[str] = []

    def look(children: list[dict[str, Any]], lost: bool) -> None:
        for child in sorted(
            children, key=lambda c: (c["at"][other(layout)]["y"], c["at"][other(layout)]["x"])
        ):
            gone = lost or layout not in child["at"]
            if gone:
                child["at"].pop(layout, None)
                found.append(child["id"])
            if child["kind"] == "container":
                look(child.get("children") or [], gone)

    for page in canvas["pages"]:
        look(page["children"], False)
    return found


def _fill(canvas: dict[str, Any], layout: str, facts: Facts | None) -> dict[str, Any]:
    """Each item with no place in `layout` placed there: phone, stacked in reading order at full width;
    desktop, at the first free place at its size. Then the layout's places stored again."""
    missing = _missing_ids(canvas, layout)
    if not missing:
        return canvas
    source = view(canvas, other(layout))
    target = view(canvas, layout, skip_missing=True)
    gap = target["sizing"]["gap"]
    for node_id in missing:
        page_a, parent_a, node_a = find(source, node_id)
        page_b = page_of(target, page_a["id"])
        parent_b = None
        if parent_a is not None:
            _, _, parent_b = find(target, parent_a["id"])
        siblings = parent_b["children"] if parent_b else page_b["children"]
        width = parent_b["w"] if parent_b else DESIGN[layout]
        least = engine.minimum(node_a | {"children": []}, facts, target)
        h = max(node_a["h"], least[1])
        if layout == "phone":
            w = width
            x = 0
            y = engine._bottom(siblings) + gap if siblings else 0
        else:
            w = max(least[0], min(width, round(node_a["w"] * DESIGN["desktop"] / DESIGN["phone"])))
            w = min(w, width)
            spot = engine._free(siblings, width, w, h, None, gap)
            x, y = spot if spot is not None else (0, engine._bottom(siblings) + gap)
        made = {k: copy.deepcopy(v) for k, v in node_a.items() if k not in ("children", "x", "y", "w", "h")}
        made |= {"x": x, "y": y, "w": w, "h": h}
        if node_a["kind"] == "container":
            made["children"] = []
        siblings.append(made)
        if parent_b is not None:
            engine._fit_up(target, parent_b)
    return _placed(source, other(layout), None, target)


def _normal(data: dict[str, Any]) -> dict[str, Any]:
    canvas = copy.deepcopy(data)
    canvas["name"] = str(canvas.get("name") or "App")[:80]
    canvas["sizing"] = {
        **SIZING_DEFAULT,
        **{k: v for k, v in (canvas.get("sizing") or {}).items() if k != "width"},
    }
    engine.check_sizing({**canvas["sizing"], "width": "desktop"})
    pages = canvas.get("pages")
    if not isinstance(pages, list) or not pages:
        raise CanvasError("A canvas has one page at least.", 1)

    def node(item: Any, depth: int) -> dict[str, Any]:
        if not isinstance(item, dict) or item.get("kind") not in ("container", "widget"):
            raise CanvasError("Each thing on a page is a container or a widget.")
        if depth > engine.MAX_DEPTH:
            raise CanvasError(f"Containers go {engine.MAX_DEPTH} deep at most.")
        if item.get("show", "both") not in SHOWS:
            raise CanvasError(f"{item.get('id')}'s show is both, desktop or phone.")
        if "hidden" in item and item["hidden"] is not True:
            raise CanvasError(f"{item.get('id')}'s hidden is true, or left out.")
        item.setdefault("show", "both")
        at = item.get("at")
        if not isinstance(at, dict) or not at:
            raise CanvasError(f"{item.get('id')} has no place.")
        for layout, place in at.items():
            check_layout(layout)
            if not isinstance(place, dict):
                raise CanvasError(f"{item.get('id')}'s {layout} place is x, y, w, h.")
            for key in ("x", "w"):
                value = place.get(key)
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not 0 <= value <= 1.000001
                ):
                    raise CanvasError(
                        f"{item.get('id')}'s {layout} {key} is a fraction of its parent's width."
                    )
            for key in ("y", "h"):
                value = place.get(key)
                if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= engine.MAX_PX:
                    raise CanvasError(f"{item.get('id')}'s {layout} {key} is a whole number of pixels.")
        if item["kind"] == "container":
            item["children"] = [node(c, depth + 1) for c in item.get("children") or []]
        return item

    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("id"), str):
            raise CanvasError("A page has an id.")
        page["children"] = [node(c, 0) for c in page.get("children") or []]
    return canvas


def problems(canvas: Mapping[str, Any], facts: Facts | None = None, sizes: bool = True) -> list[str]:
    """Every broken rule, in either layout."""
    found: list[str] = []
    for layout in LAYOUTS:
        found += [f"{p} ({layout})" for p in engine.problems(view(canvas, layout), facts, sizes)]
    return found


def read(text: str, facts: Facts | None = None) -> Read:
    """A canvas file, validated (domain/canvas_model.py read's answers): its line when it does not read, a
    newer one read-only, a missing widget a placeholder. A format 1 file is the desktop layout, its phone one
    made."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise CanvasError(f"The canvas file does not read as JSON ({error.msg}).", error.lineno) from None
    if not isinstance(data, dict):
        raise CanvasError("The canvas file is not a canvas.", 1)
    form = data.get("format")
    if not isinstance(form, int) or isinstance(form, bool):
        raise CanvasError("The canvas file has no format: it is not a canvas.", 1)
    if form > FORMAT:
        return Read(data, read_only="This canvas was made by a newer version of the app: it opens read-only.")
    if form == 1:
        old = engine.read(text, facts)
        desktop = copy.deepcopy(old.canvas)
        width = engine.page_width(desktop)
        if width != DESIGN["desktop"]:  # a centred page: its places scaled to the desktop width
            for page in desktop["pages"]:
                for child in page["children"]:
                    child["x"] = round(child["x"] * DESIGN["desktop"] / width)
                    child["w"] = round(child["w"] * DESIGN["desktop"] / width)
        desktop["sizing"]["width"] = "desktop"
        canvas = _fill(_placed(desktop, "desktop", None), "phone", facts)
        return Read(
            canvas,
            missing=old.missing,
            notes=["This canvas now has a phone layout, made from its desktop one."],
        )
    try:
        canvas = _normal(data)
        for layout in LAYOUTS:
            canvas = _fill(canvas, layout, facts)
        found = problems(canvas, facts, sizes=False)
    except CanvasError as error:
        raise CanvasError(str(error), error.line or engine._line_of(text, str(error))) from None
    if found:
        raise CanvasError(
            f"The canvas file breaks its own rules: {found[0]}", engine._line_of(text, found[0])
        )
    missing = [
        n["id"]
        for _, n in walk(canvas)
        if n["kind"] == "widget" and facts is not None and n["widget"] not in facts
    ]
    return Read(canvas, missing=missing)


# ===== commands =====


def apply(
    canvas: dict[str, Any], kind: str, body: Mapping[str, Any], facts: Facts
) -> tuple[dict[str, Any], str | None]:
    """One command in one layout (`layout`, default desktop): the new canvas and what it made. The command
    runs on that layout's pixels (domain/canvas_model.py's rules), the other layout keeps its places (a new
    item is placed there by itself), and every rule is checked in both."""
    body = dict(body)
    layout = check_layout(body.pop("layout", "desktop"))
    if kind == "show":
        after = copy.deepcopy(canvas)
        _, _, node = find(after, str(body.get("id")))
        show = body.get("show")
        if show not in SHOWS:
            raise CanvasError("Show on is both, desktop or phone.")
        node["show"] = show
        return after, None
    if kind == "hide":  # Hidden in the app: it still runs and its Outs flow; it takes no space on the page
        after = copy.deepcopy(canvas)
        _, _, node = find(after, str(body.get("id")))
        if not isinstance(body.get("hidden"), bool):
            raise CanvasError("Hidden in the app is true or false.")
        if body["hidden"]:
            node["hidden"] = True
        else:
            node.pop("hidden", None)
        return after, None
    before = set(problems(canvas, facts))
    if kind == "sizing":
        sized_a = engine.set_sizing(view(canvas, layout), body, facts)
        sized_b = engine.set_sizing(view(canvas, other(layout)), body, facts)
        after = _placed(sized_a, layout, None, sized_b)
        made = None
    else:
        changed, made = engine.apply(view(canvas, layout), kind, body, facts)
        after = _fill(_placed(changed, layout, canvas), other(layout), facts)
    found = [p for p in problems(after, facts) if p not in before]
    if found:
        raise CanvasError(found[0])
    return after, made
