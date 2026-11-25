"""What's New (domain/whats_new.py, services/whats_new.py, /whats-new): WHATSNEW.md's shape, the version check
the release runs, when the window opens by itself and who closes it."""

from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest

from swissarmybench.adapters.updates import WhatsNewFiles
from swissarmybench.domain import whats_new as rules
from swissarmybench.services.whats_new import WhatsNew
from swissarmybench.services.workspace import Refused
from tests.conftest import AGENT, AUTH, make_client

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "src" / "swissarmybench" / rules.FILE

SAMPLE = """# What's new in Swiss Army Bench

## 0.0.3 · 2026-11-25 14:30 UTC

### New features
- Emoji picker

### Bug fixes
- Fixed: stray tabs

## 0.0.2 · 2026-11-20 09:05 UTC

### New features

### Bug fixes
- Fixed: a slow start

## 0.0.1 · 2026-11-10 08:00 UTC

### New features
- First release

### Bug fixes
"""


# ----- the file's shape -----


def test_the_shipped_file_is_in_its_shape() -> None:
    text = SHIPPED.read_text(encoding="utf-8")
    assert rules.problems(text) == []
    releases = rules.parse(text)
    assert releases, "WHATSNEW.md has releases"
    for release in releases:
        for bullet in release.features + release.fixes:
            assert len(bullet) <= rules.MAX_BULLET, bullet
            assert "(" not in bullet, f"no parentheticals: {bullet}"
        for bullet in release.fixes:
            assert bullet.startswith("Fixed: "), bullet


def test_the_running_version_has_its_entry() -> None:
    """The release's check: pyproject.toml's version has a heading in WHATSNEW.md (the unit suite runs in
    the release)."""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert rules.has(rules.parse(SHIPPED.read_text(encoding="utf-8")), version), (
        f"WHATSNEW.md needs a `## {version} · YYYY-MM-DD HH:MM UTC` heading"
    )


def test_the_file_ships_in_the_wheel() -> None:
    """Hatch ships everything in the package's folder: WHATSNEW.md sits there, as mcp/index.md does."""
    wheel = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]
    assert "src/swissarmybench" in wheel["targets"]["wheel"]["packages"]
    assert SHIPPED.is_file()
    assert not any(rules.FILE in str(e) for e in wheel.get("exclude", []))
    assert WhatsNewFiles(None).text() == SHIPPED.read_text(encoding="utf-8")


def test_a_file_is_read_into_releases() -> None:
    releases = rules.parse(SAMPLE)
    assert [r.version for r in releases] == ["0.0.3", "0.0.2", "0.0.1"]
    assert releases[0].to_json() == {
        "version": "0.0.3",
        "time": "2026-11-25 14:30 UTC",
        "features": ["Emoji picker"],
        "fixes": ["Fixed: stray tabs"],
    }
    assert releases[1].features == [] and releases[2].fixes == []
    assert "### New features\nNone." in releases[1].markdown()


@pytest.mark.parametrize(
    ("line", "said"),
    [
        ("## banana · 2026-11-25 14:30 UTC", "not a version"),
        ("## 0.0.4 · 2026-13-45 14:30 UTC", "not a time"),
        ("### Improvements", "a section is"),
        ("- " + "x" * (rules.MAX_BULLET + 1), "characters at most"),
        ("Some loose words", "only a release"),
    ],
)
def test_a_line_out_of_shape_is_said_with_its_line(line: str, said: str) -> None:
    text = SAMPLE.replace("- Emoji picker", line)
    with pytest.raises(rules.WhatsNewError, match=said):
        rules.parse(text)
    assert rules.problems(text)[0].startswith("Line ")


def test_sections_come_in_their_order_and_once() -> None:
    swapped = SAMPLE.replace(
        "### New features\n- Emoji picker\n\n### Bug fixes", "### Bug fixes\n\n### New features"
    )
    assert "Line" in rules.problems(swapped)[0]
    missing = SAMPLE.replace("### Bug fixes\n- Fixed: stray tabs\n", "")
    assert rules.problems(missing) == ["0.0.3: it has both New features and Bug fixes."]


def test_releases_go_newest_first_each_once() -> None:
    older_first = SAMPLE.replace("## 0.0.3", "## 0.0.0")
    assert "newest first" in rules.problems(older_first)[0]
    assert rules.problems("# What's new\n") == ["WHATSNEW.md has no release."]


def test_which_releases_are_newer() -> None:
    releases = rules.parse(SAMPLE)
    assert [r.version for r in rules.newer_than(releases, "0.0.1")] == ["0.0.3", "0.0.2"]
    assert [r.version for r in rules.newer_than(releases, "0.0.1", "0.0.2")] == ["0.0.2"]
    assert rules.newer_than(releases, None) == []
    assert rules.has(releases, "0.0.2") and not rules.has(releases, "0.0.9")


