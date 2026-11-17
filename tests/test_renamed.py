"""Swiss Army Bench was SwissArmyGrid: every old name that still works for one release (renamed.py), and
that new files are written under the new names. Made-up data only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench import renamed
from swissarmybench.adapters.blades import KEYRING_SERVICE, OLD_KEYRING_SERVICE, BladeStore
from swissarmybench.client import html_cells, sql_cell, table_cells
from swissarmybench.domain import blades as blade_rules
from swissarmybench.domain import notebooks, relationships
from swissarmybench.server import launcher
from swissarmybench_streamlit.domain import streamlit_cells
from tests.conftest import AUTH, make_client
from tests.fake_keyring import MemoryKeyring, memory_keyring

ROOT = Path(__file__).resolve().parents[1]
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith(("SWISSARMYBENCH_", "SWISSARMYGRID_"))}


# ===== environment variables =====


def test_the_new_variable_comes_first_then_the_old_one() -> None:
    both = {"SWISSARMYBENCH_INFO": "/new.json", "SWISSARMYGRID_INFO": "/old.json"}
    assert renamed.env("SWISSARMYBENCH_INFO", environ=both) == "/new.json"
    assert renamed.env("SWISSARMYBENCH_INFO", environ={"SWISSARMYGRID_INFO": "/old.json"}) == "/old.json"
    assert renamed.env("SWISSARMYBENCH_INFO", "none", environ={}) == "none"


def test_the_old_variables_reach_the_settings_and_the_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from swissarmybench.cli import api
    from swissarmybench.client import push_client
    from swissarmybench.settings import Settings

    for name in ("STATE", "INFO", "MAX_DATASET_MB"):
        monkeypatch.delenv(f"SWISSARMYBENCH_{name}", raising=False)
    monkeypatch.setenv("SWISSARMYGRID_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("SWISSARMYGRID_INFO", str(tmp_path / "server.json"))
    monkeypatch.setenv("SWISSARMYGRID_MAX_DATASET_MB", "7")
    settings = Settings()
    assert settings.state_dir == tmp_path / "state" and settings.max_dataset_bytes == 7 * 1024 * 1024
    assert push_client.info_file() == api.info_file() == tmp_path / "server.json"


def test_the_launcher_finds_the_old_server_variable_and_the_old_tool() -> None:
    found = launcher.tool_pythons({"SWISSARMYGRID_SERVER": "/dev/old"}, Path("/home/me"), "linux", None)
    assert found == [Path("/dev/old")]
    both = {"SWISSARMYBENCH_SERVER": "/dev/new", "SWISSARMYGRID_SERVER": "/dev/old"}
    assert launcher.tool_pythons(both, Path("/home/me"), "linux", None) == [Path("/dev/new")]
    old = Path("/home/me/.local/share/uv/tools/swissarmygrid/bin/python")
    new = Path("/home/me/.local/share/uv/tools/swissarmybench/bin/python")
    assert launcher.tool_pythons({}, Path("/home/me"), "linux", None) == [new, old]
    # The old tool has only the old package: it is run by its old name.
    assert launcher.server_module(old) == "swissarmygrid.server"
    assert launcher.server_module(new) == "swissarmybench.server"


# ===== the state folder and the Workbench's folder =====


def test_the_old_state_folder_is_read_until_it_moves(tmp_path: Path) -> None:
    assert renamed.home_state_folder(tmp_path) == tmp_path / ".swissarmybench"
    (tmp_path / ".swissarmygrid").mkdir()
    assert renamed.home_state_folder(tmp_path) == tmp_path / ".swissarmygrid"
    (tmp_path / ".swissarmybench").mkdir()
    assert renamed.home_state_folder(tmp_path) == tmp_path / ".swissarmybench"


def test_the_first_start_moves_the_old_state_folder_and_says_so_once(tmp_path: Path) -> None:
    old = tmp_path / ".swissarmygrid"
    (old / "blades").mkdir(parents=True)
    (old / "blades" / "bakery.json").write_text('{"name": "Bakery"}', encoding="utf-8")
    said = renamed.move_state_folder(tmp_path, environ={})
    assert said is not None and str(tmp_path / ".swissarmybench") in said
    assert not old.exists()
    assert (tmp_path / ".swissarmybench" / "blades" / "bakery.json").read_text(encoding="utf-8") == (
        '{"name": "Bakery"}'
    )
    assert renamed.move_state_folder(tmp_path, environ={}) is None  # once: nothing left to move


def test_nothing_moves_when_the_new_folder_is_there_or_a_folder_was_named(tmp_path: Path) -> None:
    (tmp_path / ".swissarmygrid").mkdir()
    for named in (
        {"SWISSARMYBENCH_STATE": "/x"},
        {"SWISSARMYGRID_STATE": "/x"},
        {"SWISSARMYBENCH_INFO": "/x"},
    ):
        assert renamed.move_state_folder(tmp_path, environ=named) is None
    (tmp_path / ".swissarmybench").mkdir()
    assert renamed.move_state_folder(tmp_path, environ={}) is None
    assert (tmp_path / ".swissarmygrid").is_dir()


def test_a_folder_that_cannot_move_is_read_where_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = tmp_path / ".swissarmygrid"
    old.mkdir()
    in_use = renamed.move_state_folder(tmp_path, environ={}, in_use=lambda info: True)
    assert in_use is not None and "read where it is" in in_use and old.is_dir()

    def refuse(self: Path, target: Path) -> Path:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(Path, "rename", refuse)
    said = renamed.move_state_folder(tmp_path, environ={})
    assert said is not None and "could not be moved" in said and "Access is denied" in said
    assert renamed.home_state_folder(tmp_path) == old


def test_the_server_moves_the_old_folder_on_its_first_start(tmp_path: Path) -> None:
    """The real thing: `swissarmybench status` reads the old folder, `start` moves it."""
    home = tmp_path / "home"
    (home / ".swissarmygrid").mkdir(parents=True)
    (home / ".swissarmygrid" / "last_port").write_text("0", encoding="utf-8")
    env = CLEAN | {"HOME": str(home), "USERPROFILE": str(home), "SWISSARMYBENCH_OPEN": "0"}
    script = (
        "import sys\n"
        "from swissarmybench.server import __main__ as m\n"
        "m.Settings = lambda: (_ for _ in ()).throw(SystemExit(0))\n"  # stop right after the move
        "m.start(0)\n"
    )
    done = subprocess.run(  # noqa: S603 (this test's own interpreter and script)
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    assert "is now" in done.stderr and str(home / ".swissarmybench") in done.stderr
    assert (home / ".swissarmybench" / "last_port").is_file() and not (home / ".swissarmygrid").exists()


def test_the_old_workbench_folder_stays_while_only_it_is_there(tmp_path: Path) -> None:
    assert renamed.workbench_folder(tmp_path) == tmp_path / "SwissArmyBench"
    (tmp_path / "SwissArmyGrid").mkdir()
    assert renamed.workbench_folder(tmp_path) == tmp_path / "SwissArmyGrid"


# ===== the keyring =====


@pytest.fixture
def vault() -> Iterator[MemoryKeyring]:
    with memory_keyring() as fake:
        yield fake


def test_a_password_saved_under_the_old_name_is_found_and_copied_across(
    tmp_path: Path, vault: MemoryKeyring
) -> None:
    store = BladeStore(tmp_path / "blades")
    store.save(
        {
            "name": "Bakery",
            "kind": "other",
            "code": "import sqlite3\npassword = secret('password')\nconn = sqlite3.connect(':memory:')\n",
        }
    )
    vault.values[(OLD_KEYRING_SERVICE, "blade/bakery/password")] = "sourdough-starter"
    assert store.secret_status("Bakery") == {"password": True}
    assert vault.values[(KEYRING_SERVICE, "blade/bakery/password")] == "sourdough-starter"
    assert store._secret("Bakery", "password") == "sourdough-starter"
    # Forgetting it forgets both, so the old entry cannot come back.
    store.set_secrets("Bakery", {"password": None})
    assert vault.values == {}


def test_the_new_entry_wins_over_the_old_one(tmp_path: Path, vault: MemoryKeyring) -> None:
    store = BladeStore(tmp_path / "blades")
    vault.values[(OLD_KEYRING_SERVICE, "blade/x/token")] = "old-made-up"
    vault.values[(KEYRING_SERVICE, "blade/x/token")] = "new-made-up"
    assert store._secret("x", "token") == "new-made-up"
    assert vault.values[(OLD_KEYRING_SERVICE, "blade/x/token")] == "old-made-up"


# ===== old files: notebooks, blades, tangs, Streamlit apps and their pages =====


def test_an_old_notebooks_metadata_is_read_and_written_under_the_new_key() -> None:
    old = {
        "cells": [
            {
                "cell_type": "code",
                "metadata": {"swissarmygrid": {"number": 4, "name": "regions"}},
                "source": "%%sql Shop\nSELECT 1",
                "outputs": [],
                "execution_count": None,
            },
            {
                "cell_type": "code",
                "metadata": {"swissarmygrid": {"number": 7, "kind": "html"}},
                "source": "%%html\n<p>made-up</p>",
                "outputs": [],
                "execution_count": None,
            },
        ],
        "metadata": {"swissarmygrid": {"next_cell": 9}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    cells, following = notebooks.read_document(json.dumps(old))
    assert [c.number for c in cells] == [4, 7] and following == 9
    assert cells[0].kind == "sql" and cells[0].connection == "Shop" and cells[1].kind == "html"
    written = json.loads(notebooks.write_notebook(cells, next_number=following))
    assert "swissarmygrid" not in json.dumps(written)
    assert written["metadata"]["swissarmybench"] == {"next_cell": 9}
    assert written["cells"][0]["metadata"]["swissarmybench"]["number"] == 4


def test_an_old_sag_sql_cell_is_still_a_sql_cell() -> None:
    old = {
        "cells": [{"cell_type": "code", "metadata": {}, "source": "%%sag Shop\nSELECT 2", "outputs": []}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    cell = notebooks.read_notebook(json.dumps(old))[0]
    assert cell.kind == "sql" and cell.connection == "Shop" and cell.source == "SELECT 2"


def _portable(header: str) -> str:
    """A made-up blade's portable file, under `header`."""
    blade = blade_rules.parse_blade(
        {
            "name": "Made-up bakery",
            "kind": "other",
            "code": "import sqlite3\n\nconn = sqlite3.connect(':memory:')\n",
        }
    )
    text = blade_rules.write_blade(blade.to_json())
    assert text.startswith("# /// swissarmybench-blade\n")  # written with the new header
    return text.replace("swissarmybench-blade", header, 1)


