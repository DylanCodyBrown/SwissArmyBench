"""`${NAME}` anywhere a value is typed (design principle 12.7): the rules of domain/variable_refs.py."""

from __future__ import annotations

import ast

import duckdb
import pytest
import sqlglot

from swissarmybench.domain import variable_refs as refs

ENV = {
    "WAREHOUSE_HOST": "db01.example.local",
    "TENANT": "contoso",
    "SITE": "finance",
    "QUOTE": "x' OR '1'='1",
}
look = ENV.get


# ===== what is a reference =====


@pytest.mark.parametrize(
    "text",
    [
        "pa$$word",
        "Sheet1$",
        "[Orders$]",
        "${not a name}",
        "${ X}",
        "${X }",
        "${}",
        "${1ABC}",
        "$X",
        "${X",
        "$ {X}",
        "{X}",
        "cost: $5",
    ],
)
def test_text_that_is_not_a_reference_stays_as_typed(text: str) -> None:
    assert refs.find(text) == []
    assert refs.resolve(text, look) == text
    assert refs.literal(text) == text
    assert refs.escape(text) == text
    assert not refs.holds(text)


def test_a_reference_and_its_place() -> None:
    [ref] = refs.find("Server=${WAREHOUSE_HOST};")
    assert (ref.name, ref.default, ref.start, ref.end) == ("WAREHOUSE_HOST", None, 7, 24)
    assert ref.text == "${WAREHOUSE_HOST}"


def test_names_with_underscores_and_digits() -> None:
    assert refs.names("${_A1} ${b_2} ${_A1}") == ["_A1", "b_2"]


def test_mixed_with_text() -> None:
    text = "https://${TENANT}.sharepoint.com/sites/${SITE}"
    assert refs.resolve(text, look) == "https://contoso.sharepoint.com/sites/finance"


def test_a_default_answers_when_not_set() -> None:
    assert refs.resolve("${PORT:-5432}", look) == "5432"
    assert refs.resolve("${TENANT:-other}", look) == "contoso"
    assert refs.resolve("${EMPTY:-}", look) == ""


def test_a_default_is_literal_up_to_the_brace_no_nesting() -> None:
    [ref] = refs.find("${A:-${B}}")
    assert ref.default == "${B"
    assert refs.resolve("${A:-${B}}", look) == "${B}"  # the default is not read again


def test_the_doubled_dollar_is_the_literal_text() -> None:
    assert refs.find("$${WAREHOUSE_HOST}") == []
    assert refs.resolve("$${WAREHOUSE_HOST}", look) == "${WAREHOUSE_HOST}"
    assert refs.literal("a $${X} b") == "a ${X} b"
    # three dollars: one kept, then the escaped reference
    assert refs.resolve("$$${X}", look) == "$${X}"


def test_escape_round_trips() -> None:
    for value in ["${X}", "$${X}", "a${X:-1}b", "pa$$word", "${not}", "$$${A}"]:
        assert refs.parts(refs.escape(value)) == [value]
        assert refs.literal(refs.escape(value)) == value


def test_one_pass_a_value_is_never_read_again() -> None:
    values = {"PASSWORD": "pa${TENANT}word", "A": "${B}", "B": "no"}
    assert refs.resolve("${PASSWORD}", values.get) == "pa${TENANT}word"
    assert refs.resolve("${A}", values.get) == "${B}"


def test_a_missing_variable_is_one_error_with_set_it() -> None:
    with pytest.raises(refs.MissingVariables) as caught:
        refs.resolve("${NOPE}/${WAREHOUSE_HOST}/${ALSO:-x}/${OTHER}", look, where="Warehouse's server")
    error = caught.value
    assert error.missing == ["NOPE", "OTHER"]
    assert str(error) == "NOPE and OTHER are not set on this computer (Warehouse's server)."
    shape = error.to_json()
    assert shape["missing_variables"] == ["NOPE", "OTHER"]
    assert shape["fixes"][0] == {
        "label": "Set it",
        "action": "set_variable",
        "command": "variables_set",
        "page": "variables",
        "name": "NOPE",
    }
    assert str(refs.MissingVariables(["X"])) == "X is not set on this computer."


