"""The Canvas (the owner, 2026-11-21: "I want a simple grid container layout with sizing options at the top,
we can drag and draw containers or right click and insert all available streamlit widgets"; "should be able to
turn on snap to"; "with a very fine precision", "finer than the precision I see in this mockup"): its file and
its rules.

THE FILE, `<app>.canvas.json` (a project file; sorted keys, two-space indent, a newline at its end: the same
canvas is the same bytes). Every place and size is in pixels of the page, so nothing rounds away a fine
placement; the grid's columns are a guide to snap to, never a limit:

    {"format": 1, "name": "Sales",
     "sizing": {"columns": 12, "row_height": 60, "gap": 8, "width": "wide", "snap": true, "step": 1},
     "pages": [{"id": "p1", "name": "Overview", "children": [
         {"id": "c1", "kind": "container", "x": 0, "y": 0, "w": 596, "h": 260,
          "props": {"title": "Sales", "border": true, "scrollable": false, ...},
          "children": [{"id": "w1", "kind": "widget", "widget": "kpi_card",
                        "x": 12, "y": 36, "w": 290, "h": 128, "values": {"title": "Revenue"}}]}]}]}

The page is WIDTHS[width] pixels wide (wide 1200, centered 704: Streamlit's centred column); a page holds
containers; a container holds containers and widget instances, placed in its own box (pixels from its top-left
corner). An instance keeps only the values it overrides; the widget's file keeps the defaults. `snap` and
`step` (1, 2, 4 or 8 px, or "grid": a grid cell) are how the editor moves things; they are kept with the
canvas.

THE RULES, kept here (not only in the page), for the user's moves and the agent's commands alike:
  - nothing overlaps its siblings (only a child inside its parent);
  - nothing leaves its container or the page's width;
  - a widget is never smaller than its min_size (grid cells), nor a container than what it holds;
  - changing the page's width scales what is on it; changing the columns (the page's or a container's)
    moves each edge that sat on a column line to the new line; either way anything that would overlap moves
    down (a container grows when its children need more room).
`problems(canvas)` lists every broken rule (none, always, after a command: tests drive random commands).

Commands (`apply`) are pure: a canvas in, a new canvas out (the service keeps undo and redo as snapshots).
Pure rules: no I/O, standard library only.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

FORMAT: int = 1
SUFFIX: str = ".canvas.json"
OLD_SUFFIX: str = ".stapp.json"
OLD_SAID: str = (
    "App notebooks and their canvases were replaced by widgets: make a new canvas and insert widgets."
)
WIDTHS: dict[str, int] = {"wide": 1200, "centered": 704, "desktop": 1200, "phone": 390}
STEPS: tuple[int | str, ...] = (1, 2, 4, 8, "grid")
MAX_COLUMNS: int = 48
MAX_PX: int = 20_000
MIN_PX: int = 8
MAX_PAGES: int = 30
MAX_NODES: int = 2_000
MAX_DEPTH: int = 6
HEIGHTS: tuple[str, ...] = ("fit", "fixed")
SIZING_DEFAULT: dict[str, Any] = {
    "columns": 12,
    "row_height": 60,
    "gap": 8,
    "width": "wide",
    "snap": True,
    "step": 1,
}
CONTAINER_DEFAULT: dict[str, Any] = {
    "title": "",
    "border": True,
    "padding": 8,
    "height": "fit",
    "scrollable": False,
    "resizable": False,
    "background": "",
    "columns": 12,
}
_COLOUR = re.compile(r"^(#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}))?$")
_ID = re.compile(r"^[a-z]\d{1,6}$")
PLACE = ("x", "y", "w", "h")


class CanvasError(ValueError):
    """A command the rules refuse, or a file that does not read (one sentence; `line` for a file)."""

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.line = line


@dataclass(frozen=True)
class WidgetFacts:
    """What the rules need of a widget: its size and smallest size (grid cells), its properties' names."""

    size: tuple[int, int] = (4, 2)
    min_size: tuple[int, int] = (1, 1)
    properties: frozenset[str] = frozenset()


Facts = Mapping[str, WidgetFacts]


# ===== the grid, as pixels =====


def page_width(canvas: Mapping[str, Any]) -> int:
    return WIDTHS[canvas["sizing"]["width"]]


