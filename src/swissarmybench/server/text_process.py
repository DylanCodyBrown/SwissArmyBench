"""A short process that answers in text (a linter, a Python asked one question): the only place outside the
launcher where the editors' intelligence starts a process (only server/ may start one: test_client_install).

The adapters are handed `run_text` (bootstrap.py) and never import subprocess themselves.
"""

from __future__ import annotations

import subprocess


def run_text(
    argv: list[str], *, stdin: str | None = None, timeout: float, cwd: str | None = None
) -> tuple[int, str] | None:
    """The process's exit code and standard output; None when it could not run or ran out of time."""
    try:
        done = subprocess.run(  # noqa: S603 (a fixed command from the app's own code, never the user's text)
            argv, input=stdin, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.returncode, done.stdout
