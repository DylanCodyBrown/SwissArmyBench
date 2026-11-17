"""Snippets: blades that are text to drop into a cell (docs/ideas.md, the starter pack, 2026-11-15).

A snippet is a piece of DAX, HTML, Markdown, Streamlit or plain Python (the Write starters) with
**placeholders** for the names
it needs.
Dropped on a cell of its language (or picked from the cell's menu), a small form asks for each one,
prefilled from the cell's dataset or the open tables, and the text goes in at the cursor, filled.

The placeholder is `<<name>>`, or `<<name: default>>` with a value to start from:

    Sales YTD = TOTALYTD([<<measure>>], '<<date table>>'[<<date column>>])
    <div class="tile">{{ <<table>> }}</div>
    <<name>> = st.selectbox("<<label: Region>>", sorted(<<table>>["<<column>>"].unique()))

Chosen so it never meets the HTML cell's own `{{ name }}` (filled from the kernel when the cell runs:
a snippet can write one, as the second line does), and because the app already reads `<...>` in code as
"still to fill in" (domain/blades.py's placeholders). Neither DAX nor Python nor HTML writes `<<word>>`.

**What a placeholder asks for is read from its name** (the rule of principle 12.5: read the code, not a
declaration), by its last word:

    ... table     a table: the dataset's (DAX), else an open one (a Python variable)
    ... column    a column of the table placeholder with the same first words (`<<date column>>` goes
                  with `<<date table>>`), else of `<<table>>`
    ... measure   a measure of the dataset (DAX)
    ... name      a Python name the piece makes (a Streamlit filter's value): it follows the column
                  placeholder with the same first words (`region` for the column Region)
    ... connection  a connection's name (the Write starters: `sab.connection("<<connection>>")`), offered
                  from the saved connections, those of the snippet's own kind first
    otherwise     text; a number when its default is one

**Filling writes each value where it stands, safely,** by its kind and the snippet's language: DAX
doubles the quote that closes its place (`'` in a table, `]` in a column or measure, `"` in text);
HTML escapes markup; Python takes a table or a name only as an identifier and anything else as the
inside of a string; Markdown (text cells on the canvas, 2026-11-15) escapes the marks that would format
or link, and inside a code span takes the value as it is (no backtick). A line break is refused
everywhere. Standard library only, no I/O.
"""

from __future__ import annotations

import html
import keyword
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain import html_cells

LANGUAGES: tuple[str, ...] = ("dax", "html", "markdown", "streamlit", "python")
# The cell a snippet of each language goes into, in the user's words.
CELL_KIND: dict[str, str] = {
    "dax": "dax",
    "html": "html",
    "markdown": "markdown",
    "streamlit": "code",
    "python": "code",
}
CELL_WORDS: dict[str, str] = {
    "dax": "a DAX cell",
    "html": "an HTML cell",
    "markdown": "a Markdown cell",
    "streamlit": "a Python cell",
    "python": "a Python cell",
}
LANGUAGE_WORDS: dict[str, str] = {
    "dax": "DAX",
    "html": "HTML",
    "markdown": "Markdown",
    "streamlit": "Streamlit",
    "python": "Python",
}
# A typed value in Markdown: the marks that would format, link or fill a name are escaped (a backslash;
# markup as HTML's own references), the rest is as typed, so "Made-up, 2026-01-31" reads as it is.
_MARKDOWN_MARKS: frozenset[str] = frozenset("\\`*_[]{}|~$")
_MARKDOWN_REFERENCES: dict[str, str] = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}

PLACEHOLDER: re.Pattern[str] = re.compile(r"<<\s*([a-z][a-z0-9_ ]{0,39}?)\s*(?::\s*([^<>\n]{0,200}?)\s*)?>>")
# An opening `<<` that does not start a well-formed placeholder (a typing slip in a snippet).
_OPENING: re.Pattern[str] = re.compile(r"<<(?!<)")
KINDS: tuple[str, ...] = ("table", "column", "measure", "name", "connection", "number", "text")
_NUMBER: re.Pattern[str] = re.compile(r"-?\d+(\.\d+)?")
# A default made of other placeholders' values: `by_{column}`.
_TEMPLATE: re.Pattern[str] = re.compile(r"\{([a-z][a-z0-9_ ]{0,39})\}")
MAX_PLACEHOLDERS: int = 40
MAX_VALUE: int = 200


