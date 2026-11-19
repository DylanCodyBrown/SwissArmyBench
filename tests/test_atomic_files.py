"""adapters/atomic_files.py: a file written whole or not at all, its mode kept, two writers at once."""

from __future__ import annotations

import json
import os
import stat
import sys
import threading
import zipfile
from pathlib import Path

import pytest

from swissarmybench.adapters.atomic_files import JsonFile, as_bytes, replacing, write_atomic

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="file modes are POSIX's")


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_written_whole_and_nothing_left_beside_it(tmp_path: Path) -> None:
    target = tmp_path / "deeper" / "state.json"
    assert write_atomic(target, '{"a": 1}\n', newline="\n") is True
    assert target.read_bytes() == b'{"a": 1}\n'
    assert sorted(p.name for p in target.parent.iterdir()) == ["state.json"]


def test_if_changed_leaves_the_same_bytes_untouched(tmp_path: Path) -> None:
    target = tmp_path / "colours.toml"
    write_atomic(target, b"x = 1\n")
    before = target.stat().st_mtime_ns
    os.utime(target, ns=(before - 10**9, before - 10**9))
    assert write_atomic(target, b"x = 1\n", if_changed=True) is False
    assert target.stat().st_mtime_ns == before - 10**9
    assert write_atomic(target, b"x = 2\n", if_changed=True) is True
    assert target.read_bytes() == b"x = 2\n"


def test_line_ends_as_open_writes_them() -> None:
    assert as_bytes("a\nb", newline="\n") == b"a\nb"
    assert as_bytes("a\nb", newline="") == b"a\nb"
    assert as_bytes("a\nb", newline="\r\n") == b"a\r\nb"
    assert as_bytes("a\nb") == ("a" + os.linesep + "b").encode()
    assert as_bytes("é", encoding="utf-16-le") == "é".encode("utf-16-le")


@POSIX
def test_the_mode_given_wins_over_the_umask(tmp_path: Path) -> None:
    target = tmp_path / "server.json"
    write_atomic(target, "{}", mode=0o600)
    assert _mode(target) == 0o600
    target.chmod(0o644)
    write_atomic(target, "{}", mode=0o600)  # a file left readable is made owner-only again
    assert _mode(target) == 0o600


@POSIX
def test_an_existing_file_keeps_its_own_mode_and_a_new_one_gets_the_default(tmp_path: Path) -> None:
    kept = tmp_path / "notebook.ipynb"
    kept.write_text("old")
    kept.chmod(0o640)
    write_atomic(kept, "new")
    assert _mode(kept) == 0o640 and kept.read_text() == "new"
    fresh = tmp_path / "fresh.txt"
    write_atomic(fresh, "x")
    umask = os.umask(0)
    os.umask(umask)
    assert _mode(fresh) == 0o666 & ~umask


def test_a_failed_write_leaves_the_old_file_and_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "out.zip"
    target.write_bytes(b"old")
    with pytest.raises(RuntimeError), replacing(target) as partial:
        with zipfile.ZipFile(partial, "w") as archive:
            archive.writestr("a.txt", "a")
        raise RuntimeError("stopped")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["out.zip"]
    with replacing(target) as partial, zipfile.ZipFile(partial, "w") as archive:
        archive.writestr("a.txt", "a")
    assert zipfile.ZipFile(target).namelist() == ["a.txt"]


def test_two_writers_at_once_never_leave_a_broken_file(tmp_path: Path) -> None:
    """Many threads writing the same file, each a whole JSON document: every read between them parses,
    and the file at the end is one writer's whole document (a fixed .tmp name shared by two writers
    could leave one's half over the other's)."""
    target = tmp_path / "recent_projects.json"
    write_atomic(target, json.dumps({"by": -1, "rows": []}))
    failures: list[str] = []
    stop = threading.Event()

    def writer(number: int) -> None:
        body = json.dumps({"by": number, "rows": ["made-up " * 40] * (50 + number)})
        for _ in range(40):
            write_atomic(target, body)

    def reader() -> None:
        while not stop.is_set():
            try:
                json.loads(target.read_text(encoding="utf-8"))
            except PermissionError:  # Windows: the file is being replaced this instant
                continue
            except ValueError as error:
                failures.append(str(error))

    watching = threading.Thread(target=reader)
    watching.start()
    writers = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for thread in writers:
        thread.start()
    for thread in writers:
        thread.join()
    stop.set()
    watching.join()
    assert failures == []
    final = json.loads(target.read_text(encoding="utf-8"))
    assert final["by"] in range(8) and len(final["rows"]) == 50 + final["by"]
    assert [p.name for p in tmp_path.iterdir()] == ["recent_projects.json"]


def test_json_file(tmp_path: Path) -> None:
    assert JsonFile(None).read() is None
    JsonFile(None).write({"a": 1})  # no state folder: nothing written, nothing raised
    state = JsonFile(tmp_path / "follow.json")
    assert state.read() is None
    state.write({"on": True})
    assert state.read() == {"on": True}
    assert (tmp_path / "follow.json").read_text(encoding="utf-8") == '{\n "on": true\n}\n'
    (tmp_path / "follow.json").write_text("{not json")
    assert state.read() is None
