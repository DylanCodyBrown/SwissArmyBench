"""A canvas as a Streamlit app: ONE page builder for Play, Launch, a widget run alone and Export (so what
runs in the app is what an export runs on a hosted Streamlit app, unchanged).

    app.py              st.set_page_config (the page's width), st.navigation over the pages
    app_pages/<page>.py one Streamlit page per canvas page, reproducing the canvas's pixels: the page an
                        st.container keyed sab-page (CSS: position relative, the page's width and height);
                        each container and each widget an st.container keyed sab-<id>, its CSS placing it
                        absolutely at its x, y, w, h inside its parent's box (a container: its border, a
                        height that scrolls when scrollable, padding, a background; resizable is CSS
                        `resize: both`, the viewer drags its corner); each widget `sab.render(...)` inside
    sab_widgets.py      the library's widgets the pages use, inlined: each one's code as text (its properties'
                        assignments made `pass`: the page gives their values), its variable properties
    sab_canvas.py       the runtime (RUNTIME below): render() runs one widget in its place, wrapped: a widget
                        that fails shows its own error panel there while the rest of the page runs; a slow
                        one shows Streamlit's spinner; a table or variable that is missing is said in place;
                        table(), sample() (made-up data), var(), key()

Pure rules: no I/O, standard library only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from swissarmybench_streamlit.domain import canvas_model as model
from swissarmybench_streamlit.domain import widget_properties as props_rules
from swissarmybench_streamlit.domain.widget_properties import Property

# The pages' folder: not "pages/", which Streamlit would also list as pages of its own beside st.navigation's.
PAGES: str = "app_pages"
BORDER: int = 1  # the width of Streamlit's container border, in pixels
REQUIREMENTS: tuple[str, ...] = ("streamlit>=1.43", "pandas", "pyarrow")


@dataclass(frozen=True)
class Built:
    """A widget as the builder uses it: its code and its properties."""

    code: str
    properties: tuple[Property, ...]


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
    """The page as absolutely placed boxes: each container and each widget an st.container with a key, its
    CSS placing it at its pixels inside its parent (the page's own keyed container, position: relative)."""

    def __init__(
        self, canvas: Mapping[str, Any], widgets: Mapping[str, Built], context: props_rules.Context | None
    ) -> None:
        self.canvas = canvas
        self.widgets = widgets
        self.context = context
        self.lines: list[str] = []
        self.css: list[str] = []

    def emit(self, indent: int, text: str) -> None:
        self.lines.append("    " * indent + text)

    def place(self, key: str, node: Mapping[str, Any], rules: list[str], inset: int) -> None:
        """Its box at its pixels in its parent's: an absolute box is placed from inside the parent's border
        (`inset`), so the border's width is taken off and the box lands where the canvas has it."""
        box = (
            f"position: absolute; left: {node['x'] - inset}px; top: {node['y'] - inset}px; "
            f"width: {node['w']}px; "
            "max-width: none; flex: none"
        )
        self.css.append(f".st-key-{key} {{ {box}; box-sizing: border-box; gap: 0; {'; '.join(rules)}; }}")

    def children(self, children: list[dict[str, Any]], indent: int, inset: int = 0) -> None:
        for child in sorted(children, key=lambda c: (c["y"], c["x"])):
            if child["kind"] == "container":
                self.container(child, indent, inset)
            else:
                self.widget(child, indent, inset)

    def container(self, node: dict[str, Any], indent: int, inset: int = 0) -> None:
        props = node["props"]
        key = f"sab-{node['id']}"
        height = node["h"]
        args = [f"border={props['border']!r}", f"key={key!r}"]
        if props["scrollable"]:
            args.insert(1, f"height={height}")
        self.emit(indent, f"with st.container({', '.join(args)}):  # {node['id']}")
        rules = [f"padding: {props['padding']}px", "margin: 0"]
        rules.append(f"min-height: {height}px" if props["height"] == "fit" else f"height: {height}px")
        if props["height"] == "fixed" and not props["scrollable"]:
            rules.append("overflow: hidden")
        if props["scrollable"]:
            rules += [f"height: {height}px", "overflow: auto"]
        if props["background"]:
            rules += [f"background: {props['background']}", "border-radius: 0.5rem"]
        if props["resizable"]:
            rules += ["resize: both", "overflow: auto"]
        self.place(key, node, rules, inset)
        inner = indent + 1
        if props["title"]:
            self.emit(inner, f"sab.heading({json.dumps(props['title'], ensure_ascii=False)})")
        if node["children"]:
            self.children(node["children"], inner, BORDER if props["border"] else 0)
        elif not props["title"]:
            self.emit(inner, "pass")

    def widget(self, node: dict[str, Any], indent: int, inset: int = 0) -> None:
        key = f"sab-{node['id']}"
        self.emit(indent, f"with st.container(key={key!r}):  # {node['id']}")
        self.place(key, node, [f"height: {node['h']}px", "overflow: auto"], inset)
        built = self.widgets.get(node["widget"])
        if built is None:
            self.emit(indent + 1, f"sab.missing({node['widget']!r}, {node['id']!r})")
            return
        values = props_rules.values(list(built.properties), node["values"], self.context)
        self.emit(indent + 1, f"sab.render({node['widget']!r}, {_py(values)}, {node['id']!r})")


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
    bottom = max((c["y"] + c["h"] for c in page["children"]), default=40)
    writer.css.insert(
        0,
        f".st-key-sab-page {{ position: relative; width: {model.page_width(canvas)}px; height: {bottom}px; "
        "gap: 0; flex-shrink: 0; }",
    )
    head = [
        f"# {page['name']}: made from the canvas {canvas['name']} (Swiss Army Bench).",
        "# Edit the canvas, not this file.",
        "import streamlit as st",
        "",
        "import sab_canvas as sab",
        "",
        f"sab.style({json.dumps(' '.join(writer.css))})",
    ]
    return "\n".join([*head, *writer.lines]) + "\n"


def widgets_module(widgets: Mapping[str, Built]) -> str:
    """sab_widgets.py: the widgets the pages use, each one's code as text (its properties given by
    the page)."""
    lines = [
        '"""The canvas\'s widgets, from the library (Swiss Army Bench): each one\'s code, run in its',
        'place by sab_canvas.render with its properties\' values. Edit a widget in its file, not here."""',
        "",
        "CODE: dict[str, str] = {}",
        "VARIABLES: dict[str, list[str]] = {}",
        "",
    ]
    for name in sorted(widgets):
        built = widgets[name]
        code = props_rules.without_properties(built.code, list(built.properties))
        variables = [p.name for p in built.properties if p.type == "variable"]
        lines.append(f"CODE[{name!r}] = {_text(code)}")
        lines.append(f"VARIABLES[{name!r}] = {variables!r}")
        lines.append("")
    return "\n".join(lines)


def _text(code: str) -> str:
    """Code as a Python string that reads as the code: a raw triple-quoted string when it can be."""
    if '"""' not in code and not code.endswith(("\\", '"')) and "\r" not in code:
        return 'r"""' + code + '"""' if "\\" in code else '"""' + code + '"""'
    return repr(code)


def app_code(canvas: Mapping[str, Any], first: str | None = None) -> str:
    files = page_files(canvas)
    width = canvas["sizing"]["width"]
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
) -> dict[str, str]:
    """Every file of the app (Play, Launch and Export write these)."""
    names = used(canvas)
    mine = {n: widgets[n] for n in names if n in widgets}
    files = {
        "app.py": app_code(canvas, first),
        "sab_canvas.py": RUNTIME,
        "sab_widgets.py": widgets_module(mine),
    }
    for page_id, stem in page_files(canvas).items():
        files[f"{PAGES}/{stem}.py"] = page_code(canvas, page_id, mine, context)
    return files


