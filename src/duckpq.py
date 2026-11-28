"""duckpq: Power Query (M) compiled to DuckDB SQL. One file; standard library and duckdb only.

    duckpq is not a Microsoft product. "Power Query" and "Power BI" are Microsoft's names; this is an
    independent reading of the published M language, with no Microsoft code in it.

It reads M (a `let ... in` query, or a section document of many `shared` queries, the shape Power BI keeps a
dataset's queries in), and compiles each query into ONE DuckDB SQL statement: a table is lazy, every
`Table.*` step composes the query, and it runs once at the end. That is query folding, into DuckDB.

    import duckpq

    tables = duckpq.run('''
        section Sales;
        shared Orders = let
            Source = Csv.Document(File.Contents("orders.csv")),
            Promoted = Table.PromoteHeaders(Source),
            Typed = Table.TransformColumnTypes(Promoted, {{"amount", type number}}),
            Big = Table.SelectRows(Typed, each [amount] > 100)
        in Big;
        shared Customers = Sql.Database("warehouse", "crm"){[Schema = "main", Item = "customers"]}[Data];
        shared ByCustomer = Table.Group(
            Table.NestedJoin(Orders, "customer_id", Customers, "id", "c", JoinKind.Inner),
            {"customer_id"}, {{"total", each List.Sum([amount]), type number}});
    ''', resolver=lambda source: "warehouse.duckdb" if source.function == "Sql.Database" else None)
    print(tables["ByCustomer"].fetchall())        # each value is a DuckDB relation: .df(), .arrow(), ...

The public API (it changes only by adding):

    parse(text, name="Query") -> Document           the tree; PowerQueryError carries line and column
    check(text, ...) -> list[Problem]               what cannot run, before anything runs
    compile(text, name, context) -> Compiled        each query's SQL and the sources it names (no I/O)
    to_sql(text, ...) -> dict[str, str]             each table query's DuckDB SQL
    run(text, ...) -> dict[str, DuckDBPyRelation]   every table query, in dependency order
    run_query(text, query, ...) -> DuckDBPyRelation one query
    functions() -> list[str]                        every M function it runs

Sources are plugged in by the caller. `resolver(source)` gets a Source (the M function, its plain arguments,
the navigation steps after it, a native query) and returns something DuckDB can read: a path (a CSV, Parquet,
JSON or Excel file; a .duckdb file is attached and the navigation picks its table), a DuckDB relation, an
Arrow table or a DataFrame; None means "not mine". Files (Csv.Document, Parquet.Document, Json.Document,
Excel.Workbook over File.Contents) and #table literals need no resolver; `tables={"orders": relation}` gives
tables a query names by their name.

A caller that reads its sources its own way (asynchronously, through its own engine) uses compile() with a
Context: what the compiler needs (a source's columns, a variable, a JSON file, a column's values for
Table.Pivot) it asks by key; a key not in `context.resolved` is listed in `context.missing`, the caller fills
them in and compiles again until none is missing. run() is that loop over a DuckDB connection.

Where M differs from SQL the compiler writes M's meaning: `null = null` is true (IS NOT DISTINCT FROM), text
compares ordinally and by case, Text.Contains is case-sensitive, `/` is never integer division, Number.Round
rounds halves to even, positions count from 0 (Text.Middle, `{0}`), a sort puts null first. What it cannot
compile (a function it does not know, a source nothing resolves, a step that needs rows where only SQL is)
is refused in one sentence with its line and column, never guessed.

Changes
    1.1.1   What cannot be compiled is refused even inside `try` (before: `try Some.Unknown([a]) otherwise 0`
            gave 0 on every row). Two kinds of failure now: EvaluationError (a PowerQueryError) is M's own
            error known while compiling (a constant that does not convert, a missing column, field or item,
            an `error`, a file that is not there: Failure(..., raised=True)) and `try` takes its otherwise
            for it; every other PowerQueryError is a refusal and passes through every `try` with its line,
            column and name. Per row, `otherwise` is still taken only where DuckDB raises for that row.
    1.1.0   `try x otherwise y` per row with any otherwise value (before: only `otherwise null`): the otherwise
            value where x raises, x's own value where it does not, a null that is no error kept null as in M.
            A conversion of a column compiles to TRY_CAST, anything else to TRY over a lambda. `try x` alone
            per row (M's error record) is still refused with its line.
    1.0.0   the first: the parser, the compiler, the functions in functions(), the sources above.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__version__ = "1.1.1"
__all__ = [
    "Compiled", "Context", "Document", "EvaluationError", "Failure", "Member", "Node", "PowerQueryError", "Problem", "Query",
    "Resolved", "Source", "check", "compile", "functions", "parse", "run", "run_query", "to_sql",
]  # fmt: skip


# ===== errors =====


class PowerQueryError(ValueError):
    """What an M text cannot be read or run as: one sentence, the line and column it points at (from 1), and
    the name it is about (a function, a query, a column) when there is one."""

    def __init__(self, what: str, line: int = 1, column: int = 1, name: str | None = None) -> None:
        super().__init__(what)
        self.what = what
        self.line = line
        self.column = column
        self.name = name

    def to_json(self) -> dict[str, Any]:
        return {"message": self.what, "line": self.line, "column": self.column, "name": self.name}


class EvaluationError(PowerQueryError):
    """An error that is M's own, known while compiling: the value M would raise as it works the expression
    out (a constant that does not convert, a column, field or item that is not there, a file that is not
    there). `try` takes its otherwise for this kind alone; any other PowerQueryError is a refusal (duckpq
    cannot compile it, and M might have run it), which no `try` catches."""


@dataclass(frozen=True)
class Node:
    """One node of the tree: its kind, where it starts, and its parts by name.

    Kinds and parts: literal(value) · text(value) · name(name, inclusive) · list(items) · record(fields:
    [(name, node)]) · let(members: [(name, node)], body) · if(test, then, other) · each(body) ·
    function(params: [(name, optional)], body) · call(target, args) · field(target | None, name, optional) ·
    project(target | None, names, optional) · item(target, index, optional) · binary(op, left, right) ·
    unary(op, operand) · try(body, otherwise | None) · error(body) · type(type: MType) · meta(body, meta) ·
    is(body, type) · as(body, type) · range(low, high).
    """

    kind: str
    line: int
    column: int
    parts: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.parts[key]


@dataclass(frozen=True)
class MType:
    """A type as written: its name (text, number, date, table, list, record, function, any...), whether it is
    nullable, a table's or a record's fields [(name, MType | None)], a list's item type."""

    name: str
    nullable: bool = False
    fields: tuple[tuple[str, MType | None], ...] | None = None
    item: MType | None = None
    # A type written as an expression (Int64.Type, Currency.Type): the node to evaluate.
    expression: Node | None = None


@dataclass(frozen=True)
class Member:
    """One query of a section document: its name, its expression, whether it is shared, and the lines it
    spans (from 1)."""

    name: str
    body: Node
    shared: bool
    line: int
    end_line: int


@dataclass(frozen=True)
class Document:
    """An M file read: a section document's members in the order written, or one expression (a plain
    `let ... in` file) as its only member, named by the caller."""

    section: str | None
    members: tuple[Member, ...]


KEYWORDS: frozenset[str] = frozenset(
    "and as each else error false if in is let meta not null or otherwise section shared then true try type".split()
)
_HASH_WORDS: frozenset[str] = frozenset(
    "#binary #date #datetime #datetimezone #duration #infinity #nan #sections #shared #table #time".split()
)
_PUNCTUATION: tuple[str, ...] = (
    "...", "=>", "<=", ">=", "<>", "??", "..",
    "=", "<", ">", "+", "-", "*", "/", "&", "(", ")", "[", "]", "{", "}", ",", ";", "@", "?", "!",
)  # fmt: skip
_ESCAPES: dict[str, str] = {"cr": "\r", "lf": "\n", "tab": "\t", "#": "#"}
PRIMITIVE_TYPES: frozenset[str] = frozenset(
    "any anynonnull binary date datetime datetimezone duration function list logical none null number record "
    "table text time type action".split()
)


@dataclass(frozen=True)
class Token:
    kind: str  # name, quoted, number, text, punct, keyword, hash, end
    value: Any
    line: int
    column: int
    start: int
    end: int


