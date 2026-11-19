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

    def stop_in(self, folder: str) -> int:
        self.did.append(f"stop {folder}")
        return 1

    fetch_fails = False

    def end(self, pid: int) -> None:
        self.did.append(f"end {pid}")
        self.ended = True

    ended = False
    quits = False  # the app quits when asked over its channel

    def quit(self, record: str) -> bool:
        self.did.append(f"quit {Path(record).name}")
        self.ended = self.ended or self.quits
        return self.quits

    def fetch(self, url: str, folder: str) -> str:
        if self.fetch_fails:
            raise OSError(f"{url.rsplit('/', 1)[-1]}: HTTP Error 404: Not Found")
        self.did.append("fetch")
        return f"{folder}/{url.rsplit('/', 1)[-1]}"


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
    record = {"pid": os.getpid(), "shell": {"port": 5000, "key": "k" * 43}}
    (tmp_path / "desktop.json").write_text(json.dumps(record))
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
        "--refresh-package",
        "swissarmybench",
        "--python",
        f"{sys.version_info.major}.{sys.version_info.minor}",
        "swissarmybench[server]==99.0.0",
    ]
    assert handed["wait_pids"] == [os.getpid()]  # the server
    assert handed["end_pids"] == [os.getpid()]  # the desktop app: ended by the helper
    assert handed["environ"] == {"UV_TOOL_DIR": str(prefix.parent)}
    assert handed["current"] == __version__
    assert handed["stop_in"] == ""  # not Windows: nothing else is stopped
    shutil.rmtree(Path(script).parent)
    # On Windows the plan names the tool's own folder: what else runs from it is stopped first.
    Helper(
        tmp_path / "server.json",
        tmp_path / "note.json",
        prefix=prefix,
        spawn=spawned.append,
        uv=lambda: "/bin/uv",
        windows=True,
    ).launch("99.0.0", "pypi")
    handed = json.loads(Path(spawned[-1][3]).read_text())
    assert handed["stop_in"] == str(prefix)
    assert handed["steps"] == ["wait", "stop", "install", "check", "start"]
    shutil.rmtree(Path(spawned[-1][2]).parent)


def test_on_windows_what_runs_from_the_tools_folder_is_stopped_before_the_install() -> None:
    """An editor's MCP server running from the same uv tool folder locks its files (the coordinator,
    2026-11-16): the helper stops it after the app's own processes are gone, before uv installs."""
    ops = FakeOps({"install": [(0, "")], "check": [(0, "0.0.2\n")]}, starts=["0.0.2"])
    steps: list[str] = []
    stopping = plan() | {"stop_in": r"C:\Users\me\AppData\Roaming\uv\tools\swissarmybench"}
    assert run(stopping, ops, steps) == "updated"
    assert steps == ["wait", "stop", "install", "check", "start"]
    assert ops.did[0] == r"stop C:\Users\me\AppData\Roaming\uv\tools\swissarmybench"
    # Elsewhere (no folder in the plan) nothing is stopped.
    ops = FakeOps({"install": [(0, "")], "check": [(0, "0.0.2\n")]}, starts=["0.0.2"])
    assert run(plan(), ops) == "updated" and not any(d.startswith("stop") for d in ops.did)
    # The real one does nothing off Windows.
    if sys.platform != "win32":
        assert updater.SystemOps().stop_in("/nowhere") == 0


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


def test_an_extension_wheel_is_downloaded_by_the_helper_and_given_to_uv_as_a_file() -> None:
    wheel = "https://github.com/o/r/releases/download/v0.0.2/sab_ledger-0.0.2-py3-none-any.whl"
    ran: list[list[str]] = []
    ops = FakeOps({"install": [(0, "")], "check": [(0, "0.0.2")]}, ["0.0.2"])
    real_run = ops.run

    def run(command: list[str], environ: dict[str, str]) -> tuple[int, str]:
        ran.append(command)
        return real_run(command, environ)

    ops.run = run  # type: ignore[method-assign]
    shaped = plan() | {"install": ["uv", "tool", "install", "--force", "x==0.0.2", "--with", wheel]}
    steps: list[str] = []
    assert updater.run(shaped, ops, steps) == "updated"
    assert steps[:3] == ["wait", "download", "install"]
    assert ran[0][-2] == "--with" and ran[0][-1].endswith("/sab_ledger-0.0.2-py3-none-any.whl")
    assert not ran[0][-1].startswith("https://")


def test_a_wheel_that_cannot_be_downloaded_is_said_and_the_old_version_starts_again() -> None:
    wheel = "https://github.com/o/r/releases/download/v0.0.2/sab_ledger-0.0.2-py3-none-any.whl"
    ops = FakeOps({"install": []}, ["0.0.1"])
    ops.fetch_fails = True
    shaped = plan() | {"install": ["uv", "tool", "install", "--force", "x==0.0.2", "--with", wheel]}
    assert updater.run(shaped, ops) == "restored"
    assert "install" not in ops.did
    assert ops.notes[0]["reason"].startswith("An extension could not be downloaded: sab_ledger-0.0.2")