def one_widget(name: str, built: Built, values: Mapping[str, Any], size: tuple[int, int]) -> dict[str, Any]:
    """A widget run alone (the Widgets window's Run, a preview): a canvas of one page, one container that
    has no border, one instance at its size."""
    canvas = model.new_canvas(name)
    canvas["pages"][0]["name"] = name
    w, h = model.cells(canvas, *size)
    w = min(w, model.page_width(canvas))
    container = {**model.CONTAINER_DEFAULT, "border": False, "padding": 0}
    instance = {
        "id": "w1",
        "kind": "widget",
        "widget": name,
        "x": 0,
        "y": 0,
        "w": w,
        "h": h,
        "values": dict(values),
    }
    canvas["pages"][0]["children"] = [
        {
            "id": "c1",
            "kind": "container",
            "x": 0,
            "y": 0,
            "w": w,
            "h": h,
            "props": container,
            "children": [instance],
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


# The runtime every page imports (sab_canvas.py): written beside the pages for Play and in an export.
RUNTIME = r'''"""Swiss Army Bench's canvas runtime: each widget run in its own place.

render() runs a widget's code with its properties' values. A widget that fails shows its own error panel in
its place and the rest of the page runs; a table or a variable that is missing is said there; a slow one
shows a spinner while it works. Made-up sample data stands in when no table is picked.
"""

from __future__ import annotations

import contextvars
import html
import importlib
import linecache
import os
import traceback
from pathlib import Path
from typing import Any

import streamlit as st

import sab_widgets

_HERE = Path(__file__).resolve().parent
_INSTANCE: contextvars.ContextVar[str] = contextvars.ContextVar("sab_instance", default="w")
_COMPILED: dict[tuple[str, str], Any] = {}


class Missing(Exception):
    """A table or a variable a widget needs that is not here: said in its place."""


def key(name: str = "") -> str:
    """A widget key of this instance's own (two instances of one widget never share a key)."""
    instance = _INSTANCE.get()
    return f"{instance}-{name}" if name else instance


def sample(rows: int = 24) -> Any:
    """Made-up sales: month, region, product, revenue, units, margin, lat, lon (the same every time)."""
    import pandas as pd

    regions = ["North", "South", "East", "West"]
    products = ["Alpha", "Beta", "Gamma"]
    points = {"North": (52.5, 13.4), "South": (48.1, 11.6), "East": (51.3, 12.4), "West": (50.9, 6.9)}
    made = []
    for i in range(rows):
        region = regions[i % 4]
        lat, lon = points[region]
        revenue = 1000 + (i * 137) % 900 + (i % 4) * 150
        made.append(
            {
                "month": f"2026-{(i // 2) % 12 + 1:02d}-01",
                "region": region,
                "product": products[i % 3],
                "revenue": float(revenue),
                "units": 10 + (i * 7) % 40,
                "margin": round(0.1 + ((i * 13) % 20) / 100, 2),
                "lat": lat + (i % 5) * 0.05,
                "lon": lon + (i % 3) * 0.05,
            }
        )
    frame = pd.DataFrame(made)
    frame["month"] = pd.to_datetime(frame["month"])
    return frame


def table(name: str = "") -> Any:
    """A table by its name: the canvas's own copy (data/<name>.parquet), else data.py's, else none: said.
    No name: the made-up sample."""
    if not name:
        return sample()
    path = _HERE / "data" / f"{name}.parquet"
    if path.is_file():
        import pandas as pd

        return pd.read_parquet(path)
    try:
        import data as _data  # the project's data.py, when it is beside the app
    except Exception:
        _data = None
    found = getattr(_data, name, None) if _data is not None else None
    if found is not None:
        return found
    raise Missing(f"The table {name} is not here: open it in Swiss Army Bench, or pick another table.")


def var(name: str) -> str:
    """A variable of this computer (its value from the environment, set by the app or the host)."""
    value = os.environ.get(name)
    if value is None:
        raise Missing(
            f"{name} is not set on this computer: set it on the Variables page (or the host's settings)."
        )
    return value


def style(css: str) -> None:
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def heading(text: str) -> None:
    st.markdown(
        f"<div style='font-weight:600;margin-bottom:0.25rem'>{html.escape(text)}</div>",
        unsafe_allow_html=True,
    )


def space(pixels: int) -> None:
    st.markdown(f"<div style='height:{int(pixels)}px'></div>", unsafe_allow_html=True)


def empty() -> None:
    st.caption("This page is empty: draw a container on the canvas and insert a widget.")


def missing(name: str, instance: str) -> None:
    st.warning(
        f"The widget {name} is not in the library any more: Replace or Remove {instance} on the canvas."
    )


def _widgets() -> Any:
    """sab_widgets as its file is now: read again when the file changed since it was imported (a run that
    rewrote it can rerun the page before Streamlit's own watcher has looked)."""
    global sab_widgets
    path = Path(sab_widgets.__file__)
    stamp = path.stat().st_mtime_ns if path.is_file() else 0
    if getattr(sab_widgets, "_sab_stamp", None) != stamp:
        sab_widgets = importlib.reload(sab_widgets)
        sab_widgets._sab_stamp = stamp
    return sab_widgets


def _code(name: str) -> Any:
    text = _widgets().CODE[name]
    key = (name, text)
    if key not in _COMPILED:
        where = f"<widget {name}>"
        linecache.cache[where] = (len(text), None, text.splitlines(keepends=True), where)
        _COMPILED[key] = compile(text, where, "exec")
    return _COMPILED[key]


def render(name: str, values: dict[str, Any], instance: str) -> None:
    """One widget in its place, with its properties' values; whatever it does wrong stays in its place."""
    token = _INSTANCE.set(instance)
    try:
        namespace: dict[str, Any] = {"__name__": f"sab_widget_{name}", **values}
        for variable in _widgets().VARIABLES.get(name, []):
            namespace[variable] = var(str(values.get(variable) or ""))
        with st.spinner(f"Loading {name}…"):
            exec(_code(name), namespace)  # noqa: S102 (the user's own widget, from their library)
    except Missing as said:
        st.warning(str(said))
    except Exception as error:  # a widget's own failure: shown in its place, the page goes on
        if type(error).__name__ in ("RerunException", "StopException", "RerunData"):
            raise
        where = f"<widget {name}>"
        lines = [f.lineno for f in traceback.extract_tb(error.__traceback__) if f.filename == where]
        at = f" (line {lines[-1]})" if lines else ""
        st.error(f"{name} ({instance}) failed: {type(error).__name__}: {error}{at}")
        with st.expander("Details"):
            st.code(traceback.format_exc(), language="text")
    finally:
        _INSTANCE.reset(token)
'''
