"""duckpq stands alone: one file, the standard library and duckdb. It is imported in a bare Python with
swissarmybench, sqlglot, pyarrow and pandas blocked, and it names none of them in its source. Imports only
duckpq and the standard library."""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import duckpq

SOURCE = Path(duckpq.__file__)
ALLOWED = {
    "__future__",
    "collections",
    "dataclasses",
    "datetime",
    "json",
    "math",
    "os",
    "re",
    "typing",
    "duckdb",
}


def test_it_imports_only_the_standard_library_and_duckdb() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            seen.add((node.module or "").split(".")[0])
    assert seen <= ALLOWED, sorted(seen - ALLOWED)


def test_it_is_one_file_with_a_version_and_a_change_list() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert SOURCE.name == "duckpq.py"
    assert duckpq.__version__ in text.split('"""')[1], "the docstring's Changes lists the version"
    assert "not a Microsoft product" in text.split('"""')[1]
    for name in duckpq.__all__:
        assert hasattr(duckpq, name), name


def test_it_runs_in_a_bare_python_with_the_app_blocked(tmp_path: Path) -> None:
    """Copied alone into an empty folder; the app's packages and the optional libraries cannot be imported."""
    (tmp_path / "duckpq.py").write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "orders.csv").write_text("id,amount\n1,5\n2,50\n", encoding="utf-8")
    script = textwrap.dedent(
        """
        import sys

        class Blocked:
            NAMES = ("swissarmybench", "sqlglot", "pyarrow", "pandas", "numpy")
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in self.NAMES:
                    raise ImportError(name + " is blocked in this test")
                return None

        sys.meta_path.insert(0, Blocked())
        import duckpq

        assert duckpq.parse("let a = 1 in a").members[0].name == "Query"
        assert duckpq.check("Table.Nope(1)")[0].name == "Table.Nope"
        tables = duckpq.run(
            'Table.SelectRows(Table.PromoteHeaders(Csv.Document(File.Contents("orders.csv"))), each [amount] > 10)'
        )
        print(tables["Query"].fetchall())
        """
    )
    done = subprocess.run(  # noqa: S603 (this Python, a script written here)
        [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.')\n" + script],
        cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[(2, 50)]"


def test_parse_check_and_compile_need_no_duckdb(tmp_path: Path) -> None:
    (tmp_path / "duckpq.py").write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    script = textwrap.dedent(
        """
        import sys

        class Blocked:
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in ("duckdb", "swissarmybench"):
                    raise ImportError(name + " is blocked in this test")
                return None

        sys.meta_path.insert(0, Blocked())
        sys.path.insert(0, ".")
        import duckpq

        made = duckpq.compile('Table.SelectRows(#table({"x"}, {{1}, {5}}), each [x] > 2)')
        print(made.queries[0].sql)
        """
    )
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert (
        done.stdout.strip()
        == 'SELECT * FROM (SELECT "x" FROM (VALUES (1), (5)) AS v("x")) AS t WHERE (("x" > 2))'
    )


# Held like a one-file library: no function anyone cannot hold in the head, and one generous ceiling that is
# the owner's to raise (reaching it means the one-file design is due a look, not another bump).
CEILING = 5000
FUNCTION = 80


def test_no_function_is_over_80_lines_and_the_file_is_under_its_ceiling() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    long = {
        f"{node.name} (line {node.lineno})": (node.end_lineno or node.lineno) - node.lineno + 1
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and (node.end_lineno or node.lineno) - node.lineno + 1 > FUNCTION
    }
    assert long == {}
    assert len(text.splitlines()) <= CEILING
