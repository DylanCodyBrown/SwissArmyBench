"""Upgrade to In/Out (the owner, 2026-11-21): a widget that hands values on through Streamlit's session state
by named keys, rewritten as the contract's declarations (domain/widget_contract.py), shown first as a preview.

    in_key = "uploaded"                                    uploaded: In[Table] = None
    found = st.session_state.get(in_key)          ->      found = uploaded
    st.session_state["picked"] = choice                    picked: Out[str] = None ... picked = choice

A key read and never written becomes an In; one written becomes an Out (read too: its own last value). A key
is a string, or a property whose value is one (that property goes once nothing else reads it). Only plain uses
at the top level are rewritten (a read anywhere; a write as a statement of its own at the module's level); any
other use is listed as kept, with why. Its type is guessed (a table's words, the value written), and may be
changed in the preview's code before it is applied.

Pure rules: no I/O, standard library only.
"""

from __future__ import annotations

import ast
import difflib
import keyword
import re
from dataclasses import dataclass, field
from typing import Any

from swissarmybench_streamlit.domain import widget_contract as contract
from swissarmybench_streamlit.domain import widget_properties as props_rules

_TABLE_WORDS = re.compile(r"(table|frame|df|rows|uploaded|mapped|valid|records|data)$", re.IGNORECASE)


@dataclass
class _Key:
    key: str
    prop: str | None = None  # the property that holds it
    reads: list[ast.AST] = field(default_factory=list)
    writes: list[ast.Assign] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    written: list[ast.expr] = field(default_factory=list)


def _is_state(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "session_state"
        and isinstance(node.value, ast.Name)
        and node.value.id == "st"
    )


def _name(key: str, taken: set[str]) -> str:
    made = re.sub(r"\W+", "_", key).strip("_").lower() or "value"
    if made[0].isdigit() or keyword.iskeyword(made):
        made = f"v_{made}"
    base, n = made, 2
    while made in taken:
        made, n = f"{base}_{n}", n + 1
    return made


def _guess(port: str, key: _Key) -> str:
    for value in key.written:
        if isinstance(value, ast.Constant):
            kind = type(value.value).__name__
            if kind in ("str", "int", "float", "bool"):
                return kind
        if isinstance(value, ast.Dict):
            return "dict"
        if isinstance(value, (ast.List, ast.ListComp)):
            return "list"
        if isinstance(value, ast.Call):
            called = ast.unparse(value.func)
            if called.endswith(("DataFrame", "table", "read_excel", "read_csv", "drop", "copy")):
                return "Table"
    return "Table" if _TABLE_WORDS.search(port) or _TABLE_WORDS.search(key.key) else "str"


