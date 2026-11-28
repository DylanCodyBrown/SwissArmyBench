"""Where M differs from SQL, duckpq writes M's meaning. Each test works on a column's values, so DuckDB (not
Python) computes the answer. Imports only duckpq, duckdb and the standard library."""

from __future__ import annotations

import math
from typing import Any

import duckpq

T = (
    "#table(type table [a = Int64.Type, b = Int64.Type, t = text, x = number], {"
    '{7, 2, "apple", 0.5}, {-7, 2, "Banana", 1.5}, {null, null, null, 2.5}, {1, 0, "banana", -2.5}})'
)


def column(expression: str) -> list[Any]:
    return [r[4] for r in duckpq.run(f'Table.AddColumn({T}, "v", each {expression})')["Query"].fetchall()]


def kept(test: str) -> list[Any]:
    return [r[0] for r in duckpq.run(f"Table.SelectRows({T}, each {test})")["Query"].fetchall()]


def test_null_equals_null() -> None:
    """learn.microsoft.com/powerquery-m/m-spec-operators (equality): null = null is true, null = 1 is false;
    SQL's = would give null for both."""
    assert column("[a] = null") == [False, False, True, False]
    assert column("[a] = [b]") == [False, False, True, False]
    assert column("[a] <> null") == [True, True, False, True]
    assert kept("[a] = null") == [None]
    assert kept("[a] <> 7") == [-7, None, 1]


def test_a_comparison_with_null_is_null_and_filters_the_row_out() -> None:
    assert column("[a] > 0") == [True, False, None, True]
    assert kept("[a] > 0") == [7, 1]


def test_text_compares_by_code_point_and_by_case() -> None:
    """M's default comparer is ordinal: "Banana" < "apple" (B is 66, a is 97) and "banana" is not "Banana"."""
    assert column('[t] < "apple"') == [False, True, None, False]
    assert column('[t] = "banana"') == [False, False, False, True]
    ordered = duckpq.run(f'Table.Sort({T}, "t")')["Query"].fetchall()
    assert [r[2] for r in ordered] == [None, "Banana", "apple", "banana"]


def test_a_sort_puts_null_first_going_up_and_last_going_down() -> None:
    up = duckpq.run(f'Table.Sort({T}, {{"a", Order.Ascending}})')["Query"].fetchall()
    down = duckpq.run(f'Table.Sort({T}, {{"a", Order.Descending}})')["Query"].fetchall()
    assert [r[0] for r in up] == [None, -7, 1, 7]
    assert [r[0] for r in down] == [7, 1, -7, None]


def test_text_contains_is_case_sensitive() -> None:
    """learn.microsoft.com/powerquery-m/text-contains: case-sensitive unless a comparer says otherwise."""
    assert column('Text.Contains([t], "b")') == [False, False, None, True]
    assert column('Text.Contains([t], "b", Comparer.OrdinalIgnoreCase)') == [False, True, None, True]
    assert column('Text.StartsWith([t], "B")') == [False, True, None, False]


def test_division_is_never_integer_division() -> None:
    """7 / 2 is 3.5 in M even between whole numbers; a division by zero is infinity, not an error."""
    got = column("[a] / [b]")
    assert got[:3] == [3.5, -3.5, None] and math.isinf(got[3])
    assert column("Number.IntegerDivide([a], 2)") == [3, -3, None, 0]  # toward zero, not floor (-4)


def test_number_round_rounds_halves_to_even() -> None:
    """learn.microsoft.com/powerquery-m/number-round: the default RoundingMode is ToEven (banker's)."""
    assert column("Number.Round([x])") == [0, 2, 2, -2]
    assert column("Number.Round([x], 0, RoundingMode.AwayFromZero)") == [1, 2, 3, -3]
    assert column("Int64.From([x])") == [0, 2, 2, -2]


def test_positions_count_from_zero() -> None:
    """Text.Middle, Text.PositionOf and {n} count from 0 where SQL's substr and instr count from 1."""
    assert column("Text.Middle([t], 1, 3)") == ["ppl", "ana", None, "ana"]
    assert column('Text.PositionOf([t], "a")') == [0, 1, None, 1]
    assert column("Text.At([t], 0)") == ["a", "B", None, "b"]
    first = duckpq.run(f'Table.AddColumn(#table({{"k"}}, {{{{1}}}}), "v", each {T}{{0}}[t])')[
        "Query"
    ].fetchall()
    assert first == [(1, "apple")]
    assert duckpq.run('#table({"v"}, {{ {10, 20, 30}{0} }})')["Query"].fetchall() == [(10,)]


def test_text_concatenation_with_null_is_null() -> None:
    assert column('[t] & "!"') == ["apple!", "Banana!", None, "banana!"]


def test_list_count_counts_nulls_and_list_sum_skips_them() -> None:
    made = duckpq.run(
        f'Table.Group({T}, {{}}, {{{{"count", each List.Count([a])}}, {{"filled", each List.NonNullCount([a])}}, '
        '{"sum", each List.Sum([a])}})'
    )["Query"].fetchall()
    assert made == [(4, 3, 1)]


def test_list_contains_never_answers_null() -> None:
    assert column("List.Contains({7, 1}, [a])") == [True, False, False, True]
    assert column("List.Contains({7, null}, [a])") == [True, False, True, False]


def test_try_otherwise_null_per_row_and_any_other_is_refused() -> None:
    assert column("try Number.From([t]) otherwise null") == [None, None, None, None]
    (problem,) = duckpq.check(f'Table.AddColumn({T}, "v", each try Number.From([t]) otherwise 0)')
    assert "otherwise null" in problem.message and problem.name == "try"


def test_plain_values_follow_the_same_rules() -> None:
    """What is worked out while compiling (no row in it) answers as the SQL would."""
    made = duckpq.run(
        'let a = null = null, b = "B" < "a", c = 7 / 2, d = Number.Round(2.5), e = 1 / 0 > 1000 in '
        '#table({"a", "b", "c", "d", "e"}, {{a, b, c, d, e}})'
    )["Query"].fetchall()
    assert made == [(True, True, 3.5, 2, True)]
