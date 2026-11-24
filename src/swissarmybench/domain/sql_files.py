""".sql files on the Scripts page (the owner, 2026-11-24: "also we should allow .sql files" / "sql authorship
will have one place in scripts and not on the grid menu"): a script of DuckDB SQL over the open tables and
`[Conn].table` names, or of a connection's own SQL.

Its first comment lines may name where it runs, in a SQL cell's words: `-- connection: <name>` (the page's
dropdown beside Run file writes it); none is DuckDB over the open tables. Run file runs the file's one query,
Run selection the selected text or the statement under the cursor; the result becomes the open table named
after the file (orders_by_month.sql: orders_by_month), replaced on the next run. Pure rules, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SUFFIX: str = ".sql"
HEADER_WORD: str = "connection"
_HEADER = re.compile(r"^\s*--\s*connection\s*:\s*(.*?)\s*$", re.IGNORECASE)
_COMMENT = re.compile(r"^\s*(--.*)?$")
_TABLE_PART = re.compile(r"[^A-Za-z0-9_-]+")
MAX_TABLE: int = 64
DEFAULT_TABLE: str = "query"
STARTER: str = "SELECT *\nFROM "


class SqlFileError(ValueError):
    """What a .sql file's run cannot do, and the file's line it points at (from 1)."""

    def __init__(self, what: str, line: int | None = None, details: str | None = None) -> None:
        super().__init__(what)
        self.line = line
        self.details = details


@dataclass(frozen=True)
class Statement:
    """One statement of the file: its text (no `;`), the file's line it starts and ends on."""

    text: str
    line: int
    end_line: int


def _line_end(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _header_index(lines: list[str]) -> int | None:
    """The header's line among the file's first comment lines (blank lines between them too)."""
    for i, line in enumerate(lines):
        if not _COMMENT.match(line):
            return None
        if _HEADER.match(line):
            return i
    return None


def connection_of(text: Any) -> str | None:
    """The connection the file's header names; None: DuckDB over the open tables."""
    if not isinstance(text, str):
        return None
    lines = text.splitlines()
    at = _header_index(lines)
    if at is None:
        return None
    found = _HEADER.match(lines[at])
    name = found.group(1).strip() if found else ""
    return name or None


def with_connection(text: str, connection: str | None) -> str:
    """The file's text with its header naming `connection` (put first when there is none), or without one."""
    if connection is not None and ("\n" in connection or "\r" in connection):
        raise ValueError("A connection's name is one line.")
    end = _line_end(text)
    lines = text.split(end)
    at = _header_index(lines)
    header = f"-- {HEADER_WORD}: {connection.strip()}" if connection and connection.strip() else None
    if at is not None:
        if header is None:
            del lines[at]
        else:
            lines[at] = header
        return end.join(lines)
    return f"{header}{end}{text}" if header else text


def statements(text: str) -> list[Statement]:
    """The file's statements split at `;` outside strings, quoted names, brackets and comments; one that is
    only comments and blanks is left out."""
    found: list[Statement] = []
    start, i, n = 0, 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"":
            close = text.find(c, i + 1)
            while close != -1 and close + 1 < n and text[close + 1] == c:  # a doubled quote inside
                close = text.find(c, close + 2)
            i = n if close == -1 else close + 1
            continue
        if c == "[":
            close = text.find("]", i + 1)
            i = n if close == -1 else close + 1
            continue
        if text.startswith("--", i):
            close = text.find("\n", i)
            i = n if close == -1 else close
            continue
        if text.startswith("/*", i):
            close = text.find("*/", i + 2)
            i = n if close == -1 else close + 2
            continue
        if c == ";":
            _add(found, text, start, i)
            start = i + 1
        i += 1
    _add(found, text, start, n)
    return found


def _only_comments(part: str) -> bool:
    plain = re.sub(r"/\*.*?\*/", " ", part, flags=re.DOTALL)
    return all(_COMMENT.match(line) for line in plain.splitlines()) if plain.strip() else True


def _add(found: list[Statement], text: str, start: int, end: int) -> None:
    """The statement in text[start:end], from where its code starts (past blanks and `--` comment lines), so
    DuckDB's `LINE n` counts from its first line."""
    part = text[start:end]
    if _only_comments(part):
        return
    at = start
    while at < end:
        stop = text.find("\n", at, end)
        stop = end if stop == -1 else stop
        if not _COMMENT.match(text[at:stop]):
            break
        at = stop + 1
    while at < end and text[at] in " \t":
        at += 1
    body = text[at:end].rstrip()
    first = text.count("\n", 0, at) + 1
    found.append(Statement(body, first, first + body.count("\n")))


def statement_at(text: str, line: int) -> Statement | None:
    """The statement the cursor's line is in; on a line between two, the one before it (else the next)."""
    found = statements(text)
    if not found:
        return None
    inside = [s for s in found if s.line <= line <= s.end_line]
    if inside:
        return inside[0]
    before = [s for s in found if s.end_line < line]
    return before[-1] if before else found[0]


def to_run(text: str, selection: str | None, line: int | None) -> Statement:
    """What a run sends: Run selection (a line given) the selected text or the statement at the line; Run file
    the file's one query, refused with the second statement's line when it holds more."""
    if line is not None:
        if selection and selection.strip():
            return Statement(selection, line, line + selection.count("\n"))
        here = statement_at(text, line)
        if here is None:
            raise SqlFileError("There is no query here to run.", line)
        return here
    every = statements(text)
    if not every:
        raise SqlFileError("The file has no query to run yet.", 1)
    if len(every) > 1:
        raise SqlFileError(
            f"The file has {len(every)} statements: Run file runs one query. Put the cursor in one and "
            "Run selection (Ctrl+Enter).",
            every[1].line,
        )
    return every[0]


def table_name(path: Any) -> str:
    """The open table a file's run makes: its file's name without .sql (orders_by_month), other characters
    as _."""
    if not isinstance(path, str) or not path.strip():
        return DEFAULT_TABLE
    name = re.split(r"[\\/]", path)[-1]
    stem = name[: -len(SUFFIX)] if name.lower().endswith(SUFFIX) else name
    cleaned = _TABLE_PART.sub("_", stem).strip("_")[:MAX_TABLE]
    return cleaned or DEFAULT_TABLE


def file_name(table: str) -> str:
    """A table's .sql file's name (Edit in Scripts): its name as a table name allows, then .sql."""
    return table_name(table) + SUFFIX


def file_for(table: str, sql: str, connection: str | None) -> str:
    """A table's query as its .sql file's text: the header when a connection runs it, then the query."""
    body = sql.strip() + "\n"
    return with_connection(body, connection) if connection else body


_LINE = re.compile(r"\bLINE (\d+):")
_QUOTED = re.compile(r'"([^"\n]{1,200})"')


def error_line(message: str, statement: Statement) -> int:
    """The file's line an error points at: DuckDB's `LINE n:`, else the first line holding a name the message
    quotes, else the statement's first line."""
    found = _LINE.search(message)
    lines = statement.text.split("\n")
    if found and 1 <= int(found.group(1)) <= len(lines):
        return statement.line + int(found.group(1)) - 1
    for quoted in _QUOTED.findall(message):
        for offset, text in enumerate(lines):
            if re.search(rf"(?<![\w]){re.escape(quoted)}(?![\w])", text):
                return statement.line + offset
    return statement.line
