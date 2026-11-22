"""Build inserts (Plans/api-adapter.plan.md, the owner's answers after the first build): an endpoint's
notebook cell goes into the open project's data.ipynb, its function into a script the user picks, and each is
opened there; the agent's actions(build) does the same. The rules (domain/api_actions.py: with_cell,
with_function, script_path) and the app over HTTP on a live server with the made-up orders service."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from swissarmybench.domain import api_actions as rules
from swissarmybench.domain import notebooks
from swissarmybench.server.app import create_app
from swissarmybench.settings import Settings
from tests.api_standins import Service
from tests.conftest import TOKEN
from tests.fake_keyring import memory_keyring
from tests.live_server import running
from tests.test_actions import add_orders, ask

CODE = (
    'import swissarmybench as sab\n\n\ndef get_order(order_id):\n    return sab.run("Orders", "get_order")\n'
)


def test_a_cell_goes_at_the_end_with_a_number_of_its_own() -> None:
    first = notebooks.write_notebook(
        [notebooks.Cell("code", "x = 1"), notebooks.Cell("markdown", "# Orders")],
        dictionary={"orders": {"amount": "What was paid"}},
    )
    written, number = rules.with_cell(first, "answer = 1\nanswer")
    cells, following = notebooks.read_document(written)
    assert number == 3 and following == 4 and [c.number for c in cells] == [1, 2, 3]
    assert cells[-1].kind == "code" and cells[-1].source == "answer = 1\nanswer"
    assert [c.source for c in cells[:2]] == ["x = 1", "# Orders"]  # every other cell as it was
    kept = json.loads(written)["metadata"][notebooks.OWN_KEY]
    assert kept["dictionary"] == {"orders": {"amount": "What was paid"}}  # the rest of the file is kept
    again, second = rules.with_cell(written, "more = 2")
    assert second == 4 and len(notebooks.read_notebook(again)) == 4
    # A deleted cell's number is never given again: the notebook's next number moves on.
    with pytest.raises(notebooks.NotebookError):
        rules.with_cell("not a notebook", "x = 1")


def test_a_function_goes_into_a_script_of_the_users_own() -> None:
    fresh, line = rules.with_function(None, CODE, "get_order")
    assert fresh == CODE and line == 4
    mine = '"""My orders."""\n\nimport json\n\n\ndef load():\n    return json.loads("[]")\n'
    written, line = rules.with_function(mine, CODE, "get_order")
    rows = written.split("\n")
    assert rows[line - 1] == "def get_order(order_id):"
    # Among its own imports.
    assert written.startswith('"""My orders."""\n\nimport json\nimport swissarmybench as sab\n')
    assert written.count("import swissarmybench as sab") == 1 and "def load():" in written
    compile(written, "orders.py", "exec")
    # Its import already there: only the function is added.
    twice, _ = rules.with_function(written.replace("get_order", "first_order"), CODE, "get_order")
    assert twice.count("import swissarmybench as sab") == 1
    with pytest.raises(rules.BuildError, match="has get_order already"):
        rules.with_function(written, CODE, "get_order")
    # No import of its own to stand beside: the import goes before the function.
    bare, at = rules.with_function("LIMIT = 5\n", CODE, "get_order")
    assert bare.startswith("LIMIT = 5\n") and "import swissarmybench as sab\n\n\ndef get_order" in bare
    assert bare.split("\n")[at - 1].startswith("def get_order(")


def test_a_script_is_a_py_of_the_users_inside_the_project() -> None:
    assert rules.script_path("scripts\\orders.py") == "scripts/orders.py"
    assert rules.script_path(" api_functions.py ") == "api_functions.py"
    for bad, said in (
        ("", "Name the script"),
        ("/etc/orders.py", "inside the project"),
        ("C:/orders.py", "inside the project"),
        ("../orders.py", "inside the project"),
        ("orders.txt", "a .py file"),
        ("API.py", "the app's to write"),
        ("data.py", "the app's to write"),
        ("lib/api_adapter.py", "the app's to write"),
        ("API_Orders.py", "the app's to write"),
    ):
        with pytest.raises(rules.BuildError, match=said):
            rules.script_path(bad)


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    settings = Settings(
        state_dir=tmp_path / "state",
        export_dir=tmp_path / "exports",
        auto_load_catalogs=False,
        projects_dir=tmp_path / "projects",
        workbench_dir=tmp_path / "wb",
    )
    with memory_keyring(), running(lambda port: create_app(port, TOKEN, settings)) as (port, _server):
        yield port


@pytest.fixture
def service() -> Iterator[Service]:
    running_service = Service().start()
    yield running_service
    running_service.stop()


def test_build_puts_the_cell_in_data_ipynb_and_the_function_in_the_script(
    live: int, service: Service, tmp_path: Path
) -> None:
    add_orders(live, service)
    ask(live, "POST", "/actions/run", {"api": "Orders", "action": "list_orders"})
    which = {"api": "Orders", "action": "list_orders"}
    # No project open: the code alone, to copy (as before).
    loose = ask(live, "POST", "/actions/build", which | {"as": "cell"})
    assert set(loose) == {"as", "code"}
    folder = tmp_path / "shop"
    ask(live, "POST", "/project/new", {"path": str(folder)})
    data = folder / "data.ipynb"
    before = len(notebooks.read_notebook(data.read_text(encoding="utf-8")))
    cell = ask(live, "POST", "/actions/build", which | {"as": "cell", "inputs": {"status": "open"}})
    assert Path(cell["path"]) == data and cell["cell"] >= 1 and "opened" not in cell
    cells = notebooks.read_notebook(data.read_text(encoding="utf-8"))
    assert len(cells) == before + 1 and cells[-1].number == cell["cell"]
    assert cells[-1].source == cell["code"]
    assert 'sab.run("Orders", "list_orders", {"status": "open"})' in cells[-1].source
    # The Notebooks page opens it as any notebook (its cell there by its number).
    opened = ask(live, "POST", "/workbench/open", {"path": str(data)})
    assert opened["cells"][-1]["number"] == cell["cell"]
    # "insert": false answers the code alone and writes nothing.
    only = ask(live, "POST", "/actions/build", which | {"as": "cell", "insert": False})
    assert set(only) == {"as", "code"}
    assert len(notebooks.read_notebook(data.read_text(encoding="utf-8"))) == before + 1
    # A function: into the script the user picks (made when it is not there), at its line.
    one = {"api": "Orders", "action": "get_order", "as": "function"}
    assert set(ask(live, "POST", "/actions/build", one)) == {"as", "code"}  # no script picked: to copy
    made = ask(live, "POST", "/actions/build", one | {"path": "scripts/orders.py"})
    script = folder / "scripts" / "orders.py"
    assert Path(made["path"]) == script and made["name"] == "get_order"
    text = script.read_text(encoding="utf-8")
    assert text.split("\n")[made["line"] - 1] == "def get_order(order_id):" and text == made["code"]
    more = ask(live, "POST", "/actions/build", which | {"as": "function", "path": "scripts/orders.py"})
    text = script.read_text(encoding="utf-8")
    assert text.count("import swissarmybench as sab") == 1 and "def list_orders(" in text
    assert text.split("\n")[more["line"] - 1].startswith("def list_orders(")
    compile(text, "orders.py", "exec")
    for body, said in (
        (one | {"path": "scripts/orders.py"}, "has get_order already"),
        (one | {"path": "../outside.py"}, "inside the project"),
        (one | {"path": "API.py"}, "the app's to write"),
    ):
        with pytest.raises(AssertionError, match=said):
            ask(live, "POST", "/actions/build", body)
    assert not (tmp_path / "outside.py").exists()
    # The agent's build does the same; with no Notebooks page open the answer says it was not shown.
    agents = ask(live, "POST", "/actions/build", which | {"as": "cell"}, agent=True)
    assert Path(agents["path"]) == data and agents["opened"] is False
    assert len(notebooks.read_notebook(data.read_text(encoding="utf-8"))) == before + 2
    log = json.dumps(ask(live, "GET", "/session-log"))
    assert "api_built" in log or "Orders list_orders" in log
