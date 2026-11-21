"""Kind colours (the owner, 2026-11-15: "App violet, notebook blue, script green"): the fixed colour of
each kind of Workbench document, shown as a thin edge or a small mark beside the kind's icon, never as a
background and never amber (amber means out of date). Each theme has its own (grid.css holds the same
values as tokens: `--kind-app`, `--kind-notebook`, `--kind-script`); they are not a setting (the owner's
simplicity pass, 2026-11-21). The connection colours keep clear of them and use the readability rule here
(`fitted`): 4.5 to 1 against the page and the panels, 7 to 1 in the high contrast themes. Pure rules, no I/O.
"""

from __future__ import annotations

from swissarmybench.domain.themes import readable

KINDS: tuple[str, ...] = ("app", "notebook", "script")
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


def fitted(colour: str, theme: str) -> str:
    """`colour` made readable in `theme`: far enough from each of its backgrounds."""
    out = colour
    for _ in range(3):  # each background in turn; a second pass settles the darkest and the lightest
        for background in BACKGROUNDS[theme]:
            out = readable(out, background, RATIO[theme])
    return out
