"""The page's files are checked before a saved copy is used again (the owner, 2026-11-19: after updating to
0.0.27 the desktop app still drew 0.0.26's {x} buttons from its cache)."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from swissarmybench import __version__
from swissarmybench.server.app import FOREVER, cache_header, create_app, versioned_etag

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


# ===== White screen after an update, 2026-11-22: what each of the page's files may keep =====


def _web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    (web / "build" / "chunks").mkdir(parents=True)
    for name in ("index.html", "workbench.html"):
        (web / name).write_text("<!doctype html><main></main>", encoding="utf-8")
    (web / "build" / "main.js").write_text('import "./chunks/main-ABC123.js";', encoding="utf-8")
    (web / "build" / "chunks" / "main-ABC123.js").write_text("export const a = 1;", encoding="utf-8")
    return web


def test_the_pages_are_never_kept_the_entry_checked_and_the_hashed_chunks_kept_for_ever(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SWISSARMYBENCH_WEB_ROOT", str(_web(tmp_path)))
    with TestClient(create_app(token="t", port=PORT)) as client:
        for page in ("/workspace", "/g/1", "/notebooks", "/scripts"):
            answer = client.get(page, headers=HEADERS)
            assert answer.status_code == 200 and answer.headers["cache-control"] == "no-store", page
        entry = client.get("/static/build/main.js", headers=HEADERS)
        assert entry.status_code == 200 and entry.headers["cache-control"] == "no-cache"
        assert "last-modified" not in entry.headers  # only the ETag says whether a saved copy is good
        assert entry.headers["etag"].endswith(f'-{__version__}"')
        chunk = client.get("/static/build/chunks/main-ABC123.js", headers=HEADERS)
        assert chunk.status_code == 200 and "immutable" in chunk.headers["cache-control"]
        # This version's copy: a 304. Another version's copy (the same time and size): the file.
        same = client.get("/static/build/main.js", headers=HEADERS | {"If-None-Match": entry.headers["etag"]})
        assert same.status_code == 304
        other = entry.headers["etag"].replace(f"-{__version__}", "-0.0.1")
        assert (
            client.get("/static/build/main.js", headers=HEADERS | {"If-None-Match": other}).status_code == 200
        )


def test_cache_header_and_versioned_etag() -> None:
    assert cache_header("build/chunks/main-L65D35CS.js") == FOREVER
    assert cache_header("build\\chunks\\main-L65D35CS.js") == FOREVER
    for path in ("build/main.js", "build/workbench.js", "build/lazy/plotly.js", "index.html", "grid.css"):
        assert cache_header(path) == "no-cache", path
    assert versioned_etag('"abc"', "0.0.33") == '"abc-0.0.33"'
    assert versioned_etag('W/"abc"', "0.0.33") == '"abc-0.0.33"'
    assert versioned_etag('"abc"', "0.0.33") != versioned_etag('"abc"', "0.0.32")