def test_an_old_blade_header_is_still_a_blade_and_exports_with_the_new_one() -> None:
    old = _portable("swissarmygrid-blade")
    assert blade_rules.is_blade(old)
    read = blade_rules.read_blade(old)
    assert read["name"] == "Made-up bakery"
    assert blade_rules.is_blade(_portable("swissarmybench-blade"))
    assert not blade_rules.is_blade(_portable("someone-elses-blade"))
    # An old blade that imports the old package needs nothing from pip.
    assert blade_rules.provided("swissarmygrid") and blade_rules.provided("swissarmybench")


def test_an_old_tang_is_read_and_a_new_one_written_under_the_new_mark() -> None:
    tang = {
        "swissarmygrid": "tang",
        "format": 1,
        "name": "Made-up store",
        "tables": {"orders": {"primary_key": ["order_id"], "columns": [["order_id", "BIGINT"]]}},
        "relationships": [],
    }
    model = relationships.read_set(json.dumps(tang))
    assert model.name == "Made-up store"
    # Under the newer name too: "swissarmybench": "tang" (a tang until 2026-11-17) reads as a set.
    assert relationships.read_set(json.dumps({**tang, "swissarmybench": "tang"})).name == "Made-up store"
    written = json.loads(relationships.write_set(model))
    assert written["swissarmybench"] == "relationship-set" and "swissarmygrid" not in written
    assert relationships.set_file_name("Made-up store") == "made-up_store.relationships.json"
    with pytest.raises(relationships.RelationshipSetError):
        relationships.read_set(json.dumps({"someone": "tang", "format": 1}))


