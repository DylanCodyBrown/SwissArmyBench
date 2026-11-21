"""Every prebuilt widget, run headless with Streamlit's AppTest through the page builder Play and Export use:
each one draws without an error, on its made-up sample data. Streamlit is never the app's dependency: these
run in the Python named by SWISSARMYBENCH_STREAMLIT_PYTHON (or this one when it has Streamlit), else are
skipped."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from swissarmybench_streamlit.domain import canvas_build as build
from swissarmybench_streamlit.domain import widget_properties as props
from swissarmybench_streamlit.domain import widgets as rules
from swissarmybench_streamlit.server.live_runs import CHECK_RUNNER

PREBUILT = Path(__file__).resolve().parents[1] / "extensions/streamlit/src/swissarmybench_streamlit/widgets"


def _python() -> str | None:
    for python in (os.environ.get("SWISSARMYBENCH_STREAMLIT_PYTHON"), sys.executable):
        if not python:
            continue
        done = subprocess.run(  # noqa: S603 (this machine's Python, one fixed question)
            [python, "-c", "import streamlit, pandas, altair"], capture_output=True, check=False
        )
        if done.returncode == 0:
            return python
    return None


PYTHON = _python()
needs_streamlit = pytest.mark.skipif(
    PYTHON is None, reason="no Python with Streamlit here (set SWISSARMYBENCH_STREAMLIT_PYTHON)"
)


def run_pages(folder: Path, files: dict[str, str], pages: list[str]) -> list[dict[str, Any]]:
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    (folder / "check.json").write_text(json.dumps({"pages": pages}), encoding="utf-8")
    assert PYTHON is not None
    done = subprocess.run(  # noqa: S603
        [PYTHON, "-I", "-c", CHECK_RUNNER, str(folder)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=folder,
        check=False,
    )
    line = next((x for x in reversed(done.stdout.splitlines()) if x.startswith("SAB-CHECK ")), None)
    assert line, done.stdout[-2000:] + done.stderr[-2000:]
    found: list[dict[str, Any]] = json.loads(line[len("SAB-CHECK ") :])
    return found


@needs_streamlit
def test_every_prebuilt_widget_renders_without_an_error(tmp_path: Path) -> None:
    """One canvas page per widget (each in its container), so the one run checks them all."""
    from swissarmybench_streamlit.domain import canvas_model as model

    built: dict[str, build.Built] = {}
    canvas = model.new_canvas("All widgets")
    canvas["pages"] = []
    for at, path in enumerate(sorted(PREBUILT.glob("*.widget.py")), start=1):
        widget = rules.read_widget(path.read_text(encoding="utf-8"), prebuilt=True)
        built[widget.name] = build.Built(widget.code, tuple(props.detect(widget.code)))
        one = build.one_widget(widget.name, built[widget.name], {}, widget.size)
        page = one["pages"][0]
        page["id"] = f"p{at}"
        canvas["pages"].append(page)
    files = build.build(canvas, built)
    assert not build.compiles(files)
    pages = sorted(p for p in files if p.startswith("pages/"))
    found = run_pages(tmp_path, files, pages)
    failed = {p["page"]: (p["exceptions"], p["failed"]) for p in found if p["exceptions"] or p["failed"]}
    assert not failed, failed
    assert len(found) >= 40


@needs_streamlit
def test_a_failing_widget_shows_its_own_error_and_the_rest_of_the_page_runs(tmp_path: Path) -> None:
    from swissarmybench_streamlit.domain import canvas_model as model

    good = build.Built('import streamlit as st\n\ntext = "Still here"\n\nst.metric(text, 1)\n', ())
    good = build.Built(good.code, tuple(props.detect(good.code)))
    bad = build.Built("import streamlit as st\n\nst.write(1 / 0)\n", ())
    missing = build.Built(
        'from sab_canvas import table\n\ntable_name = "nowhere"  # table\n\ntable(table_name)\n', ()
    )
    missing = build.Built(missing.code, tuple(props.detect(missing.code)))
    canvas = model.new_canvas("Mixed")
    facts = {
        n: model.WidgetFacts((4, 1), (1, 1), frozenset(p.name for p in b.properties))
        for n, b in {"good": good, "bad": bad, "gone_table": missing}.items()
    }
    for name in ("bad", "good", "gone_table"):
        canvas, _ = model.insert_widget(canvas, {"widget": name}, facts)
    canvas["pages"][0]["children"].append(
        {
            "id": "c9",
            "kind": "container",
            "col": 0,
            "row": 9,
            "w": 4,
            "h": 1,
            "props": dict(model.CONTAINER_DEFAULT),
            "children": [
                {
                    "id": "w9",
                    "kind": "widget",
                    "widget": "deleted_one",
                    "col": 0,
                    "row": 0,
                    "w": 1,
                    "h": 1,
                    "values": {},
                }
            ],
        }
    )
    files = build.build(canvas, {"good": good, "bad": bad, "gone_table": missing})
    (page,) = run_pages(tmp_path, files, [p for p in files if p.startswith("pages/")])
    assert not page["exceptions"]
    assert any("ZeroDivisionError" in e and "(line 3)" in e for e in page["failed"])
    assert page["kinds"]["metric"] == 1
    warnings = " ".join(page["warnings"])
    assert "The table nowhere is not here" in warnings and "deleted_one is not in the library" in warnings