class SnippetError(ValueError):
    """A snippet that cannot be read, or a value that cannot go where it stands. The message says why."""


@dataclass(frozen=True)
class Placeholder:
    name: str  # as written: "date column"
    kind: str  # one of KINDS
    default: str  # "" when it has none
    # A column's table placeholder ("date table"), or the column a name follows ("column"); else "".
    follows: str = ""

    @property
    def label(self) -> str:
        """The form's label: "Date column"."""
        return self.name[:1].upper() + self.name[1:].replace("_", " ")

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "default": self.default,
            "follows": self.follows,
        }


def _words(name: str) -> list[str]:
    return name.replace("_", " ").split()


def _prefix(name: str) -> str:
    return " ".join(_words(name)[:-1])


def kind_of(name: str, default: str = "") -> str:
    """What a placeholder asks for, by its name's last word (and a default that is a number)."""
    last = (_words(name) or [""])[-1]
    if last in ("table", "column", "measure", "name", "connection"):
        return last
    if last == "number" or (default and _NUMBER.fullmatch(default)):
        return "number"
    return "text"


def placeholders(text: str) -> list[Placeholder]:
    """Each placeholder once, in the order it first appears; a default may be given at any of its
    places (the first one written wins)."""
    names: dict[str, str] = {}
    for match in PLACEHOLDER.finditer(text):
        name = " ".join(_words(match.group(1)))
        default = (match.group(2) or "").strip()
        if name not in names or (not names[name] and default):
            names[name] = default
    found: list[Placeholder] = []
    for name, default in names.items():
        kind = kind_of(name, default)
        follows = ""
        label = (_words(name) or [""])[-1] == "label"
        if kind in ("column", "name") or label:
            # A column goes with the table of its first words (`date year column`: `date year table`,
            # else `date table`), else the plain one; a name or a label follows the column of its
            # first words (a filter's value is named for it, and its label says it).
            wanted = "table" if kind == "column" else "column"
            words = _words(_prefix(name))
            for size in range(len(words), -1, -1):
                own = " ".join([*words[:size], wanted])
                if own in names and own != name:
                    follows = own
                    break
            if not follows and kind != "column":  # else the snippet's first column
                follows = next((n for n in names if kind_of(n, names[n]) == "column"), "")
        found.append(Placeholder(name, kind, default, follows))
    return found


def check(text: str, language: str) -> list[Placeholder]:
    """A snippet's text, checked: its language is known, it is not empty, and every `<<` opens a
    placeholder that is whole. Its placeholders."""
    if language not in LANGUAGES:
        raise SnippetError(f"A snippet's language is one of {', '.join(LANGUAGES)}, not {language!r}.")
    if not text.strip():
        raise SnippetError("The snippet has no text.")
    whole = {m.start() for m in PLACEHOLDER.finditer(text)}
    for match in _OPENING.finditer(text):
        if match.start() not in whole:
            line = text.count("\n", 0, match.start()) + 1
            raise SnippetError(
                f"Line {line}: a placeholder is <<name>> or <<name: default>>, in lowercase words."
            )
    found = placeholders(text)
    if len(found) > MAX_PLACEHOLDERS:
        raise SnippetError(f"A snippet has at most {MAX_PLACEHOLDERS} placeholders.")
    return found


def python_name(text: str) -> str:
    """A column's words as a Python name: "Order Date" -> order_date (a filter's value is named so)."""
    word = re.sub(r"[^0-9a-zA-Z_]+", "_", text.strip()).strip("_").lower() or "value"
    if word[0].isdigit():
        word = f"_{word}"
    return f"{word}_" if keyword.iskeyword(word) else word


# ===== where a placeholder stands =====
# A value is written for the place its placeholder stands in, found by reading the snippet as its
# language reads it (placeholders are skipped as words):
#
#   DAX     inside "..." (text: " doubled), '...' (a table: ' doubled), [...] (a column or measure: ]
#           doubled), a comment (plain words), or bare (a number or a name only)
#   Python  inside a string (backslashes and quotes escaped), a comment, or bare (a name or a number)
#   HTML    inside an HTML cell's {{ ... }} (a Python name only), else text with its markup escaped
#   Markdown  inside a {{ ... }} (a Python name only), inside code (as typed, no backtick), else text
#             with its formatting and linking marks escaped

_BARE: re.Pattern[str] = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|-?\d+(\.\d+)?")


