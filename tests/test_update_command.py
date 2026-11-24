"""`swissarmybench update` (the owner, 2026-11-24: "I want an update command"): the app's own update from a
terminal, through the running server's routes; nothing else asked."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from swissarmybench.server import __main__ as launcher

INFO = {"port": 1, "token": "made-up"}


def asked(monkeypatch: pytest.MonkeyPatch, answers: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []

    def post(info: dict[str, Any], route: str, body: dict[str, Any], timeout: float = 120.0) -> Any:
        calls.append((route, body))
        return answers[route]

    monkeypatch.setattr(launcher, "running_server", lambda path: INFO)
    monkeypatch.setattr(launcher, "post_json", post)
    return calls


def test_a_newer_release_is_installed_the_apps_own_way(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = asked(
        monkeypatch,
        {
            "/updates/check": {"available": True, "version": "9.9.9"},
            "/updates/install": {"updating": "9.9.9"},
        },
    )
    assert launcher.update(tmp_path / "server.json") == 0
    assert calls == [
        ("/updates/check", {"asked": True}),
        ("/updates/install", {"version": "9.9.9", "confirmed": True}),
    ]
    said = capsys.readouterr().out
    assert "to 9.9.9" in said and "connections, variables, library and projects stay" in said


def test_nothing_newer_installs_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = asked(monkeypatch, {"/updates/check": {"available": False}})
    assert launcher.update(tmp_path / "server.json") == 0
    assert [c[0] for c in calls] == ["/updates/check"]
    assert "is the newest" in capsys.readouterr().out


def test_an_unreachable_release_list_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    asked(monkeypatch, {"/updates/check": {"available": False, "error": "No release list could be reached."}})
    assert launcher.update(tmp_path / "server.json") == 1
    assert "No release list could be reached." in capsys.readouterr().out


def test_with_no_app_running_its_server_is_started_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started: list[list[str]] = []
    states = iter([None, None, INFO])
    monkeypatch.setattr(launcher, "running_server", lambda path: next(states))
    monkeypatch.setattr(launcher, "detached", lambda command: started.append(command))
    monkeypatch.setattr("swissarmybench.server.__main__.time.sleep", lambda s: None)
    monkeypatch.setattr(launcher, "post_json", lambda info, route, body, timeout=120.0: {"available": False})
    assert launcher.update(tmp_path / "server.json") == 0
    assert len(started) == 1 and "--no-window" in started[0]
