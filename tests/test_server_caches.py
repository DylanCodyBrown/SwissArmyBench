"""The server's caches (the optimisation pass, 2026-11-19): each answers as the uncached code did, hands out
values of its own, and is cleared where what it keeps can change."""

from __future__ import annotations

from swissarmybench.domain import blades as rules
from swissarmybench.domain import portability, python_connections

CODE = (
    'import os\nimport pyodbc\nserver = "my-server"\nconn = pyodbc.connect(server, password=secret("pw"))\n'
)


def test_read_code_is_kept_but_each_call_gets_lists_of_its_own() -> None:
    first = rules.read_code(CODE)
    first.secrets.append("changed")
    first.imports.clear()
    again = rules.read_code(CODE)
    assert again.secrets == ["pw"] and again.imports == ["os", "pyodbc"] and again.variable == "conn"


def test_a_bad_code_still_says_its_label_each_time() -> None:
    for label in ("The code", "List the tables"):
        try:
            rules.read_code("def (", label)
        except rules.BladeCodeError as error:
            assert str(error).startswith(label)
        else:  # pragma: no cover
            raise AssertionError("not Python")


def test_settings_are_copies_a_caller_may_change() -> None:
    found = rules.detect_settings(CODE)
    assert [s.name for s in found] == ["server"]
    found[0].placeholder = False
    found[0].suggestions.append({"value": "x", "from": "y"})
    again = rules.detect_settings(CODE)
    assert again[0].placeholder is True and again[0].suggestions == []
    assert again[0].text == "my-server"
    # apply_settings reads the same kept settings
    assert '"prod"' in rules.apply_settings(CODE, {again[0].id: "prod"})


def test_import_lines_and_env_reads_are_lists_of_their_own() -> None:
    lines = rules.import_lines(CODE)
    lines.append("import x")
    assert rules.import_lines(CODE) == ["import os", "import pyodbc"]
    reads = python_connections.env_reads('import os\nos.environ["A"]', None)
    reads.clear()
    assert [r.name for r in python_connections.env_reads('import os\nos.environ["A"]', None)] == ["A"]


def test_portability_check_is_kept_by_all_its_inputs() -> None:
    assert [f.key for f in portability.check(CODE, "sqlserver")] != []
    with_keyring = portability.check("x = 1", None, ["keyring"])
    assert [f.key for f in with_keyring] == [portability.KEYRING.key]
    assert portability.check("x = 1", None, []) == []
    with_keyring.clear()
    assert portability.check("x = 1", None, ("keyring",)) != []