def _dax_places(text: str) -> dict[int, str]:
    """Each placeholder's place in DAX, by where it starts."""
    places: dict[int, str] = {}
    matches = {m.start(): m.end() for m in PLACEHOLDER.finditer(text)}
    state, i = "code", 0
    while i < len(text):
        if i in matches:
            places[i] = state
            i = matches[i]
            continue
        two, one = text[i : i + 2], text[i]
        if state == "code":
            if two in ("--", "//"):
                state = "line comment"
            elif two == "/*":
                state, i = "block comment", i + 1
            elif one == '"':
                state = "string"
            elif one == "'":
                state = "table"
            elif one == "[":
                state = "bracket"
        elif state == "line comment" and one == "\n":
            state = "code"
        elif state == "block comment" and two == "*/":
            state, i = "code", i + 1
        elif (state, one) in (("string", '"'), ("table", "'"), ("bracket", "]")):
            if text[i + 1 : i + 2] == one:  # a doubled quote stays inside
                i += 1
            else:
                state = "code"
        i += 1
    return places


def _python_places(text: str) -> dict[int, str]:
    """Each placeholder's place in Python, by where it starts."""
    places: dict[int, str] = {}
    matches = {m.start(): m.end() for m in PLACEHOLDER.finditer(text)}
    state, quote, i = "code", "", 0
    while i < len(text):
        if i in matches:
            places[i] = state
            i = matches[i]
            continue
        one = text[i]
        if state == "code":
            if one == "#":
                state = "comment"
            elif one in "'\"":
                quote = text[i : i + 3] if text[i : i + 3] in ('"""', "'''") else one
                prefix = re.search(r"[A-Za-z]*$", text[:i])
                formatted = "f" in (prefix.group(0) if prefix else "").lower()
                state, i = ("f-string" if formatted else "string"), i + len(quote) - 1
        elif state == "comment" and one == "\n":
            state = "code"
        elif state in ("string", "f-string"):
            if one == "\\":
                i += 1
            elif text.startswith(quote, i):
                state, i = "code", i + len(quote) - 1
        i += 1
    return places


def _html_places(text: str) -> dict[int, str]:
    """Each placeholder's place in HTML: inside an HTML cell's {{ ... }}, or the markup."""
    places: dict[int, str] = {}
    for match in PLACEHOLDER.finditer(text):
        before, after = text[: match.start()], text[match.end() :]
        inside = before.rfind("{{") > before.rfind("}}") and after.find("}}") != -1
        inside = inside and (after.find("{{") == -1 or after.find("}}") < after.find("{{"))
        places[match.start()] = "name" if inside else "markup"
    return places


def _markdown_places(text: str) -> dict[int, str]:
    """Each placeholder's place in Markdown: inside a Markdown cell's {{ ... }} (a name, as an HTML
    cell's), inside code (a code span or a fenced block), or the text."""
    code = html_cells.markdown_code(text)
    return {
        at: "code" if place == "markup" and any(a <= at < b for a, b in code) else place
        for at, place in _html_places(text).items()
    }


def markdown_value(value: str) -> str:
    """A typed value as Markdown text: its formatting and linking marks escaped, the rest as typed."""
    return "".join(_MARKDOWN_REFERENCES.get(c) or (f"\\{c}" if c in _MARKDOWN_MARKS else c) for c in value)


def _written(value: str, place: str, language: str, kind: str, label: str) -> str:
    """A value as it is written where its placeholder stands."""
    if "\n" in value or "\r" in value:
        raise SnippetError(f"{label} is one line.")
    if len(value) > MAX_VALUE:
        raise SnippetError(f"{label} is at most {MAX_VALUE} characters.")
    if kind == "number" and not _NUMBER.fullmatch(value):
        raise SnippetError(f"{label} is a number.")
    if place in ("line comment", "block comment", "comment"):
        return value.replace("*/", "* /")
    if language == "dax":
        doubled = {"string": '"', "table": "'", "bracket": "]"}.get(place)
        if doubled:
            return value.replace(doubled, doubled * 2)
    elif language in ("streamlit", "python") and place in ("string", "f-string"):
        written = value.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
        return written.replace("{", "{{").replace("}", "}}") if place == "f-string" else written

    elif language == "html" and place == "markup":
        return html.escape(value, quote=True)
    elif language == "markdown" and place == "markup":
        return markdown_value(value)
    elif language == "markdown" and place == "code":
        if "`" in value:
            raise SnippetError(f"{label} goes inside code here: it cannot hold a backtick (`).")
        return value
    # Bare in DAX or Python, or an HTML cell's name: a name or a number, nothing that could be code.
    if not _BARE.fullmatch(value) or keyword.iskeyword(value):
        what = "a Python name" if language != "dax" else "a name"
        raise SnippetError(f"{label} is {what} or a number here: letters, digits and _ ({value!r}).")
    return value


