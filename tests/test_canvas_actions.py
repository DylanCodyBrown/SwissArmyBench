"""The canvas calls every API through api_adapter (Plans/api-adapter.plan.md, the owner's answers after the
first build): one action picker for any API (the project's local sandbox API's endpoints as "GET /orders",
a library API's actions as "[Orders] GET /orders"), every built app carrying api_adapter.py beside its pages
with the actions it calls (sab_actions.json: definitions and learned shapes, types only) and a library API's
own client file; the prebuilt API widgets read the envelope. A library API here is the made-up orders service
(tests/api_standins.py). Every row is made up."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.server.app import create_app
from swissarmybench.settings import Settings
from swissarmybench_streamlit.domain import canvas_build as build
from swissarmybench_streamlit.domain import canvas_wiring as wiring
from swissarmybench_streamlit.domain import widget_properties as props
from swissarmybench_streamlit.domain.widget_contract import ContractError, Port
from tests.api_standins import Service
from tests.conftest import TOKEN
from tests.fake_keyring import memory_keyring
from tests.live_server import running
from tests.test_actions import add_orders, ask
from tests.test_api_widgets import PYTHON, RUNNER, _widget, needs_streamlit


def test_an_action_is_named_one_way_for_any_api() -> None:
    assert wiring.action_ref("GET /orders/{id}") == ("local", "GET", "/orders/{id}")
    assert wiring.action_ref("[Orders] POST /orders") == ("Orders", "POST", "/orders")
    assert wiring.action_ref("[Finance API] GET /v1/x") == ("Finance API", "GET", "/v1/x")
    for bad in ("orders", "[Orders] /orders", "[] GET /orders", "FETCH /orders", None, 7):
        assert wiring.action_ref(bad) is None


def test_a_wire_takes_another_apis_action_and_says_when_it_is_not_there() -> None:
    known = {"GET /orders", "[Orders] GET /orders", "[Orders] POST /orders"}
    context = wiring.Context(endpoints=known)
    wiring.check_in(Port("rows", "in", "Table"), {"endpoint": "[Orders] GET /orders"}, context)
    with pytest.raises(ContractError, match=r"Orders has no action GET /gone"):
        wiring.check_in(Port("rows", "in", "Table"), {"endpoint": "[Orders] GET /gone"}, context)
    with pytest.raises(ContractError, match=r"API\.py has no endpoint GET /gone"):
        wiring.check_in(Port("rows", "in", "Table"), {"endpoint": "GET /gone"}, context)
    with pytest.raises(ContractError, match="reads a GET endpoint"):
        wiring.check_in(Port("rows", "in", "Table"), {"endpoint": "[Orders] POST /orders"}, context)
    event = Port("saved", "event", "dict")
    call = {"do": "call", "endpoint": "[Orders] POST /orders", "body": "values"}
    wiring.check_event(event, {"actions": [call]}, known)
    with pytest.raises(ContractError, match=r"Orders has no action POST /gone"):
        wiring.check_event(event, {"actions": [call | {"endpoint": "[Orders] POST /gone"}]}, known)
    canvas = {
        "pages": [
            {
                "id": "p1",
                "name": "One",
                "children": [
                    {
                        "id": "w1",
                        "kind": "widget",
                        "widget": "x",
                        "values": {},
                        "wires": {"rows": {"endpoint": "[Orders] GET /orders"}, "saved": {"actions": [call]}},
                    }
                ],
            }
        ]
    }
    assert wiring.api_calls(canvas) == ["[Orders] GET /orders", "[Orders] POST /orders"]


def test_an_endpoint_property_takes_another_apis_action() -> None:
    prop = next(p for p in _widget("api_table")[1].properties if p.name == "endpoint")
    context = props.Context(endpoints={"[Orders] GET /orders/{order_id}"})
    props.check(prop, "[Orders] GET /orders/{order_id}", context)
    with pytest.raises(props.PropertyError, match=r"Orders has no action GET /gone"):
        props.check(prop, "[Orders] GET /gone", context)
    assert props.path_names("[Orders] GET /orders/{order_id}") == ["order_id"]
    assert props.path_names("[Finance API] GET /a/{b}/{c}") == ["b", "c"]


def test_the_runtime_has_one_call_and_the_wiring_uses_it() -> None:
    runtime = build.RUNTIME
    compile(runtime, "sab_canvas.py", "exec")
    assert runtime.count("urllib.request") == 0  # no request of its own: api_adapter sends
    source = runtime.split("def _source(", 1)[1].split("\nclass _Fire", 1)[0]
    fire = runtime.split("class _Fire", 1)[1].split("\ndef var(", 1)[0]
    assert 'action(str(wire["endpoint"]))' in source and "action(ref, filled" in fire
    assert "api_call(" not in source and "api_call(" not in fire
    files = build.build({"name": "A", "pages": []}, {}, carried={"api_adapter.py": "# the adapter\n"})
    assert files["api_adapter.py"] == "# the adapter\n"


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    settings = Settings(
        state_dir=tmp_path / "state",
        export_dir=tmp_path / "exports",
        auto_load_catalogs=False,
        projects_dir=tmp_path / "projects",
        workbench_dir=tmp_path / "wb",
    )
    with memory_keyring(), running(lambda port: create_app(port, TOKEN, settings)) as (port, _server):
        yield port


@pytest.fixture
def service() -> Iterator[Service]:
    running_service = Service().start()
    yield running_service
    running_service.stop()


def _export(port: int, project: Path, out: Path, widgets: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    made = ask(port, "POST", "/streamlit/canvases", {"name": "Shop", "folder": str(project)})
    canvas = made["canvas"]
    path = f"/streamlit/canvases/{canvas}/command"
    ask(port, "POST", path, {"kind": "add_container", "x": 0, "y": 0, "w": 900, "h": 900})
    for name, values in widgets:
        ask(port, "POST", path, {"kind": "insert_widget", "parent": "c1", "widget": name, "values": values})
    done: dict[str, Any] = ask(port, "POST", f"/streamlit/canvases/{canvas}/export", {"folder": str(out)})
    return done


def test_the_picker_lists_every_apis_actions_and_a_built_app_carries_what_it_calls(
    live: int, service: Service, tmp_path: Path
) -> None:
    add_orders(live, service)
    project = tmp_path / "shop"
    ask(live, "POST", "/project/new", {"path": str(project)})
    listed = ask(live, "GET", "/streamlit/widgets/context")
    assert {"[Orders] GET /orders", "[Orders] POST /orders", "[Orders] GET /orders/{order_id}"} <= set(
        listed["endpoints"]
    )
    assert set(listed["endpoint_fields"]["[Orders] POST /orders"]) >= {"amount", "status"}
    # A learned shape travels with the app (types only): run the action once first.
    assert ask(live, "POST", "/actions/run", {"api": "Orders", "action": "list_orders"})["ok"]
    out = tmp_path / "out"
    done = _export(
        live,
        project,
        out,
        [("api_table", {"endpoint": "[Orders] GET /orders"}), ("metric", {"label": "Orders"})],
    )
    assert {"api_adapter.py", "sab_actions.json", "API_Orders.py", "sab_canvas.py"} <= {
        Path(f).name for f in done["files"]
    }
    adapter = Path(__file__).resolve().parents[1] / "src/swissarmybench/adapters/api_adapter.py"
    assert (out / "api_adapter.py").read_bytes() == adapter.read_bytes()  # the same file, as it is
    text = (out / "sab_actions.json").read_text(encoding="utf-8")
    kept = json.loads(text)
    orders = kept["Orders"]
    # Only what the app calls travels with it.
    assert orders["module"] == "API_Orders" and set(orders["actions"]) == {"GET /orders"}
    one = orders["actions"]["GET /orders"]
    assert one["action"]["name"] == "list_orders" and one["kind"] == "records"
    assert set(one["known"]["fields"]) == {"order_id", "amount", "status"}
    assert "shipped" not in text.replace('"shipped"', "") and "12.5" not in text  # no value: types only
    # Only the other API is called: the local sandbox API's variables are not asked for.
    assert "SAB_API_URL" not in done["variables"]
    assert text == json.dumps(kept, indent=2, sort_keys=True, ensure_ascii=False) + "\n"  # byte-stable


@needs_streamlit
def test_a_built_app_reads_another_apis_action_through_api_adapter(
    live: int, service: Service, tmp_path: Path
) -> None:
    add_orders(live, service)
    project = tmp_path / "shop"
    ask(live, "POST", "/project/new", {"path": str(project)})
    out = tmp_path / "out"
    _export(
        live,
        project,
        out,
        [
            ("api_table", {"endpoint": "[Orders] GET /orders"}),
            ("api_metric", {"endpoint": "[Orders] GET /orders/{order_id}", "path_values": {"order_id": 3},
                            "field": "amount", "label": "Amount"}),
            ("api_metric", {"endpoint": "[Orders] GET /orders/{order_id}", "path_values": {"order_id": 9999},
                            "field": "amount", "label": "Gone"}),
        ],
    )  # fmt: skip
    pages = sorted(str(p.relative_to(out)) for p in (out / "app_pages").glob("*.py"))
    (out / "check.json").write_text(json.dumps({"pages": pages}), encoding="utf-8")
    assert PYTHON is not None
    done = subprocess.run(  # noqa: S603 (this machine's Python with Streamlit)
        [PYTHON, "-I", "-c", RUNNER, str(out)],
        capture_output=True, text=True, timeout=600, cwd=out, check=False,
    )  # fmt: skip
    line = next((x for x in reversed(done.stdout.splitlines()) if x.startswith("SAB-RUN ")), None)
    assert line, done.stdout[-2000:] + done.stderr[-2000:]
    found = json.loads(line[len("SAB-RUN ") :])[0]
    assert not found["exceptions"], found
    # The table: the envelope's records, found under the service's `items` (one page: the widget pages).
    assert [r["order_id"] for r in found["frames"][0]][:3] == [1, 2, 3] and len(found["frames"][0]) == 10
    # One record's field by its path; a failed call's words in the widget's own place.
    assert found["metrics"][0] != "-" and found["metrics"][1] == "-"
    assert any("answered 404" in i and "No such order" in i for i in found["infos"]), found["infos"]