def cell_width(width: float, columns: int, gap: int) -> float:
    return max(1.0, (width - (columns - 1) * gap) / columns)


def cells(canvas: Mapping[str, Any], w: int, h: int) -> tuple[int, int]:
    """w by h of the page's grid cells, as pixels."""
    sizing = canvas["sizing"]
    gap = sizing["gap"]
    column = cell_width(page_width(canvas), sizing["columns"], gap)
    return round(w * column + (w - 1) * gap), round(h * sizing["row_height"] + (h - 1) * gap)


def lines(width: float, columns: int, gap: int) -> list[float]:
    """The column lines of a box (each column's left and right edge)."""
    column = cell_width(width, columns, gap)
    found: list[float] = []
    for i in range(columns):
        left = i * (column + gap)
        found += [left, left + column]
    return found


# ===== the file =====


def new_canvas(name: str) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "name": name[:80] or "App",
        "sizing": dict(SIZING_DEFAULT),
        "pages": [{"id": "p1", "name": "Page 1", "children": []}],
    }


def write(canvas: Mapping[str, Any]) -> str:
    return json.dumps(canvas, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


@dataclass
class Read:
    canvas: dict[str, Any]
    read_only: str | None = None  # why it opens read-only (a newer format)
    missing: list[str] = field(default_factory=list)  # instances whose widget is not there: their ids
    notes: list[str] = field(default_factory=list)


def read(text: str, facts: Facts | None = None) -> Read:
    """A canvas file, validated. A file that does not read raises CanvasError with its line (the service
    keeps it as it is and opens nothing over it). A newer format opens read-only; an instance of a widget
    that is gone stays as a placeholder (`missing`)."""
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
    try:
        canvas = _normal(data)
    except CanvasError as error:
        raise CanvasError(str(error), error.line or _line_of(text, str(error))) from None
    found = problems(canvas, facts, sizes=False)
    if found:
        raise CanvasError(f"The canvas file breaks its own rules: {found[0]}", _line_of(text, found[0]))
    missing = [
        n["id"]
        for _, n in walk(canvas)
        if n["kind"] == "widget" and facts is not None and n["widget"] not in facts
    ]
    return Read(canvas, missing=missing)


def _line_of(text: str, problem: str) -> int | None:
    found = re.search(r"\b([a-z]\d{1,6})\b", problem)
    if not found:
        return None
    at = text.find(f'"id": "{found.group(1)}"')
    return text.count("\n", 0, at) + 1 if at >= 0 else None


def _int(value: Any, low: int, high: int, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise CanvasError(f"{what} is a whole number from {low} to {high}.")
    return value


def _normal(data: dict[str, Any]) -> dict[str, Any]:
    """The canvas with every field there and of its type (unknown fields kept)."""
    canvas = copy.deepcopy(data)
    canvas["name"] = str(canvas.get("name") or "App")[:80]
    canvas["sizing"] = {**SIZING_DEFAULT, **(canvas.get("sizing") or {})}
    check_sizing(canvas["sizing"])
    pages = canvas.get("pages")
    if not isinstance(pages, list) or not pages:
        raise CanvasError("A canvas has one page at least.", 1)
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("id"), str):
            raise CanvasError("A page has an id.")
        page["name"] = str(page.get("name") or "Page")[:60]
        page["children"] = [_node(c, 0) for c in page.get("children") or []]
    return canvas


def _node(node: Any, depth: int) -> dict[str, Any]:
    if not isinstance(node, dict) or node.get("kind") not in ("container", "widget"):
        raise CanvasError("Each thing on a page is a container or a widget.")
    if depth > MAX_DEPTH:
        raise CanvasError(f"Containers go {MAX_DEPTH} deep at most.")
    if not isinstance(node.get("id"), str) or not _ID.match(node["id"]):
        raise CanvasError(f"{str(node.get('id'))[:20]} is not an id this canvas uses.")
    for key in PLACE:
        node[key] = _int(node.get(key), 0 if key in ("x", "y") else 1, MAX_PX, f"{node['id']}'s {key}")
    if node["kind"] == "container":
        node["props"] = {**CONTAINER_DEFAULT, **(node.get("props") or {})}
        check_container_props(node["props"])
        node["children"] = [_node(c, depth + 1) for c in node.get("children") or []]
    else:
        if not isinstance(node.get("widget"), str) or not node["widget"]:
            raise CanvasError(f"{node['id']} names no widget.")
        values = node.get("values") or {}
        if not isinstance(values, dict):
            raise CanvasError(f"{node['id']}'s values are names and values.")
        node["values"] = values
    return node


def check_sizing(sizing: Mapping[str, Any]) -> None:
    _int(sizing.get("columns"), 1, MAX_COLUMNS, "The columns")
    _int(sizing.get("row_height"), 8, 400, "The row height")
    _int(sizing.get("gap"), 0, 64, "The gap")
    if sizing.get("width") not in WIDTHS:
        raise CanvasError("The page's width is wide or centered.")
    if not isinstance(sizing.get("snap"), bool):
        raise CanvasError("Snap is on or off.")
    if sizing.get("step") not in STEPS or isinstance(sizing.get("step"), bool):
        raise CanvasError("The snap step is 1, 2, 4 or 8 px, or grid (a grid cell).")


def check_container_props(props: Mapping[str, Any]) -> None:
    if not isinstance(props.get("title"), str) or len(props["title"]) > 120:
        raise CanvasError("A container's title is text, 120 characters at most.")
    for flag in ("border", "scrollable", "resizable"):
        if not isinstance(props.get(flag), bool):
            raise CanvasError(f"A container's {flag} is on or off.")
    _int(props.get("padding"), 0, 64, "A container's padding")
    if props.get("height") not in HEIGHTS:
        raise CanvasError("A container's height is fit or fixed.")
    if not isinstance(props.get("background"), str) or not _COLOUR.match(props["background"]):
        raise CanvasError("A container's background is a colour, as #f5f5f5, or none.")
    _int(props.get("columns"), 1, MAX_COLUMNS, "A container's columns")
    if props.get("scrollable") and props.get("height") != "fixed":
        raise CanvasError("A scrollable container has a fixed height.")


# ===== walking =====


def walk(canvas: Mapping[str, Any]) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Every node with its page."""

    def nodes(children: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for child in children:
            yield child
            if child["kind"] == "container":
                yield from nodes(child["children"])

    for page in canvas["pages"]:
        for node in nodes(page["children"]):
            yield page, node


def find(
    canvas: Mapping[str, Any], node_id: str
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    """(page, parent or None for the page's own level, node)."""

    def look(children: list[dict[str, Any]], parent: dict[str, Any] | None) -> tuple[Any, Any] | None:
        for child in children:
            if child["id"] == node_id:
                return parent, child
            if child["kind"] == "container":
                found = look(child["children"], child)
                if found:
                    return found
        return None

    for page in canvas["pages"]:
        found = look(page["children"], None)
        if found:
            return page, found[0], found[1]
    raise CanvasError(f"There is no {node_id} on this canvas.")


def page_of(canvas: Mapping[str, Any], page_id: str | None) -> dict[str, Any]:
    if page_id is None:
        return canvas["pages"][0]  # type: ignore[no-any-return]
    for page in canvas["pages"]:
        if page["id"] == page_id:
            return page  # type: ignore[no-any-return]
    raise CanvasError(f"There is no page {page_id} on this canvas.")


def _next_id(canvas: Mapping[str, Any], letter: str) -> str:
    used = [int(n["id"][1:]) for _, n in walk(canvas) if n["id"][0] == letter]
    if letter == "p":
        used = [int(p["id"][1:]) for p in canvas["pages"] if _ID.match(p["id"])]
    return f"{letter}{max(used, default=0) + 1}"


def _bounds(parent: Mapping[str, Any] | None, canvas: Mapping[str, Any]) -> tuple[int, int | None]:
    """Width and height (None: as tall as it needs) of a parent's box."""
    if parent is None:
        return page_width(canvas), None
    return parent["w"], parent["h"]


def _overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return bool(
        a["x"] < b["x"] + b["w"]
        and b["x"] < a["x"] + a["w"]
        and a["y"] < b["y"] + b["h"]
        and b["y"] < a["y"] + a["h"]
    )


def _right(children: list[dict[str, Any]]) -> int:
    return max((c["x"] + c["w"] for c in children), default=0)


def _bottom(children: list[dict[str, Any]]) -> int:
    return max((c["y"] + c["h"] for c in children), default=0)


def minimum(
    node: Mapping[str, Any], facts: Facts | None, canvas: Mapping[str, Any] | None = None
) -> tuple[int, int]:
    """The smallest a node may be: a widget's min_size (grid cells, as pixels), a container what it holds."""
    if node["kind"] == "widget":
        known = (facts or {}).get(node["widget"])
        if known is None or canvas is None:
            return MIN_PX, MIN_PX
        return cells(canvas, *known.min_size)
    return max(MIN_PX, _right(node["children"])), max(MIN_PX, _bottom(node["children"]))


# ===== the rules =====


def problems(canvas: Mapping[str, Any], facts: Facts | None = None, sizes: bool = True) -> list[str]:
    """Every broken rule (none: the canvas is good)."""
    found: list[str] = []
    ids: set[str] = set()
    pages = {p["id"] for p in canvas["pages"]}
    if len(pages) != len(canvas["pages"]):
        found.append("Two pages share an id.")
    count = 0

    def check(children: list[dict[str, Any]], parent: dict[str, Any] | None) -> None:
        nonlocal count
        width, height = _bounds(parent, canvas)
        for i, child in enumerate(children):
            count += 1
            if child["id"] in ids:
                found.append(f"{child['id']} is there twice.")
            ids.add(child["id"])
            if parent is None and child["kind"] != "container":
                found.append(f"{child['id']} is a widget on the page itself: it goes in a container.")
            if child["x"] + child["w"] > width:
                where = "page" if parent is None else "container"
                found.append(f"{child['id']} leaves its {where} on the right.")
            if height is not None and child["y"] + child["h"] > height:
                found.append(f"{child['id']} leaves its container at the bottom.")
            for other in children[i + 1 :]:
                if _overlap(child, other):
                    found.append(f"{child['id']} and {other['id']} overlap.")
            if sizes:
                least = minimum(child, facts, canvas)
                if child["w"] < least[0] or child["h"] < least[1]:
                    found.append(f"{child['id']} is smaller than {least[0]} by {least[1]} px.")
            if child["kind"] == "container":
                check(child["children"], child)

    for page in canvas["pages"]:
        check(page["children"], None)
    if count > MAX_NODES:
        found.append(f"A canvas holds {MAX_NODES} things at most.")
    return found


def _free(
    children: list[dict[str, Any]], width: int, w: int, h: int, rows: int | None, gap: int
) -> tuple[int, int] | None:
    """The first place (top to bottom, left to right) a w by h box fits among the children: at the box's
    corner, or a gap right of or below another."""
    w = min(w, width)
    xs = sorted({0, *(min(width - w, o["x"] + o["w"] + gap) for o in children)})
    ys = sorted({0, *(o["y"] + o["h"] + gap for o in children)})
    for y in ys:
        if rows is not None and y + h > rows:
            break
        for x in xs:
            if x < 0 or x + w > width:
                continue
            box = {"x": x, "y": y, "w": w, "h": h}
            if not any(_overlap(box, o) for o in children):
                return x, y
    return None


def _settle(children: list[dict[str, Any]], gap: int) -> None:
    """Anything that overlaps an earlier child (top to bottom) moved down below it."""
    placed: list[dict[str, Any]] = []
    for child in sorted(children, key=lambda c: (c["y"], c["x"])):
        hit = next((p for p in placed if _overlap(child, p)), None)
        while hit is not None:
            child["y"] = hit["y"] + hit["h"] + gap
            hit = next((p for p in placed if _overlap(child, p)), None)
        placed.append(child)


def _scale(
    children: list[dict[str, Any]], ratio: float, width: int, facts: Facts | None, canvas: Mapping[str, Any]
) -> None:
    """Children made `ratio` as wide (a narrower or wider page), kept inside, then settled."""
    gap = canvas["sizing"]["gap"]
    for child in children:
        new_w = max(MIN_PX, round(child["w"] * ratio))
        if child["kind"] == "container":
            _scale(child["children"], ratio, new_w, facts, canvas)
        least = minimum(child, facts, canvas)[0]
        child["w"] = min(width, max(least, new_w))
        child["x"] = max(0, min(width - child["w"], round(child["x"] * ratio)))
        if child["kind"] == "container":
            child["h"] = max(child["h"], _bottom(child["children"]))
    _settle(children, gap)


def _realign(children: list[dict[str, Any]], width: int, old: int, new: int, gap: int) -> None:
    """Each left and right edge that sat on one of the old columns' lines moved to the new columns' nearest
    line; then settled."""
    before = lines(width, old, gap)
    after = lines(width, new, gap)

    def on(value: float) -> float | None:
        if any(abs(value - line) <= 1 for line in before):
            return min(after, key=lambda line: abs(line - value))
        return None

    for child in children:
        left, right = on(child["x"]), on(child["x"] + child["w"])
        x = round(left) if left is not None else child["x"]
        end = round(right) if right is not None else child["x"] + child["w"]
        if end - x >= max(MIN_PX, _right(child["children"]) if child["kind"] == "container" else 0):
            child["x"], child["w"] = max(0, x), min(width - max(0, x), end - x)
    _settle(children, gap)


def _fit_up(canvas: dict[str, Any], container: dict[str, Any] | None) -> None:
    """After a container's children changed: it grows to hold them, and its siblings settle, up to the
    page."""
    gap = canvas["sizing"]["gap"]
    while container is not None:
        need_h, need_w = _bottom(container["children"]), _right(container["children"])
        if container["h"] >= need_h and container["w"] >= need_w:
            return
        page, parent, _ = find(canvas, container["id"])
        width, _ = _bounds(parent, canvas)
        container["h"] = max(container["h"], need_h)
        container["w"] = min(width, max(container["w"], need_w))
        container["x"] = min(container["x"], width - container["w"])
        _settle(parent["children"] if parent else page["children"], gap)
        container = parent


# ===== commands =====


def _place(node: dict[str, Any], body: Mapping[str, Any]) -> None:
    for key in PLACE:
        if key in body and body[key] is not None:
            node[key] = _int(body[key], 0 if key in ("x", "y") else 1, MAX_PX, key)


def _fits_here(
    canvas: dict[str, Any],
    node: dict[str, Any],
    siblings: list[dict[str, Any]],
    parent: dict[str, Any] | None,
    facts: Facts | None,
) -> None:
    width, height = _bounds(parent, canvas)
    name = node["id"]
    least = minimum(node, facts, canvas)
    if node["w"] < least[0] or node["h"] < least[1]:
        what = "its widget" if node["kind"] == "widget" else "what it holds"
        raise CanvasError(f"{name} cannot be smaller than {least[0]} by {least[1]} px: {what} needs that.")
    if node["x"] + node["w"] > width:
        where = "the page" if parent is None else "its container"
        raise CanvasError(f"That would take {name} past the right of {where} ({width} px wide).")
    if height is not None and node["y"] + node["h"] > height:
        raise CanvasError(
            f"That would take {name} out of its container at the bottom: make the container taller."
        )
    for other in siblings:
        if other["id"] != name and _overlap(node, other):
            raise CanvasError(f"That place is taken by {other['id']}.")


def _container_of(
    canvas: dict[str, Any], page: dict[str, Any], parent_id: str | None
) -> dict[str, Any] | None:
    if not parent_id:
        return None
    found_page, _, parent = find(canvas, parent_id)
    if found_page is not page:
        raise CanvasError(f"{parent_id} is on another page.")
    if parent["kind"] != "container":
        raise CanvasError(f"{parent_id} is a widget: only a container holds things.")
    return parent


def _depth(canvas: dict[str, Any], node_id: str | None) -> int:
    depth = 0
    while node_id:
        _, parent, _ = find(canvas, node_id)
        depth += 1
        node_id = parent["id"] if parent else None
    return depth


def _height(node: Mapping[str, Any]) -> int:
    if node["kind"] != "container" or not node["children"]:
        return 1
    return 1 + max(_height(c) for c in node["children"])


def add_container(
    canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts | None = None
) -> tuple[dict[str, Any], str]:
    canvas = copy.deepcopy(canvas)
    page = page_of(canvas, body.get("page"))
    parent = _container_of(canvas, page, body.get("parent"))
    if parent is not None and _depth(canvas, parent["id"]) >= MAX_DEPTH:
        raise CanvasError(f"Containers go {MAX_DEPTH} deep at most.")
    siblings = parent["children"] if parent else page["children"]
    width, height = _bounds(parent, canvas)
    props = {**CONTAINER_DEFAULT, **(body.get("props") or {})}
    check_container_props(props)
    w, h = cells(canvas, 4, 3)
    node: dict[str, Any] = {
        "id": _next_id(canvas, "c"),
        "kind": "container",
        "x": 0,
        "y": 0,
        "w": min(width, w),
        "h": h,
        "props": props,
        "children": [],
    }
    if height is not None:
        node["h"] = min(node["h"], height)
    _place(node, body)
    if body.get("x") is None or body.get("y") is None:
        spot = _free(siblings, width, node["w"], node["h"], height, canvas["sizing"]["gap"])
        if spot is None:
            raise CanvasError("There is no room for a container there: make it larger first.")
        node["x"], node["y"] = spot
    _fits_here(canvas, node, siblings, parent, facts)
    siblings.append(node)
    return canvas, node["id"]


def insert_widget(
    canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts
) -> tuple[dict[str, Any], str]:
    """A widget instance put in a container (`parent`), at a place or the first free one (the container grown
    when it is too small); with no container, one is made around it on the page."""
    name = body.get("widget")
    if not isinstance(name, str) or name not in facts:
        raise CanvasError(f"There is no widget called {str(name)[:60]}.")
    known = facts[name]
    canvas = copy.deepcopy(canvas)
    gap = canvas["sizing"]["gap"]
    page = page_of(canvas, body.get("page"))
    parent = _container_of(canvas, page, body.get("parent"))
    w, h = cells(canvas, *known.size)
    w, h = int(body.get("w") or w), int(body.get("h") or h)
    if parent is None:
        pad = CONTAINER_DEFAULT["padding"]
        around = {
            "page": page["id"],
            "x": body.get("x"),
            "y": body.get("y"),
            "w": min(page_width(canvas), w + 2 * pad),
            "h": h + 2 * pad,
        }
        canvas, made = add_container(canvas, around, facts)
        page = page_of(canvas, page["id"])
        _, _, parent = find(canvas, made)
        body = {k: v for k, v in body.items() if k not in ("x", "y")} | {"x": pad, "y": pad}
    if parent is None:
        raise CanvasError("There is no container for the widget.")
    node: dict[str, Any] = {
        "id": _next_id(canvas, "w"),
        "kind": "widget",
        "widget": name,
        "x": 0,
        "y": 0,
        "w": max(MIN_PX, min(w, parent["w"])),
        "h": max(MIN_PX, h),
        "values": {},
    }
    _place(node, {k: body.get(k) for k in ("x", "y") if body.get(k) is not None})
    if body.get("x") is None or body.get("y") is None:
        spot = _free(parent["children"], parent["w"], node["w"], node["h"], None, gap)
        if spot is None:
            raise CanvasError("There is no room for it there.")
        node["x"], node["y"] = spot
    node["w"] = min(node["w"], max(MIN_PX, parent["w"] - node["x"]))
    values = body.get("values") or {}
    if values:
        node["values"] = {k: v for k, v in dict(values).items() if k in known.properties}
    for other in parent["children"]:
        if _overlap(node, other):
            raise CanvasError(f"That place is taken by {other['id']}.")
    parent["children"].append(node)
    _fit_up(canvas, parent)  # a container too small for it grows to hold it
    return canvas, node["id"]


def move(canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts | None = None) -> dict[str, Any]:
    """A node to another place, its size changed, or into another container (`parent`; "" the page)."""
    canvas = copy.deepcopy(canvas)
    page, parent, node = find(canvas, str(body.get("id")))
    if "parent" in body and (body.get("parent") or None) != (parent["id"] if parent else None):
        target = _container_of(canvas, page, body.get("parent") or None)
        if target is not None:
            at: dict[str, Any] | None = target
            while at is not None:
                if at["id"] == node["id"]:
                    raise CanvasError(f"{node['id']} cannot go inside itself.")
                _, up, _ = find(canvas, at["id"])
                at = up
            if node["kind"] == "container" and _depth(canvas, target["id"]) + _height(node) > MAX_DEPTH:
                raise CanvasError(f"Containers go {MAX_DEPTH} deep at most.")
        if target is None and node["kind"] == "widget":
            raise CanvasError("A widget goes in a container.")
        (parent["children"] if parent else page["children"]).remove(node)
        parent = target
        siblings = parent["children"] if parent else page["children"]
        width, _rows = _bounds(parent, canvas)
        node["w"] = min(node["w"], width)
        if body.get("x") is None or body.get("y") is None:
            spot = _free(siblings, width, node["w"], node["h"], None, canvas["sizing"]["gap"])
            if spot is None:
                raise CanvasError("There is no room for it there.")
            node["x"], node["y"] = spot
        _place(node, body)
        if parent is not None and node["y"] + node["h"] > parent["h"]:
            for other in siblings:  # dropped into a container that is full: it grows to hold it
                if _overlap(node, other):
                    raise CanvasError(f"That place is taken by {other['id']}.")
            siblings.append(node)
            _fit_up(canvas, parent)
            return canvas
        _fits_here(canvas, node, siblings, parent, facts)
        siblings.append(node)
        return canvas
    siblings = parent["children"] if parent else page["children"]
    _place(node, body)
    _fits_here(canvas, node, siblings, parent, facts)
    return canvas


def set_container(
    canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts | None = None
) -> dict[str, Any]:
    canvas = copy.deepcopy(canvas)
    _, _, node = find(canvas, str(body.get("id")))
    if node["kind"] != "container":
        raise CanvasError(f"{node['id']} is a widget: its values are set with set_values.")
    sent = dict(body.get("props") or {})
    props = {**node["props"], **sent}
    if props.get("scrollable") and not node["props"].get("scrollable") and "height" not in sent:
        props["height"] = "fixed"  # scrollable needs a fixed height
    if props.get("height") == "fit" and node["props"].get("height") == "fixed" and "scrollable" not in sent:
        props["scrollable"] = False
    check_container_props(props)
    old = node["props"]["columns"]
    node["props"] = props
    if props["columns"] != old:
        _realign(node["children"], node["w"], old, props["columns"], canvas["sizing"]["gap"])
        _fit_up(canvas, node)
    return canvas


def set_values(canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts | None = None) -> dict[str, Any]:
    """An instance's values: each given one kept (None takes an override away: back to the default)."""
    canvas = copy.deepcopy(canvas)
    _, _, node = find(canvas, str(body.get("id")))
    if node["kind"] != "widget":
        raise CanvasError(f"{node['id']} is a container: its properties are set with set_container.")
    known = (facts or {}).get(node["widget"])
    for key, value in dict(body.get("values") or {}).items():
        if known is not None and key not in known.properties:
            raise CanvasError(f"{node['widget']} has no property {key}.")
        if value is None:
            node["values"].pop(key, None)
        else:
            node["values"][key] = value
    return canvas


def replace_widget(canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts) -> dict[str, Any]:
    """An instance's widget replaced (a placeholder's Replace): its place kept, the values the new one has."""
    canvas = copy.deepcopy(canvas)
    _, parent, node = find(canvas, str(body.get("id")))
    name = body.get("widget")
    if node["kind"] != "widget":
        raise CanvasError(f"{node['id']} is a container.")
    if not isinstance(name, str) or name not in facts:
        raise CanvasError(f"There is no widget called {str(name)[:60]}.")
    node["widget"] = name
    node["values"] = {k: v for k, v in node["values"].items() if k in facts[name].properties}
    least = minimum(node, facts, canvas)
    node["w"], node["h"] = max(node["w"], least[0]), max(node["h"], least[1])
    if parent is not None:
        node["w"] = min(node["w"], parent["w"])
        node["x"] = min(node["x"], parent["w"] - node["w"])
    _fits_here(canvas, node, parent["children"] if parent else [], parent, facts)
    return canvas


def delete(canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts | None = None) -> dict[str, Any]:
    canvas = copy.deepcopy(canvas)
    page, parent, node = find(canvas, str(body.get("id")))
    (parent["children"] if parent else page["children"]).remove(node)
    return canvas


def set_sizing(canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts | None = None) -> dict[str, Any]:
    canvas = copy.deepcopy(canvas)
    sizing = {**canvas["sizing"], **{k: v for k, v in dict(body).items() if k in SIZING_DEFAULT}}
    check_sizing(sizing)
    old = dict(canvas["sizing"])
    canvas["sizing"] = sizing
    if sizing["width"] != old["width"]:
        ratio = WIDTHS[sizing["width"]] / WIDTHS[old["width"]]
        for page in canvas["pages"]:
            _scale(page["children"], ratio, WIDTHS[sizing["width"]], facts, canvas)
    if sizing["columns"] != old["columns"]:
        for page in canvas["pages"]:
            _realign(page["children"], page_width(canvas), old["columns"], sizing["columns"], sizing["gap"])
    return canvas


def add_page(
    canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts | None = None
) -> tuple[dict[str, Any], str]:
    canvas = copy.deepcopy(canvas)
    if len(canvas["pages"]) >= MAX_PAGES:
        raise CanvasError(f"A canvas has {MAX_PAGES} pages at most.")
    made = _next_id(canvas, "p")
    name = str(body.get("name") or f"Page {len(canvas['pages']) + 1}")[:60]
    canvas["pages"].append({"id": made, "name": name, "children": []})
    return canvas, made


def change_page(
    canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts | None = None
) -> dict[str, Any]:
    canvas = copy.deepcopy(canvas)
    page = page_of(canvas, str(body.get("page")))
    if body.get("name") is not None:
        name = str(body["name"]).strip()[:60]
        if not name:
            raise CanvasError("A page has a name.")
        page["name"] = name
    if body.get("index") is not None:
        index = _int(body["index"], 0, len(canvas["pages"]) - 1, "The page's place")
        canvas["pages"].remove(page)
        canvas["pages"].insert(index, page)
    return canvas


def remove_page(
    canvas: dict[str, Any], body: Mapping[str, Any], facts: Facts | None = None
) -> dict[str, Any]:
    canvas = copy.deepcopy(canvas)
    page = page_of(canvas, str(body.get("page")))
    if len(canvas["pages"]) == 1:
        raise CanvasError("A canvas keeps one page at least.")
    canvas["pages"].remove(page)
    return canvas


def rename_widget(canvas: dict[str, Any], old: str, new: str) -> tuple[dict[str, Any], int]:
    """Every instance of widget `old` made an instance of `new` (a widget renamed in its window)."""
    canvas = copy.deepcopy(canvas)
    count = 0
    for _, node in walk(canvas):
        if node["kind"] == "widget" and node["widget"] == old:
            node["widget"] = new
            count += 1
    return canvas, count


def prune(canvas: dict[str, Any], facts: Facts) -> tuple[dict[str, Any], list[str]]:
    """Each instance's overrides of properties its widget's code no longer has, taken away (said once)."""
    canvas = copy.deepcopy(canvas)
    said: list[str] = []
    for _, node in walk(canvas):
        if node["kind"] != "widget" or node["widget"] not in facts:
            continue
        gone = sorted(k for k in node["values"] if k not in facts[node["widget"]].properties)
        for key in gone:
            del node["values"][key]
        if gone:
            said.append(f"{node['id']} ({node['widget']}): {', '.join(gone)} went with the widget's code.")
    return canvas, said


Command = Callable[..., Any]
COMMANDS: dict[str, Command] = {
    "add_container": add_container,
    "insert_widget": insert_widget,
    "move": move,
    "set_container": set_container,
    "set_values": set_values,
    "replace_widget": replace_widget,
    "delete": delete,
    "sizing": set_sizing,
    "add_page": add_page,
    "change_page": change_page,
    "remove_page": remove_page,
}


def apply(
    canvas: dict[str, Any], kind: str, body: Mapping[str, Any], facts: Facts
) -> tuple[dict[str, Any], str | None]:
    """One command: the new canvas and what it made (an id), the rules checked after (a rule broken by the
    command, not one the canvas broke before, refuses it)."""
    command = COMMANDS.get(kind)
    if command is None:
        raise CanvasError(f"The canvas has no command {kind[:40]}.")
    made = command(canvas, body, facts)
    after, made_id = made if isinstance(made, tuple) else (made, None)
    before = set(problems(canvas, facts))
    found = [p for p in problems(after, facts) if p not in before]
    if found:
        raise CanvasError(found[0])
    return after, made_id
