"""The system's own file dialog, in a short-lived child process (domain/file_dialogs.py makes its plan). Here
because only server/ starts processes. One dialog at a time; ten minutes at most; on the user's click only
(services/file_dialogs.py refuses the agent).

  status   which tool this computer's dialogs open with, or why none (asked once: Tk's check starts a Python)
  choose   the dialog opened, its answer read: {"path"}, {"cancelled": true}, {"busy": true}, or DialogFailed
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from swissarmybench.domain import file_dialogs as rules

Run = Callable[..., "subprocess.CompletedProcess[str]"]


def nearest_folder(start: str | None) -> str:
    """The folder a dialog starts in: `start` (a file's folder for a file), else the nearest folder above it
    that exists, else the home folder."""
    home = str(Path.home())
    if not start:
        return home
    try:
        path = Path(start).expanduser()
        for candidate in (path, *path.parents):
            if candidate.is_dir():
                return str(candidate)
    except OSError:
        pass
    return home


class DialogRunner:
    def __init__(
        self,
        env: Mapping[str, str] | None = None,
        platform: str = sys.platform,
        which: Callable[[str], str | None] = shutil.which,
        python: str = sys.executable,
        run: Run = subprocess.run,
        time_limit: int = rules.TIME_LIMIT_SECONDS,
    ) -> None:
        self._env = os.environ if env is None else env
        self._platform, self._which, self._python, self._run = platform, which, python, run
        self._time_limit = time_limit
        self._lock = threading.Lock()
        self._found: tuple[str | None, str] | None = None

    def _tk(self) -> bool:
        try:
            done = self._run(
                [self._python, "-I", "-c", "import tkinter; tkinter.Tcl()"],
                capture_output=True,
                text=True,
                timeout=30,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == 0

    def status(self) -> dict[str, Any]:
        if self._found is None:
            self._found = rules.choose_tool(
                self._platform, self._env, lambda c: self._which(c) is not None, self._tk
            )
        tool, reason = self._found
        return {"system": tool is not None, "tool": tool} | ({"reason": reason} if reason else {})

    def choose(self, request: rules.DialogRequest) -> dict[str, Any]:
        tool = self.status()["tool"]
        if tool is None:
            raise rules.DialogFailed(self.status().get("reason") or "No system dialog here.")
        if not self._lock.acquire(blocking=False):
            return {"busy": True}
        try:
            plan = rules.plan(tool, request, nearest_folder(request.start), self._python)
            try:
                done = self._run(
                    list(plan.argv),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self._time_limit,
                    stdin=subprocess.DEVNULL,
                    env={**os.environ, **plan.env},
                )
            except subprocess.TimeoutExpired:
                return {"cancelled": True, "timedOut": True}
            except OSError as error:
                raise rules.DialogFailed(f"The {tool} dialog could not start: {error.strerror}") from None
            return rules.read_answer(plan, done.returncode, done.stdout or "", done.stderr or "")
        finally:
            self._lock.release()
