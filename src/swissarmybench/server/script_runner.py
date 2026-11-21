"""Run as scheduled (services/script_runs.py): `python <script> <arguments>` as a fresh process, in the
script's folder, with no app. The client inside finds no server (SWISSARMYBENCH_INFO names a file that
is not there), so `sab.read`, `sab.blade` and the rest read connections as an exported script does
(client/standalone.py). Its output (both streams) is kept to its last part; a run that goes over its
time is stopped."""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
import time
from pathlib import Path

MAX_OUTPUT_BYTES: int = 256 * 1024
# What the app's own processes carry and a scheduled run must not: it is a run with no app.
_DROPPED = ("SWISSARMYBENCH_KERNEL", "SWISSARMYBENCH_TOKEN", "SWISSARMYBENCH_PORT")


class ScriptRunner:
    async def run(
        self, python: str, script: str, arguments: list[str], environ: dict[str, str], seconds: float
    ) -> tuple[int | None, float, str]:
        env = {k: v for k, v in environ.items() if k not in _DROPPED}
        nowhere = Path(tempfile.gettempdir()) / "swissarmybench-no-app" / "server.json"
        env |= {"SWISSARMYBENCH_INFO": str(nowhere), "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        started = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                python,
                script,
                *arguments,
                cwd=str(Path(script).parent),
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as error:
            return 127, time.monotonic() - started, f"The script could not start in {python}: {error}"
        kept = bytearray()

        async def read() -> None:
            if process.stdout is None:
                return
            while chunk := await process.stdout.read(65536):
                kept.extend(chunk)
                if len(kept) > MAX_OUTPUT_BYTES:
                    del kept[: len(kept) - MAX_OUTPUT_BYTES]

        reading = asyncio.create_task(read())
        code: int | None
        try:
            code = await asyncio.wait_for(process.wait(), seconds)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            code = None
        with contextlib.suppress(asyncio.TimeoutError, TimeoutError):
            await asyncio.wait_for(reading, 5)
        return code, time.monotonic() - started, kept.decode("utf-8", "replace")
