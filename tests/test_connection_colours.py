"""Connection colours (the owner, 2026-11-16: "choose connection colors that everything associated with
that connection is painted that color ... reserve the rail colors for the rail"): the palette and its
turns, the rail's colours refused or turned away from, every colour readable in every theme, the colour
kept in the connection's own record, which cells use which connection, and the agent's command."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from swissarmybench.domain import connection_colours as rules
from swissarmybench.domain import connection_usage, kind_colours
from swissarmybench.domain.themes import contrast
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


# ===== the palette =====


def test_the_palette_wears_none_of_the_rails_colours_and_reads_in_every_theme() -> None:
    assert len(rules.PALETTE) == 8
    assert len({c for _, c in rules.PALETTE}) == 8
    for _, colour in rules.PALETTE:
        assert rules.clash(colour) is None, colour
        assert rules.readable_everywhere(colour), colour
    # Every theme's colour stands 4.5 to 1 (7 in high contrast) from that theme's page and panels.
    shown = rules.themes("#0e7c7b")
    for theme in kind_colours.THEMES:
        for background in kind_colours.BACKGROUNDS[theme]:
            assert contrast(shown[theme], background) >= kind_colours.RATIO[theme] - 0.01


def test_a_new_connection_gets_the_next_free_colour() -> None:
    first, second, third = (c for _, c in rules.PALETTE[:3])
    assert rules.next_free([]) == first
    assert rules.next_free([first]) == second
    assert rules.next_free([second, first.upper()]) == third
    every = [c for _, c in rules.PALETTE]
    assert rules.next_free(every) == first  # all worn: the least worn, first in turn
    assert rules.next_free([*every, first]) == second


def test_connections_without_a_kept_colour_wear_the_free_ones_in_turn() -> None:
    first, second, third = (c for _, c in rules.PALETTE[:3])
    colours = rules.assign([("Warehouse", second), ("orders api", None), ("Finance", None)])
    assert colours == {"Warehouse": second, "Finance": first, "orders api": third}
    listed = rules.listing([("Warehouse", second), ("Finance", None)])
    assert [(c["name"], c["chosen"]) for c in listed["connections"]] == [
        ("Warehouse", second),
        ("Finance", None),
    ]
    assert listed["connections"][1]["colour"] == first
    assert set(listed["connections"][0]["themes"]) == set(kind_colours.THEMES)
    assert len(listed["palette"]) == 8


# ===== the rail's colours =====


@pytest.mark.parametrize(
    ("colour", "words"),
    [
        ("#7b3fc4", "violet"),  # the app pages' own
        ("#8044cc", "violet"),  # near it
        ("#1f63b0", "blue"),
        ("#2b7238", "green"),
        ("#c8102e", "red"),  # the accent: the rail's current bar
        ("#d29922", "amber"),
    ],
)
def test_the_rails_colours_are_refused(colour: str, words: str) -> None:
    with pytest.raises(rules.ConnectionColourError, match=words):
        rules.check(colour)


def test_what_is_sent_is_checked() -> None:
    assert rules.check("#0E7C7B") == "#0e7c7b"
    assert rules.check(None) is None
    assert rules.check("#808080") == "#808080"  # a grey has no hue to clash with
    with pytest.raises(rules.ConnectionColourError, match="#rrggbb"):
        rules.check("teal")
    assert rules.kept("#ABCDEF") == "#abcdef" and rules.kept("nope") is None and rules.kept(3) is None


# ===== which connections a cell uses =====


def test_the_connections_a_cell_names() -> None:
    assert connection_usage.cell_connections("sql", "SELECT 1", "Warehouse -> orders") == ["Warehouse"]
    assert connection_usage.cell_connections("dax", "EVALUATE x", "Finance/Sales model") == ["Finance"]
    code = (
        "import swissarmybench as sab\n"
        "# sab.sql('Hidden', 'x') in a comment is no use\n"
        "a = sab.sql('Warehouse', 'SELECT 1')\n"
        "b = sab.read(connection='Orders API', table='orders')\n"
        "c = sab.sql('Warehouse', 'SELECT 2')\n"
        "%time d = 1\n"
    )
    assert connection_usage.cell_connections("code", code, None) == ["Warehouse", "Orders API"]
    assert connection_usage.cell_connections("markdown", "sab.sql('Warehouse')", None) == []
    assert connection_usage.cell_connections("code", "def (", None) == []


# ===== kept in the connection's record; the pages and the agent =====


def _connection(client: object, name: str, colour: str | None = None) -> None:
    body: dict[str, object] = {
        "name": name,
        "kind": "sql",
        "template": "postgres",
        "dialect": "postgres",
        "code": "import sqlite3\nconn = sqlite3.connect(':memory:')\n",
        "variable": "conn",
    }
    if colour:
        body["colour"] = colour
    answer = client.post("/connections", json=body, headers=AUTH)  # type: ignore[attr-defined]
    assert answer.status_code == 200, answer.text


def test_a_connection_keeps_its_colour_and_the_user_and_agent_change_it(tmp_path: Path) -> None:
    first, second = (c for _, c in rules.PALETTE[:2])
    with make_client(tmp_path) as client:
        _connection(client, "Warehouse")
        _connection(client, "Finance")
        listed = {
            c["name"]: c for c in client.get("/connection-colours", headers=AGENT).json()["connections"]
        }
        assert listed["Warehouse"]["chosen"] == first and listed["Finance"]["chosen"] == second
        # Saved again from its form: the colour stays.
        again = client.put(
            "/connections/Warehouse",
            json={
                "name": "Warehouse",
                "kind": "sql",
                "template": "postgres",
                "dialect": "postgres",
                "code": "import sqlite3\nconn = sqlite3.connect(':memory:')\n",
                "variable": "conn",
            },
            headers=AUTH,
        )
        assert again.status_code == 200, again.text
        done = client.put("/connection-colours/Warehouse", json={"colour": "#808080"}, headers=AGENT)
        assert done.status_code == 200, done.text
        assert {c["name"]: c["chosen"] for c in done.json()["connections"]}["Warehouse"] == "#808080"
        refused = client.put("/connection-colours/Warehouse", json={"colour": "#7b3fc4"}, headers=AUTH)
        assert refused.status_code == 400 and "violet" in refused.text
        assert (
            client.put("/connection-colours/Nope", json={"colour": "#808080"}, headers=AUTH).status_code
            == 404
        )
        uses = client.post(
            "/connection-colours/uses",
            json={
                "cells": [
                    {"kind": "code", "source": "x = sab.sql('warehouse', 'q')"},
                    {"kind": "sql", "connection": "Finance"},
                    {"kind": "code", "source": "sab.sql('Gone', 'q')"},
                ]
            },
            headers=AUTH,
        ).json()
        assert uses == {"cells": [["Warehouse"], ["Finance"], []]}
    # The library's colours.toml, sorted keys, one line each: a new start keeps it.
    kept = (tmp_path / "state" / "library" / "colours.toml").read_text(encoding="utf-8")
    assert kept.splitlines()[1:] == ['"Finance" = "' + second + '"', '"Warehouse" = "#808080"']
    with make_client(tmp_path) as client:
        listed = {c["name"]: c for c in client.get("/connection-colours", headers=AUTH).json()["connections"]}
        assert listed["Warehouse"]["colour"] == "#808080"
        assert client.get("/connections/Warehouse", headers=AUTH).json().get("colour") == "#808080"


# ===== colours.toml =====


def test_colours_toml_is_sorted_stable_and_read_back() -> None:
    text = rules.to_toml(
        {"warehouse": "#0E7C7B", 'Orders "API"': "#b3307f", "Bad": "nope", "a\nb": "#123456"}
    )
    assert text.splitlines() == [
        rules.TOML_HEAD.strip(),
        '"Orders \\"API\\"" = "#b3307f"',
        '"warehouse" = "#0e7c7b"',
    ]
    assert rules.from_toml(text) == {'Orders "API"': "#b3307f", "warehouse": "#0e7c7b"}
    assert rules.to_toml(rules.from_toml(text)) == text  # the same colours: the same bytes
    assert rules.from_toml("not = [toml") == {} and rules.from_toml('x = 3\ny = "#zzzzzz"') == {}


def test_a_save_that_changes_nothing_writes_nothing(tmp_path: Path) -> None:
    from swissarmybench.adapters.connection_colours import ColoursFile

    kept = ColoursFile(tmp_path / "colours.toml")
    kept.write(rules.to_toml({"Warehouse": "#0e7c7b"}))
    before = (tmp_path / "colours.toml").stat().st_mtime_ns
    kept.write(rules.to_toml({"Warehouse": "#0e7c7b"}))
    assert (tmp_path / "colours.toml").stat().st_mtime_ns == before
    assert ColoursFile(None).read() == "" and ColoursFile(tmp_path / "none.toml").read() == ""


def test_a_renamed_connection_keeps_its_colour(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _connection(client, "Warehouse", "#808080")
        body = {
            "name": "Old warehouse",
            "kind": "sql",
            "template": "postgres",
            "dialect": "postgres",
            "code": "import sqlite3\nconn = sqlite3.connect(':memory:')\n",
            "variable": "conn",
        }
        assert client.put("/connections/Warehouse", json=body, headers=AUTH).status_code == 200
        listed = {
            c["name"]: c["chosen"]
            for c in client.get("/connection-colours", headers=AUTH).json()["connections"]
        }
        assert listed == {"Old warehouse": "#808080"}
        refused = client.post("/connections", json=body | {"name": "B", "colour": "#1f63b0"}, headers=AUTH)
        assert refused.status_code == 400 and "blue" in refused.text
