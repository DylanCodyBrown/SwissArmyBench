"""A dialect's name in sqlglot and its other names are written once, in domain/catalogs.py; this holds every
reader of them to it (the craft review of 2026-11-22: three full tables and two inline ones had drifted)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlglot

from swissarmybench.domain import (
    api_pattern_code,
    catalogs,
    connection_sql,
    intellisense,
    lakes,
    query_text,
    sandbox_dialects,
)
from swissarmybench.domain.api_scaffold import Source

DOMAIN = Path(catalogs.__file__).parent
ALIASES = sorted(catalogs._DIALECT_ALIASES.items())
BROKEN = "SELECT FROM WHERE ("  # no dialect reads this


def test_every_dialect_is_decided_once() -> None:
    """Each of catalogs.DIALECTS either has a name in sqlglot or is listed as one sqlglot never reads."""
    named = set(catalogs._SQLGLOT_NAMES)
    never = set(catalogs.NO_SQLGLOT)
    assert named | never == set(catalogs.DIALECTS)
    assert not named & never
    for word in catalogs.DIALECTS:
        assert (catalogs.sqlglot_name(word) is None) == (word in never)


@pytest.mark.parametrize("name", sorted(set(catalogs._SQLGLOT_NAMES.values())))
def test_each_name_is_one_sqlglot_knows(name: str) -> None:
    assert sqlglot.Dialect.get_or_raise(name) is not None


@pytest.mark.parametrize(("alias", "word"), ALIASES)
def test_an_alias_is_its_dialect_everywhere(alias: str, word: str) -> None:
    assert word in catalogs.DIALECTS
    assert alias not in catalogs.DIALECTS
    assert catalogs.normalize_dialect(alias.upper()) == word
    assert catalogs.sqlglot_name(alias) == catalogs.sqlglot_name(word)
    assert sandbox_dialects.dialect_of(alias) == word
    text = "select a, b from t where a = 1"
    assert query_text.format_sql(text, alias) == query_text.format_sql(text, word)
    assert intellisense.sql_problems(BROKEN, alias) == intellisense.sql_problems(BROKEN, word)
    source = Source("Warehouse", alias)
    assert api_pattern_code._dialect(source) == api_pattern_code._dialect(Source("Warehouse", word))


@pytest.mark.parametrize("word", sorted(catalogs._SQLGLOT_NAMES))
def test_every_reader_reads_a_named_dialect(word: str) -> None:
    """A dialect with a name is formatted, checked as typed, and its filters sent (or structured)."""
    text = "select a, b from t where a = 1"
    assert query_text.format_sql(text, word) != text
    assert intellisense.sql_problems(BROKEN, word), word
    assert intellisense.sql_problems("SELECT a FROM t", word) == []
    assert connection_sql._filter_dialect(word) in (catalogs.sqlglot_name(word), "structured")


@pytest.mark.parametrize("word", catalogs.NO_SQLGLOT)
def test_a_dialect_sqlglot_never_reads_is_left_alone(word: str) -> None:
    assert query_text.format_sql(BROKEN, word) == BROKEN
    assert intellisense.sql_problems(BROKEN, word) == []
    assert connection_sql._filter_dialect(word) in (None, "structured")


def test_structured_filters_are_the_lake_and_sharepoint_kinds() -> None:
    assert set(connection_sql._STRUCTURED) == set(lakes.KINDS)
    assert set(connection_sql._STRUCTURED) <= set(catalogs.DIALECTS)


def test_the_mock_reads_dialects_that_have_a_name() -> None:
    assert set(sandbox_dialects.PARAMSTYLE) == set(sandbox_dialects.WORDS) == set(sandbox_dialects.SQLGLOT)
    for word, name in sandbox_dialects.SQLGLOT.items():
        assert word in catalogs.DIALECTS
        assert name == catalogs.sqlglot_name(word)
    assert sandbox_dialects.dialect_of(None) == "duckdb"
    assert sandbox_dialects.dialect_of("  TSQL ") == "sqlserver"


def test_no_other_domain_file_keeps_a_table_of_its_own() -> None:
    """The table and the alias list are catalogs.py's alone: another file that maps a dialect to its sqlglot
    name, or one name to another, by hand is the drift this test is here for."""
    table = re.compile(
        r"""["'](?:sqlserver|mssql|postgresql|pg|tsql)["']\s*:\s*["'](?:tsql|sqlserver|postgres)["']"""
    )
    found = [
        f"{path.name}:{number}"
        for path in sorted(DOMAIN.glob("*.py"))
        if path.name != "catalogs.py"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if table.search(line)
    ]
    assert not found, found