def test_an_old_streamlit_app_and_its_old_saved_pages_are_still_its_own() -> None:
    old = '{"swissarmygrid": "streamlit-app", "version": 1, "pages": [{"name": "Overview", "blocks": []}]}'
    pages = streamlit_cells.read_app(old)
    assert [p.name for p in pages] == ["Overview"]
    assert '"swissarmybench": "streamlit-app"' in streamlit_cells.write_app(pages)
    old_page = (
        '"""Overview"""\n'
        "# Written from sales.stapp.json by SwissArmyGrid: change the canvas, not this file.\n"
    )
    assert streamlit_cells.is_saved_page(old_page, "sales.stapp.json")
    assert not streamlit_cells.is_saved_page(old_page, "other.stapp.json")
    assert "Swiss Army Bench" in streamlit_cells.page_mark("sales.stapp.json")


# ===== the magics =====


class Shell:
    def __init__(self) -> None:
        self.user_ns: dict[str, Any] = {}
        self.cells: dict[str, Any] = {}
        self.lines: dict[str, Any] = {}

    def find_cell_magic(self, name: str) -> Any:
        return self.cells.get(name)

    def find_line_magic(self, name: str) -> Any:
        return self.lines.get(name)

    def register_magic_function(self, fn: Any, magic_kind: str, magic_name: str) -> None:
        (self.cells if magic_kind == "cell" else self.lines)[magic_name] = fn


