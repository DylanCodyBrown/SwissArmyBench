"""The API widgets (the Streamlit extension's prebuilt api_table, api_form, api_button, api_metric) against a
running
local sandbox API: built by the page builder Play uses, run headless with Streamlit's AppTest, their answers
the
endpoint's rows. The endpoint property is a mask of its own: a value is one of API.py's endpoints, checked.
With
no API running, each says how to start it. Streamlit is never the app's dependency: the runs need the Python
named
by SWISSARMYBENCH_STREAMLIT_PYTHON (else skipped). Made-up data only."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.server.app import create_app
from swissarmybench.settings import Settings
from swissarmybench_streamlit.domain import canvas_build as build
from swissarmybench_streamlit.domain import widget_properties as props
from swissarmybench_streamlit.domain import widgets as rules
from tests.conftest import TOKEN
from tests.live_server import running
from tests.test_local_api import API_PY, ORDERS, _ask

PREBUILT = Path(__file__).resolve().parents[1] / "extensions/streamlit/src/swissarmybench_streamlit/widgets"
API_WIDGETS = ("api_table", "api_form", "api_button", "api_metric")


def _python() -> str | None:
    for python in (os.environ.get("SWISSARMYBENCH_STREAMLIT_PYTHON"), sys.executable):
        if (
            python
            and subprocess.run(  # noqa: S603 (this machine's Python, one fixed question)
                [python, "-c", "import streamlit"], capture_output=True, check=False
            ).returncode
            == 0
        ):
            return python
    return None


PYTHON = _python()
needs_streamlit = pytest.mark.skipif(PYTHON is None, reason="no Python with Streamlit here")

RUNNER = textwrap.dedent(
    r"""
    import json, os, sys
    folder = sys.argv[1]
    sys.path.insert(0, folder)
    os.chdir(folder)
    from streamlit.testing.v1 import AppTest
    out = []
    for page in json.load(open("check.json"))["pages"]:
        at = AppTest.from_file(os.path.join(folder, page), default_timeout=60)
        at.run()
        frames = [f.value.to_dict(orient="records") for f in at.dataframe]
        out.append({
            "page": page,
            "exceptions": [str(e.value)[:500] for e in at.exception],
            "infos": [str(i.value) for i in at.info] + [str(c.value) for c in at.caption],
            "frames": frames,
            "metrics": [m.value for m in at.metric],
            "said": [str(e.value)[:500] for e in at.error] + [str(w.value)[:500] for w in at.warning],
        })
    print("SAB-RUN " + json.dumps(out, default=str))
    """
)


def _widget(name: str) -> tuple[rules.Widget, build.Built]:
    widget = rules.read_widget((PREBUILT / f"{name}.widget.py").read_text(encoding="utf-8"), prebuilt=True)
    return widget, build.Built(widget.code, tuple(props.detect(widget.code)))


def _run(folder: Path, uses: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """One page per (widget, its values), built as Play builds it, run headless."""
    from swissarmybench_streamlit.domain import canvas_model as model

    canvas = model.new_canvas("API widgets")
    canvas["pages"] = []
    built: dict[str, build.Built] = {}
    for at, (name, values) in enumerate(uses, start=1):
        widget, made = _widget(name)
        built[name] = made
        page = build.one_widget(name, made, values, widget.size)["pages"][0]
        page["id"] = f"p{at}"
        page["name"] = f"Page {at}"
        canvas["pages"].append(page)
    files = build.build(canvas, built)
    pages = sorted(
        (p for p in files if p.startswith("app_pages/")), key=lambda p: int(re.sub(r"\D", "", p) or 0)
    )
    for path, text in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text(text, encoding="utf-8")
    (folder / "check.json").write_text(json.dumps({"pages": pages}), encoding="utf-8")
    assert PYTHON is not None
    done = subprocess.run(  # noqa: S603
        [PYTHON, "-I", "-c", RUNNER, str(folder)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=folder,
        check=False,
    )
    line = next((x for x in reversed(done.stdout.splitlines()) if x.startswith("SAB-RUN ")), None)
    assert line, done.stdout[-2000:] + done.stderr[-2000:]
    found: list[dict[str, Any]] = json.loads(line[len("SAB-RUN ") :])
    return found


def test_the_endpoint_mask_is_detected_and_checked() -> None:
    for name in API_WIDGETS:
        _, made = _widget(name)
        endpoint = next(p for p in made.properties if p.name == "endpoint")
        assert endpoint.type == "endpoint" and endpoint.mask == "endpoint"
    prop = next(p for p in _widget("api_table")[1].properties if p.name == "endpoint")
    props.check(prop, "GET /orders/{region}", props.Context(endpoints={"GET /orders/{region}"}))
    with pytest.raises(props.PropertyError, match=r"like GET /orders"):
        props.check(prop, "orders", props.Context())
    with pytest.raises(props.PropertyError, match=r"API\.py has no endpoint GET /gone"):
        props.check(prop, "GET /gone", props.Context(endpoints={"GET /orders"}))


@pytest.fixture
def live(tmp_path: Path) -> Iterator[int]:
    settings = Settings(
        state_dir=tmp_path / "state", export_dir=tmp_path / "exports", auto_load_catalogs=False,
        projects_dir=tmp_path / "projects", workbench_dir=tmp_path / "wb",
    )  # fmt: skip
    with running(lambda port: create_app(port, TOKEN, settings)) as (port, _server):
        yield port


@needs_streamlit
def test_the_api_widgets_show_the_running_apis_answers(live: int, tmp_path: Path) -> None:
    port = live
    folder = tmp_path / "shop"
    _ask(port, "POST", "/project/new", {"path": str(folder)})
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    _ask(port, "POST", "/sandbox/tables", {"from": "file", "path": str(csv)})
    (folder / "API.py").write_text(API_PY, encoding="utf-8")
    # Not running yet: each widget says how to start it.
    quiet = _run(
        tmp_path / "before",
        [("api_table", {"endpoint": "GET /orders/{region}", "path_values": {"region": "West"}})],
    )
    assert not quiet[0]["exceptions"] and any("Run the local sandbox API" in i for i in quiet[0]["infos"])
    assert _ask(port, "POST", "/local-api/run", {})["running"]
    try:
        # The picker's choices: API.py's endpoints.
        assert "GET /orders/{region}" in _ask(port, "GET", "/streamlit/widgets/context")["endpoints"]
        found = _run(
            tmp_path / "after",
            [
                (
                    "api_table",
                    {"endpoint": "GET /orders/{region}", "path_values": {"region": "West"}, "page_size": 5},
                ),
                (
                    "api_metric",
                    {
                        "endpoint": "GET /orders/one/{order_id}",
                        "path_values": {"order_id": 2},
                        "field": "amount",
                        "label": "Amount",
                    },
                ),
                (
                    "api_metric",
                    {
                        "endpoint": "GET /orders/{region}",
                        "path_values": {"region": "West"},
                        "label": "Orders",
                    },
                ),
                ("api_button", {"endpoint": "GET /orders/one/{order_id}", "path_values": {"order_id": 1}}),
                ("api_form", {"endpoint": "POST /orders"}),
            ],
        )
        assert not [p for p in found if p["exceptions"]], found
        assert found[0]["frames"], found
        assert [r["order_id"] for r in found[0]["frames"][0]] == [1, 3]
        assert found[1]["metrics"] == ["7.25"] and found[2]["metrics"] == ["2"]
    finally:
        _ask(port, "POST", "/local-api/stop", {})
