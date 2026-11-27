"""A canvas as a Streamlit app: ONE page builder for Play, Launch, a widget run alone and Export (so what
runs in the app is what an export runs on a hosted Streamlit app, unchanged).

    app.py              st.set_page_config (wide: the page fills the browser), st.navigation over the pages
    app_pages/<page>.py one Streamlit page per canvas page, reproducing the canvas's pixels: the page an
                        st.container keyed sab-page (CSS: position relative, the page's width and height);
                        each container and each widget an st.container keyed sab-<id>, its CSS placing it
                        absolutely at its x, y, w, h inside its parent's box (a container: its border, a
                        height that scrolls when scrollable, padding, a background; resizable is CSS
                        `resize: both`, the viewer drags its corner); each widget `sab.render(...)` inside
    sab_widgets.py      the library's widgets the pages use, inlined: each one's code as text (its properties'
                        assignments made `pass`: the page gives their values), its variable properties
    sab_canvas.py       the runtime (server/sab_canvas.py's text): render() runs one widget in its place,
                        wrapped: a widget that fails shows its own error panel there while the rest of
                        the page runs; a slow one shows Streamlit's spinner; a table or variable that is
                        missing is said in place;
                        table() (a page value too: "page:<key>"), sample(kind) (made-up data), var(),
                        key(), choices() (a select's from a table's column), start() (a starting value from
                        another widget's key), marked() and problem() (the inputs' one look), emit() (an
                        event's wiring carried out: call an API's action, set a page value, rerun);
                        action(endpoint, inputs) (any API's action through api_adapter, its one envelope;
                        said(answer), data(answer), takes(endpoint)); api_call (the older form)
    api_adapter.py      the API adapter, as it is (carried: the services hand its text in), and
    sab_actions.json    each action the app calls: its definition and learned shape (types only); a library
                        API's own client, API_<name>.py

Pure rules, standard library only; no I/O but the runtime's own text, read once from the package.
"""

from __future__ import annotations

import hashlib
import json
import pkgutil
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from swissarmybench_streamlit.domain import canvas_layouts as layouts
from swissarmybench_streamlit.domain import canvas_layouts as model
from swissarmybench_streamlit.domain import canvas_wiring as wiring
from swissarmybench_streamlit.domain import widget_contract as contract
from swissarmybench_streamlit.domain import widget_properties as props_rules
from swissarmybench_streamlit.domain.widget_contract import Port
from swissarmybench_streamlit.domain.widget_properties import Property

# The runtime every page imports (sab_canvas.py), written beside the pages for Play and in an export: a real
# module of this package (server/sab_canvas.py: linted, typed and formatted there), carried as its text. It
# is read once, from the package itself; nothing else is read here.
RUNTIME: str = (pkgutil.get_data("swissarmybench_streamlit", "server/sab_canvas.py") or b"").decode("utf-8")
RUNTIME = RUNTIME.replace("\r\n", "\n")

# The pages' folder: not "pages/", which Streamlit would also list as pages of its own beside st.navigation's.
PAGES: str = "app_pages"
BORDER: int = 1  # the width of Streamlit's container border, in pixels
# A container's title takes this one line on the played page (its children placed below it as on the canvas);
# a title that wraps on a narrow page pushes them down by its extra lines, never over the first widget.
TITLE_PX: int = 28
REQUIREMENTS: tuple[str, ...] = ("streamlit>=1.43", "pandas", "pyarrow")


@dataclass(frozen=True)
class Built:
    """A widget as the builder uses it: its code, its properties and its contract's Ins, Outs and Events."""

    code: str
    properties: tuple[Property, ...]
    ports: tuple[Port, ...] = ()


def made(code: str, properties: Any = None) -> Built:
    """A widget's code as the builder uses it (its properties and contract read; code that does not read: its
    error raised in its place on the page)."""
    try:
        found = tuple(props_rules.detect(code)) if properties is None else tuple(properties)
        return Built(code, found, tuple(contract.detect(code)))
    except props_rules.PropertyError as error:
        return Built(f"raise SyntaxError({str(error)!r})", ())


def contracts(widgets: Mapping[str, Built]) -> dict[str, list[Port]]:
    return {name: list(built.ports) for name, built in widgets.items()}


