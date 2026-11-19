"""The designer's Toolbox and the property grid's catalog (the owner, 2026-11-19: "a canvas as flexible as
WinForms and WPF"): every Streamlit element the canvas offers, as data.

  ELEMENTS    each element by its call's name (`selectbox`): its group, its words, the parameters it takes by
              position, the parameters the property grid lists (type, default, one line of what it does, its
              category), which parameter is its default value, its event, and the minimal code a drop makes
  CONTAINERS  the layout containers (WPF's panels): columns, tabs, expander, container, form, sidebar and
              popover, each with its own properties; a container is the canvas's, not a cell's
  cell_code   the code of a new cell for a dropped element, its names free of the ones already made

Everything here exports as plain Streamlit: an element is one `st.<call>(...)`, a container one
`st.columns(...)`, `st.tabs(...)`, `st.expander(...)`, `st.container(...)`, `st.form(...)`, `st.sidebar` or
`st.popover(...)`. Pure rules, no I/O; standard library only.
"""

from __future__ import annotations

import keyword
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

GROUPS: tuple[str, ...] = ("Input", "Data", "Charts", "Text", "Media", "Layout", "Status")


@dataclass(frozen=True)
class Param:
    """A property: its type (text, number, bool, choice, list, any), Streamlit's own default (None: none
    worth saying), the grid's one line, its category and a choice's values."""

    name: str
    type: str
    default: Any = None
    words: str = ""
    category: str = "Behaviour"
    choices: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "default": self.default,
            "words": self.words,
            "category": self.category,
            "choices": list(self.choices),
        }


def _p(
    name: str, kind: str, default: Any = None, words: str = "", category: str = "Behaviour", *choices: str
) -> Param:
    return Param(name, kind, default, words, category, tuple(choices))


LABEL = _p("label", "text", None, "The words beside it on the page.", "Appearance")
HELP = _p("help", "text", None, "A tooltip shown beside the label.", "Appearance")
DISABLED = _p("disabled", "bool", False, "Greyed out: the page's user cannot change it.")
VISIBILITY = _p(
    "label_visibility", "choice", "visible", "Show the label, hide it, or collapse its space.", "Appearance",
    "visible", "hidden", "collapsed",
)  # fmt: skip
KEY = _p("key", "text", None, "Its session state key: st.session_state[key] holds its value.", "State")
WIDTH = _p("width", "any", "stretch", 'Its width: "stretch", "content" or pixels.', "Layout")
PLACEHOLDER = _p("placeholder", "text", None, "Grey words shown while it is empty.", "Appearance")
CONTAINER_WIDTH = _p("use_container_width", "bool", None, "As wide as its block.", "Layout")
INPUT_TAIL: tuple[Param, ...] = (KEY, HELP, DISABLED, VISIBILITY)


@dataclass(frozen=True)
class Element:
    call: str
    group: str
    label: str
    words: str
    positional: tuple[str, ...]  # its parameters in the order a call may give them without a name
    params: tuple[Param, ...]
    code: str  # the minimal cell: {name} the variable, {key} its key, {title} its label
    default: str | None = None  # the parameter that is its default value (value, index, default)
    event: str | None = None  # on_change or on_click
    makes: bool = False  # the cell gives its value a name

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.call,
            "group": self.group,
            "label": self.label,
            "words": self.words,
            "kind": "element",
            "params": [p.to_json() for p in self.params],
            "default": self.default,
            "event": self.event,
        }


def _input(
    call: str,
    label: str,
    words: str,
    positional: tuple[str, ...],
    own: tuple[Param, ...],
    code: str,
    default: str | None = "value",
    event: str | None = "on_change",
) -> Element:
    return Element(
        call, "Input", label, words, positional, (LABEL, *own, *INPUT_TAIL), code, default, event, True
    )


def _show(
    call: str,
    group: str,
    label: str,
    words: str,
    positional: tuple[str, ...],
    own: tuple[Param, ...],
    code: str,
) -> Element:
    return Element(call, group, label, words, positional, own, code)


