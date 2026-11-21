"""The Canvas's two layouts (domain/canvas_layouts.py; the owner, 2026-11-21: "Canvas should only have two
layouts phone portrait and desktop just like powerapps but ... always resizable"): every item in both, each
layout its own places, stored as fractions of the parent's width that round-trip to the pixel; an item made in
one layout stacked in the other at full width (phone) or at the first free place (desktop); Show on hides it
in one; a format 1 file read as desktop with a phone layout made; the built page placing each item by
fractions in both layouts (desktop by default, phone below 768 px); and random commands in both layouts
keeping every rule, no item lost from either, the page compiling. Made-up data only."""

from __future__ import annotations

import json
import random
import re
from typing import Any

import pytest

from swissarmybench_streamlit.domain import canvas_build as build
from swissarmybench_streamlit.domain import canvas_layouts as layouts
from swissarmybench_streamlit.domain import canvas_model as engine
from swissarmybench_streamlit.domain import widget_properties as props
from swissarmybench_streamlit.domain.canvas_model import CanvasError, WidgetFacts

FACTS = {
    "metric": WidgetFacts((3, 2), (2, 1), frozenset({"label", "value"})),
    "chart": WidgetFacts((6, 4), (3, 2), frozenset({"table_name", "colour"})),
}
METRIC = 'import streamlit as st\n\nlabel = "Revenue"\nvalue = 42\n\nst.metric(label, value)\n'
BUILT = {
    "metric": build.Built(METRIC, tuple(props.detect(METRIC))),
    "chart": build.Built("import streamlit as st\n\ntable_name = ''  # table\n\nst.write(table_name)\n", ()),
}


def run(canvas: dict[str, Any], kind: str, **body: Any) -> tuple[dict[str, Any], str | None]:
    return layouts.apply(canvas, kind, body, FACTS)


def px(canvas: dict[str, Any], node_id: str, layout: str = "desktop") -> dict[str, Any]:
    return engine.find(layouts.view(canvas, layout), node_id)[2]


def test_every_item_is_in_both_layouts_each_with_its_own_place() -> None:
    canvas, c1 = run(layouts.new_canvas("Sales"), "add_container", x=13, y=7, w=401, h=203)
    canvas, w1 = run(canvas, "insert_widget", parent=c1, widget="metric", x=5, y=31)
    assert (px(canvas, str(c1))["x"], px(canvas, str(c1))["w"]) == (13, 401)  # the pixel, round-tripped
    phone = px(canvas, str(c1), "phone")
    assert (phone["x"], phone["w"]) == (0, 390)  # stacked at full width
    assert px(canvas, str(w1), "phone")["w"] == 390
    # Moved in one layout, the other keeps its place.
    canvas, _ = run(canvas, "move", id=c1, x=100, layout="desktop")
    assert px(canvas, str(c1))["x"] == 100 and px(canvas, str(c1), "phone")["x"] == 0
    canvas, _ = run(canvas, "move", id=c1, y=40, layout="phone")
    assert px(canvas, str(c1), "phone")["y"] == 40 and px(canvas, str(c1))["y"] == 7
    # Made in phone: placed in desktop at a free place.
    canvas, c2 = run(canvas, "add_container", layout="phone", x=0, y=300, w=390, h=120)
    assert px(canvas, str(c2))["w"] > 390 and not layouts.problems(canvas, FACTS)
    text = layouts.write(canvas)
    assert layouts.write(layouts.read(text, FACTS).canvas) == text


def test_phone_stacks_new_items_in_reading_order() -> None:
    canvas = layouts.new_canvas("S")
    for x in (600, 0):
        canvas, _ = run(canvas, "add_container", x=x, y=0, w=300, h=100)
    first, second = px(canvas, "c1", "phone"), px(canvas, "c2", "phone")
    assert first["y"] == 0 and second["y"] == 108 and first["w"] == second["w"] == 390


def test_show_on_hides_an_item_in_one_layout_only() -> None:
    canvas, w1 = run(layouts.new_canvas("S"), "insert_widget", widget="metric")
    canvas, _ = run(canvas, "show", id=w1, show="desktop")
    page = build.page_code(canvas, "p1", BUILT)
    css = json.loads(re.search(r"sab\.style\((.*)\)", page).group(1))  # type: ignore[union-attr]
    phone = css[css.index("@media (max-width: 767px)") :]
    assert "display: none" in phone.split(".st-key-sab-w1 {")[1].split("}")[0]
    assert "display: none" not in css[: css.index("@media")].split(".st-key-sab-w1 {")[1].split("}")[0]
    with pytest.raises(CanvasError, match="Show on"):
        run(canvas, "show", id=w1, show="tablet")


