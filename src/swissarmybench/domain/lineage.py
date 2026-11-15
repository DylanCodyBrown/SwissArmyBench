"""Lineage (docs/ideas.md, lineage with values and approved outputs, 2026-11-15): from a canvas block or
any cell, back through every cell to the data. Pure rules, no I/O.

The walk starts at one cell (a notebook's or a script's; a canvas block is a link to one) and goes back
by what each cell reads:

  names       a name a cell reads comes from the cell that makes it: on a canvas page, the first block
              placed that makes it (the page's own run order); else in the cell's document, the
              nearest cell above that makes it (else the first below); else a project's data.ipynb
              (what data.py gives: `from data import ...` names go there too); else an open table
  @cell       a comment's `@cell7` links the cell to cell 7 of its document (a dotted edge)
  tables      a table's read-only cell goes back through the grid's steps (one node each, in order)
              to the cell of the user's that made it, or to where it came from: the file, the
              connection, the paste. An open table no document holds is the grid's own
  sources     connections and files the code names (`sab.sql("Shop", ...)`, `pd.read_csv("x.csv")`),
              and a SQL or DAX cell's connection
  controllers a cell that makes a widget's value (`region = st.selectbox(...)`) is a controller, the
              kind that drives what follows; a Markdown or HTML cell reads its `{{ names }}`

The graph is the nodes in flow order (the data first, the cell asked about last), the edges (each with
the name it carries), and the same as a Mermaid flowchart. The values are not here: the services read
them from the kernel, a live page and the grid, and give each node's in a word for its Mermaid label.
"""

from __future__ import annotations

import ast
import ntpath
import posixpath
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import html_cells, table_cells
from swissarmybench.domain.streamlit_cells import WIDGETS, facts, piece_name

MAX_NODES: int = 120
MAX_LABEL: int = 60
_LINK = re.compile(r"@cell(\d+)\b")
_CONTRACT = re.compile(r"^#\s*makes:", re.MULTILINE)  # a controller's header (the controllers work)
_SOURCES = {"sql", "dax", "read", "connection", "blade"}  # sab.<one>("Name", ...)
_FILE_READERS = re.compile(r"^(?:read_(?:csv|parquet|json|excel|table|feather|orc|ndjson)|scan_\w+)$")
DATA_NAME: str = "data.ipynb"
DATA_MODULE: str = "data"

# A cell: the document's path and the cell's own number.
Key = tuple[str, int]


class LineageError(ValueError):
    """A lineage that cannot be traced as asked (the message says why)."""


@dataclass(frozen=True)
class DocCell:
    number: int
    kind: str  # code, sql, dax, html, markdown
    code: str  # its source (a SQL or DAX cell's query; an HTML or Markdown cell's text)
    name: str | None = None
    role: str = ""  # its part in the Tables group (domain/notebooks.py ROLES)
    table: str | None = None
    connection: str | None = None  # a SQL cell's connection (`Shop -> recent`), a DAX cell's dataset


@dataclass(frozen=True)
class Document:
    path: str
    cells: tuple[DocCell, ...]
    data: bool = False  # a project's data.ipynb


@dataclass(frozen=True)
class TableFacts:
    """An open table, as the grid holds it: where it came from and its steps in plain words."""

    name: str
    variable: str
    origin: str = "unknown"  # python, file, dropped, paste, connection, query, unknown
    source: str = ""  # where in a word: orders.csv, Warehouse, Pasted
    steps: tuple[str, ...] = ()


@dataclass(frozen=True)
class Node:
    id: str
    kind: str  # cell, controller, text, table, step, source
    label: str
    where: str = ""  # "analysis.ipynb @cell4", "the grid", "grid step 2", "file", "connection"
    document: str | None = None
    cell: int | None = None
    doc_kind: str | None = None  # notebook, script, data (its kind colour)
    makes: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    table: str | None = None  # a table's variable (a table, its steps, its source)
    step: int | None = None  # a grid step's place, from 1
    target: bool = False
    on_page: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "where": self.where,
            "document": self.document,
            "cell": self.cell,
            "doc_kind": self.doc_kind,
            "makes": list(self.makes),
            "reads": list(self.reads),
            "table": self.table,
            "step": self.step,
            "target": self.target,
            "on_page": self.on_page,
        }


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    name: str = ""  # the names it carries, joined
    kind: str = "name"  # name, link (@cell), table, step

    def to_json(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "name": self.name, "kind": self.kind}


