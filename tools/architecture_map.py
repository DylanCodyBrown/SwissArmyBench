"""The architecture map: what really imports what, drawn and measured (the owner asked for it after Robert
Martin's diagrams, 2026-11-22). It reads the imports of `src/swissarmybench` and of every extension with
`ast` (nothing is imported or run) and writes docs/architecture-map.md:

  (a) a Mermaid flowchart of the components (the base's layers and its other folders, each extension a box)
      with an arrow for every dependency and how many imports make it;
  (b) a table of each component's couplings: afferent Ca (modules outside that depend on it), efferent Ce
      (modules outside that it depends on), instability I = Ce / (Ca + Ce), abstractness A (the share of
      its classes that are a Protocol or an abstract base class) and its distance from the main sequence
      D = |A + I - 1|;
  (c) the import cycles between modules: the ones Python meets while a module loads (none allowed: the
      test refuses one), and the ones that close only through an import inside a function.

    python tools/architecture_map.py            # writes docs/architecture-map.md
    python tools/architecture_map.py --check    # says whether the file is current (exit 1 when it is not)

Standard library only. The same code gives the same bytes (everything sorted, no date, no machine's path), so
tests/test_architecture_map.py compares the file with what the code says now.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "swissarmybench"
TARGET = ROOT / "docs" / "architecture-map.md"
# The base's components in the order of the dependency rule (REFACTOR.md): a lower number is further in.
# An arrow from a lower number to a higher one points outward, against the rule.
RANK: dict[str, int] = {
    "settings": 0,
    "domain": 0,
    "services": 1,
    "adapters": 2,
    "server": 2,
    "client": 2,
    "cli": 2,
    "mcp": 3,
    "root": 2,
    "bootstrap": 3,
}
WORDS: dict[str, str] = {
    "domain": "the model and its rules",
    "services": "the use cases",
    "adapters": "the driven edge: DuckDB, files, the keyring",
    "server": "the HTTP door and what starts a process",
    "client": "the plain client and the kernel's helpers",
    "cli": "the agent's commands",
    "mcp": "the MCP server",
    "settings": "every limit, one frozen record",
    "root": "the package's own modules: its public face, stats, sab_excel, extensions",
    "bootstrap": "the composition root",
}
ABSTRACT_BASES = {"Protocol", "ABC", "ABCMeta"}
EXTENSION_RANK = 4


@dataclass
class Module:
    name: str  # swissarmybench.domain.steps
    path: Path
    is_package: bool
    loads: set[str] = field(default_factory=set)  # imported while the module loads
    later: set[str] = field(default_factory=set)  # imported inside a function, or for type checking only
    classes: int = 0
    abstract: int = 0


def packages() -> list[tuple[str, Path]]:
    """The base package and each extension's, by name."""
    found = [(BASE, ROOT / "src" / BASE)]
    for home in sorted((ROOT / "extensions").glob("*/src/swissarmybench_*")):
        if home.is_dir():
            found.append((home.name, home))
    return found


def component(module: str) -> str:
    """The box a module is drawn in: the base's folder (root: its own modules; bootstrap and settings each
    alone), or its extension."""
    parts = module.split(".")
    if parts[0] != BASE:
        return "ext:" + parts[0].removeprefix(BASE + "_")
    if len(parts) == 1:
        return "root"
    if parts[1] in ("bootstrap", "settings"):
        return parts[1]
    return parts[1] if parts[1] in RANK else "root"


def rank(box: str) -> int:
    return EXTENSION_RANK if box.startswith("ext:") else RANK[box]


def read_modules() -> dict[str, Module]:
    """Every importable module of the packages (a starter or a widget, `x.blade.py`, is not one)."""
    modules: dict[str, Module] = {}
    for package, home in packages():
        for path in sorted(home.rglob("*.py")):
            relative = path.relative_to(home).with_suffix("")
            parts = list(relative.parts)
            if any(not part.isidentifier() for part in parts):
                continue
            is_package = parts[-1] == "__init__"
            if is_package:
                parts = parts[:-1]
            name = ".".join([package, *parts])
            modules[name] = Module(name, path, is_package)
    for module in modules.values():
        _read(module, modules)
    return modules


