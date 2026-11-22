"""The architecture map (tools/architecture_map.py -> docs/architecture-map.md): no module imports another
in a ring while loading, and the committed page is what the code says now. A stale page is fixed by running
`python tools/architecture_map.py`; this test only compares, it never writes."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from tools import architecture_map as amap

MODULES = amap.read_modules()


def test_no_module_imports_another_in_a_ring_while_loading() -> None:
    assert amap.loading_cycles(MODULES) == []


def test_the_page_is_current() -> None:
    text = amap.render(MODULES)
    assert amap.TARGET.exists(), "run: python tools/architecture_map.py"
    assert amap.TARGET.read_text(encoding="utf-8") == text, (
        "docs/architecture-map.md is stale (what imports what changed): run python tools/architecture_map.py"
    )


def test_the_same_code_gives_the_same_bytes() -> None:
    again = amap.render(amap.read_modules())
    assert again == amap.render(MODULES)
    assert str(amap.ROOT) not in again  # no path of this machine, no date: only what the code says


def test_it_reads_the_base_and_every_extension() -> None:
    found = set(amap.boxes(MODULES))
    assert {"domain", "services", "adapters", "server", "bootstrap", "settings"} <= found
    extensions = {p.parent.parent.name for p in (amap.ROOT / "extensions").glob("*/src/swissarmybench_*")}
    assert {f"ext:{name}" for name in extensions} <= found
    assert "swissarmybench.domain.steps" in MODULES and "swissarmybench.bootstrap" in MODULES
    assert not [name for name in MODULES if name.endswith((".blade", ".widget"))]  # not modules


def test_the_measures_are_martins() -> None:
    by = {m.box: m for m in amap.measures(MODULES)}
    domain = by["domain"]
    assert domain.efferent == 0 and domain.instability == 0.0  # nothing in the domain looks outward
    assert by["bootstrap"].instability > 0.9  # the composition root depends on everything
    for m in by.values():
        assert 0.0 <= m.instability <= 1.0 and 0.0 <= m.abstractness <= 1.0
        assert m.distance == abs(m.abstractness + m.instability - 1)
        if m.afferent + m.efferent:
            assert m.instability == m.efferent / (m.afferent + m.efferent)
    assert by["services"].abstract > 50  # its ports are Protocols


def test_a_ring_is_found_and_an_import_inside_a_function_is_not_a_loading_one() -> None:
    assert amap.cycles({"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}, "e": set()}) == [["a", "b", "c"]]
    assert amap.cycles({"a": {"b"}, "b": set()}) == []
    assert amap.cycles({"a": {"b"}, "b": {"a"}, "c": {"d"}, "d": {"c"}}) == [["a", "b"], ["c", "d"]]
    every = {tuple(group) for group in amap.deferred_cycles(MODULES)}
    assert not every & {tuple(group) for group in amap.loading_cycles(MODULES)}


def test_the_tool_needs_only_the_standard_library() -> None:
    tree = ast.parse(Path(amap.__file__).read_text(encoding="utf-8"))
    imported = {
        (node.module or "").split(".")[0] if isinstance(node, ast.ImportFrom) else alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert imported <= set(sys.stdlib_module_names)
