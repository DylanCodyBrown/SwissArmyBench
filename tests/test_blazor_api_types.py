"""The Blazor front end's generated answer records (blazor/tools/generate_api.py) are current: the generator
reads the server's own answers on made-up data and writes Api/<Area>/Generated/*.cs; a field the server
renames or drops makes these files differ, and the C# that read it no longer builds."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_generated_api_records_are_current() -> None:
    done = subprocess.run(  # noqa: S603 (our own script)
        [sys.executable, str(ROOT / "blazor" / "tools" / "generate_api.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert done.returncode == 0, (
        "Run python blazor/tools/generate_api.py and commit what it writes:\n" + done.stdout + done.stderr
    )
