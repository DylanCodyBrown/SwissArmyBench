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
import os
import secrets
import socket
import socketserver
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


class RecordFile:
    """desktop.json: the app's process id and channel (written atomically; owner-only where the system has
    modes)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> Any:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def shell(self) -> tuple[int, int, str] | None:
        return rules.read_record(self.read())

    def write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(json.dumps(data))
        os.replace(temporary, self.path)

    def remove(self, pid: int) -> None:
        """Gone at the shell's end, when it is still this shell's."""
        said = self.read()
        if isinstance(said, dict) and said.get("pid") == pid:
            with contextlib.suppress(OSError):
                self.path.unlink()


class JsonState:
    """A small state file (windows.json: the windows' places), written only when its text changes."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> Any:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write_text(self, text: str) -> None:
        try:
            if self.path.is_file() and self.path.read_text(encoding="utf-8") == text:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.tmp")
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            pass
