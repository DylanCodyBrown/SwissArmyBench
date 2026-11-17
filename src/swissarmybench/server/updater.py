"""The update's helper: a small process that installs the new version once the app has stopped.

The running app cannot replace its own files (on Windows a running program's files are locked), so
"Update to X" hands over to this helper and stops:

    the server: plan (domain/updates.py) -> this file and the plan copied to a temporary folder ->
                started with the base Python (outside the uv tool's environment, which uv replaces),
                detached and with no window -> the server stops
    the helper: wait for the server's and the tray's processes to end -> uv tool install --force ->
                the installed version checked -> the app started (it starts the tray, opens the page)
    on a failure: a note of why (update_failed.json, which the next server reads and shows), then the
                old version started again, reinstalled first when it no longer starts

`run` and `main` need nothing but the standard library and nothing from this package: the file runs as
a copy, after the package itself may have been replaced. `Helper` (the server's side) imports the
package's own modules where it runs, inside the server.
"""

from __future__ import annotations

import ctypes
import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

WAIT_FOR_EXIT_SECONDS: float = 60.0
WAIT_FOR_START_SECONDS: float = 90.0
INSTALL_ATTEMPTS: int = 3
INSTALL_TIMEOUT_SECONDS: float = 900.0
# Windows: no console window, its own process group (Ctrl+C in the terminal that started the app does
# not reach it), and out of the terminal's job when the job allows it.
CREATE_NEW_PROCESS_GROUP: int = 0x00000200
CREATE_NO_WINDOW: int = 0x08000000
CREATE_BREAKAWAY_FROM_JOB: int = 0x01000000
IN_USE = (
    "Files of the app are in use by another program (an agent's MCP server, a terminal running sab). "
    "Close it and try again."
)


# ===== the helper (standard library only) =====


class Ops(Protocol):
    """What the helper does to the computer; a test passes its own."""

    def alive(self, pid: int) -> bool: ...

    def run(self, command: list[str], environ: dict[str, str]) -> tuple[int, str]: ...

    def start(self, command: list[str], environ: dict[str, str]) -> None: ...

    def started(self, info_file: str, version: str | None) -> bool: ...

    def sleep(self, seconds: float) -> None: ...

    def note(self, path: str, note: dict[str, str]) -> None: ...

    def stop_in(self, folder: str) -> int: ...


def _tail(text: str, lines: int = 12) -> str:
    kept = [line for line in text.strip().splitlines() if line.strip()][-lines:]
    return "\n".join(kept)[-2000:]


def _why(output: str) -> str:
    if "os error 5" in output or "os error 32" in output or "Access is denied" in output:
        return IN_USE
    return _tail(output) or "uv could not install it."


def _gone(ops: Ops, pid: int) -> bool:
    return not ops.alive(pid)


