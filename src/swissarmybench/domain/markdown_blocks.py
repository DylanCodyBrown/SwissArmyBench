"""A Markdown file as blocks (the owner, 2026-11-27: "Our markdown reader and inline editor would be a great
addition"): the reader draws a .md file block by block, a click turns one block into its source text, and
what was typed is written back into only that block's characters.

blocks(text)        the file's blocks in order: front matter (a `---` block at its very top), a heading, a
                    paragraph, a list (its nested items and indented lines with it), a table, a quote, a
                    fenced code block (blank lines inside it kept; ```mermaid a diagram), a rule. Each has
                    its place in the text (start, end: characters; line: from 1) and its own text. Blank
                    lines between blocks belong to none.
replace(text, i, to) block i's characters replaced by `to` (typed with \\n: written with the file's own line
                    ends); every other character of the file is kept as it is. An empty `to` takes the block
                    out with the blank line after it.
tick(text, i, n)    the n-th task box of block i ticked or cleared: one character changes.
title(text)         a document's title: its first heading's words (context.md lists a doc by path and title).

Pure rules, no I/O. The same splitting serves the page (POST /workbench/markdown) and the agent
(`workbench_file` blocks, edit_block).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([A-Za-z0-9_+.-]*)")
_HEADING = re.compile(r"^ {0,3}#{1,6}(\s|$)")
_RULE = re.compile(r"^\s*(---+|\*\*\*+|___+)\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_QUOTE = re.compile(r"^ {0,3}>")
_ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
_TASK = re.compile(r"^(\s*[-*+]\s+\[)([ xX])(\]\s)")
_FRONT_END = re.compile(r"^(---|\.\.\.)\s*$")
_LINE = re.compile(r"[^\r\n]*(\r\n|\n|\r|$)")
DIAGRAM_LANGUAGES: tuple[str, ...] = ("mermaid",)


class BlockError(ValueError):
    """A block that cannot be found or changed as asked: one plain sentence."""


@dataclass(frozen=True)
class Block:
    index: int
    kind: str  # front_matter, heading, paragraph, list, table, quote, code, diagram, rule
    start: int  # its first character in the text
    end: int  # one past its last (its last line's end mark is not part of it)
    line: int  # its first line, from 1
    lines: int
    text: str
    language: str = ""  # a fenced block's
    tasks: int = 0  # the task boxes in it

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "line": self.line,
            "lines": self.lines,
            "text": self.text,
            "language": self.language,
            "tasks": self.tasks,
        }


@dataclass(frozen=True)
class _Line:
    start: int
    end: int  # without its end mark
    text: str


def _lines(text: str) -> list[_Line]:
    out: list[_Line] = []
    at = 0
    while at < len(text):
        found = _LINE.match(text, at)
        end = found.end() if found else len(text)
        mark = len(found.group(1)) if found else 0
        out.append(_Line(at, end - mark, text[at : end - mark]))
        at = end
    return out


def _blank(line: _Line) -> bool:
    return not line.text.strip()


def _starts_block(lines: list[_Line], at: int) -> bool:
    """Does a line end the paragraph before it: a heading, a fence, a rule, a quote, a list item, a table."""
    text = lines[at].text
    return bool(
        _HEADING.match(text)
        or _FENCE.match(text)
        or _RULE.match(text)
        or _QUOTE.match(text)
        or _ITEM.match(text)
        or _table_at(lines, at)
    )


def _table_at(lines: list[_Line], at: int) -> bool:
    return "|" in lines[at].text and at + 1 < len(lines) and bool(_TABLE_RULE.match(lines[at + 1].text))


def _front_matter(lines: list[_Line]) -> int:
    """How many lines the file's front matter takes (a `---` line first, to its closing `---` or `...`)."""
    if not lines or lines[0].text.rstrip() != "---":
        return 0
    for at in range(1, len(lines)):
        if _FRONT_END.match(lines[at].text):
            return at + 1
    return 0


def _fence_end(lines: list[_Line], at: int) -> int:
    opened = _FENCE.match(lines[at].text)
    mark = opened.group(1) if opened else "```"
    closing = re.compile(rf"^ {{0,3}}{re.escape(mark[0])}{{{len(mark)},}}\s*$")
    for end in range(at + 1, len(lines)):
        if closing.match(lines[end].text):
            return end + 1
    return len(lines)  # not closed: the rest of the file is its code


def _list_end(lines: list[_Line], at: int) -> int:
    """A list runs through its items, their indented lines and lazy lines, and over a blank line when what
    follows is indented or another item."""
    end = at + 1
    while end < len(lines):
        line = lines[end]
        if _blank(line):
            after = end + 1
            while after < len(lines) and _blank(lines[after]):
                after += 1
            if after < len(lines) and (
                lines[after].text[:1] in (" ", "\t") or _ITEM.match(lines[after].text)
            ):
                end = after
                continue
            break
        if not _ITEM.match(line.text) and line.text[:1] not in (" ", "\t") and _starts_block(lines, end):
            break
        end += 1
    return end


