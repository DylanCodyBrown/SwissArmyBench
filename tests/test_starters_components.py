"""The Components family of the starter pack (docs/ideas.md, "Components: your own HTML and JavaScript in
Streamlit", 2026-11-15): Streamlit pieces for a Python cell that put HTML, CSS and JavaScript of their
own on the page, in one of Streamlit's three ways (st.html, a frame, a two-way v2 component).

Every piece says what it makes and reads (tests/test_starters.py checks those against the app's name
finder, and every `st.` call against its header, for all Streamlit pieces); here: each says which way it
uses and uses that way, nothing is fetched from the internet, no value is ever pasted into the HTML, CSS
or JavaScript, and each runs under Streamlit's own test runner (AppTest) with a made-up table. A value
holding `</script><b>x` reaches the page as text only.

AppTest runs the Python; it has no browser, so it cannot click inside a component. The two-way pieces
are tested on their Python side: the component registers and mounts, gives back its default, and a value
put in its state (what the JavaScript's setStateValue does) comes back from the mount call; a trigger
(setTriggerValue, which AppTest cannot set) is stood in for at the mount call. Streamlit is never the
app's dependency: these run in the Python named by SWISSARMYBENCH_STREAMLIT_PYTHON, and are skipped
without one, as in tests/test_starters_streamlit.py."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain.blades import read_blade
from swissarmybench.domain.snippets import fill
from swissarmybench_streamlit.domain.streamlit_cells import facts
from tests.test_starters_streamlit import PYTHON, TABLE

FOLDER = Path(__file__).resolve().parents[1] / "extensions" / "streamlit" / "src" / "swissarmybench_streamlit"
FOLDER = FOLDER / "starters"  # the Streamlit extension's starters
FILES = sorted(FOLDER.glob("components_*.blade.py"))
PIECES = [read_blade(p.read_text(encoding="utf-8")) for p in FILES]
VALUES = {
    "table": "orders",
    "column": "region",
    "value column": "amount",
    "date column": "order_date",
    "title column": "product",
}
# The way each piece is built, by the call that builds it.
WAYS = {
    "1, st.html": "st.html",
    "2, a frame": "st.iframe",
    "3, a v2 component": "st.components.v2.component",
}
TWO_WAY = {
    "Component clickable cards",
    "Component segmented slicer",
    "Component copy table button",
    "Component keyboard shortcuts",
}
NASTY = "</script><b>x"

needs_streamlit = pytest.mark.skipif(
    PYTHON is None,
    reason="no Python with Streamlit, pandas and openpyxl here (set SWISSARMYBENCH_STREAMLIT_PYTHON to one)",
)


def _filled(piece: dict[str, Any], values: dict[str, str] | None = None) -> str:
    return fill(piece["code"], "streamlit", VALUES | (values or {}))


def _calls(tree: ast.AST) -> set[str]:
    """Every st.<...> chain the code names, whole (st.components.v2.component, not its parts)."""
    found: set[str] = set()
    inner: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            inner.add(id(node.value))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or id(node) in inner:
            continue
        parts: list[str] = []
        part: ast.AST = node
        while isinstance(part, ast.Attribute):
            parts.append(part.attr)
            part = part.value
        if isinstance(part, ast.Name) and part.id == "st":
            found.add(".".join(["st", *reversed(parts)]))
    return found


def _code_strings(text: str, values: dict[str, str]) -> list[str]:
    """The piece's HTML, CSS and JavaScript: every string in it that holds markup, a style or a script
    (a value given, a string by itself, is not)."""
    tree = ast.parse(text)
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    code = [s for s in strings if re.search(r"<\w|\{\s*$|export default|\{ [a-z-]+:", s, re.MULTILINE)]
    return [s for s in code if s not in values.values()]


# ===== the family =====


def test_the_family_has_its_nine_pieces_each_a_streamlit_piece_for_a_python_cell() -> None:
    assert [p["name"] for p in PIECES] == [
        "Component animated KPI counter",
        "Component callout banner",
        "Component clickable cards",
        "Component copy table button",
        "Component gauge",
        "Component keyboard shortcuts",
        "Component segmented slicer",
        "Component sortable table",
        "Component timeline",
    ]
    for piece in PIECES:
        assert piece["family"] == "Components" and piece["language"] == "streamlit", piece["name"]
        assert piece["kind"] == "snippet" and "component" in piece["tags"], piece["name"]
        assert ("two-way" in piece["tags"]) == (piece["name"] in TWO_WAY), piece["name"]


def test_every_piece_explains_the_three_ways_in_the_same_words() -> None:
    def block(code: str) -> str:
        found = re.search(r"^# Three ways.*?(?=^#\n)", code, re.MULTILINE | re.DOTALL)
        assert found, "no '# Three ways' paragraph"
        return found.group(0)

    blocks = {block(p["code"]) for p in PIECES}
    assert len(blocks) == 1
    (words,) = blocks
    assert "TWO-WAY" in words and "never pasted into them as code" in words and "html.escape" in words


@pytest.mark.parametrize("piece", PIECES, ids=lambda p: p["name"])
def test_a_piece_says_which_way_it_uses_why_and_uses_it(piece: dict[str, Any]) -> None:
    text = _filled(piece)
    said = re.search(r"^# This piece uses (\d, [^:]+):(.+)$", text, re.MULTILINE)
    assert said, "no '# This piece uses ...:' line"
    way = WAYS[said.group(1)]
    assert len(said.group(2).strip()) > 20, "the line says why"
    used = _calls(ast.parse(text)) & set(WAYS.values())
    assert used == {way}
    assert (way == "st.components.v2.component") == (piece["name"] in TWO_WAY)
    if way == "st.html":
        assert "unsafe_allow_javascript=True" in text  # its <script> runs only so
    if way == "st.components.v2.component":
        # how the value travels, both ways, said where it happens
        assert "Python to the page:" in text and "The page to Python:" in text
        assert re.search(r"set(State|Trigger)Value\(\"\w+\"", text)


@pytest.mark.parametrize("piece", PIECES, ids=lambda p: p["name"])
def test_nothing_comes_from_the_internet(piece: dict[str, Any]) -> None:
    text = _filled(piece)
    pattern = r"https?://|<link|@import|url\(|src=|fetch\(|import\(|XMLHttpRequest|WebSocket|sendBeacon"
    assert not re.search(pattern, text, re.IGNORECASE)


@pytest.mark.parametrize("piece", PIECES, ids=lambda p: p["name"])
def test_no_value_is_pasted_into_the_html_css_or_javascript(piece: dict[str, Any]) -> None:
    """Every placeholder stands in Python (a name, a number, or a string Python then escapes or hands
    over as data), never inside the page's code; and the JavaScript writes values as text only."""
    values = {"label": NASTY, "title": NASTY, "message": NASTY, "keys": NASTY}
    text = _filled(piece, values)
    code = _code_strings(text, values)
    assert code, "the piece's HTML, CSS and JavaScript are found"
    for string in code:
        assert NASTY not in string and "orders" not in string and "region" not in string
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", string)


