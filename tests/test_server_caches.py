"""The server's caches (the optimisation pass, 2026-11-19): each answers as the uncached code did, hands out
values of its own, and is cleared where what it keeps can change."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swissarmybench.adapters.blades import KEYRING_SERVICE, SECRET_STATUS_SECONDS, BladeStore
from swissarmybench.domain import blades as rules
from swissarmybench.domain import portability, python_connections
from tests.fake_keyring import memory_keyring

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


def test_a_secret_saved_or_forgotten_here_is_said_at_once(tmp_path: Path) -> None:
    with memory_keyring() as vault:
        store = BladeStore(tmp_path / "blades")
        store.save({"name": "Bakery", "kind": "other", "code": "password = secret('password')\n"})
        assert store.secret_status("Bakery") == {"password": False}
        store.set_secrets("Bakery", {"password": "made-up"})
        assert store.secret_status("Bakery") == {"password": True}
        assert store.providers(store.get("Bakery"))[0] == []
        store.set_secrets("Bakery", {"password": None})
        assert store.secret_status("Bakery") == {"password": False}
        # Changed outside the app: said once the kept answer is older than SECRET_STATUS_SECONDS.
        vault.values[(KEYRING_SERVICE, "blade/bakery/password")] = "made-up"
        assert store.secret_status("Bakery") == {"password": False}
        kept = store.secrets._saved_status
        store.secrets._saved_status = {
            user: (when - SECRET_STATUS_SECONDS, saved) for user, (when, saved) in kept.items()
        }
        assert store.secret_status("Bakery") == {"password": True}


def test_a_starter_found_by_name_follows_its_file(tmp_path: Path) -> None:
    starters = tmp_path / "starters"
    starters.mkdir()

    def starter(file: str, name: str, description: str) -> None:
        blade = {"name": name, "kind": "other", "code": "x = 1\n", "description": description}
        (starters / file).write_text(rules.write_blade(blade), encoding="utf-8")

    starter("a.blade.py", "Made up", "first")
    store = BladeStore(tmp_path / "blades", starters=starters)
    assert store.get("made up").description == "first"  # not listed yet: found by listing them
    assert store.get("Made up").description == "first"  # from the index
    starter("a.blade.py", "Made up", "changed and longer")
    assert store.get("Made up").description == "changed and longer"
    (starters / "a.blade.py").unlink()
    starter("b.blade.py", "Made up", "moved")
    assert store.get("Made up").description == "moved"
    (starters / "b.blade.py").unlink()
    try:
        store.get("Made up")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("a starter gone is gone")


def test_start_up_catalogs_wait_for_the_first_window_or_the_time_limit() -> None:
    import asyncio
    import time

    from swissarmybench.services.catalog_loading import CatalogLoading

    def loading(windows: list[int]) -> tuple[CatalogLoading, list[float]]:
        started: list[float] = []
        made = CatalogLoading.__new__(CatalogLoading)
        made._enabled = True
        made._windows = lambda: windows[0]

        def at_start() -> list[str]:
            started.append(time.monotonic())
            return []

        made.at_start = at_start  # type: ignore[method-assign]
        return made, started

    async def scenario() -> None:
        # No window ever: after the wait.
        made, started = loading([0])
        began = time.monotonic()
        await made.at_start_later(wait=0.3, settle=5)
        assert len(started) == 1 and 0.25 <= started[0] - began < 2
        # A window opens: then, after the page settles; long before the wait.
        windows = [0]
        made, started = loading(windows)
        began = time.monotonic()
        task = asyncio.create_task(made.at_start_later(wait=30, settle=0.1))
        await asyncio.sleep(0.3)
        assert started == []
        windows[0] = 1
        await asyncio.wait_for(task, 5)
        assert len(started) == 1 and started[0] - began < 5
        # Loading off: nothing.
        made, started = loading([1])
        made._enabled = False
        assert await made.at_start_later(wait=0, settle=0) == [] and started == []

    asyncio.run(scenario())


def test_step_counts_are_kept_until_the_steps_or_the_rows_change(tmp_path: Path) -> None:
    import pyarrow as pa

    from tests.conftest import AUTH, grid_id, make_client, push

    def orders(regions: list[str]) -> pa.Table:
        return pa.table({"id": pa.array(range(len(regions)), pa.int64()), "region": pa.array(regions)})

    def counts(client: Any, grid: str) -> list[int]:
        answer = client.get(f"/grids/{grid}/step-counts", headers=AUTH)
        assert answer.status_code == 200, answer.text
        return list(answer.json()["counts"])

    keep_north = [{"kind": "filter", "params": {"column": "region", "op": "eq", "value": "North"}}]
    with make_client(tmp_path) as client:
        grid = grid_id(push(client, "orders", orders(["North", "South", "North"])))
        assert counts(client, grid) == [3]
        assert (
            client.post(f"/grids/{grid}/steps", json={"steps": keep_north}, headers=AUTH).status_code == 200
        )
        assert counts(client, grid) == [3, 2] == counts(client, grid)
        push(client, "orders", orders(["North", "South", "South", "South"]))  # pushed again: new rows
        assert counts(client, grid) == [4, 1]
        assert client.post(f"/grids/{grid}/steps", json={"steps": []}, headers=AUTH).status_code == 200
        assert counts(client, grid) == [4]


def test_the_grammar_is_read_on_its_first_use_and_is_duckdbs() -> None:
    from swissarmybench.adapters.database import duckdb_grammar, grammar_later

    later, now = grammar_later(), duckdb_grammar()
    assert later.keywords == now.keywords and later.reserved == now.reserved
    assert later.table_functions == now.table_functions and "select" in later.keywords
    assert later.parse("SELECT 1") == now.parse("SELECT 1")


def test_the_index_and_guide_pages_are_read_again_when_they_change(tmp_path: Path) -> None:
    from swissarmybench.adapters.claude import ClaudeFiles

    files = ClaudeFiles(tmp_path / "claude", None)
    page = tmp_path / "page.md"
    page.write_text("# One\n", encoding="utf-8")
    assert files._page(page) == "# One\n" == files._page(page)
    page.write_text("# Two, longer\n", encoding="utf-8")
    assert files._page(page) == "# Two, longer\n"
    assert files.index() and files.guide("no-such-topic") == ""
