"""Where M differs from SQL, duckpq writes M's meaning. Each test works on a column's values, so DuckDB (not
Python) computes the answer. Imports only duckpq, duckdb and the standard library."""

from __future__ import annotations

import math
from typing import Any

import duckdb
import pytest

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


# ----- try ... otherwise per row (1.1.0) -----
#
# learn.microsoft.com/powerquery-m/m-spec-error-handling: `try x otherwise y` is y when x raises an error, and
# x's own value when it does not: a null that is no error stays null.

S = (
    "#table(type table [s = text, u = text, n = Int64.Type], {"
    '{"12", "1", 1}, {"x", "7", 2}, {null, "3", 3}, {"2.5", "4", 0}, {"y", "z", 5}})'
)


def tried(expression: str) -> list[Any]:
    return [r[3] for r in duckpq.run(f'Table.AddColumn({S}, "v", each {expression})')["Query"].fetchall()]


def tried_sql(expression: str) -> str:
    return duckpq.to_sql(f'Table.AddColumn({S}, "v", each {expression})')["Query"]


def test_try_otherwise_an_error_row_takes_the_otherwise_value_and_a_good_row_keeps_its_own() -> None:
    assert tried("try Number.From([s]) otherwise 0")[:2] == [12.0, 0.0]
    assert tried("try Number.From([s]) otherwise 0")[3:] == [2.5, 0.0]
    assert tried("try Number.From([s]) * 2 otherwise -1")[:2] == [24.0, -1.0]
    assert tried("try Date.From([s]) otherwise #date(2000, 1, 1)")[1].isoformat() == "2000-01-01"


def test_try_otherwise_a_null_that_is_no_error_stays_null_as_in_m() -> None:
    """The row whose s is null: Number.From(null) is null and no error, so M answers null, not the otherwise
    value. Both shapes keep it: a conversion of a column (TRY_CAST), and any other expression (TRY of a list)."""
    assert tried("try Number.From([s]) otherwise 0")[2] is None
    assert tried("try Number.From([s]) * 2 otherwise -1")[2] is None
    assert tried("try Number.From([s]) otherwise [n]") == [12.0, 2.0, None, 2.5, 5.0]


def test_try_otherwise_how_it_compiles() -> None:
    cast = tried_sql("try Number.From([s]) otherwise 0")
    assert 'CASE WHEN "s" IS NULL THEN NULL ELSE COALESCE(TRY_CAST("s" AS DOUBLE), 0) END' in cast
    other = tried_sql("try Number.From([s]) * 2 otherwise -1")
    assert "CASE WHEN TRY(list_transform([0], lambda duckpq_tried: " in other
    assert "IS NULL THEN -1 ELSE list_extract(TRY(list_transform([0], lambda duckpq_tried: " in other
    assert 'TRY_CAST("s" AS DOUBLE) AS "v"' in tried_sql("try Number.From([s]) otherwise null")
    assert tried("try Number.From([s]) otherwise null") == [12.0, None, None, 2.5, None]
    assert tried("try Number.From([s]) * 2 otherwise null") == [24.0, None, None, 5.0, None]


def test_try_catches_a_part_that_appears_twice_in_the_step() -> None:
    """DuckDB 2.0.0 works a part of an expression that appears twice in a SELECT out once, outside its TRY:
    `SELECT TRY(CAST(s AS DOUBLE) + CAST(s AS DOUBLE))` raises on a text that is no number. The tried
    expression is compiled inside a lambda, which is left whole."""
    assert tried("try Number.From([s]) + Number.From([s]) otherwise -1") == [24.0, -1.0, None, 5.0, -1.0]
    assert tried("try Number.From([s]) + Number.From([s]) otherwise null") == [24.0, None, None, 5.0, None]
    two = "(try Number.From([s]) + 1 otherwise 0) + (try Number.From([s]) * 2 otherwise 0)"
    assert tried(two) == [37.0, 0.0, None, 8.5, 0.0]


def test_try_otherwise_nested() -> None:
    """The inner otherwise fails too on the last row: the outer one answers for it."""
    inner = "try Number.From([s]) otherwise Number.From([u])"
    assert tried(f"try ({inner}) otherwise -5") == [12.0, 7.0, None, 2.5, -5.0]
    assert tried(f"try ({inner}) + Number.From([u]) otherwise -5") == [13.0, 14.0, None, 6.5, -5.0]
    assert tried("try Number.From([u]) + (try Number.From([s]) otherwise 100) otherwise -5") == [
        13.0,
        107.0,
        None,
        6.5,
        -5.0,
    ]


def test_try_otherwise_in_a_filter_and_in_a_column_transform() -> None:
    kept_rows = duckpq.run(f"Table.SelectRows({S}, each (try Number.From([s]) otherwise 0) > 2)")
    assert [r[0] for r in kept_rows["Query"].fetchall()] == ["12", "2.5"]
    made = duckpq.run(f'Table.TransformColumns({S}, {{{{"s", each try Number.From(_) otherwise -1}}}})')
    assert [r[0] for r in made["Query"].fetchall()] == [12.0, -1.0, None, 2.5, -1.0]


def test_try_with_no_otherwise_per_row_is_refused_with_its_line() -> None:
    """`try x` alone is a record ([HasError, Value, Error]) in M: a column of SQL has no such value."""
    (problem,) = duckpq.check(f'Table.AddColumn({S},\n "v", each try Number.From([s]))')
    assert (problem.line, problem.column, problem.name) == (2, 12, "try")
    assert "otherwise" in problem.message


def test_try_refuses_what_duckdb_cannot_try_with_its_line() -> None:
    """DuckDB's TRY takes no error() of the query's own and no subquery: said here, not by the engine."""
    (raised,) = duckpq.check(
        f'Table.AddColumn({S}, "v", each try (if [n] > 2 then error "big" else [n]) otherwise 0)'
    )
    assert raised.name == "try" and "error" in raised.message and raised.line == 1


def test_try_otherwise_wants_one_type_as_any_column_of_sql() -> None:
    """The known difference from M: the otherwise value must fit the tried value's type. M would keep a text
    beside numbers in one column; DuckDB refuses it when it runs."""
    with pytest.raises(duckdb.Error):
        tried('try Number.From([s]) otherwise "bad"')


def test_plain_values_follow_the_same_rules() -> None:
    """What is worked out while compiling (no row in it) answers as the SQL would."""
    made = duckpq.run(
        'let a = null = null, b = "B" < "a", c = 7 / 2, d = Number.Round(2.5), e = 1 / 0 > 1000 in '
        '#table({"a", "b", "c", "d", "e"}, {{a, b, c, d, e}})'
    )["Query"].fetchall()
    assert made == [(True, True, 3.5, 2, True)]