OPTIONS = _p("options", "list", None, "The choices it offers.", "Data")
MIN = _p("min_value", "number", None, "The smallest value it takes.", "Data")
MAX = _p("max_value", "number", None, "The largest value it takes.", "Data")
STEP = _p("step", "number", None, "How much one step changes it.", "Data")
HEIGHT = _p("height", "any", None, 'Its height: pixels, "content" or "stretch".', "Layout")
BODY = _p("body", "text", None, "The words it shows.", "Appearance")
ICON = _p("icon", "text", None, "An emoji or a Material icon (:material/info:).", "Appearance")
X = _p("x", "text", None, "The column along the bottom.", "Data")
Y = _p("y", "any", None, "The column, or columns, drawn up the side.", "Data")
COLOR = _p("color", "any", None, "A column to colour by, or a colour.", "Appearance")
CHART: tuple[Param, ...] = (
    X, Y, COLOR,
    _p("x_label", "text", None, "The words under the bottom axis.", "Appearance"),
    _p("y_label", "text", None, "The words beside the side axis.", "Appearance"),
    HEIGHT, CONTAINER_WIDTH,
)  # fmt: skip

_ELEMENTS: tuple[Element, ...] = (
    # ----- Input
    _input(
        "text_input",
        "Text",
        "One line of text the page's user types.",
        ("label", "value", "max_chars", "key"),
        (
            _p("value", "text", "", "What it holds before the user types.", "Data"),
            _p("max_chars", "number", None, "The most characters it takes.", "Data"),
            PLACEHOLDER,
            _p(
                "type",
                "choice",
                "default",
                "Plain text, or a password's dots.",
                "Behaviour",
                "default",
                "password",
            ),
        ),
        '{name} = st.text_input("{title}", key="{key}")',
    ),
    _input(
        "text_area",
        "Text area",
        "Several lines of text the page's user types.",
        ("label", "value", "height"),
        (_p("value", "text", "", "What it holds before the user types.", "Data"), HEIGHT, PLACEHOLDER),
        '{name} = st.text_area("{title}", key="{key}")',
    ),
    _input(
        "number_input",
        "Number",
        "A number typed or stepped.",
        ("label", "min_value", "max_value", "value", "step"),
        (
            _p("value", "number", "min", "The number it starts at.", "Data"),
            MIN,
            MAX,
            STEP,
            _p("format", "text", None, "How the number is written (%d, %.2f).", "Appearance"),
        ),
        '{name} = st.number_input("{title}", value=0, key="{key}")',
    ),
    _input(
        "slider",
        "Slider",
        "A number (or a range) chosen by sliding.",
        ("label", "min_value", "max_value", "value", "step"),
        (
            _p("value", "any", None, "Where it starts; two values make a range.", "Data"),
            MIN,
            MAX,
            STEP,
            _p("format", "text", None, "How the number is written (%d, %.2f).", "Appearance"),
        ),
        '{name} = st.slider("{title}", min_value=0, max_value=100, value=50, key="{key}")',
    ),
    _input(
        "selectbox",
        "Select",
        "One choice from a list that drops down.",
        ("label", "options", "index"),
        (
            OPTIONS,
            _p("index", "number", 0, "Which choice it starts on, from 0 (None: none).", "Data"),
            PLACEHOLDER,
            _p("accept_new_options", "bool", False, "The user may type a choice of their own."),
        ),
        '{name} = st.selectbox("{title}", ["First", "Second", "Third"], key="{key}")',
        "index",
    ),
    _input(
        "multiselect",
        "Multiselect",
        "Several choices from a list.",
        ("label", "options", "default"),
        (
            OPTIONS,
            _p("default", "list", None, "The choices picked at the start.", "Data"),
            PLACEHOLDER,
            _p("max_selections", "number", None, "The most choices it takes.", "Data"),
        ),
        '{name} = st.multiselect("{title}", ["First", "Second", "Third"], key="{key}")',
        "default",
    ),
    _input(
        "date_input",
        "Date",
        "A date (or a range of dates) picked from a calendar.",
        ("label", "value", "min_value", "max_value"),
        (
            _p("value", "any", "today", 'The date it starts on ("today", 2026-01-31, or None).', "Data"),
            _p("min_value", "any", None, "The earliest date it takes.", "Data"),
            _p("max_value", "any", None, "The latest date it takes.", "Data"),
            _p("format", "text", "YYYY/MM/DD", "How the date is written.", "Appearance"),
        ),
        '{name} = st.date_input("{title}", key="{key}")',
    ),
    _input(
        "checkbox",
        "Checkbox",
        "A box ticked or not.",
        ("label", "value"),
        (_p("value", "bool", False, "Ticked at the start.", "Data"),),
        '{name} = st.checkbox("{title}", key="{key}")',
    ),
    _input(
        "toggle",
        "Toggle",
        "A switch, on or off.",
        ("label", "value"),
        (_p("value", "bool", False, "On at the start.", "Data"),),
        '{name} = st.toggle("{title}", key="{key}")',
    ),
    _input(
        "radio",
        "Radio",
        "One choice from a few, all shown.",
        ("label", "options", "index"),
        (
            OPTIONS,
            _p("index", "number", 0, "Which choice it starts on, from 0 (None: none).", "Data"),
            _p("horizontal", "bool", False, "The choices side by side.", "Layout"),
            _p("captions", "list", None, "A line of small words under each choice.", "Appearance"),
        ),
        '{name} = st.radio("{title}", ["First", "Second", "Third"], key="{key}")',
        "index",
    ),
    _input(
        "file_uploader",
        "File upload",
        "A file the page's user gives.",
        ("label", "type", "accept_multiple_files"),
        (
            _p("type", "list", None, 'The endings it takes (["csv", "xlsx"]).', "Data"),
            _p("accept_multiple_files", "bool", False, "Several files at once."),
        ),
        '{name} = st.file_uploader("{title}", key="{key}")',
        None,
    ),
    Element(
        "button",
        "Input",
        "Button",
        "A button: True on the run its click starts.",
        ("label", "key", "help", "on_click"),
        (
            LABEL,
            _p(
                "type",
                "choice",
                "secondary",
                "How loud it looks.",
                "Appearance",
                "primary",
                "secondary",
                "tertiary",
            ),
            ICON,
            KEY,
            HELP,
            DISABLED,
            WIDTH,
        ),
        '{name} = st.button("{title}", key="{key}")',
        None,
        "on_click",
        True,
    ),
    Element(
        "form_submit_button",
        "Input",
        "Form submit",
        "A form's button: its inputs are sent together.",
        ("label", "help", "on_click"),
        (
            LABEL,
            _p(
                "type",
                "choice",
                "secondary",
                "How loud it looks.",
                "Appearance",
                "primary",
                "secondary",
                "tertiary",
            ),
            ICON,
            HELP,
            DISABLED,
            WIDTH,
        ),
        '{name} = st.form_submit_button("{title}")',
        None,
        "on_click",
        True,
    ),
    # ----- Data
    _show(
        "dataframe",
        "Data",
        "Dataframe",
        "A table to scroll, sort and search.",
        ("data", "width", "height"),
        (
            _p("data", "any", None, "The table it shows.", "Data"),
            HEIGHT,
            CONTAINER_WIDTH,
            _p("hide_index", "bool", None, "Leave the row numbers out.", "Appearance"),
            _p("column_order", "list", None, "The columns shown, in order.", "Data"),
            KEY,
        ),
        "st.dataframe({table})",
    ),
    Element(
        "data_editor",
        "Data",
        "Data editor",
        "A table the page's user edits.",
        ("data",),
        (
            _p("data", "any", None, "The table it starts from.", "Data"),
            HEIGHT,
            CONTAINER_WIDTH,
            _p("hide_index", "bool", None, "Leave the row numbers out.", "Appearance"),
            _p(
                "num_rows",
                "choice",
                "fixed",
                "Whether rows can be added and deleted.",
                "Behaviour",
                "fixed",
                "dynamic",
            ),
            DISABLED,
            KEY,
        ),
        '{name} = st.data_editor({table}, key="{key}")',
        None,
        "on_change",
        True,
    ),
    _show(
        "metric",
        "Data",
        "Metric",
        "One number in large type, with its change.",
        ("label", "value", "delta"),
        (
            LABEL,
            _p("value", "any", None, "The number shown.", "Data"),
            _p("delta", "any", None, "The change shown under it, green or red.", "Data"),
            _p(
                "delta_color",
                "choice",
                "normal",
                "Which way is good.",
                "Appearance",
                "normal",
                "inverse",
                "off",
            ),
            _p("border", "bool", False, "A border round it.", "Appearance"),
            HELP,
            VISIBILITY,
        ),
        'st.metric("{title}", 0)',
    ),
    _show(
        "table",
        "Data",
        "Table",
        "A plain table, every row shown.",
        ("data",),
        (_p("data", "any", None, "The table it shows.", "Data"),),
        "st.table({table})",
    ),
    _show(
        "json",
        "Data",
        "JSON",
        "A dict or list as a tree to open and close.",
        ("body",),
        (
            _p("body", "any", None, "The value shown.", "Data"),
            _p("expanded", "any", True, "Open at the start (or how many levels).", "Appearance"),
        ),
        'st.json({{"name": "value"}})',
    ),
    # ----- Charts
    _show(
        "line_chart",
        "Charts",
        "Line chart",
        "Lines over a column.",
        ("data",),
        CHART,
        "st.line_chart({table})",
    ),
    _show(
        "bar_chart",
        "Charts",
        "Bar chart",
        "Bars over a column.",
        ("data",),
        (
            *CHART,
            _p("horizontal", "bool", False, "Bars lying down.", "Appearance"),
            _p("stack", "any", None, 'Stacked, side by side (False) or "normalize".', "Appearance"),
        ),
        "st.bar_chart({table})",
    ),
    _show(
        "area_chart",
        "Charts",
        "Area chart",
        "Filled areas over a column.",
        ("data",),
        CHART,
        "st.area_chart({table})",
    ),
    _show(
        "scatter_chart",
        "Charts",
        "Scatter chart",
        "A dot for each row.",
        ("data",),
        (*CHART, _p("size", "any", None, "A column to size the dots by, or a size.", "Appearance")),
        "st.scatter_chart({table})",
    ),
    _show(
        "map",
        "Charts",
        "Map",
        "Points on a map.",
        ("data",),
        (
            _p("latitude", "text", None, "The column of latitudes.", "Data"),
            _p("longitude", "text", None, "The column of longitudes.", "Data"),
            _p("size", "any", None, "A column to size the points by, or a size.", "Appearance"),
            COLOR,
            _p("zoom", "number", None, "How close it starts.", "Appearance"),
            HEIGHT,
        ),
        "st.map({table})",
    ),
    _show(
        "plotly_chart",
        "Charts",
        "Plotly",
        "A Plotly figure.",
        ("figure_or_data",),
        (
            CONTAINER_WIDTH,
            _p(
                "theme",
                "choice",
                "streamlit",
                "Streamlit's look, or Plotly's own.",
                "Appearance",
                "streamlit",
                "None",
            ),
            KEY,
        ),
        'import plotly.express as px\n\n{name} = px.bar(x=["First", "Second", "Third"], y=[3, 5, 4])\n'
        "st.plotly_chart({name})",
    ),
    _show(
        "altair_chart",
        "Charts",
        "Altair",
        "An Altair chart.",
        ("altair_chart",),
        (
            CONTAINER_WIDTH,
            _p(
                "theme",
                "choice",
                "streamlit",
                "Streamlit's look, or Altair's own.",
                "Appearance",
                "streamlit",
                "None",
            ),
            KEY,
        ),
        "import altair as alt\nimport pandas as pd\n\n"
        '{name} = alt.Chart(pd.DataFrame({{"x": ["First", "Second", "Third"], "y": [3, 5, 4]}}))'
        '.mark_bar().encode(x="x", y="y")\nst.altair_chart({name})',
    ),
    # ----- Text
    _show(
        "title",
        "Text",
        "Title",
        "The page's largest heading.",
        ("body",),
        (BODY, _p("anchor", "any", None, "Its link's name (False: no link).", "Behaviour"), HELP),
        'st.title("{title}")',
    ),
    _show(
        "header",
        "Text",
        "Header",
        "A heading.",
        ("body",),
        (BODY, _p("divider", "any", False, "A line under it (True, or a colour).", "Appearance"), HELP),
        'st.header("{title}")',
    ),
    _show(
        "markdown",
        "Text",
        "Markdown",
        "Words written as Markdown.",
        ("body",),
        (BODY, HELP),
        'st.markdown("{title}")',
    ),
    _show(
        "caption", "Text", "Caption", "Small grey words.", ("body",), (BODY, HELP), 'st.caption("{title}")'
    ),
    _show(
        "code",
        "Text",
        "Code",
        "Code, coloured and copyable.",
        ("body", "language"),
        (
            BODY,
            _p("language", "text", "python", "The language it is coloured as.", "Appearance"),
            _p("line_numbers", "bool", False, "Number the lines.", "Appearance"),
            _p("wrap_lines", "bool", False, "Wrap long lines.", "Appearance"),
        ),
        'st.code("print(\\"hello\\")", language="python")',
    ),
    _show("divider", "Text", "Divider", "A line across the block.", (), (), "st.divider()"),
    # ----- Media
    _show(
        "image",
        "Media",
        "Image",
        "A picture: a file, an address or an array.",
        ("image", "caption"),
        (
            _p("image", "any", None, "The picture: a path, an address or an array.", "Data"),
            _p("caption", "text", None, "Small words under it.", "Appearance"),
            CONTAINER_WIDTH,
        ),
        'st.image("https://placehold.co/600x240", caption="{title}")',
    ),
    # ----- Status
    _show("success", "Status", "Success", "A green note.", ("body",), (BODY, ICON), 'st.success("{title}")'),
    _show("info", "Status", "Info", "A blue note.", ("body",), (BODY, ICON), 'st.info("{title}")'),
    _show("warning", "Status", "Warning", "An amber note.", ("body",), (BODY, ICON), 'st.warning("{title}")'),
    _show("error", "Status", "Error", "A red note.", ("body",), (BODY, ICON), 'st.error("{title}")'),
    _show(
        "spinner",
        "Status",
        "Spinner",
        "A turning mark while the code under it runs.",
        ("text",),
        (
            _p("text", "text", "In progress...", "The words beside it.", "Appearance"),
            _p("show_time", "bool", False, "Show how long it has run.", "Appearance"),
        ),
        'import time\n\nwith st.spinner("{title}"):\n    time.sleep(1)',
    ),
    _show(
        "progress",
        "Status",
        "Progress",
        "A bar filled part of the way.",
        ("value", "text"),
        (
            _p("value", "number", None, "How full: 0 to 100 (or 0.0 to 1.0).", "Data"),
            _p("text", "text", None, "The words over it.", "Appearance"),
        ),
        'st.progress(40, text="{title}")',
    ),
)

