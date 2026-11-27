"""Text documents of the Scripts page (the owner, 2026-11-27: "Our markdown reader and inline editor would
be a great addition" / "Html would be a great addition, html, markdown, and renderable code should get a
preview toggle"): the files that open as a plain editor's tab, each with its editor's language and, where
the app has a renderer for it, the preview its tab's toggle draws.

ONE table (KINDS: the first ending that matches a file's lower-cased name): Markdown (its Read view the
default), HTML and SVG (drawn in the HTML cells' walled-off frame), Mermaid (.mmd, .mermaid), Vega-Lite and
Vega specs (.vl.json, .vg.json: never a structure's tab), plain text (no preview). The views are the same
three for every one that renders: preview, split, source. Pure rules, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VIEWS: tuple[str, ...] = ("preview", "split", "source")


@dataclass(frozen=True)
class TextKind:
    ending: str
    language: str  # the editor's (Monaco's) language
    preview: str  # "" (none), markdown, html, svg, mermaid, vega
    first: str  # the view a tab of it opens in
    icon: str
    words: str  # the kind in a few words

    def to_json(self) -> dict[str, Any]:
        return {
            "ending": self.ending,
            "language": self.language,
            "preview": self.preview,
            "first": self.first,
            "icon": self.icon,
            "words": self.words,
        }


KINDS: tuple[TextKind, ...] = (
    TextKind(".md", "markdown", "markdown", "preview", "markdown", "Markdown"),
    TextKind(".html", "html", "html", "source", "code", "HTML"),
    TextKind(".htm", "html", "html", "source", "code", "HTML"),
    TextKind(".svg", "xml", "svg", "source", "chart", "An SVG picture"),
    TextKind(".mmd", "plaintext", "mermaid", "source", "chart", "A Mermaid diagram"),
    TextKind(".mermaid", "plaintext", "mermaid", "source", "chart", "A Mermaid diagram"),
    TextKind(".vl.json", "json", "vega", "source", "chart", "A Vega-Lite chart"),
    TextKind(".vg.json", "json", "vega", "source", "chart", "A Vega chart"),
    TextKind(".txt", "plaintext", "", "source", "note", "Plain text"),
)
ENDINGS: tuple[str, ...] = tuple(k.ending for k in KINDS)
# The endings that would read as a structure's (a .json file) but are a chart's spec: never a structure's tab.
NOT_STRUCTURES: tuple[str, ...] = tuple(k.ending for k in KINDS if k.ending.endswith(".json"))


def kind_of(path: Any) -> TextKind | None:
    """A file's text kind by its name's ending; none: not a text document."""
    if not isinstance(path, str):
        return None
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name.startswith("."):
        return None
    return next((k for k in KINDS if name.endswith(k.ending)), None)


def is_text(path: Any) -> bool:
    return kind_of(path) is not None


def view_of(value: Any) -> str:
    """A view a call names: preview, split or source (read: Markdown's word for preview)."""
    asked = value.strip().lower() if isinstance(value, str) else ""
    asked = "preview" if asked == "read" else asked
    if asked not in VIEWS:
        raise ValueError("view is preview, split or source.")
    return asked


def rules() -> dict[str, Any]:
    """The table as data, for the pages (GET /app/rules: text)."""
    return {"kinds": [k.to_json() for k in KINDS], "views": list(VIEWS)}
