"""Live Streamlit runs: a widget run alone (the Widgets window's Run) and a canvas's Play, each a process of
its own started by server/streamlit_apps.py's Runner in a temporary folder of the app's, passed through the
Streamlit proxy at /streamlit/run/<key>-<secret>/; and the same pages run headless with AppTest (`check`).

A run follows live data (the owner, 2026-11-22: "yea live changes"): the tables it names are remembered, and
when one changes (services/live_tables.py hears it) `follow` writes that table's data/<stem>.parquet again,
only when its bytes changed, and then sab_live.py's stamp: a module the runtime imports, so Streamlit's own
file watcher (poll, runOnSave) runs every open page again by itself. The runtime reads a table's Parquet again
only when its file changed (its time and size).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench_streamlit.domain.canvas_build import table_stem
from swissarmybench_streamlit.domain.widget_properties import connection_of

RUN_PATH = "/streamlit/run/"
CHECK_SECONDS = 90.0
FOLLOWED_FILES = ("data.py",)  # a run's files that follow the project's own (data.ipynb's export)
LIVE_FILE = "sab_live.py"  # the stamp the runtime imports: rewritten, the open pages run again


def live_text(version: int) -> str:
    """sab_live.py: the stamp of the tables a run reads (never a value, a name or a row)."""
    return (
        '"""Swiss Army Bench rewrites this stamp when a table this app reads changes: '
        'its pages run again."""\n'
        f"VERSION = {int(version)}\n"
    )


# The headless check (AppTest), run in the app's own Python in its run folder: each page's exceptions, errors
# (a widget's own error panel), warnings and how many of a few kinds of element it drew.
CHECK_RUNNER = r"""
import json, os, re, sys
folder = sys.argv[1]
sys.path.insert(0, folder)
os.chdir(folder)
from streamlit.testing.v1 import AppTest
plan = json.load(open(os.path.join(folder, "check.json"), encoding="utf-8"))
out = []
for page in plan["pages"]:
    at = AppTest.from_file(os.path.join(folder, page), default_timeout=plan.get("timeout", 60))
    at.run()
    kinds = {}
    for kind in ("metric", "dataframe", "button", "markdown", "selectbox", "text_input", "slider"):
        try:
            kinds[kind] = len(at.get(kind))
        except Exception:
            pass
    errors = [str(e.value)[:1000] for e in at.error]
    out.append({
        "page": page,
        "exceptions": [str(e.value)[:1000] for e in at.exception],
        "errors": errors,
        # a widget's own error panel (sab_canvas.render): "<widget> (<instance>) failed: ..."
        "failed": [e for e in errors if re.match(r"^[a-z][a-z0-9_]* \([a-z][0-9]+\) failed: ", e)],
        "warnings": [str(w.value)[:500] for w in at.warning],
        "kinds": kinds,
    })
print("SAB-CHECK " + json.dumps(out))
"""


@dataclass
class Live:
    """One live run: its folder, its process, its own secret (in its address)."""

    key: str
    # Hex: never a "-", so <key>-<secret> splits at its last "-" (token_urlsafe's "-" sent a run to 404
    # at random).
    secret: str = field(default_factory=lambda: secrets.token_hex(12))
    folder: str | None = None
    process: Any = None
    python: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # What it follows: the table names its pages read, the followed files it was given (data.py), the stamp.
    names: frozenset[str] = frozenset()
    followed: frozenset[str] = frozenset()
    version: int = 0

    @property
    def base(self) -> str:
        return f"{RUN_PATH}{self.key}-{self.secret}"

    def running(self) -> bool:
        return self.process is not None and self.process.alive()