ELEMENTS: dict[str, Element] = {e.call: e for e in _ELEMENTS}
# Widgets the Toolbox does not list, read by the property grid all the same (their default and event).
_MORE: tuple[tuple[str, str | None, str | None, tuple[str, ...]], ...] = (
    ("select_slider", "value", "on_change", ("label", "options", "value")),
    ("time_input", "value", "on_change", ("label", "value")),
    ("color_picker", "value", "on_change", ("label", "value")),
    ("pills", "default", "on_change", ("label", "options")),
    ("segmented_control", "default", "on_change", ("label", "options")),
    ("feedback", None, "on_change", ("options",)),
    ("chat_input", None, "on_submit", ("placeholder",)),
    ("download_button", None, "on_click", ("label", "data", "file_name", "mime")),
    ("camera_input", None, "on_change", ("label",)),
    ("audio_input", None, "on_change", ("label",)),
    ("link_button", None, None, ("label", "url")),
    ("subheader", None, None, ("body",)),
    ("text", None, None, ("body",)),
    ("write", None, None, ()),
    ("html", None, None, ("body",)),
    ("latex", None, None, ("body",)),
    ("exception", None, None, ("exception",)),
    ("toast", None, None, ("body",)),
    ("pyplot", None, None, ("fig",)),
    ("vega_lite_chart", None, None, ("data", "spec")),
    ("pydeck_chart", None, None, ("pydeck_obj",)),
    ("graphviz_chart", None, None, ("figure_or_dot",)),
    ("video", None, None, ("data",)),
    ("audio", None, None, ("data",)),
)
for _call, _default, _event, _positional in _MORE:
    _own = tuple(p for p in (LABEL if "label" in _positional else None, KEY if _event else None) if p)
    ELEMENTS[_call] = Element(_call, "", _call, "", _positional, _own, "", _default, _event, bool(_event))


