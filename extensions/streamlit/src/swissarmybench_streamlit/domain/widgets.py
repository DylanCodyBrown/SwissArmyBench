"""A widget (the owner, 2026-11-21: "Creating a widget is what will replace the concept of app cells and app
notebooks"): one file in the library's widgets/ folder, `<name>.widget.py`, shared by every project and the
team like a blade. Prebuilt ones ship with the extension (read-only: Copy as your own).

THE FILE

    # /// swissarmybench-widget
    # format = 1
    # name = "kpi_card"
    # description = "One number with its change"
    # framework = "streamlit"
    # group = "Data"
    # tags = ["kpi"]
    # size = [3, 2]
    # min_size = [2, 1]
    # ///
    import streamlit as st
    ...

The header is TOML in comments (as a blade's); the code below it is the widget's own Python. The app writes
only the header (Name and Description in the Widgets window) and a property's value (domain/
widget_properties.py): every other byte of the code stays as typed, and a save that changes nothing changes
no byte.

`framework` names the app framework the widget is made for; an extension's MODE names the framework its
canvas uses (`widget_framework`), and the Widgets browser and the canvas show only that framework's widgets.

Pure rules: no I/O, standard library only.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field, replace
from typing import Any

FORMAT: int = 1
HEADER_TYPE: str = "swissarmybench-widget"
SUFFIX: str = ".widget.py"
FOLDER: str = "widgets"  # in the library
DEFAULT_SIZE: tuple[int, int] = (4, 2)
DEFAULT_MIN: tuple[int, int] = (1, 1)
MAX_SIZE: int = 48
MAX_FILE_BYTES: int = 500_000
GROUPS: tuple[str, ...] = ("Buttons", "Inputs", "Data", "Charts", "Text", "Filters", "Forms", "Other")
_OPEN = re.compile(r"^# /// (?P<type>[a-zA-Z0-9-]+)\s*$")
_CLOSE = "# ///"
NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DESCRIPTION_MAX = 300


class WidgetError(ValueError):
    """A widget file that cannot be read, or a change that cannot be made (one sentence; `line` when it has
    one)."""

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.line = line


@dataclass(frozen=True)
class Widget:
    name: str
    code: str  # the code below the header, exactly as in the file
    description: str = ""
    framework: str = "streamlit"
    group: str = "Other"
    tags: tuple[str, ...] = ()
    size: tuple[int, int] = DEFAULT_SIZE
    min_size: tuple[int, int] = DEFAULT_MIN
    prebuilt: bool = False
    extra: dict[str, Any] = field(default_factory=dict)  # header keys this version does not know: kept

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "framework": self.framework,
            "group": self.group,
            "tags": list(self.tags),
            "size": list(self.size),
            "min_size": list(self.min_size),
            "prebuilt": self.prebuilt,
        }


def file_name(name: str) -> str:
    return name + SUFFIX


def check_name(name: Any, taken: set[str] | frozenset[str], own: str | None = None) -> dict[str, Any]:
    """The live check of a widget's name: available, taken, or not a valid name (one sentence each). `own`:
    the widget's present name (its own name is available to it)."""
    if not isinstance(name, str) or not NAME.match(name):
        return {
            "ok": False,
            "state": "invalid",
            "said": "Not a valid name: small letters, digits and _ , starting with a letter (64 at most).",
        }
    if name != own and name in taken:
        return {"ok": False, "state": "taken", "said": f"{name} is taken: another widget has that name."}
    return {"ok": True, "state": "available", "said": f"{name} is available."}


def free_name(wanted: str, taken: set[str] | frozenset[str]) -> str:
    """`wanted` made a valid name that is not taken (a copy: my_button, my_button_2)."""
    base = re.sub(r"[^a-z0-9_]+", "_", wanted.lower()).strip("_") or "widget"
    if not base[0].isalpha():
        base = "w_" + base
    base = base[:56]
    name, n = base, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    return name


# ===== the header =====


def _toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def header_lines(widget: Widget) -> list[str]:
    body = [
        f"format = {FORMAT}",
        f"name = {_toml(widget.name)}",
        f"description = {_toml(widget.description)}",
        f"framework = {_toml(widget.framework)}",
        f"group = {_toml(widget.group)}",
        f"tags = {_toml(list(widget.tags))}",
        f"size = {_toml(list(widget.size))}",
        f"min_size = {_toml(list(widget.min_size))}",
    ]
    body += [f"{key} = {_toml(value)}" for key, value in sorted(widget.extra.items()) if _plain(value)]
    return ["# /// " + HEADER_TYPE, *("# " + line for line in body), _CLOSE]


def _plain(value: Any) -> bool:
    if isinstance(value, (bool, int, str)):
        return True
    return isinstance(value, (list, tuple)) and all(isinstance(v, (bool, int, str)) for v in value)


def write_widget(widget: Widget) -> str:
    """The widget as its file: the header, then the code as it is."""
    return "\n".join(header_lines(widget)) + "\n" + widget.code


