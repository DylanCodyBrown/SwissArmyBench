"""duckpq's parser: every construct of M it reads, and its errors with their line and column. Imports only
duckpq and the standard library (the file moves with the library)."""

from __future__ import annotations

import pytest

import duckpq


def tree(text: str) -> duckpq.Node:
    return duckpq.parse(text).members[0].body


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("1", "literal"),
        ("0x1F", "literal"),
        ("1.5e3", "literal"),
        ('"a ""quoted"" word"', "text"),
        ("null", "literal"),
        ("true", "literal"),
        ("{1, 2, 3}", "list"),
        ("{1..5}", "list"),
        ("[a = 1, b = [c = 2]]", "record"),
        ("[]", "record"),
        ("let a = 1, b = a + 1 in b", "let"),
        ("if 1 = 1 then 2 else 3", "if"),
        ("each [Amount] > 10", "each"),
        ("each _ + 1", "each"),
        ("(x, optional y as number) as number => x + 1", "function"),
        ("Table.SelectRows(t, each true)", "call"),
        ("t[Column]", "field"),
        ("t[Column]?", "field"),
        ("t[[A], [B]]", "project"),
        ("t{0}", "item"),
        ("t{0}?", "item"),
        ('#"Changed Type"', "name"),
        ("#date(2024, 1, 2)", "call"),
        ("#datetime(2024, 1, 2, 3, 4, 5)", "call"),
        ("#duration(1, 2, 3, 4)", "call"),
        ('#table({"a"}, {{1}})', "call"),
        ("try 1 otherwise 2", "try"),
        ('error "no"', "error"),
        ("1 + 2 * 3", "binary"),
        ('"a" & "b"', "binary"),
        ("a and b or not c", "binary"),
        ("a ?? b", "binary"),
        ("-x", "unary"),
        ("not x", "unary"),
        ('type table [a = number, #"b c" = text]', "type"),
        ("type nullable text", "type"),
        ("type {number}", "type"),
        ("x is number", "is"),
        ("x as text", "as"),
        ('"a" meta [IsParameterQuery = true]', "meta"),
        ("@f(1)", "call"),
        ("/* a */ 1 // b", "literal"),
    ],
)
def test_reads_every_construct(text: str, kind: str) -> None:
    assert tree(text).kind == kind


def test_precedence_is_ms() -> None:
    """The specification's order: * before +, comparison before and, and before or, meta tightest."""
    add = tree("1 + 2 * 3")
    assert add["op"] == "+" and add["right"]["op"] == "*"
    logic = tree("a or b and c = d")
    assert logic["op"] == "or" and logic["right"]["op"] == "and" and logic["right"]["right"]["op"] == "="
    assert tree("1 + 2 meta [a = 1]")["right"].kind == "meta"


def test_text_escapes() -> None:
    assert tree('"a#(lf)b#(tab)c#(0041)"')["value"] == "a\nb\tcA"
    assert tree('"say ""hi"""')["value"] == 'say "hi"'


def test_a_field_name_may_hold_spaces_and_a_record_is_told_from_a_field() -> None:
    assert tree("each [Order Date]")["body"]["name"] == "Order Date"
    assert tree('each [#"Odd ] name"]')["body"]["name"] == "Odd ] name"
    assert tree("[Order Date = 1]").kind == "record"
    assert tree("[Order Date = 1]")["fields"][0][0] == "Order Date"


def test_a_dotted_name_is_one_name_and_a_range_is_not() -> None:
    assert tree("Table.SelectRows")["name"] == "Table.SelectRows"
    assert tree("{a..b}")["items"][0].kind == "range"


def test_a_section_document_is_its_queries() -> None:
    document = duckpq.parse(
        '[Version = "1.0"]\nsection Sales;\n\nshared Server = "x" meta [IsParameterQuery = true];\n'
        "shared Orders = let\n    a = 1\nin\n    a;\nHelper = 2;\n"
    )
    assert document.section == "Sales"
    assert [(m.name, m.shared, m.line, m.end_line) for m in document.members] == [
        ("Server", True, 4, 4),
        ("Orders", True, 5, 8),
        ("Helper", False, 9, 9),
    ]


def test_a_plain_file_is_one_query_named_by_the_caller() -> None:
    document = duckpq.parse("let\n  a = 1\nin\n  a\n", "orders")
    assert document.section is None and [m.name for m in document.members] == ["orders"]
    assert (document.members[0].line, document.members[0].end_line) == (1, 4)


@pytest.mark.parametrize(
    ("text", "line", "column", "words"),
    [
        ("let a = 1,\n in a", 2, 2, "comma before `in`"),
        ("let a = (1 in a", 1, 12, ") is missing"),
        ('let\n a = "x\nin a', 2, 6, "never closed"),
        ("1 +", 1, 4, "A value is expected"),
        ("let a = 1 b = 2 in a", 1, 11, "`in` is missing"),
        ("if 1 then 2", 1, 12, "`else` is missing"),
        ("let a = 1, a = 2 in a", 1, 12, "Two steps are named a"),
        ("section S; shared A = 1; shared A = 2;", 1, 33, "Two queries are named A"),
        ("{1, 2", 1, 6, "} is missing"),
        ("/* open", 1, 1, "comment is never closed"),
        ("#nope", 1, 1, "not a word of M"),
        ("", 1, 1, "no query yet"),
        ("try 1 catch (e) => 2", 1, 7, "try ... otherwise"),
    ],
)
def test_an_error_points_at_its_line_and_column(text: str, line: int, column: int, words: str) -> None:
    with pytest.raises(duckpq.PowerQueryError) as caught:
        duckpq.parse(text)
    assert (caught.value.line, caught.value.column) == (line, column), caught.value
    assert words in str(caught.value)


def test_check_gives_a_parse_error_as_a_problem() -> None:
    (problem,) = duckpq.check("let a = \nin a")
    assert (problem.line, problem.column) == (2, 1) and "value is expected" in problem.message