def _take(lines: list[_Line], at: int) -> tuple[str, int, str]:
    """The block that starts at a line: (its kind, the line after it, a fenced block's language)."""
    text = lines[at].text
    fence = _FENCE.match(text)
    if fence:
        language = fence.group(2).lower()
        return ("diagram" if language in DIAGRAM_LANGUAGES else "code"), _fence_end(lines, at), language
    if _HEADING.match(text):
        return "heading", at + 1, ""
    if _table_at(lines, at):
        end = at + 2
        while end < len(lines) and "|" in lines[end].text and not _blank(lines[end]):
            end += 1
        return "table", end, ""
    if _RULE.match(text):
        return "rule", at + 1, ""
    if _QUOTE.match(text):
        end = at + 1
        while end < len(lines) and _QUOTE.match(lines[end].text):
            end += 1
        return "quote", end, ""
    if _ITEM.match(text):
        return "list", _list_end(lines, at), ""
    end = at + 1
    while end < len(lines) and not _blank(lines[end]) and not _starts_block(lines, end):
        end += 1
    return "paragraph", end, ""


def blocks(text: str) -> list[Block]:
    """The text's blocks, in order."""
    lines = _lines(text)
    out: list[Block] = []

    def add(kind: str, first: int, after: int, language: str = "") -> None:
        start, end = lines[first].start, lines[after - 1].end
        body = text[start:end]
        tasks = sum(1 for line in lines[first:after] if _TASK.match(line.text)) if kind == "list" else 0
        out.append(Block(len(out), kind, start, end, first + 1, after - first, body, language, tasks))

    at = _front_matter(lines)
    if at:
        add("front_matter", 0, at)
    while at < len(lines):
        if _blank(lines[at]):
            at += 1
            continue
        kind, after, language = _take(lines, at)
        add(kind, at, after, language)
        at = after
    return out


def line_end(text: str) -> str:
    """The file's own line end: the one most of its lines have (none yet: \\n)."""
    crlf = text.count("\r\n")
    lone = text.count("\n") - crlf
    return "\r\n" if crlf > lone else "\n"


def _block(text: str, index: Any) -> Block:
    found = blocks(text)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(found):
        raise BlockError(
            f"block is a block's index, 0 to {len(found) - 1}." if found else "The file has no blocks."
        )
    return found[index]


def replace(text: str, index: Any, to: Any) -> str:
    """Block `index`'s characters replaced by `to`; everything else kept byte for byte."""
    if not isinstance(to, str):
        raise BlockError("to is the block's new text.")
    block = _block(text, index)
    mark = line_end(text)
    typed = to.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if typed.strip():
        return text[: block.start] + typed.replace("\n", mark) + text[block.end :]
    # Taken out: its own line end and the blank line after it go with it.
    rest = text[block.end :]
    for _ in range(2):
        gone = re.match(r"[ \t]*(\r\n|\n|\r)", rest)
        if gone is None:
            break
        rest = rest[gone.end() :]
    return text[: block.start] + rest


def insert_after(text: str, index: Any, to: Any) -> str:
    """A new block after block `index` (-1: at the top), a blank line between them."""
    if not isinstance(to, str) or not to.strip():
        raise BlockError("to is the new block's text.")
    mark = line_end(text)
    typed = to.replace("\r\n", "\n").replace("\r", "\n").strip("\n").replace("\n", mark)
    if index == -1:
        return typed + mark + (mark + text if text else "")
    block = _block(text, index)
    return text[: block.end] + mark + mark + typed + text[block.end :]


def tick(text: str, index: Any, task: Any, done: Any = None) -> str:
    """Block `index`'s task box number `task` (from 0) ticked, cleared, or with no `done` switched: one
    character of the file changes."""
    block = _block(text, index)
    if isinstance(task, bool) or not isinstance(task, int) or not 0 <= task < block.tasks:
        raise BlockError(
            f"task is a box of the block, 0 to {block.tasks - 1}."
            if block.tasks
            else "That block has no task boxes."
        )
    seen = -1
    for line in _lines(block.text):
        found = _TASK.match(line.text)
        if found is None:
            continue
        seen += 1
        if seen == task:
            at = block.start + line.start + found.start(2)
            now = text[at] in "xX"
            want = (not now) if done is None else bool(done)
            return text[:at] + ("x" if want else " ") + text[at + 1 :]
    raise BlockError("That block has no such task box.")


def title(text: str) -> str:
    """A document's title: its first heading's words (none: "")."""
    for block in blocks(text):
        if block.kind == "heading":
            return block.text.strip().lstrip("#").strip().rstrip("#").strip()
    return ""
