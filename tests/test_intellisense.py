"""The Workbench editors' intelligence (domain/intellisense.py): docstrings in three styles, IPython's
lines, the app's names inside strings, the lint, imports and ranking. Made-up names throughout."""

from __future__ import annotations

from swissarmybench.domain import intellisense as rules

GOOGLE = """Write rows to a SQLite table.

    Args:
        connection: The connection's name.
        table (str): The table to write.
        mode: append or replace; longer words
            that go on.

    Returns:
        int: the rows written.

    Raises:
        ValueError: when the table is missing.
    """

NUMPY = """Write rows to a SQLite table.

    Parameters
    ----------
    connection : str
        The connection's name.
    table : str
        The table to write.

    Returns
    -------
    int
        The rows written.
    """

REST = """Write rows to a SQLite table.

    :param connection: The connection's name.
    :param str table: The table to write.
    :type connection: str
    :returns: the rows written.
    :rtype: int
    :raises ValueError: when the table is missing.
    """


def test_google_docstrings_give_each_parameter_its_words() -> None:
    d = rules.parse_docstring(GOOGLE)
    assert d.summary == "Write rows to a SQLite table."
    assert d.params == {
        "connection": "The connection's name.",
        "table": "The table to write.",
        "mode": "append or replace; longer words that go on.",
    }
    assert d.types == {"table": "str"}
    assert d.returns == "int: the rows written."
    assert d.raises == ("ValueError: when the table is missing.",)


def test_numpy_docstrings_give_each_parameter_its_words() -> None:
    d = rules.parse_docstring(NUMPY)
    assert d.summary == "Write rows to a SQLite table."
    assert d.params == {"connection": "The connection's name.", "table": "The table to write."}
    assert d.types == {"connection": "str", "table": "str"}
    assert "rows written" in d.returns


def test_rest_docstrings_give_each_parameter_its_words() -> None:
    d = rules.parse_docstring(REST)
    assert d.params == {"connection": "The connection's name.", "table": "The table to write."}
    assert d.types == {"table": "str", "connection": "str"}
    assert d.returns == "int: the rows written."
    assert d.raises == ("ValueError: when the table is missing.",)


def test_plain_words_are_all_summary() -> None:
    assert rules.parse_docstring("Just words.\n\nMore words.").summary == "Just words.\n\nMore words."
    assert rules.parse_docstring(None).summary == ""


def test_the_documentation_panel_says_the_signature_and_the_parameters() -> None:
    words = rules.markdown_doc("write_sqlite(connection, table)", GOOGLE, "functions.py")
    assert words.startswith("```python\nwrite_sqlite(connection, table)\n```")
    assert "- `table`: The table to write." in words
    assert "**Returns** int: the rows written." in words
    assert words.endswith("_From functions.py_")


def test_ipython_lines_are_python_of_the_same_lines() -> None:
    cell = "%timeit x = 1\nfiles = !ls\n!pip install pandas\norders?\n    %load_ext foo\ny = 2"
    made = rules.to_python(cell)
    assert made.split("\n") == ["pass", "files = []", "pass", "orders", "    pass", "y = 2"]
    assert rules.is_cell_magic("\n%%sql Warehouse\nSELECT 1")
    assert not rules.is_cell_magic("x = 1\n%%time")


def test_the_apps_names_inside_strings() -> None:
    def at(text: str) -> rules.Quoted | None:
        return rules.quoted_context(text, len(text))

    assert at('conn = sab.connection("Ware') == rules.Quoted("connection", "Ware", 23)
    assert at("sab.sql('") == rules.Quoted("connection", "", 9)
    assert at('sab.read("Or').kind == "connection"  # type: ignore[union-attr]
    assert at('x = os.environ["WARE').kind == "variable"  # type: ignore[union-attr]
    assert at('os.environ.get("W').kind == "variable"  # type: ignore[union-attr]
    assert at('os.getenv("').kind == "variable"  # type: ignore[union-attr]
    assert at('password = secret("WAREHOUSE_').typed == "WAREHOUSE_"  # type: ignore[union-attr]
    assert at('sab.blade("tidy').kind == "blade"  # type: ignore[union-attr]
    assert at('sab.structure("ord').kind == "structure"  # type: ignore[union-attr]
    assert at("%%sql Ware").kind == "connection"  # type: ignore[union-attr]
    assert at('orders["reg') == rules.Quoted("column", "reg", 8, "orders")
    assert at('print("hello') is None
    assert at("x = 1") is None