def _resolved(module: Module, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    parts = module.name.split(".")
    base = parts if module.is_package else parts[:-1]
    base = base[: len(base) - (node.level - 1)]
    return ".".join([*base, *(node.module.split(".") if node.module else [])])


def _targets(module: Module, node: ast.AST, known: dict[str, Module]) -> set[str]:
    """The known modules one import statement names (`from a import b`: a.b when it is a module, else a)."""
    found: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            name = alias.name
            while name and name not in known:
                name = name.rpartition(".")[0]
            if name:
                found.add(name)
    elif isinstance(node, ast.ImportFrom):
        source = _resolved(module, node)
        for alias in node.names:
            name = f"{source}.{alias.name}"
            if name in known:
                found.add(name)
            elif source in known:
                found.add(source)
    found.discard(module.name)
    return found


def _is_type_checking(node: ast.If) -> bool:
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _read(module: Module, known: dict[str, Module]) -> None:
    tree = ast.parse(module.path.read_text(encoding="utf-8"))

    def walk(nodes: list[ast.stmt], loading: bool) -> None:
        for node in nodes:
            if isinstance(node, ast.Import | ast.ImportFrom):
                (module.loads if loading else module.later).update(_targets(module, node, known))
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                walk(node.body, False)
            elif isinstance(node, ast.ClassDef):
                module.classes += 1
                module.abstract += _is_abstract(node)
                walk(node.body, loading)
            elif isinstance(node, ast.If):
                walk(node.body, loading and not _is_type_checking(node))
                walk(node.orelse, loading)
            elif isinstance(node, ast.Try):
                for body in (node.body, node.orelse, node.finalbody, *(h.body for h in node.handlers)):
                    walk(body, loading)
            elif isinstance(node, ast.With | ast.AsyncWith | ast.For | ast.AsyncFor | ast.While):
                walk(node.body, loading)
                walk(getattr(node, "orelse", []), loading)

    walk(tree.body, True)
    module.later -= module.loads


def _is_abstract(node: ast.ClassDef) -> bool:
    """A Protocol, an abstract base class, or a class with an abstract method."""
    for base in node.bases:
        inner = base.value if isinstance(base, ast.Subscript) else base
        name = (
            inner.id
            if isinstance(inner, ast.Name)
            else inner.attr
            if isinstance(inner, ast.Attribute)
            else ""
        )
        if name in ABSTRACT_BASES:
            return True
    for item in node.body:
        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            for decorator in item.decorator_list:
                name = (
                    decorator.id
                    if isinstance(decorator, ast.Name)
                    else decorator.attr
                    if isinstance(decorator, ast.Attribute)
                    else ""
                )
                if name == "abstractmethod":
                    return True
    return False


# ===== the measures =====


@dataclass(frozen=True)
class Measure:
    box: str
    modules: int
    afferent: int  # Ca: modules outside that depend on it
    efferent: int  # Ce: modules outside that it depends on
    classes: int
    abstract: int

    @property
    def instability(self) -> float:
        total = self.afferent + self.efferent
        return self.efferent / total if total else 0.0

    @property
    def abstractness(self) -> float:
        return self.abstract / self.classes if self.classes else 0.0

    @property
    def distance(self) -> float:
        return abs(self.abstractness + self.instability - 1)


def boxes(modules: dict[str, Module]) -> list[str]:
    found = {component(name) for name in modules}
    base = sorted((b for b in found if not b.startswith("ext:")), key=lambda b: (RANK[b], b))
    return base + sorted(b for b in found if b.startswith("ext:"))


def edges(modules: dict[str, Module]) -> dict[tuple[str, str], int]:
    """Component to component: how many (module, module) imports make each arrow."""
    count: dict[tuple[str, str], int] = defaultdict(int)
    for module in modules.values():
        source = component(module.name)
        for target in module.loads | module.later:
            box = component(target)
            if box != source:
                count[(source, box)] += 1
    return dict(count)


def measures(modules: dict[str, Module]) -> list[Measure]:
    out = []
    for box in boxes(modules):
        inside = {name for name in modules if component(name) == box}
        afferent = {m.name for m in modules.values() if m.name not in inside and (m.loads | m.later) & inside}
        efferent = {
            t for name in inside for t in modules[name].loads | modules[name].later if t not in inside
        }
        out.append(
            Measure(
                box,
                len(inside),
                len(afferent),
                len(efferent),
                sum(modules[name].classes for name in inside),
                sum(modules[name].abstract for name in inside),
            )
        )
    return out


def cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """The groups of modules that import each other in a ring (Tarjan's strongly connected components of
    more than one module), each sorted, the groups sorted."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: list[list[str]] = []
    counter = 0
    for start in sorted(graph):
        if start in index:
            continue
        work: list[tuple[str, list[str]]] = [(start, sorted(graph.get(start, ())))]
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, rest = work[-1]
            if rest:
                target = rest.pop()
                if target not in index:
                    index[target] = low[target] = counter
                    counter += 1
                    stack.append(target)
                    on_stack.add(target)
                    work.append((target, sorted(graph.get(target, ()))))
                elif target in on_stack:
                    low[node] = min(low[node], index[target])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                group = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.append(member)
                    if member == node:
                        break
                if len(group) > 1:
                    found.append(sorted(group))
    return sorted(found)


def loading_cycles(modules: dict[str, Module]) -> list[list[str]]:
    """Cycles Python meets while a module loads (imports at the top of a module)."""
    return cycles({name: set(module.loads) for name, module in modules.items()})


def deferred_cycles(modules: dict[str, Module]) -> list[list[str]]:
    """Cycles that close only through an import inside a function (or for type checking): no trouble while
    loading, still two modules that know each other."""
    every = cycles({name: module.loads | module.later for name, module in modules.items()})
    loading = {tuple(group) for group in loading_cycles(modules)}
    return [group for group in every if tuple(group) not in loading]


# ===== the page =====


def _node(box: str) -> str:
    return box.replace(":", "_")


def _label(box: str, modules: int) -> str:
    name = box.removeprefix("ext:")
    return f"{name}<br/>{modules} module{'' if modules == 1 else 's'}"


def flowchart(modules: dict[str, Module]) -> list[str]:
    found = measures(modules)
    count = {m.box: m.modules for m in found}
    lines = ["```mermaid", "flowchart TB"]
    lines.append('    subgraph base["swissarmybench (the base)"]')
    for box in boxes(modules):
        if not box.startswith("ext:"):
            lines.append(f'        {_node(box)}["{_label(box, count[box])}"]')
    lines.append("    end")
    lines.append('    subgraph extensions["extensions"]')
    for box in boxes(modules):
        if box.startswith("ext:"):
            lines.append(f'        {_node(box)}["{_label(box, count[box])}"]')
    lines.append("    end")
    for (source, target), number in sorted(edges(modules).items()):
        arrow = "-.->" if rank(source) < rank(target) else "-->"
        lines.append(f"    {_node(source)} {arrow}|{number}| {_node(target)}")
    lines.append("```")
    return lines


def outward(modules: dict[str, Module]) -> list[str]:
    """The arrows that point outward (from a component further in to one further out), with the modules
    that make them."""
    found: dict[tuple[str, str], list[str]] = defaultdict(list)
    for module in sorted(modules.values(), key=lambda m: m.name):
        source = component(module.name)
        for target in sorted(module.loads | module.later):
            box = component(target)
            if box != source and rank(source) < rank(box):
                where = "" if target in module.loads else " (inside a function)"
                found[(source, box)].append(f"`{module.name}` imports `{target}`{where}")
    lines = []
    for (source, target), made in sorted(found.items()):
        lines.append(f"- **{source} → {target}** ({len(made)}):")
        lines.extend(f"  - {line}" for line in made)
    return lines


def most_depended(modules: dict[str, Module], most: int = 15) -> list[tuple[str, int]]:
    count: dict[str, int] = defaultdict(int)
    for module in modules.values():
        for target in module.loads | module.later:
            count[target] += 1
    return sorted(count.items(), key=lambda item: (-item[1], item[0]))[:most]


def render(modules: dict[str, Module] | None = None) -> str:
    modules = modules if modules is not None else read_modules()
    lines = [
        "# The architecture map",
        "",
        "Made by `python tools/architecture_map.py` from the real imports of `src/swissarmybench` and every",
        "extension (read with `ast`; nothing is run). Do not edit it by hand: run the tool again after a",
        "change to what imports what. `tests/test_architecture_map.py` refuses a stale file and an import",
        "cycle.",
        "",
        "## The components and what depends on what",
        "",
        "Each box is a component: a folder of the base (its layers after REFACTOR.md; `root` is the package's",
        "own modules, `bootstrap` the composition root, `settings` the limits) or a whole extension. An arrow",
        "goes from the component",
        "that imports to the one it imports, with the number of module-to-module imports that make it. A solid",
        "arrow points inward or sideways, as the dependency rule asks; a dotted one points outward (listed",
        "below the picture).",
        "",
        *flowchart(modules),
        "",
        "### Arrows that point outward",
        "",
        "From a component further in to one further out (settings, domain 0; services 1; adapters, server,",
        "client, cli, root 2; mcp, bootstrap 3; an extension 4). `tests/test_architecture.py` is what enforces the layers;",
        "this list is everything the picture draws dotted, including what that test allows on purpose (the",
        "plain client borrowing a rule, the server starting the composition root).",
        "",
        *(outward(modules) or ["None."]),
        "",
        "## The couplings (Robert Martin's component measures)",
        "",
        "- **Ca** (afferent): modules outside the component that depend on it. **Ce** (efferent): modules",
        "  outside that it depends on. Only this repository's code is counted, never a library.",
        "- **I** = Ce / (Ca + Ce): 0 is stable (much depends on it, it depends on little), 1 is free to change.",
        "- **A**: the share of its classes that are a `Protocol`, an abstract base class or have an abstract",
        "  method. **D** = |A + I - 1|: the distance from the line where stable things are abstract and",
        "  changeable things are concrete; 0 is on it.",
        "",
        "Read with care: the domain here is functions and frozen records far more than classes, so its A is",
        "low by design and its D says little; the measure bites for the components that hold ports.",
        "",
        "| Component | What it is | Modules | Ca | Ce | I | Classes | Abstract | A | D |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in measures(modules):
        words = WORDS.get(m.box, "an extension")
        lines.append(
            f"| {m.box.removeprefix('ext:')} | {words} | {m.modules} | {m.afferent} | {m.efferent} | "
            f"{m.instability:.2f} | {m.classes} | {m.abstract} | {m.abstractness:.2f} | {m.distance:.2f} |"
        )
    lines += [
        "",
        "### The modules most depended on",
        "",
        "| Module | Modules that import it |",
        "|---|---:|",
        *(f"| `{name}` | {number} |" for name, number in most_depended(modules)),
        "",
        "## Import cycles between modules",
        "",
        "### While loading",
        "",
        "Modules that import each other at their top, so one meets the other half made. None is allowed.",
        "",
    ]
    loading = loading_cycles(modules)
    lines += [f"- {' ⇄ '.join(f'`{name}`' for name in group)}" for group in loading] or ["None."]
    lines += [
        "",
        "### Only through an import inside a function",
        "",
        "Rings that close through an import made when a function runs (or for type checking only): nothing",
        "breaks while loading, but the modules know each other. Each group is listed whole.",
        "",
    ]
    deferred = deferred_cycles(modules)
    for number, group in enumerate(deferred, 1):
        lines.append(f"- Group {number} ({len(group)} modules):")
        lines.extend(f"  - `{name}`" for name in group)
    if not deferred:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main(arguments: list[str]) -> int:
    text = render()
    if "--check" in arguments:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print("docs/architecture-map.md is stale: run python tools/architecture_map.py")
            return 1
        print("docs/architecture-map.md is current.")
        return 0
    if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != text:
        TARGET.write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {TARGET.relative_to(ROOT)}.")
    else:
        print("docs/architecture-map.md is already current.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
