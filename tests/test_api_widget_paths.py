"""The API widgets' path fields (the owner approved "Path fields for API widgets", 2026-11-21): one box per
{name} in the chosen endpoint's path (the path_values mask, `# path values of endpoint`), each a value, a
variable or a page value, checked against the endpoint picked; and a canvas app's Export naming the API
variables to set (SAB_API_URL, SAB_API_KEY, SAB_API_BASE) in its README and its warning list. Made-up data
only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench_streamlit.domain import widget_properties as props
from tests.conftest import AUTH, make_client
from tests.streamlit_helpers import FakeRunner
from tests.test_api_widgets import API_WIDGETS, PYTHON, _run, _widget, needs_streamlit

DOLLAR = chr(36)  # a variable's reference is written as DOLLAR + "{NAME}"


def _path_prop() -> props.Property:
    return next(p for p in _widget("api_table")[1].properties if p.name == "path_values")


def test_every_api_widget_has_path_boxes_of_its_endpoint() -> None:
    for name in API_WIDGETS:
        prop = next(p for p in _widget(name)[1].properties if p.name == "path_values")
        assert prop.type == "path_values" and prop.mask == "path_values" and prop.of == "endpoint"
    assert props.path_names("GET /orders/{region}/{order_id}") == ["region", "order_id"]
    assert props.path_names("GET /orders") == [] and props.path_names("") == []


def test_a_path_box_takes_a_value_a_variable_or_a_page_value() -> None:
    prop = _path_prop()
    ctx = props.Context(values={"endpoint": "GET /orders/{region}"}, variables={"REGION"})
    for good in (
        {"region": "West"},
        {"region": 7},
        {"region": DOLLAR + "{REGION}"},
        {"region": "{{ area }}"},
        {},
    ):
        props.check(prop, good, ctx)
    with pytest.raises(props.PropertyError, match=r"has no \{order_id\} in its path"):
        props.check(prop, {"order_id": 1}, ctx)
    with pytest.raises(props.PropertyError, match="is not set on this computer"):
        props.check(prop, {"region": DOLLAR + "{NOPE}"}, ctx)
    with pytest.raises(props.PropertyError, match="is not a page value"):
        props.check(prop, {"region": "{{ two words }}"}, ctx)
    with pytest.raises(props.PropertyError, match="one value"):
        props.check(prop, {"region": ["West"]}, ctx)
    # The endpoint not picked yet: no name is refused.
    props.check(prop, {"anything": "x"}, props.Context())


@needs_streamlit
def test_a_page_value_not_set_says_which_box_and_a_variable_fills_its_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert PYTHON is not None
    monkeypatch.setenv("SAB_TEST_REGION", "West")
    monkeypatch.delenv("SAB_API_URL", raising=False)
    unset, filled = _run(
        tmp_path,
        [
            ("api_table", {"endpoint": "GET /orders/{region}", "path_values": {"region": "{{ area }}"}}),
            (
                "api_table",
                {"endpoint": "GET /orders/{region}", "path_values": {"region": DOLLAR + "{SAB_TEST_REGION}"}},
            ),
        ],
    )
    assert not unset["exceptions"] and any("Give region in Properties" in s for s in unset["said"])
    # Its variable filled the box: the next thing it needs is the API itself.
    assert not filled["exceptions"] and not filled["said"]
    assert any("Run the local sandbox API" in i for i in filled["infos"])


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    with make_client(tmp_path) as client:
        client.app.state.ctx.live_runs._runner = FakeRunner()  # type: ignore[attr-defined]
        project = tmp_path / "shop"
        project.mkdir()
        yield client, project


def ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return dict(response.json())


def _canvas_with(client: TestClient, project: Path, widget: str, values: dict[str, Any]) -> str:
    canvas = ok(
        client.post("/streamlit/canvases", headers=AUTH, json={"name": "Shop", "folder": str(project)})
    )["canvas"]
    path = f"/streamlit/canvases/{canvas}/command"
    ok(client.post(path, headers=AUTH, json={"kind": "add_container", "x": 0, "y": 0, "w": 600, "h": 300}))
    ok(
        client.post(
            path,
            headers=AUTH,
            json={"kind": "insert_widget", "parent": "c1", "widget": widget, "values": values},
        )
    )
    return str(canvas)


def test_an_export_that_calls_the_api_names_its_variables(
    served: tuple[TestClient, Path], tmp_path: Path
) -> None:
    client, project = served
    canvas = _canvas_with(client, project, "api_table", {"endpoint": "GET /orders"})
    out = tmp_path / "out"
    done = ok(client.post(f"/streamlit/canvases/{canvas}/export", headers=AUTH, json={"folder": str(out)}))
    assert done["variables"] == ["SAB_API_URL", "SAB_API_KEY", "SAB_API_BASE"]
    assert [w.split(" where")[0] for w in done["warnings"]] == [f"Set {v}" for v in done["variables"]]
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "## Variables to set where it runs" in readme and all(
        f"`{v}`" in readme for v in done["variables"]
    )
    # Every built app carries api_adapter.py beside its pages, and the actions it calls (types only).
    assert (out / "api_adapter.py").read_text(encoding="utf-8").startswith('"""api_adapter:')
    kept = json.loads((out / "sab_actions.json").read_text(encoding="utf-8"))
    assert kept == {}  # this folder has no API.py: the call says so where it runs


def test_an_export_that_does_not_call_it_names_none(served: tuple[TestClient, Path], tmp_path: Path) -> None:
    client, project = served
    canvas = _canvas_with(client, project, "metric", {"label": "Orders"})
    out = tmp_path / "plain"
    done = ok(client.post(f"/streamlit/canvases/{canvas}/export", headers=AUTH, json={"folder": str(out)}))
    assert done["variables"] == [] and done["warnings"] == [] and not (out / "README.md").exists()
