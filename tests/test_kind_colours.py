"""Kind colours (the owner, 2026-11-15: "App violet, notebook blue, script green"): each kind's default
per theme (grid.css's tokens hold the same), a chosen colour made readable in every theme, never amber,
shared by every window and kept across restarts (a small file in the state folder). The agent reads and
sets them too."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from swissarmybench.domain import kind_colours as rules
from swissarmybench.domain.themes import contrast
from tests.conftest import AGENT, AUTH, make_client
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command

CSS = (Path(__file__).resolve().parents[1] / "web" / "static" / "grid.css").read_text(encoding="utf-8")


def _block(theme: str) -> str:
    found = re.search(re.escape(f'html[data-theme="{theme}"]') + r"\s*\{(.*?)\n\}", CSS, re.S)
    assert found, theme
    return found.group(1)


@pytest.mark.parametrize("theme", rules.THEMES)
def test_the_css_tokens_are_the_defaults_and_readable(theme: str) -> None:
    tokens = dict(re.findall(r"--kind-([a-z]+):\s*(#[0-9a-fA-F]{6})", _block(theme)))
    assert tokens == rules.DEFAULTS[theme]
    for colour in tokens.values():
        assert not rules.looks_amber(colour)
        for background in rules.BACKGROUNDS[theme]:
            assert contrast(colour, background) >= rules.RATIO[theme]


def test_violet_blue_green_and_never_amber() -> None:
    def hue(colour: str) -> float:
        return rules._hue_saturation(colour)[0]

    light = rules.DEFAULTS["light"]
    assert 255 <= hue(light["app"]) <= 290  # violet
    assert 200 <= hue(light["notebook"]) <= 225  # blue
    assert 100 <= hue(light["script"]) <= 150  # green
    assert rules.looks_amber("#d29922") and rules.looks_amber("#855800")
    assert not rules.looks_amber("#7b3fc4")


def test_a_chosen_colour_is_made_readable_in_every_theme() -> None:
    chosen = {"app": "#e8d8ff", "script": "#003300"}  # too light for light, too dark for dark
    shown = rules.tokens(chosen)
    assert rules.readable_everywhere(chosen)
    assert shown["light"]["app"] != "#e8d8ff" and shown["dark"]["script"] != "#003300"
    assert shown["light"]["notebook"] == rules.DEFAULTS["light"]["notebook"]
    listed = rules.listing(chosen)["kinds"]
    assert [k["kind"] for k in listed] == ["app", "notebook", "script"]
    assert listed[0]["chosen"] == "#e8d8ff" and listed[1]["chosen"] is None


def test_what_is_sent_is_checked() -> None:
    assert rules.check({"app": "#AABBCC", "script": None}) == {"app": "#aabbcc", "script": None}
    for bad, words in (
        ({}, "Send the colours"),
        ({"page": "#ffffff"}, "No kind is called 'page'"),
        ({"app": "violet"}, "#rrggbb"),
        ({"notebook": "#d29922"}, "amber"),
    ):
        with pytest.raises(rules.KindColourError, match=words):
            rules.check(bad)
    assert rules.read_saved({"app": "#123456", "notebook": "nope", "script": "#d29922"}) == {"app": "#123456"}


def test_shared_kept_across_restarts_and_put_back(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        first = client.get("/kind-colours", headers=AUTH).json()["kinds"]
        assert all(k["chosen"] is None for k in first)
        done = client.put("/kind-colours", json={"app": "#9933cc"}, headers=AUTH)
        assert done.status_code == 200, done.text
        assert client.put("/kind-colours", json={"app": "#d29922"}, headers=AUTH).status_code == 400
    # A new start of Swiss Army Bench keeps the choice (it is a preference, unlike the panels).
    with make_client(tmp_path) as client:
        kinds = {k["kind"]: k for k in client.get("/kind-colours", headers=AGENT).json()["kinds"]}
        assert kinds["app"]["chosen"] == "#9933cc"
        back = client.put("/kind-colours", json={"app": None}, headers=AUTH).json()["kinds"]
        assert back[0]["chosen"] is None and back[0]["themes"]["light"] == rules.DEFAULTS["light"]["app"]


def test_the_agent_reads_and_sets_them(live: Live) -> None:  # noqa: F811
    assert [k["kind"] for k in command("app_kind_colours")["kinds"]] == ["app", "notebook", "script"]
    done = command("app_kind_colours", set={"script": "#227744"})
    assert {k["kind"]: k["chosen"] for k in done["kinds"]}["script"] == "#227744"
    command("app_kind_colours", set={"script": None})
