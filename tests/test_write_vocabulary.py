"""A write has three vocabularies: the adapter's modes, the Write starters' own words, and the Connections
page's operations (domain/write_capability.py WRITABLE). This holds them together (the craft review of
2026-11-22: WRITABLE's operations were tied to nothing, and had drifted from the starters)."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

import swissarmybench
from swissarmybench.adapters import adapter
from swissarmybench.client import write_sql
from swissarmybench.domain import write_capability as wc

STARTERS = Path(swissarmybench.__file__).parent / "starters"
FUNCTIONS = sorted(STARTERS.glob("write_to_*.blade.py"))
CALLS = sorted(p for p in STARTERS.glob("write_*.blade.py") if not p.name.startswith("write_to_"))


def _tags(text: str) -> list[str]:
    found = re.search(r"^# tags = (\[.*\])$", text, re.M)
    return list(ast.literal_eval(found.group(1))) if found else []


def _modes(text: str) -> tuple[list[str], dict[str, str]]:
    """A starter function's own modes (its MODES or _MODES: a tuple of words, or words to the adapter's
    modes) and any mapping to the adapter's it declares (_ADAPTER)."""
    words: list[str] = []
    mapped: dict[str, str] = {}
    for node in ast.parse(text).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name not in ("MODES", "_MODES", "_ADAPTER"):
            continue
        value: Any = ast.literal_eval(node.value)
        if isinstance(value, dict):
            mapped.update(value)
        if name != "_ADAPTER":
            words = list(value)
    return words, mapped


def test_every_operation_is_a_mode_or_a_starters_own() -> None:
    assert set(wc.OPERATION_MODES.values()) == set(adapter.MODES)
    assert not set(wc.OPERATION_MODES) & set(wc.STARTER_ONLY)
    for kind, found in wc.WRITABLE.items():
        assert set(found.modes) <= set(adapter.MODES), kind
        assert [m for m in adapter.MODES if m in found.modes] == list(found.modes), (
            kind
        )  # the adapter's order
        for operation in found.operations:
            if operation in wc.STARTER_ONLY:
                continue
            assert operation in wc.OPERATION_MODES, f"{kind}: {operation} is no mode and no starter's own"
            assert wc.OPERATION_MODES[operation] in found.modes, f"{kind}: {operation}"


def test_the_sql_starters_words_are_the_same_table() -> None:
    for word, mode in write_sql.ADAPTER_MODES.items():
        assert wc.OPERATION_MODES[word] == mode


@pytest.mark.parametrize("path", FUNCTIONS, ids=lambda p: p.name.split(".")[0])
def test_a_starters_modes_are_its_kinds_operations(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    kinds = [t for t in _tags(text) if t in wc.WRITABLE]
    assert kinds, f"{path.name} names no writable kind"
    words, mapped = _modes(text)
    for word, mode in mapped.items():
        assert wc.OPERATION_MODES[word] == mode, f"{path.name}: {word}"
    for word in words:
        assert word in wc.OPERATION_MODES or word in wc.STARTER_ONLY, f"{path.name}: {word}"
        for kind in kinds:
            assert word in wc.WRITABLE[kind].operations, f"{kind} does not say {word} ({path.name})"


def test_a_kinds_operations_are_ones_a_starter_of_its_has() -> None:
    """Where every starter of a kind declares its modes, the kind says exactly those (no operation nobody
    does); a kind with a starter that takes no mode (a file put in its place) may say more."""
    declared: dict[str, set[str]] = {}
    open_ended: set[str] = set()
    for path in FUNCTIONS:
        text = path.read_text(encoding="utf-8")
        words, _ = _modes(text)
        for kind in (t for t in _tags(text) if t in wc.WRITABLE):
            if words:
                declared.setdefault(kind, set()).update(words)
            else:
                open_ended.add(kind)
    assert declared, "no starter declares its modes"
    for kind, done in declared.items():
        if kind not in open_ended:
            assert set(wc.WRITABLE[kind].operations) == done, kind


@pytest.mark.parametrize("path", CALLS, ids=lambda p: p.name.split(".")[0])
def test_a_calls_mode_comment_names_operations(path: Path) -> None:
    """A call starter's `mode="<<mode: append>>",  # append, create...` lists its kind's operations."""
    text = path.read_text(encoding="utf-8")
    found = re.search(r'mode="<<mode: (\w+)>>",\s*#\s*(.+)$', text, re.M)
    if not found:
        return
    kinds = [t for t in _tags(text) if t in wc.WRITABLE]
    said = re.sub(r"\([^)]*\)", "", found.group(2))
    words = [w for w in re.split(r"[,\s]+|\bor\b", said) if w and w != "or"]
    assert found.group(1) in words
    for word in words:
        assert any(word in wc.WRITABLE[k].operations for k in kinds), f"{path.name}: {word}"


def test_the_words_say_both_lists() -> None:
    delta = wc.capability("delta", tables_kind="delta")
    assert delta["operations"] == ["append", "overwrite", "merge", "delete", "optimize", "vacuum"]
    assert delta["modes"] == list(adapter.MODES)
    assert delta["words"].startswith(
        "Writes: append, overwrite, merge, delete, optimize, vacuum with its Write starters; "
        "insert, update, merge, delete, truncate with sab.write"
    )
    csv = wc.capability("csv")
    assert csv["modes"] == ["insert", "truncate"] and csv["words"].endswith("insert, truncate with sab.write")
    assert wc.capability("duckdb")["modes"] == []


def test_a_file_takes_only_the_whole_modes_in_the_adapter(tmp_path: Path) -> None:
    """WHOLE_MODES is what the adapter's Files source really takes: a keyed mode is refused."""
    import pyarrow as pa

    rows = pa.table({"id": [1, 2], "name": ["a", "b"]})
    target = tmp_path / "people.csv"
    source = adapter.source_from(str(target))
    for mode in wc.WHOLE_MODES:
        adapter.write(source, "people.csv", rows, mode=mode)
    for mode in set(adapter.MODES) - set(wc.WHOLE_MODES):
        with pytest.raises(adapter.AdapterError):
            adapter.write(source, "people.csv", rows, key=("id",), mode=mode)
