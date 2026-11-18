"""Shared fixtures: a full app on a fake port, with its state in a temp folder."""

from __future__ import annotations

import io
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# The Streamlit extension, preinstalled with every install, from this checkout: on its path and switched on
# (SWISSARMYBENCH_EXTENSIONS) before anything of the app is imported, so the commands' registry and every
# server a test starts (in this process or its own) have it, as an installed app does. A test of the BI base
# without it turns it off ("-streamlit"); a child process finds it through PYTHONPATH.
STREAMLIT_SRC = str(Path(__file__).resolve().parents[1] / "extensions" / "streamlit" / "src")
if STREAMLIT_SRC not in sys.path:
    sys.path.insert(0, STREAMLIT_SRC)
if STREAMLIT_SRC not in os.environ.get("PYTHONPATH", "").split(os.pathsep):
    os.environ["PYTHONPATH"] = os.pathsep.join(p for p in (STREAMLIT_SRC, os.environ.get("PYTHONPATH")) if p)
if "streamlit" not in os.environ.get("SWISSARMYBENCH_EXTENSIONS", ""):
    os.environ["SWISSARMYBENCH_EXTENSIONS"] = ",".join(
        p for p in ("streamlit", os.environ.get("SWISSARMYBENCH_EXTENSIONS")) if p
    )

import pyarrow as pa  # noqa: E402
import pyarrow.ipc as ipc  # noqa: E402
import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from swissarmybench.server.app import create_app  # noqa: E402
from swissarmybench.settings import Settings  # noqa: E402

# The Accounting extension, from this checkout (it is not installed here: SWISSARMYBENCH_EXTENSIONS turns
# it on where a test wants it; off, nothing of it shows).
ACCOUNTING_SRC = str(Path(__file__).resolve().parents[1] / "extensions" / "accounting" / "src")
if ACCOUNTING_SRC not in sys.path:
    sys.path.insert(0, ACCOUNTING_SRC)
# The GitHub Copilot extension, the same way (tests/test_copilot*.py turn it on).
COPILOT_SRC = str(Path(__file__).resolve().parents[1] / "extensions" / "copilot" / "src")
if COPILOT_SRC not in sys.path:
    sys.path.insert(0, COPILOT_SRC)
# The Power Apps extension, the same way (tests/test_powerapps*.py turn it on).
POWERAPPS_SRC = str(Path(__file__).resolve().parents[1] / "extensions" / "powerapps" / "src")
if POWERAPPS_SRC not in sys.path:
    sys.path.insert(0, POWERAPPS_SRC)

# A server a test starts never opens a browser window (`swissarmybench start` does, by hand).
os.environ.setdefault("SWISSARMYBENCH_NO_BROWSER", "1")
# Nor a system file dialog (domain/file_dialogs.py): the page's own picker, on every system a test runs on.
os.environ["SWISSARMYBENCH_SYSTEM_DIALOGS"] = "off"

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
        # Never this machine's own Claude Code plugins: a test lays out its own packs here.
        claude_dir=overrides.pop("claude_dir", tmp_path / "claude"),
        # Never this computer's own sign-in entries: start at sign-in writes under a temporary home.
        autostart_home=overrides.pop("autostart_home", tmp_path / "home"),
        # Never this machine's own SwissArmyBench folder: the app makes it the first time it is needed.
        workbench_dir=overrides.pop("workbench_dir", tmp_path / "home" / "SwissArmyBench"),
        projects_dir=overrides.pop("projects_dir", tmp_path / "home" / "Swiss Army Bench Projects"),
        max_total_bytes=overrides.pop("max_total_bytes", 512 * 1024 * 1024),
        # Catalogs loading themselves start child processes: off unless a test is about them.
        auto_load_catalogs=overrides.pop("auto_load_catalogs", False),
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