def _span(lines: list[str]) -> tuple[int, int] | None:
    for i, line in enumerate(lines[:200]):
        match = _OPEN.match(line)
        if match and match["type"] == HEADER_TYPE:
            end = next((j for j in range(i + 1, len(lines)) if lines[j].rstrip() == _CLOSE), None)
            return None if end is None else (i, end)
        if line.strip() and not line.lstrip().startswith("#"):
            return None
    return None


def is_widget(text: str) -> bool:
    return _span(text.split("\n")) is not None


def _size(value: Any, default: tuple[int, int], what: str) -> tuple[int, int]:
    if value is None:
        return default
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= MAX_SIZE for v in value)
    ):
        raise WidgetError(f"{what} is two whole numbers from 1 to {MAX_SIZE}: [width, height].")
    return (int(value[0]), int(value[1]))


def read_widget(text: str, prebuilt: bool = False) -> Widget:
    """The widget a file holds (nothing run). A file that is not one says why, with its line."""
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise WidgetError(f"A widget file is {MAX_FILE_BYTES // 1000} KB at most.")
    lines = text.split("\n")
    span = _span(lines)
    if span is None:
        raise WidgetError(f"This file has no {HEADER_TYPE} header: it is not a widget.", 1)
    start, end = span
    toml_text = "\n".join(re.sub(r"^#( |$)", "", line) for line in lines[start + 1 : end])
    try:
        data = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as error:
        line = start + 1 + _bad_line(toml_text)
        raise WidgetError(f"The widget's header does not read as TOML ({error}).", line) from None
    if int(data.get("format", FORMAT)) > FORMAT:
        raise WidgetError("This widget was made by a newer version of the app: update to open it.", start + 1)
    name = data.get("name")
    if not isinstance(name, str) or not NAME.match(name):
        raise WidgetError("The widget's name is not a valid name (small letters, digits and _).", start + 1)
    size = _size(data.get("size"), DEFAULT_SIZE, "size")
    least = _size(data.get("min_size"), DEFAULT_MIN, "min_size")
    if least[0] > size[0] or least[1] > size[1]:
        least = (min(least[0], size[0]), min(least[1], size[1]))
    tags = data.get("tags") or []
    known = {"format", "name", "description", "framework", "group", "tags", "size", "min_size"}
    return Widget(
        name=name,
        code="\n".join(lines[end + 1 :]),
        description=str(data.get("description") or "")[:_DESCRIPTION_MAX],
        framework=str(data.get("framework") or "streamlit"),
        group=str(data.get("group") or "Other"),
        tags=tuple(str(t) for t in tags if isinstance(t, (str, int)))[:20],
        size=size,
        min_size=least,
        prebuilt=prebuilt,
        extra={k: v for k, v in data.items() if k not in known},
    )


def _bad_line(toml_text: str) -> int:
    """The header's first line that does not read on its own (1 from the header's first line)."""
    for at, line in enumerate(toml_text.split("\n"), start=1):
        if not line.strip() or line.lstrip().startswith(("#", "[")):
            continue
        try:
            tomllib.loads(line)
        except tomllib.TOMLDecodeError:
            return at
    return 0


def with_header(text: str, **changes: Any) -> str:
    """The file with its header changed (name, description, group, tags, size, min_size): the lines below
    the header, the code, are the same bytes."""
    widget = read_widget(text)
    allowed = {"name", "description", "group", "tags", "size", "min_size", "framework"}
    unknown = set(changes) - allowed
    if unknown:
        raise WidgetError(f"A widget's header has no {', '.join(sorted(unknown))}.")
    if "name" in changes and (not isinstance(changes["name"], str) or not NAME.match(changes["name"])):
        raise WidgetError(check_name(changes["name"], set())["said"])
    if "description" in changes:
        changes["description"] = " ".join(str(changes["description"] or "").split())[:_DESCRIPTION_MAX]
    if "tags" in changes:
        changes["tags"] = tuple(str(t) for t in changes["tags"] or [])
    if "size" in changes:
        changes["size"] = _size(list(changes["size"]), DEFAULT_SIZE, "size")
    if "min_size" in changes:
        changes["min_size"] = _size(list(changes["min_size"]), DEFAULT_MIN, "min_size")
    lines = text.split("\n")
    span = _span(lines)
    if span is None:  # read_widget found it
        raise WidgetError("This file has no header.", 1)
    start, end = span
    head = header_lines(replace(widget, **changes))
    return "\n".join([*lines[:start], *head, *lines[end + 1 :]])


def new_widget(name: str, framework: str, description: str = "") -> Widget:
    """New widget's starting code: a heading and a value, as properties, so the Properties pane shows
    something at once."""
    code = (
        "import streamlit as st\n"
        "\n"
        "# The heading above the value\n"
        'title = "New widget"\n'
        "# The value shown\n"
        "value = 42\n"
        "\n"
        "st.subheader(title)\n"
        "st.metric(title, value)\n"
    )
    return Widget(name=name, code=code, description=description, framework=framework, group="Other")
