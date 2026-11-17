"""Shared for the browser tests: each test leaves no project open behind it.

A project is a folder now (the owner, 2026-11-17), and opening one from the Workbench makes it THE open
project of the module's shared server: a test that opened one closes it (its unsaved changes let go), so
the next test's windows do not open its documents too."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def no_project_left_open(request: pytest.FixtureRequest) -> Iterator[None]:
    yield
    if "server" not in request.fixturenames:
        return
    from tests.e2e.test_ui import call

    server: dict[str, Any] = request.getfixturevalue("server")
    try:
        if call(server, "GET", "/project")["project"]:
            call(server, "POST", "/project/close", {"discard": True})
    except Exception:  # noqa: S110 (a server that stopped: nothing is open)
        pass
