"""Shared fixtures: a full app on a fake port, with its state in a temp folder."""

from __future__ import annotations

import atexit
import io
import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# Every feature is built in (the owner, 2026-11-27): the app's package and each feature's own sit side by side
# in src/. A child process a test starts finds them through PYTHONPATH.
SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in os.environ.get("PYTHONPATH", "").split(os.pathsep):
    os.environ["PYTHONPATH"] = os.pathsep.join(p for p in (SRC, os.environ.get("PYTHONPATH")) if p)

# Folder extensions (the library's extensions/<id>/): none in a test unless it makes one
# (test_folder_extensions.py points this at its own folder); never the real home's library, and never a folder
# of the repository that every run shares: one a failed run left there was found by the next run. An empty
# temporary folder of this process's own, removed as it ends.
_NO_EXTENSIONS = tempfile.mkdtemp(prefix="sab-no-extensions-")
atexit.register(shutil.rmtree, _NO_EXTENSIONS, ignore_errors=True)
os.environ["SWISSARMYBENCH_EXTENSION_FOLDERS"] = _NO_EXTENSIONS

import pyarrow as pa  # noqa: E402
import pyarrow.ipc as ipc  # noqa: E402
import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from swissarmybench.server.app import create_app  # noqa: E402
from swissarmybench.settings import Settings  # noqa: E402

# A server a test starts never opens a browser window (`swissarmybench start` does, by hand).
os.environ.setdefault("SWISSARMYBENCH_NO_BROWSER", "1")
# A server a test starts lives for the test's whole run (services/lifecycle.py stops it once no window of the
# app is open: the browser tests open and close pages all along). A test about its life sets its own.
for _name in ("GRACE", "START_GRACE", "IDLE"):
    os.environ.setdefault(f"SWISSARMYBENCH_LIFE_{_name}", "86400")
# Nor a system file dialog (domain/file_dialogs.py): the page's own picker, on every system a test runs on.
os.environ["SWISSARMYBENCH_SYSTEM_DIALOGS"] = "off"
# Nor a project's own .venv made as it opens (services/project_python.py: a download and a minute): a test
# about it asks (Settings(project_venv=True)) and stands the making in (tests/libraries_standin.py).
os.environ.setdefault("SWISSARMYBENCH_PROJECT_VENV", "off")
# Missing packages never installed by a run here (server/blade_runner.py install_missing): its test asks.
os.environ.setdefault("SWISSARMYBENCH_AUTO_INSTALL", "off")

PORT = 8765
TOKEN = "test-token"
BASE = f"http://127.0.0.1:{PORT}"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
AGENT = AUTH | {"X-Actor": "agent"}
ARROW = "application/vnd.apache.arrow.stream"


@pytest.fixture(autouse=True, scope="session")
def no_folder_in_the_real_home(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """The app makes its own folder (SwissArmyBench in the home folder) the first time it is needed.
    In tests that folder is a temporary one, for every server a test starts (in this process or its own)."""
    import os

    # Nor a tray, nor an update check (nothing leaves this computer): a test that is about them asks.
    wanted = {
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp_path_factory.mktemp("home") / "SwissArmyBench"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(tmp_path_factory.mktemp("projects") / "Swiss Army Bench Projects"),
        "SWISSARMYBENCH_TRAY": "0",
        "SWISSARMYBENCH_UPDATE_FEED": "none",
        # Sharing's devtunnel: the stand-in, never Microsoft's download (nothing leaves this computer).
        "SWISSARMYBENCH_DEVTUNNEL_STANDIN": str(Path(__file__).parent / "devtunnel_standin.py"),
    }
    before = {key: os.environ.get(key) for key in wanted}
    os.environ.update(wanted)
    yield
    for key, value in before.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def make_client(tmp_path: Path, **overrides: Any) -> TestClient:
    settings = Settings(
        state_dir=tmp_path / "state",
        export_dir=tmp_path / "exports",
        # Never this machine's own SwissArmyBench folder: the app makes it the first time it is needed.
        workbench_dir=overrides.pop("workbench_dir", tmp_path / "home" / "SwissArmyBench"),
        projects_dir=overrides.pop("projects_dir", tmp_path / "home" / "Swiss Army Bench Projects"),
        max_total_bytes=overrides.pop("max_total_bytes", 512 * 1024 * 1024),
        # Catalogs loading themselves start child processes: off unless a test is about them.
        auto_load_catalogs=overrides.pop("auto_load_catalogs", False),
        # A vault's names read again at start: a child process each, off unless a test is about it.
        auto_read_vaults=overrides.pop("auto_read_vaults", False),
        **overrides,
    )
    return TestClient(create_app(PORT, TOKEN, settings), base_url=BASE)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        yield test_client


def arrow_bytes(table: pa.Table) -> bytes:
    sink = io.BytesIO()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return sink.getvalue()


def push(
    client: TestClient,
    name: str,
    table: pa.Table,
    query: str = "",
    headers: dict[str, str] | None = None,
) -> Any:
    return client.put(
        f"/datasets/{name}{query}",
        content=arrow_bytes(table),
        headers=(headers or AUTH) | {"Content-Type": ARROW, "X-Source-Kind": "arrow"},
    )


def push_json(client: TestClient, name: str, payload: Any) -> Any:
    return client.put(
        f"/datasets/{name}",
        content=json.dumps(payload).encode(),
        headers=AUTH | {"Content-Type": "application/json"},
    )


def grid_id(response: Any) -> str:
    assert response.status_code == 200, response.text
    return str(response.json()["grid"])
