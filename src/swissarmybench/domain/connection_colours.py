"""Connection colours (the owner, 2026-11-16: "can we add a feature where we can choose connection colors
that everything associated with that connection is painted that color, cells, grids, app cells that are
associated with that connection etc.? reserve the rail colors for the rail").

  [PALETTE]   eight colours a new connection is given in turn (the first one no connection wears yet;
              when every one is worn, the one worn least). None of them is a rail's colour.
  [RESERVED]  the rail's colours are the rail's: the kind colours (app violet, notebook blue, script
              green: domain/kind_colours.py), the accent (the rail's current
              bar, the brand) and amber (out of date). A colour whose hue is within RESERVED_DEGREES of
              one of them is refused when chosen; a kept colour that comes too near later (a kind colour
              chosen since) is shown turned just far enough away, its own kept as it was.
  [READABLE]  every colour shown is made readable in each theme by the kind colours' rule (kind_colours.
              fitted: 4.5 to 1 against the page and the panels, 7 to 1 in high contrast), its hue kept.
  [ASSIGNED]  a connection's colour is this computer's, the same in every project (the owner, 2026-11-17:
              connections are a library outside any project). It is kept in colours.toml, keyed by the
              connection's name (sorted keys, one stable line each: a save that changes nothing changes no
              byte, so the file diffs well in the library's Git repository). One with no line there (saved
              before colours existed, or on the blades page) wears the first free colour in its turn (by
              name), so every one has one.

Pure rules, no I/O. A colour is #rrggbb, lower case.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from swissarmybench.domain import kind_colours
from swissarmybench.domain.themes import HEX, contrast

# The palette: names (for the agent and the picker's tooltips) and the light theme's colour; each theme
# shows it made readable there. Ordered so that neighbours differ most.
PALETTE: tuple[tuple[str, str], ...] = (
    ("Teal", "#0e7c7b"),
    ("Magenta", "#b3307f"),
    ("Olive", "#6b7a12"),
    ("Orchid", "#9b3fae"),
    ("Rust", "#b4521e"),
    ("Pine", "#1d7a5a"),
    ("Brown", "#7d5a45"),
    ("Slate", "#5f6670"),
)
# The accent (grid.css --accent, light and dark) and the error colour: the rail's current bar and the
# brand. The errors' red sits beside it, so one guard keeps both.
ACCENTS: tuple[str, ...] = ("#c8102e", "#ff6b73")
RESERVED_DEGREES = 18.0
# Below this saturation a colour is a grey: it has no hue to clash with.
GREY = 0.25


class ConnectionColourError(ValueError):
    """A colour that cannot be a connection's (the message says why)."""


def _hsv(colour: str) -> tuple[float, float, float]:
    hue, saturation = kind_colours._hue_saturation(colour)
    value = max(int(colour[i : i + 2], 16) for i in (1, 3, 5)) / 255
    return hue, saturation, value