def table_stem(name: str) -> str:
    """A table's file name in the run's data/ folder: an open table's own name, or for another (a
    connection's `[Conn].table`) its words made safe with a short digest (the runtime's own _stem)."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,80}", name):
        return name
    base = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")[:60] or "table"
    return f"{base}_{hashlib.sha256(name.encode('utf-8')).hexdigest()[:8]}"


def slug(name: str) -> str:
    made = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return (made or "page")[:40]


def page_files(canvas: Mapping[str, Any]) -> dict[str, str]:
    """Each page's file name (pages/<slug>.py, the same slug told apart by a number)."""
    out: dict[str, str] = {}
    used: set[str] = set()
    for page in canvas["pages"]:
        base = slug(page["name"])
        name, n = base, 2
        while name in used:
            name, n = f"{base}_{n}", n + 1
        used.add(name)
        out[page["id"]] = name
    return out


class _Writer:
    """The page as placed boxes in both layouts: each container and each widget an st.container with a key,
    its CSS placing it inside its parent: left and width as fractions of the parent's width (so the page fits
    any width), top and height in pixels; desktop's places by default, phone's below the breakpoint (a media
    query: the browser switches layouts as it is resized, with no rerun). An item shown in one layout only is
    hidden in the other."""

    def __init__(
        self, canvas: Mapping[str, Any], widgets: Mapping[str, Built], context: props_rules.Context | None
    ) -> None:
        self.canvas = canvas
        self.widgets = widgets
        self.context = context
        self.sources = wiring.analyse(canvas, contracts(widgets))["sources"]
        self.needs = wiring.needs(self.sources)
        self.lines: list[str] = []
        self.css: list[str] = []
        self.phone: list[str] = []

    def emit(self, indent: int, text: str) -> None:
        self.lines.append("    " * indent + text)

    @staticmethod
    def _box(place: Mapping[str, Any], inset: int, top: int = 0) -> str:
        """Left and width as the fractions they are: of the parent's padding box widened by its border, less
        the border (an absolute box is placed from inside it), so the box lands where the canvas has it.
        `top`: what its parent's own box starts below (a titled container's padding and title line)."""
        grow = f" + {2 * inset}px" if inset else ""
        less = f" - {inset}px" if inset else ""
        # Under a title, never above the box below it: a widget drawn in the title's line sits under it.
        down = max(0, place["y"] - inset - top) if top else place["y"] - inset
        return (
            f"left: calc((100%{grow}) * {place['x']}{less}); top: {down}px; "
            f"width: calc((100%{grow}) * {place['w']})"
        )

    def place(
        self, key: str, node: Mapping[str, Any], rules: dict[str, list[str]], inset: int, top: int = 0
    ) -> None:
        base = "position: absolute; max-width: none; flex: none; box-sizing: border-box; gap: 0"
        at = node["at"]
        hidden = takes_no_space(node)  # Hidden in the app: it runs, it takes no space
        desktop = rules["desktop"] + (
            [] if layouts.shown(node, "desktop") and not hidden else ["display: none"]
        )
        phone = rules["phone"] + (
            ["display: flex"] if layouts.shown(node, "phone") and not hidden else ["display: none"]
        )
        self.css.append(
            f".st-key-{key} {{ {base}; {self._box(at['desktop'], inset, top)}; {'; '.join(desktop)}; }}"
        )
        self.phone.append(f".st-key-{key} {{ {self._box(at['phone'], inset, top)}; {'; '.join(phone)}; }}")

    def children(self, children: list[dict[str, Any]], indent: int, inset: int = 0, top: int = 0) -> None:
        # Each placed by its key's CSS, so they run in the wiring's order: a reader after what it reads.
        for child in wiring.order(children, self.needs):
            if child["kind"] == "container":
                self.container(child, indent, inset, top)
            else:
                self.widget(child, indent, inset, top)

    def container(self, node: dict[str, Any], indent: int, inset: int = 0, top: int = 0) -> None:
        props = node["props"]
        key = f"sab-{node['id']}"
        args = [f"border={props['border']!r}", f"key={key!r}"]
        self.emit(indent, f"with st.container({', '.join(args)}):  # {node['id']}")
        shared = [f"padding: {props['padding']}px", "margin: 0"]
        if props["background"]:
            shared += [f"background: {props['background']}", "border-radius: 0.5rem"]
        rules: dict[str, list[str]] = {}
        for layout in layouts.LAYOUTS:
            height = node["at"][layout]["h"]
            made = [f"min-height: {height}px" if props["height"] == "fit" else f"height: {height}px"]
            if props["height"] == "fixed":
                made.append("overflow: auto" if props["scrollable"] else "overflow: hidden")
            if props["resizable"]:
                made += ["resize: both", "overflow: auto"]
            rules[layout] = made
        rules["desktop"] = shared + rules["desktop"]
        self.place(key, node, rules, inset, top)
        inner = indent + 1
        border = BORDER if props["border"] else 0
        if props["title"]:
            # The title in the flow, the children in a box below it: a title that wraps pushes them down.
            self.emit(inner, f"sab.heading({json.dumps(props['title'], ensure_ascii=False)})")
            body = f"{key}-body"
            self.emit(inner, f"with st.container(key={body!r}):")
            pad = int(props["padding"])
            for layout in layouts.LAYOUTS:
                h = max(0, node["at"][layout]["h"] - 2 * border - 2 * pad - TITLE_PX)
                rule = (
                    f".st-key-{body} {{ position: relative; width: calc(100% + {2 * pad}px); "
                    f"margin-left: -{pad}px; flex: none; gap: 0; height: {h}px; }}"
                )
                (self.css if layout == "desktop" else self.phone).append(rule)
            if node["children"]:
                self.children(node["children"], inner + 1, border, pad + TITLE_PX)
            else:
                self.emit(inner + 1, "pass")
            return
        if node["children"]:
            self.children(node["children"], inner, border)
        else:
            self.emit(inner, "pass")

    def widget(self, node: dict[str, Any], indent: int, inset: int = 0, top: int = 0) -> None:
        key = f"sab-{node['id']}"
        self.emit(indent, f"with st.container(key={key!r}):  # {node['id']}")
        rules = {
            layout: [f"height: {node['at'][layout]['h']}px", "overflow: auto"] for layout in layouts.LAYOUTS
        }
        self.place(key, node, rules, inset, top)
        built = self.widgets.get(node["widget"])
        if built is None:
            self.emit(indent + 1, f"sab.missing({node['widget']!r}, {node['id']!r})")
            return
        values = props_rules.values(list(built.properties), node["values"], self.context)
        wires = self.sources.get(node["id"]) or {}
        tail = f", {_py(wires)}" if wires else ""
        self.emit(indent + 1, f"sab.render({node['widget']!r}, {_py(values)}, {node['id']!r}{tail})")