def plan(code: str) -> dict[str, Any]:
    """The upgrade: the code rewritten, each key's new declaration, what was kept and why, and the diff.
    Nothing to upgrade: `changes` is empty and the code as it is."""
    module = props_rules.parse(code)
    source = props_rules._Source(code)
    properties = {p.name: p for p in props_rules.detect(code)}
    string_props = {n: p.default for n, p in properties.items() if isinstance(p.default, str) and p.default}
    keys: dict[str, _Key] = {}
    top = {id(s) for s in module.body}

    def key_of(node: ast.expr) -> _Key | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
            return keys.setdefault(node.value, _Key(node.value))
        if isinstance(node, ast.Name) and node.id in string_props:
            found = keys.setdefault(string_props[node.id], _Key(string_props[node.id], node.id))
            found.prop = found.prop or node.id
            return found
        return None

    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(module):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    for node in ast.walk(module):
        if isinstance(node, ast.Subscript) and _is_state(node.value):
            found = key_of(node.slice)
            if found is None:
                continue
            above = parents.get(id(node))
            if isinstance(node.ctx, ast.Load):
                found.reads.append(node)
            elif (
                isinstance(above, ast.Assign)
                and id(above) in top
                and len(above.targets) == 1
                and above.targets[0] is node
            ):
                found.writes.append(above)
                found.written.append(above.value)
            else:
                found.kept.append(f"line {node.lineno}: a write inside a block or a function")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and _is_state(node.func.value)
            and node.args
        ):
            found = key_of(node.args[0])
            if found is None:
                continue
            if node.func.attr == "get" and len(node.args) <= 2 and not node.keywords:
                found.reads.append(node)
            else:
                found.kept.append(f"line {node.lineno}: st.session_state.{node.func.attr}(...)")
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and _is_state(node.comparators[0]):
            found = key_of(node.left)
            if found is not None and isinstance(node.ops[0], (ast.In, ast.NotIn)):
                found.reads.append(node)
    taken = {n.id for n in ast.walk(module) if isinstance(n, ast.Name)} | set(properties)
    edits: list[tuple[int, int, str]] = []
    changes: list[dict[str, Any]] = []
    kept: list[str] = []
    declarations: list[str] = []
    for key in sorted(keys.values(), key=lambda k: k.key):
        if key.kept:
            kept += [f"{key.key}: {why}" for why in key.kept]
            continue
        if not key.reads and not key.writes:
            continue
        port = _name(key.key, taken - ({key.prop} if key.prop else set()))
        taken.add(port)
        direction = "out" if key.writes else "in"
        kind = _guess(port, key)
        for node in key.reads:
            start, end = source.span(node)
            if isinstance(node, ast.Call):
                text = (
                    port
                    if len(node.args) == 1
                    else (f"({port} if {port} is not None else {ast.get_source_segment(code, node.args[1])})")
                )
            elif isinstance(node, ast.Compare):
                text = f"{port} is {'not ' if isinstance(node.ops[0], ast.In) else ''}None"
            else:
                text = port
            edits.append((start, end, text))
        for statement in key.writes:
            start, _ = source.span(statement.targets[0])
            _, end = source.span(statement.targets[0])
            edits.append((start, end, port))
        marker = "In" if direction == "in" else "Out"
        words = (
            "comes in from another widget" if direction == "in" else "goes out to the widgets that read it"
        )
        declarations.append(f"# {key.key}: {words} (was the session state key {key.key!r})")
        declarations.append(f"{port}: {marker}[{kind}] = None")
        changes.append(
            {"key": key.key, "port": port, "direction": direction, "type": kind, "property": key.prop}
        )
    if not changes:
        return {"code": code, "changes": [], "kept": kept, "diff": ""}
    after = code
    for start, end, text in sorted(edits, reverse=True):
        after = after[:start] + text + after[end:]
    after = _drop_unused(after, {c["property"] for c in changes if c["property"]})
    after = _declare(after, declarations)
    after = _import(
        after,
        sorted(
            {"In" if c["direction"] == "in" else "Out" for c in changes}
            | ({"Table"} if any(c["type"] == "Table" for c in changes) else set())
        ),
    )
    contract.detect(after)  # the rewritten code reads (raises its line otherwise)
    diff = "".join(
        difflib.unified_diff(
            code.splitlines(keepends=True), after.splitlines(keepends=True), "before", "after", n=2
        )
    )
    return {"code": after, "changes": changes, "kept": kept, "diff": diff}


def _drop_unused(code: str, names: set[str]) -> str:
    """Each property that held a key, taken out once nothing reads it."""
    module = ast.parse(code)
    used = {n.id for n in ast.walk(module) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    source = props_rules._Source(code)
    spans = []
    for statement in module.body:
        target = (
            statement.targets[0]
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1
            else None
        )
        if isinstance(target, ast.Name) and target.id in names and target.id not in used:
            start, end = source.span(statement)
            end = end + 1 if code[end : end + 1] == "\n" else end
            line = statement.lineno - 2  # its help: the comment lines just above it
            while line >= 0 and source.lines[line].strip().startswith("#"):
                start = source.starts[line]
                line -= 1
            spans.append((start, end))
    for start, end in sorted(spans, reverse=True):
        code = code[:start] + code[end:]
    return code


def _declare(code: str, lines: list[str]) -> str:
    """The declarations after the last top-level import (else at the top)."""
    module = ast.parse(code)
    last = max(
        (s.end_lineno or s.lineno for s in module.body if isinstance(s, (ast.Import, ast.ImportFrom))),
        default=0,
    )
    rows = code.split("\n")
    return "\n".join([*rows[:last], "", *lines, *rows[last:]])


def _import(code: str, names: list[str]) -> str:
    found = re.search(r"^from sab_canvas import (.+)$", code, re.M)
    if found:
        had = {n.strip() for n in found.group(1).split(",")}
        merged = sorted(had | set(names), key=lambda n: (n[0].islower(), n))
        return code[: found.start()] + "from sab_canvas import " + ", ".join(merged) + code[found.end() :]
    line = "from sab_canvas import " + ", ".join(names)
    if re.search(r"^import streamlit as st$", code, re.M):
        return re.sub(r"^(import streamlit as st)$", r"\1\n" + line, code, count=1, flags=re.M)
    return line + "\n" + code
