"""Kind colours (the owner, 2026-11-15: "App violet, notebook blue, script green"): each kind's fixed
colour per theme (grid.css's tokens hold the same), readable in every theme, never amber."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from swissarmybench.domain import kind_colours as rules
from swissarmybench.domain.themes import contrast

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