class LiveRuns:
    """Streamlit processes for a widget run alone and a canvas's Play: written, started, refreshed,
    stopped."""

    def __init__(self, files: Any, runner: Any) -> None:
        self._files = files  # adapters/streamlit_files.py AppFiles
        self._runner = runner  # server/streamlit_apps.py Runner
        self._runs: dict[str, Live] = {}
        # Told a run's key when the run ends or its app is written again (a launch again): a share of a
        # launched app ends with it (services/sharing_target.py).
        self.ended: list[Callable[[str], Awaitable[None]]] = []

    def port_of(self, key: str) -> int | None:
        run_id, _, secret = key.rpartition("-")
        live = self._runs.get(run_id)
        if live is None or not secret or not secrets.compare_digest(secret.encode(), live.secret.encode()):
            return None
        return live.process.port if live.running() else None

    def default_python(self) -> str:
        return str(os.environ.get("SWISSARMYBENCH_STREAMLIT_PYTHON") or self._runner.default_python())

    async def missing(self, python: str) -> dict[str, Any] | None:
        """What the Python lacks to run a Streamlit page (None: nothing)."""
        from swissarmybench.domain.packages import missing_packages

        try:
            found = await self._runner.check(python)
        except ValueError as error:
            return {"kind": "failed", "message": str(error)}
        if found["missing"]:  # set up for Streamlit: the Excel widgets' packages come along
            return {"kind": "missing"} | missing_packages(
                "Streamlit widgets", [*found["missing"], *found.get("extras", [])], python, own=False
            )
        return None

    async def run(
        self,
        key: str,
        files: Mapping[str, str],
        tables: Mapping[str, bytes],
        python: str,
        page: str = "",
        names: Iterable[str] = (),
    ) -> dict[str, Any]:
        """The files written (only what changed: Streamlit runs its open pages again) and the process
        started when it is not running. Its address, or the problem. `names`: the tables its pages read,
        followed while it runs (`follow`)."""
        live = self._runs.setdefault(key, Live(key))
        async with live.lock:
            live.names = frozenset(names)
            live.followed = frozenset(FOLLOWED_FILES) & frozenset(files)
            if live.process is not None and (not live.process.alive() or live.python != python):
                await live.process.stop()
                live.process = None
            if live.process is None:
                problem = await self.missing(python)
                if problem:
                    return {"ok": False, "problem": problem}
            if live.folder is None:
                live.folder = self._files.folder()
            self._write(live.folder, files, tables)
            stamp = Path(live.folder) / LIVE_FILE
            write_atomic(stamp, live_text(live.version), if_changed=True, newline="\n")
            if live.process is None:
                try:
                    live.process = await self._runner.start(python, live.folder, live.base)
                except ValueError as error:
                    return {"ok": False, "problem": {"kind": "failed", "message": str(error)}}
                live.python = python
            else:
                for told in self.ended:  # the app written again: a share of the run before ends
                    await told(key)
                self._files.touch(live.folder, "app.py")
        return {"ok": True, "url": f"{live.base}/{page}" if page else f"{live.base}/", "base": live.base}

    async def follow(
        self,
        wanted: Callable[[str], bool],
        read: Callable[[set[str]], Awaitable[Mapping[str, bytes]]] | None,
        files: Mapping[str, str | None] | None = None,
    ) -> list[str]:
        """The running runs that read a changed table brought up to date: the tables `wanted` picks among
        each run's names read once (`read`: their Parquet by stem), each run's file written only when its
        bytes changed (an open table no longer open: its file taken away, so the page says so), a followed
        file (data.py) the same; then its stamp, so its open pages run again. The runs' keys that changed."""
        lives = [live for live in self._runs.values() if live.running() and live.folder]
        names = {n for live in lives for n in live.names if wanted(n)}
        found: Mapping[str, bytes] = {}
        if names and read is not None:
            found = await read(names)
        changed: list[str] = []
        for live in lives:
            async with live.lock:
                if not live.running() or not live.folder:
                    continue
                moved = False
                for name in sorted(n for n in live.names if n in names):
                    stem = table_stem(name)
                    if stem in found:
                        moved |= self._files.write_table(live.folder, stem, found[stem]) is not False
                    elif connection_of(name) is None:  # an open table closed: no copy of it stays
                        moved |= self._files.drop_table(live.folder, stem)
                for name, text in (files or {}).items():
                    if name in live.followed and text is not None:
                        moved |= write_atomic(Path(live.folder) / name, text, if_changed=True, newline="\n")
                if moved:
                    live.version += 1
                    write_atomic(Path(live.folder) / LIVE_FILE, live_text(live.version), newline="\n")
                    changed.append(live.key)
        return changed

    def _write(self, folder: str, files: Mapping[str, str], tables: Mapping[str, bytes]) -> None:
        root = Path(folder)
        for name, text in files.items():
            write_atomic(root / name, text, if_changed=True, newline="\n")
        for name, data in tables.items():
            self._files.write_table(folder, name, data)

    async def check(
        self, key: str, files: Mapping[str, str], tables: Mapping[str, bytes], python: str, pages: list[str]
    ) -> dict[str, Any]:
        """The pages run headless with AppTest in a folder of their own: each page's errors."""
        problem = await self.missing(python)
        if problem:
            return {"ok": False, "problem": problem}
        folder = self._files.folder()
        try:
            self._write(folder, files, tables)
            (Path(folder) / "check.json").write_text(json.dumps({"pages": pages}), encoding="utf-8")
            process = await asyncio.create_subprocess_exec(
                python,
                "-I",
                "-c",
                CHECK_RUNNER,
                folder,
                cwd=folder,
                env=dict(os.environ) | {"STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"},
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                out, err = await asyncio.wait_for(process.communicate(), CHECK_SECONDS)
            except TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "ok": False,
                    "problem": {"kind": "failed", "message": "The check took too long and was stopped."},
                }
        finally:
            self._files.remove(folder)
        said = out.decode("utf-8", "replace")
        line = next((x for x in reversed(said.splitlines()) if x.startswith("SAB-CHECK ")), None)
        if line is None:
            tail = (err.decode("utf-8", "replace") or said)[-1500:]
            return {
                "ok": False,
                "problem": {"kind": "failed", "message": f"The check did not finish: {tail}"},
            }
        pages_found = json.loads(line[len("SAB-CHECK ") :])
        ok = not any(p["exceptions"] or p["failed"] for p in pages_found)
        return {"ok": ok, "pages": pages_found}

    async def stop(self, key: str) -> bool:
        live = self._runs.pop(key, None)
        if live is None:
            return False
        for told in self.ended:  # a share ends first: its process runs from this run's folder
            with contextlib.suppress(Exception):
                await told(key)
        if live.process is not None:
            await live.process.stop()
        if live.folder:
            self._files.remove(live.folder)
        return True

    async def stop_all(self) -> None:
        for key in list(self._runs):
            with contextlib.suppress(Exception):
                await self.stop(key)

    def running(self, key: str) -> bool:
        live = self._runs.get(key)
        return bool(live and live.running())

    def launched(self, key: str) -> tuple[str, str] | None:
        """A running run's folder and Python (None: not running): a shared run starts from them."""
        live = self._runs.get(key)
        return (live.folder, live.python) if live and live.running() and live.folder else None

    def seen_columns(self, key: str) -> dict[str, list[str]]:
        """Each Out[Table]'s columns as the run last had them (sab_canvas writes .sab_columns.json beside the
        app: names only, never rows); {} before it ran."""
        live = self._runs.get(key)
        if live is None or not live.folder:
            return {}
        try:
            found = json.loads((Path(live.folder) / ".sab_columns.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(found, dict):
            return {}
        return {str(k): [str(c) for c in v][:500] for k, v in found.items() if isinstance(v, list)}

    def folder_of(self, key: str) -> str | None:
        live = self._runs.get(key)
        return live.folder if live else None
