"""The records of a notebook's or script's export (split from domain/script_export.py, which makes them):
what the service gathers (each Piece: a connection, vault or blade as saved; each ExportCell), what cannot
be exported (Problem), the one ordered Plan both renderings are made from (its Blocks), and what an export
gives back (Exported). Standard library only, beside script_runtime's Secret."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from swissarmybench.domain.script_runtime import Secret


@dataclass(frozen=True)
class Piece:
    """A connection, vault or blade the script writes out: its own code, as saved in the app."""

    name: str
    kind: str  # the blade's kind: sql, other, vault, secret, snippet, analysis
    connection: str | None  # database, file, python, vault, or None (a blade)
    code: str
    variable: str
    dialect: str = "other"
    read: str | None = None  # a connection from your own Python: its Read a table box
    secrets: tuple[Secret, ...] = ()
    vault_mapping: Mapping[str, str] = field(default_factory=dict)  # variable -> entry
    vault_all: bool = False
    env_names: tuple[str, ...] = ()  # a secret blade's variables


@dataclass(frozen=True)
class ExportCell:
    kind: str  # code, sql, dax, html, markdown
    source: str
    connection: str | None = None  # a SQL cell's connection (`Shop -> orders`), a DAX cell's dataset
    role: str = ""
    table: str | None = None
    number: int | None = None
    name: str | None = None


@dataclass(frozen=True)
class Problem:
    """Something that cannot be exported: where, and why."""

    where: str  # "cell 4", or "Orders API"
    why: str
    cell: int | None = None  # the cell's index in the document

    def to_json(self) -> dict[str, object]:
        return {"where": self.where, "why": self.why}

    def __str__(self) -> str:
        return f"{self.where}: {self.why}"


@dataclass(frozen=True)
class Exported:
    text: str
    requirements: tuple[str, ...]
    settings: tuple[dict[str, object], ...]  # each variable, where it came from, whether it is a secret
    problems: tuple[Problem, ...]  # not exported (with `stub`: each such cell is a stub)
    stubs: tuple[str, ...]  # FILL IN: the tables and cells written as stubs
    skipped: tuple[str, ...]  # what was left out, in words
    places: tuple[tuple[int, int, str], ...]  # each cell's first and last line in the code, and its label
    code: str = ""  # a notebook's code cells one after another (what the checks read); a script: its text

    @property
    def python(self) -> str:
        """The Python the checks read: the script, or the notebook's code cells."""
        return self.code or self.text


@dataclass(frozen=True)
class Block:
    """One step of the document, in order: a cell's Python (at the top level), or its Markdown."""

    label: str
    lines: tuple[str, ...]
    markdown: bool = False


@dataclass(frozen=True)
class Plan:
    """The one ordered list both renderings are made from: the script, and the notebook."""

    title: str
    source: str
    blocks: tuple[Block, ...]
    pieces: tuple[Piece, ...]
    settings: tuple[Secret, ...]
    extra: tuple[str, ...]
    problems: tuple[Problem, ...]
    stubs: tuple[str, ...]
    skipped: tuple[str, ...]
    clients: tuple[tuple[str, str], ...] = ()  # (module, code): an API_<name>.py the code imports, inline