def test_the_built_page_places_by_fractions_in_both_layouts() -> None:
    canvas, c1 = run(layouts.new_canvas("S"), "add_container", x=300, y=10, w=600, h=200)
    canvas, _ = run(canvas, "insert_widget", parent=c1, widget="metric", x=30, y=20)
    files = build.build(canvas, BUILT)
    assert not build.compiles(files)
    page = files["app_pages/page_1.py"]
    assert "left: calc((100%) * 0.25); top: 10px; width: calc((100%) * 0.5)" in page  # 300 and 600 of 1200
    assert "left: calc((100% + 2px) * 0.05 - 1px); top: 19px" in page  # inside c1's 1 px border
    assert "@media (max-width: 767px)" in page and "layout='wide'" in files["app.py"]


def test_a_format_1_canvas_is_read_as_desktop_with_a_phone_layout_made() -> None:
    old = engine.new_canvas("Old")
    old, _ = engine.apply(old, "add_container", {"x": 0, "y": 0, "w": 600, "h": 200}, FACTS)
    found = layouts.read(engine.write(old), FACTS)
    assert found.canvas["format"] == 2 and found.notes
    assert px(found.canvas, "c1")["w"] == 600 and px(found.canvas, "c1", "phone")["w"] == 390


def test_a_bad_layout_is_refused() -> None:
    with pytest.raises(CanvasError, match="phone or desktop"):
        run(layouts.new_canvas("S"), "add_container", layout="tablet")


@pytest.mark.parametrize("seed", range(30))
def test_random_commands_in_both_layouts_keep_every_rule_and_lose_nothing(seed: int) -> None:
    rng = random.Random(seed)  # noqa: S311 (made-up commands, not secrets)
    canvas = layouts.new_canvas("Fuzz")
    back: list[dict[str, Any]] = []
    for _step in range(50):
        layout = rng.choice(layouts.LAYOUTS)
        width = layouts.DESIGN[layout]
        nodes = [n for _, n in layouts.walk(canvas)]
        containers = [n["id"] for n in nodes if n["kind"] == "container"]
        ids = [n["id"] for n in nodes]
        choice = rng.choice(
            ["add", "add", "insert", "insert", "move", "resize", "nest", "delete", "undo", "columns", "show"]
        )
        kind, body = "", {}
        if choice == "undo" and back:
            canvas = back.pop()
            continue
        if choice == "add":
            kind = "add_container"
            body = {"parent": rng.choice([None, *containers]), "y": rng.randint(0, 600)}
            body |= {"w": rng.randint(8, width), "h": rng.randint(8, 300)}
        elif choice == "insert":
            kind = "insert_widget"
            body = {"widget": rng.choice(list(FACTS)), "parent": rng.choice([None, *containers])}
        elif choice == "move" and ids:
            kind, body = "move", {"id": rng.choice(ids), "x": rng.randint(0, width), "y": rng.randint(0, 900)}
        elif choice == "resize" and ids:
            kind, body = "move", {"id": rng.choice(ids), "w": rng.randint(1, width), "h": rng.randint(1, 400)}
        elif choice == "nest" and ids:
            kind, body = "move", {"id": rng.choice(ids), "parent": rng.choice(["", *containers])}
        elif choice == "delete" and ids:
            kind, body = "delete", {"id": rng.choice(ids)}
        elif choice == "columns":
            kind, body = "sizing", {"columns": rng.randint(1, 24)}
        elif choice == "show" and ids:
            kind, body = "show", {"id": rng.choice(ids), "show": rng.choice(layouts.SHOWS)}
        if not kind:
            continue
        try:
            after, _ = layouts.apply(canvas, kind, body | {"layout": layout}, FACTS)
        except CanvasError:
            continue
        back.append(canvas)
        canvas = after
        assert layouts.problems(canvas, FACTS) == [], (seed, kind, body, layout)
        every = {n["id"] for _, n in layouts.walk(canvas)}
        for each in layouts.LAYOUTS:  # no item lost from either layout
            assert {n["id"] for _, n in engine.walk(layouts.view(canvas, each))} == every
        assert layouts.read(layouts.write(canvas), FACTS).canvas == canvas
    assert build.compiles(build.build(canvas, BUILT)) == []
