"""Launch, Builds and the Performance Analyzer on the widget Canvas (the owner, 2026-11-19: "think Visual
Studio"; carried over to the Canvas of widgets, 2026-11-21). The wire reader on made-up Streamlit messages
(tests/golden/perf/*.bin, written once with Streamlit's own classes); the socket's reruns and their triggers;
the hints' rules; build.json's bytes; what changed between two canvases in words; a build's widgets read back
with ast; then over HTTP with a stand-in for the Streamlit process: Launch makes a build, a second Launch says
what changed, Compare shows it (and against the canvas now), Restore puts the canvas back as one change Undo
takes back, the analyzer records only while attached and says the big table by its widget. Made-up data."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.cli.commands import CommandError
from swissarmybench_streamlit.domain import builds, canvas_build, perf
from swissarmybench_streamlit.domain import canvas_layouts as model
from tests.conftest import AUTH, make_client, push
from tests.streamlit_helpers import FakeRunner

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
    assert [r.trigger for r in reruns] == ["first load", "rerun", "zoom"]
    # The first ask holds every widget's value (which changed is not known); then zoom changed.
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


def test_build_json_is_byte_stable_and_names_its_sessions() -> None:
    one = builds.build_json(3, "2026-11-19T10:00:00Z", "sales", "{}", ["The first build."], "started", 812.4)
    assert one == builds.build_json(
        3, "2026-11-19T10:00:00Z", "sales", "{}", ["The first build."], "started", 812.4
    )
    data = json.loads(one)
    assert list(data) == sorted(data) and one.endswith("}\n") and data["first_load_ms"] == 812
    saved = builds.with_session(one, "perf-20261119T100500Z.json")
    assert json.loads(saved)["sessions"] == ["perf-20261119T100500Z.json"]
    assert builds.with_session(saved, "perf-20261119T100500Z.json") == saved
    assert builds.next_number(["1", "2", "10", "x"]) == 11
    assert builds.trimmed(["1", "2", "3", "4"], 2) == ["2", "1"]


def _canvas(*widgets: tuple[str, str, dict[str, Any]], x: float = 0.0) -> str:
    canvas = model.new_canvas("Sales")
    place = {"x": x, "y": 0, "w": 0.5, "h": 100}
    canvas["pages"][0]["children"] = [
        {
            "id": wid,
            "kind": "widget",
            "widget": name,
            "show": "both",
            "values": values,
            "at": {"desktop": place, "phone": place},
        }
        for wid, name, values in widgets
    ]
    return model.write(canvas)


def test_what_changed_between_two_canvases_in_words() -> None:
    first = _canvas(("w1", "metric", {"label": "Orders"}), ("w2", "data_table", {}))
    assert builds.canvas_changes(None, first) == ["The first build."]
    assert builds.canvas_changes(first, first, "", "") == ["Nothing changed."]
    second = _canvas(("w1", "metric", {"label": "Revenue"}), ("w3", "bar_chart", {}), x=0.25)
    assert builds.canvas_changes(first, second) == [
        "metric (w1): label changed.",
        "bar_chart (w3) added on Page 1.",
        "data_table (w2) taken off Page 1.",
        "The layout changed.",
    ]
    old = canvas_build.widgets_module({"metric": canvas_build.Built("st.metric('A', 1)\n", ())})
    new = canvas_build.widgets_module({"metric": canvas_build.Built("st.metric('B', 2)\n", ())})
    assert builds.widget_code(old) == {"metric": "st.metric('A', 1)\n"}
    assert builds.canvas_changes(first, first, old, new) == ["The widget metric's code changed."]
    # The build before an app notebook's (before widgets): said, never a crash.
    assert builds.canvas_changes('{"pages": []}', first)[0].startswith("The first build on the Canvas")
    assert builds.widget_code("this is not python (") == {}


def test_compare_file_by_file() -> None:
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


def test_the_built_page_times_each_widget_only_beside_the_analyzer() -> None:
    """One builder: the page calls sab.begin and sab.finish, and render times each instance through sab_perf
    when (and only when) it is beside the pages: an export has no sab_perf, so nothing is timed there."""
    canvas = json.loads(_canvas(("w1", "metric", {})))
    files = canvas_build.build(canvas, {"metric": canvas_build.Built("x = 1\n", ())})
    page = files["app_pages/page_1.py"]
    assert 'sab.begin("Page 1")' in page and page.rstrip().endswith("sab.finish()")
    assert (
        "import sab_perf as _perf" in files["sab_canvas.py"]
        and "_perf.mark(instance)" in files["sab_canvas.py"]
    )
    assert canvas_build.compiles(files) == []


# ===== over HTTP, the process stood in for =====

ORDERS = pa.table({"month": ["2026-01", "2026-02"], "region": ["North", "South"], "revenue": [120.5, 98.0]})


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, FakeRunner, Path]]:
    with make_client(tmp_path) as client:
        runner = FakeRunner()
        client.app.state.ctx.extension["streamlit"].live_runs.use_runner(runner)  # type: ignore[attr-defined]
        assert push(client, "orders", ORDERS).status_code == 200
        project = tmp_path / "shop"
        project.mkdir()
        yield client, runner, project


def ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return dict(response.json())


def _open(client: TestClient, project: Path) -> str:
    made = ok(
        client.post("/streamlit/canvases", headers=AUTH, json={"name": "Sales", "folder": str(project)})
    )
    canvas = str(made["canvas"])

    def send(kind: str, **body: Any) -> dict[str, Any]:
        return ok(
            client.post(f"/streamlit/canvases/{canvas}/command", headers=AUTH, json={"kind": kind, **body})
        )

    send("add_container", x=0, y=0, w=600, h=300)
    send("insert_widget", parent="c1", widget="metric", values={"label": "Orders"})
    send("insert_widget", parent="c1", widget="data_table", values={"table_name": "orders"})
    return canvas


def test_launch_makes_builds_compare_shows_them_and_restore_puts_the_canvas_back(
    served: tuple[TestClient, FakeRunner, Path],
) -> None:
    client, runner, project = served
    canvas = _open(client, project)
    base = f"/streamlit/canvases/{canvas}"
    first = ok(client.post(f"{base}/launch", headers=AUTH, json={}))
    assert first["build"] == 1 and first["changed"] == ["The first build."] and first["running"] is True
    folder = project / "builds" / "sales"
    assert (folder / "1" / "canvas.json").is_file() and not (folder / "1" / "sab_perf.py").exists()
    run = Path(runner.started[-1][1])
    assert (run / "sab_perf.py").is_file() and not (run / "sab_perf.on").exists()  # beside the run only
    assert "Sales · build 1" in (run / "app.py").read_text(encoding="utf-8")
    widget = next(
        n for _, n in model.walk(ok(client.get(base, headers=AUTH))["model"]) if n.get("widget") == "metric"
    )
    ok(
        client.post(
            f"{base}/command",
            headers=AUTH,
            json={"kind": "set_values", "id": widget["id"], "values": {"label": "Revenue"}},
        )
    )
    second = ok(client.post(f"{base}/launch", headers=AUTH, json={}))
    assert second["build"] == 2 and second["changed"] == [f"metric ({widget['id']}): label changed."]
    listed = ok(client.get(f"{base}/builds", headers=AUTH))
    assert [b["number"] for b in listed["builds"]] == [2, 1] and listed["running"] == 2
    assert listed["builds"][0]["result"] == "started"
    compared = ok(client.get(f"{base}/builds/compare?a=1&b=2", headers=AUTH))
    changed = {f["file"]: f for f in compared["files"] if f["status"] == "changed"}
    assert set(changed) == {"app.py", "canvas.json", "app_pages/page_1.py"} or "canvas.json" in changed
    assert '"Orders"' in changed["canvas.json"]["before"] and '"Revenue"' in changed["canvas.json"]["after"]
    now = ok(client.get(f"{base}/builds/compare?a=2", headers=AUTH))
    assert now["b"] == "now" and all(f["status"] == "same" for f in now["files"] if f["file"] != "app.py")
    files = ok(client.get(f"{base}/builds/1", headers=AUTH))["files"]
    assert {"app.py", "canvas.json", "sab_widgets.py", "build.json"} <= set(files)
    # Restore build 1: one change, Undo takes it back.
    restored = ok(client.post(f"{base}/builds/1/restore", headers=AUTH, json={}))
    assert restored["restored"] == 1
    assert model.find(restored["model"], widget["id"])[2]["values"]["label"] == "Orders"
    undone = ok(client.post(f"{base}/undo", headers=AUTH))
    assert model.find(undone["model"], widget["id"])[2]["values"]["label"] == "Revenue"
    # Relaunch an old build: its own code.
    again = ok(client.post(f"{base}/builds/1/launch", headers=AUTH, json={}))
    assert again["build"] == 1 and again["running"] is True
    assert ok(client.delete(f"{base}/launch", headers=AUTH))["running"] is False
    assert ok(client.get(f"{base}/launch", headers=AUTH))["running"] is False
    assert client.get(f"{base}/builds/9", headers=AUTH).status_code == 404
    assert client.get(f"{base}/builds/x", headers=AUTH).status_code == 400


def test_an_old_app_notebooks_build_is_said_never_restored(
    served: tuple[TestClient, FakeRunner, Path],
) -> None:
    client, _, project = served
    canvas = _open(client, project)
    old = project / "builds" / "sales" / "1"
    old.mkdir(parents=True)
    (old / "app.py").write_text("import streamlit as st\n", encoding="utf-8")
    (old / "build.json").write_text(
        builds.build_json(1, "2026-11-19T10:00:00Z", "sales", "{}", [], "started", 1), encoding="utf-8"
    )
    refused = client.post(f"/streamlit/canvases/{canvas}/builds/1/restore", headers=AUTH, json={})
    assert refused.status_code == 403 and "before widgets" in refused.text
    second = ok(client.post(f"/streamlit/canvases/{canvas}/launch", headers=AUTH, json={}))
    assert second["build"] == 2


def test_the_analyzer_records_only_while_attached_and_names_the_widget(
    served: tuple[TestClient, FakeRunner, Path],
) -> None:
    client, runner, project = served
    canvas = _open(client, project)
    base = f"/streamlit/canvases/{canvas}"
    assert client.get(f"{base}/perf", headers=AUTH).status_code == 409  # not launched
    launched = ok(client.post(f"{base}/launch", headers=AUTH, json={"analyzer": True}))
    assert launched["analyzer"] is True
    run = Path(runner.started[-1][1])
    assert (run / "sab_perf.on").is_file()  # F5 with the analyzer: recording from the first load
    launches = client.app.state.ctx.extension["streamlit"].launches  # type: ignore[attr-defined]
    key = launched["url"].rstrip("/").rsplit("/", 1)[-1]
    tables = [n for _, n in model.walk(ok(client.get(base, headers=AUTH))["model"]) if n["kind"] == "widget"]
    table = next(n["id"] for n in tables if n["widget"] == "data_table")
    launches.tap(key, "down", _bin("new_session"))
    launches.tap("launch-cvnotone-secret", "down", _bin("new_session"))  # another key: nothing kept
    held = launches.recording(canvas)
    assert len(held.messages) == 1
    frame = perf.Message("down", "delta", 2_400_000, "dataframe", (0, 2))
    held.messages += [frame, perf.read_forward(_bin("script_finished")), perf.read_back(_bin("rerun")), frame]
    lines = [
        _record("first load", [[table, 40.0]], tables=[{"block": table, "rows": 50000, "columns": 9}]),
        _record("zoom", [[table, 41.0]], tables=[{"block": table, "rows": 50000, "columns": 9}]),
    ]
    (run / "sab_perf.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
    session = ok(client.get(f"{base}/perf", headers=AUTH))
    assert [r["trigger"] for r in session["reruns"]] == ["first load", "rerun"]
    assert session["reruns"][1]["blocks"] == [{"block": table, "title": f"data_table ({table})", "ms": 41.0}]
    assert session["hints"][0]["words"] == (
        f"data_table ({table}): 2.4 MB each rerun: cache it, or send fewer rows or columns."
    )
    assert ok(client.get(f"{base}/perf/hints", headers=AUTH))["hints"] == session["hints"]
    saved = ok(client.post(f"{base}/perf/save", headers=AUTH))
    build = project / "builds" / "sales" / "1"
    assert json.loads((build / "build.json").read_text(encoding="utf-8"))["sessions"] == [saved["file"]]
    again = ok(client.get(f"{base}/builds/1/perf/{saved['file']}", headers=AUTH))
    assert again["hints"] == session["hints"]
    ok(client.post(f"{base}/perf", headers=AUTH, json={"on": False}))
    assert not (run / "sab_perf.on").exists()
    ok(client.delete(f"{base}/perf", headers=AUTH))
    assert launches.recording(canvas) is None


def test_the_folded_canvas_commands_answer_by_their_old_names() -> None:
    """The tool list's budget (2026-11-21): builds and the analyzer are one tool each, by an action, and four
    canvas tools were folded into others; the old names still answer, one release."""
    from swissarmybench.cli import commands

    assert commands.current_name("canvas_list") == "canvas_open"
    assert commands.current_name("canvas_show") == "canvas_move"
    assert commands.current_name("canvas_stop") == "canvas_play"
    assert commands.OLD_ARGS[("canvas_play", "run")] == "stop"
    assert "canvas_undo redo=true" in commands.GONE_NAMES["canvas_redo"]
    for name in ("canvas_builds", "canvas_perf", "app_launch"):
        assert name in commands.REGISTRY
    with pytest.raises(CommandError, match="action is one of"):
        commands.execute_result("canvas_builds", {"canvas": "cv1", "action": "everything"})
