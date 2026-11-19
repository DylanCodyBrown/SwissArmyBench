"""Launch, build history and the Performance Analyzer (the owner, 2026-11-19: "think Visual Studio"; builds
are folders in the project, shared in Git; the analyzer records only when it is opened).

The wire reader on made-up Streamlit messages (tests/golden/perf/*.bin, written once with Streamlit's own
classes: a new session, a markdown and a dataframe delta, a block, script_finished, two reruns); the socket's
reruns and their triggers; the hints' rules; build.json's bytes; compare; what changed; Restore's plans; then
over HTTP with a stand-in for the Streamlit process: Launch makes a build, a second Launch says what changed,
Compare shows it, Restore plans the old code, the analyzer's session joins the page's records and the socket's
messages and says the big uncached table. Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks
from swissarmybench_streamlit.domain import builds, perf
from swissarmybench_streamlit.domain import streamlit_cells as cells_rules
from tests.conftest import AUTH, make_client, push
from tests.test_streamlit_apps import ORDERS, FakeRunner, _ok

GOLDEN = Path(__file__).parent / "golden" / "perf"


def _bin(name: str) -> bytes:
    return (GOLDEN / f"{name}.bin").read_bytes()


# ===== the wire reader =====


def test_the_wire_reader_names_each_messages_kind_element_and_path_never_its_content() -> None:
    assert perf.read_forward(_bin("new_session")).kind == "new_session"
    markdown = perf.read_forward(_bin("markdown"))
    assert (markdown.kind, markdown.element, markdown.path) == ("delta", "markdown", (0, 1, 2))
    frame = perf.read_forward(_bin("dataframe"))
    assert (frame.element, frame.path, frame.size) == ("dataframe", (0, 3, 0), len(_bin("dataframe")))
    assert perf.read_forward(_bin("add_block")).element == "block"
    assert perf.read_forward(_bin("script_finished")).kind == "script_finished"
    rerun = perf.read_back(_bin("rerun"))
    assert rerun.kind == "rerun_script" and [k for k, _ in rerun.widgets] == ["region_pick", "zoom"]
    assert perf.read_back(_bin("rerun_fragment")).fragment == "fragment"
    # What is kept says nothing of the content: no markdown's words, no widget's value.
    said = json.dumps([markdown.to_json(), rerun.to_json(), [d for _, d in rerun.widgets]])
    assert "Orders by region" not in said and "West" not in said
    assert perf.read_forward(b"\xff\xff").kind == "unreadable"
    assert perf.widget_key("$$ID-0123abcd-region-pick") == "region-pick"
    assert perf.widget_key("$$ID-0123abcd-None") == "$$ID-0123abcd-None"


def _socket() -> list[perf.Message]:
    first = [perf.read_forward(_bin(n)) for n in ("new_session", "markdown", "dataframe", "script_finished")]
    second = [
        perf.read_back(_bin("rerun_fragment")),
        perf.read_forward(_bin("dataframe")),
        perf.read_forward(_bin("script_finished")),
    ]
    return [*first, perf.read_back(_bin("rerun")), *first[1:], *second]


def test_the_socket_is_grouped_per_rerun_with_its_trigger() -> None:
    reruns = perf.socket_reruns(_socket())
    assert [r.trigger for r in reruns] == ["first load", "region_pick", "zoom"]
    # The first rerun after the first load: both widgets are new, the first is its trigger; then zoom changed.
    assert reruns[0].to_json()["elements"]["dataframe"]["count"] == 1
    assert reruns[2].size == len(_bin("dataframe")) + len(_bin("script_finished"))


def _record(trigger: str, blocks: list[list[Any]], **more: Any) -> dict[str, Any]:
    return {
        "kind": "run",
        "page": "p1",
        "trigger": trigger,
        "ms": sum(b[1] for b in blocks),
        "blocks": blocks,
    } | more


def test_the_hints_rules() -> None:
    big = perf.Message("down", "delta", 4_800_000, "dataframe", (0, 3))
    socket = [perf.SocketRerun("first load", [big]), perf.SocketRerun("region_pick", [big])]
    records = [
        _record(
            "first load",
            [["b1", 2.0], ["b2", 120.0], ["b3", 300.0]],
            tables=[{"block": "b3", "rows": 90000, "columns": 12}],
            calls=[{"kind": "sql", "connection": "Shop", "query": "q1", "ms": 450.0, "cached": False}],
            caches=[
                {
                    "name": "load",
                    "cache": "data",
                    "calls": 2,
                    "misses": 2,
                    "miss_ms": 40.0,
                    "arguments": [[["day", "a1"]], [["day", "a2"]]],
                }
            ],
        ),
        _record(
            "region_pick",
            [["b1", 2.0], ["b2", 130.0], ["b3", 310.0]],
            tables=[{"block": "b3", "rows": 90000, "columns": 12}],
            calls=[{"kind": "sql", "connection": "Shop", "query": "q1", "ms": 470.0, "cached": False}],
            caches=[
                {
                    "name": "load",
                    "cache": "data",
                    "calls": 1,
                    "misses": 1,
                    "miss_ms": 20.0,
                    "arguments": [[["day", "a3"]]],
                }
            ],
        ),
        _record("region_pick", [["b1", 2.0], ["b2", 125.0], ["b3", 2.0]]),
    ]
    reruns = perf.reruns_of(records, socket)
    caches = perf.caches_of(records)
    assert caches[0] | {"arguments": None} == {
        "name": "load",
        "kind": "data",
        "calls": 3,
        "misses": 3,
        "miss_ms": 60.0,
        "hits": 0,
        "arguments": None,
    }
    facts = perf.Facts(
        titles={"b1": "Region", "b2": "Totals", "b3": "Orders"},
        makes={"b1": ("region",), "b2": ("totals",), "b3": ()},
        reads={"b1": (), "b2": ("orders",), "b3": ("region", "orders")},
        keys={"b1": ("region_pick",)},
    )
    said = {h["rule"]: h for h in perf.hints(reruns, caches, facts)}
    assert said["big_table"]["words"] == "Orders: 4.8 MB each rerun: cache it, or send fewer rows or columns."
    assert said["needless_rerun"]["block"] == "b2" and said["needless_rerun"]["words"].startswith(
        "Totals reruns each time region_pick changes though it does not read it"
    )
    assert said["cache_misses"]["words"] == "load misses every time: its argument day is new each call."
    assert said["slow_query"]["words"] == "A query on Shop took 460 ms, 2 times with the same text: cache it."
    small = [perf.Message("down", "delta", 80, "markdown")] * 250
    many = perf.hints(perf.reruns_of([_record("rerun", [])], [perf.SocketRerun("rerun", small)]), [], facts)
    assert [h["rule"] for h in many] == ["many_messages"]
    # No reason, no hint.
    quiet = perf.reruns_of([_record("first load", [["b1", 1.0]])], [perf.SocketRerun("first load", [])])
    assert perf.hints(quiet, [], facts) == []


# ===== builds =====


def test_build_json_is_byte_stable_and_says_what_changed() -> None:
    one = builds.build_json(3, "2026-11-19T10:00:00Z", "sales", "{}", ["The first build."], "started", 812.4)
    assert one == builds.build_json(
        3, "2026-11-19T10:00:00Z", "sales", "{}", ["The first build."], "started", 812.4
    )
    data = json.loads(one)
    assert list(data) == sorted(data) and one.endswith("}\n") and data["first_load_ms"] == 812
    saved = builds.with_session(one, "perf-20261119T100500Z.json")
    assert json.loads(saved)["sessions"] == ["perf-20261119T100500Z.json"]
    assert builds.with_session(saved, "perf-20261119T100500Z.json") == saved
    a = [
        builds.CellCode("app.ipynb", 1, "code", "Region", "x = 1"),
        builds.CellCode("app.ipynb", 2, "code", None, "y"),
    ]
    b = [
        builds.CellCode("app.ipynb", 1, "code", "Region", "x = 2"),
        builds.CellCode("app.ipynb", 3, "sql", None, "q"),
    ]
    assert builds.changes(None, a, None, "{}") == ["The first build."]
    assert builds.changes(a, b, "{1}", "{2}") == [
        "Region (app.ipynb @cell1) changed.",
        "app.ipynb @cell3 added.",
        "app.ipynb @cell2 taken off.",
        "The layout changed.",
    ]
    assert builds.changes(a, a, "{}", "{}") == ["Nothing changed."]
    assert builds.read_cells(builds.cells_text(b)) == sorted(b, key=lambda c: (c.document, c.cell))
    assert builds.next_number(["1", "2", "10", "x"]) == 11
    assert builds.trimmed(["1", "2", "3", "4"], 2) == ["2", "1"]


def test_compare_and_restore() -> None:
    left = {"app.py": "a\n", "app_pages/p.py": "x = 1\n", "build.json": "{}", "gone.py": "g"}
    right = {"app.py": "a\n", "app_pages/p.py": "x = 2\ny = 3\n", "build.json": "{1}", "new.py": "n"}
    found = {f["file"]: f for f in builds.compare(left, right)}
    assert [f["file"] for f in builds.compare(left, right)] == [
        "app_pages/p.py",
        "new.py",
        "gone.py",
        "app.py",
    ]
    assert (found["app_pages/p.py"]["added"], found["app_pages/p.py"]["removed"]) == (2, 1)
    assert "build.json" not in found
    kept = [builds.CellCode("/w/app.ipynb", 1, "code", None, "x = 1")]
    plans = builds.restore_plans(kept, {("/w/app.ipynb", 1): "x = 22"})
    assert plans[0]["edits"] == [{"start": 0, "end": 6, "text": "x = 1"}]
    assert builds.restore_plans(kept, {("/w/app.ipynb", 1): "x = 1"}) == []


# ===== over HTTP, the process stood in for =====

FILTER = '# Region\nregion = st.selectbox("Region", ["East", "West"], key="region_pick")'
TABLE = "# Orders\nst.dataframe(orders[orders['region'] == region])"


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, FakeRunner]]:
    with make_client(tmp_path) as client:
        runner = FakeRunner()
        client.app.state.ctx.streamlit._runner = runner  # type: ignore[attr-defined]
        client.app.state.ctx.launches._runner = runner  # type: ignore[attr-defined]
        assert push(client, "orders", ORDERS).status_code == 200
        yield client, runner


def _app(client: TestClient, folder: Path, filter_code: str = FILTER) -> tuple[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    notebook = folder / "app.ipynb"
    cells = [notebooks.Cell("code", filter_code, name="Region"), notebooks.Cell("code", TABLE, name="Orders")]
    notebook.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    path = folder / "sales.stapp.json"
    blocks = [
        {"document": str(notebook), "cell": 1, "row": 1},
        {"document": str(notebook), "cell": 2, "row": 2},
    ]
    path.write_text(
        cells_rules.write_app(cells_rules.read_pages([{"name": "Overview", "blocks": blocks}])),
        encoding="utf-8",
    )
    body = {"canvas": True, "window": "w1", "path": str(path)}
    app = _ok(client.post("/streamlit/apps", headers=AUTH, json=body))["app"]
    return app, notebook


def test_launch_makes_a_build_a_second_says_what_changed_and_compare_shows_it(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, runner = served
    project = tmp_path / "shop"
    app, notebook = _app(client, project)
    base = f"/streamlit/apps/{app}"
    first = _ok(client.post(f"{base}/launch", headers=AUTH, json={}))
    assert first["build"] == 1 and first["running"] and first["title"] == "sales · build 1"
    assert first["address"].startswith("/streamlit/launch/") and first["changed"] == ["The first build."]
    build = project / "builds" / "sales" / "1"
    names = sorted(p.relative_to(build).as_posix() for p in build.rglob("*") if p.is_file())
    assert names == [
        "README.txt",
        "app.py",
        "app.stapp.json",
        "app_pages/overview.py",
        "build.json",
        "cells.json",
        "requirements.txt",
    ]
    page = (build / "app_pages" / "overview.py").read_text(encoding="utf-8")
    assert "_sab_perf" not in page  # the build is the plain export: the run's copy is timed
    run_folder = Path(runner.started[-1][1])
    assert "_sab_perf.mark('b1')" in (run_folder / "app_pages" / "overview.py").read_text(encoding="utf-8")
    assert (run_folder / "sab_perf.py").is_file() and (run_folder / "data" / "orders.parquet").is_file()
    assert not list(build.rglob("*.parquet"))  # never rows in a build
    data = json.loads((build / "build.json").read_text(encoding="utf-8"))
    assert data["result"] == "started" and data["number"] == 1
    # A cell changes; Launch again: build 2, what changed in words, the old run replaced.
    notebook.write_text(
        notebooks.write_notebook(
            [
                notebooks.Cell("code", FILTER.replace('"West"]', '"West", "North"]'), name="Region"),
                notebooks.Cell("code", TABLE, name="Orders"),
            ]
        ),
        encoding="utf-8",
    )
    second = _ok(client.post(f"{base}/launch", headers=AUTH, json={}))
    assert second["build"] == 2 and second["changed"] == ["Region (app.ipynb @cell1) changed."]
    assert not runner.processes[0].alive() and runner.processes[1].alive()
    listed = _ok(client.get(f"{base}/builds", headers=AUTH))
    assert [b["number"] for b in listed["builds"]] == [2, 1] and listed["running"] == 2
    compared = _ok(client.get(f"{base}/builds/compare", headers=AUTH, params={"a": 1, "b": 2}))
    changed = [f for f in compared["files"] if f["status"] == "changed"]
    assert {f["file"] for f in changed} >= {"app_pages/overview.py", "cells.json"}
    assert '"North"' in next(f for f in changed if f["file"] == "app_pages/overview.py")["after"]
    # Restore build 1: a plan for the cell that differs now, sent to the window that holds the app.
    restored = _ok(client.post(f"{base}/builds/1/restore", headers=AUTH))
    assert restored["cells"] == [{"document": str(notebook), "cell": 1}]
    # Stop.
    assert _ok(client.delete(f"{base}/launch", headers=AUTH))["running"] is False
    assert not run_folder.exists()


def test_the_analyzer_records_only_while_attached_and_says_the_big_table(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, runner = served
    app, _ = _app(client, tmp_path / "shop")
    base = f"/streamlit/apps/{app}"
    assert client.get(f"{base}/perf", headers=AUTH).status_code == 409  # not launched
    launched = _ok(client.post(f"{base}/launch", headers=AUTH, json={}))
    run_folder = Path(runner.started[-1][1])
    launches = client.app.state.ctx.launches  # type: ignore[attr-defined]
    key = launched["address"].split("/")[3]
    big = b"\x2a\x04\x12\x02\x00\x03" + _bin("dataframe")  # never mind: read as a delta of some size
    # Not attached: nothing is kept, and the page's switch is off.
    launches.tap(key, "down", _bin("dataframe"))
    assert not (run_folder / "sab_perf.on").exists()
    _ok(client.post(f"{base}/perf", headers=AUTH, json={}))
    assert (run_folder / "sab_perf.on").is_file()
    frame = perf.Message("down", "delta", 2_400_000, "dataframe", (0, 2))
    for message in (_bin("new_session"), _bin("script_finished"), _bin("rerun"), _bin("script_finished")):
        launches.tap(key, "down" if message != _bin("rerun") else "up", message)
    held = launches._running[app].recording
    held.messages.insert(1, frame)
    held.messages.insert(4, frame)
    lines = [
        _record(
            "first load", [["b1", 3.0], ["b2", 40.0]], tables=[{"block": "b2", "rows": 50000, "columns": 9}]
        ),
        _record(
            "region_pick", [["b1", 3.0], ["b2", 41.0]], tables=[{"block": "b2", "rows": 50000, "columns": 9}]
        ),
    ]
    (run_folder / "sab_perf.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
    session = _ok(client.get(f"{base}/perf", headers=AUTH))
    assert [r["trigger"] for r in session["reruns"]] == ["first load", "region_pick"]
    assert session["reruns"][1]["blocks"] == [
        {"block": "b1", "title": "Region", "ms": 3.0},
        {"block": "b2", "title": "Orders", "ms": 41.0},
    ]
    assert session["reruns"][0]["socket"]["elements"]["dataframe"]["size"] == 2_400_000
    assert (
        session["hints"][0]["words"] == "Orders: 2.4 MB each rerun: cache it, or send fewer rows or columns."
    )
    assert _ok(client.get(f"{base}/perf/hints", headers=AUTH))["hints"] == session["hints"]
    # Saved into its build: the session, no data; build.json names it.
    saved = _ok(client.post(f"{base}/perf/save", headers=AUTH))
    build = tmp_path / "shop" / "builds" / "sales" / "1"
    assert json.loads((build / "build.json").read_text(encoding="utf-8"))["sessions"] == [saved["file"]]
    again = _ok(client.get(f"{base}/builds/1/perf/{saved['file']}", headers=AUTH))
    assert again["hints"] == session["hints"]
    # Paused: the switch is off again.
    _ok(client.post(f"{base}/perf", headers=AUTH, json={"on": False}))
    assert not (run_folder / "sab_perf.on").exists()
    del big
