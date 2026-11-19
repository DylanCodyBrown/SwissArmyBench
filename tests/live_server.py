"""A real server in a thread for the tests that talk to it over HTTP (the agent's commands, sab.read, ...).

Two things a plain `uvicorn.Server(Config(port=port))` got wrong:
- the port: a probe socket was bound to port 0, closed, and uvicorn bound the same number later, a race
  another process (a parallel test run) could win. Here uvicorn is handed the socket already bound.
- the stop: `should_exit` waits for every open connection (a kernel's socket, a page's websocket) with no
  limit, so `thread.join(10)` waited the whole ten seconds. Here the graceful part lasts a second, then
  the server is told to go at once."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import uvicorn


@contextmanager
def running(
    make_app: Callable[[int], Any], log_level: str = "warning", **config: Any
) -> Iterator[tuple[int, uvicorn.Server]]:
    """Serve the app `make_app(port)` builds on a free 127.0.0.1 port: yields the port and the server."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = int(listener.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(make_app(port), log_level=log_level, timeout_graceful_shutdown=1, **config)
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline and thread.is_alive():
        time.sleep(0.02)
    try:
        assert server.started, "the server did not start"
        yield port, server
    finally:
        stop(server, thread)
        listener.close()


def stop(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(3)
    if thread.is_alive():  # a connection still open past the graceful second: go now
        server.force_exit = True
        thread.join(5)
