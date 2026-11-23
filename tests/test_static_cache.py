"""The page's files are checked before a saved copy is used again (the owner, 2026-11-19: after updating to
0.0.27 the desktop app still drew 0.0.26's {x} buttons from its cache)."""

from __future__ import annotations

from pathlib import Path

from swissarmybench import __version__
from swissarmybench.server.app import versioned_etag
from tests.conftest import make_client


def _web(tmp_path: Path) -> Path:
    web = tmp_path / "wwwroot"
    (web / "css").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><main></main>", encoding="utf-8")
    (web / "css" / "app.css").write_text("body { margin: 0; }", encoding="utf-8")
    return web


def test_a_page_file_is_checked_each_time_and_unchanged_is_a_304(tmp_path: Path) -> None:
    with make_client(tmp_path, blazor_root=_web(tmp_path)) as client:
        first = client.get("/blazor/css/app.css")
        assert first.status_code == 200
        assert first.headers["cache-control"] == "no-cache"
        assert "last-modified" not in first.headers  # only the ETag says whether a saved copy is good
        assert first.headers["etag"].endswith(f'-{__version__}"')
        again = client.get("/blazor/css/app.css", headers={"If-None-Match": first.headers["etag"]})
        assert again.status_code == 304
        # Another version's copy (the same time and size): the file.
        other = first.headers["etag"].replace(f"-{__version__}", "-0.0.1")
        assert client.get("/blazor/css/app.css", headers={"If-None-Match": other}).status_code == 200
        # A page's own address answers its index.html, checked the same way.
        page = client.get("/blazor/connections")
        assert page.status_code == 200 and page.headers["cache-control"] == "no-cache"


def test_versioned_etag() -> None:
    assert versioned_etag('"abc"', "0.0.33") == '"abc-0.0.33"'
    assert versioned_etag('W/"abc"', "0.0.33") == '"abc-0.0.33"'
    assert versioned_etag('"abc"', "0.0.33") != versioned_etag('"abc"', "0.0.32")
