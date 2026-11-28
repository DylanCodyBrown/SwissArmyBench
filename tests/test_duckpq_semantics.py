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


# ----- what cannot be compiled is refused, even inside try (1.1.1) -----
#
# Two kinds of failure. An EvaluationError is M's own error, known while compiling (a constant that does not
# convert, a missing column, field or item, a file that is not there): `try` takes its otherwise for it, as it
# does per row for what DuckDB raises. Every other PowerQueryError is a refusal: duckpq cannot compile this,
# and M might well have run it, so an otherwise value would be a guess.


def refused(text: str, **given: Any) -> duckpq.PowerQueryError:
    with pytest.raises(duckpq.PowerQueryError) as raised:
        duckpq.run(text, **given)
    assert not isinstance(raised.value, duckpq.EvaluationError)
    return raised.value


def test_try_per_row_does_not_swallow_a_function_duckpq_does_not_run() -> None:
    """Before 1.1.1 this gave 0 on every row."""
    error = refused(f'Table.AddColumn({S},\n "v", each try Text.Frobnicate([s]) otherwise 0)')
    assert (error.line, error.column, error.name) == (2, 16, "Text.Frobnicate")
    assert "not a function duckpq runs" in error.what
    other = refused(f'Table.AddColumn({S}, "v", each try Some.Unknown([s]) otherwise 0)')
    assert other.name == "Some.Unknown" and other.line == 1
    (problem,) = duckpq.check(f'Table.AddColumn({S}, "v", each try Text.Frobnicate([s]) otherwise 0)')
    assert problem.name == "Text.Frobnicate"


def test_try_around_a_whole_query_does_not_swallow_what_cannot_be_compiled() -> None:
    """M's meaning for a whole-query try: its otherwise is the answer only when working the query out raises
    an error. A function duckpq does not run, or a step it cannot map, raises nothing in M (M has the
    function): the answer there would be the query's own, so here it is refused, never the otherwise."""
    unknown = refused(f"try Table.Frobnicate({S}) otherwise {S}")
    assert (unknown.line, unknown.column, unknown.name) == (1, 5, "Table.Frobnicate")
    step = refused(f'try Table.Group({S}, {{"s"}}, {{}}, GroupKind.Local) otherwise {S}')
    assert step.name == "Table.Group" and "GroupKind.Global" in step.what


def test_try_does_not_swallow_a_source_nothing_resolves() -> None:
    database = f'try Sql.Database("srv", "db"){{[Schema = "a", Item = "b"]}}[Data] otherwise {S}'
    error = refused(database)
    assert error.line == 1 and "Nothing reads Sql.Database" in error.what
    said = refused(
        database, resolver=lambda source: (_ for _ in ()).throw(RuntimeError("the server said no"))
    )
    assert "the server said no" in said.what
    failure = duckpq.Context()
    first = duckpq.compile(database, "Query", failure)
    assert not first.complete
    for key in failure.missing:
        failure.resolved[key] = duckpq.Failure("No connection reads srv.")
    (problem,) = duckpq.compile(database, "Query", failure).problems  # a caller's Failure: a refusal
    assert problem.message == "No connection reads srv." and problem.line == 1
    # a caller that knows M's own read would raise (the file is not there) says so: the otherwise is taken
    file = f'try Csv.Document(File.Contents("orders.csv")) otherwise {S}'
    for said_raised, problems in ((False, 1), (True, 0)):
        context = duckpq.Context()
        duckpq.compile(file, "Query", context)
        for key in context.missing:
            context.resolved[key] = duckpq.Failure("orders.csv is not there.", raised=said_raised)
        assert len(duckpq.compile(file, "Query", context).problems) == problems


def test_try_nested_refuses_through_every_level_and_from_the_otherwise() -> None:
    inner = "try Text.Frobnicate([s]) otherwise 1"
    assert refused(f'Table.AddColumn({S}, "v", each try ({inner}) otherwise 0)').name == "Text.Frobnicate"
    assert (
        refused(f'Table.AddColumn({S}, "v", each try Number.From([s]) otherwise Text.Frobnicate([s]))').name
        == "Text.Frobnicate"
    )
    whole = f"try (try Table.Frobnicate({S}) otherwise {S}) otherwise {S}"
    assert refused(whole).name == "Table.Frobnicate"
    # an inner try that may take its otherwise still does, inside an outer one
    assert tried('try (try Number.From("x") otherwise Number.From([s])) otherwise -5') == [
        12.0,
        -5.0,
        None,
        2.5,
        -5.0,
    ]


def test_try_still_takes_its_otherwise_for_an_error_that_is_m_s_own() -> None:
    """What M itself raises, known while compiling: the otherwise is M's answer, not a guess."""
    plain = {
        'try Number.From("x") otherwise 5': 5,
        'try 1 + "a" otherwise 5': 5,
        "try {1, 2}{5} otherwise 5": 5,
        "try [a = 1][b] otherwise 5": 5,
        'try error "no" otherwise 5': 5,
        "try not 1 otherwise 5": 5,
        "try Text.Length(5) otherwise 5": 5,
        "try 7 otherwise 5": 7,
    }
    for text, answer in plain.items():
        made = duckpq.run(f'#table({{"v"}}, {{{{{text}}}}})')["Query"].fetchall()
        assert made == [(answer,)], text
    kept_table = duckpq.run(f'try Table.SelectColumns({S}, {{"nope"}}) otherwise Table.FirstN({S}, 1)')
    assert len(kept_table["Query"].fetchall()) == 1
    assert tried("try [nope] otherwise 0") == [0, 0, 0, 0, 0]
    missing = f'try Csv.Document(File.Contents("/nowhere/none.csv")) otherwise Table.FirstN({S}, 2)'
    assert len(duckpq.run(missing)["Query"].fetchall()) == 2
    with pytest.raises(duckpq.PowerQueryError) as raised:  # with no try around it, it is said as any problem
        duckpq.run('Csv.Document(File.Contents("/nowhere/none.csv"))')
    assert "not a file" in raised.value.what and issubclass(duckpq.EvaluationError, duckpq.PowerQueryError)
    assert duckpq.Failure("x").raised is False


def test_plain_values_follow_the_same_rules() -> None:
    """What is worked out while compiling (no row in it) answers as the SQL would."""
    made = duckpq.run(
        'let a = null = null, b = "B" < "a", c = 7 / 2, d = Number.Round(2.5), e = 1 / 0 > 1000 in '
        '#table({"a", "b", "c", "d", "e"}, {{a, b, c, d, e}})'
    )["Query"].fetchall()
    assert made == [(True, True, 3.5, 2, True)]
