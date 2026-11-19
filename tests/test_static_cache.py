"""The page's files are checked before a saved copy is used again (the owner, 2026-11-19: after updating to
0.0.27 the desktop app still drew 0.0.26's {x} buttons from its cache)."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from swissarmybench.server.app import create_app

PORT = 5999
HEADERS = {"Authorization": "Bearer t", "Host": f"127.0.0.1:{PORT}"}


def test_a_page_file_is_checked_each_time_and_unchanged_is_a_304(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    with TestClient(create_app(token="t", port=PORT)) as client:
        first = client.get("/static/grid.css", headers=HEADERS)
        assert first.status_code == 200
        assert first.headers["cache-control"] == "no-cache"
        again = client.get("/static/grid.css", headers=HEADERS | {"If-None-Match": first.headers["etag"]})
        assert again.status_code == 304
