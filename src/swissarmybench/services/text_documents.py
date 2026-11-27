"""Text documents (domain/text_documents.py, domain/markdown_blocks.py; the owner, 2026-11-27: "Our markdown
reader and inline editor would be a great addition" / "html, markdown, and renderable code should get a
preview toggle" / "The idea is the context documentation for a project can be created and edited"), for the
page and the agent alike (the golden rule).

markdown        a Markdown text's blocks; one block edited, inserted after another or a task box ticked,
                written back into only that block's characters. With the text sent (the page's unsaved
                text) nothing is written: the new text is answered. With only a path (the agent's
                `workbench_file` blocks, edit_block) the file is read and, when it changed, saved as any
                other save (refused over a file changed on disk).
picture         a picture beside a document, for its preview (a Markdown file's relative images): pictures
                only, by their ending, at most MAX_PICTURE; never anything else of the disk.
export_picture  a diagram's preview saved beside its file as <name>.svg or <name>.png (the page drew it;
                the agent asks the page: workbench_window preview.saveSvg, preview.savePng).
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.domain import markdown_blocks as blocks
from swissarmybench.domain import text_documents as rules
from swissarmybench.services.workspace import Conflict, NotFound, Refused

MAX_PICTURE = 20_000_000
PICTURES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}
_PNG = b"\x89PNG\r\n\x1a\n"


class Pictures(Protocol):
    def read_bytes(self, path: str, most: int) -> bytes: ...

    def write_bytes(self, path: str, data: bytes) -> tuple[str, bool]: ...


class TextDocuments:
    def __init__(
        self,
        read: Callable[[str], tuple[str, str, float]],
        save: Callable[[Any, str], dict[str, Any]],
        pictures: Pictures,
    ) -> None:
        self._read = read  # a document's (text, whole path, modified)
        self._save = save  # the Workbench's own save: {path, text, modified}
        self._pictures = pictures

    def markdown(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{text | path, block?, to?, after?, task?, done?}: the blocks; with `block` and `to` that block's
        text replaced (after: true puts `to` after it as a new block; block -1 with after: at the top); with
        `block` and `task` that task box ticked (done: true or false; none: switched).
        {text, blocks, changed, written, title}."""
        if not isinstance(body, dict):
            raise ValueError('Send {"path": "README.md"} or {"text": "# Notes"}.')
        given, path, modified = body.get("text"), body.get("path"), None
        from_file = not isinstance(given, str)
        text: str = given if isinstance(given, str) else ""
        if from_file:
            if not isinstance(path, str) or not path.strip():
                raise ValueError('Send {"path": a Markdown file} or {"text": its text}.')
            kind = rules.kind_of(path)
            if kind is None or kind.preview != "markdown":
                raise ValueError(f"{path} is not a Markdown file (.md).")
            try:
                text, path, modified = self._read(path)
            except FileNotFoundError as error:
                raise NotFound(str(error)) from None
        after = text
        try:
            if "task" in body and body.get("task") is not None:
                after = blocks.tick(text, body.get("block"), body.get("task"), body.get("done"))
            elif body.get("after"):
                after = blocks.insert_after(text, body.get("block"), body.get("to"))
            elif "to" in body:
                after = blocks.replace(text, body.get("block"), body.get("to"))
        except blocks.BlockError as error:
            raise ValueError(str(error)) from None
        written = False
        if from_file and after != text:
            self._save({"path": path, "text": after, "modified": modified}, who)
            written = True
        return {
            "text": after,
            "blocks": [b.to_json() for b in blocks.blocks(after)],
            "changed": after != text,
            "written": written,
            "title": blocks.title(after),
        }

    def picture(self, path: Any) -> tuple[bytes, str]:
        """A picture's bytes and type, for a document's preview."""
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path is a picture's file.")
        ending = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ending not in PICTURES:
            raise Refused("Only a picture is shown here (.png, .jpg, .gif, .webp, .svg).")
        try:
            return self._pictures.read_bytes(path, MAX_PICTURE), PICTURES[ending]
        except FileNotFoundError:
            raise NotFound(f"There is no picture at {path}.") from None
        except ValueError as error:
            raise Refused(str(error)) from None

    def export_picture(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{path: the diagram's file, format: "svg" | "png", data: the SVG's text or the PNG as base64,
        replace?}: saved beside the file under its name. {path, written}."""
        if not isinstance(body, dict) or not isinstance(body.get("path"), str) or not body["path"].strip():
            raise ValueError('Send {"path": the diagram\'s file, "format": "svg" or "png", "data": ...}.')
        source = body["path"]
        kind = rules.kind_of(source)
        if kind is None or not kind.preview:
            raise ValueError(f"{source} has no preview to save.")
        wanted, data = body.get("format"), body.get("data")
        if wanted not in ("svg", "png") or not isinstance(data, str) or not data:
            raise ValueError('format is "svg" or "png", and data its picture.')
        if wanted == "svg":
            raw = data.encode("utf-8")
            if "<svg" not in data[:2000].lower():
                raise ValueError("data is not an SVG picture.")
        else:
            try:
                raw = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError):
                raise ValueError("data is not a PNG picture (base64).") from None
            if not raw.startswith(_PNG):
                raise ValueError("data is not a PNG picture.")
        if len(raw) > MAX_PICTURE:
            raise Refused(f"The picture is over {MAX_PICTURE // 1_000_000} MB: not saved.")
        cut = len(source) - len(kind.ending)
        target = source[:cut] + "." + wanted
        if target.lower() == source.lower():
            target = source[:cut] + ".preview." + wanted  # an .svg file's own preview never replaces it
        try:
            full, written = self._pictures.write_bytes(target, raw)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except PermissionError as error:
            raise Conflict(str(error)) from None
        return {"path": full, "written": written, "format": wanted}
