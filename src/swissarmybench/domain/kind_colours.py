"""Kind colours (the owner, 2026-11-15: "App violet, notebook blue, script green"): the colour of each
kind of Workbench document, shown as a thin edge or a small mark beside the kind's icon, never as a
background and never amber (amber means out of date).

Three kinds: an app's page (a Streamlit app's canvas), a notebook (data.ipynb too: its own icon tells it
apart), a script. Each theme has its own default (grid.css holds the same values as tokens:
`--kind-app`, `--kind-notebook`, `--kind-script`). The user may choose any colour for a kind in Settings;
it is then made readable for each theme (moved toward black or white just far enough, its hue kept):
4.5 to 1 against the page and the panels, 7 to 1 in the high contrast themes, since a cell's `@cell7`
is written in it. Pure rules, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from swissarmybench.domain.themes import HEX, contrast, readable

KINDS: tuple[str, ...] = ("app", "notebook", "script")
LABELS: dict[str, str] = {"app": "App pages", "notebook": "Notebooks", "script": "Scripts"}
THEMES: tuple[str, ...] = ("light", "dark", "hc-light", "hc-dark")

# Each theme's default for each kind (the same as grid.css's tokens; a test holds them together).
DEFAULTS: dict[str, dict[str, str]] = {
    "light": {"app": "#7b3fc4", "notebook": "#1f63b0", "script": "#2b7238"},
    "dark": {"app": "#b79cf2", "notebook": "#7db3ee", "script": "#6fc77d"},
    "hc-light": {"app": "#5a1a9e", "notebook": "#0a4a94", "script": "#0d5a1d"},
    "hc-dark": {"app": "#d4bfff", "notebook": "#a3cdff", "script": "#8ff09a"},
}
# What a kind's colour must stand apart from, in each theme: the page and the panels (grid.css's --bg,
# --surface and --surface-2), and how far.
BACKGROUNDS: dict[str, tuple[str, ...]] = {
    "light": ("#ffffff", "#eef1f4", "#e1e6eb"),
    "dark": ("#121518", "#191d22", "#21272d"),
    "hc-light": ("#ffffff", "#f2f2f2"),
    "hc-dark": ("#000000", "#121212"),
}
RATIO: dict[str, float] = {"light": 4.5, "dark": 4.5, "hc-light": 7.0, "hc-dark": 7.0}
# Amber is out of date's colour: a kind may not look like it (hues from 30 to 60 degrees, saturated).
_AMBER = (30.0, 60.0)


class KindColourError(ValueError):
    """A colour that cannot be a kind's (the message says why)."""


def _hue_saturation(colour: str) -> tuple[float, float]:
    r, g, b = (int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    high, low = max(r, g, b), min(r, g, b)
    if high == low:
        return 0.0, 0.0
    delta = high - low
    saturation = delta / high
    if high == r:
        hue = ((g - b) / delta) % 6
    elif high == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return hue * 60, saturation


def looks_amber(colour: str) -> bool:
    hue, saturation = _hue_saturation(colour)
    return _AMBER[0] <= hue <= _AMBER[1] and saturation >= 0.45


def check(sent: Any) -> dict[str, str | None]:
    """Colours as sent: {"app": "#7b3fc4", "script": null, ...}: a known kind each, a #rrggbb colour or
    null (the theme's own again)."""
    if not isinstance(sent, dict) or not sent:
        raise KindColourError('Send the colours: {"app": "#7b3fc4"} (null puts a kind\'s own back).')
    unknown = [key for key in sent if key not in KINDS]
    if unknown:
        raise KindColourError(f"No kind is called {unknown[0]!r}. The kinds: {', '.join(KINDS)}.")
    out: dict[str, str | None] = {}
    for kind, value in sent.items():
        if value is None:
            out[kind] = None
            continue
        if not isinstance(value, str) or not HEX.match(value):
            raise KindColourError(f"{LABELS[kind]}' colour is #rrggbb, like #7b3fc4.")
        if looks_amber(value):
            raise KindColourError(f"{value} reads as amber, which means out of date: choose another colour.")
        out[kind] = value.lower()
    return out


def read_saved(raw: Any) -> dict[str, str]:
    """The colours kept in the state folder (a file written by hand or by an older version: anything
    that is not a kind's good colour is left out)."""
    if not isinstance(raw, dict):
        return {}
    kept: dict[str, str] = {}
    for kind in KINDS:
        value = raw.get(kind)
        if isinstance(value, str) and HEX.match(value) and not looks_amber(value):
            kept[kind] = value.lower()
    return kept


def fitted(colour: str, theme: str) -> str:
    """`colour` made readable in `theme`: far enough from each of its backgrounds."""
    out = colour
    for _ in range(3):  # each background in turn; a second pass settles the darkest and the lightest
        for background in BACKGROUNDS[theme]:
            out = readable(out, background, RATIO[theme])
    return out


def tokens(chosen: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """Each theme's colour for each kind: the user's choice made readable there, else the default."""
    return {
        theme: {
            kind: fitted(chosen[kind], theme) if kind in chosen else DEFAULTS[theme][kind] for kind in KINDS
        }
        for theme in THEMES
    }


def listing(chosen: Mapping[str, str]) -> dict[str, Any]:
    """What Settings and the agent see: each kind with its chosen colour (null: the theme's own) and the
    colour each theme shows."""
    shown = tokens(chosen)
    return {
        "kinds": [
            {
                "kind": kind,
                "name": LABELS[kind],
                "chosen": chosen.get(kind),
                "themes": {theme: shown[theme][kind] for theme in THEMES},
            }
            for kind in KINDS
        ]
    }


def readable_everywhere(chosen: Mapping[str, str]) -> bool:
    """Every kind's colour stands far enough from every background of every theme (a test's check)."""
    shown = tokens(chosen)
    return all(
        contrast(shown[theme][kind], background) >= RATIO[theme] - 0.01
        for theme in THEMES
        for kind in KINDS
        for background in BACKGROUNDS[theme]
    )