def test_a_syntax_error_says_where() -> None:
    [p] = rules.lint("def f(:\n    pass")
    assert (p.code, p.severity, p.line, p.col) == ("E999", "error", 1, 7)


def test_magics_are_not_syntax_errors_in_a_notebook() -> None:
    cell = "%matplotlib inline\nfiles = !ls\nprint(files)"
    assert rules.lint(cell, notebook=True) == []
    assert rules.lint("%%sql Warehouse\nSELEC 1", notebook=True) == []  # not Python
    assert rules.lint(cell)[0].code == "E999"  # a script is plain Python


def test_undefined_names_know_earlier_cells_the_kernel_and_builtins() -> None:
    text = "total = sum(amounts) + rate\nprint(totl)"
    found = rules.lint(text, known={"amounts"})
    assert [(p.code, p.message) for p in found] == [
        ("F821", "`rate` is not defined"),
        ("F821", "`totl` is not defined"),
    ]
    close = found[1].fixes[0]
    assert close.title == "Use `total`" and close.edits[0].text == "total"
    assert rules.lint(text.replace("totl", "total"), known={"amounts", "rate"}) == []
    assert rules.lint("display(sab)", notebook=True) == []  # the kernel's own names


def test_a_star_import_makes_names_unknowable() -> None:
    found = rules.lint("from helpers import *\nprint(anything)")
    assert [p.code for p in found] == ["F403"]


def test_unused_imports_are_faded_hints_unless_a_later_cell_uses_them() -> None:
    [p] = rules.lint("import json\nimport os\nos.getcwd()")
    assert (p.code, p.severity, p.unnecessary, p.line) == ("F401", "hint", True, 1)
    assert p.fixes[0].edits[0].to_json() == {"line": 1, "col": 1, "end_line": 2, "end_col": 1, "text": ""}
    assert rules.lint("import json", used_later={"json"}) == []
    [one] = rules.lint("from os import path, sep\nprint(sep)")
    edit = one.fixes[0].edits[0]
    assert (edit.col, edit.end_col) == (16, 22)  # "path, " goes


def test_the_small_patterns() -> None:
    codes = [
        p.code
        for p in rules.lint('x = None\nif x == None:\n    print(f"none")\ntry:\n    pass\nexcept:\n    pass')
    ]
    assert codes == ["E711", "F541", "E722"]
    fix = rules.lint("x = 1\ny = x != None")[0].fixes[0]
    assert fix.edits[0].text == "x is not None"


def test_an_undefined_name_offers_its_import_and_the_variables_page() -> None:
    text = '"""A script."""\nimport json\n\nurl = WAREHOUSE_URL + json.dumps(pd)'
    found = {p.message: p for p in rules.lint(text, variables={"WAREHOUSE_URL": "keyring"})}
    pandas = found["`pd` is not defined"].fixes[0]
    assert pandas.kind == "import" and pandas.edits[0].to_json() == {
        "line": 3,
        "col": 1,
        "end_line": 3,
        "end_col": 1,
        "text": "import pandas as pd\n",
    }
    define = found["`WAREHOUSE_URL` is not defined"].fixes[0]
    assert define.kind == "define"
    assert define.edits[0].text == 'import os\nWAREHOUSE_URL = os.environ["WAREHOUSE_URL"]\n'
    importable = {"write_sqlite": "from functions import write_sqlite"}
    [p] = rules.lint("write_sqlite(1)", importable=importable)
    assert p.fixes[0].edits[0].text == "from functions import write_sqlite\n\n"