def takes_no_space(node: Mapping[str, Any]) -> bool:
    """A widget or a container Hidden in the app (a titled one too: the owner approved, 2026-11-21), or a
    container with no title holding only such: its widgets run, their Outs flow, the page gives it no
    space."""
    if node.get("hidden"):
        return True
    if node["kind"] == "widget":
        return False
    children = node.get("children") or []
    return bool(children) and not node["props"].get("title") and all(takes_no_space(c) for c in children)


def _py(value: Any) -> str:
    return props_rules.literal(value)


def page_code(
    canvas: Mapping[str, Any],
    page_id: str,
    widgets: Mapping[str, Built],
    context: props_rules.Context | None = None,
) -> str:
    """One canvas page as one Streamlit page: a box the page's width, every container and widget placed in
    it at its exact pixels (the canvas's positions, in Play and in an export alike)."""
    page = model.page_of(canvas, page_id)
    writer = _Writer(canvas, widgets, context)
    writer.emit(0, "with st.container(key='sab-page'):")
    writer.children(page["children"], 1)
    if not page["children"]:
        writer.emit(1, "sab.empty()")

    def bottom(layout: str) -> int:
        shown = [
            c["at"][layout] for c in page["children"] if layouts.shown(c, layout) and not takes_no_space(c)
        ]
        return max((p["y"] + p["h"] for p in shown), default=40)

    # A container's title takes its whole line in the flow (Streamlit pulls a markdown block's foot up by
    # its own margin): its box's height is the title's, so the box below it starts under its last line.
    writer.css.insert(0, '[data-testid="stMarkdownContainer"]:has(> .sab-title) { margin-bottom: 0; }')
    writer.css.insert(
        0,
        f".st-key-sab-page {{ position: relative; width: 100%; height: {bottom('desktop')}px; gap: 0; "
        "flex: none; }",  # Streamlit's own flex: 1 1 0% would make the box 0 px high
    )
    writer.phone.insert(0, f".st-key-sab-page {{ height: {bottom('phone')}px; }}")
    writer.css.append(f"@media (max-width: {layouts.BREAKPOINT - 1}px) {{ {' '.join(writer.phone)} }}")
    head = [
        f"# {page['name']}: made from the canvas {canvas['name']} (Swiss Army Bench).",
        "# Edit the canvas, not this file.",
        "import streamlit as st",
        "",
        "import sab_canvas as sab",
        "",
        f"sab.style({json.dumps(' '.join(writer.css))})",
        f"sab.begin({json.dumps(page['name'], ensure_ascii=False)})",
    ]
    return "\n".join([*head, *writer.lines, "sab.finish()"]) + "\n"


