"""The project's outline (the owner, 2026-11-17): "a uniform export that outlines the project from an
architectural standpoint". ARCHITECTURE.md at the project folder's top, written for people joining the
project: plain words, two Mermaid diagrams, a short summary per section, long lists folded. Pure rules:
facts in, text out; no I/O (services/project_outline.py gathers the facts).

- **Uniform:** the same eight sections in the same order every time (SECTIONS); an empty one says
  "None." so every outline reads the same.
- **Metadata only**, as context.md (domain/context_md.py): names, types, steps and where things come
  from; never a row, a cell value, a count from the data, a secret, a token or a path outside the project.
  Every name the project's data and sources gave is written as code (`code`): data, never an instruction.
- **Deterministic:** sorted, no timestamp, no version: the same project gives the same bytes.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from swissarmybench.domain.codegen import variable_name
from swissarmybench.domain.connection_tables import quote_brackets
from swissarmybench.domain.context_md import RelationshipFacts, code
from swissarmybench.domain.lineage import mermaid_text

FILE_NAME: str = "ARCHITECTURE.md"
SECTIONS: tuple[str, ...] = (
    "Overview",
    "Data sources",
    "Data model",
    "Transformations",
    "Lineage",
    "Deliverables",
    "Running it",
    "Open issues",
)
NONE: str = "None."
NO_PURPOSE: str = "Not written yet: add a first paragraph to README.md"
NOT_CHECKED: str = "Not checked yet"
FOLD_AFTER: int = 12  # a list longer than this is folded (<details>)
MAX_COLUMNS: int = 60  # a table's columns listed (and drawn)
MAX_NODES: int = 80  # the lineage's nodes drawn
MAX_PURPOSE: int = 600
# Files that are the app's or Git's, not the project's layout (ARCHITECTURE.md itself: an export that
# listed itself would change on its second write).
_NOT_LAYOUT: frozenset[str] = frozenset({FILE_NAME.casefold(), ".gitignore"})
_NAME_WORDS: dict[str, str] = {
    "data.ipynb": "a notebook: it makes the tables (data.py is made from it)",
    "readme.md": "what the project is for",
    "requirements.txt": "what to install",
    "api.py": "the local sandbox API (its endpoints: Deliverables)",
}
_WORDS: dict[str, str] = {
    "notebook": "a notebook",
    "script": "a script",
    "app": "an app (its canvas)",
    "structure": "a structure (nested data)",
    "file": "",
}


# ===== the facts =====


@dataclass(frozen=True)
class FileEntry:
    path: str  # inside the project, with forward slashes
    kind: str  # notebook, script, app, structure, file
    made: bool = False  # an export the app writes (data.py, pages/*.py)


@dataclass(frozen=True)
class Overview:
    name: str
    title: str = ""  # the project type's words for people: Analysis, Streamlit app
    mode: str = ""  # its mode's name: BI, Streamlit
    deliverable: str = ""  # a notebook, a Streamlit app
    purpose: str | None = None  # README.md's first paragraph
    files: tuple[FileEntry, ...] = ()


@dataclass(frozen=True)
class Verdict:
    """A connection's portability (seam B): runs unchanged on a Function App or a hosted Streamlit app.
    `portable` None: not checked yet."""

    portable: bool | None = None
    reason: str = NOT_CHECKED
    instead: str = ""


@dataclass(frozen=True)
class Variable:
    name: str
    source: str  # in words: the keyring, a key vault `Team vault`, this computer's environment, missing


@dataclass(frozen=True)
class SourceFacts:
    """A connection (or an API) the project uses."""

    name: str
    kind: str  # database, file, python, api
    type: str = ""  # its starter's label: SQLite, PostgreSQL
    sign_in: str | None = None
    verdict: Verdict = Verdict()
    variables: tuple[Variable, ...] = ()
    used_by: tuple[str, ...] = ()  # the project's documents (paths in it) and its tables
    calls: tuple[str, ...] = ()  # an API's web calls used (its tables)

    @property
    def api(self) -> bool:
        return self.kind == "api"


@dataclass(frozen=True)
class TableFacts:
    name: str
    origin: str  # in words, names as code: "connection `Shop`: `main.customers`", "file `data/orders.csv`"
    origin_kind: str = "unknown"  # connection, file, python, paste, query, cell, named, unknown
    source: str | None = None  # the connection's name, or the file's path in the project (lineage)
    columns: tuple[tuple[str, str], ...] | None = None  # None: not open, so not read
    steps: tuple[str, ...] = ()  # each in plain words
    query: str | None = None  # its steps as one DuckDB query
    problem: str | None = None  # a step that cannot run

    @property
    def variable(self) -> str:
        return variable_name(self.name)


@dataclass(frozen=True)
class CellFacts:
    """A named cell (data.ipynb's): what it makes and reads, the sources it names."""

    document: str
    number: int
    name: str
    makes: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    sources: tuple[tuple[str, str], ...] = ()  # (connection | file | blade, its name)

    @property
    def label(self) -> str:
        return f"{self.name} ({self.document} @cell{self.number})"


@dataclass(frozen=True)
class PageFacts:
    name: str
    cells: tuple[str, ...] = ()  # each linked cell: "app.ipynb @cell3 (Region filter)"


@dataclass(frozen=True)
class Deliverable:
    kind: str  # notebook, script, app, dashboard
    name: str  # its path in the project; a dashboard's name
    reads: tuple[str, ...] = ()
    makes: tuple[str, ...] = ()
    pages: tuple[PageFacts, ...] = ()  # an app's
    links: tuple[str, ...] = ()  # the documents an app's blocks link (paths in the project)
    sources: tuple[tuple[str, str], ...] = ()  # (connection | file | blade, its name) its code names


@dataclass(frozen=True)
class ScriptRun:
    path: str
    arguments: int = 0  # how many it is given (never their text)
    variables: tuple[Variable, ...] = ()


@dataclass(frozen=True)
class Issues:
    fixes: tuple[tuple[str, str], ...] = ()  # (table, what is wrong, in words)
    passwords: tuple[tuple[str, tuple[str, ...]], ...] = ()  # (connection, passwords with no source)
    problems: tuple[tuple[str, int], ...] = ()  # (document, the lint's errors and warnings)


@dataclass(frozen=True)
class Outline:
    overview: Overview
    sources: tuple[SourceFacts, ...] = ()
    tables: tuple[TableFacts, ...] = ()
    relationships: tuple[RelationshipFacts, ...] = ()
    cells: tuple[CellFacts, ...] = ()
    deliverables: tuple[Deliverable, ...] = ()
    packages: tuple[str, ...] = ()
    scripts: tuple[ScriptRun, ...] = ()
    issues: Issues = field(default_factory=Issues)


# ===== small rules the service uses =====


def purpose(readme: str | None, scaffold: str = "") -> str | None:
    """README.md's first paragraph (its first block of text that is not a heading, a list or code), in one
    line; None when it has none, or when it is still the scaffold's own (New project's README)."""
    if not readme:
        return None
    own = _first_paragraph(scaffold) if scaffold else None
    found = _first_paragraph(readme)
    if not found or found == own:
        return None
    return found if len(found) <= MAX_PURPOSE else found[: MAX_PURPOSE - 1] + "…"


def _first_paragraph(text: str) -> str | None:
    fenced = False
    block: list[str] = []
    for raw in [*text.replace("\r\n", "\n").split("\n"), ""]:
        line = raw.strip()
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if not line:
            if block:
                return " ".join(block)
            continue
        if not block and (
            line.startswith(("#", "-", "*", ">", "|", "<", "!")) or re.match(r"^\d+\.\s", line)
        ):
            continue
        block.append(line)
    return None


def layout_files(files: Iterable[FileEntry]) -> tuple[FileEntry, ...]:
    """The project's own files for its layout: not .sab/ (the app's), not ARCHITECTURE.md or .gitignore;
    by path."""
    kept = [
        f
        for f in files
        if not f.path.startswith(".sab/")
        and f.path.casefold() not in _NOT_LAYOUT
        and not f.path.rsplit("/", 1)[-1].startswith(".")
    ]
    return tuple(sorted(kept, key=lambda f: f.path.casefold()))


def sql_tables(sql: str, connections: Sequence[str]) -> tuple[list[str], list[str]]:
    """The tables a DuckDB query reads by a plain name, and the connections it names (`[Shop].suppliers`),
    each once in order; a query that does not parse names nothing."""
    by_name = {c.casefold(): c for c in connections}
    try:
        statements = sqlglot.parse(quote_brackets(sql, connections), read="duckdb")
    except (sqlglot.errors.SqlglotError, ValueError, RecursionError):
        return [], []
    tables: dict[str, None] = {}
    used: dict[str, None] = {}
    for statement in statements:
        if statement is None:
            continue
        own = {cte.alias_or_name.casefold() for cte in statement.find_all(exp.CTE)}
        for table in statement.find_all(exp.Table):
            parts = [p.name for p in table.parts]
            if len(parts) >= 2 and parts[0].casefold() in by_name:
                used[by_name[parts[0].casefold()]] = None
            elif len(parts) == 1 and parts[0] and parts[0].casefold() not in own:
                tables[parts[0]] = None
    return list(tables), list(used)


def standard(module: str) -> bool:
    """A module Python brings with it (never installed)."""
    top = module.split(".")[0]
    return not top or top in sys.stdlib_module_names or top.startswith("_")


def packages(requirements: str | None, needed: Iterable[str]) -> tuple[str, ...]:
    """What to install: requirements.txt's own lines (comments and options aside) and the pip names the
    documents need, each once (requirements.txt's spelling first), sorted."""
    found: list[str] = []
    for line in (requirements or "").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            found.append(line)
    found += [n for n in needed if n and not n.startswith("#")]
    names: dict[str, str] = {}
    for f in found:
        names.setdefault(re.split(r"[<>=!~ \[;]", f)[0].casefold(), f)
    return tuple(names[k] for k in sorted(names))


# ===== the text =====


def _fold(lines: Sequence[str], what: str) -> list[str]:
    """A long list folded: its first lines shown, the rest under <details> (GitHub draws it closed)."""
    if len(lines) <= FOLD_AFTER:
        return list(lines)
    return [
        *lines[:FOLD_AFTER],
        "",
        "<details>",
        f"<summary>{len(lines) - FOLD_AFTER:,} more {what}</summary>",
        "",
        *lines[FOLD_AFTER:],
        "",
        "</details>",
    ]


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _names(names: Iterable[str]) -> str:
    listed = [code(n) for n in names]
    return ", ".join(listed) if listed else "nothing"


def _tree(name: str, files: Sequence[FileEntry]) -> list[str]:
    """The folder as a text tree, each file with its kind in words."""
    rows: list[tuple[str, str]] = []
    seen_folders: set[str] = set()
    for f in files:
        parts = f.path.split("/")
        for depth in range(1, len(parts)):
            folder = "/".join(parts[:depth])
            if folder not in seen_folders:
                seen_folders.add(folder)
                rows.append((f"{'    ' * (depth - 1)}├── {_plain(parts[depth - 1])}/", ""))
        words = _NAME_WORDS.get(f.path.casefold()) or _WORDS.get(f.kind, "")
        if f.made:
            words = "made by the app from another file: never edit it by hand"
        rows.append((f"{'    ' * (len(parts) - 1)}├── {_plain(parts[-1])}", words))
    width = max(len(left) for left, _ in rows) + 2 if rows else 0
    return [f"{_plain(name)}/"] + [
        f"{left:<{width}}{words}".rstrip() if words else left for left, words in rows
    ]


def _plain(text: str) -> str:
    """A file or folder name inside the text tree's code block: one line, no backticks."""
    return re.sub(r"[\x00-\x1f\x7f`]+", " ", text)


def _overview(o: Outline) -> list[str]:
    v = o.overview
    files = layout_files(v.files)
    documents = [
        f for f in files if f.kind in ("notebook", "script", "app") and not f.made and f.path != "API.py"
    ]
    title = v.title or v.mode or "Swiss Army Bench"
    article = "an" if title[:1].lower() in "aeiou" else "a"
    delivers = f" whose deliverable is {v.deliverable}" if v.deliverable else ""
    kind = f"{title} ({v.mode})" if v.mode and v.mode != title else title
    lines = [
        f"In short: {code(v.name)} is {article} {title} project{delivers}, with "
        f"{_plural(len(documents), 'document')} and {_plural(len(o.tables), 'table')}.",
        "",
        f"- **Name:** {code(v.name)}",
        f"- **Type:** {kind}" + (f": its deliverable is {v.deliverable}" if v.deliverable else ""),
        f"- **Purpose:** {v.purpose if v.purpose else NO_PURPOSE}",
        "",
        "### Folder layout",
        "",
    ]
    if not files:
        return [*lines, NONE]
    tree = _tree(v.name, files)
    if len(tree) > FOLD_AFTER * 2:
        summary = f"<summary>{_plural(len(files), 'file')}</summary>"
        return [*lines, "<details>", summary, "", "```text", *tree, "```", "", "</details>"]
    return [*lines, "```text", *tree, "```"]


def _verdict_words(v: Verdict) -> str:
    if v.portable is None:
        return f"{v.reason or NOT_CHECKED}."
    if v.portable:
        return "Runs on a Function App or a hosted Streamlit app." + (f" {v.reason}" if v.reason else "")
    instead = f" On a Function App or hosted Streamlit app use {v.instead}." if v.instead else ""
    return f"Only works on your machine: {v.reason}.{instead}"


def _source(s: SourceFacts) -> list[str]:
    what = s.type or s.kind
    lines = [f"- {code(s.name)}: {what}" + (f", signs in {s.sign_in}" if s.sign_in else "")]
    lines.append(f"  - Portability: {_verdict_words(s.verdict)}")
    if s.variables:
        lines.append("  - Needs: " + ", ".join(f"{code(x.name)} ({x.source})" for x in s.variables))
    if s.calls:
        lines.append(f"  - Web calls used: {_names(s.calls)}")
    if s.used_by:
        lines.append(f"  - Used by: {_names(s.used_by)}")
    return lines


def _sources(o: Outline) -> list[str]:
    if not o.sources:
        return [NONE]
    connections = [s for s in o.sources if not s.api]
    apis = [s for s in o.sources if s.api]
    counted = [(len(connections), "connection"), (len(apis), "API")]
    said = " and ".join(_plural(n, word) for n, word in counted if n)
    lines = [
        f"In short: the project reads from {said}. Each is named here; its password or key is found on each "
        "computer by its name, never kept in the project.",
        "",
    ]
    if connections:
        lines += ["### Connections", "", *_fold([x for s in connections for x in _source(s)], "lines")]
    if apis:
        lines += ["", "### APIs", "", *_fold([x for s in apis for x in _source(s)], "lines")]
    return lines


def _attribute(name: str) -> str:
    clean = re.sub(r"\W+", "_", name, flags=re.ASCII).strip("_") or "column"
    return clean if not clean[0].isdigit() else f"c_{clean}"


def _type(type_: str) -> str:
    return re.sub(r"\W+", "_", type_, flags=re.ASCII).strip("_") or "unknown"


def er_diagram(tables: Sequence[TableFacts], relationships: Sequence[RelationshipFacts]) -> str:
    """The tables and their relationships as a Mermaid erDiagram: each table an entity (its name as the
    label), its columns with their types; a many-to-one line from the many side to the one side."""
    ids = {t.name: f"T{i}" for i, t in enumerate(tables, start=1)}
    lines = ["erDiagram"]
    for t in tables:
        lines.append(f'  {ids[t.name]}["{mermaid_text(t.name)}"] {{')
        for column, type_ in (t.columns or ())[:MAX_COLUMNS]:
            attribute = _attribute(column)
            note = f' "{mermaid_text(column)}"' if attribute != column else ""
            lines.append(f"    {_type(type_)} {attribute}{note}")
        lines.append("  }")
    shapes = {
        "many-to-one": "}o--||",
        "one-to-many": "||--o{",
        "one-to-one": "||--||",
        "many-to-many": "}o--o{",
    }
    for r in relationships:
        if r.from_table not in ids or r.to_table not in ids:
            continue
        shape = shapes.get(r.kind, "}o--||")
        if not r.active:
            shape = shape.replace("--", "..")
        label = mermaid_text(", ".join(r.from_columns) + " to " + ", ".join(r.to_columns))
        lines.append(f'  {ids[r.from_table]} {shape} {ids[r.to_table]} : "{label}"')
    return "\n".join(lines)


def _model(o: Outline, related: Sequence[RelationshipFacts]) -> list[str]:
    if not o.tables:
        return [NONE]
    lines = [
        f"In short: {_plural(len(o.tables), 'table')} and {_plural(len(related), 'relationship')} among "
        "them. Columns are listed by name and type only.",
        "",
    ]
    for t in o.tables:
        lines.append(f"- {code(t.name)}: {t.origin}")
        if t.columns is None:
            lines.append("  - Columns: not read (the table is not open)")
        elif t.columns:
            shown = [f"{code(n)} {ty}" for n, ty in t.columns[:MAX_COLUMNS]]
            more = f", and {len(t.columns) - MAX_COLUMNS:,} more" if len(t.columns) > MAX_COLUMNS else ""
            lines.append(f"  - Columns: {', '.join(shown)}{more}")
    lines += ["", "### Relationships", ""]
    if not related:
        lines.append(NONE)
    else:
        rel_lines = [
            f"- {code(r.from_table)} ({_names(r.from_columns)}) to "
            f"{code(r.to_table)} ({_names(r.to_columns)}): {r.kind}{'' if r.active else ', inactive'}"
            for r in related
        ]
        lines += _fold(rel_lines, "relationships")
    drawn = [
        t
        for t in o.tables
        if t.columns is not None or any(t.name in (r.from_table, r.to_table) for r in related)
    ]
    if drawn:
        lines += ["", "```mermaid", er_diagram(drawn, related), "```"]
    return lines


def _transformations(o: Outline) -> list[str]:
    stepped = [t for t in o.tables if t.steps or t.query or t.problem]
    if not stepped and not o.cells:
        return [NONE]
    lines = [
        f"In short: {_plural(len(stepped), 'table')} {'is' if len(stepped) == 1 else 'are'} shaped by steps "
        f"(each as one DuckDB query over the table), and {_plural(len(o.cells), 'named cell')} in "
        "data.ipynb make or read the rest.",
        "",
    ]
    for t in stepped:
        lines += [f"### {code(t.name)}", ""]
        if t.problem:
            lines.append(f"A step cannot run: {code(t.problem)}")
        lines += [f"{n}. {code(words)}" for n, words in enumerate(t.steps, start=1)]
        if t.query:
            fence = "````" if "```" in t.query else "```"
            lines += ["", f"{fence}sql", t.query.rstrip("\n"), fence]
        lines.append("")
    if o.cells:
        lines += ["### Named cells", ""]
        cell_lines = [
            f"- {code(c.name)} ({code(c.document)} @cell{c.number}): "
            f"makes {_names(c.makes)}; reads {_names(c.reads)}"
            for c in o.cells
        ]
        lines += _fold(cell_lines, "cells")
    return lines[:-1] if lines and lines[-1] == "" else lines


# ----- the lineage: sources -> tables -> cells -> deliverables -----

_SHAPES: dict[str, tuple[str, str]] = {
    "source": ("[(", ")]"),
    "table": ("[[", "]]"),
    "cell": ("[", "]"),
    "deliverable": ("([", "])"),
}


@dataclass(frozen=True)
class Node:
    id: str
    kind: str  # source, table, cell, deliverable
    label: str


def lineage_graph(o: Outline) -> tuple[tuple[Node, ...], tuple[tuple[str, str], ...]]:
    """The project's flow as nodes and edges (by node id), in a stable order: sources, tables, cells,
    deliverables."""
    keys: dict[tuple[str, str], str] = {}
    nodes: list[Node] = []

    def node(kind: str, key: str, label: str) -> str:
        found = keys.get((kind, key.casefold()))
        if found is None and len(nodes) < MAX_NODES:
            found = f"n{len(nodes) + 1}"
            keys[(kind, key.casefold())] = found
            nodes.append(Node(found, kind, label))
        return found or ""

    for s in sorted(o.sources, key=lambda s: s.name.casefold()):
        node("source", s.name, s.name)
    for t in o.tables:
        if t.origin_kind == "file" and t.source:
            node("source", t.source, t.source)

    def file_id(name: str) -> str:
        """A file the code reads (its name as written), matched to a file source by its last part."""
        base = name.replace("\\", "/").rsplit("/", 1)[-1].casefold()
        found = [i for (kind, key), i in keys.items() if kind == "source" and key.rsplit("/", 1)[-1] == base]
        return found[0] if len(found) == 1 else ""

    for named in [c.sources for c in o.cells] + [d.sources for d in o.deliverables]:
        for kind, name in named:
            if kind == "file" and not file_id(name):
                node("source", name, name)
    for t in o.tables:
        node("table", t.name, t.name)
    for c in o.cells:
        node("cell", f"{c.document}@{c.number}", c.name)
    for d in o.deliverables:
        node("deliverable", f"{d.kind}:{d.name}", d.name)

    edges: dict[tuple[str, str], None] = {}

    def edge(a: str, b: str) -> None:
        if a and b and a != b:
            edges[(a, b)] = None

    def source_id(name: str) -> str:
        return keys.get(("source", name.casefold()), "")

    def table_id(name: str) -> str:
        return keys.get(("table", name.casefold()), "")

    variables = {t.variable: t.name for t in o.tables}
    made_by: dict[str, str] = {}
    for c in o.cells:
        cid = keys.get(("cell", f"{c.document}@{c.number}".casefold()), "")
        for name in c.makes:
            made_by.setdefault(name, cid)
    for t in o.tables:
        if t.source and t.origin_kind in ("connection", "file", "named"):
            edge(source_id(t.source), table_id(t.name))
        maker = made_by.get(t.variable)
        if maker:
            edge(maker, table_id(t.name))
    for c in o.cells:
        cid = keys.get(("cell", f"{c.document}@{c.number}".casefold()), "")
        for kind, name in c.sources:
            edge(source_id(name) if kind != "file" else file_id(name), cid)
        for name in c.reads:
            if name in variables and made_by.get(name) != cid:
                edge(table_id(variables[name]), cid)
            elif name in made_by:
                edge(made_by[name], cid)
    for d in o.deliverables:
        did = keys.get(("deliverable", f"{d.kind}:{d.name}".casefold()), "")
        for name in d.reads:
            if name in made_by:
                edge(made_by[name], did)
            elif name in variables:
                edge(table_id(variables[name]), did)
            elif name in {t.name for t in o.tables}:
                edge(table_id(name), did)
        for kind, name in d.sources:
            edge(source_id(name) if kind != "file" else file_id(name), did)
        for linked in d.links:
            edge(keys.get(("deliverable", f"notebook:{linked}".casefold()), ""), did)
            edge(keys.get(("deliverable", f"script:{linked}".casefold()), ""), did)
    return tuple(nodes), tuple(edges)


def flowchart(nodes: Sequence[Node], edges: Sequence[tuple[str, str]]) -> str:
    lines = ["flowchart LR"]
    for n in nodes:
        start, end = _SHAPES[n.kind]
        lines.append(f'  {n.id}{start}"{mermaid_text(n.label)}"{end}')
    lines += [f"  {a} --> {b}" for a, b in edges]
    return "\n".join(lines)


def _lineage(o: Outline) -> list[str]:
    nodes, edges = lineage_graph(o)
    if not nodes:
        return [NONE]
    lines = [
        "In short: data flows left to right, from the sources (cylinders) into the tables (double boxes), "
        "through data.ipynb's named cells (boxes), to what the project delivers (rounded).",
        "",
        "```mermaid",
        flowchart(nodes, edges),
        "```",
    ]
    if len(nodes) >= MAX_NODES:
        lines += ["", f"Only the first {MAX_NODES} steps are drawn."]
    return lines


def _deliverables(o: Outline) -> list[str]:
    if not o.deliverables:
        return [NONE]
    counts: dict[str, int] = {}
    for d in o.deliverables:
        counts[d.kind] = counts.get(d.kind, 0) + 1
    order = ("notebook", "script", "app", "api", "dashboard")
    words = {"api": "local sandbox API"}
    said = ", ".join(_plural(counts[k], words.get(k, k)) for k in order if k in counts)
    lines = [f"In short: {said}.", ""]
    headings = {
        "notebook": "Notebooks",
        "script": "Scripts",
        "app": "Apps",
        "api": "Local sandbox API",
        "dashboard": "Analyze dashboards",
    }
    for kind in order:
        listed = [d for d in o.deliverables if d.kind == kind]
        if not listed:
            continue
        lines += [f"### {headings[kind]}", ""]
        for d in listed:
            if kind == "dashboard":
                shows = ", ".join(d.makes) or "no cards"
                lines.append(f"- {code(d.name)}: reads {_names(d.reads)}; shows {shows} cards")
            elif kind == "api":
                lines.append(f"- {code(d.name)}: mocks {_names(d.reads)} over the sandbox; answers:")
                lines += [f"  - {code(m)}" for m in d.makes]
            elif kind == "app":
                lines.append(f"- {code(d.name)}: reads {_names(d.reads)}; links {_names(d.links)}")
            else:
                lines.append(f"- {code(d.name)}: reads {_names(d.reads)}; makes {_names(d.makes)}")
            for page in d.pages:
                lines.append(
                    f"  - Page {code(page.name)}: {_names(page.cells) if page.cells else 'no blocks yet'}"
                )
        lines.append("")
    return lines[:-1]


_UNPORTABLE: dict[str, str] = {
    "paste": "pasted into the app, so only its kept rows travel. Read it from a file in the project or a "
    "connection instead.",
    "outside": "a file outside the project folder. Copy it into the project, or read it from a connection.",
    "query": "a query typed in the app's + tab. Put it in data.ipynb.",
}


def _readiness(o: Outline) -> list[str]:
    """Each thing that decides whether it runs on a Function App or a hosted Streamlit app, ticked or not."""
    out: list[str] = []
    for s in sorted(o.sources, key=lambda s: s.name.casefold()):
        mark = "x" if s.verdict.portable else " "
        out.append(f"- [{mark}] {code(s.name)}: {_verdict_words(s.verdict)}")
    for t in o.tables:
        why = _UNPORTABLE.get("outside" if t.origin_kind == "file" and not t.source else t.origin_kind)
        if why:
            out.append(f"- [ ] {code(t.name)}: {why}")
    return out


def _running(o: Outline) -> list[str]:
    readiness = _readiness(o)
    if not o.packages and not o.scripts and not readiness:
        return [NONE]
    lines = [
        "In short: what to install, how each script runs, and whether it runs unchanged on an Azure Function "
        "App or a hosted Streamlit app.",
        "",
        "### Packages",
        "",
    ]
    lines += _fold([f"- {code(p)}" for p in o.packages], "packages") if o.packages else [NONE]
    lines += ["", "### Scripts", ""]
    if not o.scripts:
        lines.append(NONE)
    for s in o.scripts:
        given = f", given {_plural(s.arguments, 'argument')}" if s.arguments else ""
        lines.append(f"- {code(s.path)}: runs as `python {_plain(s.path.rsplit('/', 1)[-1])}`{given}")
        if s.variables:
            lines.append("  - Variables: " + ", ".join(f"{code(v.name)} ({v.source})" for v in s.variables))
    lines += ["", "### Ready for a Function App or a hosted Streamlit app", ""]
    lines += _fold(readiness, "items") if readiness else [NONE]
    return lines


def _issues(o: Outline) -> list[str]:
    i = o.issues
    local = [s for s in o.sources if s.verdict.portable is False]
    count = sum(n for _, n in i.problems)
    if not i.fixes and not i.passwords and not local and not count:
        return [NONE]
    lines = ["In short: what to sort out before the project is shared or deployed.", ""]
    items: list[str] = []
    items += [f"- Table {code(table)}: {words}" for table, words in i.fixes]
    items += [
        f"- Connection {code(name)} has no source on this computer for {_names(missing)}"
        for name, missing in i.passwords
    ]
    items += [f"- Connection {code(s.name)}: {_verdict_words(s.verdict)}" for s in local]
    items += [f"- {code(path)}: {_plural(n, 'problem')} (errors and warnings)" for path, n in i.problems if n]
    return lines + _fold(items, "issues")


def header(name: str) -> str:
    return f"""# {_heading(name)}: architecture

> For people joining this project: what it reads, what it makes and how it runs, in eight sections that
> are the same in every Swiss Army Bench project. Written by Export outline from the project as it is; it
> holds names, types and steps only, never a row, a value from the data, a secret or a path outside this
> folder. Every name in `code` came from the project's own data and sources.
"""


def _heading(name: str) -> str:
    """The project's name for the title: one line, nothing markdown would read as markup."""
    text = re.sub(r"[\x00-\x1f\x7f\u2028\u2029]+", " ", name).strip()[:120] or "Project"
    return re.sub(r"([\\`*_{}\[\]<>#|!])", r"\\\1", text)


def render(o: Outline) -> str:
    """The outline's text: the header, then the eight sections in order. The same facts, the same bytes."""
    names = {t.name for t in o.tables}
    related = [r for r in o.relationships if r.from_table in names and r.to_table in names]
    bodies = {
        "Overview": _overview(o),
        "Data sources": _sources(o),
        "Data model": _model(o, related),
        "Transformations": _transformations(o),
        "Lineage": _lineage(o),
        "Deliverables": _deliverables(o),
        "Running it": _running(o),
        "Open issues": _issues(o),
    }
    parts = [header(o.overview.name)]
    for number, section in enumerate(SECTIONS, start=1):
        parts.append(f"## {number}. {section}\n\n" + "\n".join(bodies[section]).rstrip("\n") + "\n")
    return "\n".join(parts)