def test_an_import_joins_its_modules_line_or_goes_after_the_imports() -> None:
    text = "from __future__ import annotations\n\nfrom functions import tidy\nimport os\n\nx = 1"
    assert rules.import_edit(text, "from functions import write_sqlite").to_json() == {
        "line": 3,
        "col": 27,
        "end_line": 3,
        "end_col": 27,
        "text": ", write_sqlite",
    }
    assert rules.import_edit(text, "import json").line == 5
    assert rules.import_edit("x = 1", "import json").text == "import json\n\n"  # apart from the code
    assert rules.import_edit('"""Doc."""\nx = 1', "import json").line == 2


def test_cells_say_what_they_make_and_use() -> None:
    assert rules.names_made("import pandas as pd\norders = pd.read_csv('a')\ndef f(): pass") >= {
        "pd",
        "orders",
        "f",
    }
    assert rules.names_made("%%sql Warehouse -> sales\nSELECT 1") == {"sales"}
    assert rules.names_used("print(orders.head())") == {"print", "orders"}


def test_sql_syntax_by_sqlglot_and_duckdb_errors_placed() -> None:
    [p] = rules.sql_problems("SELECT a FROM t WHERE", "postgres")
    assert p.code == "SQL" and p.line == 1
    assert rules.sql_problems("SELECT * FROM [Finance Captive].Sales", "duckdb") == []
    assert rules.sql_problems("SELECT [a] FROM [dbo].[t]", "tsql") == []
    message = 'Parser Error: syntax error at or near "t"\n\nLINE 2: FORM t WHERE\n             ^'
    placed = rules.duckdb_error(message, "SELECT a\nFORM t WHERE")
    assert (placed.line, placed.col, placed.end_col) == (2, 6, 7)
    assert placed.message == 'Syntax error at or near "t"'


def test_a_project_modules_public_names() -> None:
    source = (
        'def write_sqlite(connection: str, table: str, mode: str = "append") -> int:\n'
        '    """Write."""\n\ndef _hidden(): pass\nRATE = 0.2\nclass Loader: pass'
    )
    names = {n["name"]: n for n in rules.module_names(source)}
    assert set(names) == {"write_sqlite", "RATE", "Loader"}
    assert (
        names["write_sqlite"]["signature"]
        == "write_sqlite(connection: str, table: str, mode: str='append') -> int"
    )
    assert names["write_sqlite"]["doc"] == "Write."
    assert [n["name"] for n in rules.module_names('__all__ = ["a"]\na = 1\nb = 2')] == ["a"]
    assert rules.imported_names("from functions import a, b as c\nimport os.path, json as j") == {
        "a",
        "c",
        "os",
        "j",
    }


def test_ranking_puts_scope_first_and_the_recent_first_in_each_group() -> None:
    items = [
        {"label": "print", "group": "library"},
        {"label": "orders", "group": "scope"},
        {"label": "_hidden", "group": "scope"},
        {"label": "write_sqlite", "group": "project"},
        {"label": "Warehouse", "group": "app"},
        {"label": "order_count", "group": "scope"},
        {"label": "orders", "group": "library", "documentation": "from the library"},
    ]
    ranked = rules.rank(items, recent=["order_count"])
    assert [i["label"] for i in ranked] == [
        "order_count",
        "orders",
        "_hidden",
        "write_sqlite",
        "Warehouse",
        "print",
    ]
    assert ranked[1]["documentation"] == "from the library"  # the duplicate's words join
    assert [i["sort"] for i in ranked[:2]] == ["00000", "00001"]


def test_a_calls_required_arguments_are_tab_stops() -> None:
    params = [
        ("connection", True, False),
        ("table", True, False),
        ("mode", False, False),
        ("dry_run", True, True),
    ]
    assert (
        rules.snippet("write_sqlite", params) == "write_sqlite(${1:connection}, ${2:table}, dry_run=${3})$0"
    )
    assert rules.snippet("now", []) == "now($0)"