def widgets_module(widgets: Mapping[str, Built]) -> str:
    """sab_widgets.py: the widgets the pages use, each one's code as text (its properties given by
    the page)."""
    lines = [
        '"""The canvas\'s widgets, from the library (Swiss Army Bench): each one\'s code, run in its',
        'place by sab_canvas.render with its properties\' values. Edit a widget in its file, not here."""',
        "",
        "CODE: dict[str, str] = {}",
        "VARIABLES: dict[str, list[str]] = {}",
        "# Each widget's contract: its Ins and Outs (type, starting value), its Events (payload).",
        "PORTS: dict[str, dict] = {}",
        "",
    ]
    for name in sorted(widgets):
        built = widgets[name]
        code = props_rules.without_properties(built.code, list(built.properties))
        code = contract.without_declarations(code, list(built.ports))
        variables = [p.name for p in built.properties if p.type == "variable"]
        lines.append(f"CODE[{name!r}] = {_text(code)}")
        lines.append(f"VARIABLES[{name!r}] = {variables!r}")
        if built.ports:
            ports = {
                kind: {p.name: [p.type, p.default] for p in built.ports if p.direction == direction}
                for kind, direction in (("ins", "in"), ("outs", "out"), ("events", "event"))
            }
            lines.append(f"PORTS[{name!r}] = {_py(ports)}")
        lines.append("")
    return "\n".join(lines)


def _text(code: str) -> str:
    """Code as a Python string that reads as the code: a raw triple-quoted string when it can be."""
    if '"""' not in code and not code.endswith(("\\", '"')) and "\r" not in code:
        return 'r"""' + code + '"""' if "\\" in code else '"""' + code + '"""'
    return repr(code)


def app_code(canvas: Mapping[str, Any], first: str | None = None) -> str:
    files = page_files(canvas)
    width = "wide"  # the page fills the browser's width; the canvas's places are fractions of it
    lines = [
        f"# {canvas['name']}: made from its canvas (Swiss Army Bench). Run: streamlit run app.py",
        "import streamlit as st",
        "",
        f"st.set_page_config(page_title={json.dumps(canvas['name'], ensure_ascii=False)}, layout={width!r})",
        "pages = [",
    ]
    for page in canvas["pages"]:
        default = page["id"] == (first or canvas["pages"][0]["id"])
        lines.append(
            f"    st.Page({(PAGES + '/' + files[page['id']] + '.py')!r}, "
            f"title={json.dumps(page['name'], ensure_ascii=False)}, "
            f"url_path={files[page['id']]!r}{', default=True' if default else ''}),"
        )
    lines.append("]")
    position = "sidebar" if len(canvas["pages"]) > 1 else "hidden"
    lines.append(f"st.navigation(pages, position={position!r}).run()")
    return "\n".join(lines) + "\n"


def used(canvas: Mapping[str, Any]) -> set[str]:
    return {n["widget"] for _, n in model.walk(canvas) if n["kind"] == "widget"}


def build(
    canvas: Mapping[str, Any],
    widgets: Mapping[str, Built],
    context: props_rules.Context | None = None,
    first: str | None = None,
    carried: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Every file of the app (Play, Launch and Export write these). `carried`: what the app carries to call
    APIs (api_adapter.py, sab_actions.json, a library API's client: the base's services/actions.py)."""
    names = used(canvas)
    mine = {n: widgets[n] for n in names if n in widgets}
    files = {
        "app.py": app_code(canvas, first),
        "sab_canvas.py": RUNTIME,
        "sab_widgets.py": widgets_module(mine),
    }
    for page_id, stem in page_files(canvas).items():
        files[f"{PAGES}/{stem}.py"] = page_code(canvas, page_id, mine, context)
    calls = wiring.api_calls(canvas)
    if calls:
        files["README.md"] = readme(canvas, calls)
    return files | dict(carried or {})


# ===== the export: the fewest files (Plans/adapter.plan.md "The exported project: the fewest files") =====

FOLDED_AWAY: tuple[str, ...] = ("sab_canvas.py", "sab_widgets.py", "sab_actions.json")
WIDGETS_FILE = "widgets.py"


def _indented(code: str) -> str:
    """Code indented one level as a function's body, a line inside a multi-line string left as it is."""
    import io
    import tokenize

    inside: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(code).readline):
            if token.type == tokenize.STRING and token.end[0] > token.start[0]:
                inside.update(range(token.start[0] + 1, token.end[0] + 1))
    except (tokenize.TokenError, SyntaxError):
        pass
    lines = code.split("\n")
    return "\n".join(
        line if (at in inside or not line.strip()) else "    " + line for at, line in enumerate(lines, 1)
    )


