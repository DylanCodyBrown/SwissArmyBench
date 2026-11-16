"""The update's helper (server/updater.py): its steps in order, what it does on each failure, the server's
side (where it refuses, what it hands over), and a real upgrade: a wheel bumped to a new version, installed
by the helper into a temporary uv tool folder over the current one, and the new version started."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from swissarmybench import __version__
from swissarmybench.domain import updates as rules
from swissarmybench.domain.updates import UpdateError
from swissarmybench.server import updater
from swissarmybench.server.updater import IN_USE, Helper, run

ROOT = Path(__file__).resolve().parents[1]
UV = shutil.which("uv") or "uv"


class FakeOps:
    """The computer as the helper sees it: each command's answer, in turn, and what it was asked."""

    def __init__(self, answers: dict[str, list[tuple[int, str]]], starts: list[str | None]) -> None:
        self.answers = answers
        self.starts = starts  # the version each start brings up (None: nothing comes up)
        self.running: str | None = None
        self.did: list[str] = []
        self.notes: list[dict[str, str]] = []
        self.alive_for = 0  # how many looks before the old server is gone

    def alive(self, pid: int) -> bool:
        self.alive_for -= 1
        return self.alive_for >= 0

    def run(self, command: list[str], environ: dict[str, str]) -> tuple[int, str]:
        kind = "check" if "-c" in command else "restore" if command[-1].endswith("==0.0.1") else "install"
        self.did.append(kind)
        return self.answers[kind].pop(0)

    def start(self, command: list[str], environ: dict[str, str]) -> None:
        self.did.append("start")
        self.running = self.starts.pop(0)

    def started(self, info_file: str, version: str | None) -> bool:
        return self.running is not None and (version is None or self.running == version)

    def sleep(self, seconds: float) -> None:
        pass

    def note(self, path: str, note: dict[str, str]) -> None:
        self.notes.append(note)


def plan() -> dict[str, Any]:
    return rules.plan_update(
        version="0.0.2",
        current="0.0.1",
        source="pypi",
        uv="uv",
        tool_python="python",
        python_version="3.12",
        wait_pids=[100, 200],
        info_file="server.json",
        note_file="update_failed.json",
    ).to_json()


def test_it_waits_installs_checks_and_starts_in_order() -> None:
    ops = FakeOps({"install": [(0, "")], "check": [(0, "0.0.2\n")]}, starts=["0.0.2"])
    ops.alive_for = 3
    steps: list[str] = []
    assert run(plan(), ops, steps) == "updated"
    assert steps == ["wait", "install", "check", "start"]
    assert ops.did == ["install", "check", "start"] and ops.notes == []


def test_a_failed_install_is_tried_again_then_the_old_version_starts_and_a_note_says_why() -> None:
    failed = (2, "error: Failed to fetch https://pypi.org/simple/swissarmybench/\n  Caused by: dns error")
    ops = FakeOps({"install": [failed, failed, failed]}, starts=["0.0.1"])
    assert run(plan(), ops) == "restored"
    assert ops.did == ["install", "install", "install", "start"]
    assert ops.notes == [{"version": "0.0.2", "reason": failed[1]}]


def test_files_in_use_on_windows_say_what_to_close() -> None:
    locked = (2, "error: failed to remove directory `...\\swissarmybench`: Access is denied. (os error 5)")
    ops = FakeOps({"install": [locked, locked, (0, "")], "check": [(0, "0.0.2")]}, starts=["0.0.2"])
    assert run(plan(), ops) == "updated"  # a moment later, the files were free
    ops = FakeOps({"install": [locked] * 3}, starts=["0.0.1"])
    run(plan(), ops)
    assert ops.notes[0]["reason"] == IN_USE


def test_a_new_version_that_does_not_start_is_replaced_by_the_old_one() -> None:
    ops = FakeOps(
        {"install": [(0, "")], "check": [(0, "0.0.2")], "restore": [(0, "")]}, starts=[None, "0.0.1"]
    )
    assert run(plan(), ops) == "restored"
    assert ops.did == ["install", "check", "start", "restore", "start"]
    assert ops.notes[0]["reason"] == "0.0.2 was installed but did not start."


def test_the_wrong_version_installed_is_a_failure() -> None:
    ops = FakeOps({"install": [(0, "")], "check": [(0, "0.0.1")]}, starts=["0.0.1"])
    assert run(plan(), ops) == "restored"
    assert ops.notes[0]["reason"] == "0.0.1 was installed instead of 0.0.2."


def test_an_app_that_does_not_stop_is_left_alone() -> None:
    ops = FakeOps({}, starts=[])
    ops.alive_for = 10**9
    assert run(plan(), ops) == "failed" and ops.did == []  # nothing installed under a running app
    assert ops.notes == [{"version": "0.0.2", "reason": "The app did not stop."}]


def test_the_server_refuses_to_update_a_copy_uv_did_not_install(tmp_path: Path) -> None:
    helper = Helper(tmp_path / "server.json", tmp_path / "note.json", prefix=tmp_path, spawn=lambda c: None)
    with pytest.raises(UpdateError, match="not installed with uv"):
        helper.launch("99.0.0", "pypi")
    (tmp_path / "uv-receipt.toml").write_text("[tool]\n")
    with pytest.raises(UpdateError, match="uv was not found"):
        Helper(tmp_path / "server.json", tmp_path / "n", prefix=tmp_path, uv=lambda: None).launch(
            "99.0.0", "pypi"
        )