# ===== containers (the canvas's own: WPF's panels) =====


@dataclass(frozen=True)
class ContainerKind:
    kind: str
    label: str
    words: str
    params: tuple[Param, ...]
    slots: str = "one"  # one, widths (a slot a column), labels (a slot a tab)

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.kind,
            "group": "Layout",
            "label": self.label,
            "words": self.words,
            "kind": "container",
            "params": [p.to_json() for p in self.params],
        }


BORDER = _p("border", "bool", False, "A border round it.", "Appearance")
CONTAINERS: dict[str, ContainerKind] = {
    c.kind: c
    for c in (
        ContainerKind(
            "columns",
            "Columns",
            "Columns side by side, their widths as ratios (WPF's Grid).",
            (
                _p(
                    "widths",
                    "list",
                    [1, 1],
                    "Each column's width as a ratio: [2, 1] is two thirds and a third.",
                    "Layout",
                ),
                _p(
                    "gap",
                    "choice",
                    "small",
                    "The space between the columns.",
                    "Layout",
                    "small",
                    "medium",
                    "large",
                ),
                _p(
                    "vertical_alignment",
                    "choice",
                    "top",
                    "Where each column's blocks sit.",
                    "Layout",
                    "top",
                    "center",
                    "bottom",
                ),
                BORDER,
            ),
            "widths",
        ),
        ContainerKind(
            "tabs",
            "Tabs",
            "Tabs: one shows at a time (WPF's TabControl).",
            (_p("labels", "list", ["First", "Second"], "Each tab's name.", "Appearance"),),
            "labels",
        ),
        ContainerKind(
            "expander",
            "Expander",
            "A section the page's user opens and closes.",
            (
                _p("label", "text", "Details", "The words on its bar.", "Appearance"),
                _p("expanded", "bool", False, "Open at the start."),
                ICON,
            ),
        ),
        ContainerKind(
            "container",
            "Container",
            "A box for blocks, with a border or a fixed height.",
            (_p("border", "bool", True, "A border round it.", "Appearance"),),
        ),
        ContainerKind(
            "form",
            "Form",
            "Its inputs are sent together when its button is clicked.",
            (
                _p("submit", "text", "Submit", "The words on its button.", "Appearance"),
                _p(
                    "submitted",
                    "text",
                    "",
                    "A name for the button's value (True on the run its click starts).",
                    "State",
                ),
                _p("clear_on_submit", "bool", False, "Its inputs go back to their defaults after a click."),
                _p("enter_to_submit", "bool", True, "Enter in an input clicks its button."),
                BORDER,
            ),
        ),
        ContainerKind("sidebar", "Sidebar", "The page's side panel (one a page).", ()),
        ContainerKind(
            "popover",
            "Popover",
            "A button that opens a small panel of blocks.",
            (_p("label", "text", "Open", "The words on its button.", "Appearance"), ICON, HELP, DISABLED),
        ),
    )
}