# ===== under Streamlit's own test runner =====

RUNNER = """
import json, sys
from streamlit.testing.v1 import AppTest

import streamlit.components.v2 as v2

real = v2.component
found = {}
for job in json.load(open(sys.argv[1], encoding="utf-8")):
    v2.component = real  # a stand-in a job before put in (STAND_IN) goes with it
    at = AppTest.from_file(job["path"], default_timeout=60).run()
    for key, value in job.get("state", {}).items():
        at.session_state[key] = value  # what the component's setStateValue does in a browser
    if job.get("state"):
        at.run()
    shown = []
    for element in at.main:
        kind = element.type
        proto = getattr(element, "proto", None)
        if kind == "html":
            shown.append({"kind": kind, "body": element.value})
        elif kind == "iframe":
            shown.append({"kind": kind, "srcdoc": proto.srcdoc})
        elif kind == "bidi_component":
            shown.append({"kind": kind, "name": proto.component_name, "html": proto.html_content,
                          "css": proto.css_content, "js": proto.js_content, "data": proto.json,
                          "value": dict(element.value or {})})
        elif kind in ("markdown", "caption", "text"):
            shown.append({"kind": kind, "body": element.value})
    found[job["path"]] = {
        "problems": [str(e.value) for e in at.exception] + [f"error box: {e.value}" for e in at.error],
        "shown": shown,
        "toasts": [t.value for t in at.toast],
    }
print(json.dumps(found))
"""
# Each name a piece makes, shown after it as text (a table by its rows), so the test can read it.
MADE = """
st.text("MADE " + json.dumps({_n: (len(_v) if hasattr(_v, "columns") else _v) for _n, _v in [{pairs}]}))
"""
# A trigger stood in for at the mount call (AppTest cannot press a key or click in a component).
STAND_IN = """
import streamlit as st

_real_component = st.components.v2.component


def _standing_in(name, **parts):
    mount = _real_component(name, **parts)

    def mounted(**given):
        result = mount(**given)
        result.update({triggers})
        return result

    return mounted


st.components.v2.component = _standing_in
"""


def _script(code: str, table: str = TABLE, triggers: dict[str, Any] | None = None) -> str:
    found = facts(code)
    imported = ("st", "pd", "json", "html", "Template")
    made = [n for n in found.makes if not n.startswith("_") and n not in imported]
    pairs = ", ".join(f"({n!r}, {n})" for n in made)
    stand_in = STAND_IN.replace("{triggers}", repr(triggers)) if triggers else ""
    tail = ("import json\n" + MADE.replace("{pairs}", pairs)) if made else ""
    return stand_in + table + "\n" + code + "\n" + tail


