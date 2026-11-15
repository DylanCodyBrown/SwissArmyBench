"""Python's own checks on an exported script (services/script_export.py), by ruff when the app's
Python (or this computer) has it: the errors that stop a script, and a name used that nothing makes.
Nothing runs the script; its text goes to ruff on its standard input."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from typing import Any

# A script that cannot run as written: syntax, `return` outside a function, a name nothing makes.
RULES: str = "E9,F63,F7,F82"
TIMEOUT_SECONDS: float = 60.0


def _ruff() -> list[str] | None:
    if importlib.util.find_spec("ruff") is not None:
        return [sys.executable, "-m", "ruff"]
    found = shutil.which("ruff")
    return [found] if found else None


def lint(text: str) -> list[dict[str, Any]] | None:
    """ruff's findings, each {"line", "code", "message"}; None when there is no ruff to ask."""
    ruff = _ruff()
    if ruff is None:
        return None
    command = [*ruff, "check", "--isolated", "--select", RULES, "--output-format", "json"]
    command += ["--stdin-filename", "script.py", "-"]
    try:
        done = subprocess.run(  # noqa: S603 (ruff, with a fixed command)
            command, input=text, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False
        )
        found = json.loads(done.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return [
        {
            "line": int((f.get("location") or {}).get("row") or 0),
            "code": str(f.get("code") or ""),
            "message": str(f.get("message") or ""),
        }
        for f in found
        if isinstance(f, dict)
    ]