def _page_body(text: str) -> str:
    """A page file's code without its imports (the runtime is app.py itself in an export)."""
    dropped = ("import streamlit as st", "import sab_canvas as sab")
    lines = [line for line in text.rstrip("\n").split("\n") if line.strip() not in dropped]
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines)


def _folded_app(canvas: Mapping[str, Any], files: Mapping[str, str], first: str | None) -> str:
    stems = page_files(canvas)
    runtime = files["sab_canvas.py"].replace("\nimport sab_widgets\n", "\nimport widgets as sab_widgets\n", 1)
    actions = files.get("sab_actions.json")
    parts = [
        f"# {canvas['name']}: made from its canvas (Swiss Army Bench). Run: streamlit run app.py",
        "# Its pages, its layout and its wiring, and the canvas runtime every page calls (sab), in one file;",
        "# its widgets are widgets.py. Edit the canvas, not this file.",
        runtime.rstrip("\n"),
        "",
        "",
        "# ===== the runtime as the pages and the widgets name it (sab, sab_canvas) =====",
        "import sys as _sys  # noqa: E402",
        "import types as _types  # noqa: E402",
        "",
        "sab = _types.SimpleNamespace(**{k: v for k, v in list(globals().items()) if k[:2] != '__'})",
        "_sys.modules['sab_canvas'] = sab  # a widget's `from sab_canvas import table` finds it",
    ]
    if actions is not None:
        parts += [
            "import json as _json  # noqa: E402",
            "",
            "# Each API action the app calls, as it was when the app was built (types only).",
            f"_KEPT['apis'] = _json.loads({_text(actions)!s})",
        ]
    for page in canvas["pages"]:
        stem = stems[page["id"]]
        body = _page_body(files[f"{PAGES}/{stem}.py"])
        parts += ["", "", f"def _page_{stem}() -> None:", f'    """{page["name"]}: a page of the canvas."""',
                  _indented(body)]  # fmt: skip
    parts += ["", ""]
    width = "wide"
    parts.append(
        f"st.set_page_config(page_title={json.dumps(canvas['name'], ensure_ascii=False)}, layout={width!r})"
    )
    parts.append("pages = [")
    for page in canvas["pages"]:
        stem = stems[page["id"]]
        default = page["id"] == (first or canvas["pages"][0]["id"])
        parts.append(
            f"    st.Page(_page_{stem}, title={json.dumps(page['name'], ensure_ascii=False)}, "
            f"url_path={stem!r}{', default=True' if default else ''}),"
        )
    parts.append("]")
    position = "sidebar" if len(canvas["pages"]) > 1 else "hidden"
    parts.append(f"st.navigation(pages, position={position!r}).run()")
    return "\n".join(parts) + "\n"


def folded(canvas: Mapping[str, Any], files: Mapping[str, str], first: str | None = None) -> dict[str, str]:
    """The one builder's files (Play's and Launch's: app.py, app_pages/*.py, sab_canvas.py, sab_widgets.py,
    sab_actions.json) folded into the fewest an export needs: app.py (the pages, the layout, the wiring and
    the runtime) and widgets.py (the widgets the pages use); every other file (data.py, requirements.txt,
    README.md, api_adapter.py, an API's own client) as it is. What runs is the same code: only where it sits
    changes."""
    out = {
        n: t
        for n, t in files.items()
        if n not in FOLDED_AWAY and n != "app.py" and not n.startswith(PAGES + "/")
    }
    out["app.py"] = _folded_app(canvas, files, first)
    out[WIDGETS_FILE] = files["sab_widgets.py"].replace(
        "The canvas's widgets, from the library (Swiss Army Bench)",
        "widgets.py: the canvas's widgets (Swiss Army Bench)",
        1,
    )
    return out