def _run(jobs: list[dict[str, Any]], folder: Path) -> dict[str, dict[str, Any]]:
    for job in jobs:
        path = folder / f"{job['name'].replace(' ', '_')}.py"
        path.write_text(job.pop("script"), encoding="utf-8")
        job["path"] = str(path)
    spec = folder / "jobs.json"
    spec.write_text(json.dumps(jobs), encoding="utf-8")
    environment = os.environ | {"STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
    done = subprocess.run(  # noqa: S603 (the tester's Streamlit Python, on files this test wrote)
        [str(PYTHON), "-I", "-c", RUNNER, str(spec)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=folder,
        env=environment,
    )
    assert done.returncode == 0, done.stderr[-3000:]
    answer: dict[str, dict[str, Any]] = json.loads(done.stdout.strip().splitlines()[-1])
    return {job["name"]: answer[job["path"]] for job in jobs}


def _made(found: dict[str, Any]) -> dict[str, Any]:
    texts = [s["body"] for s in found["shown"] if s["kind"] == "text" and s["body"].startswith("MADE ")]
    return json.loads(texts[-1].removeprefix("MADE ")) if texts else {}


def _of(found: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [s for s in found["shown"] if s["kind"] == kind]


@needs_streamlit
def test_every_piece_runs_under_streamlits_own_test_runner(tmp_path: Path) -> None:
    jobs = [{"name": p["name"], "script": _script(_filled(p))} for p in PIECES]
    found = _run(jobs, tmp_path)
    assert {name: f["problems"] for name, f in found.items() if f["problems"]} == {}
    by_way = {name: {s["kind"] for s in f["shown"]} for name, f in found.items()}
    assert "html" in by_way["Component callout banner"] and "html" in by_way["Component animated KPI counter"]
    for name in ("Component sortable table", "Component gauge", "Component timeline"):
        assert "iframe" in by_way[name], name
    for name in TWO_WAY:
        assert "bidi_component" in by_way[name], name
    # what the pieces drew, from the made-up table (40 orders, four regions)
    kpi = _of(found["Component animated KPI counter"], "html")[0]["body"]
    total = sum(round(10 + (i * 7.3) % 90, 2) for i in range(40))
    counted = re.search(r'data-sab-count="([^"]+)"', kpi)
    assert counted and float(counted.group(1)) == pytest.approx(total) and f">{total:,.0f}<" in kpi
    table = _of(found["Component sortable table"], "iframe")[0]["srcdoc"]
    assert '"columns": ["region", "product", "order_date"' in table and '"total": 40' in table
    assert '["North", "Widget", "2026-01-01", ' in table  # a date as its day
    gauge = _of(found["Component gauge"], "iframe")[0]["srcdoc"]
    assert f'"words": "{total:,.0f} of 1,000,000"' in gauge
    timeline = _of(found["Component timeline"], "iframe")[0]["srcdoc"]
    assert timeline.count('"when": ') == 12 and '[{"when": "28 Apr 2026"' in timeline  # the latest first


@needs_streamlit
def test_the_two_way_pieces_register_mount_and_give_back_their_default(tmp_path: Path) -> None:
    jobs = [{"name": p["name"], "script": _script(_filled(p))} for p in PIECES if p["name"] in TWO_WAY]
    found = _run(jobs, tmp_path)
    assert {name: f["problems"] for name, f in found.items() if f["problems"]} == {}
    mounted = {name: _of(f, "bidi_component")[0] for name, f in found.items()}
    assert {name: m["name"] for name, m in mounted.items()} == {
        "Component clickable cards": "sab_clickable_cards",
        "Component segmented slicer": "sab_segmented_slicer",
        "Component copy table button": "sab_copy_table",
        "Component keyboard shortcuts": "sab_keyboard_shortcuts",
    }
    for name, m in mounted.items():
        assert m["js"].lstrip().startswith("export default function (component)"), name
    # the defaults: no card picked (every row), "All" on the slicer, no key pressed
    assert _made(found["Component clickable cards"]) == {"picked_region": None, "by_region": 40}
    assert _made(found["Component segmented slicer"]) == {"picked_region": "All", "by_region": 40}
    assert _made(found["Component keyboard shortcuts"]) == {"pressed_key": None}
    assert mounted["Component clickable cards"]["value"] == {"picked": None}
    assert mounted["Component segmented slicer"]["value"] == {"picked": "All"}
    # what Python sends is data: the cards' words and totals, the slicer's options, the keys, the text
    cards = json.loads(mounted["Component clickable cards"]["data"])
    assert [c["label"] for c in cards["cards"]] == ["East", "North", "South", "West"]
    assert cards["picked"] is None
    assert cards["label"] == "Region" and cards["cards"][0]["rows"] == "10 rows"
    slicer = json.loads(mounted["Component segmented slicer"]["data"])
    assert slicer["options"] == ["All", "East", "North", "South", "West"]
    assert json.loads(mounted["Component keyboard shortcuts"]["data"]) == {"keys": ["n", "p", "r"]}
    copied = json.loads(mounted["Component copy table button"]["data"])
    assert copied["rows"] == 40 and copied["text"].startswith("region\tproduct\torder_date\tamount\t")
    assert found["Component copy table button"]["toasts"] == []  # nothing copied yet


@needs_streamlit
def test_a_value_the_javascript_sends_comes_back_from_the_mount_call(tmp_path: Path) -> None:
    """A state (setStateValue in a browser) put where Streamlit keeps it; a trigger stood in for."""
    by_name = {p["name"]: p for p in PIECES}
    jobs: list[dict[str, Any]] = [
        {
            "name": "cards",
            "script": _script(_filled(by_name["Component clickable cards"])),
            "state": {"picked_region_pick": {"picked": "South"}},
        },
        {
            "name": "slicer",
            "script": _script(_filled(by_name["Component segmented slicer"])),
            "state": {"picked_region_pick": {"picked": "West"}},
        },
        {
            "name": "keys",
            "script": _script(_filled(by_name["Component keyboard shortcuts"]), triggers={"pressed": "n"}),
        },
        {
            "name": "copy",
            "script": _script(_filled(by_name["Component copy table button"]), triggers={"copied": 40}),
        },
    ]
    found = _run(jobs, tmp_path)
    assert {name: f["problems"] for name, f in found.items() if f["problems"]} == {}
    assert _made(found["cards"]) == {"picked_region": "South", "by_region": 10}
    # the card picked goes back to the page as data, so it is drawn picked
    assert json.loads(_of(found["cards"], "bidi_component")[0]["data"])["picked"] == "South"
    assert _made(found["slicer"]) == {"picked_region": "West", "by_region": 10}
    assert json.loads(_of(found["slicer"], "bidi_component")[0]["data"])["picked"] == "West"
    assert _made(found["keys"]) == {"pressed_key": "n"}
    assert "You pressed n." in [s["body"] for s in _of(found["keys"], "caption")]
    assert found["copy"]["toasts"] == ["Copied 40 rows: paste them into Excel."]


class _Tags(HTMLParser):
    """The tags a page holds, and what its scripts say, as a browser reads them."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.scripts: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self._in_script = tag == "script"

    def handle_endtag(self, tag: str) -> None:
        self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.scripts.append(data)


def _read(page: str) -> _Tags:
    parser = _Tags()
    parser.feed(page)
    parser.close()
    return parser


@needs_streamlit
def test_a_value_holding_a_closing_script_tag_is_shown_as_text(tmp_path: Path) -> None:
    """`</script><b>x` in the data and in every label: never a <b> tag, never the end of a script;
    on the page it is text, and in a frame's data JSON that reads back as the same characters."""
    nasty_table = TABLE + (
        f"orders['region'] = ['North', {NASTY!r}, 'East', 'West'] * 10\n"
        f"orders['product'] = [{NASTY!r}, 'Gadget', 'Gizmo', 'Doohickey', 'Widget'] * 8\n"
    )
    values = {"label": NASTY, "title": NASTY, "message": NASTY}
    jobs = [{"name": p["name"], "script": _script(_filled(p, values), nasty_table)} for p in PIECES]
    found = _run(jobs, tmp_path)
    assert {name: f["problems"] for name, f in found.items() if f["problems"]} == {}
    for name, f in found.items():
        for shown in f["shown"]:
            if shown["kind"] == "html":  # st.html: escaped text
                page = _read(shown["body"])
                assert "b" not in page.tags, name
                assert "&lt;/script&gt;&lt;b&gt;x" in shown["body"], name
                assert all(NASTY not in s for s in page.scripts), name
            elif shown["kind"] == "iframe":  # a frame: the data as JSON, < > & written as \u003c...
                page = _read(shown["srcdoc"])
                assert "b" not in page.tags and page.tags.count("script") == 2, name
                data = json.loads(page.scripts[0])
                assert NASTY in json.dumps(data, ensure_ascii=False), name  # read back as it was
                assert NASTY not in shown["srcdoc"], name
            elif shown["kind"] == "bidi_component":  # a component: in its data only
                for part in ("html", "css", "js"):
                    assert NASTY not in shown[part] and "<b>" not in shown[part], (name, part)
                if name != "Component keyboard shortcuts":  # it shows no value of the data
                    assert NASTY in shown["data"], name
    cards = json.loads(_of(found["Component clickable cards"], "bidi_component")[0]["data"])
    assert NASTY in [c["label"] for c in cards["cards"]] and cards["label"] == NASTY