@dataclass(frozen=True)
class Graph:
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    notes: tuple[str, ...] = ()

    @property
    def target(self) -> Node:
        return next(n for n in self.nodes if n.target)

    def to_json(self, short: Mapping[str, str] | None = None) -> dict[str, Any]:
        return {
            "target": self.target.id,
            "nodes": [n.to_json() for n in self.nodes],
            "edges": [e.to_json() for e in self.edges],
            "notes": list(self.notes),
            "mermaid": mermaid(self, short),
        }


# ===== a cell: what it makes, reads, names as a source =====


def file_name(path: str) -> str:
    return ntpath.basename(posixpath.basename(path)) or path


def doc_kind(document: Document) -> str:
    if document.data or file_name(document.path).lower() == DATA_NAME:
        return "data"
    return "script" if document.path.lower().endswith(".py") else "notebook"


@dataclass(frozen=True)
class _Read:
    makes: tuple[str, ...]
    reads: tuple[str, ...]
    imported: frozenset[str]  # names it makes only by an import
    from_data: frozenset[str]  # names it imports from the project's data.py
    links: tuple[int, ...]  # the cells its comments link to (@cell7)
    sources: tuple[tuple[str, str], ...]  # (kind, label): connection, file, blade
    controller: bool


def _call_sources(tree: ast.AST) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Constant) or not isinstance(first.value, str) or not first.value.strip():
            continue
        owner = node.func.value
        attr = node.func.attr
        if attr in _SOURCES and isinstance(owner, ast.Name) and owner.id in ("sab", "sag"):
            kind = "blade" if attr == "blade" else "connection"
            found.append((kind, first.value.split("/")[0] if attr == "dax" else first.value))
        elif _FILE_READERS.match(attr):
            found.append(("file", file_name(first.value)))
    return found


def _widgets(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in WIDGETS
        for node in ast.walk(tree)
    )


def _imports(tree: ast.Module) -> tuple[set[str], set[str]]:
    plain: set[str] = set()
    data: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, ast.Import):
            plain |= {(a.asname or a.name).split(".")[0] for a in statement.names}
        elif isinstance(statement, ast.ImportFrom):
            names = {a.asname or a.name for a in statement.names if a.name != "*"}
            (data if statement.module == DATA_MODULE and statement.level == 0 else plain).update(names)
    return plain, data


def read_cell(cell: DocCell) -> _Read:
    """What a cell makes and reads, the cells it links to, the sources it names."""
    code = table_cells.split_uses(cell.code, sql=cell.kind in ("sql", "dax"), html=cell.kind == "html")[1]
    links = tuple(int(n) for n in dict.fromkeys(_LINK.findall(cell.code)))
    if cell.kind in ("markdown", "html"):
        return _Read((), tuple(html_cells.names(code)), frozenset(), frozenset(), links, (), False)
    if cell.kind in ("sql", "dax"):
        connection, _, made = (cell.connection or "").partition(" -> ")
        source = connection.split("/")[0].strip()
        reads = tuple(table_cells.names_used(code, sql=True))
        makes = (made.strip(),) if made.strip().isidentifier() else ()
        return _Read(
            makes, reads, frozenset(), frozenset(), links, (("connection", source),) if source else (), False
        )
    found = facts(code)
    try:
        tree = ast.parse(table_cells.split_uses(code)[1])
    except (SyntaxError, ValueError, RecursionError):
        return _Read(found.makes, found.reads, frozenset(), frozenset(), links, (), False)
    plain, data = _imports(tree)
    controller = _widgets(tree) or bool(_CONTRACT.search(code))
    return _Read(
        found.makes,
        found.reads,
        frozenset(plain),
        frozenset(data),
        links,
        tuple(_call_sources(tree)),
        controller,
    )