def test_resolve_all_says_every_missing_name_at_once() -> None:
    with pytest.raises(refs.MissingVariables) as caught:
        refs.resolve_all({"a": "${A}", "b": "${B}", "n": 3}, look)
    assert caught.value.missing == ["A", "B"]
    assert refs.resolve_all({"h": "${TENANT}", "n": 3}, look) == {"h": "contoso", "n": 3}


def test_preview_masks_a_secret_and_says_what_is_missing() -> None:
    values = {"USER": "ana", "WAREHOUSE_PASSWORD": "s3cr3t-value"}
    shown = refs.preview("${USER}:${WAREHOUSE_PASSWORD}@${HOST}", values.get, lambda n: "PASSWORD" in n)
    assert "s3cr3t-value" not in str(shown)
    assert shown["value"] == "ana:••••••••@${HOST}"
    assert shown["masked"] is True
    assert shown["missing"] == ["HOST"]
    assert shown["error"]["error"] == "HOST is not set on this computer."


# ===== the export form =====


def _run(expr: str, environ: dict[str, str]) -> str:
    """The expression evaluated with a stand-in os whose environment is `environ`."""
    values = dict(environ)

    class FakeOs:
        environ = values

        @staticmethod
        def getenv(name: str, default: str | None = None) -> str | None:
            return values.get(name, default)

    return str(eval(expr, {"os": FakeOs}))  # noqa: S307 (our own expression, a test)


def test_python_expr_reads_the_environment_where_it_runs() -> None:
    assert refs.python_expr("plain") == '"plain"'
    assert refs.python_expr("${WAREHOUSE_HOST}") == 'os.environ["WAREHOUSE_HOST"]'
    assert refs.python_expr("${PORT:-5432}") == 'os.environ.get("PORT", "5432")'
    text = "https://${TENANT}.sharepoint.com/sites/${SITE}"
    expr = refs.python_expr(text)
    assert 'f"' not in expr and "+" in expr
    assert _run(expr, ENV) == "https://contoso.sharepoint.com/sites/finance"
    # an escaped reference is literal text in the export
    assert _run(refs.python_expr("$${X}"), {}) == "${X}"


def test_from_python_reads_the_export_back() -> None:
    for text in ["plain", "${A}", "${PORT:-5432}", "https://${TENANT}.x/${SITE}", "$${X}", "a${B:-c}d"]:
        node = ast.parse(refs.python_expr(text), mode="eval").body
        assert refs.from_python(node) == text
    assert refs.from_python(ast.parse('os.getenv("A", "b")', mode="eval").body) == "${A:-b}"
    assert refs.from_python(ast.parse('os.environ.get("A")', mode="eval").body) == "${A}"
    assert refs.from_python(ast.parse('"a" + "b"', mode="eval").body) is None
    assert refs.from_python(ast.parse("x + 1", mode="eval").body) is None
    assert refs.from_python(ast.parse('os.environ.get("A", "}")', mode="eval").body) is None


# ===== SQL =====


def test_sql_reference_is_a_bound_parameter() -> None:
    bound = refs.bind_sql("SELECT * FROM orders WHERE region = ${REGION} AND n > ${N:-5}")
    assert bound.sql == "SELECT * FROM orders WHERE region = $1 AND n > $2"
    assert bound.params({"REGION": "North"}.get) == ["North", "5"]


@pytest.mark.parametrize(
    "style, placeholder",
    [
        ("qmark", "?"),
        ("numeric", ":1"),
        ("named", ":p1"),
        ("format", "%s"),
        ("pyformat", "%(p1)s"),
        ("dollar", "$1"),
    ],
)
def test_each_drivers_style(style: str, placeholder: str) -> None:
    bound = refs.bind_sql("SELECT 1 WHERE a = ${A}", "postgres", style)
    assert bound.sql == f"SELECT 1 WHERE a = {placeholder}"
    params = bound.params({"A": "v"}.get)
    assert params == ({"p1": "v"} if style in ("named", "pyformat") else ["v"])