def folded_actions(app_py: str) -> str | None:
    """The API actions' JSON an exported app.py carries (sab_actions.json's text, folded in; None: none)."""
    import ast

    for node in ast.parse(app_py).body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Subscript)
            and isinstance(node.value, ast.Call)
            and node.value.args
            and isinstance(node.value.args[0], ast.Constant)
            and ast.unparse(node.targets[0]) == "_KEPT['apis']"
        ):
            return str(node.value.args[0].value)
    return None


def one_widget(name: str, built: Built, values: Mapping[str, Any], size: tuple[int, int]) -> dict[str, Any]:
    """A widget run alone (the Widgets window's Run, a preview): a canvas of one page, one container that
    has no border, one instance at its size (in both layouts)."""
    from swissarmybench_streamlit.domain import canvas_model as engine

    canvas = model.new_canvas(name)
    canvas["pages"][0]["name"] = name
    w, h = engine.cells({"sizing": {**engine.SIZING_DEFAULT, "width": "desktop"}}, *size)
    fraction = round(min(w, layouts.DESIGN["desktop"]) / layouts.DESIGN["desktop"], layouts.DIGITS)
    container = {**engine.CONTAINER_DEFAULT, "border": False, "padding": 0}
    full = {"x": 0.0, "y": 0, "w": 1.0, "h": h}
    canvas["pages"][0]["children"] = [
        {
            "id": "c1",
            "kind": "container",
            "show": "both",
            "at": {"desktop": {**full, "w": fraction}, "phone": full},
            "props": container,
            "children": [
                {
                    "id": "w1",
                    "kind": "widget",
                    "widget": name,
                    "show": "both",
                    "at": {"desktop": full, "phone": full},
                    "values": dict(values),
                }
            ],
        }
    ]
    return canvas


def kernel_setup() -> str:
    """What the Widgets window's kernel runs first: sab_canvas (the runtime: table, sample, key, var) as a
    module, so the editor completes `from sab_canvas import table` and its signatures, as the page runs it."""
    return (
        "import sys as _sys, types as _types\n"
        "_sab_w = _types.ModuleType('sab_widgets'); _sab_w.CODE = {}; _sab_w.VARIABLES = {}\n"
        "_sys.modules.setdefault('sab_widgets', _sab_w)\n"
        "_sab_c = _types.ModuleType('sab_canvas')\n"
        "try:\n"
        f"    exec({RUNTIME!r}, _sab_c.__dict__)\n"
        "    _sys.modules['sab_canvas'] = _sab_c\n"
        "except Exception:\n"
        "    pass\n"
        "del _sys, _types, _sab_w, _sab_c\n"
    )


def readme(canvas: Mapping[str, Any], calls: list[str]) -> str:
    """README.md of an app whose events call the local sandbox API: the variables its host sets to the
    deployed API's address (the runtime reads them; Play and Launch give the running sandbox's)."""
    lines = [
        f"# {canvas['name']}",
        "",
        "Made from its canvas (Swiss Army Bench). Run: `streamlit run app.py`.",
        "",
        "## The API it calls",
        "",
        "Its wires call these actions through api_adapter.py (beside the pages): the project's local "
        "sandbox API's (API.py), and any other API's as `[its name] METHOD /path` (through its own client "
        "file, API_<name>.py, its sign-in from the variables set where the app runs):",
        "",
        *[f"- `{c}`" for c in calls],
        "",
        "For API.py's, set these on the host to the deployed API (Play and Launch set them to the "
        "running sandbox):",
        "",
        "- `SAB_API_URL`: the API's address, as https://orders-api.azurewebsites.net",
        "- `SAB_API_KEY`: its key, sent as `Authorization: Bearer <key>` (a secret: the host's settings)",
        "- `SAB_API_BASE`: its base path (empty when it has none)",
        "",
    ]
    return "\n".join(lines)


def compiles(files: Mapping[str, str]) -> list[str]:
    """Each file that is not whole Python, and why (a test's check, and the builder's own)."""
    found: list[str] = []
    for name, text in files.items():
        if name.endswith(".py"):
            try:
                compile(text, name, "exec")
            except SyntaxError as error:
                found.append(f"{name} line {error.lineno}: {error.msg}")
    return found
