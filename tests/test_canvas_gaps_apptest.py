"""The canvas's gaps run for real, headless with Streamlit's AppTest through the one page builder (Play,
Launch and Export run the same pages): a widget Hidden in the app still runs and its Out reaches a widget on
another page (an app-wide value kept in the session across pages), who is viewing (this computer's user in
Play, "unknown" when nothing says), and a File Out read by excel_upload. Skipped without a Python with
Streamlit (SWISSARMYBENCH_STREAMLIT_PYTHON). Made-up data only."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from swissarmybench_streamlit.domain import canvas_build as build
from swissarmybench_streamlit.domain import canvas_layouts as model
from swissarmybench_streamlit.domain import widgets as rules
from swissarmybench_streamlit.domain.canvas_model import WidgetFacts
from tests.test_widgets_apptest import PREBUILT, PYTHON, needs_streamlit

RUNNER = r"""
import json, os, sys
folder = sys.argv[1]
sys.path.insert(0, folder)
os.chdir(folder)
from streamlit.testing.v1 import AppTest
plan = json.load(open("plan.json", encoding="utf-8"))
at = AppTest.from_file("app.py", default_timeout=90)
out = []
for step in plan["steps"]:
    if step.get("page"):
        at.switch_page(step["page"])
    at.run()
    out.append({
        "markdown": [str(m.value) for m in at.markdown],
        "caption": [str(c.value) for c in at.caption],
        "exceptions": [str(e.value)[:800] for e in at.exception],
        "errors": [str(e.value)[:800] for e in at.error],
        "warnings": [str(w.value)[:400] for w in at.warning],
    })
print("SAB-RUN " + json.dumps(out))
"""

PRODUCER = """import streamlit as st
from sab_canvas import Out

# The region picked
region: Out[str] = None
region = "West"
st.markdown("producer ran")
"""

READER = """import streamlit as st
from sab_canvas import In

region: In[str] = "All"
viewer: In[str] = "nobody"
st.markdown(f"region={region} viewer={viewer}")
"""

FILE_MAKER = """import streamlit as st
from sab_canvas import File, Out

# A made-up export, as an upload would give it
file: Out[File] = None
file = File("orders.csv", b"order_id,amount\\n1,2.5\\n2,3\\n3,4\\n", "text/csv")
"""


def _run(folder: Path, files: dict[str, str], steps: list[dict[str, Any]], env: dict[str, str]) -> list[Any]:
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    (folder / "plan.json").write_text(json.dumps({"steps": steps}), encoding="utf-8")
    assert PYTHON is not None
    environ = {k: v for k, v in os.environ.items() if k not in ("SAB_LOCAL_VIEWER", "WEBSITE_SITE_NAME")}
    done = subprocess.run(  # noqa: S603 (this machine's Python with Streamlit, the test's own runner)
        [PYTHON, "-I", "-c", RUNNER, str(folder)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=folder,
        check=False,
        env=environ | env,
    )
    line = next((x for x in reversed(done.stdout.splitlines()) if x.startswith("SAB-RUN ")), None)
    assert line, done.stdout[-2000:] + done.stderr[-2000:]
    found: list[Any] = json.loads(line[len("SAB-RUN ") :])
    return found


def _app() -> tuple[dict[str, Any], dict[str, build.Built]]:
    def prebuilt(name: str) -> build.Built:
        text = (PREBUILT / f"{name}.widget.py").read_text(encoding="utf-8")
        return build.made(rules.read_widget(text, prebuilt=True).code)

    built = {
        "producer": build.made(PRODUCER),
        "reader": build.made(READER),
        "file_maker": build.made(FILE_MAKER),
        "excel_upload": prebuilt("excel_upload"),
    }
    facts = {n: WidgetFacts((4, 2), (1, 1)) for n in built}
    canvas = model.new_canvas("Shop")
    canvas["pages"][0]["name"] = "Load"
    canvas["pages"].append({"id": "p2", "name": "Reports", "children": []})
    steps: list[tuple[str, dict[str, Any]]] = [
        ("add_container", {"page": "p1", "x": 0, "y": 0, "w": 1200, "h": 700}),
        ("insert_widget", {"parent": "c1", "widget": "producer", "x": 8, "y": 8}),
        ("insert_widget", {"parent": "c1", "widget": "file_maker", "x": 8, "y": 200}),
        ("insert_widget", {"parent": "c1", "widget": "excel_upload", "x": 440, "y": 8}),
        ("add_container", {"page": "p2", "x": 0, "y": 0, "w": 600, "h": 300}),
        ("insert_widget", {"page": "p2", "parent": "c2", "widget": "reader"}),
        ("hide", {"id": "w1", "hidden": True}),
        ("hide", {"id": "w2", "hidden": True}),
        ("wire", {}),
    ]
    for kind, body in steps:
        if kind == "wire":
            from swissarmybench_streamlit.domain import canvas_wiring as wiring

            canvas = wiring.set_wire(canvas, {"id": "w4", "port": "region", "wire": {"out": "w1.region"}})
            continue
        canvas, _ = model.apply(canvas, kind, body, facts)
    return canvas, built


@needs_streamlit
def test_hidden_cross_page_viewer_and_a_file_run_for_real(tmp_path: Path) -> None:
    canvas, built = _app()
    files = build.build(canvas, built)
    assert not build.compiles(files)
    load_page = files["app_pages/load.py"]
    assert "sab.render('producer'" in load_page  # hidden, it still runs
    steps = [{}, {"page": "app_pages/reports.py"}]
    played = _run(tmp_path / "played", files, steps, {"SAB_LOCAL_VIEWER": "ada.ashdown"})
    load, reports = played
    assert not load["exceptions"] and not load["errors"], load
    assert "producer ran" in load["markdown"]  # the hidden widget ran
    assert any(c.startswith("orders.csv, from the page's file") for c in load["caption"]), load["caption"]
    assert "3 rows, 2 columns" in load["caption"]  # excel_upload read the File Out, not its sample
    assert not any("Made-up sample" in c for c in load["caption"])
    assert not reports["exceptions"], reports
    assert "region=West viewer=ada.ashdown" in reports["markdown"]  # another page's Out, the viewer
    # Nothing says who views (an export on a host with no sign-in, a shared run): "unknown", never invented
    unknown = _run(tmp_path / "exported", files, steps, {})
    assert "region=West viewer=unknown" in unknown[1]["markdown"]
    # App Service's headers are trusted only on App Service: there, with none sent, still unknown
    hosted = _run(tmp_path / "hosted", files, steps, {"WEBSITE_SITE_NAME": "made-up-app"})
    assert "region=West viewer=unknown" in hosted[1]["markdown"]
    # Reports opened first: the Load page has not run in this session, the In takes its starting value
    first = _run(tmp_path / "first", files, [{"page": "app_pages/reports.py"}], {})
    assert "region=All viewer=unknown" in first[0]["markdown"]