def test_it_opens_only_after_an_update() -> None:
    assert rules.should_open("0.0.3", "0.0.2")
    assert not rules.should_open("0.0.3", "0.0.3")
    assert not rules.should_open("0.0.3", None)  # a brand new install
    assert not rules.should_open("0.0.2", "0.0.3")


# ----- the service -----


class Files:
    def __init__(self, seen: str | None) -> None:
        self.saw = seen

    def text(self) -> str:
        return SAMPLE

    def seen(self) -> str | None:
        return self.saw

    def write_seen(self, version: str) -> None:
        self.saw = version


class Told:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


class Audit:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str]] = []

    def write(self, who: str, action: str, dataset: str | None, **details: Any) -> None:
        self.entries.append((who, action))


def made(files: Files, told: Told, audit: Audit) -> WhatsNew:
    """The fakes stand in for the Notifier and Audit ports (only the parts What's New calls)."""
    return WhatsNew("0.0.3", files, cast(Any, told), cast(Any, audit))


def test_a_brand_new_install_records_its_version_and_opens_nothing() -> None:
    files = Files(None)
    state = made(files, Told(), Audit()).state()
    assert state["open"] is False and state["releases"] == []
    assert files.saw == "0.0.3"


def test_after_an_update_every_newer_release_is_shown_newest_first() -> None:
    files = Files("0.0.1")
    news = made(files, Told(), Audit())
    state = news.state()
    assert state["open"] is True and state["seen"] == "0.0.1"
    assert [r["version"] for r in state["releases"]] == ["0.0.3", "0.0.2"]
    asyncio.run(news.seen())
    assert files.saw == "0.0.3"
    assert news.state()["open"] is False


def test_all_and_since_choose_the_releases_without_opening() -> None:
    news = made(Files("0.0.3"), Told(), Audit())
    assert [r["version"] for r in news.state(every=True)["releases"]] == ["0.0.3", "0.0.2", "0.0.1"]
    assert [r["version"] for r in news.state(since="0.0.2")["releases"]] == ["0.0.3"]
    assert news.state()["open"] is False


def test_the_agent_opens_it_and_only_the_user_closes_it() -> None:
    files, told, audit = Files("0.0.1"), Told(), Audit()
    news = made(files, told, audit)
    asyncio.run(news.show(who="agent"))
    assert told.messages == [{"type": "whats_new_open"}] and audit.entries == [("agent", "whats_new_open")]
    with pytest.raises(Refused):
        asyncio.run(news.seen(who="agent"))
    assert files.saw == "0.0.1"


def test_the_state_file_holds_the_version_only(tmp_path: Path) -> None:
    files = WhatsNewFiles(tmp_path / "whats_new.json")
    assert files.seen() is None
    files.write_seen("0.0.3")
    assert json.loads((tmp_path / "whats_new.json").read_text(encoding="utf-8")) == {"version": "0.0.3"}
    assert WhatsNewFiles(tmp_path / "whats_new.json").seen() == "0.0.3"


# ----- the routes -----


def test_the_routes_open_after_an_update_and_the_close_marks_it_seen(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "whats_new.json").write_text('{"version": "0.0.1"}', encoding="utf-8")
    with make_client(tmp_path) as client:
        state = client.get("/whats-new", headers=AUTH).json()
        assert state["open"] is True and state["seen"] == "0.0.1"
        assert state["releases"][0]["version"] == state["version"]
        assert {"features", "fixes", "time"} <= set(state["releases"][0])
        assert client.post("/whats-new/seen", json={}, headers=AGENT).status_code == 403
        assert client.post("/whats-new/seen", json={}, headers=AUTH).json()["open"] is False
        assert client.get("/whats-new", headers=AUTH).json() == state | {
            "seen": state["version"],
            "open": False,
            "releases": [],
        }
        every = client.get("/whats-new?all=1", headers=AUTH).json()["releases"]
        assert len(every) >= 4
        assert (
            client.get("/whats-new?since=0.0.37", headers=AGENT).json()["releases"][-1]["version"] == "0.0.38"
        )
        assert client.post("/whats-new/open", json={}, headers=AGENT).json() == {"shown": True}
    assert json.loads((tmp_path / "state" / "whats_new.json").read_text(encoding="utf-8")) == {
        "version": state["version"]
    }


def test_a_fresh_install_opens_nothing(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/whats-new", headers=AUTH).json()["open"] is False
    assert (tmp_path / "state" / "whats_new.json").is_file()