def resolved(text: str, language: str, values: Mapping[str, Any]) -> dict[str, str]:
    """Each placeholder's value as typed (not yet escaped): from `values` (by placeholder name), else its
    default; with neither, a name or a label follows its column (`region` and Region for Region). A
    default may be made of others' values: `<<name: by_{column}>>` is by_region. Raises SnippetError
    naming the ones that have no value."""
    found = {p.name: p for p in check(text, language)}
    given: dict[str, str] = {}
    for name, value in values.items():
        key = " ".join(_words(str(name)))
        if key in found and value is not None and str(value).strip() != "":
            given[key] = str(value).strip()
    for name, value in found.items():
        if name not in given and value.default and not _TEMPLATE.search(value.default):
            given[name] = value.default
    for name, value in found.items():
        if name not in given and not value.default and value.follows in given:
            followed = given[value.follows]
            words = followed.replace("_", " ").strip()  # a label says the column: order_date, Order date
            given[name] = python_name(followed) if value.kind == "name" else words[:1].upper() + words[1:]
    for name, value in found.items():  # a default made of others: by_{column} is by_region
        if name not in given and value.default:
            given[name] = _TEMPLATE.sub(
                lambda m: python_name(given.get(" ".join(_words(m.group(1))), m.group(1))), value.default
            )
    missing = [found[n].label for n in found if n not in given]
    if missing:
        raise SnippetError(f"Fill in {', '.join(missing)}.")
    return given


def fill(text: str, language: str, values: Mapping[str, Any]) -> str:
    """The snippet with every placeholder filled (see `resolved`), each value written safely for the
    place it stands in. Raises SnippetError naming a placeholder with no value, or a value that cannot
    go where it stands."""
    found = {p.name: p for p in check(text, language)}
    given = resolved(text, language, values)
    places = {
        "dax": _dax_places,
        "streamlit": _python_places,
        "python": _python_places,
        "html": _html_places,
        "markdown": _markdown_places,
    }[language](text)

    def write(match: re.Match[str]) -> str:
        name = " ".join(_words(match.group(1)))
        return _written(given[name], places[match.start()], language, found[name].kind, found[name].label)

    return PLACEHOLDER.sub(write, text)


def cell_name(template: str, given: Mapping[str, str], fallback: str) -> str:
    """The name a Streamlit piece gives the cell it goes into: its header's `cell_name` with the
    placeholders' values (from `resolved`) as plain words, else `fallback` (the blade's name)."""

    def word(match: re.Match[str]) -> str:
        return given.get(" ".join(_words(match.group(1)))) or (match.group(2) or "").strip()

    named = " ".join(PLACEHOLDER.sub(word, template).split())
    return (named[:1].upper() + named[1:80]) or fallback  # a cell's name starts with a capital


# ===== a snippet in its .blade.py file =====
# The header's `language` (and a Streamlit piece's `cell_name`), then the text as one Python string,
# `snippet = r"""..."""`, so a blade file stays Python. In the app, a snippet's code is the text itself.

VARIABLE: str = "snippet"


def file_body(text: str) -> str:
    """The lines after the header: the text as one string given the name `snippet`."""
    return f"{VARIABLE} = " + html_cells.script_body(text)


def read_file(body: str, header: Mapping[str, Any]) -> dict[str, Any]:
    """What a snippet's file holds after its header: its code (the text), language and cell name."""
    held, problem, _ = html_cells.script_string(body)
    if held is None or problem:
        raise SnippetError(f'A snippet\'s file holds its text as one string: {VARIABLE} = r"""...""".')
    language = header.get("language")
    if language not in LANGUAGES:
        raise SnippetError(f"A snippet's header names its language: one of {', '.join(LANGUAGES)}.")
    found: dict[str, Any] = {"code": held, "language": language}
    if isinstance(header.get("cell_name"), str):
        found["cell_name"] = header["cell_name"]
    return found