def run(plan: dict[str, Any], ops: Ops, done: list[str] | None = None) -> str:
    """Carry out `plan` (UpdatePlan.to_json); "updated", "restored" (the old version runs again) or
    "failed". `done` collects each step's name, in order, for the tests."""
    steps = done if done is not None else []
    environ: dict[str, str] = dict(plan.get("environ") or {})
    version, current = str(plan["version"]), str(plan["current"])

    def waited(seconds: float, ready: Callable[[], bool]) -> bool:
        for _ in range(int(seconds / 0.25)):
            if ready():
                return True
            ops.sleep(0.25)
        return ready()

    steps.append("wait")
    for pid in plan.get("wait_pids", []):
        if not waited(WAIT_FOR_EXIT_SECONDS, functools.partial(_gone, ops, int(pid))):
            ops.note(plan["note_file"], {"version": version, "reason": "The app did not stop."})
            return "failed"
    if plan.get("stop_in"):
        # Windows: any other program still running from the tool's folder (an editor's MCP server)
        # holds its files; uv cannot replace them while it runs.
        steps.append("stop")
        ops.stop_in(str(plan["stop_in"]))

    reason = ""
    steps.append("install")
    for attempt in range(INSTALL_ATTEMPTS):
        code, output = ops.run(list(plan["install"]), environ)
        if code == 0:
            reason = ""
            break
        reason = _why(output)
        if attempt + 1 < INSTALL_ATTEMPTS:
            ops.sleep(2.0)  # Windows can hold a just-ended program's files for a moment
    if not reason:
        steps.append("check")
        code, output = ops.run(list(plan["installed_version"]), environ)
        installed = output.strip().splitlines()[-1].strip() if output.strip() else ""
        if code != 0 or installed != version:
            reason = f"{installed or 'Nothing'} was installed instead of {version}."
    if not reason:
        steps.append("start")
        ops.start(list(plan["start"]), environ)
        if waited(WAIT_FOR_START_SECONDS, lambda: ops.started(plan["info_file"], version)):
            return "updated"
        reason = f"{version} was installed but did not start."

    ops.note(plan["note_file"], {"version": version, "reason": reason})
    steps.append("start old")
    if not reason.endswith("did not start."):
        ops.start(list(plan["start"]), environ)
        if waited(WAIT_FOR_START_SECONDS, lambda: ops.started(plan["info_file"], None)):
            return "restored"
    steps.append("restore")
    code, _ = ops.run(list(plan["restore"]), environ)
    if code == 0:
        ops.start(list(plan["start"]), environ)
        if waited(WAIT_FOR_START_SECONDS, lambda: ops.started(plan["info_file"], current)):
            return "restored"
    return "failed"


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def detached(command: list[str], environ: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
    """Start `command` on its own: no window, no console of the terminal's, outliving its parent."""
    options: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": os.environ | (environ or {}),
        "close_fds": True,
    }
    if sys.platform == "win32":
        flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        try:
            # Our own arguments: the app's Python and its module, or uv.
            return subprocess.Popen(command, creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **options)  # noqa: S603
        except OSError:  # the job does not allow leaving it
            return subprocess.Popen(command, creationflags=flags, **options)  # noqa: S603
    return subprocess.Popen(command, start_new_session=True, **options)  # noqa: S603


class SystemOps:
    def alive(self, pid: int) -> bool:
        return _alive(pid)

    def run(self, command: list[str], environ: dict[str, str]) -> tuple[int, str]:
        flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            done = subprocess.run(  # noqa: S603 (uv, or the app's own Python, from the plan)
                command,
                capture_output=True,
                text=True,
                timeout=INSTALL_TIMEOUT_SECONDS,
                env=os.environ | environ,
                creationflags=flags,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return 1, str(error)
        return done.returncode, (done.stdout or "") + (done.stderr or "")

    def start(self, command: list[str], environ: dict[str, str]) -> None:
        detached(command, environ)

    def started(self, info_file: str, version: str | None) -> bool:
        try:
            info = json.loads(Path(info_file).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(info, dict) or not isinstance(info.get("pid"), int) or not _alive(info["pid"]):
            return False
        return version is None or info.get("version") == version

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def note(self, path: str, note: dict[str, str]) -> None:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json.dumps(note) + "\n", encoding="utf-8")
        except OSError:
            pass

    def stop_in(self, folder: str) -> int:
        """Stop every process whose program is inside `folder`, but this one; how many were stopped.
        Windows only (elsewhere a running program's files can be replaced): PowerShell's process list
        with each program's path (the standard library has none), the folder and this process's id
        passed as variables, never pasted into the command."""
        if sys.platform != "win32" or not folder:
            return 0
        script = (
            "$f = $env:SAB_STOP_IN.TrimEnd('\\') + '\\'; $me = [int]$env:SAB_SELF; $n = 0; "
            "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ProcessId -ne $me -and "
            "$_.ExecutablePath.StartsWith($f, [StringComparison]::OrdinalIgnoreCase) } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $n++ }; $n"
        )
        code, output = self.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            {"SAB_STOP_IN": folder, "SAB_SELF": str(os.getpid())},
        )
        last = output.strip().splitlines()[-1].strip() if output.strip() else ""
        if code != 0 or not last.isdigit():
            return 0
        if int(last):
            time.sleep(1.0)  # Windows lets go of a stopped program's files a moment later
        return int(last)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    plan_file = Path(args[0])
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    outcome = run(plan, SystemOps())
    shutil.rmtree(plan_file.parent, ignore_errors=True)  # this copy and its plan
    return 0 if outcome == "updated" else 1


# ===== the server's side: plan, copy, hand over =====