class _Reader:
    """The text read one token at a time: the parser asks for the next token, or, inside `[...]`, for a field's
    name as written (which may hold spaces: [Order Date])."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.at = 0
        self._peeked: Token | None = None
        self._line_starts = [0]
        for i, c in enumerate(text):
            if c == "\n":
                self._line_starts.append(i + 1)

    def place(self, offset: int) -> tuple[int, int]:
        low, high = 0, len(self._line_starts) - 1
        while low < high:
            mid = (low + high + 1) // 2
            if self._line_starts[mid] <= offset:
                low = mid
            else:
                high = mid - 1
        return low + 1, offset - self._line_starts[low] + 1

    def fail(self, what: str, offset: int | None = None, name: str | None = None) -> PowerQueryError:
        line, column = self.place(self.at if offset is None else offset)
        return PowerQueryError(what, line, column, name)

    def skip_blank(self) -> None:
        text, n = self.text, len(self.text)
        while self.at < n:
            c = text[self.at]
            if c.isspace() or c == "﻿":
                self.at += 1
            elif text.startswith("//", self.at):
                end = text.find("\n", self.at)
                self.at = n if end == -1 else end
            elif text.startswith("/*", self.at):
                end = text.find("*/", self.at + 2)
                if end == -1:
                    raise self.fail("This comment is never closed: add */.")
                self.at = end + 2
            else:
                return

    def peek(self) -> Token:
        if self._peeked is None:
            self._peeked = self._read()
        return self._peeked

    def next(self) -> Token:
        token = self.peek()
        self._peeked = None
        self.at = token.end
        return token

    def rewind(self, offset: int) -> None:
        self._peeked = None
        self.at = offset

    def _token(self, kind: str, value: Any, start: int, end: int) -> Token:
        line, column = self.place(start)
        return Token(kind, value, line, column, start, end)

    def _read(self) -> Token:
        self.skip_blank()
        text, start, n = self.text, self.at, len(self.text)
        if start >= n:
            return self._token("end", None, n, n)
        c = text[start]
        if c == '"':
            value, end = self._text(start)
            return self._token("text", value, start, end)
        if c == "#":
            if text.startswith('#"', start):
                value, end = self._text(start + 1)
                return self._token("quoted", value, start, end)
            end = start + 1
            while end < n and text[end].isalpha():
                end += 1
            word = text[start:end]
            if word in _HASH_WORDS:
                return self._token("hash", word, start, end)
            raise self.fail(f"{word} is not a word of M.", start, word)
        if c.isdigit() or (c == "." and start + 1 < n and text[start + 1].isdigit()):
            return self._number(start)
        if c.isalpha() or c == "_":
            end = start + 1
            while end < n and (text[end].isalnum() or text[end] == "_"):
                end += 1
                # A dotted name is one identifier (Table.SelectRows), but `..` is the range operator.
                if end < n - 1 and text[end] == "." and (text[end + 1].isalpha() or text[end + 1] == "_"):
                    end += 1
            word = text[start:end]
            return self._token("keyword" if word in KEYWORDS else "name", word, start, end)
        for mark in _PUNCTUATION:
            if text.startswith(mark, start):
                return self._token("punct", mark, start, start + len(mark))
        raise self.fail(f"{c!r} is not expected here.", start)

    def _text(self, start: int) -> tuple[str, int]:
        """A text literal from its opening quote: its value ("" is a quote, #(lf) an escape) and its end."""
        text, n = self.text, len(self.text)
        out: list[str] = []
        i = start + 1
        while i < n:
            c = text[i]
            if c == '"':
                if i + 1 < n and text[i + 1] == '"':
                    out.append('"')
                    i += 2
                    continue
                return "".join(out), i + 1
            if text.startswith("#(", i):
                close = text.find(")", i)
                if close != -1:
                    out.append(self._escape(text[i + 2 : close], i))
                    i = close + 1
                    continue
            out.append(c)
            i += 1
        raise self.fail('This text is never closed: add ".', start)

    def _escape(self, inside: str, offset: int) -> str:
        made: list[str] = []
        for part in inside.split(","):
            word = part.strip()
            if word in _ESCAPES:
                made.append(_ESCAPES[word])
            elif len(word) in (4, 8) and all(ch in "0123456789abcdefABCDEF" for ch in word):
                made.append(chr(int(word, 16)))
            else:
                raise self.fail(f"#({inside}) is not an escape M knows.", offset)
        return "".join(made)

    def _number(self, start: int) -> Token:
        text, n = self.text, len(self.text)
        if text.startswith(("0x", "0X"), start):
            end = start + 2
            while end < n and text[end] in "0123456789abcdefABCDEF":
                end += 1
            return self._token("number", int(text[start + 2 : end], 16), start, end)
        end = start
        while end < n and text[end].isdigit():
            end += 1
        whole = True
        if end < n - 1 and text[end] == "." and text[end + 1].isdigit():
            whole = False
            end += 1
            while end < n and text[end].isdigit():
                end += 1
        if end < n and text[end] in "eE":
            more = end + 1
            if more < n and text[more] in "+-":
                more += 1
            if more < n and text[more].isdigit():
                whole = False
                end = more
                while end < n and text[end].isdigit():
                    end += 1
        word = text[start:end]
        return self._token("number", int(word) if whole else float(word), start, end)

    def field_name(self) -> tuple[str, int] | None:
        """A field's name as written at this place (inside `[`): a quoted name, or the words up to `]`, `=`
        or `,`; None when none is here. Nothing is consumed."""
        self.skip_blank()
        text, start, n = self.text, self.at, len(self.text)
        if text.startswith('#"', start):
            value, end = self._text(start + 1)
            return value, end
        end = start
        while end < n and (text[end].isalnum() or text[end] in "_. \t"):
            end += 1
        name = text[start:end].strip()
        if not name or not (name[0].isalpha() or name[0] == "_" or name[0].isdigit()):
            return None
        return name, start + len(text[start:end].rstrip())


def _node(kind: str, token: Token, **parts: Any) -> Node:
    return Node(kind, token.line, token.column, parts)


class _Parser:
    def __init__(self, text: str) -> None:
        self.r = _Reader(text)

    # ----- tokens -----

    def _is(self, kind: str, value: Any = None) -> bool:
        token = self.r.peek()
        return token.kind == kind and (value is None or token.value == value)

    def _punct(self, mark: str) -> bool:
        return self._is("punct", mark)

    def _word(self, word: str) -> bool:
        return self._is("keyword", word)

    def _take(self, mark: str) -> bool:
        if self._punct(mark):
            self.r.next()
            return True
        return False

    def _expect(self, mark: str, after: str) -> Token:
        token = self.r.peek()
        if token.kind == "punct" and token.value == mark:
            return self.r.next()
        raise self._unexpected(token, f"{mark} is missing {after}")

    def _expect_word(self, word: str, after: str) -> Token:
        token = self.r.peek()
        if token.kind == "keyword" and token.value == word:
            return self.r.next()
        raise self._unexpected(token, f"`{word}` is missing {after}")

    def _unexpected(self, token: Token, what: str) -> PowerQueryError:
        found = "the end of the text" if token.kind == "end" else repr(self.r.text[token.start : token.end])
        return PowerQueryError(f"{what}: found {found}.", token.line, token.column)

    def _name(self, what: str) -> tuple[str, Token]:
        token = self.r.peek()
        if token.kind in ("name", "quoted"):
            self.r.next()
            return str(token.value), token
        raise self._unexpected(token, f"{what} is expected here")

    # ----- documents -----

    def document(self, name: str) -> Document:
        first = self.r.peek()
        if first.kind == "punct" and first.value == "[":
            # A section's attributes ([Version = "1.0"] section ...): read past when a section follows.
            start = self.r.at
            self.expression()
            if not self._word("section"):
                self.r.rewind(start)
        if self._word("section"):
            return self._section()
        body = self.expression()
        end = self.r.peek()
        if end.kind != "end":
            raise self._unexpected(end, "The query ended before this")
        last = self.r.place(len(self.r.text.rstrip()) or 0)[0]
        return Document(None, (Member(name, body, True, body.line, max(last, body.line)),))

    def _section(self) -> Document:
        self.r.next()
        section = None
        if not self._punct(";"):
            section, _ = self._name("The section's name")
        self._expect(";", "after the section's name")
        members: list[Member] = []
        seen: dict[str, Token] = {}
        while not self._is("end"):
            if self._punct("["):  # a member's attributes: read past
                self.expression()
            shared = self._word("shared")
            if shared:
                self.r.next()
            name, token = self._name("A query's name")
            if name in seen:
                raise PowerQueryError(
                    f"Two queries are named {name}: rename one.", token.line, token.column, name
                )
            seen[name] = token
            self._expect("=", f"after the query's name {name}")
            body = self.expression()
            closing = self.r.peek()
            if closing.kind == "end":
                end_line = self.r.place(max(len(self.r.text.rstrip()) - 1, 0))[0]
            else:
                end_line = self._expect(";", f"after the query {name}").line
            members.append(Member(name, body, shared, token.line, max(end_line, token.line)))
        return Document(section, tuple(members))

    # ----- expressions -----

    def expression(self) -> Node:
        token = self.r.peek()
        if token.kind == "keyword":
            if token.value == "let":
                return self._let()
            if token.value == "if":
                return self._if()
            if token.value == "each":
                self.r.next()
                return _node("each", token, body=self.expression())
            if token.value == "try":
                return self._try()
            if token.value == "error":
                self.r.next()
                return _node("error", token, body=self.expression())
        if token.kind == "punct" and token.value == "(" and self._function_ahead():
            return self._function()
        return self._coalesce()

    def _let(self) -> Node:
        start = self.r.next()
        members: list[tuple[str, Node]] = []
        seen: set[str] = set()
        while True:
            name, token = self._name("A step's name")
            if name in seen:
                raise PowerQueryError(
                    f"Two steps are named {name}: rename one.", token.line, token.column, name
                )
            seen.add(name)
            self._expect("=", f"after the step's name {name}")
            members.append((name, self.expression()))
            if not self._take(","):
                break
            if self._word("in"):
                token = self.r.peek()
                raise PowerQueryError("A comma before `in`: take it out.", token.line, token.column)
        self._expect_word("in", "after the last step (or a comma between two steps)")
        return _node("let", start, members=members, body=self.expression())

    def _if(self) -> Node:
        start = self.r.next()
        test = self.expression()
        self._expect_word("then", "after if's condition")
        then = self.expression()
        self._expect_word("else", "after if ... then ...")
        return _node("if", start, test=test, then=then, other=self.expression())

    def _try(self) -> Node:
        start = self.r.next()
        body = self.expression()
        otherwise = None
        if self._word("otherwise"):
            self.r.next()
            otherwise = self.expression()
        elif self._is("name", "catch"):
            token = self.r.peek()
            raise PowerQueryError(
                "try ... catch is not read: write try ... otherwise.", token.line, token.column, "catch"
            )
        return _node("try", start, body=body, otherwise=otherwise)

    def _function_ahead(self) -> bool:
        """Whether the `(` here opens a function's parameters: its matching `)` is followed by `=>` or `as`."""
        start, depth = self.r.at, 0
        try:
            while True:
                token = self.r.next()
                if token.kind == "end":
                    return False
                if token.kind == "punct" and token.value in "([{":
                    depth += 1
                elif token.kind == "punct" and token.value in ")]}":
                    depth -= 1
                    if depth == 0:
                        return self._punct("=>") or self._word("as")
        except PowerQueryError:
            return False
        finally:
            self.r.rewind(start)

    def _function(self) -> Node:
        start = self.r.next()
        params: list[tuple[str, bool]] = []
        while not self._punct(")"):
            optional = self._is("name", "optional")
            if optional:
                self.r.next()
            name, _ = self._name("A parameter's name")
            if self._word("as"):
                self.r.next()
                self._type()
            params.append((name, optional))
            if not self._take(","):
                break
        self._expect(")", "after the function's parameters")
        if self._word("as"):
            self.r.next()
            self._type()
        self._expect("=>", "after the function's parameters")
        return _node("function", start, params=params, body=self.expression())

    def _coalesce(self) -> Node:
        left = self._or()
        if self._punct("??"):
            token = self.r.next()
            return _node("binary", token, op="??", left=left, right=self._coalesce())
        return left

    def _or(self) -> Node:
        left = self._and()
        while self._word("or"):
            token = self.r.next()
            left = _node("binary", token, op="or", left=left, right=self._and())
        return left

    def _and(self) -> Node:
        left = self._is_as()
        while self._word("and"):
            token = self.r.next()
            left = _node("binary", token, op="and", left=left, right=self._is_as())
        return left

    def _is_as(self) -> Node:
        left = self._equality()
        while self._word("is") or self._word("as"):
            token = self.r.next()
            left = _node(str(token.value), token, body=left, type=self._type())
        return left

    def _equality(self) -> Node:
        left = self._relational()
        while self._punct("=") or self._punct("<>"):
            token = self.r.next()
            left = _node("binary", token, op=token.value, left=left, right=self._relational())
        return left

    def _relational(self) -> Node:
        left = self._additive()
        while any(self._punct(m) for m in ("<", ">", "<=", ">=")):
            token = self.r.next()
            left = _node("binary", token, op=token.value, left=left, right=self._additive())
        return left

    def _additive(self) -> Node:
        left = self._multiplicative()
        while any(self._punct(m) for m in ("+", "-", "&")):
            token = self.r.next()
            left = _node("binary", token, op=token.value, left=left, right=self._multiplicative())
        return left

    def _multiplicative(self) -> Node:
        left = self._meta()
        while self._punct("*") or self._punct("/"):
            token = self.r.next()
            left = _node("binary", token, op=token.value, left=left, right=self._meta())
        return left

    def _meta(self) -> Node:
        left = self._unary()
        while self._word("meta"):
            token = self.r.next()
            left = _node("meta", token, body=left, meta=self._unary())
        return left

    def _unary(self) -> Node:
        token = self.r.peek()
        if (token.kind == "punct" and token.value in "+-") or (
            token.kind == "keyword" and token.value == "not"
        ):
            self.r.next()
            return _node("unary", token, op=token.value, operand=self._unary())
        if token.kind == "keyword" and token.value == "type":
            self.r.next()
            return _node("type", token, type=self._type(primary=True))
        return self._postfix(self._primary())

    def _postfix(self, target: Node) -> Node:
        while True:
            token = self.r.peek()
            if token.kind != "punct":
                return target
            if token.value == "(":
                self.r.next()
                args: list[Node] = []
                while not self._punct(")"):
                    args.append(self.expression())
                    if not self._take(","):
                        break
                self._expect(")", "after the function's arguments")
                target = _node("call", token, target=target, args=args)
            elif token.value == "{":
                self.r.next()
                index = self.expression()
                self._expect("}", "after the item's position")
                target = _node("item", token, target=target, index=index, optional=self._take("?"))
            elif token.value == "[":
                self.r.next()
                target = self._access(token, target)
            else:
                return target

    def _access(self, opened: Token, target: Node | None) -> Node:
        """After `[`: a field `[Name]` or a projection `[[A], [B]]` of `target` (None: of `_`)."""
        if self._take("["):
            names: list[str] = []
            while True:
                names.append(self._field("A column's name"))
                self._expect("]", "after the column's name")
                self._take("?")
                if not self._take(","):
                    break
                self._expect("[", "before the next column's name")
            self._expect("]", "after the columns")
            return _node("project", opened, target=target, names=names, optional=self._take("?"))
        name = self._field("A field's name")
        self._expect("]", f"after the field's name {name}")
        return _node("field", opened, target=target, name=name, optional=self._take("?"))

    def _field(self, what: str) -> str:
        found = self.r.field_name()
        if found is None:
            raise self._unexpected(self.r.peek(), f"{what} is expected here")
        self.r.rewind(found[1])
        return found[0]

    def _primary(self) -> Node:
        token = self.r.peek()
        if token.kind in ("number", "text"):
            self.r.next()
            return _node("text" if token.kind == "text" else "literal", token, value=token.value)
        if token.kind == "keyword" and token.value in ("true", "false", "null"):
            self.r.next()
            return _node("literal", token, value={"true": True, "false": False, "null": None}[token.value])
        if token.kind in ("name", "quoted", "hash"):
            self.r.next()
            return _node("name", token, name=str(token.value), inclusive=False)
        if token.kind == "punct":
            if token.value == "@":
                self.r.next()
                name, _ = self._name("A name")
                return _node("name", token, name=name, inclusive=True)
            if token.value == "(":
                self.r.next()
                inner = self.expression()
                self._expect(")", "to close the bracket")
                return inner
            if token.value == "{":
                return self._list()
            if token.value == "[":
                return self._record_or_access()
            if token.value == "...":
                self.r.next()
                return _node("error", token, body=_node("text", token, value="Not implemented."))
        raise self._unexpected(token, "A value is expected here")

    def _list(self) -> Node:
        start = self.r.next()
        items: list[Node] = []
        while not self._punct("}"):
            item = self.expression()
            if self._punct(".."):
                token = self.r.next()
                item = _node("range", token, low=item, high=self.expression())
            items.append(item)
            if not self._take(","):
                break
        self._expect("}", "to close the list")
        return _node("list", start, items=items)

    def _record_or_access(self) -> Node:
        """`[` where a value starts: a record `[a = 1]`, the empty record `[]`, or a field of `_` (`[Amount]`,
        `[[A], [B]]`)."""
        start = self.r.next()
        if self._take("]"):
            return _node("record", start, fields=[])
        after = self.r.at
        if self._punct("["):
            return self._access(start, None)
        found = self.r.field_name()
        if found is not None:
            self.r.rewind(found[1])
            if self._punct("="):
                self.r.rewind(after)
                return self._record(start)
            self.r.rewind(after)
        return self._access(start, None)

    def _record(self, start: Token) -> Node:
        fields: list[tuple[str, Node]] = []
        seen: set[str] = set()
        while True:
            token = self.r.peek()
            name = self._field("A field's name")
            if name in seen:
                raise PowerQueryError(f"The record names {name} twice.", token.line, token.column, name)
            seen.add(name)
            self._expect("=", f"after the field's name {name}")
            fields.append((name, self.expression()))
            if not self._take(","):
                break
        self._expect("]", "to close the record")
        return _node("record", start, fields=fields)

    # ----- types -----

    def _type(self, primary: bool = False) -> MType:
        """A type after `type`, `as` or `is`: nullable T, a primitive's name, table [..], {T}, [..], function
        (..) as T; after `type` anything else is an expression (type Int64.Type is not M, but `type` before a
        bracketed expression is)."""
        token = self.r.peek()
        if token.kind == "name" and token.value == "nullable":
            self.r.next()
            inner = self._type(primary)
            return MType(inner.name, True, inner.fields, inner.item, inner.expression)
        if token.kind == "keyword" and token.value == "null":
            self.r.next()
            return MType("null")
        if token.kind == "name" and token.value == "table":
            self.r.next()
            if self._punct("["):
                self.r.next()
                return MType("table", fields=self._type_fields())
            if primary and (self._is("name") or self._is("quoted")):  # type table <a record type's name>
                return MType("table", expression=self._unary())
            return MType("table")
        if token.kind == "name" and token.value == "function" and primary:
            self.r.next()
            if self._punct("("):
                self._function_type()
            return MType("function")
        if token.kind == "name" and token.value in PRIMITIVE_TYPES:
            self.r.next()
            return MType(str(token.value))
        if token.kind == "punct" and token.value == "{" and primary:
            self.r.next()
            item = self._type(primary=True)
            self._expect("}", "to close the list type")
            return MType("list", item=item)
        if token.kind == "punct" and token.value == "[" and primary:
            self.r.next()
            return MType("record", fields=self._type_fields())
        if token.kind in ("name", "quoted"):  # Int64.Type, a type kept in a step
            return MType("expression", expression=self._postfix(self._primary()))
        if primary and token.kind == "punct" and token.value == "(":
            return MType("expression", expression=self._primary())
        raise self._unexpected(token, "A type is expected here")

    def _type_fields(self) -> tuple[tuple[str, MType | None], ...]:
        fields: list[tuple[str, MType | None]] = []
        while not self._punct("]"):
            if self._take("..."):
                break
            if self._is("name", "optional"):
                start = self.r.at
                self.r.next()
                if self._punct("=") or self._punct(",") or self._punct("]"):
                    self.r.rewind(start)
            name = self._field("A column's name")
            kind: MType | None = None
            if self._take("="):
                kind = self._type(primary=True)
            fields.append((name, kind))
            if not self._take(","):
                break
        self._expect("]", "to close the type")
        return tuple(fields)

    def _function_type(self) -> None:
        depth = 0
        while True:
            token = self.r.next()
            if token.kind == "end":
                raise self._unexpected(token, "The function type is never closed")
            if token.kind == "punct" and token.value == "(":
                depth += 1
            elif token.kind == "punct" and token.value == ")":
                depth -= 1
                if depth == 0:
                    break
        if self._word("as"):
            self.r.next()
            self._type(primary=True)


# ===== the tree read =====


def parse(text: str, name: str = "Query") -> Document:
    """An M file read: a section document's queries, or one expression as the query `name`. PowerQueryError says what
    cannot be read, with its line and column."""
    if not isinstance(text, str) or not text.strip():
        raise PowerQueryError("The file has no query yet.", 1, 1)
    return _Parser(text).document(name)


def parse_expression(text: str) -> Node:
    """One expression read (tests, and a selection run alone)."""
    parser = _Parser(text)
    node = parser.expression()
    end = parser.r.peek()
    if end.kind != "end":
        raise parser._unexpected(end, "The expression ended before this")
    return node


def quoted_name(name: str) -> str:
    """A name as M writes it: plain when it is an identifier, else #"..."."""
    plain = bool(name) and (name[0].isalpha() or name[0] == "_") and name not in KEYWORDS
    plain = (
        plain and all(c.isalnum() or c in "_." for c in name) and ".." not in name and not name.endswith(".")
    )
    return name if plain else '#"' + name.replace('"', '""') + '"'


def text_literal(value: str) -> str:
    """A text as M writes it: quotes doubled, line ends and tabs as their escapes."""
    out = value.replace('"', '""').replace("\r", "#(cr)").replace("\n", "#(lf)").replace("\t", "#(tab)")
    return f'"{out}"'


# ===== values =====

Key = tuple[Any, ...]


class Unknown:
    """A value not known yet (a source whose columns were not read, a variable not resolved): whatever is made
    from it is unknown too, and nothing about it is reported as a problem."""

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = Unknown()


@dataclass(frozen=True)
class Sx:
    """A piece of DuckDB SQL standing for one value of a row."""

    sql: str


@dataclass(frozen=True)
class Var:
    """A text that is exactly one `${NAME}`: a bound parameter in SQL, its value where a plain one is needed."""

    name: str

    @property
    def text(self) -> str:
        return "${" + self.name + "}"


class Cols(list[str]):
    """A table's column names in order. `open`: not known yet (any name is taken as there)."""

    open: bool = False

    def __contains__(self, name: object) -> bool:
        return self.open or super().__contains__(name)


def cols(names: Iterable[str], like: Cols | None = None, unknown: bool = False) -> Cols:
    made = Cols(names)
    made.open = unknown or (like is not None and like.open)
    return made


def q(name: str) -> str:
    """A name quoted for DuckDB."""
    return '"' + name.replace('"', '""') + '"'


@dataclass(frozen=True)
class Nested:
    """Table.NestedJoin's column before it is expanded: the other table, the keys and the join's kind."""

    other: Table
    keys: tuple[str, ...]
    other_keys: tuple[str, ...]
    kind: int


@dataclass
class Table:
    """A lazy table. Flat: SELECT `picks` FROM `base` WHERE `wheres` (a filter and a pick of columns stay one
    query, so a source can take them); else `text`, a whole SELECT."""

    columns: Cols
    base: str | None = None
    picks: list[str] | None = None
    wheres: list[str] = field(default_factory=list)
    text: str | None = None
    nested: dict[str, Nested] = field(default_factory=dict)
    # Read with its first row as the header where M has not promoted it yet (a CSV, a sheet).
    promotable: bool = False
    # A literal's rows (#table, Table.FromRecords), for what needs them (Table.PromoteHeaders).
    rows: list[list[Any]] | None = None
    # Table.FromList over a JSON file's root list: the file, read by DuckDB once its records are expanded.
    record_file: str | None = None

    def sql(self) -> str:
        if self.text is not None:
            return self.text
        picked = ", ".join(q(c) for c in self.picks) if self.picks is not None else "*"
        where = " WHERE " + " AND ".join(self.wheres) if self.wheres else ""
        return f"SELECT {picked} FROM {self.base}{where}"

    def source(self, alias: str = "t") -> str:
        """This table where a FROM names it."""
        if self.text is None and self.picks is None and not self.wheres and self.base and alias == "t":
            return self.base
        return f"({self.sql()}) AS {alias}"


def raw(text: str, columns: Cols, like: Table | None = None, keep: Iterable[str] = ()) -> Table:
    """A table from a whole SELECT; `keep`: the nested columns of `like` that are still there."""
    made = Table(columns, text=text)
    if like is not None:
        made.promotable = like.promotable
        made.nested = {name: like.nested[name] for name in keep if name in like.nested}
    return made


@dataclass(frozen=True)
class ColumnList:
    """A table's column as a list: `table` None inside Table.Group (the group's rows)."""

    expr: str
    table: Table | None = None
    distinct: bool = False

    def aggregate(self, function: str, extra: str = "") -> Sx:
        inner = ("DISTINCT " if self.distinct else "") + self.expr
        made = f"{function}({inner}{extra})"
        return Sx(made if self.table is None else f"(SELECT {made} FROM {self.table.source()})")

    def values_sql(self) -> str:
        if self.table is None:
            raise ValueError("A group's column has no rows of its own.")
        return f"SELECT {'DISTINCT ' if self.distinct else ''}{self.expr} FROM {self.table.source()}"


@dataclass(frozen=True)
class GroupRows:
    """`_` inside Table.Group's aggregate: the group's rows."""

    columns: Cols


@dataclass(frozen=True)
class RowRef:
    """`_` inside each over a table's rows: a field is its column."""

    columns: Cols
    alias: str = ""

    def column(self, name: str) -> Sx:
        return Sx((self.alias + "." if self.alias else "") + q(name))


@dataclass(frozen=True)
class TableRow:
    """One row of a table (`Orders{0}`, `Orders{[Id = 3]}`): a field is a scalar subquery."""

    table: Table
    where: str | None
    offset: int


@dataclass(frozen=True)
class Nav:
    """A source's navigation (Sql.Database(...) before a table is picked): the function, its plain arguments,
    the records picked so far and a native query."""

    function: str
    arguments: tuple[Any, ...] = ()
    navigation: tuple[Mapping[str, Any], ...] = ()
    query: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
    at: Node | None = field(default=None, compare=False)  # where it was last written: its errors point there


@dataclass(frozen=True)
class FileRef:
    """File.Contents(path)."""

    path: str


@dataclass(frozen=True)
class Workbook:
    """Excel.Workbook(File.Contents(path)): `headers` its useHeaders argument."""

    path: str
    headers: bool = False


class JsonRoot(list[Any]):
    """A JSON file's root list: `path` its file, so a table of it is read by DuckDB, not written out."""

    path: str = ""


@dataclass(frozen=True)
class Closure:
    params: tuple[tuple[str, bool], ...]
    body: Node
    scope: Any


@dataclass(frozen=True)
class Builtin:
    name: str


@dataclass(frozen=True)
class Tagged:
    """A library value that only says what it is (Splitter.SplitTextByDelimiter(","), Replacer.ReplaceText)."""

    kind: str
    args: tuple[Any, ...] = ()


@dataclass(frozen=True)
class Source:
    """One source a query reads that is not SQL's own, as the caller's resolver sees it. `name` is what the
    composed SQL calls it (m_source_0). `function` is the M function (Csv.Document, Excel.Workbook,
    Parquet.Document, Json.Document, Sql.Database, any other source function), `arguments` its plain
    arguments (a File.Contents(path) is its path), `navigation` the records picked after it
    ({[Schema = "dbo", Item = "Orders"]}), `query` a native query (Value.NativeQuery, the Query option).
    A file's `path` and a workbook's `sheet` are also given by themselves; `options` the function's options
    record (a CSV's Delimiter)."""

    name: str
    function: str
    arguments: tuple[Any, ...] = ()
    navigation: tuple[Mapping[str, Any], ...] = ()
    query: str | None = None
    path: str | None = None
    sheet: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
    line: int = 1

    @property
    def kind(self) -> str:
        """file (a path this library can read by itself) or call (a resolver's)."""
        return "file" if self.path is not None else "call"

    def words(self) -> str:
        """The source as M writes it, shortened: Sql.Database("srv", "db") dbo.Orders."""
        if self.path is not None:
            return self.path + (f" [{self.sheet}]" if self.sheet else "")
        shown = ", ".join(text_literal(a) if isinstance(a, str) else str(a) for a in self.arguments)
        picked = ".".join(str(v) for step in self.navigation for v in _picked(step))
        return (
            f"{self.function}({shown})"
            + (f" {picked}" if picked else "")
            + (" (a query)" if self.query else "")
        )

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "function": self.function, "kind": self.kind,
                               "words": self.words()}  # fmt: skip
        for key in ("path", "sheet", "query"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        return out


def _picked(step: Mapping[str, Any]) -> list[str]:
    """A navigation step's names in order: its Schema then Item, else its Name."""
    return [str(step[k]) for k in ("Schema", "Item", "Name") if step.get(k) not in (None, "")][:2]


@dataclass(frozen=True)
class Resolved:
    """A source resolved: its columns in order, and how the SQL names it when not by its own name (a caller
    whose engine has its own names for a source's table)."""

    columns: Sequence[str]
    sql: str | None = None


@dataclass(frozen=True)
class Failure:
    """A key that cannot be resolved, in one sentence: said at the line that asked. `raised`: M's own read
    would raise too (the file is not there), so a `try` around the source takes its otherwise; left False
    (nothing here reads it, a connection is missing) it is a refusal that no `try` catches."""

    message: str
    raised: bool = False


SOURCE_PREFIX = "m_source_"


class Context:
    """What the compiler knows while it compiles, and what it still needs.

    `tables`: tables a query may name by their name, each with its columns. `parameters`: values that stand
    in for the file's own parameter queries, by name. `folder`: what a relative path is relative to.
    `bind_variables`: a text that is exactly one ${NAME} goes into the SQL as ${NAME} (the caller binds it)
    instead of being asked for.

    `resolved` maps a key to its answer (or a Failure); `missing` lists the keys the last compile asked for
    and did not find. Keys: ("source", name) -> Resolved or the columns · ("json", path) -> the file's value ·
    ("variable", NAME) -> its text · ("probe", sql) -> the query's first column, as a list. `sources` maps
    every source's name to its Source."""

    def __init__(
        self,
        tables: Mapping[str, Sequence[str]] | None = None,
        parameters: Mapping[str, Any] | None = None,
        folder: str | None = None,
        bind_variables: bool = False,
    ) -> None:
        self.tables = dict(tables or {})
        self.parameters = dict(parameters or {})
        self.folder = folder
        self.bind_variables = bind_variables
        self.resolved: dict[Key, Any] = {}
        self.missing: list[Key] = []
        self.sources: dict[str, Source] = {}
        self._names: dict[str, str] = {}

    def ask(self, key: Key, node: Node | None = None) -> Any:
        """What was resolved for `key`, else UNKNOWN (and the key noted as missing); a Failure is raised at
        `node`."""
        if key in self.resolved:
            found = self.resolved[key]
            if isinstance(found, Failure):
                kind = EvaluationError if found.raised else PowerQueryError
                raise kind(found.message, node.line if node else 1, node.column if node else 1)
            return found
        if key not in self.missing:
            self.missing.append(key)
        return UNKNOWN

    def source(self, node: Node, function: str, **parts: Any) -> Source:
        """The Source for this call (one per distinct source, named in the order they are first met; the
        same source keeps its name from one compile to the next)."""
        identity = repr((function, sorted((k, repr(v)) for k, v in parts.items())))
        name = self._names.setdefault(identity, f"{SOURCE_PREFIX}{len(self._names)}")
        if name not in self.sources:
            self.sources[name] = Source(name, function, line=node.line, **parts)
        return self.sources[name]


# ----- literals as DuckDB SQL -----


def text_sql(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def literal(value: Any) -> str | None:
    """A plain value as DuckDB SQL; None when it has no SQL form."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "CAST('nan' AS DOUBLE)"
        if math.isinf(value):
            return "CAST('inf' AS DOUBLE)" if value > 0 else "CAST('-inf' AS DOUBLE)"
        return f"CAST({value!r} AS DOUBLE)"
    if isinstance(value, str):
        return text_sql(value)
    if isinstance(value, dt.datetime):
        kind = "TIMESTAMPTZ" if value.tzinfo is not None else "TIMESTAMP"
        return f"{kind} '{value.isoformat(sep=' ')}'"
    if isinstance(value, dt.date):
        return f"DATE '{value.isoformat()}'"
    if isinstance(value, dt.time):
        return f"TIME '{value.isoformat()}'"
    if isinstance(value, dt.timedelta):
        micro = value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds
        return f"to_microseconds({micro})"
    if isinstance(value, Var):
        return f"({value.text})"  # bracketed: a caller's binder sees a value's place, whatever word is before
    if isinstance(value, Sx):
        return value.sql
    if isinstance(value, list):
        parts = [literal(v) for v in value]
        return None if any(p is None for p in parts) else "[" + ", ".join(str(p) for p in parts) + "]"
    return None


# M's types as DuckDB's (None: no cast, any value).
DUCK_TYPES: dict[str, str | None] = {
    "text": "VARCHAR",
    "number": "DOUBLE",
    "logical": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    "datetimezone": "TIMESTAMPTZ",
    "time": "TIME",
    "duration": "INTERVAL",
    "binary": "BLOB",
    "any": None,
    "anynonnull": None,
    "null": None,
    "none": None,
    "Int64.Type": "BIGINT",
    "Int32.Type": "INTEGER",
    "Int16.Type": "SMALLINT",
    "Int8.Type": "TINYINT",
    "Byte.Type": "UTINYINT",
    "Double.Type": "DOUBLE",
    "Single.Type": "FLOAT",
    "Decimal.Type": "DOUBLE",
    "Number.Type": "DOUBLE",
    "Currency.Type": "DECIMAL(19,4)",
    "Percentage.Type": "DOUBLE",
    "Text.Type": "VARCHAR",
    "Character.Type": "VARCHAR",
    "Logical.Type": "BOOLEAN",
    "Date.Type": "DATE",
    "DateTime.Type": "TIMESTAMP",
    "DateTimeZone.Type": "TIMESTAMPTZ",
    "Time.Type": "TIME",
    "Duration.Type": "INTERVAL",
    "Binary.Type": "BLOB",
    "Any.Type": None,
    "Guid.Type": "VARCHAR",
}
# typeof()'s answers a Value.Is or `is` test of a type takes.
TYPE_NAMES: dict[str, tuple[str, ...]] = {
    "VARCHAR": ("VARCHAR",),
    "BOOLEAN": ("BOOLEAN",),
    "DATE": ("DATE",),
    "TIME": ("TIME",),
    "TIMESTAMP": ("TIMESTAMP", "TIMESTAMP_NS", "TIMESTAMP_MS", "TIMESTAMP_S"),
    "TIMESTAMPTZ": ("TIMESTAMP WITH TIME ZONE",),
    "INTERVAL": ("INTERVAL",),
    "BLOB": ("BLOB",),
}
NUMBER_TYPES: tuple[str, ...] = (
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT",
    "FLOAT", "DOUBLE",
)  # fmt: skip


def duck_type(kind: MType, node: Node) -> str | None:
    """A type as DuckDB's (None: any); PowerQueryError for one with no column type."""
    if kind.name not in DUCK_TYPES:
        raise PowerQueryError(f"A column cannot be typed {kind.name}.", node.line, node.column, kind.name)
    return DUCK_TYPES[kind.name]


Function = Callable[..., Any]


# ===== the evaluator =====

_BINARY_SQL: dict[str, str] = {
    "=": "({0} IS NOT DISTINCT FROM {1})",
    "<>": "({0} IS DISTINCT FROM {1})",
    "<": "({0} < {1})",
    ">": "({0} > {1})",
    "<=": "({0} <= {1})",
    ">=": "({0} >= {1})",
    "+": "({0} + {1})",
    "-": "({0} - {1})",
    "*": "({0} * {1})",
    "/": "({0} / {1})",
    "&": "({0} || {1})",
    "and": "({0} AND {1})",
    "or": "({0} OR {1})",
    "??": "coalesce({0}, {1})",
}
_MAX_RANGE = 100_000
# The namespaces of M's own library: an unknown function in one of them is not a source a resolver could know.
_LIBRARY_SPACES: frozenset[str] = frozenset(
    "Table Text List Number Date DateTime DateTimeZone Time Duration Record Value Logical Type Function "
    "Comparer Replacer Splitter Combiner Lines Binary Character Expression Error Int64 Int32 Int16 Int8 "
    "Double Single Decimal Currency Percentage Byte Guid Uri Variable Diagnostics".split()
)


@dataclass(frozen=True)
class ErrorValue:
    """`error "..."`: raised when it is the answer, DuckDB's error() inside a row's expression."""

    message: str


def _symbolic(value: Any) -> bool:
    return isinstance(value, Sx | Var | ErrorValue)


def _same(left: Any, right: Any) -> bool:
    """M's equality of two plain values: a logical is never a number, lists and records by their parts."""
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return bool(left == right)


class _Scope:
    """Names and their values, each worked out when first asked for (M is lazy: a step may name a later one)."""

    def __init__(self, run: _Run, nodes: Mapping[str, Node], parent: _Scope | None) -> None:
        self.run = run
        self.nodes = dict(nodes)
        self.values: dict[str, Any] = {}
        self.busy: list[str] = []
        self.parent = parent

    def bound(self, values: Mapping[str, Any]) -> _Scope:
        made = _Scope(self.run, {}, self)
        made.values = dict(values)
        return made

    def has(self, name: str) -> bool:
        return (
            name in self.values or name in self.nodes or (self.parent is not None and self.parent.has(name))
        )

    def get(self, name: str, node: Node, skip_self: bool = False) -> Any:
        if name in self.values:
            return self.values[name]
        if name in self.nodes and not (skip_self and self.busy and self.busy[-1] == name):
            if name in self.busy:
                loop = " -> ".join([*self.busy[self.busy.index(name) :], name])
                raise PowerQueryError(f"{name} refers to itself ({loop}).", node.line, node.column, name)
            self.busy.append(name)
            try:
                self.values[name] = self.run.ev(self.nodes[name], self)
            finally:
                self.busy.pop()
            return self.values[name]
        if self.parent is not None:
            return self.parent.get(name, node)
        return self.run.outer(name, node)


class _Section(_Scope):
    """A section document's queries: who names whom is noted (the order they run in), and a parameter given
    by the caller stands in for the file's own."""

    def __init__(self, run: _Run, document: Document) -> None:
        super().__init__(run, {m.name: m.body for m in document.members}, None)
        self.depends: dict[str, list[str]] = {m.name: [] for m in document.members}
        self.reads: dict[str, list[str]] = {m.name: [] for m in document.members}
        self.failed: dict[str, PowerQueryError] = {}

    def get(self, name: str, node: Node, skip_self: bool = False) -> Any:
        if name in self.nodes:
            if self.busy and name not in self.depends[self.busy[-1]] and name != self.busy[-1]:
                self.depends[self.busy[-1]].append(name)
            if name in self.run.context.parameters:
                return self.run.context.parameters[name]
            if name in self.failed and name not in self.busy:
                first = self.failed[name]
                raise PowerQueryError(f"{name} cannot run: {first.what}", node.line, node.column, name)
            try:
                return super().get(name, node, skip_self)
            except PowerQueryError as error:
                if not self.busy:
                    self.failed.setdefault(name, error)
                raise
        return self.run.outer(name, node)


class _Run:
    """One compile: the evaluator over a Context."""

    def __init__(self, context: Context) -> None:
        self.context = context
        self.section: _Section | None = None
        self.finishing: str | None = None  # the query whose value is being made its table (a bare source)
        self._kinds: dict[str, Callable[[Node, _Scope], Any]] = {
            "literal": lambda n, s: n["value"],
            "text": self._text,
            "name": self._name,
            "list": self._list,
            "record": self._record,
            "let": lambda n, s: self.ev(n["body"], _Scope(self, dict(n["members"]), s)),
            "if": self._if,
            "each": lambda n, s: Closure((("_", False),), n["body"], s),
            "function": lambda n, s: Closure(tuple(n["params"]), n["body"], s),
            "call": self._call,
            "field": self._field,
            "project": self._project,
            "item": self._item,
            "binary": self._binary,
            "unary": self._unary,
            "try": self._try,
            "error": self._error,
            "type": lambda n, s: self.type_of(n["type"], s),
            "meta": lambda n, s: self.ev(n["body"], s),
            "is": self._is,
            "as": lambda n, s: self.ev(n["body"], s),
        }

    def ev(self, node: Node, scope: _Scope) -> Any:
        return self._kinds[node.kind](node, scope)

    def fail(self, node: Node, what: str, name: str | None = None) -> PowerQueryError:
        """A refusal: what cannot be compiled. No `try` catches it."""
        return PowerQueryError(what, node.line, node.column, name)

    def raised(self, node: Node, what: str, name: str | None = None) -> EvaluationError:
        """M's own error, known while compiling: a `try` around it takes its otherwise."""
        return EvaluationError(what, node.line, node.column, name)

    # ----- names -----

    def outer(self, name: str, node: Node) -> Any:
        """A name no step or query has: a parameter given, a table given, a library function or constant."""
        context = self.context
        if name in context.parameters:
            return context.parameters[name]
        if name in context.tables:
            return Table(cols(context.tables[name]), base=q(name))
        if name in _FUNCTIONS or name in _SCALARS:
            return Builtin(name)
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        if name in DUCK_TYPES:
            return MType(name)
        if name == "_":
            raise self.fail(node, "`_` (or a bare [column]) is only inside `each`.", "_")
        space = name.split(".")[0]
        if "." in name and space not in _LIBRARY_SPACES:
            return Builtin(name)  # a source function a resolver may know (its call is the source)
        if "." in name:
            raise self.fail(node, f"{name} is not a function duckpq runs yet.", name)
        raise self.fail(node, f"{name} is not a step, a query or a table here.", name)

    def _name(self, node: Node, scope: _Scope) -> Any:
        return scope.get(node["name"], node)

    def _text(self, node: Node, scope: _Scope) -> Any:
        value: str = node["value"]
        if "${" not in value:
            return value
        whole = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", value)
        if whole and self.context.bind_variables:
            return Var(whole.group(1))
        return self.filled(value, node)

    def filled(self, value: str, node: Node) -> Any:
        """A text with its ${NAME}s filled in ($${ is the text ${); UNKNOWN while one is not resolved."""
        unknown = False

        def one(found: re.Match[str]) -> str:
            nonlocal unknown
            if found.group(0).startswith("$$"):
                return found.group(0)[1:]
            answer = self.context.ask(("variable", found.group(1)), node)
            if isinstance(answer, Unknown):
                unknown = True
                return ""
            return str(answer)

        made = re.sub(r"\$?\$\{([A-Za-z_][A-Za-z0-9_]*)\}", one, value)
        return UNKNOWN if unknown else made

    def _list(self, node: Node, scope: _Scope) -> Any:
        out: list[Any] = []
        for item in node["items"]:
            if item.kind != "range":
                out.append(self.ev(item, scope))
                continue
            low, high = self.ev(item["low"], scope), self.ev(item["high"], scope)
            if isinstance(low, Unknown) or isinstance(high, Unknown):
                return UNKNOWN
            if not isinstance(low, int) or not isinstance(high, int) or high - low > _MAX_RANGE:
                raise self.fail(item, "A range {a..b} takes two whole numbers at most 100,000 apart.")
            out.extend(range(low, high + 1))
        return out

    def _record(self, node: Node, scope: _Scope) -> Any:
        inner = _Scope(self, dict(node["fields"]), scope)
        return {name: inner.get(name, value) for name, value in node["fields"]}

    def type_of(self, kind: MType, scope: _Scope) -> MType:
        """A type with its written expressions worked out (type table [a = Int64.Type])."""
        if kind.expression is not None and kind.name == "expression":
            found = self.ev(kind.expression, scope)
            if not isinstance(found, MType):
                raise self.fail(kind.expression, "A type is expected here.")
            return MType(found.name, kind.nullable or found.nullable, found.fields, found.item)
        if kind.fields is None:
            return kind
        fields = tuple((name, self.type_of(t, scope) if t is not None else None) for name, t in kind.fields)
        return MType(kind.name, kind.nullable, fields, kind.item)

    # ----- values made plain or SQL -----

    def sx(self, value: Any, node: Node) -> str:
        """A value as the SQL of a row's expression."""
        if isinstance(value, ErrorValue):
            return f"error({text_sql(value.message)})"
        if isinstance(value, ColumnList) and value.table is not None:
            return f"({value.values_sql()})"
        made = literal(value)
        if made is None:
            raise self.fail(node, f"{_words(value)} cannot be a value in a row here.")
        return made

    def plain(self, value: Any, node: Node, what: str = "A plain value") -> Any:
        """A value that must be known while compiling (a path, a server, a column's name): a ${NAME} asked
        for, a column's values probed; UNKNOWN while they are not resolved."""
        if isinstance(value, Var):
            return self.context.ask(("variable", value.name), node)
        if isinstance(value, ColumnList) and value.table is not None:
            return self.context.ask(("probe", _first_seen(value)), node)
        if isinstance(value, Sx | ErrorValue | RowRef | GroupRows):
            raise self.fail(node, f"{what} is needed here, not one worked out per row.")
        if isinstance(value, list) and not isinstance(value, JsonRoot):
            made = [self.plain(v, node, what) for v in value]
            return UNKNOWN if any(isinstance(v, Unknown) for v in made) else made
        return value

    def table(self, value: Any, node: Node) -> Table:
        """A value used as a table."""
        if isinstance(value, Table):
            return value
        if isinstance(value, Nav):
            return _nav_table(self, node, value)
        if isinstance(value, Unknown):
            return _open_table()
        raise self.fail(node, f"A table is needed here, not {_words(value).lower()}.")

    def apply(self, function: Any, args: Sequence[Any], node: Node) -> Any:
        if isinstance(function, Closure):
            needed = sum(1 for _, optional in function.params if not optional)
            if not needed <= len(args) <= len(function.params):
                raise self.fail(node, f"This function takes {len(function.params)} values, not {len(args)}.")
            given = list(args) + [None] * (len(function.params) - len(args))
            scope = function.scope.bound(
                {name: v for (name, _), v in zip(function.params, given, strict=True)}
            )
            return self.ev(function.body, scope)
        if isinstance(function, Builtin):
            return self.library(function.name, list(args), node)
        if isinstance(function, Unknown):
            return UNKNOWN
        raise self.fail(node, f"{_words(function)} is not a function.")

    def library(self, name: str, args: list[Any], node: Node) -> Any:
        if any(_unknown(a) for a in args):
            return _open_table() if name.startswith(("Table.", "#table")) else UNKNOWN
        try:
            if name in _FUNCTIONS:
                return _FUNCTIONS[name](self, node, args)
            if name in _SCALARS:
                return _scalar(self, node, name, args)
        except PowerQueryError:
            raise
        except (TypeError, ValueError, IndexError, KeyError, AttributeError) as error:
            # a scalar worked out on plain values failed as M's own would; a table step's is a refusal
            kind = self.raised if name in _SCALARS else self.fail
            raise kind(node, f"{name} cannot take these values ({error}).", name) from None
        if any(isinstance(a, Sx | ErrorValue | RowRef | GroupRows) for a in args):
            raise self.fail(
                node, f"{name} is not a function duckpq runs (per row it is no source either).", name
            )
        return Nav(name, tuple(self.plain(a, node, f"{name}'s argument") for a in args), at=node)

    # ----- expressions -----

    def _call(self, node: Node, scope: _Scope) -> Any:
        target = self.ev(node["target"], scope)
        args = [self.ev(a, scope) for a in node["args"]]
        return self.apply(target, args, node)

    def _if(self, node: Node, scope: _Scope) -> Any:
        test = self.ev(node["test"], scope)
        if isinstance(test, Unknown):
            return UNKNOWN
        if isinstance(test, bool):
            return self.ev(node["then" if test else "other"], scope)
        if not _symbolic(test):
            raise self.raised(node, "if needs a condition that is true or false.")
        then, other = self.ev(node["then"], scope), self.ev(node["other"], scope)
        if _unknown(then) or _unknown(other):
            return UNKNOWN
        return Sx(
            f"CASE WHEN {self.sx(test, node)} THEN {self.sx(then, node)} ELSE {self.sx(other, node)} END"
        )

    def _try(self, node: Node, scope: _Scope) -> Any:
        try:
            value = self.ev(node["body"], scope)
        except EvaluationError:  # M's own error; a refusal (any other PowerQueryError) passes through
            if node["otherwise"] is None:
                raise
            return self.ev(node["otherwise"], scope)
        if isinstance(value, ErrorValue) and node["otherwise"] is not None:
            return self.ev(node["otherwise"], scope)
        if not isinstance(value, Sx):
            return value
        if node["otherwise"] is None:
            raise self.fail(
                node,
                "Per row, try needs an otherwise (`try ... otherwise 0`): try alone is a record of the error, "
                "which a column of SQL cannot hold.",
                "try",
            )
        otherwise = self.ev(node["otherwise"], scope)
        if _unknown(otherwise):
            return UNKNOWN
        return Sx(_try_sql(self, node, value.sql, otherwise))

    def _error(self, node: Node, scope: _Scope) -> Any:
        message = self.ev(node["body"], scope)
        if isinstance(message, dict):
            message = message.get("Message") or message.get("Reason") or "An error."
        return ErrorValue(str(message) if not _symbolic(message) else "An error.")

    def _unary(self, node: Node, scope: _Scope) -> Any:
        value = self.ev(node["operand"], scope)
        op = node["op"]
        if isinstance(value, Unknown):
            return UNKNOWN
        if _symbolic(value):
            return Sx(f"(NOT {self.sx(value, node)})" if op == "not" else f"({op}{self.sx(value, node)})")
        if value is None:
            return None
        if op == "not":
            if not isinstance(value, bool):
                raise self.raised(node, "not needs true or false.")
            return not value
        return -value if op == "-" else value

    def _binary(self, node: Node, scope: _Scope) -> Any:
        op = node["op"]
        left = self.ev(node["left"], scope)
        if op in ("and", "or") and isinstance(left, bool) and left is (op == "or"):
            return left
        if op == "??" and not _symbolic(left) and not isinstance(left, Unknown):
            return self.ev(node["right"], scope) if left is None else left
        right = self.ev(node["right"], scope)
        if _unknown(left) or _unknown(right):
            both = isinstance(left, Table | Nav) or isinstance(right, Table | Nav)
            return _open_table() if both else UNKNOWN
        if op == "&" and isinstance(left, Table | Nav) and isinstance(right, Table | Nav):
            return _FUNCTIONS["Table.Combine"](self, node, [[left, right]])
        if _symbolic(left) or _symbolic(right):
            return Sx(_BINARY_SQL[op].format(self.sx(left, node), self.sx(right, node)))
        try:
            return _plain_binary(op, left, right)
        except (TypeError, ValueError):
            raise self.raised(
                node, f"{op} cannot be worked out between {_words(left).lower()} and {_words(right).lower()}."
            ) from None

    def _is(self, node: Node, scope: _Scope) -> Any:
        value = self.ev(node["body"], scope)
        return _is_type(self, node, value, self.type_of(node["type"], scope))

    def _field(self, node: Node, scope: _Scope) -> Any:
        target = scope.get("_", node) if node["target"] is None else self.ev(node["target"], scope)
        return self.field(target, node["name"], node["optional"], node)

    def field(self, target: Any, name: str, optional: bool, node: Node) -> Any:
        if isinstance(target, Unknown):
            return UNKNOWN
        if isinstance(target, dict):
            if name not in target:
                if optional:
                    return None
                raise self.raised(node, f"The record has no field {name}.", name)
            return target[name]
        if isinstance(target, RowRef):
            _need(self, node, target.columns, [name])
            return target.column(name)
        if isinstance(target, GroupRows):
            _need(self, node, target.columns, [name])
            return ColumnList(q(name))
        if isinstance(target, Table):
            _need(self, node, target.columns, [name])
            return ColumnList(q(name), target)
        if isinstance(target, TableRow):
            _need(self, node, target.table.columns, [name])
            where = f" WHERE {target.where}" if target.where else ""
            return Sx(
                f"(SELECT {q(name)} FROM {target.table.source()}{where} LIMIT 1 OFFSET {target.offset})"
            )
        if isinstance(target, Nav) and name in ("Data", "Content"):
            return target
        if isinstance(target, Nav):
            return _nav_table_field(self, node, target, name)
        raise self.fail(node, f"[{name}] cannot be read from {_words(target).lower()}.", name)

    def _project(self, node: Node, scope: _Scope) -> Any:
        target = scope.get("_", node) if node["target"] is None else self.ev(node["target"], scope)
        if isinstance(target, Unknown):
            return UNKNOWN
        if isinstance(target, dict):
            return {n: self.field(target, n, node["optional"], node) for n in node["names"]}
        if isinstance(target, Table | Nav):
            return _FUNCTIONS["Table.SelectColumns"](self, node, [target, list(node["names"])])
        raise self.fail(node, f"[[...]] cannot pick columns from {_words(target).lower()}.")

    def _item(self, node: Node, scope: _Scope) -> Any:
        target = self.ev(node["target"], scope)
        index = self.ev(node["index"], scope)
        if _unknown(target) or _unknown(index):
            return UNKNOWN
        if isinstance(target, Nav | Workbook):
            return _navigate(self, node, target, index)
        if isinstance(target, Table):
            return _table_row(self, node, target, index)
        if isinstance(target, ColumnList) and target.table is not None and isinstance(index, int):
            return Sx(f"({target.values_sql()} LIMIT 1 OFFSET {index})")
        if isinstance(target, list) and isinstance(index, int) and not isinstance(index, bool):
            if 0 <= index < len(target):
                return target[index]
            if node["optional"]:
                return None
            raise self.raised(node, f"The list has {len(target)} items: there is no item {index} (from 0).")
        raise self.fail(node, f"{{...}} cannot pick from {_words(target).lower()}.")


def _unknown(value: Any) -> bool:
    return isinstance(value, Unknown) or (
        isinstance(value, list) and any(isinstance(v, Unknown) for v in value)
    )


def _open_table() -> Table:
    return Table(cols([], unknown=True), text="SELECT NULL WHERE FALSE")


def _words(value: Any) -> str:
    """What a value is, for a sentence."""
    kinds: list[tuple[Any, str]] = [
        (Table, "A table"), (Nav, "A source"), (str, "A text"), (bool, "A logical"), (int, "A number"),
        (float, "A number"), (list, "A list"), (dict, "A record"), (Closure, "A function"),
        (Builtin, "A function"), (Sx, "A row's value"), (ColumnList, "A column"), (MType, "A type"),
        (RowRef, "A row"), (GroupRows, "A group's rows"), (dt.date, "A date"), (FileRef, "A file"),
        (Workbook, "A workbook"), (TableRow, "A row"),
    ]  # fmt: skip
    if value is None:
        return "Null"
    return next((words for kind, words in kinds if isinstance(value, kind)), "This value")


def _first_seen(column: ColumnList) -> str:
    """A column's distinct values in the order they are first met (List.Distinct's order)."""
    if column.table is None:
        raise ValueError("A group's column has no rows of its own.")
    inner = f"SELECT {column.expr} AS v, row_number() OVER () AS n FROM {column.table.source()}"
    if not column.distinct:
        return f"SELECT v FROM ({inner}) AS s ORDER BY n"
    return f"SELECT v FROM ({inner}) AS s GROUP BY v ORDER BY min(n)"


def _plain_binary(op: str, left: Any, right: Any) -> Any:
    """An operator between two plain values, with M's meaning."""
    if op == "=":
        return _same(left, right)
    if op == "<>":
        return not _same(left, right)
    if op in ("and", "or"):
        if not all(v is None or isinstance(v, bool) for v in (left, right)):
            raise TypeError(op)
        if op == "and":
            return False if False in (left, right) else (None if None in (left, right) else True)
        return True if True in (left, right) else (None if None in (left, right) else False)
    if op == "&" and isinstance(left, dict) and isinstance(right, dict):
        return {**left, **right}
    if left is None or right is None:
        return None
    if op == "&":
        if not (isinstance(left, str | list) and type(left) is type(right)):
            raise TypeError(op)
        first: Any = left
        return first + right
    if op == "/":
        if right == 0:
            return math.nan if left == 0 else math.copysign(math.inf, left)
        return left / right
    if op in ("+", "-", "*") and (isinstance(left, str) or isinstance(right, str)):
        raise TypeError(op)
    compare: dict[str, Callable[[Any, Any], Any]] = {
        "<": lambda a, b: a < b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b,
        "+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b,
    }  # fmt: skip
    return compare[op](left, right)


def _is_type(run: _Run, node: Node, value: Any, kind: MType) -> Any:
    """`value is type` / Value.Is: a plain value by its Python type, a row's value by DuckDB's typeof."""
    if isinstance(value, Unknown):
        return UNKNOWN
    if kind.name in ("any",):
        return True
    if _symbolic(value):
        sql = run.sx(value, node)
        if kind.name == "null":
            return Sx(f"({sql} IS NULL)")
        if kind.name == "anynonnull":
            return Sx(f"({sql} IS NOT NULL)")
        duck = duck_type(kind, node)
        names = NUMBER_TYPES if kind.name == "number" else TYPE_NAMES.get(str(duck), (str(duck),))
        listed = ", ".join(text_sql(n) for n in names)
        decimal = f" OR typeof({sql}) LIKE 'DECIMAL%'" if kind.name == "number" else ""
        null = f" OR {sql} IS NULL" if kind.nullable else ""
        return Sx(f"(({sql} IS NOT NULL AND (typeof({sql}) IN ({listed}){decimal})){null})")
    tests: dict[str, Callable[[Any], bool]] = {
        "null": lambda v: v is None,
        "anynonnull": lambda v: v is not None,
        "text": lambda v: isinstance(v, str),
        "logical": lambda v: isinstance(v, bool),
        "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
        "date": lambda v: isinstance(v, dt.date) and not isinstance(v, dt.datetime),
        "datetime": lambda v: isinstance(v, dt.datetime),
        "time": lambda v: isinstance(v, dt.time),
        "duration": lambda v: isinstance(v, dt.timedelta),
        "list": lambda v: isinstance(v, list),
        "record": lambda v: isinstance(v, dict),
        "table": lambda v: isinstance(v, Table | Nav),
        "function": lambda v: isinstance(v, Closure | Builtin),
    }
    if kind.name not in tests:
        raise run.fail(node, f"`is {kind.name}` is not a test duckpq runs.", kind.name)
    return (kind.nullable and value is None) or tests[kind.name](value)


def _need(run: _Run, node: Node, columns: Cols, names: Iterable[str]) -> None:
    """Every name is a column, else the one sentence that says which is not."""
    for name in names:
        if name not in columns:
            shown = ", ".join(columns[:8]) + (", ..." if len(columns) > 8 else "")
            raise run.raised(
                node, f"{name} is not a column here (the table has {shown or 'no columns'}).", name
            )


# ===== sources =====


def _source_table(run: _Run, node: Node, source: Source, promotable: bool = False) -> Table:
    """A source as a table: its columns asked of the context (an open table while they are not known)."""
    section = run.section
    reader = (section.busy[-1] if section.busy else run.finishing) if section is not None else None
    if section is not None and reader is not None and source.name not in section.reads[reader]:
        section.reads[reader].append(source.name)
    found = run.context.ask(("source", source.name), node)
    if isinstance(found, Unknown):
        made = _open_table()
    elif isinstance(found, Resolved):
        made = Table(cols(str(c) for c in found.columns), base=found.sql or q(source.name))
    else:
        made = Table(cols(str(c) for c in found), base=q(source.name))
    made.promotable = promotable
    return made


def _path(run: _Run, node: Node, value: Any, function: str) -> Any:
    """A file function's first argument as its path (File.Contents(...)); UNKNOWN while a variable is."""
    if isinstance(value, FileRef):
        return value.path
    raise run.fail(node, f"{function} needs File.Contents(a path).", function)


def _file_contents(run: _Run, node: Node, args: list[Any]) -> Any:
    path = run.plain(args[0], node, "A file's path")
    if isinstance(path, Unknown):
        return UNKNOWN
    if not isinstance(path, str) or not path.strip():
        raise run.fail(node, "File.Contents needs a file's path as text.", "File.Contents")
    folder = run.context.folder
    if folder and not os.path.isabs(path) and not re.match(r"^[A-Za-z]:[\\/]|^[a-z][a-z0-9+.-]*://", path):
        path = os.path.join(folder, path)
    return FileRef(path)


def _options(args: list[Any], at: int) -> dict[str, Any]:
    return dict(args[at]) if len(args) > at and isinstance(args[at], dict) else {}


def _other_content(run: _Run, node: Node, nav: Nav, promotable: bool) -> Table:
    """A document function over content that is not a file here (Web.Contents(...)): a resolver's source."""
    source = run.context.source(node, nav.function, arguments=nav.arguments)
    return _source_table(run, node, source, promotable)


def _csv_document(run: _Run, node: Node, args: list[Any]) -> Any:
    if isinstance(args[0], Nav):
        return _other_content(run, node, args[0], True)
    path = _path(run, node, args[0], "Csv.Document")
    options = {k: v for k, v in _options(args, 1).items() if k in ("Delimiter", "Encoding", "QuoteStyle")}
    if len(args) > 1 and isinstance(args[1], str):
        options = {"Delimiter": args[1]}
    source = run.context.source(node, "Csv.Document", arguments=(path,), path=path, options=options)
    return _source_table(run, node, source, promotable=True)


def _parquet_document(run: _Run, node: Node, args: list[Any]) -> Any:
    if isinstance(args[0], Nav):
        return _other_content(run, node, args[0], False)
    path = _path(run, node, args[0], "Parquet.Document")
    return _source_table(
        run, node, run.context.source(node, "Parquet.Document", arguments=(path,), path=path)
    )


def _json_document(run: _Run, node: Node, args: list[Any]) -> Any:
    path = _path(run, node, args[0], "Json.Document")
    value = run.context.ask(("json", path), node)
    if isinstance(value, list):
        root = JsonRoot(value)
        root.path = path
        return root
    return value


def _excel_workbook(run: _Run, node: Node, args: list[Any]) -> Any:
    path = _path(run, node, args[0], "Excel.Workbook")
    headers = args[1] if len(args) > 1 else None
    if isinstance(headers, dict):
        headers = headers.get("UseHeaders")
    return Workbook(path, headers is True)


def _navigate(run: _Run, node: Node, target: Nav | Workbook, index: Any) -> Any:
    """`Source{[Schema = "dbo", Item = "Orders"]}`: one more record picked."""
    if not isinstance(index, dict) or not index:
        raise run.fail(
            node, "A source's table is picked by a record: Source{[Schema = ..., Item = ...]}[Data]."
        )
    step = {str(k): run.plain(v, node, "A source's table name") for k, v in index.items()}
    if any(isinstance(v, Unknown) for v in step.values()):
        return UNKNOWN
    if isinstance(target, Workbook):
        sheet = step.get("Item") or step.get("Name")
        if not isinstance(sheet, str):
            raise run.fail(
                node, 'A workbook\'s sheet is picked by its name: {[Item = "Sheet1", Kind = "Sheet"]}.'
            )
        kind = str(step.get("Kind") or "Sheet")
        return Nav("Excel.Workbook", (target.path,), (step,), options={"path": target.path, "sheet": sheet,
                   "promotable": not target.headers and kind == "Sheet"}, at=node)  # fmt: skip
    return Nav(
        target.function, target.arguments, (*target.navigation, step), target.query, target.options, node
    )


def _nav_table(run: _Run, node: Node, nav: Nav) -> Table:
    """A navigation used as a table: its Source, asked of the context."""
    node = nav.at or node
    if nav.function == "Excel.Workbook":
        if not nav.navigation:
            raise run.fail(
                node, 'Pick the workbook\'s sheet: Source{[Item = "Sheet1", Kind = "Sheet"]}[Data].'
            )
        source = run.context.source(node, "Excel.Workbook", arguments=nav.arguments, navigation=nav.navigation,
                                    path=nav.options["path"], sheet=nav.options["sheet"])  # fmt: skip
        return _source_table(run, node, source, promotable=bool(nav.options["promotable"]))
    source = run.context.source(
        node, nav.function, arguments=nav.arguments, navigation=nav.navigation, query=nav.query,
        options={k: v for k, v in nav.options.items() if isinstance(v, str | int | float | bool)},
    )  # fmt: skip
    return _source_table(run, node, source)


def _nav_table_field(run: _Run, node: Node, nav: Nav, name: str) -> Any:
    """A field other than [Data] read off a navigation: a column of the table it stands for."""
    table = _nav_table(run, node, nav)
    _need(run, node, table.columns, [name])
    return ColumnList(q(name), table)


def _database(function: str) -> Callable[[_Run, Node, list[Any]], Any]:
    """A database source function: its plain arguments, its options record and its Query option."""

    def made(run: _Run, node: Node, args: list[Any]) -> Any:
        plain = [run.plain(a, node, f"{function}'s argument") for a in args]
        if any(isinstance(a, Unknown) for a in plain):
            return UNKNOWN
        options = next((a for a in plain if isinstance(a, dict)), {})
        query = options.get("Query") if isinstance(options.get("Query"), str) else None
        arguments = tuple(a for a in plain if not isinstance(a, dict))
        while arguments and arguments[-1] is None:
            arguments = arguments[:-1]
        return Nav(function, arguments, (), query, {k: v for k, v in options.items() if k != "Query"}, node)

    return made


def _native_query(run: _Run, node: Node, args: list[Any]) -> Any:
    target, query = args[0], run.plain(args[1], node, "The query's text")
    if isinstance(query, Unknown):
        return UNKNOWN
    if not isinstance(target, Nav) or not isinstance(query, str):
        raise run.fail(
            node, "Value.NativeQuery needs a database source and the query's text.", "Value.NativeQuery"
        )
    if len(args) > 2 and args[2] not in (None, {}, []):
        raise run.fail(node, "Value.NativeQuery's parameters are not run: write the values in the query.",
                       "Value.NativeQuery")  # fmt: skip
    return Nav(target.function, target.arguments, target.navigation, query, target.options, node)


def _table_row(run: _Run, node: Node, table: Table, index: Any) -> Any:
    """`Orders{0}` (a row by position, from 0) or `Orders{[Id = 3]}` (the row with these values)."""
    if isinstance(index, int) and not isinstance(index, bool) and index >= 0:
        return TableRow(table, None, index)
    if isinstance(index, dict) and index:
        _need(run, node, table.columns, index)
        tests = [f"{q(k)} IS NOT DISTINCT FROM {run.sx(v, node)}" for k, v in index.items()]
        return TableRow(table, " AND ".join(tests), 0)
    raise run.fail(node, "A table's row is picked by its position (from 0) or by a record of its values.")


# ===== the scalar functions, as data =====
#
# name -> {how many arguments: the DuckDB SQL, {0} {1} ... its arguments}. One entry a function; what needs more
# than a template (an optional comparer, a list argument) is a function in _FUNCTIONS below.

_TRIM = r"' ' || chr(9) || chr(10) || chr(13)"
_SCALARS: dict[str, dict[int, str]] = {
    "Text.Upper": {1: "upper({0})"},
    "Text.Lower": {1: "lower({0})"},
    "Text.Trim": {1: f"trim({{0}}, {_TRIM})", 2: "trim({0}, {1})"},
    "Text.TrimStart": {1: f"ltrim({{0}}, {_TRIM})", 2: "ltrim({0}, {1})"},
    "Text.TrimEnd": {1: f"rtrim({{0}}, {_TRIM})", 2: "rtrim({0}, {1})"},
    "Text.Start": {2: "left({0}, {1})"},
    "Text.End": {2: "right({0}, {1})"},
    "Text.Middle": {2: "substr({0}, ({1}) + 1)", 3: "substr({0}, ({1}) + 1, {2})"},
    "Text.Range": {2: "substr({0}, ({1}) + 1)", 3: "substr({0}, ({1}) + 1, {2})"},
    "Text.At": {2: "substr({0}, ({1}) + 1, 1)"},
    "Text.Length": {1: "length({0})"},
    "Text.Replace": {3: "replace({0}, {1}, {2})"},
    "Text.From": {1: "CAST({0} AS VARCHAR)", 2: "CAST({0} AS VARCHAR)"},
    "Text.Reverse": {1: "reverse({0})"},
    "Text.Repeat": {2: "repeat({0}, {1})"},
    "Text.PadStart": {2: "lpad({0}, {1}, ' ')", 3: "lpad({0}, {1}, {2})"},
    "Text.PadEnd": {2: "rpad({0}, {1}, ' ')", 3: "rpad({0}, {1}, {2})"},
    "Text.PositionOf": {2: "(instr({0}, {1}) - 1)"},
    "Text.Split": {2: "string_split({0}, {1})"},
    "Text.BeforeDelimiter": {
        2: "CASE WHEN contains({0}, {1}) THEN left({0}, instr({0}, {1}) - 1) ELSE {0} END"
    },
    "Text.AfterDelimiter": {
        2: "CASE WHEN contains({0}, {1}) THEN substr({0}, instr({0}, {1}) + length({1})) ELSE '' END"
    },
    "Number.From": {1: "CAST({0} AS DOUBLE)", 2: "CAST({0} AS DOUBLE)"},
    "Number.FromText": {1: "CAST({0} AS DOUBLE)", 2: "CAST({0} AS DOUBLE)"},
    "Number.ToText": {1: "CAST({0} AS VARCHAR)"},
    "Number.Abs": {1: "abs({0})"},
    "Number.Sign": {1: "sign({0})"},
    "Number.Sqrt": {1: "sqrt({0})"},
    "Number.Power": {2: "pow({0}, {1})"},
    "Number.Mod": {2: "({0} % {1})"},
    "Number.IntegerDivide": {2: "CAST(trunc(({0}) / ({1})) AS BIGINT)"},
    "Number.RoundDown": {1: "floor({0})"},
    "Number.RoundUp": {1: "ceil({0})"},
    "Number.IsEven": {1: "(({0}) % 2 = 0)"},
    "Number.IsOdd": {1: "(({0}) % 2 <> 0)"},
    "Number.IsNaN": {1: "isnan({0})"},
    "Int64.From": {1: "CAST(round_even(CAST({0} AS DOUBLE), 0) AS BIGINT)"},
    "Int32.From": {1: "CAST(round_even(CAST({0} AS DOUBLE), 0) AS INTEGER)"},
    "Double.From": {1: "CAST({0} AS DOUBLE)"},
    "Decimal.From": {1: "CAST({0} AS DOUBLE)"},
    "Currency.From": {1: "CAST({0} AS DECIMAL(19,4))"},
    "Logical.From": {1: "CAST({0} AS BOOLEAN)"},
    "Logical.FromText": {1: "CAST({0} AS BOOLEAN)"},
    "Date.From": {1: "CAST({0} AS DATE)", 2: "CAST({0} AS DATE)"},
    "Date.FromText": {1: "CAST({0} AS DATE)"},
    "Date.Year": {1: "year({0})"},
    "Date.Month": {1: "month({0})"},
    "Date.Day": {1: "day({0})"},
    "Date.QuarterOfYear": {1: "quarter({0})"},
    "Date.DayOfYear": {1: "dayofyear({0})"},
    "Date.MonthName": {1: "monthname({0})"},
    "Date.DayOfWeekName": {1: "dayname({0})"},
    "Date.DaysInMonth": {1: "day(last_day({0}))"},
    "Date.StartOfDay": {1: "date_trunc('day', {0})"},
    "Date.StartOfMonth": {1: "CAST(date_trunc('month', {0}) AS DATE)"},
    "Date.StartOfQuarter": {1: "CAST(date_trunc('quarter', {0}) AS DATE)"},
    "Date.StartOfYear": {1: "CAST(date_trunc('year', {0}) AS DATE)"},
    "Date.EndOfMonth": {1: "last_day({0})"},
    "Date.EndOfYear": {1: "make_date(year({0}), 12, 31)"},
    "Date.AddDays": {2: "CAST({0} + to_days(CAST({1} AS INTEGER)) AS DATE)"},
    "Date.AddWeeks": {2: "CAST({0} + to_days(CAST(({1}) * 7 AS INTEGER)) AS DATE)"},
    "Date.AddMonths": {2: "CAST({0} + to_months(CAST({1} AS INTEGER)) AS DATE)"},
    "Date.AddQuarters": {2: "CAST({0} + to_months(CAST(({1}) * 3 AS INTEGER)) AS DATE)"},
    "Date.AddYears": {2: "CAST({0} + to_years(CAST({1} AS INTEGER)) AS DATE)"},
    "Date.IsLeapYear": {1: "(day(last_day(make_date(year({0}), 2, 1))) = 29)"},
    "DateTime.From": {1: "CAST({0} AS TIMESTAMP)", 2: "CAST({0} AS TIMESTAMP)"},
    "DateTime.FromText": {1: "CAST({0} AS TIMESTAMP)"},
    "DateTime.Date": {1: "CAST({0} AS DATE)"},
    "DateTime.Time": {1: "CAST({0} AS TIME)"},
    "DateTime.LocalNow": {0: "CAST(now() AS TIMESTAMP)"},
    "DateTime.FixedLocalNow": {0: "CAST(now() AS TIMESTAMP)"},
    "Time.From": {1: "CAST({0} AS TIME)"},
    "Time.Hour": {1: "hour({0})"},
    "Time.Minute": {1: "minute({0})"},
    "Time.Second": {1: "second({0})"},
    "Character.FromNumber": {1: "chr({0})"},
    "Character.ToNumber": {1: "unicode({0})"},
}
# The same functions on plain values, where one is needed while compiling (a parameter made upper case).
_PLAIN: dict[str, Callable[..., Any]] = {
    "Text.Upper": lambda t: t.upper(),
    "Text.Lower": lambda t: t.lower(),
    "Text.Trim": lambda t: t.strip(),
    "Text.Length": lambda t: len(t),
    "Text.Start": lambda t, n: t[:n],
    "Text.End": lambda t, n: t[-n:] if n else "",
    "Text.Replace": lambda t, a, b: t.replace(a, b),
    "Text.From": lambda v: (
        v if isinstance(v, str) else ("true" if v is True else "false" if v is False else str(v))
    ),
    "Number.From": lambda v: (
        float(v) if isinstance(v, str) and not v.strip().lstrip("-").isdigit() else int(v)
    ),
    "Number.Abs": abs,
    "Int64.From": lambda v: round(float(v)),
    "Date.Year": lambda d: d.year,
    "Date.Month": lambda d: d.month,
    "Date.Day": lambda d: d.day,
}


_SQL_TEXT = re.compile(r"'(?:[^']|'')*'")
_CAST_OF_A_COLUMN = re.compile(r'CAST\(("(?:[^"]|"")*") AS ([A-Z][A-Z0-9(), ]*)\)')


def _try_sql(run: _Run, node: Node, body: str, otherwise: Any) -> str:
    """`try <body> otherwise <otherwise>` for one row. M: the otherwise value when the body raises, the
    body's own value when it does not, so a null that is no error stays null. Two shapes, both exact:

        a conversion of a column     CASE WHEN c IS NULL THEN NULL ELSE COALESCE(TRY_CAST(c AS T), y) END
        anything else                CASE WHEN g IS NULL THEN y ELSE list_extract(g, 1) END
                                     g = TRY(list_transform([0], lambda duckpq_tried: x))

    g is null only when x raised: a null x gives [NULL], a list that is not null. x sits in a lambda because
    DuckDB (seen in 2.0.0) works a part of x that appears twice in the SELECT out once, OUTSIDE its TRY, where
    its error is not caught (`TRY(CAST(s AS DOUBLE) + CAST(s AS DOUBLE))` raises); a lambda's body is left
    whole. With `otherwise null` the same two, without their fallback."""
    bare = _SQL_TEXT.sub("''", body)
    if re.search(r"\berror\(", bare) or "(SELECT " in bare.upper():
        what = "an `error` of its own" if re.search(r"\berror\(", bare) else "another table's values"
        raise run.fail(node, f"Per row, try cannot hold {what}: DuckDB's TRY refuses it.", "try")
    cast = _CAST_OF_A_COLUMN.fullmatch(body)
    if cast:
        column, kind = cast.groups()
        tried = f"TRY_CAST({column} AS {kind})"
        if otherwise is None:
            return tried
        return f"CASE WHEN {column} IS NULL THEN NULL ELSE COALESCE({tried}, {run.sx(otherwise, node)}) END"
    tried = f"TRY(list_transform([0], lambda duckpq_tried: {body}))"
    if otherwise is None:
        return f"list_extract({tried}, 1)"
    return f"CASE WHEN {tried} IS NULL THEN {run.sx(otherwise, node)} ELSE list_extract({tried}, 1) END"


def _scalar(run: _Run, node: Node, name: str, args: list[Any]) -> Any:
    forms = _SCALARS[name]
    if len(args) not in forms:
        counts = " or ".join(str(n) for n in sorted(forms))
        raise run.fail(node, f"{name} takes {counts} values, not {len(args)}.", name)
    plain = not any(_symbolic(a) or isinstance(a, ColumnList) for a in args)
    if name in _PLAIN and plain and len(args) == min(forms):
        return None if args and args[0] is None else _PLAIN[name](*args)
    return Sx(forms[len(args)].format(*(run.sx(a, node) for a in args)))


def _comparer(run: _Run, node: Node, args: list[Any], at: int) -> bool:
    """Whether the optional comparer at `at` ignores case; any other comparer is refused."""
    if len(args) <= at or args[at] is None or args[at] == Tagged("Comparer.Ordinal"):
        return False
    if args[at] == Tagged("Comparer.OrdinalIgnoreCase"):
        return True
    raise run.fail(node, "Only Comparer.Ordinal and Comparer.OrdinalIgnoreCase are run.")


def _text_test(function: str) -> Callable[[_Run, Node, list[Any]], Any]:
    """Text.Contains, Text.StartsWith, Text.EndsWith: by case unless Comparer.OrdinalIgnoreCase is given."""

    def made(run: _Run, node: Node, args: list[Any]) -> Any:
        fold = _comparer(run, node, args, 2)
        text, part = (run.sx(a, node) for a in args[:2])
        if fold:
            text, part = f"lower({text})", f"lower({part})"
        return Sx(f"{function}({text}, {part})")

    return made


def _text_combine(run: _Run, node: Node, args: list[Any]) -> Any:
    separator = run.sx(args[1], node) if len(args) > 1 and args[1] is not None else "''"
    if isinstance(args[0], ColumnList):
        return args[0].aggregate("string_agg", f", {separator}")
    if not isinstance(args[0], list):
        raise run.fail(node, "Text.Combine needs a list of texts.", "Text.Combine")
    if not any(_symbolic(a) for a in args[0]) and not _symbolic(args[1] if len(args) > 1 else None):
        return (args[1] if len(args) > 1 and args[1] else "").join(str(a) for a in args[0] if a is not None)
    return Sx(f"concat_ws({separator}, {', '.join(run.sx(a, node) for a in args[0])})")


def _number_round(run: _Run, node: Node, args: list[Any]) -> Any:
    """Number.Round: halves to even unless RoundingMode says away from zero."""
    digits = run.sx(args[1], node) if len(args) > 1 and args[1] is not None else "0"
    mode = args[2] if len(args) > 2 else None
    if mode not in (None, 2, 4):  # RoundingMode.AwayFromZero = 2, ToEven = 4
        raise run.fail(
            node, "Number.Round runs with RoundingMode.ToEven or RoundingMode.AwayFromZero.", "Number.Round"
        )
    function = "round" if mode == 2 else "round_even"
    if not _symbolic(args[0]) and args[0] is not None and mode != 2 and digits.isdigit():
        return round(args[0], int(digits)) if int(digits) else round(args[0])
    return Sx(f"{function}({run.sx(args[0], node)}, {digits})")


def _hash_date(run: _Run, node: Node, args: list[Any]) -> Any:
    if any(_symbolic(a) for a in args):
        return Sx("make_date({}, {}, {})".format(*(run.sx(a, node) for a in args)))
    return dt.date(*args)


def _hash_datetime(run: _Run, node: Node, args: list[Any]) -> Any:
    if any(_symbolic(a) for a in args):
        return Sx("make_timestamp({}, {}, {}, {}, {}, {})".format(*(run.sx(a, node) for a in args)))
    year, month, day, hour, minute, second = args
    whole = int(second)
    return dt.datetime(year, month, day, hour, minute, whole, round((second - whole) * 1_000_000))


def _hash_duration(run: _Run, node: Node, args: list[Any]) -> Any:
    if any(_symbolic(a) for a in args):
        parts = [run.sx(a, node) for a in args]
        return Sx(
            f"(to_days({parts[0]}) + to_hours({parts[1]}) + to_minutes({parts[2]}) + to_seconds({parts[3]}))"
        )
    return dt.timedelta(days=args[0], hours=args[1], minutes=args[2], seconds=args[3])


def _value_is(run: _Run, node: Node, args: list[Any]) -> Any:
    if not isinstance(args[1], MType):
        raise run.fail(node, "Value.Is needs a type: Value.Is([Amount], type number).", "Value.Is")
    return _is_type(run, node, args[0], args[1])


_AGGREGATES: dict[str, str] = {
    "List.Sum": "sum", "List.Count": "count", "List.NonNullCount": "count", "List.Average": "avg",
    "List.Max": "max", "List.Min": "min", "List.Median": "median", "List.StandardDeviation": "stddev_samp",
    "List.First": "first", "List.Last": "last", "List.Product": "product",
}  # fmt: skip


def _plain_aggregate(name: str, items: list[Any]) -> Any:
    kept = [v for v in items if v is not None]
    if name == "List.Count":
        return len(items)
    if name == "List.NonNullCount":
        return len(kept)
    if name in ("List.First", "List.Last"):
        return (items[0] if name == "List.First" else items[-1]) if items else None
    if not kept:
        return None
    if name == "List.Sum":
        return sum(kept)
    if name == "List.Average":
        return sum(kept) / len(kept)
    if name == "List.Product":
        return math.prod(kept)
    if name in ("List.Max", "List.Min"):
        return max(kept) if name == "List.Max" else min(kept)
    raise ValueError(name)


def _aggregate(name: str) -> Callable[[_Run, Node, list[Any]], Any]:
    """List.Sum and its kind: over a column an SQL aggregate, over a plain list its value."""

    def made(run: _Run, node: Node, args: list[Any]) -> Any:
        if isinstance(args[0], ColumnList):
            if name == "List.Count" and not args[0].distinct:
                return ColumnList("*", args[0].table).aggregate("count")  # M counts the nulls too
            return args[0].aggregate(_AGGREGATES[name])
        if isinstance(args[0], list) and any(_symbolic(a) for a in args[0]):
            items = ", ".join(run.sx(a, node) for a in args[0])
            if name in ("List.Max", "List.Min"):
                return Sx(f"{'greatest' if name == 'List.Max' else 'least'}({items})")
            return Sx(f"list_aggregate([{items}], {text_sql(_AGGREGATES[name])})")
        if not isinstance(args[0], list):
            raise run.fail(node, f"{name} needs a list or a table's column.", name)
        return _plain_aggregate(name, args[0])

    return made


def _list_distinct(run: _Run, node: Node, args: list[Any]) -> Any:
    if isinstance(args[0], ColumnList):
        return ColumnList(args[0].expr, args[0].table, True)
    seen: list[Any] = []
    for item in args[0]:
        if not any(_same(item, s) for s in seen):
            seen.append(item)
    return seen


def _list_contains(run: _Run, node: Node, args: list[Any]) -> Any:
    items, value = args[0], args[1]
    if isinstance(items, ColumnList) and items.table is not None:
        return Sx(f"coalesce({run.sx(value, node)} IN ({items.values_sql()}), FALSE)")
    if not isinstance(items, list):
        raise run.fail(node, "List.Contains needs a list or a table's column.", "List.Contains")
    if not _symbolic(value) and not any(_symbolic(i) for i in items):
        return any(_same(value, i) for i in items)
    sql = run.sx(value, node)
    listed = ", ".join(run.sx(i, node) for i in items if i is not None)
    null = f" OR {sql} IS NULL" if any(i is None for i in items) else ""
    return Sx(f"(coalesce({sql} IN ({listed}), FALSE){null})" if listed else f"(FALSE{null})")


def _list_transform(run: _Run, node: Node, args: list[Any]) -> Any:
    return [run.apply(args[1], [item], node) for item in run.plain(args[0], node, "A plain list")]


def _list_select(run: _Run, node: Node, args: list[Any]) -> Any:
    return [
        item for item in run.plain(args[0], node, "A plain list") if run.apply(args[1], [item], node) is True
    ]


def _record_field(run: _Run, node: Node, args: list[Any]) -> Any:
    optional = len(args) > 2
    found = run.field(args[0], str(args[1]), optional, node)
    return args[2] if optional and found is None else found


# ===== the table functions =====

_JOINS: dict[int, str] = {0: "INNER JOIN", 1: "LEFT JOIN", 2: "RIGHT JOIN", 3: "FULL JOIN"}
_ROW = '"__duckpq_row"'


def _names(run: _Run, node: Node, value: Any, what: str = "A column's name") -> list[str]:
    """One name or a list of names, as plain texts."""
    plain = run.plain(value, node, what)
    found = [plain] if isinstance(plain, str) else plain
    if not isinstance(found, list) or not all(isinstance(n, str) for n in found):
        raise run.fail(node, f"{what} is a text, or a list of texts.")
    return found


def _pairs(run: _Run, node: Node, value: Any, what: str) -> list[list[Any]]:
    """{{a, b}, {c, d}} or one {a, b}."""
    if isinstance(value, list) and value and not isinstance(value[0], list):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(p, list) and len(p) >= 2 for p in value):
        raise run.fail(node, f'{what} is a list of pairs: {{{{"a", ...}}, {{"b", ...}}}}.')
    return value


def _whole(run: _Run, node: Node, value: Any, what: str) -> int:
    plain = run.plain(value, node, what)
    if isinstance(plain, bool) or not isinstance(plain, int) or plain < 0:
        raise run.fail(node, f"{what} is a whole number, 0 or more.")
    return plain


def _select(
    table: Table, items: Sequence[tuple[str, str]], keep: Iterable[str] = (), tail: str = ""
) -> Table:
    """SELECT each (expression, name) FROM the table; a nested column named in `keep` stays (it has no SQL)."""
    keep = set(keep)
    parts = [e if e == q(n) else f"{e} AS {q(n)}" for e, n in items if n not in table.nested]
    names = [n for _, n in items if n not in table.nested or n in keep]
    text = f"SELECT {', '.join(parts) or 'NULL'} FROM {table.source()}{tail}"
    return raw(text, cols(names, table.columns), table, keep)


def _same_rows(table: Table, tail: str) -> Table:
    """The same columns, with something after the FROM (ORDER BY, LIMIT)."""
    return raw(f"SELECT * FROM {table.source()}{tail}", table.columns, table, table.nested)


def _cast(sql: str, kind: Any, run: _Run, node: Node) -> str:
    if kind is None:
        return sql
    if not isinstance(kind, MType):
        raise run.fail(node, "A type is expected here (type text, Int64.Type...).")
    duck = duck_type(kind, node)
    return sql if duck is None else f"CAST({sql} AS {duck})"


def _select_rows(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    test = run.apply(args[1], [RowRef(table.columns)], node)
    if isinstance(test, Unknown):
        return _open_table()
    where = f"({run.sx(test, node)})"
    if table.text is None:
        made = Table(table.columns, table.base, table.picks, [*table.wheres, where])
        made.nested, made.promotable = dict(table.nested), table.promotable
        return made
    return _same_rows(table, f" WHERE {where}")


def _missing(args: list[Any], at: int) -> int:
    """The MissingField argument: 0 Error, 1 Ignore, 2 UseNull."""
    return args[at] if len(args) > at and isinstance(args[at], int) else 0


def _select_columns(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    names, missing = _names(run, node, args[1]), _missing(args, 2)
    if missing == 1:
        names = [n for n in names if n in table.columns]
    elif missing == 0:
        _need(run, node, table.columns, names)
    if table.text is None and all(n in table.columns for n in names) and not table.nested:
        made = Table(cols(names, table.columns), table.base, list(names), list(table.wheres))
        made.promotable = table.promotable
        return made
    items = [(q(n) if n in table.columns else "NULL", n) for n in names]
    return _select(table, items, keep=names)


def _remove_columns(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    names = _names(run, node, args[1])
    if _missing(args, 2) == 0:
        _need(run, node, table.columns, names)
    for name in names:
        if name in table.nested:
            table = _drop_nested(run, node, table, name)
    left = [c for c in table.columns if c not in names]
    made = _select_columns(run, node, [table, left]) if not table.columns.open else table
    return made


def _drop_nested(run: _Run, node: Node, table: Table, name: str) -> Table:
    """A nested join's column removed before it was expanded: the join only filters (inner, anti) or does
    nothing (left outer)."""
    nested = table.nested[name]
    rest = {k: v for k, v in table.nested.items() if k != name}
    columns = cols([c for c in table.columns if c != name], table.columns)
    if nested.kind == 1:
        made = raw(table.sql(), columns, table, rest)
    elif nested.kind in (0, 4):
        test = " AND ".join(
            f"l.{q(a)} IS NOT DISTINCT FROM r.{q(b)}"
            for a, b in zip(nested.keys, nested.other_keys, strict=True)
        )
        exists = f"{'NOT ' if nested.kind == 4 else ''}EXISTS (SELECT 1 FROM {nested.other.source('r')} WHERE {test})"
        real = ", ".join(f"l.{q(c)}" for c in columns if c not in rest)
        made = raw(f"SELECT {real} FROM {table.source('l')} WHERE {exists}", columns, table, rest)
    else:
        raise run.fail(node, f"Expand {name} before removing it: a right or full join adds rows.", name)
    made.nested = rest
    return made


def _rename_columns(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    renames = {str(a): str(b) for a, b, *_ in _pairs(run, node, run.plain(args[1], node), "The renames")}
    if _missing(args, 2) == 0:
        _need(run, node, table.columns, renames)
    names = [renames.get(c, c) for c in table.columns]
    twice = next((n for n in names if names.count(n) > 1), None)
    if twice is not None:
        raise run.fail(node, f"The rename would make two columns named {twice}.", twice)
    made = _select(table, [(q(c), renames.get(c, c)) for c in table.columns], keep=table.nested)
    made.nested = {renames.get(k, k): v for k, v in table.nested.items()}
    made.columns = cols(names, table.columns)
    return made


def _reorder_columns(run: _Run, node: Node, args: list[Any]) -> Any:
    """Table.ReorderColumns: the named columns take, in the order given, the places they held between them;
    the others stay where they are."""
    table = run.table(args[0], node)
    names = _names(run, node, args[1])
    if _missing(args, 2) == 1:
        names = [n for n in names if n in table.columns]
    _need(run, node, table.columns, names)
    if table.columns.open:
        return table
    places = sorted(table.columns.index(n) for n in names)
    order = list(table.columns)
    for place, name in zip(places, names, strict=True):
        order[place] = name
    return _select(table, [(q(c), c) for c in order], keep=table.nested)


def _transform_column_types(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    kinds = {str(run.plain(a, node)): b for a, b, *_ in _pairs(run, node, args[1], "The types")}
    _need(run, node, table.columns, kinds)
    items = [(_cast(q(c), kinds[c], run, node) if c in kinds else q(c), c) for c in table.columns]
    return _select(table, items, keep=table.nested)


def _add_column(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    name = str(run.plain(args[1], node, "The new column's name"))
    if name in table.columns and not table.columns.open:
        raise run.fail(node, f"The table already has a column named {name}.", name)
    value = run.apply(args[2], [RowRef(table.columns)], node)
    if isinstance(value, Unknown):
        return _open_table()
    sql = _cast(run.sx(value, node), args[3] if len(args) > 3 else None, run, node)
    return _select(table, [*((q(c), c) for c in table.columns), (sql, name)], keep=table.nested)


def _duplicate_column(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    old, new = str(run.plain(args[1], node)), str(run.plain(args[2], node))
    _need(run, node, table.columns, [old])
    sql = _cast(q(old), args[3] if len(args) > 3 else None, run, node)
    return _select(table, [*((q(c), c) for c in table.columns), (sql, new)], keep=table.nested)


def _transform_columns(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    changes: dict[str, str] = {}
    for name, function, *more in _pairs(run, node, args[1], "The transformations"):
        column = str(run.plain(name, node))
        _need(run, node, table.columns, [column])
        value = run.apply(function, [Sx(q(column))], node)
        if isinstance(value, Unknown):
            return _open_table()
        changes[column] = _cast(run.sx(value, node), more[0] if more else None, run, node)
    return _select(table, [(changes.get(c, q(c)), c) for c in table.columns], keep=table.nested)


def _replace_value(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    old, new, replacer = args[1], args[2], args[3]
    names = _names(run, node, args[4])
    _need(run, node, table.columns, names)
    row = RowRef(table.columns)
    old = run.apply(old, [row], node) if isinstance(old, Closure) else old
    new = run.apply(new, [row], node) if isinstance(new, Closure) else new
    a, b = run.sx(old, node), run.sx(new, node)
    if replacer == Builtin("Replacer.ReplaceText"):
        made = {n: f"replace({q(n)}, {a}, {b})" for n in names}
    elif replacer == Builtin("Replacer.ReplaceValue"):
        made = {n: f"CASE WHEN {q(n)} IS NOT DISTINCT FROM {a} THEN {b} ELSE {q(n)} END" for n in names}
    else:
        raise run.fail(node, "Table.ReplaceValue runs with Replacer.ReplaceValue or Replacer.ReplaceText.")
    return _select(table, [(made.get(c, q(c)), c) for c in table.columns], keep=table.nested)


def _numbered(table: Table) -> str:
    """The table with its rows numbered in the order they come (what "the row above" means)."""
    return f"(SELECT *, row_number() OVER () AS {_ROW} FROM {table.source()}) AS t"


def _fill(direction: str) -> Callable[[_Run, Node, list[Any]], Any]:
    def made(run: _Run, node: Node, args: list[Any]) -> Any:
        table = run.table(args[0], node)
        names = _names(run, node, args[1])
        _need(run, node, table.columns, names)
        frame = (
            f"last_value({{0}} IGNORE NULLS) OVER (ORDER BY {_ROW} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)"
            if direction == "down"
            else f"first_value({{0}} IGNORE NULLS) OVER (ORDER BY {_ROW} ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING)"
        )
        items = [
            (frame.format(q(c)) if c in names else q(c), c) for c in table.columns if c not in table.nested
        ]
        listed = ", ".join(f"{e} AS {q(n)}" for e, n in items)
        text = f"SELECT {listed} FROM {_numbered(table)} ORDER BY {_ROW}"
        return raw(text, cols([n for _, n in items], table.columns), table)

    return made


def _distinct(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    if len(args) < 2 or args[1] is None:
        real = ", ".join(q(c) for c in table.columns if c not in table.nested) or "*"
        return raw(f"SELECT DISTINCT {real} FROM {table.source()}", table.columns, table)
    names = _names(run, node, args[1])
    _need(run, node, table.columns, names)
    real = ", ".join(q(c) for c in table.columns if c not in table.nested)
    keys = ", ".join(q(n) for n in names)
    text = (
        f"SELECT {real} FROM {_numbered(table)} "
        f"QUALIFY row_number() OVER (PARTITION BY {keys} ORDER BY {_ROW}) = 1 ORDER BY {_ROW}"
    )
    return raw(text, table.columns, table)


def _sort(run: _Run, node: Node, args: list[Any]) -> Any:
    """Table.Sort: text by its code points and case, null first going up (and last going down), as M."""
    table = run.table(args[0], node)
    wanted = run.plain(args[1], node, "The sort")
    if isinstance(wanted, str):
        wanted = [wanted]
    if (
        isinstance(wanted, list)
        and len(wanted) == 2
        and isinstance(wanted[0], str)
        and isinstance(wanted[1], int)
    ):
        wanted = [wanted]
    order: list[str] = []
    for item in wanted if isinstance(wanted, list) else [None]:
        name, down = (
            (item, 0)
            if isinstance(item, str)
            else (item[0], item[1])
            if isinstance(item, list)
            else (None, 0)
        )
        if not isinstance(name, str):
            raise run.fail(node, 'Table.Sort takes {"a"} or {{"a", Order.Descending}, ...}.', "Table.Sort")
        _need(run, node, table.columns, [name])
        order.append(f"{q(name)} DESC NULLS LAST" if down == 1 else f"{q(name)} ASC NULLS FIRST")
    return _same_rows(table, " ORDER BY " + ", ".join(order))


def _first_n(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    if isinstance(args[1], Closure | Builtin):
        raise run.fail(node, "Table.FirstN takes a count here, not a condition.", "Table.FirstN")
    return _same_rows(table, f" LIMIT {_whole(run, node, args[1], 'The count')}")


def _skip(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    count = _whole(run, node, args[1], "The count") if len(args) > 1 and args[1] is not None else 1
    return _same_rows(table, f" OFFSET {count}")


def _range(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    limit = (
        f" LIMIT {_whole(run, node, args[2], 'The count')}" if len(args) > 2 and args[2] is not None else ""
    )
    return _same_rows(table, f"{limit} OFFSET {_whole(run, node, args[1], 'The offset')}")


def _group(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    keys = _names(run, node, args[1])
    _need(run, node, table.columns, keys)
    if len(args) > 3 and args[3] not in (None, 1):  # GroupKind.Global = 1
        raise run.fail(node, "Table.Group runs with GroupKind.Global (the default).", "Table.Group")
    items = [(q(k), k) for k in keys]
    for name, function, *more in _pairs(run, node, args[2], "The aggregations"):
        value = run.apply(function, [GroupRows(table.columns)], node)
        if isinstance(value, Unknown):
            return _open_table()
        if not isinstance(value, Sx):
            raise run.fail(
                node,
                f"{name}: a group's rows as a nested table are not run. Aggregate them (List.Sum, Table.RowCount).",
                str(name),
            )
        items.append((_cast(value.sql, more[0] if more else None, run, node), str(run.plain(name, node))))
    by = " GROUP BY " + ", ".join(q(k) for k in keys) if keys else ""
    made = _select(Table(table.columns, base=table.source()), items, tail=by)
    return made


def _row_count(run: _Run, node: Node, args: list[Any]) -> Any:
    if isinstance(args[0], GroupRows):
        return Sx("count(*)")
    return Sx(f"(SELECT count(*) FROM {run.table(args[0], node).source()})")


def _join_sql(
    left: Table, right: Table, keys: Sequence[str], other: Sequence[str], kind: int,
    left_items: Sequence[tuple[str, str]], right_items: Sequence[tuple[str, str]],
) -> str:  # fmt: skip
    """One join: `left_items` and `right_items` are (column, name as) of each side. Keys match as M matches
    them (null equals null)."""
    on = " AND ".join(f"l.{q(a)} IS NOT DISTINCT FROM r.{q(b)}" for a, b in zip(keys, other, strict=True))
    one = [f"l.{q(c)} AS {q(n)}" for c, n in left_items]
    two = [f"r.{q(c)} AS {q(n)}" for c, n in right_items]
    if kind in _JOINS:
        listed = ", ".join(one + two)
        return f"SELECT {listed} FROM {left.source('l')} {_JOINS[kind]} {right.source('r')} ON {on}"
    if kind == 4:  # left anti: the left rows with no match, the right's columns null
        listed = ", ".join(one + [f"NULL AS {q(n)}" for _, n in right_items])
        return f"SELECT {listed} FROM {left.source('l')} WHERE NOT EXISTS (SELECT 1 FROM {right.source('r')} WHERE {on})"
    listed = ", ".join([f"NULL AS {q(n)}" for _, n in left_items] + two)
    return f"SELECT {listed} FROM {right.source('r')} WHERE NOT EXISTS (SELECT 1 FROM {left.source('l')} WHERE {on})"


def _join_kind(run: _Run, node: Node, args: list[Any], at: int, default: int) -> int:
    kind = args[at] if len(args) > at and args[at] is not None else default
    if not isinstance(kind, int) or not 0 <= kind <= 5:
        raise run.fail(
            node,
            "The join's kind is one of JoinKind.Inner, LeftOuter, RightOuter, FullOuter, LeftAnti, RightAnti.",
        )
    return kind


def _join_sides(run: _Run, node: Node, args: list[Any]) -> tuple[Table, list[str], Table, list[str]]:
    left, right = run.table(args[0], node), run.table(args[2], node)
    keys, other = _names(run, node, args[1], "A key"), _names(run, node, args[3], "A key")
    _need(run, node, left.columns, keys)
    _need(run, node, right.columns, other)
    if len(keys) != len(other):
        raise run.fail(node, f"The join names {len(keys)} keys on one side and {len(other)} on the other.")
    for side in (left, right):
        if side.nested:
            raise run.fail(
                node, f"Expand {next(iter(side.nested))} before joining again.", next(iter(side.nested))
            )
    return left, keys, right, other


def _nested_join(run: _Run, node: Node, args: list[Any]) -> Any:
    left, keys, right, other = _join_sides(run, node, args)
    name = str(run.plain(args[4], node, "The new column's name"))
    made = raw(left.sql(), cols([*left.columns, name], left.columns), left)
    made.nested = {name: Nested(right, tuple(keys), tuple(other), _join_kind(run, node, args, 5, 1))}
    return made


def _expand_table_column(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    name = str(run.plain(args[1], node))
    if table.columns.open:
        return _open_table()
    if name not in table.nested:
        raise run.fail(
            node, f"{name} is not a nested table's column here (Table.NestedJoin makes one).", name
        )
    nested = table.nested[name]
    picked = _names(run, node, args[2])
    named = _names(run, node, args[3]) if len(args) > 3 and args[3] is not None else picked
    _need(run, node, nested.other.columns, picked)
    if len(named) != len(picked):
        raise run.fail(node, "Table.ExpandTableColumn's new names are as many as its columns.")
    at = table.columns.index(name)
    real = [c for c in table.columns if c not in table.nested]
    taken = next((n for n in named if n in real), None)
    if taken is not None:
        raise run.fail(
            node, f"The table already has a column named {taken}: give the expanded one a new name.", taken
        )
    left = Table(cols(real), text=table.sql())
    text = _join_sql(left, nested.other, nested.keys, nested.other_keys, nested.kind,
                     [(c, c) for c in real], list(zip(picked, named, strict=True)))  # fmt: skip
    order = [*table.columns[:at], *named, *table.columns[at + 1 :]]
    order = [c for c in order if c not in table.nested]
    listed = ", ".join(q(c) for c in order)
    return raw(f"SELECT {listed} FROM ({text}) AS t", cols(order))


def _join(run: _Run, node: Node, args: list[Any]) -> Any:
    left, keys, right, other = _join_sides(run, node, args)
    both = next((c for c in left.columns if c in right.columns), None)
    if both is not None and not (left.columns.open or right.columns.open):
        raise run.fail(node, f"Both tables have a column named {both}: rename one before Table.Join.", both)
    text = _join_sql(left, right, keys, other, _join_kind(run, node, args, 4, 0),
                     [(c, c) for c in left.columns], [(c, c) for c in right.columns])  # fmt: skip
    return raw(text, cols([*left.columns, *right.columns], left.columns))


def _combine(run: _Run, node: Node, args: list[Any]) -> Any:
    """Table.Combine: by column name; a column a table lacks is null there."""
    if not isinstance(args[0], list) or not args[0]:
        raise run.fail(node, "Table.Combine needs a list of tables.", "Table.Combine")
    tables = [run.table(t, node) for t in args[0]]
    if any(t.columns.open for t in tables):
        return _open_table()
    names: list[str] = []
    for table in tables:
        names.extend(c for c in table.columns if c not in names and c not in table.nested)
    parts = []
    for table in tables:
        listed = ", ".join(q(n) if n in table.columns else f"NULL AS {q(n)}" for n in names)
        parts.append(f"SELECT {listed} FROM {table.source()}")
    return raw(" UNION ALL ".join(parts), cols(names))


def _promote_headers(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    if table.promotable:  # read with its first row as the header already: nothing more to do
        return Table(table.columns, table.base, table.picks, list(table.wheres), table.text)
    if table.rows is not None and table.rows:
        names = ["" if v is None else str(v) for v in table.rows[0]]
        return _literal_table(run, node, names, table.rows[1:], None)
    if table.columns.open:
        return table
    raise run.fail(
        node,
        "Table.PromoteHeaders runs on a file's or a sheet's table, or on a #table: elsewhere the column names "
        "would depend on the rows.",
        "Table.PromoteHeaders",
    )


def _unpivot(others: bool) -> Callable[[_Run, Node, list[Any]], Any]:
    def made(run: _Run, node: Node, args: list[Any]) -> Any:
        table = run.table(args[0], node)
        named = _names(run, node, args[1])
        attribute, value = str(run.plain(args[2], node)), str(run.plain(args[3], node))
        _need(run, node, table.columns, named)
        if table.columns.open:
            return _open_table()
        real = [c for c in table.columns if c not in table.nested]
        kept = [c for c in real if c in named] if others else [c for c in real if c not in named]
        turned = [c for c in real if c not in kept]
        if not turned:
            raise run.fail(node, "No column is left to unpivot.")
        listed = "".join(f"{q(c)}, " for c in kept)
        parts = [
            f'SELECT {listed}{text_sql(c)} AS {q(attribute)}, {q(c)} AS {q(value)}, {_ROW}, {i} AS "__duckpq_at" '
            f"FROM {_numbered(table)} WHERE {q(c)} IS NOT NULL"
            for i, c in enumerate(turned)
        ]
        out = [*kept, attribute, value]
        text = (
            f"SELECT {', '.join(q(c) for c in out)} FROM ({' UNION ALL '.join(parts)}) AS u "
            f'ORDER BY {_ROW}, "__duckpq_at"'
        )
        return raw(text, cols(out))

    return made


def _pivot(run: _Run, node: Node, args: list[Any]) -> Any:
    """Table.Pivot: one column per value of the list (a column's distinct values are read first)."""
    table = run.table(args[0], node)
    values = run.plain(args[1], node, "The pivot's values")
    attribute, value = str(run.plain(args[2], node)), str(run.plain(args[3], node))
    _need(run, node, table.columns, [attribute, value])
    if isinstance(values, Unknown) or table.columns.open:
        return _open_table()
    function = args[4] if len(args) > 4 and args[4] is not None else Builtin("List.Max")
    others = [c for c in table.columns if c not in (attribute, value) and c not in table.nested]
    items = [(q(c), c) for c in others]
    for item in values:
        if item is None:
            continue
        mine = f"CASE WHEN {q(attribute)} IS NOT DISTINCT FROM {run.sx(item, node)} THEN {q(value)} END"
        made = run.apply(function, [ColumnList(mine)], node)
        items.append((run.sx(made, node), item if isinstance(item, str) else str(item)))
    by = " GROUP BY " + ", ".join(q(c) for c in others) if others else ""
    return _select(Table(table.columns, base=table.source()), items, tail=by)


def _split_column(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    name = str(run.plain(args[1], node))
    _need(run, node, table.columns, [name])
    splitter = args[2]
    if not isinstance(splitter, Tagged) or splitter.kind != "Splitter.SplitTextByDelimiter":
        raise run.fail(
            node, "Table.SplitColumn runs with Splitter.SplitTextByDelimiter.", "Table.SplitColumn"
        )
    into = run.plain(args[3], node) if len(args) > 3 else None
    if isinstance(into, int) and not isinstance(into, bool):
        into = [f"{name}.{i + 1}" for i in range(into)]
    if not isinstance(into, list) or not into:
        raise run.fail(
            node, "Table.SplitColumn needs the new columns' names, or how many: the rows cannot say."
        )
    delimiter = run.sx(splitter.args[0], node)
    made = [(f"list_extract(string_split(CAST({q(name)} AS VARCHAR), {delimiter}), {i + 1})", str(n))
            for i, n in enumerate(into)]  # fmt: skip
    items: list[tuple[str, str]] = []
    for column in table.columns:
        items.extend(made if column == name else [(q(column), column)])
    return _select(table, items, keep=table.nested)


def _add_index_column(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    name = str(run.plain(args[1], node))
    start = run.plain(args[2], node) if len(args) > 2 and args[2] is not None else 0
    step = run.plain(args[3], node) if len(args) > 3 and args[3] is not None else 1
    sql = f"({start} + (row_number() OVER () - 1) * {step})"
    return _select(table, [*((q(c), c) for c in table.columns), (sql, name)], keep=table.nested)


def _prefix_columns(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    prefix = str(run.plain(args[1], node))
    return _select(table, [(q(c), f"{prefix}.{c}") for c in table.columns])


def _column(run: _Run, node: Node, args: list[Any]) -> Any:
    return run.field(run.table(args[0], node), str(run.plain(args[1], node)), False, node)


def _column_names(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    return UNKNOWN if table.columns.open else [c for c in table.columns if c not in table.nested]


def _has_columns(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    return UNKNOWN if table.columns.open else all(n in table.columns for n in _names(run, node, args[1]))


def _is_empty(run: _Run, node: Node, args: list[Any]) -> Any:
    return Sx(f"(NOT EXISTS (SELECT 1 FROM {run.table(args[0], node).source()}))")


# ----- tables written out: #table, Table.FromRecords, Table.FromRows, Table.FromList -----


def _literal_table(
    run: _Run,
    node: Node,
    names: Sequence[str],
    rows: Sequence[Sequence[Any]],
    kinds: Sequence[MType | None] | None,
) -> Table:
    """Rows written in the query as a VALUES list; a typed column is cast."""
    casts = [duck_type(k, node) if k is not None else None for k in (kinds or [None] * len(names))]
    for row in rows:
        if len(row) != len(names):
            raise run.fail(node, f"A row has {len(row)} values where the table has {len(names)} columns.")
    listed = ", ".join(q(n) for n in names)
    if rows:
        lines = ", ".join("(" + ", ".join(run.sx(v, node) for v in row) + ")" for row in rows)
        inner = f"(VALUES {lines}) AS v({listed})"
        picked = ", ".join(
            f"CAST({q(n)} AS {c}) AS {q(n)}" if c else q(n) for n, c in zip(names, casts, strict=True)
        )
        text = f"SELECT {picked} FROM {inner}"
    else:
        picked = ", ".join(
            f"CAST(NULL AS {c or 'VARCHAR'}) AS {q(n)}" for n, c in zip(names, casts, strict=True)
        )
        text = f"SELECT {picked} WHERE FALSE"
    made = raw(text, cols(names))
    made.rows = [list(r) for r in rows]
    return made


def _hash_table(run: _Run, node: Node, args: list[Any]) -> Any:
    columns, rows = args[0], run.plain(args[1], node, "The table's rows") if len(args) > 1 else []
    kinds: list[MType | None] | None = None
    if isinstance(columns, MType) and columns.fields is not None:
        names, kinds = [n for n, _ in columns.fields], [k for _, k in columns.fields]
    elif isinstance(columns, int) and not isinstance(columns, bool):
        names = [f"Column{i + 1}" for i in range(columns)]
    else:
        names = _names(run, node, columns, "#table's columns")
    if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
        raise run.fail(node, '#table\'s rows are a list of lists: {{1, "a"}, {2, "b"}}.', "#table")
    return _literal_table(run, node, names, rows, kinds)


def _from_records(run: _Run, node: Node, args: list[Any]) -> Any:
    records = args[0]
    if isinstance(records, JsonRoot):
        source = run.context.source(node, "Json.Document", arguments=(records.path,), path=records.path)
        return _source_table(run, node, source)
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise run.fail(node, "Table.FromRecords needs a list of records.", "Table.FromRecords")
    names: list[str] = []
    for record in records:
        names.extend(k for k in record if k not in names)
    return _literal_table(run, node, names, [[r.get(n) for n in names] for r in records], None)


def _from_rows(run: _Run, node: Node, args: list[Any]) -> Any:
    rows = run.plain(args[0], node, "The rows")
    columns = args[1] if len(args) > 1 else None
    width = len(rows[0]) if rows else 0
    return _hash_table(run, node, [columns if columns is not None else width, rows])


def _from_list(run: _Run, node: Node, args: list[Any]) -> Any:
    items = args[0]
    if not isinstance(items, list):
        raise run.fail(node, "Table.FromList needs a list.", "Table.FromList")
    names = _names(run, node, args[2]) if len(args) > 2 and args[2] is not None else ["Column1"]
    if all(isinstance(i, dict) for i in items) and items:
        made = Table(cols(names), text="SELECT NULL WHERE FALSE", rows=[[i] for i in items])
        made.record_file = items.path if isinstance(items, JsonRoot) else None
        return made
    return _literal_table(run, node, names, [[i] for i in items], None)


def _expand_record_column(run: _Run, node: Node, args: list[Any]) -> Any:
    table = run.table(args[0], node)
    name = str(run.plain(args[1], node))
    fields = _names(run, node, args[2])
    named = _names(run, node, args[3]) if len(args) > 3 and args[3] is not None else fields
    if table.columns.open:
        return _open_table()
    if table.rows is None or len(table.columns) != 1 or table.columns[0] != name:
        raise run.fail(node, "Table.ExpandRecordColumn runs on a list of records made a table (Table.FromList).",
                       "Table.ExpandRecordColumn")  # fmt: skip
    if table.record_file is not None:
        source = run.context.source(
            node, "Json.Document", arguments=(table.record_file,), path=table.record_file
        )
        whole = _source_table(run, node, source)
        if whole.columns.open:
            return whole
        return _select(
            whole, [(q(f) if f in whole.columns else "NULL", n) for f, n in zip(fields, named, strict=True)]
        )
    rows = [[row[0].get(f) if isinstance(row[0], dict) else None for f in fields] for row in table.rows]
    return _literal_table(run, node, named, rows, None)


# ===== the library: every function and constant by its M name =====


def _same_table(run: _Run, node: Node, args: list[Any]) -> Any:
    return run.table(args[0], node)


def _tagged(kind: str) -> Callable[[_Run, Node, list[Any]], Any]:
    return lambda run, node, args: Tagged(kind, tuple(args))


_FUNCTIONS: dict[str, Callable[[_Run, Node, list[Any]], Any]] = {
    # sources
    "File.Contents": _file_contents,
    "Csv.Document": _csv_document,
    "Parquet.Document": _parquet_document,
    "Json.Document": _json_document,
    "Excel.Workbook": _excel_workbook,
    "Value.NativeQuery": _native_query,
    **{
        name: _database(name)
        for name in (
            "Sql.Database",
            "Sql.Databases",
            "PostgreSQL.Database",
            "MySQL.Database",
            "Snowflake.Databases",
            "Oracle.Database",
            "Databricks.Catalogs",
            "CommonDataService.Database",
        )
    },
    # tables
    "Table.SelectRows": _select_rows,
    "Table.SelectColumns": _select_columns,
    "Table.RemoveColumns": _remove_columns,
    "Table.RenameColumns": _rename_columns,
    "Table.ReorderColumns": _reorder_columns,
    "Table.TransformColumnTypes": _transform_column_types,
    "Table.AddColumn": _add_column,
    "Table.DuplicateColumn": _duplicate_column,
    "Table.TransformColumns": _transform_columns,
    "Table.ReplaceValue": _replace_value,
    "Table.FillDown": _fill("down"),
    "Table.FillUp": _fill("up"),
    "Table.Distinct": _distinct,
    "Table.Sort": _sort,
    "Table.FirstN": _first_n,
    "Table.Skip": _skip,
    "Table.RemoveFirstN": _skip,
    "Table.Range": _range,
    "Table.Group": _group,
    "Table.RowCount": _row_count,
    "Table.NestedJoin": _nested_join,
    "Table.AddJoinColumn": _nested_join,
    "Table.ExpandTableColumn": _expand_table_column,
    "Table.Join": _join,
    "Table.Combine": _combine,
    "Table.PromoteHeaders": _promote_headers,
    "Table.UnpivotOtherColumns": _unpivot(True),
    "Table.Unpivot": _unpivot(False),
    "Table.Pivot": _pivot,
    "Table.SplitColumn": _split_column,
    "Table.AddIndexColumn": _add_index_column,
    "Table.PrefixColumns": _prefix_columns,
    "Table.Column": _column,
    "Table.ColumnNames": _column_names,
    "Table.HasColumns": _has_columns,
    "Table.IsEmpty": _is_empty,
    "Table.Buffer": _same_table,
    "Table.StopFolding": _same_table,
    "Table.AddKey": _same_table,
    "Table.FromRecords": _from_records,
    "Table.FromRows": _from_rows,
    "Table.FromList": _from_list,
    "Table.ExpandRecordColumn": _expand_record_column,
    "#table": _hash_table,
    # values
    "#date": _hash_date,
    "#datetime": _hash_datetime,
    "#duration": _hash_duration,
    "Text.Contains": _text_test("contains"),
    "Text.StartsWith": _text_test("starts_with"),
    "Text.EndsWith": _text_test("ends_with"),
    "Text.Combine": _text_combine,
    "Number.Round": _number_round,
    "Value.Is": _value_is,
    **{name: _aggregate(name) for name in _AGGREGATES},
    "List.Distinct": _list_distinct,
    "List.Contains": _list_contains,
    "List.Transform": _list_transform,
    "List.Select": _list_select,
    "List.Buffer": lambda run, node, args: args[0],
    "Record.Field": _record_field,
    "Record.FieldOrDefault": _record_field,
    "Splitter.SplitTextByDelimiter": _tagged("Splitter.SplitTextByDelimiter"),
    "Splitter.SplitByNothing": _tagged("Splitter.SplitByNothing"),
    # named only (an argument of another function)
    "Replacer.ReplaceValue": _tagged("Replacer.ReplaceValue"),
    "Replacer.ReplaceText": _tagged("Replacer.ReplaceText"),
}
_ENUMS: dict[str, tuple[str, ...]] = {
    "Order": ("Ascending", "Descending"),
    "JoinKind": ("Inner", "LeftOuter", "RightOuter", "FullOuter", "LeftAnti", "RightAnti"),
    "MissingField": ("Error", "Ignore", "UseNull"),
    "GroupKind": ("Local", "Global"),
    "RoundingMode": ("Up", "Down", "AwayFromZero", "TowardZero", "ToEven"),
    "ExtraValues": ("List", "Error", "Ignore"),
    "QuoteStyle": ("None", "Csv"),
    "Occurrence": ("First", "Last", "All"),
    "JoinAlgorithm": (
        "Dynamic",
        "PairwiseHash",
        "SortMerge",
        "LeftHash",
        "RightHash",
        "LeftIndex",
        "RightIndex",
    ),
}
_CONSTANTS: dict[str, Any] = {
    **{f"{space}.{name}": at for space, names in _ENUMS.items() for at, name in enumerate(names)},
    "Comparer.Ordinal": Tagged("Comparer.Ordinal"),
    "Comparer.OrdinalIgnoreCase": Tagged("Comparer.OrdinalIgnoreCase"),
    "TextEncoding.Utf8": 65001,
    "TextEncoding.Windows": 1252,
    "TextEncoding.Unicode": 1200,
    "Number.PI": math.pi,
    "#infinity": math.inf,
    "#nan": math.nan,
}


def functions() -> list[str]:
    """Every M function this version runs, by name."""
    return sorted({*_FUNCTIONS, *_SCALARS})


# ===== compile =====


@dataclass(frozen=True)
class Problem:
    """What cannot be read or run: one sentence, where (line and column from 1), the name it is about and
    the query it is in."""

    message: str
    line: int
    column: int
    name: str | None = None
    query: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"message": self.message, "line": self.line, "column": self.column, "name": self.name,
                "query": self.query}  # fmt: skip


@dataclass(frozen=True)
class Query:
    """One query compiled. kind: "table" (its `sql` and `columns`), "value" (a parameter or another plain
    value: `value`), "function", or "problem". `depends`: the other queries it names; `sources`: the names of
    the Sources its SQL reads."""

    name: str
    kind: str
    line: int
    end_line: int
    shared: bool = True
    sql: str | None = None
    columns: tuple[str, ...] = ()
    value: Any = None
    depends: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    problem: Problem | None = None


@dataclass(frozen=True)
class Compiled:
    """A file compiled: its queries in the order written, `order` the table queries' names in the order they
    run (a query after the ones it names), every problem, and whether something is still missing (the
    context's `missing`: resolve those keys and compile again)."""

    queries: tuple[Query, ...]
    order: tuple[str, ...]
    problems: tuple[Problem, ...]
    complete: bool
    sources: Mapping[str, Source]

    def query(self, name: str) -> Query:
        found = next((x for x in self.queries if x.name == name), None)
        if found is None:
            raise PowerQueryError(f"The file has no query named {name}.", 1, 1, name)
        return found

    def tables(self) -> list[Query]:
        """The table queries in the order they run."""
        return [self.query(name) for name in self.order]


def _finished(run: _Run, member: Member, value: Any, depends: Sequence[str]) -> Query:
    """A query's value as its Query."""
    made: dict[str, Any] = {"name": member.name, "line": member.line, "end_line": member.end_line,
                            "shared": member.shared, "depends": tuple(depends)}  # fmt: skip
    if isinstance(value, Nav):
        value = _nav_table(run, member.body, value)
    if isinstance(value, ErrorValue):
        raise run.fail(member.body, f"The query raises an error: {value.message}", member.name)
    if isinstance(value, Table):
        if value.nested:
            name = next(iter(value.nested))
            raise run.fail(member.body, f"{name} is a nested table's column: expand it or remove it.", name)
        if value.promotable:
            raise run.fail(
                member.body,
                "A file's table is read with its first row as the header: add Table.PromoteHeaders.",
                "Table.PromoteHeaders",
            )
        sql = value.sql()
        return Query(kind="table", sql=sql, columns=tuple(value.columns), **made)
    if isinstance(value, Closure | Builtin):
        return Query(kind="function", **made)
    if isinstance(value, Unknown):
        return Query(kind="unknown", **made)
    return Query(kind="value", value=value.text if isinstance(value, Var) else value, **made)


def _with_sources(query: Query, section: _Section) -> Query:
    """The query with every Source it reads, the ones of the queries it names among them."""
    seen: list[str] = []
    found: list[str] = []

    def visit(name: str) -> None:
        if name in seen or name not in section.reads:
            return
        seen.append(name)
        found.extend(s for s in section.reads[name] if s not in found)
        for other in section.depends[name]:
            visit(other)

    visit(query.name)
    return Query(**{**query.__dict__, "sources": tuple(found)})


def _ordered(queries: Sequence[Query]) -> tuple[str, ...]:
    """The table queries, each after the ones it names."""
    by_name = {x.name: x for x in queries}
    done: list[str] = []

    def visit(name: str, path: tuple[str, ...]) -> None:
        if name in done or name in path or name not in by_name:
            return
        for other in by_name[name].depends:
            visit(other, (*path, name))
        done.append(name)

    for query in queries:
        visit(query.name, ())
    return tuple(n for n in done if by_name[n].kind == "table")


def compile(text: str, name: str = "Query", context: Context | None = None) -> Compiled:
    """Each query of an M text as DuckDB SQL. No I/O: what must come from outside is asked of `context` by key
    (see Context); while `complete` is false, fill `context.resolved` for each of `context.missing` and compile
    again. A problem (with its line and column) is listed, never raised, and a query with a problem does not
    stop the others."""
    context = context if context is not None else Context()
    context.missing = []
    try:
        document = parse(text, name)
    except PowerQueryError as error:
        problem = Problem(error.what, error.line, error.column, error.name)
        return Compiled((), (), (problem,), True, {})
    run = _Run(context)
    section = run.section = _Section(run, document)
    queries: list[Query] = []
    problems: list[Problem] = []
    for member in document.members:
        try:
            value = section.get(member.name, member.body)
            run.finishing = member.name
            queries.append(_finished(run, member, value, section.depends[member.name]))
        except PowerQueryError as error:
            problem = Problem(error.what, error.line, error.column, error.name, member.name)
            again = error.what.startswith(tuple(f"{other} cannot run: " for other in section.failed))
            if not again or member.name not in section.failed:
                problems.append(problem)
            queries.append(Query(member.name, "problem", member.line, member.end_line, member.shared,
                                 depends=tuple(section.depends[member.name]), problem=problem))  # fmt: skip
        except RecursionError:
            problem = Problem(
                f"{member.name} is nested too deeply to compile.", member.line, 1, None, member.name
            )
            problems.append(problem)
            queries.append(
                Query(member.name, "problem", member.line, member.end_line, member.shared, problem=problem)
            )
    queries = [_with_sources(x, section) for x in queries]
    return Compiled(
        tuple(queries), _ordered(queries), tuple(problems), not context.missing, dict(context.sources)
    )


def check(
    text: str,
    name: str = "Query",
    tables: Mapping[str, Sequence[str]] | None = None,
    parameters: Mapping[str, Any] | None = None,
) -> list[Problem]:
    """What cannot run, found without reading anything: a mistake in the text, a function duckpq does not
    run, a column a table written in the file does not have. A source's columns are not known here, so a
    wrong column of a source shows when it runs."""
    return list(compile(text, name, Context(tables, parameters)).problems)


# ===== run: the same over a DuckDB connection =====

Resolver = Callable[[Source], Any]
_ATTACHED = (".duckdb", ".db", ".ddb")
_MAX_ROUNDS = 12


class _Runner:
    """What run() and to_sql() share: a DuckDB connection, the caller's resolver, and each missing key
    resolved (a file read by DuckDB, a resolver's answer registered as a view)."""

    def __init__(
        self,
        connection: Any,
        resolver: Resolver | None,
        variables: Mapping[str, Any] | None,
        context: Context,
    ) -> None:
        self.connection = connection
        self.resolver = resolver
        self.variables = dict(variables or {})
        self.context = context
        self.attached: dict[str, str] = {}

    def compiled(self, text: str, name: str) -> Compiled:
        for _ in range(_MAX_ROUNDS):
            made = compile(text, name, self.context)
            if made.complete:
                return made
            for key in list(self.context.missing):
                self.context.resolved[key] = self.resolve(key)
        raise PowerQueryError("The queries' sources could not all be resolved.", 1, 1)

    def resolve(self, key: Key) -> Any:
        try:
            if key[0] == "variable":
                if key[1] not in self.variables:
                    return Failure(f"${{{key[1]}}} has no value: pass variables={{{key[1]!r}: ...}}.")
                return str(self.variables[key[1]])
            if key[0] == "json":
                with open(key[1], encoding="utf-8-sig") as file:
                    return json.load(file)
            if key[0] == "probe":
                return [row[0] for row in self.connection.execute(key[1]).fetchall()]
            return self.source(self.context.sources[key[1]])
        except PowerQueryError as error:
            return Failure(error.what, isinstance(error, EvaluationError))
        except (
            Exception
        ) as error:  # the file's, DuckDB's or the resolver's own words, said at the source's line
            return Failure(_one_line(error))

    def source(self, source: Source) -> Any:
        given = self.resolver(source) if self.resolver is not None else None
        if given is None and source.path is None:
            return Failure(
                f"Nothing reads {source.words()} here: pass a resolver that answers for {source.function}."
            )
        name = q(source.name)
        if given is None or isinstance(given, str | os.PathLike):
            path = os.fspath(given) if given is not None else str(source.path)
            if path.lower().endswith(_ATTACHED):
                self.from_database(source, path)
            else:
                reader = _file_reader(source, path, self.connection)
                self.connection.execute(f"CREATE OR REPLACE TEMP VIEW {name} AS SELECT * FROM {reader}")
        elif hasattr(given, "create_view") and hasattr(given, "columns"):  # a DuckDB relation
            self.connection.register(source.name, given.arrow() if _other(given, self.connection) else given)
        else:  # an Arrow table, a DataFrame: whatever DuckDB registers
            self.connection.register(source.name, given)
        return Resolved([row[0] for row in self.connection.execute(f"DESCRIBE {name}").fetchall()])

    def from_database(self, source: Source, path: str) -> None:
        """A DuckDB file attached read-only: the navigation's table, or the native query run in it."""
        alias = self.attached.get(path)
        if alias is None:
            alias = self.attached[path] = f"duckpq_db_{len(self.attached)}"
            self.connection.execute(f"ATTACH {text_sql(path)} AS {alias} (READ_ONLY)")
        name = q(source.name)
        if source.query is not None:
            before = self.connection.execute("SELECT current_database()").fetchone()[0]
            self.connection.execute(f"USE {alias}")
            try:
                self.connection.execute(f"CREATE OR REPLACE TEMP TABLE {name} AS {source.query}")
            finally:
                self.connection.execute(f"USE {q(before)}")
            return
        parts = [v for step in source.navigation for v in _picked(step)]
        if not parts:
            raise PowerQueryError(
                f"Pick a table of {source.words()}: Source{{[Schema = ..., Item = ...]}}[Data]."
            )
        tries = [[alias, *parts[-2:]], [alias, "main", parts[-1]], [alias, parts[-1]]]
        for attempt in tries:
            dotted = ".".join(q(p) if p != alias else p for p in attempt)
            try:
                self.connection.execute(f"CREATE OR REPLACE TEMP VIEW {name} AS SELECT * FROM {dotted}")
                return
            except Exception:  # noqa: S112 (the next spelling of its name is tried)
                continue
        raise PowerQueryError(f"{'.'.join(parts)} is not a table of {os.path.basename(path)}.")


def _other(relation: Any, connection: Any) -> bool:
    """Whether a relation belongs to another connection (it is then handed over as Arrow)."""
    try:
        connection.register("__duckpq_try", relation)
        connection.execute('SELECT * FROM "__duckpq_try" LIMIT 0')
        connection.unregister("__duckpq_try")
        return False
    except Exception:
        return True


def _one_line(error: BaseException) -> str:
    words = str(error).strip().splitlines()
    return (words[0] if words else type(error).__name__)[:300]


def _file_reader(source: Source, path: str, connection: Any) -> str:
    """The DuckDB table function that reads a file, by the M function that named it (else by its ending)."""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", path) and not os.path.exists(path):
        raise EvaluationError(f"{path} is not a file here.")
    quoted = text_sql(path)
    lower = path.lower()
    if source.function == "Excel.Workbook" or lower.endswith((".xlsx", ".xlsm")):
        try:
            connection.execute("LOAD excel")
        except Exception:
            try:
                connection.execute("INSTALL excel")
                connection.execute("LOAD excel")
            except Exception:
                raise PowerQueryError(
                    "A workbook is read by DuckDB's excel extension, which is not installed here: run INSTALL "
                    "excel once, or answer for this source in the resolver."
                ) from None
        sheet = f", sheet = {text_sql(source.sheet)}" if source.sheet else ""
        return f"read_xlsx({quoted}, header = true{sheet})"
    if source.function == "Parquet.Document" or lower.endswith(".parquet"):
        return f"read_parquet({quoted})"
    if source.function == "Json.Document" or lower.endswith((".json", ".jsonl", ".ndjson")):
        return f"read_json_auto({quoted})"
    delimiter = source.options.get("Delimiter")
    extra = f", delim = {text_sql(delimiter)}" if isinstance(delimiter, str) and delimiter else ""
    return f"read_csv({quoted}, header = true{extra})"


def _runner(
    resolver: Resolver | None, tables: Mapping[str, Any] | None, parameters: Mapping[str, Any] | None,
    variables: Mapping[str, Any] | None, connection: Any, folder: str | None,
) -> _Runner:  # fmt: skip
    import duckdb  # here, so parse(), check() and compile() need only the standard library

    connection = connection if connection is not None else duckdb.connect()
    columns: dict[str, list[str]] = {}
    for name, table in (tables or {}).items():
        if not (isinstance(table, str) and table == name):  # a name alone: a table the connection has already
            connection.register(name, table)
        columns[name] = [row[0] for row in connection.execute(f"DESCRIBE {q(name)}").fetchall()]
    return _Runner(connection, resolver, variables, Context(columns, parameters, folder))


def _raise_first(made: Compiled, only: str | None) -> None:
    for problem in made.problems:
        if only is None or problem.query in (None, only):
            raise PowerQueryError(problem.message, problem.line, problem.column, problem.name)


def to_sql(
    text: str,
    *,
    name: str = "Query",
    resolver: Resolver | None = None,
    tables: Mapping[str, Any] | None = None,
    parameters: Mapping[str, Any] | None = None,
    variables: Mapping[str, Any] | None = None,
    connection: Any = None,
    folder: str | None = None,
) -> dict[str, str]:
    """Each table query's DuckDB SQL, by name, in the order they run. The sources are resolved (their
    columns are needed) and stay registered in `connection` under the names the SQL uses, so the SQL runs
    there as it is. PowerQueryError for the first problem."""
    runner = _runner(resolver, tables, parameters, variables, connection, folder)
    made = runner.compiled(text, name)
    _raise_first(made, None)
    return {query.name: str(query.sql) for query in made.tables()}


def run(
    text: str,
    *,
    name: str = "Query",
    resolver: Resolver | None = None,
    tables: Mapping[str, Any] | None = None,
    parameters: Mapping[str, Any] | None = None,
    variables: Mapping[str, Any] | None = None,
    connection: Any = None,
    folder: str | None = None,
) -> dict[str, Any]:
    """Run an M text: every query that is a table, as a DuckDB relation by its name, in dependency order.

    name: the query's name when the text is one `let ... in` (not a section document).
    resolver: maps a Source to something DuckDB reads (see the module's words); None for "not mine".
    tables: tables a query may name by their name (a relation, an Arrow table, a DataFrame).
    parameters: values for the file's parameter queries, by name.
    variables: values for ${NAME} inside a text.
    connection: the DuckDB connection to run in (a new in-memory one when not given).
    folder: what a relative File.Contents path is relative to.

    PowerQueryError (with .line and .column) for the first problem."""
    runner = _runner(resolver, tables, parameters, variables, connection, folder)
    made = runner.compiled(text, name)
    _raise_first(made, None)
    return {query.name: runner.connection.sql(str(query.sql)) for query in made.tables()}


def run_query(text: str, query: str, **options: Any) -> Any:
    """One query of an M text as a DuckDB relation (the queries it names are compiled into it, not run by
    themselves). The options are run()'s."""
    runner = _runner(
        options.get("resolver"), options.get("tables"), options.get("parameters"), options.get("variables"),
        options.get("connection"), options.get("folder"),
    )  # fmt: skip
    made = runner.compiled(text, str(options.get("name") or "Query"))
    found = made.query(query)
    _raise_first(made, query)
    if found.kind != "table":
        raise PowerQueryError(f"{query} is not a table: it is a {found.kind}.", found.line, 1, query)
    return runner.connection.sql(str(found.sql))