def test_the_old_magics_are_the_new_ones() -> None:
    shell = Shell()
    table_cells.install(shell)
    html_cells.install(shell)
    sql_cell.register(shell)
    for new, old in (("sab_table", "sag_table"), ("sab_html", "sag_html"), ("sab", "sag")):
        assert shell.cells[old] is shell.cells[new], old
    assert shell.lines["sag_run"] is shell.lines["sab_run"]
    assert shell.lines["sag_connect"] is shell.lines["sab_connect"]
    assert "sql" in shell.cells and "dax" in shell.cells  # unchanged


# ===== the old package and the old commands =====


def _python(code: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (this test's own interpreter and script)
        [sys.executable, "-W", "always::DeprecationWarning", "-c", code],
        capture_output=True,
        text=True,
        env=CLEAN | {"SWISSARMYBENCH_WATCH": "0"} | env,
        timeout=60,
        check=False,
    )


def test_import_swissarmygrid_is_the_new_package_with_a_warning() -> None:
    done = _python(
        "import swissarmygrid as sag, swissarmybench as sab\n"
        "import swissarmygrid.client.push_client as old, swissarmybench.client.push_client as new\n"
        "from swissarmygrid.domain.blades import HEADER_TYPE\n"
        "print(old is new, sag.push is sab.push, sag.sql is sab.sql, sag.__version__ == sab.__version__)\n"
        "print(HEADER_TYPE)\n"
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["True", "True", "True", "True", "swissarmybench-blade"]
    assert "DeprecationWarning" in done.stderr and "import swissarmybench as sab" in done.stderr


def test_python_m_with_the_old_name_runs_the_new_server(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "swissarmygrid.server", "status"],
        capture_output=True,
        text=True,
        env=CLEAN | {"SWISSARMYBENCH_INFO": str(tmp_path / "none.json")},
        timeout=60,
        check=False,
    )
    assert done.returncode == 1 and "Swiss Army Bench is not running." in done.stdout, done.stderr


def test_the_old_commands_are_installed_and_say_the_new_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["swissarmybench"] == "swissarmybench.server.launcher:main"
    assert scripts["sab"] == "swissarmybench.cli.main:main"
    old = {
        "swissarmygrid": ("swissarmybench.server.launcher", "swissarmybench"),
        "sag": ("swissarmybench.cli.main", "sab"),
        "swissarmygrid-mcp": ("swissarmybench.mcp.server", "swissarmybench-mcp"),
        "swissarmygrid-context": ("swissarmybench.client.context_hook", "swissarmybench-context"),
    }
    import importlib

    for command, (module, new) in old.items():
        target = scripts[command]
        assert target.startswith("swissarmybench.renamed:"), command
        ran: list[str] = []
        monkeypatch.setattr(importlib.import_module(module), "main", lambda ran=ran: ran.append("ran"))
        getattr(renamed, target.split(":")[1])()
        said = capsys.readouterr()
        assert ran == ["ran"] and said.out == ""  # stdout stays the command's own (MCP, the hook)
        assert said.err.strip() == f"`{command}` is now `{new}`; the old name goes in the next release."


def test_the_old_sag_command_runs_the_agent_commands() -> None:
    done = subprocess.run(
        [sys.executable, "-c", "from swissarmybench.renamed import sag; sag()", "--help"],
        capture_output=True,
        text=True,
        env=CLEAN,
        timeout=60,
        check=False,
    )
    assert "`sag` is now `sab`" in done.stderr
    assert done.stdout.strip(), done.stderr


def test_a_kernel_is_lent_the_old_name_too() -> None:
    from swissarmybench.server.environments import client_path

    holder = Path(client_path())
    assert (holder / "swissarmybench" / "__init__.py").is_file()
    assert (holder / "swissarmygrid" / "__init__.py").is_file()


# ===== the old websocket subprotocol =====


def test_a_client_offering_the_old_subprotocol_is_answered_in_it(tmp_path: Path) -> None:
    host = {"Host": "127.0.0.1:8765"}
    with make_client(tmp_path) as client:
        for offered in ("swissarmygrid", "swissarmybench"):
            with client.websocket_connect(
                "/ws?workspace=1", headers=AUTH | host, subprotocols=[offered, "test-token"]
            ) as socket:
                assert socket.accepted_subprotocol == offered


# ===== an HTML cell's output saved before the rename =====


def test_an_old_html_cell_output_is_still_read() -> None:
    from swissarmybench.cli.commands import _outputs

    detail: dict[str, Any] = {"values": {}, "marks": {}, "missing": []}
    lines = [
        {
            "output_type": "display_data",
            "data": {"text/html": "<p>made-up</p>", "application/vnd.swissarmygrid.html-cell+json": detail},
        },
        {"done": {"ok": True}},
    ]
    shown = _outputs(lines)
    assert any("design" in item for item in shown["outputs"]), shown
