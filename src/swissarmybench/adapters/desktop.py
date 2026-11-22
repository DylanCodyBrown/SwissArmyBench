"""The desktop app's channel: how the server, `swissarmybench open` and a second start of the app tell the
running app to open a page (domain/desktop.py's messages). Standard library only.

The app listens on 127.0.0.1, on a port the system picks, and writes the port and a fresh key into
desktop.json beside the server's connection file, with its process id (the update's helper ends the app by
it). A message is one line of JSON carrying the key; the answer is one line of JSON. Nothing
but 127.0.0.1 is ever listened on; the key is made at each start and lives in that file only.
"""

from __future__ import annotations

import contextlib
import json
import secrets
import shutil
import socket
import socketserver
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from swissarmybench.adapters.atomic_files import JsonFile
from swissarmybench.domain import desktop as rules

Handler = Callable[[dict[str, Any]], dict[str, Any]]
ANSWER_SECONDS = 10.0


def new_key() -> str:
    return secrets.token_urlsafe(32)


class Listener:
    """The shell's side: each checked message handed to `handle` (on this listener's thread)."""

    def __init__(self, key: str, handle: Handler) -> None:
        self.key = key
        outer = self

        class One(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                self.request.settimeout(ANSWER_SECONDS)
                try:
                    line = self.rfile.readline(rules.MAX_MESSAGE + 1)
                    said = rules.read_message(line, outer.key)
                    answer = handle(said)
                except rules.ShellError as error:
                    answer = {"error": str(error)}
                except Exception as error:  # the shell keeps listening
                    answer = {"error": f"The shell could not: {error}"}
                with contextlib.suppress(OSError):
                    self.wfile.write((json.dumps(answer) + "\n").encode("utf-8"))

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False

        self._server = Server((rules.HOST, 0), One)
        self.port: int = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, name="sab-shell", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def ask(port: int, key: str, said: dict[str, Any], timeout: float = ANSWER_SECONDS) -> dict[str, Any]:
    """Send the shell one message; its answer. OSError when it does not answer."""
    with socket.create_connection((rules.HOST, port), timeout=timeout) as connection:
        connection.sendall(rules.message(key, said))
        data = b""
        while not data.endswith(b"\n") and len(data) <= rules.MAX_MESSAGE:
            chunk = connection.recv(65536)
            if not chunk:
                break
            data += chunk
    try:
        answer = json.loads(data.decode("utf-8") or "null")
    except (UnicodeDecodeError, ValueError):
        raise OSError("The shell's answer was not one.") from None
    if not isinstance(answer, dict):
        raise OSError("The shell did not answer.")
    return answer


class RecordFile(JsonFile):
    """desktop.json: the app's process id and channel (written atomically; owner-only where the system has
    modes)."""

    path: Path

    def __init__(self, path: Path) -> None:
        super().__init__(path, mode=0o600, indent=None, end="")

    def shell(self) -> tuple[int, int, str] | None:
        return rules.read_record(self.read())

    def remove(self, pid: int) -> None:
        """Gone at the shell's end, when it is still this shell's."""
        said = self.read()
        if isinstance(said, dict) and said.get("pid") == pid:
            with contextlib.suppress(OSError):
                self.path.unlink()


class JsonState(JsonFile):
    """A small state file (windows.json: the windows' places), written only when its text changes; a
    failed write is let go (the places are a nicety)."""

    path: Path

    def __init__(self, path: Path) -> None:
        super().__init__(path, if_changed=True)

    def write_text(self, text: str) -> None:
        with contextlib.suppress(OSError):
            super().write_text(text)


def fresh_cache(storage: Path, version: str) -> Path:
    """The profile's HTTP cache folder for `version` (domain/desktop.py cache_folder), before the profile is
    made: every other version's cache folder removed (as far as the system lets: a file another process still
    holds stays, and is never read again), and the version that runs written in the profile's version.txt.
    Nothing here asks Chromium to clear anything (White screen after an update, 2026-11-22)."""
    with contextlib.suppress(OSError):
        storage.mkdir(parents=True, exist_ok=True)
    try:
        names = [p.name for p in storage.iterdir() if p.is_dir()]
    except OSError:
        names = []
    for name in rules.stale_caches(names, version):
        shutil.rmtree(storage / name, ignore_errors=True)
    mark = storage / rules.VERSION_MARK
    with contextlib.suppress(OSError):
        if not mark.is_file() or mark.read_text(encoding="utf-8").strip() != version:
            mark.write_text(version, encoding="utf-8")
    return storage / rules.cache_folder(version)
