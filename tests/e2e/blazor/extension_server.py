"""A server of its own for the extensions' Blazor pages: the extensions named on (each one's src folder on the
path), a state folder of its own, made-up data only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


@contextmanager
def extension_server(
    tmp: Path, extensions: list[str], extra: dict[str, str] | None = None
) -> Iterator[dict[str, Any]]:
    env = (
        os.environ
        | {
            "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
            "SWISSARMYBENCH_STATE": str(tmp / "state"),
            "SWISSARMYBENCH_EXTENSIONS": ",".join(extensions),
            "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
            "SWISSARMYBENCH_PROJECTS_DIR": str(tmp / "projects"),
            "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "workbench"),
            "SWISSARMYBENCH_NO_BROWSER": "1",
            "SWISSARMYBENCH_SYSTEM_DIALOGS": "off",
            "SWISSARMYBENCH_PROJECT_VENV": "off",
            "PYTHON_KEYRING_BACKEND": "tests.file_keyring.FileKeyring",
            "SAB_TEST_KEYRING_FILE": str(tmp / "keyring.json"),
            "PYTHONPATH": os.pathsep.join(
                [str(ROOT / "extensions" / name / "src") for name in extensions]
                + [str(ROOT), str(ROOT / "src")]
            ),
        }
        | (extra or {})
    )
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    info: dict[str, Any] | None = None
    for _ in range(300):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    try:
        assert info is not None, "the server did not start"
        yield info | {"tmp": tmp}
    finally:
        process.terminate()
        process.wait(timeout=20)