def test_the_server_hands_a_copy_of_the_helper_and_its_plan_to_the_base_python(tmp_path: Path) -> None:
    prefix = tmp_path / "tools" / "swissarmybench"
    prefix.mkdir(parents=True)
    (prefix / "uv-receipt.toml").write_text("[tool]\n")
    (tmp_path / "tray.json").write_text(json.dumps({"pid": os.getpid()}))
    spawned: list[list[str]] = []
    helper = Helper(
        tmp_path / "server.json",
        tmp_path / "note.json",
        prefix=prefix,
        spawn=spawned.append,
        uv=lambda: "/bin/uv",
    )
    helper.launch("99.0.0", "pypi")
    [command] = spawned
    _python, isolated, script, plan_file = command
    assert isolated == "-I" and Path(script).name == "sab_update.py"
    assert Path(script).read_text() == Path(updater.__file__).read_text()
    handed = json.loads(Path(plan_file).read_text())
    assert handed["install"] == [
        "/bin/uv",
        "tool",
        "install",
        "--force",
        "--python",
        f"{sys.version_info.major}.{sys.version_info.minor}",
        "swissarmybench[server]==99.0.0",
    ]
    assert handed["wait_pids"] == [os.getpid(), os.getpid()]  # the server, then the tray
    assert handed["environ"] == {"UV_TOOL_DIR": str(prefix.parent)}
    assert handed["current"] == __version__
    shutil.rmtree(Path(script).parent)


def test_the_helper_needs_nothing_from_the_package() -> None:
    """It runs as a copy, after the package itself may have been replaced."""
    source = Path(updater.__file__).read_text()
    top = source.split("# ===== the server's side")[0]
    assert "swissarmybench" not in "".join(
        line for line in top.splitlines() if line.startswith(("import", "from"))
    )


# ===== a real upgrade, into a temporary uv tool folder =====


def _wheel(version: str, out: Path) -> Path:
    """This repository's wheel, its version set to `version` (pyproject and __version__)."""
    tree = out / f"src-{version}"
    shutil.copytree(ROOT / "src", tree / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (tree / "web").mkdir()
    shutil.copytree(ROOT / "web" / "static", tree / "web" / "static", ignore=shutil.ignore_patterns("build"))
    for name in ("README.md", "LICENSE-MIT", "LICENSE-APACHE"):
        shutil.copy(ROOT / name, tree / name)
    text = (
        (ROOT / "pyproject.toml")
        .read_text()
        .replace(f'version = "{__version__}"', f'version = "{version}"', 1)
    )
    (tree / "pyproject.toml").write_text(text)
    init = tree / "src" / "swissarmybench" / "__init__.py"
    init.write_text(
        init.read_text().replace(f'__version__: str = "{__version__}"', f'__version__: str = "{version}"')
    )
    wheels = out / "wheels"
    subprocess.run(  # noqa: S603 (uv, building our own wheel)
        [UV, "build", "--wheel", "--out-dir", str(wheels), str(tree)],
        check=True,
        capture_output=True,
        timeout=600,
    )
    [wheel] = wheels.glob(f"swissarmybench-{version}-*.whl")
    return wheel


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_the_helper_upgrades_a_uv_tool_and_the_new_version_starts(tmp_path: Path) -> None:
    newer = f"{__version__}.post42"  # never on PyPI: only the local wheel has it
    wheels = tmp_path / "out"
    old_wheel, _ = _wheel(__version__, wheels), _wheel(newer, wheels)
    tools, bins = tmp_path / "tools", tmp_path / "bin"
    environ = {"UV_TOOL_DIR": str(tools), "UV_TOOL_BIN_DIR": str(bins)}
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    subprocess.run(  # noqa: S603
        [UV, "tool", "install", "--force", "--python", python, f"{old_wheel}[server]"],
        check=True,
        capture_output=True,
        timeout=900,
        env=os.environ | environ,
    )
    tool_python = (
        tools / "swissarmybench" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    )
    assert (tools / "swissarmybench" / "uv-receipt.toml").is_file()  # what the server checks before updating
    state = tmp_path / "state"
    plan = rules.plan_update(
        version=newer,
        current=__version__,
        source="pypi",
        uv=shutil.which("uv") or "uv",
        tool_python=str(tool_python),
        python_version=python,
        wait_pids=[],
        info_file=str(state / "server.json"),
        note_file=str(state / "update_failed.json"),
        find_links=str(wheels / "wheels"),
        environ=environ
        | {
            "SWISSARMYBENCH_INFO": str(state / "server.json"),
            "SWISSARMYBENCH_STATE": str(state),
            "SWISSARMYBENCH_TRAY": "0",
            "SWISSARMYBENCH_UPDATE_FEED": "none",
            "SWISSARMYBENCH_OPEN": "0",
            "BROWSER": "true",  # webbrowser opens nothing
        },
    ).to_json()
    steps: list[str] = []
    notes: list[dict[str, str]] = []

    class Recorded(updater.SystemOps):
        def note(self, path: str, note: dict[str, str]) -> None:
            notes.append(note)

    try:
        outcome = run(plan, Recorded(), steps)
        assert outcome == "updated", notes
        assert steps == ["wait", "install", "check", "start"]
        info = json.loads((state / "server.json").read_text())
        assert info["version"] == newer and info["executable"].startswith(str(tools))
    finally:
        info_file = state / "server.json"
        if info_file.exists():
            pid = json.loads(info_file.read_text()).get("pid")
            if isinstance(pid, int):
                try:
                    os.kill(pid, 15)
                except OSError:
                    pass
                for _ in range(100):
                    if not updater._alive(pid):
                        break
                    time.sleep(0.1)