def find_uv(environ: dict[str, str] | None = None, home: Path | None = None) -> str | None:
    """uv: on PATH, else where its installer puts it (~/.local/bin, on Windows too), else cargo's."""
    found = shutil.which("uv", path=(environ or dict(os.environ)).get("PATH"))
    if found:
        return found
    home = home or Path.home()
    name = "uv.exe" if sys.platform == "win32" else "uv"
    for folder in (home / ".local" / "bin", home / ".cargo" / "bin"):
        if (folder / name).is_file():
            return str(folder / name)
    return None


def uv_tool_prefix(prefix: Path) -> bool:
    """True when this Python is a uv tool's environment (uv writes uv-receipt.toml into it)."""
    return (prefix / "uv-receipt.toml").is_file()


def _tray_pid(tray_file: Path) -> int:
    try:
        pid = json.loads(tray_file.read_text(encoding="utf-8")).get("pid")
    except (OSError, ValueError, AttributeError):
        return 0
    return pid if isinstance(pid, int) and _alive(pid) else 0


class Helper:
    """Starts the helper for an update (services/updates.py's UpdateHelper)."""

    def __init__(
        self,
        info_file: Path,
        note_file: Path,
        prefix: Path | None = None,
        spawn: Callable[[list[str]], object] = detached,
        uv: Callable[[], str | None] = find_uv,
        windows: bool = sys.platform == "win32",
        kept: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.info_file = info_file
        self.note_file = note_file
        self.prefix = prefix or Path(sys.prefix)
        self._spawn = spawn
        self._uv = uv
        self.windows = windows
        # The installed extensions' wheels at a version (services/extensions.py): an update keeps them.
        self.kept: Callable[[str], list[str]] = kept or (lambda version: [])

    def installable(self) -> bool:
        """A uv tool's install (the installer's), not a development checkout."""
        return uv_tool_prefix(self.prefix)

    def _ready(self) -> str:
        from swissarmybench.domain.updates import UpdateError

        if not uv_tool_prefix(self.prefix):
            raise UpdateError(
                "This copy was not installed with uv (its installer): update it the way it was installed."
            )
        uv = self._uv()
        if uv is None:
            raise UpdateError("uv was not found: run the installer again to update.")
        return uv

    def launch(self, version: str, source: str) -> None:
        from swissarmybench import __version__
        from swissarmybench.domain.updates import plan_update

        uv = self._ready()
        tray = _tray_pid(self.info_file.with_name("tray.json"))
        plan = plan_update(
            version=version,
            current=__version__,
            source=source,
            uv=uv,
            tool_python=sys.executable,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
            wait_pids=[os.getpid(), tray],
            info_file=str(self.info_file),
            note_file=str(self.note_file),
            # This very tool is the one replaced, wherever its folder is.
            environ={"UV_TOOL_DIR": str(self.prefix.parent)},
            # Windows: what else runs from its folder (an editor's MCP server) is stopped first.
            stop_in=str(self.prefix) if self.windows else "",
            wheels=tuple(self.kept(version)),
            restore_wheels=tuple(self.kept(__version__)),
        )
        self._hand_over(plan.to_json())

    def launch_change(self, wheels: list[str], before: list[str]) -> None:
        """Install or Remove an extension: this same version with `wheels` (`before` again on a failure)."""
        from swissarmybench import __version__
        from swissarmybench.domain.extensions import plan_change

        uv = self._ready()
        plan = plan_change(
            current=__version__,
            uv=uv,
            tool_python=sys.executable,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
            wheels=wheels,
            before=before,
            wait_pids=[os.getpid(), _tray_pid(self.info_file.with_name("tray.json"))],
            info_file=str(self.info_file),
            note_file=str(self.note_file),
            environ={"UV_TOOL_DIR": str(self.prefix.parent)},
            stop_in=str(self.prefix) if self.windows else "",
        )
        self._hand_over(plan.to_json())

    def _hand_over(self, plan: dict[str, Any]) -> None:
        """This file and `plan` copied to a temporary folder, run by the base Python, detached."""
        folder = Path(tempfile.mkdtemp(prefix="sab-update-"))
        script = folder / "sab_update.py"
        shutil.copyfile(Path(__file__), script)
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        # The base Python, outside the tool's environment, which uv is about to replace.
        python = getattr(sys, "_base_executable", None) or sys.executable
        self._spawn([python, "-I", str(script), str(folder / "plan.json")])


if __name__ == "__main__":
    sys.exit(main())