def _label(cell: DocCell) -> str:
    if cell.name:
        return cell.name
    if cell.kind in ("markdown", "html"):
        first = next((line.strip() for line in cell.code.split("\n") if line.strip()), "")
        return re.sub(r"^#+\s*", "", first)[:MAX_LABEL] or f"Cell {cell.number}"
    if cell.kind in ("sql", "dax"):
        first = next((line.strip() for line in cell.code.split("\n") if line.strip()), "")
        return first[:MAX_LABEL] or f"Cell {cell.number}"
    return piece_name(cell.code, cell.number)


# ===== the walk =====


@dataclass
class _Walk:
    docs: Mapping[str, Document]
    tables: Mapping[str, TableFacts]
    page: tuple[Key, ...]
    data: str | None
    nodes: dict[str, Node] = field(default_factory=dict)  # by a key of its own (below)
    order: list[str] = field(default_factory=list)  # the keys, as found
    edges: dict[tuple[str, str], tuple[list[str], str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    reads: dict[Key, _Read] = field(default_factory=dict)

    # --- documents and cells

    def cell(self, key: Key) -> DocCell | None:
        document = self.docs.get(key[0])
        return next((c for c in document.cells if c.number == key[1]), None) if document else None

    def read(self, key: Key) -> _Read:
        if key not in self.reads:
            found = self.cell(key)
            self.reads[key] = (
                read_cell(found) if found else _Read((), (), frozenset(), frozenset(), (), (), False)
            )
        return self.reads[key]

    def makes(self, key: Key, name: str) -> bool:
        mine = self.read(key)
        return name in mine.makes and name not in mine.imported and name not in mine.from_data

    def in_doc_maker(self, path: str, at: int | None, name: str, last: bool = False) -> Key | None:
        document = self.docs.get(path)
        if document is None:
            return None
        numbers = [c.number for c in document.cells]
        others = [n for n in numbers if n != at and self.makes((path, n), name)]
        if not others:
            return None
        if last or at not in numbers:
            return (path, others[-1])
        place = numbers.index(at)
        above = [n for n in others if numbers.index(n) < place]
        return (path, above[-1] if above else others[0])

    def maker(self, at: Key, name: str) -> tuple[str, Any] | None:
        """Where a name a cell reads comes from: ("cell", key) or ("table", variable)."""
        if at in self.page:
            for key in self.page:
                if key != at and self.makes(key, name):
                    return ("cell", key)
        mine = self.read(at)
        if name not in mine.from_data:
            found = self.in_doc_maker(at[0], at[1], name)
            if found is not None:
                return ("cell", found)
        if self.data and self.data != at[0]:
            found = self.in_doc_maker(self.data, None, name, last=True)
            if found is not None:
                return ("cell", found)
        if name in self.tables:
            return ("table", name)
        return None

    # --- nodes

    def ranks(self) -> dict[str, tuple[int, ...]]:
        """Each cell node's place for the flow's ties: data.ipynb first, then the documents as met, each
        in its own order. The rest (sources, the grid's tables) before every cell."""
        documents = list(dict.fromkeys(n.document for n in self.nodes.values() if n.document))
        documents.sort(key=lambda d: d != self.data)
        out: dict[str, tuple[int, ...]] = {}
        for key, node in self.nodes.items():
            if node.document is None or node.cell is None:
                out[key] = (0, 0, 0)
                continue
            numbers = [c.number for c in self.docs[node.document].cells]
            place = numbers.index(node.cell) if node.cell in numbers else 0
            out[key] = (1, documents.index(node.document), place)
        return out

    def add(self, key: str, node: Node) -> str:
        if key not in self.nodes:
            self.nodes[key] = node
            self.order.append(key)
        return key

    def link(self, source: str, target: str, name: str = "", kind: str = "name") -> None:
        if source == target:
            return
        names, was = self.edges.get((source, target), ([], kind))
        if name and name not in names:
            names.append(name)
        self.edges[(source, target)] = (names, was if was != "link" else kind)

    def cell_node(self, key: Key) -> str:
        """A cell's node (and everything it comes from, walked once)."""
        ident = f"c:{key[0]}:{key[1]}"
        if ident in self.nodes:
            return ident
        if len(self.nodes) >= MAX_NODES:
            if not self.notes:
                self.notes.append(f"The flow is cut at {MAX_NODES} steps.")
            return ""
        cell = self.cell(key)
        document = self.docs[key[0]]
        if cell is None:
            return ""
        mine = self.read(key)
        if cell.role == "transformations" and cell.table:
            kind = "table"
        elif cell.kind in ("markdown", "html"):
            kind = "text"
        else:
            kind = "controller" if mine.controller else "cell"
        label = cell.table if kind == "table" and cell.table else _label(cell)
        shown = tuple(n for n in mine.makes if n not in mine.imported and not n.startswith("_"))
        self.add(
            ident,
            Node(
                "",
                kind,
                label,
                f"{file_name(key[0])} @cell{key[1]}",
                key[0],
                key[1],
                doc_kind(document),
                shown,
                tuple(n for n in mine.reads if n not in ("st", "pd")),
                cell.table if kind == "table" else None,
                on_page=key in self.page,
            ),
        )
        if kind == "table" and cell.table:
            self.table_chain(cell.table, ident, key)
        for source_kind, label_ in mine.sources:
            self.link(self.source_node(source_kind, label_), ident, "", "table")
        for name in mine.reads:
            found = self.maker(key, name)
            if found is None:
                continue
            upstream = self.cell_node(found[1]) if found[0] == "cell" else self.grid_table(found[1])
            if upstream:
                self.link(upstream, ident, name)
        for number in mine.links:
            linked = (key[0], number)
            if number != key[1] and self.cell(linked) is not None:
                upstream = self.cell_node(linked)
                if upstream:
                    self.link(upstream, ident, "", "link")
        return ident

    def source_node(self, kind: str, label: str) -> str:
        where = {"file": "file", "connection": "connection", "blade": "blade"}.get(kind, kind)
        return self.add(f"s:{kind}:{label}", Node("", "source", label, where))

    def table_chain(self, variable: str, ident: str, key: Key | None) -> None:
        """A table's node `ident` from its steps, back to the user's cell that made it or its origin."""
        facts_ = self.tables.get(variable)
        start: str | None = None
        if key is not None:
            maker = next(
                (
                    c
                    for c in self.docs[key[0]].cells
                    if c.role == "maker" and c.table == variable and c.number != key[1]
                ),
                None,
            )
            if maker is not None:
                start = self.cell_node((key[0], maker.number)) or None
        if start is None and facts_ is not None and facts_.origin not in ("python", "unknown"):
            start = self.source_node(
                "file" if facts_.origin in ("file", "dropped") else facts_.origin,
                facts_.source or facts_.origin,
            )
        before = start
        for index, words in enumerate(facts_.steps if facts_ else (), start=1):
            step = self.add(
                f"t:{variable}:{index}",
                Node("", "step", words, f"grid step {index}", table=variable, step=index),
            )
            if before:
                self.link(before, step, "", "step")
            before = step
        if before:
            self.link(
                before, ident, variable if before == start else "", "step" if before != start else "table"
            )

    def grid_table(self, variable: str) -> str:
        """An open table no document holds a cell for: the grid's own."""
        ident = f"g:{variable}"
        if ident in self.nodes:
            return ident
        facts_ = self.tables[variable]
        self.add(ident, Node("", "table", facts_.name, "the grid", table=variable))
        self.table_chain(variable, ident, None)
        return ident


def _flow_order(
    keys: Sequence[str], edges: Iterable[tuple[str, str]], rank: Mapping[str, tuple[int, ...]]
) -> list[str]:
    """The nodes with every node after the ones it comes from; otherwise by `rank` (data.ipynb's cells
    first, then each document's cells in its own order), then as they were found, latest first (the
    data before the cells that read it)."""
    found = list(reversed(keys))
    place = {key: (*rank.get(key, ()), i) for i, key in enumerate(found)}
    before: dict[str, set[str]] = {key: set() for key in found}
    for source, target in edges:
        if source in before and target in before:
            before[target].add(source)
    done: list[str] = []
    waiting = list(found)
    while waiting:
        ready = [k for k in waiting if before[k] <= set(done)]
        if not ready:  # a cycle (cells that link to each other): take the first found
            ready = [waiting[0]]
        first = min(ready, key=lambda k: place[k])
        done.append(first)
        waiting.remove(first)
    return done


def trace(
    target: Key,
    docs: Mapping[str, Document],
    tables: Mapping[str, TableFacts],
    page: Sequence[Key] = (),
    data: str | None = None,
) -> Graph:
    """The lineage of one cell: every node it comes from, in flow order, the cell itself last.

    `docs`: the documents by path (the target's, the canvas page's, data.ipynb). `tables`: the open
    tables by their names as Python variables. `page`: a canvas page's blocks, in the order placed,
    when the cell is a block's. `data`: the project's data.ipynb, when there is one."""
    walk = _Walk(docs, tables, tuple(page), data if data in docs else None)
    if walk.cell(target) is None:
        raise LineageError(f"{file_name(target[0])} has no cell {target[1]} to trace.")
    start = walk.cell_node(target)
    walk.nodes[start] = _replace(walk.nodes[start], target=True)
    keys = _flow_order(walk.order, walk.edges, walk.ranks())
    if keys and keys[-1] != start:  # the target last, always
        keys.remove(start)
        keys.append(start)
    ids = {key: f"n{i}" for i, key in enumerate(keys, start=1)}
    nodes = tuple(_replace(walk.nodes[key], id=ids[key]) for key in keys)
    edges = tuple(
        Edge(ids[s], ids[t], ", ".join(names), kind)
        for (s, t), (names, kind) in walk.edges.items()
        if s in ids and t in ids
    )
    return Graph(nodes, edges, tuple(walk.notes))


def _replace(node: Node, **changes: Any) -> Node:
    return Node(**(node.to_json() | {"makes": node.makes, "reads": node.reads} | changes))


# ===== the Mermaid text =====

_SHAPES: dict[str, tuple[str, str]] = {
    "source": ("[(", ")]"),  # a cylinder: data at rest
    "step": ("[/", "/]"),
    "table": ("[[", "]]"),
    "controller": ("{{", "}}"),
    "text": (">", "]"),
    "cell": ("[", "]"),
}
# Neutral colours: the Workbench draws its own (the kind colours and the theme) in their place.
CLASSES: tuple[str, ...] = (
    "classDef notebook stroke-width:2px",
    "classDef script stroke-width:2px",
    "classDef data stroke-width:2px",
    "classDef source stroke-dasharray:3 3",
    "classDef target stroke-width:3px",
)


def mermaid_text(text: str) -> str:
    """Words as a Mermaid label holds them: no markup, no quote, nothing a label can run."""
    cut = " ".join(text.split())
    cut = cut if len(cut) <= MAX_LABEL else cut[: MAX_LABEL - 1] + "…"
    for raw, safe in (("#", "#35;"), ('"', "#quot;"), ("<", "#lt;"), (">", "#gt;"), ("`", "#96;")):
        cut = cut.replace(raw, safe)
    return cut


def mermaid(graph: Graph, short: Mapping[str, str] | None = None) -> str:
    """The graph as a Mermaid flowchart, top to bottom: each node's name, where it is and (`short`, by
    node id) its value in a word."""
    lines = ["flowchart TD"]
    for node in graph.nodes:
        start, end = _SHAPES.get(node.kind, ("[", "]"))
        parts = [node.label, node.where] if node.where else [node.label]
        if short and short.get(node.id):
            parts.append(short[node.id])
        label = "<br/>".join(mermaid_text(p) for p in parts if p)
        lines.append(f'  {node.id}{start}"{label}"{end}')
    for edge in graph.edges:
        arrow = "-.->" if edge.kind == "link" else "-->"
        named = f"|{mermaid_text(edge.name)}|" if edge.name else ""
        lines.append(f"  {edge.source} {arrow}{named} {edge.target}")
    for node in graph.nodes:
        if node.doc_kind:
            lines.append(f"  class {node.id} {node.doc_kind}")
        if node.kind == "source":
            lines.append(f"  class {node.id} source")
    lines.append(f"  class {graph.target.id} target")
    lines += [f"  {line}" for line in CLASSES]
    return "\n".join(lines) + "\n"