def _from_hsv(hue: float, saturation: float, value: float) -> str:
    hue %= 360
    chroma = value * saturation
    x = chroma * (1 - abs((hue / 60) % 2 - 1))
    low = value - chroma
    r, g, b = [
        (chroma, x, 0.0),
        (x, chroma, 0.0),
        (0.0, chroma, x),
        (0.0, x, chroma),
        (x, 0.0, chroma),
        (chroma, 0.0, x),
    ][int(hue // 60) % 6]
    return "#" + "".join(f"{round((c + low) * 255):02x}" for c in (r, g, b))


def _apart(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def reserved() -> dict[str, str]:
    """The rail's colours, by what each is: the kind colours (the light theme's) and the accent."""
    out = {kind: kind_colours.DEFAULTS["light"][kind] for kind in kind_colours.KINDS}
    return out | {"accent": ACCENTS[0]}


def clash(colour: str) -> str | None:
    """What a colour is too near (a kind's name, "accent" or "amber"), or None: it may be a connection's."""
    if kind_colours.looks_amber(colour):
        return "amber"
    hue, saturation, _ = _hsv(colour)
    if saturation < GREY:
        return None
    for what, other in reserved().items():
        their_hue, their_saturation = kind_colours._hue_saturation(other)
        if their_saturation >= GREY and _apart(hue, their_hue) < RESERVED_DEGREES:
            return what
    return None


_WORDS = {
    "app": "the app pages' violet",
    "notebook": "the notebooks' blue",
    "script": "the scripts' green",
    "accent": "the rail's red",
    "amber": "amber, which means out of date",
}


def check(sent: Any) -> str | None:
    """A colour as sent: #rrggbb, or null (the connection takes the next free one again)."""
    if sent is None:
        return None
    if not isinstance(sent, str) or not HEX.match(sent):
        raise ConnectionColourError("A connection's colour is #rrggbb, like #0e7c7b.")
    near = clash(sent.lower())
    if near:
        raise ConnectionColourError(
            f"{sent.lower()} reads as {_WORDS[near]}: the rail keeps its colours. Choose another colour."
        )
    return sent.lower()


def kept(raw: Any) -> str | None:
    """A record's colour as read back (anything that is not #rrggbb is no colour)."""
    return raw.lower() if isinstance(raw, str) and HEX.match(raw) else None


def shifted(colour: str) -> str:
    """`colour`, turned just far enough from a rail colour it has come too near (its saturation and
    brightness kept); unchanged when it is near none."""
    out = colour
    for _ in range(4):
        near = clash(out)
        if near is None:
            return out
        hue, saturation, value = _hsv(out)
        if near == "amber":
            target = 25.0 if hue < 45 else 65.0
        else:
            their = kind_colours._hue_saturation(reserved()[near])[0]
            step = (hue - their + 540) % 360 - 180  # which side of it this hue is on
            target = their + (RESERVED_DEGREES + 2) * (1 if step >= 0 else -1)
        out = _from_hsv(target, saturation, value)
    return out


def palette() -> list[tuple[str, str]]:
    """The palette's colours a connection may be given (any too near a kind colour the user chose since
    is left out)."""
    return [(name, colour) for name, colour in PALETTE if clash(colour) is None]


def next_free(worn: Iterable[str]) -> str:
    """The colour a new connection is given: the palette's first that none wears, else the least worn."""
    counts: dict[str, int] = {}
    for colour in worn:
        counts[colour.lower()] = counts.get(colour.lower(), 0) + 1
    offered = [colour for _, colour in palette()] or [PALETTE[0][1]]
    return min(offered, key=lambda c: (counts.get(c, 0), offered.index(c)))


def assign(connections: Sequence[tuple[str, str | None]]) -> dict[str, str]:
    """Every connection's colour: its own kept one, else the next free one in turn (by name)."""
    out = {name: colour for name, colour in connections if colour}
    for name, colour in sorted(connections, key=lambda c: c[0].casefold()):
        if not colour:
            out[name] = next_free(out.values())
    return out


def themes(colour: str) -> dict[str, str]:
    """The colour each theme shows: turned from a rail colour if it came too near, made readable."""
    base = shifted(colour)
    return {theme: kind_colours.fitted(base, theme) for theme in kind_colours.THEMES}


def listing(connections: Sequence[tuple[str, str | None]]) -> dict[str, Any]:
    """What every page and the agent see: each connection's colour (`chosen`: its record's, null when
    it wears the next free one), each theme's, and the palette."""
    colours = assign(connections)
    return {
        "connections": [
            {
                "name": name,
                "colour": colours[name],
                "chosen": colour,
                "themes": themes(colours[name]),
            }
            for name, colour in connections
        ],
        "palette": [{"name": name, "colour": c, "themes": themes(c)} for name, c in palette()],
    }


def readable_everywhere(colour: str) -> bool:
    """The colour each theme shows stands far enough from each of that theme's backgrounds."""
    shown = themes(colour)
    return all(
        contrast(shown[theme], background) >= kind_colours.RATIO[theme] - 0.01
        for theme in kind_colours.THEMES
        for background in kind_colours.BACKGROUNDS[theme]
    )


# ===== colours.toml =====

TOML_HEAD = "# Each connection's colour (Swiss Army Bench). One line per connection, by name.\n"


def _toml_key(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_toml(colours: Mapping[str, str]) -> str:
    """colours.toml's text: sorted keys (case folded, then as spelled), one `"name" = "#rrggbb"` line
    each, so the same colours are always the same bytes."""
    lines = [
        f'{_toml_key(name)} = "{colour.lower()}"'
        for name, colour in sorted(colours.items(), key=lambda kv: (kv[0].casefold(), kv[0]))
        if kept(colour) and not any(ord(ch) < 32 for ch in name)
    ]
    return TOML_HEAD + "".join(line + "\n" for line in lines)


def from_toml(text: str) -> dict[str, str]:
    """colours.toml read back: every name with a #rrggbb colour (anything else, or a broken file, is no
    colour: the connections wear their next free ones)."""
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeError):
        return {}
    out: dict[str, str] = {}
    for name, raw in data.items():
        colour = kept(raw)
        if colour:
            out[name] = colour
    return out
