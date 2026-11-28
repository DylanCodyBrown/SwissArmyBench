"""duckpq's functions: each one's result against rows worked out by hand, on made-up data. Imports only
duckpq, duckdb and the standard library."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

import duckpq

T = (
    "#table(type table [id = Int64.Type, name = text, amount = number, day = date], {"
    '{1, "ann", 10.5, #date(2024, 1, 3)}, {2, "Bob", 200, #date(2024, 1, 31)}, '
    '{3, "ann", 150, #date(2024, 2, 29)}, {4, null, null, null}})'
)
D = dt.date


def rows(expression: str, **options: Any) -> list[tuple[Any, ...]]:
    return list(duckpq.run(f"let T = {T} in {expression}", **options)["Query"].fetchall())


def names(expression: str) -> list[str]:
    return list(duckpq.run(f"let T = {T} in {expression}")["Query"].columns)


def value(expression: str) -> Any:
    """One value worked out per row, on a one-row table."""
    return duckpq.run(f'Table.AddColumn(#table({{"x"}}, {{{{1}}}}), "v", each {expression})')[
        "Query"
    ].fetchall()[0][1]


def test_select_rows() -> None:
    assert [r[0] for r in rows("Table.SelectRows(T, each [amount] > 100)")] == [2, 3]
    assert [r[0] for r in rows('Table.SelectRows(T, each [name] = "ann" and [amount] < 100)')] == [1]


def test_select_remove_rename_reorder_columns() -> None:
    assert names('Table.SelectColumns(T, {"name", "id"})') == ["name", "id"]
    assert names('Table.SelectColumns(T, "id")') == ["id"]
    assert names('Table.SelectColumns(T, {"id", "zz"}, MissingField.Ignore)') == ["id"]
    assert rows('Table.SelectColumns(T, {"id", "zz"}, MissingField.UseNull)')[0] == (1, None)
    assert names('Table.RemoveColumns(T, {"day", "amount"})') == ["id", "name"]
    assert names('Table.RenameColumns(T, {{"id", "key"}, {"name", "who"}})') == [
        "key",
        "who",
        "amount",
        "day",
    ]
    assert names('Table.RenameColumns(T, {"zz", "y"}, MissingField.Ignore)') == [
        "id",
        "name",
        "amount",
        "day",
    ]
    assert names("T[[name], [id]]") == ["name", "id"]


def test_reorder_columns_swaps_the_named_ones_in_place() -> None:
    """learn.microsoft.com/powerquery-m/table-reordercolumns: the columns not named keep their places."""
    assert names('Table.ReorderColumns(T, {"amount", "id"})') == ["amount", "name", "id", "day"]
    assert names('Table.ReorderColumns(T, {"day", "amount", "name", "id"})') == [
        "day",
        "amount",
        "name",
        "id",
    ]


def test_transform_column_types() -> None:
    made = rows('Table.TransformColumnTypes(T, {{"id", type text}, {"amount", Int64.Type}})')
    assert made[0][0] == "1" and made[1][2] == 200 and isinstance(made[1][2], int)


def test_add_duplicate_and_transform_columns() -> None:
    assert rows('Table.AddColumn(T, "double", each [amount] * 2, type number)')[0][4] == 21.0
    assert names('Table.DuplicateColumn(T, "name", "copy")')[-1] == "copy"
    assert [r[1] for r in rows('Table.TransformColumns(T, {{"name", Text.Upper, type text}})')] == [
        "ANN", "BOB", "ANN", None,
    ]  # fmt: skip
    assert [r[1] for r in rows('Table.TransformColumns(T, {"name", each Text.Start(_, 1)})')][:2] == [
        "a",
        "B",
    ]


def test_replace_value() -> None:
    replaced = rows('Table.ReplaceValue(T, null, "nobody", Replacer.ReplaceValue, {"name"})')
    assert [r[1] for r in replaced] == ["ann", "Bob", "ann", "nobody"]
    text = rows('Table.ReplaceValue(T, "an", "AN", Replacer.ReplaceText, {"name"})')
    assert [r[1] for r in text] == ["ANn", "Bob", "ANn", None]


def test_fill_down_and_up() -> None:
    gaps = '#table({"a", "b"}, {{1, "x"}, {null, null}, {3, null}, {null, "y"}})'
    assert duckpq.run(f'Table.FillDown({gaps}, {{"a", "b"}})')["Query"].fetchall() == [
        (1, "x"), (1, "x"), (3, "x"), (3, "y"),
    ]  # fmt: skip
    assert duckpq.run(f'Table.FillUp({gaps}, {{"a"}})')["Query"].fetchall() == [
        (1, "x"), (3, None), (3, None), (None, "y"),
    ]  # fmt: skip


def test_distinct() -> None:
    twice = '#table({"a", "b"}, {{1, "x"}, {1, "x"}, {1, "y"}, {2, "x"}})'
    assert sorted(duckpq.run(f"Table.Distinct({twice})")["Query"].fetchall()) == [
        (1, "x"),
        (1, "y"),
        (2, "x"),
    ]
    # By a column: the first row of each value is kept, in the rows' order.
    assert duckpq.run(f'Table.Distinct({twice}, {{"a"}})')["Query"].fetchall() == [(1, "x"), (2, "x")]


def test_sort_first_n_skip_range() -> None:
    assert [r[0] for r in rows('Table.Sort(T, {{"amount", Order.Descending}})')] == [2, 3, 1, 4]
    assert [r[0] for r in rows('Table.Sort(T, {{"name", Order.Ascending}, {"id", Order.Descending}})')] == [
        4, 2, 3, 1,
    ]  # fmt: skip
    assert [r[0] for r in rows('Table.FirstN(Table.Sort(T, "id"), 2)')] == [1, 2]
    assert [r[0] for r in rows("Table.Skip(T, 3)")] == [4]
    assert [r[0] for r in rows("Table.Range(T, 1, 2)")] == [2, 3]


def test_group_with_each_aggregate() -> None:
    made = rows(
        'Table.Sort(Table.Group(T, {"name"}, {{"total", each List.Sum([amount]), type number}, '
        '{"n", each Table.RowCount(_), Int64.Type}, {"avg", each List.Average([amount])}, '
        '{"low", each List.Min([amount])}, {"high", each List.Max([amount])}, '
        '{"count", each List.Count([amount])}}), "name")'
    )
    assert made == [
        (None, None, 1, None, None, None, 1),
        ("Bob", 200.0, 1, 200.0, 200.0, 200.0, 1),
        ("ann", 160.5, 2, 80.25, 10.5, 150.0, 2),
    ]
    assert rows('Table.Group(T, {}, {{"n", each Table.RowCount(_)}})') == [(4,)]


def test_nested_join_then_expand_and_join() -> None:
    regions = '#table({"who", "region"}, {{"ann", "North"}, {"zed", "West"}})'
    joined = rows(
        f'Table.ExpandTableColumn(Table.NestedJoin(T, {{"name"}}, {regions}, {{"who"}}, "r", JoinKind.LeftOuter), '
        '"r", {"region"}, {"Region"})'
    )
    assert sorted((r[0], r[4]) for r in joined) == [(1, "North"), (2, None), (3, "North"), (4, None)]
    inner = rows(f'Table.Join(T, "name", {regions}, "who", JoinKind.Inner)')
    assert sorted(r[0] for r in inner) == [1, 3] and len(inner[0]) == 6
    anti = rows(
        f'Table.RemoveColumns(Table.NestedJoin(T, "name", {regions}, "who", "r", JoinKind.LeftAnti), "r")'
    )
    assert sorted(r[0] for r in anti) == [2, 4]
    full = rows(f'Table.Join(T, "name", {regions}, "who", JoinKind.FullOuter)')
    assert len(full) == 5


def test_a_join_matches_null_with_null_as_m_does() -> None:
    other = '#table({"who", "note"}, {{null, "no name"}})'
    joined = rows(f'Table.Join(T, "name", {other}, "who")')
    assert [(r[0], r[5]) for r in joined] == [(4, "no name")]


def test_combine_by_column_name() -> None:
    made = duckpq.run('Table.Combine({#table({"a", "b"}, {{1, "x"}}), #table({"b", "c"}, {{"y", true}})})')[
        "Query"
    ]
    assert made.columns == ["a", "b", "c"] and made.fetchall() == [(1, "x", None), (None, "y", True)]
    both = duckpq.run('#table({"a"}, {{1}}) & #table({"a"}, {{2}})')["Query"].fetchall()
    assert both == [(1,), (2,)]


def test_promote_headers_on_a_literal() -> None:
    made = duckpq.run('Table.PromoteHeaders(#table({"Column1", "Column2"}, {{"id", "name"}, {1, "ann"}}))')[
        "Query"
    ]
    assert made.columns == ["id", "name"] and made.fetchall() == [(1, "ann")]


def test_unpivot_and_pivot() -> None:
    wide = '#table({"id", "jan", "feb"}, {{1, 10, 20}, {2, null, 5}})'
    long = duckpq.run(f'Table.UnpivotOtherColumns({wide}, {{"id"}}, "month", "value")')["Query"]
    assert long.columns == ["id", "month", "value"]
    assert long.fetchall() == [(1, "jan", 10), (1, "feb", 20), (2, "feb", 5)]
    assert (
        duckpq.run(f'Table.Unpivot({wide}, {{"jan", "feb"}}, "month", "value")')["Query"].fetchall()
        == long.fetchall()
    )
    back = duckpq.run(
        f'let L = Table.UnpivotOtherColumns({wide}, {{"id"}}, "month", "value") in '
        'Table.Sort(Table.Pivot(L, List.Distinct(L[month]), "month", "value", List.Sum), "id")'
    )["Query"]
    assert back.columns == ["id", "jan", "feb"] and back.fetchall() == [(1, 10, 20), (2, None, 5)]


def test_split_column_by_a_delimiter() -> None:
    made = duckpq.run(
        'Table.SplitColumn(#table({"id", "code"}, {{1, "a-b"}, {2, "c"}}), "code", '
        'Splitter.SplitTextByDelimiter("-", QuoteStyle.Csv), {"left", "right"})'
    )["Query"]
    assert made.columns == ["id", "left", "right"] and made.fetchall() == [(1, "a", "b"), (2, "c", None)]


def test_buffer_index_and_the_small_ones() -> None:
    assert rows("Table.Buffer(T)") == rows("T")
    assert [r[4] for r in rows('Table.AddIndexColumn(T, "i", 1, 1)')] == [1, 2, 3, 4]
    assert value(f"Table.RowCount({T})") == 4
    assert value(f"List.Sum({T}[amount])") == 360.5
    assert value(f"{T}{{1}}[name]") == "Bob"
    assert value(f"{T}{{[id = 3]}}[amount]") == 150


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ('Text.Upper("aBc")', "ABC"),
        ('Text.Lower("aBc")', "abc"),
        ('Text.Trim("  a b \t")', "a b"),
        ('Text.Start("abcdef", 2)', "ab"),
        ('Text.End("abcdef", 2)', "ef"),
        ('Text.Middle("abcdef", 2, 3)', "cde"),
        ('Text.Contains("Hello", "ell")', True),
        ('Text.Contains("Hello", "ELL", Comparer.OrdinalIgnoreCase)', True),
        ('Text.StartsWith("Hello", "He")', True),
        ('Text.EndsWith("Hello", "lo")', True),
        ('Text.Replace("a-b-c", "-", "+")', "a+b+c"),
        ('Text.Length("héllo")', 5),
        ("Text.From(12)", "12"),
        ("Text.From(true)", "true"),
        ('Text.PositionOf("abc", "c")', 2),
        ('Text.Combine({"a", null, "b"}, "-")', "a-b"),
        ('Text.BeforeDelimiter("a@b", "@")', "a"),
        ('Text.AfterDelimiter("a@b", "@")', "b"),
        ('Text.PadStart("7", 3, "0")', "007"),
        ("Number.Round(2.345, 2)", 2.35),
        ("Number.RoundDown(2.9)", 2),
        ("Number.RoundUp(2.1)", 3),
        ('Number.From("12.5")', 12.5),
        ("Number.Abs(-3)", 3),
        ("Number.Mod(7, 3)", 1),
        ("Number.IntegerDivide(7, 2)", 3),
        ("Number.Power(2, 10)", 1024),
        ('Int64.From("42")', 42),
        ("Date.Year(#date(2024, 2, 29))", 2024),
        ("Date.Month(#date(2024, 2, 29))", 2),
        ("Date.Day(#date(2024, 2, 29))", 29),
        ('Date.From("2024-02-29")', D(2024, 2, 29)),
        ("Date.From(#datetime(2024, 2, 29, 13, 0, 0))", D(2024, 2, 29)),
        ("Date.StartOfMonth(#date(2024, 2, 29))", D(2024, 2, 1)),
        ("Date.EndOfMonth(#date(2024, 2, 3))", D(2024, 2, 29)),
        ("Date.AddDays(#date(2024, 2, 28), 2)", D(2024, 3, 1)),
        ("Date.AddMonths(#date(2024, 1, 31), 1)", D(2024, 2, 29)),
        ("Date.QuarterOfYear(#date(2024, 5, 1))", 2),
        ("List.Sum({1, 2, 3.5})", 6.5),
        ("List.Count({1, null, 3})", 3),
        ("List.Max({1, 9, 3})", 9),
        ("List.Min({4, 2, 8})", 2),
        ("List.Count(List.Distinct({1, 1, 2}))", 2),
        ("List.Contains({1, 2}, 2)", True),
        ('List.Contains({"a", "b"}, "c")', False),
        ('Logical.From("true")', True),
        ("Logical.From(0)", False),
        ("Value.Is(1, type number)", True),
        ('Value.Is("a", type number)', False),
        ("if 1 > 2 then 1 else 2", 2),
        ('try Number.From("x") otherwise null', None),
        ("null ?? 5", 5),
    ],
)
def test_each_scalar_function_on_a_row(expression: str, expected: Any) -> None:
    """Each function as one value of a row."""
    got = value(expression)
    if isinstance(expected, float):
        assert got == pytest.approx(expected)
    else:
        assert got == expected


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("Text.Upper([t])", "ABC"),
        ("Text.Start([t], 2)", "ab"),
        ('Text.Contains([t], "B")', False),
        ("[n] + 1", 8),
        ("[n] / 2", 3.5),
        ("List.Contains({7, 8}, [n])", True),
        ("Value.Is([t], type text)", True),
        ("Value.Is([n], type text)", False),
        ("Value.Is([n], type number)", True),
        ('if [n] > 5 then "big" else "small"', "big"),
        ('[t] & "!"', "abc!"),
        ("not ([n] = 7)", False),
    ],
)
def test_a_row_expression_over_columns(expression: str, expected: Any) -> None:
    table = '#table(type table [t = text, n = Int64.Type], {{"abc", 7}})'
    got = duckpq.run(f'Table.AddColumn({table}, "v", each {expression})')["Query"].fetchall()[0][2]
    assert got == expected


def test_a_function_written_in_the_file_runs_per_row() -> None:
    made = duckpq.run(
        'let Double = (v) => v * 2, Label = (v as number) => if v > 100 then "big" else "small" in '
        f'Table.AddColumn(Table.AddColumn({T}, "d", each Double([amount])), "l", each Label([amount]))'
    )["Query"].fetchall()
    assert [(r[4], r[5]) for r in made[:2]] == [(21.0, "small"), (400.0, "big")]


def test_functions_lists_what_runs() -> None:
    listed = duckpq.functions()
    for name in ("Table.SelectRows", "Table.Group", "Text.Upper", "Number.Round", "Date.AddDays", "List.Sum",
                 "Logical.From", "Value.Is", "Csv.Document", "Sql.Database"):  # fmt: skip
        assert name in listed