def catalog() -> dict[str, Any]:
    """The Toolbox as the page and the agent read it: the groups in order, each element and container."""
    items = [e.to_json() for e in _ELEMENTS] + [c.to_json() for c in CONTAINERS.values()]
    return {"groups": list(GROUPS), "items": items}


# ===== a dropped element's cell =====


class ToolboxError(ValueError):
    """An element the Toolbox does not hold, or a drop that cannot be made (the message says why)."""


def free_name(base: str, taken: Iterable[str]) -> str:
    """`slider_1`, the first number no name of `taken` has."""
    used = set(taken)
    n = 1
    while f"{base}_{n}" in used or keyword.iskeyword(f"{base}_{n}"):
        n += 1
    return f"{base}_{n}"


@dataclass(frozen=True)
class NewCell:
    code: str
    name: str  # the cell's own name ("Slider 1")
    variable: str | None  # the name its value has (None: it shows something and makes nothing)

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "name": self.name, "variable": self.variable}


def cell_code(
    call: str, taken: Iterable[str] = (), tables: Iterable[str] = (), title: str | None = None
) -> NewCell:
    """A dropped element's cell: a title line, the element's minimal code. Its variable and key are one
    name no cell has made (`taken`); a data element shows the first open table (`tables`), else a small
    made-up one."""
    element = ELEMENTS.get(call)
    if element is None or not element.code:
        raise ToolboxError(f"The Toolbox has no element called {call!r}.")
    base = re.sub(r"_(input|chart)$", "", call)
    name = free_name(base, taken)
    number = name.rsplit("_", 1)[1]
    words = (title or f"{element.label} {number}").replace('"', "'").replace("\n", " ")
    table = next(iter(tables), None)
    lines = [f"# {words}"]
    if "{table}" in element.code and table is None:
        table = f"{name}_data" if element.makes else "sample"
        lines += [
            "import pandas as pd",
            "",
            f'{table} = pd.DataFrame({{"item": ["First", "Second", "Third"], "amount": [3, 5, 4]}})',
        ]
    lines.append(element.code.format(name=name, key=name, title=words, table=table))
    makes = element.makes or "{name}" in element.code
    return NewCell("\n".join(lines) + "\n", words, name if makes else None)