def test_the_desktop_app_is_ended_and_the_install_goes_on() -> None:
    """The desktop app (desktop.json's pid) may still run when the server stops for an update: the helper
    ends it after a moment's grace, installs, and its start step starts the new version's app."""
    made = plan() | {"wait_pids": [100], "end_pids": [200]}

    class App(FakeOps):
        ended = False

        def alive(self, pid: int) -> bool:
            return pid == 200 and not self.ended  # the server is gone; the app stays until it is ended

    ops = App({"install": [(0, "")], "check": [(0, "0.0.2")]}, ["0.0.2"])
    assert updater.run(made, ops) == "updated"
    # Asked to quit first (over its channel); it did not, so it was ended.
    assert ops.did[:2] == ["quit desktop.json", "end 200"] and ops.notes == []


def test_the_desktop_app_is_asked_to_quit_before_any_kill() -> None:
    """The app quits cleanly when asked (each window's place kept, the server told): nothing is ended."""
    made = plan() | {"wait_pids": [100], "end_pids": [200]}

    class App(FakeOps):
        ended = False
        quits = True

        def alive(self, pid: int) -> bool:
            return pid == 200 and not self.ended

    ops = App({"install": [(0, "")], "check": [(0, "0.0.2")]}, ["0.0.2"])
    assert updater.run(made, ops) == "updated"
    assert ops.did[0] == "quit desktop.json" and not any(d.startswith("end") for d in ops.did)


def test_the_helpers_quit_speaks_the_apps_channel(tmp_path: Path) -> None:
    """SystemOps.quit (standard library only: it runs as a copy) sends what the app's channel reads."""
    from swissarmybench.adapters.desktop import Listener, new_key
    from swissarmybench.domain import desktop as shell_rules

    heard: list[dict[str, Any]] = []
    key = new_key()

    def handle(said: dict[str, Any]) -> dict[str, Any]:
        heard.append(said)
        return {"ok": True}

    listener = Listener(key, handle)
    try:
        record = tmp_path / "desktop.json"
        record.write_text(json.dumps(shell_rules.record(4321, listener.port, key)), encoding="utf-8")
        assert updater.SystemOps().quit(str(record)) is True
        assert heard == [{"quit": True}]
        assert updater.SystemOps().quit(str(tmp_path / "none.json")) is False
    finally:
        listener.close()


def test_an_app_that_cannot_be_ended_is_said() -> None:
    made = plan() | {"wait_pids": [100], "end_pids": [200]}

    class Stuck(FakeOps):
        def alive(self, pid: int) -> bool:
            return pid == 200

    ops = Stuck({"install": [(0, "")], "check": [(0, "0.0.2")]}, ["0.0.2"])
    assert updater.run(made, ops) == "failed"
    assert ops.notes[-1]["reason"] == "The app's window did not close." and "install" not in ops.did


def test_an_update_and_an_extension_change_keep_the_users_own_packages(tmp_path: Path) -> None:
    """The owner (2026-11-18): "everytime I add an extension or update, im having to reinstall all of the
    imports" (No module named 'azure'): what Install now added goes `--with` into the new environment."""
    prefix = tmp_path / "tools" / "swissarmybench"
    site = prefix / "lib" / "python3.12" / "site-packages"
    for name, requires in {
        "swissarmybench": ["duckdb>=1"],
        "duckdb": [],
        "azure_identity": ["azure-core>=1.31"],
        "azure_core": [],
    }.items():
        info = site / f"{name}-1.0.dist-info"
        info.mkdir(parents=True)
        lines = [
            f"Name: {name.replace('_', '-')}",
            "Version: 1.0",
            *(f"Requires-Dist: {r}" for r in requires),
        ]
        (info / "METADATA").write_text("Metadata-Version: 2.1\n" + "\n".join(lines) + "\n")
    (prefix / "uv-receipt.toml").write_text("[tool]\n")
    spawned: list[list[str]] = []
    helper = Helper(
        tmp_path / "server.json", tmp_path / "n.json", prefix=prefix, spawn=spawned.append, uv=lambda: "uv"
    )
    assert helper.own() == ["azure-identity"]
    helper.launch("99.0.0", "pypi")
    update = json.loads(Path(spawned[-1][-1]).read_text())
    assert update["install"][-2:] == ["--with", "azure-identity"]
    assert update["restore"][-2:] == ["--with", "azure-identity"]  # a failed update gets them back too
    helper.launch_change(["https://example.invalid/ledger.whl"], [])
    change = json.loads(Path(spawned[-1][-1]).read_text())
    assert change["install"][-4:] == [
        "--with",
        "https://example.invalid/ledger.whl",
        "--with",
        "azure-identity",
    ]
    assert change["restore"][-2:] == ["--with", "azure-identity"]
    for handed in spawned:
        shutil.rmtree(Path(handed[-1]).parent)