def test_format_styles_double_the_percent() -> None:
    bound = refs.bind_sql("SELECT 1 WHERE a LIKE 'x%' AND b = ${B}", "postgres", "format")
    assert bound.sql == "SELECT 1 WHERE a LIKE 'x%%' AND b = %s"


def test_inside_strings_quoted_names_and_comments_stays_as_typed() -> None:
    sql = "SELECT '${A}' AS \"${B}\", $$${C}$$ -- ${D}\n/* ${E} */ FROM t WHERE x = ${F}"
    bound = refs.bind_sql(sql, "duckdb")
    assert [r.name for r in bound.refs] == ["F"]
    assert (
        "'${A}'" in bound.sql
        and '"${B}"' in bound.sql
        and "-- ${D}" in bound.sql
        and "/* ${E} */" in bound.sql
    )
    # T-SQL's bracketed name
    assert refs.bind_sql("SELECT [${A}] FROM t", "tsql", "qmark").refs == ()
    # a '' inside a string does not end it
    assert refs.bind_sql("SELECT 'it''s ${A}' , ${B}", "duckdb").sql == "SELECT 'it''s ${A}' , $1"


def test_the_escape_in_sql_is_the_literal_text() -> None:
    bound = refs.bind_sql("SELECT '$${A}', 1 AS v WHERE 1 = 1", "duckdb")
    assert bound.refs == () and bound.sql == "SELECT '${A}', 1 AS v WHERE 1 = 1"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM ${TABLE}",
        "SELECT * FROM t JOIN ${OTHER} ON 1=1",
        "SELECT a AS ${ALIAS} FROM t",
        "SELECT ${SCHEMA}.orders.id FROM t",
        "SELECT orders_${YEAR} FROM t",
        "SELECT ${FN}(1)",
        "INSERT INTO ${T} VALUES (1)",
    ],
)
def test_where_a_name_goes_it_is_refused(sql: str) -> None:
    with pytest.raises(refs.SqlRefError, match="never pasted"):
        refs.bind_sql(sql, "duckdb")


def test_a_value_with_a_quote_cannot_change_the_query() -> None:
    con = duckdb.connect()
    con.execute("CREATE TABLE people AS SELECT * FROM (VALUES ('Ana'), ('Bo')) t(name)")
    bound = refs.bind_sql("SELECT count(*) FROM people WHERE name = ${QUOTE}", "duckdb")
    assert con.execute(bound.sql, bound.params(look)).fetchone() == (0,)
    bound = refs.bind_sql("SELECT count(*) FROM people WHERE name = ${WHO}", "duckdb")
    assert con.execute(bound.sql, bound.params({"WHO": "Ana"}.get)).fetchone() == (1,)


def test_a_missing_variable_in_sql() -> None:
    with pytest.raises(refs.MissingVariables, match="REGION is not set on this computer"):
        refs.bind_sql("SELECT ${REGION}").params(look)


def test_the_scanner_agrees_with_sqlglots_strings() -> None:
    """Our spans of strings and quoted names agree with sqlglot's tokens (which keep no comment places)."""
    sql = "SELECT 'a''b', \"c d\", x FROM t WHERE y = 'q' -- note\n AND z = 1"
    ours = [sql[s:e] for s, e in refs._spans(sql, "duckdb") if not sql[s:e].startswith("--")]
    tokens = [
        t for t in sqlglot.tokenize(sql, read="duckdb") if t.token_type.name in ("STRING", "IDENTIFIER")
    ]
    assert [sql[t.start : t.end + 1] for t in tokens] == ours


def test_sql_without_references_is_untouched() -> None:
    sql = "SELECT 'pa$$word', $1, [Orders$] FROM t"
    assert refs.bind_sql(sql, "duckdb").sql == sql


def test_holding_lists_saved_text_that_now_names_a_variable() -> None:
    found = refs.holding([("Warehouse: server", "${HOST}"), ("Sales: path", "C:/x$/y"), ("x", "$${A}")])
    assert found == [{"where": "Warehouse: server", "names": ["HOST"]}]
