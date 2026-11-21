"""Microsoft's devtunnel command line run (services/sharing.py's Program); its file is adapters/tunnels.py's.

install   the download checked (adapters/tunnels.py), then on Windows the Authenticode signature
          (PowerShell's Get-AuthenticodeSignature: Valid, signed by Microsoft Corporation) and on macOS the
          code signature (codesign: valid, Microsoft's Team ID); Linux has no published signature
run       one command line at a time as a child process (no shell; stdin closed), its words and exit code
start     a command that keeps running (`host`, `user login`): its lines as they come, stopped on request
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from swissarmybench.domain import sharing as rules
from swissarmybench.domain.sharing import SharingError


def _windows_signed(path: Path) -> bool:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if shell is None:
        return False
    done = subprocess.run(  # noqa: S603 (a fixed script; the path in an environment variable, not its text)
        [shell, "-NoProfile", "-NonInteractive", "-Command", rules.SIGNATURE_SCRIPT],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=dict(os.environ) | {"SAB_DEVTUNNEL": str(path)},
    )
    return rules.windows_signed(done.stdout)


def _macos_signed(path: Path) -> bool:
    codesign = shutil.which("codesign") or "/usr/bin/codesign"  # Apple's own
    verify = subprocess.run(  # noqa: S603 (the file's path as one argument)
        [codesign, "--verify", "--strict", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    details = subprocess.run(  # noqa: S603
        [codesign, "-dv", "--verbose=2", str(path)], capture_output=True, text=True, timeout=60, check=False
    )
    return rules.macos_signed(verify.returncode, details.stdout + details.stderr)


def verify(system: str, path: Path) -> bool:
    """The system's signature on a downloaded devtunnel (Linux: none is published; the checksum only)."""
    if system == "windows":
        return _windows_signed(path)
    if system == "macos":
        return _macos_signed(path)
    return True


class Running:
    """A command that keeps running: its lines as they come (the last 200 kept)."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        self.lines: list[str] = []

    def alive(self) -> bool:
        return self._process.returncode is None

    @property
    def code(self) -> int | None:
        return self._process.returncode

    async def line(self, timeout: float) -> str | None:
        """The next line (None: it ended); TimeoutError when none came in time."""
        stream = self._process.stdout
        if stream is None:
            return None
        raw = await asyncio.wait_for(stream.readline(), timeout)
        if not raw:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._process.wait(), 5)
            return None
        text = raw.decode("utf-8", "replace").rstrip()
        self.lines.append(text)
        del self.lines[:-200]
        return text

    async def stop(self) -> None:
        if self._process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), 5)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self._process.kill()
                await self._process.wait()


class Files(Protocol):
    """devtunnel's file (adapters/tunnels.py TunnelFiles, given by the composition root)."""

    def installed(self) -> bool: ...

    def checks(self) -> str: ...

    def command(self, args: list[str]) -> list[str]: ...

    def install(self, verify: Callable[[str, Path], bool]) -> None: ...


class DevTunnelProgram:
    def __init__(self, files: Files) -> None:
        self.files = files

    def installed(self) -> bool:
        return self.files.installed()

    def checks(self) -> str:
        return self.files.checks()

    async def install(self) -> None:
        await asyncio.to_thread(self.files.install, verify)

    async def run(self, args: list[str], timeout: float = 60.0) -> tuple[int, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                *self.files.command(args),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as error:
            raise SharingError(f"devtunnel did not start: {error}") from None
        try:
            out, _ = await asyncio.wait_for(process.communicate(), timeout)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            raise SharingError("devtunnel did not answer in time.") from None
        return int(process.returncode or 0), out.decode("utf-8", "replace")

    async def start(self, args: list[str]) -> Running:
        try:
            process = await asyncio.create_subprocess_exec(
                *self.files.command(args),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as error:
            raise SharingError(f"devtunnel did not start: {error}") from None
        return Running(process)
