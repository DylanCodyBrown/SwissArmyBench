"""The widget starter packs (domain/widget_packs.py): every pack widget names a known pack, reads its
properties, follows its pack's conventions (the inputs' common properties and required marker, a table
property where it reads data, a save event where it hands data on), and is listed under its pack first.
Then a few of them driven with Streamlit's AppTest as a viewer would: a required input left empty, a form
submitted empty and then filled, the Excel round trip, the upload's sample and the column matching."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from swissarmybench_streamlit.adapters.widget_files import excel_files
from swissarmybench_streamlit.domain import canvas_build as build
from swissarmybench_streamlit.domain import canvas_model as model
from swissarmybench_streamlit.domain import widget_contract as contract
from swissarmybench_streamlit.domain import widget_packs as packs
from swissarmybench_streamlit.domain import widget_properties as props
from swissarmybench_streamlit.domain import widgets as rules
from tests.test_widgets_apptest import PREBUILT, PYTHON, needs_streamlit


def _prebuilt() -> dict[str, rules.Widget]:
    found = {}
    for path in sorted(PREBUILT.glob("*.widget.py")):
        widget = rules.read_widget(path.read_text(encoding="utf-8"), prebuilt=True)
        found[widget.name] = widget
    return found


WIDGETS = _prebuilt()
PACKED = {name: w for name, w in WIDGETS.items() if w.pack}


def _properties(widget: rules.Widget) -> dict[str, props.Property]:
    return {p.name: p for p in props.detect(widget.code)}


def test_every_pack_has_its_widgets_and_every_pack_widget_names_a_known_pack() -> None:
    assert {w.pack for w in PACKED.values()} == set(packs.PACKS)
    by_pack = {pack: sorted(n for n, w in PACKED.items() if w.pack == pack) for pack in packs.PACKS}
    assert by_pack["Sales dashboard"] == [
        "sales_filter_bar", "sales_kpi_row", "sales_region_map", "sales_revenue_trend", "sales_top_products"
    ]  # fmt: skip
    assert len(by_pack["Operations"]) == 4 and len(by_pack["Customer service"]) == 5
    assert len(by_pack["Data entry"]) == 4 and len(by_pack["Admin"]) == 3
    assert (
        len(by_pack["User inputs"]) >= 22 and len(by_pack["Excel"]) == 6 and len(by_pack["Form builder"]) == 4
    )
    assert all(description.strip() for description in packs.PACKS.values())
    assert len(WIDGETS) >= 56 + 53


def test_a_pack_is_kept_in_the_header_and_written_back_byte_for_byte() -> None:
    for path in sorted(PREBUILT.glob("*.widget.py")):
        text = path.read_text(encoding="utf-8")
        widget = rules.read_widget(text, prebuilt=True)
        assert rules.write_widget(widget) == text, path.name
    text = (PREBUILT / "sales_kpi_row.widget.py").read_text(encoding="utf-8")
    assert rules.read_widget(rules.with_header(text, pack="Admin")).pack == "Admin"
    assert "pack" not in rules.write_widget(rules.read_widget(rules.with_header(text, pack="")))
    assert packs.order("Sales dashboard") == 0 and packs.order("") > packs.order("Nowhere") > packs.order(
        "Excel"
    )


def test_every_pack_widget_reads_its_properties_without_a_problem() -> None:
    for name, widget in PACKED.items():
        found = props.detect(widget.code)
        assert found, name
        assert not [p.name for p in found if p.problem], name


def test_the_inputs_share_their_properties_marker_and_error_look() -> None:
    """Their one required marker and error look are the runtime's (sab_canvas.marked, problem), once."""
    common = {"label", "help_text", "required", "disabled", "validation_message"}
    for name, widget in PACKED.items():
        if widget.pack != "User inputs":
            continue
        found = _properties(widget)
        assert common <= set(found), (name, common - set(found))
        assert "def _label" not in widget.code and (
            "marked(label, required)" in widget.code or name == "input_data_editor"
        )
        assert "problem(validation_message" in widget.code and "def _problem" not in widget.code, name
    assert (
        ':red[\\\\*]" if needed else text' in build.RUNTIME
        and 'st.markdown(f":red[{message}]")' in build.RUNTIME
    )


def test_the_widgets_that_read_data_take_a_table_and_those_that_hand_it_on_a_save_event() -> None:
    for name in ("sales_kpi_row", "ops_low_stock_table", "cs_ticket_queue", "de_edit_grid", "admin_audit_log",
                 "input_data_editor", "excel_round_trip", "form_submissions"):  # fmt: skip
        ports = {p.name: p for p in contract.detect(PACKED[name].code)}
        assert (ports["table_name"].direction, ports["table_name"].type) == ("in", "Table"), name
        assert "table_name" not in _properties(PACKED[name]), name
    for name in ("cs_reply_form", "de_record_form", "de_edit_grid", "de_approve_reject", "admin_settings_form",
                 "excel_round_trip", "form_designer", "form_fill"):  # fmt: skip
        events = [p for p in contract.detect(PACKED[name].code) if p.direction == "event"]
        assert events and all(e.type == "dict" and e.problem is None for e in events), name
        assert (
            "save_event" not in _properties(PACKED[name])
            and "session_state[save_event]" not in PACKED[name].code
        )
    designer = _properties(PACKED["form_designer"])
    assert designer["definition"].type == "dict" and "definition_key" not in designer


# ===== driven as a viewer would, with AppTest =====

DRIVER = r"""
import json, os, sys
folder = sys.argv[1]
sys.path.insert(0, folder)
os.chdir(folder)
from streamlit.testing.v1 import AppTest
plan = json.load(open(os.path.join(folder, "drive.json"), encoding="utf-8"))
out = {}
for case in plan:
    at = AppTest.from_file(os.path.join(folder, case["page"]), default_timeout=90)
    at.run()
    for kind, index, action, *value in case["steps"]:
        element = at.get(kind)[index]
        getattr(element, action)(*value)
        if action == "click":  # a form's values go with its submit button: one run for them all
            at.run()
    if case["steps"] and case["steps"][-1][2] != "click":
        at.run()
    state = {}
    for name in case["keys"]:
        try:
            value = at.session_state[name]
        except Exception:
            value = None
        if hasattr(value, "to_dict"):
            value = {"columns": [str(c) for c in value.columns], "rows": len(value)}
        state[name] = value
    out[case["name"]] = {
        "exceptions": [str(e.value)[:500] for e in at.exception],
        "markdown": [str(m.value) for m in at.markdown],
        "success": [str(s.value) for s in at.success],
        "metrics": {str(m.label): str(m.value) for m in at.metric},
        "state": state,
    }
print("SAB-DRIVE " + json.dumps(out, default=str))
"""


def _has(module: str) -> bool:
    if PYTHON is None:
        return False
    done = subprocess.run([PYTHON, "-c", f"import {module}"], capture_output=True, check=False)  # noqa: S603
    return done.returncode == 0


def _drive(folder: Path, cases: list[dict[str, Any]]) -> dict[str, Any]:
    canvas = model.new_canvas("Drive")
    canvas["pages"] = []
    built: dict[str, build.Built] = {}
    plan = []
    for at, case in enumerate(cases, start=1):
        widget = WIDGETS[case["widget"]]
        built[widget.name] = build.made(widget.code)
        page = build.one_widget(widget.name, built[widget.name], case.get("values", {}), widget.size)[
            "pages"
        ][0]
        page["id"], page["name"] = f"p{at}", case["name"]
        canvas["pages"].append(page)
    # What the services carry beside the pages for the Excel widgets: adapter.py and sab_excel.py.
    carried = excel_files("\n".join(b.code for b in built.values()))
    files = build.build(canvas, built, carried=carried)
    pages = sorted(p for p in files if p.startswith("app_pages/"))
    for case, page in zip(
        cases, sorted(pages, key=lambda p: [c["name"] for c in cases].index(Path(p).stem)), strict=True
    ):
        plan.append(
            {"name": case["name"], "page": page, "steps": case.get("steps", []), "keys": case.get("keys", [])}
        )
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    (folder / "drive.json").write_text(json.dumps(plan), encoding="utf-8")
    assert PYTHON is not None
    done = subprocess.run(  # noqa: S603
        [PYTHON, "-I", "-c", DRIVER, str(folder)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=folder,
        check=False,
    )
    line = next((x for x in reversed(done.stdout.splitlines()) if x.startswith("SAB-DRIVE ")), None)
    assert line, done.stdout[-2000:] + done.stderr[-3000:]
    found: dict[str, Any] = json.loads(line[len("SAB-DRIVE ") :])
    return found


@needs_streamlit
def test_inputs_and_forms_as_a_viewer_uses_them(tmp_path: Path) -> None:
    cases: list[dict[str, Any]] = [
        {"name": "text_required", "widget": "input_text", "values": {"required": True, "label": "Name"},
         "steps": [["text_input", 0, "input", "   "]], "keys": ["w1-value"]},
        {"name": "text_given", "widget": "input_text", "values": {"required": True},
         "steps": [["text_input", 0, "input", "Ada"]], "keys": ["sab:w1.value"]},
        {"name": "fill_empty", "widget": "form_fill", "steps": [["button", 0, "click"]], "keys": ["sab:w1.saved"]},
        {"name": "fill_done", "widget": "form_fill",
         "values": {"definition": {"name": "count", "title": "Count", "fields": [
             {"name": "product", "label": "Product", "type": "text", "required": True},
             {"name": "counted", "label": "Counted", "type": "number", "required": True, "format": "0..100"}]},
             },
         "steps": [["text_input", 0, "input", "Kettle"], ["number_input", 0, "set_value", 12], ["button", 0, "click"]],
         "keys": ["sab:w1.saved", "sab:w1.form_submissions"]},
        {"name": "fill_range", "widget": "form_fill",
         "values": {"definition": {"name": "count", "fields": [
             {"name": "counted", "label": "Counted", "type": "number", "required": True, "format": "0..100"}]},
             },
         "steps": [["number_input", 0, "set_value", 200], ["button", 0, "click"]], "keys": ["sab:w1.saved"]},
        {"name": "designer_save", "widget": "form_designer", "steps": [["button", 0, "click"]],
         "keys": ["sab:w1.saved", "sab:w1.form_definition"]},
        {"name": "settings_empty", "widget": "admin_settings_form",
         "steps": [["text_input", 0, "input", ""], ["button", 0, "click"]], "keys": ["sab:w1.saved"]},
        {"name": "filter_bar", "widget": "sales_filter_bar", "steps": [["multiselect", 0, "select", "North"]],
         "keys": ["sab:w1.sales_filter"]},
    ]  # fmt: skip
    found = _drive(tmp_path, cases)
    assert not any(case["exceptions"] for case in found.values()), found
    assert any(":red[Enter a value.]" in m for m in found["text_required"]["markdown"])
    assert found["text_given"]["state"]["sab:w1.value"] == "Ada"
    assert not any(":red[" in m for m in found["text_given"]["markdown"])
    empty = found["fill_empty"]
    assert empty["state"]["sab:w1.saved"] is None
    assert any("Store: Fill this in." in m for m in empty["markdown"]) and any(
        "Your name" in m for m in empty["markdown"]
    )
    done = found["fill_done"]["state"]
    assert done["sab:w1.saved"]["form"] == "count"
    assert done["sab:w1.saved"]["values"] == {"product": "Kettle", "counted": 12.0}
    assert len(done["sab:w1.form_submissions"]) == 1
    assert found["fill_range"]["state"]["sab:w1.saved"] is None
    assert any(m.startswith(":red[Counted: ") for m in found["fill_range"]["markdown"])
    saved = found["designer_save"]["state"]
    assert saved["sab:w1.saved"]["name"] == "site_visit" and len(saved["sab:w1.saved"]["fields"]) == 8
    assert saved["sab:w1.form_definition"] == saved["sab:w1.saved"]
    assert found["settings_empty"]["state"]["sab:w1.saved"] is None
    assert any("Company name: Fill this in." in m for m in found["settings_empty"]["markdown"])
    assert found["filter_bar"]["state"]["sab:w1.sales_filter"]["regions"] == ["North"]


@needs_streamlit
@pytest.mark.skipif(not _has("openpyxl"), reason="no openpyxl in the Streamlit Python")
def test_the_excel_pack_reads_maps_validates_and_round_trips(tmp_path: Path) -> None:
    cases: list[dict[str, Any]] = [
        {"name": "upload", "widget": "excel_upload", "keys": ["sab:w1.uploaded"]},
        {"name": "upload_range", "widget": "excel_upload", "values": {"cell_range": "A1:C5", "sheet": "1"}, "keys": ["sab:w1.uploaded"]},
        {"name": "map", "widget": "excel_map_columns", "keys": ["sab:w1.mapped", "sab:w1.mapping"]},
        {"name": "validate", "widget": "excel_validate_rows", "keys": ["sab:w1.valid"]},
        {"name": "round_trip", "widget": "excel_round_trip", "steps": [["button", 0, "click"]], "keys": ["sab:w1.saved"]},
    ]  # fmt: skip
    found = _drive(tmp_path, cases)
    assert not any(case["exceptions"] for case in found.values()), found
    assert found["upload"]["state"]["sab:w1.uploaded"] == {
        "columns": ["Order No", "Cust. name", "Product", "Qty", "Unit price", "Order date", "Status"],
        "rows": 12,
    }
    assert found["upload_range"]["state"]["sab:w1.uploaded"] == {
        "columns": ["Order No", "Cust. name", "Product"],
        "rows": 4,
    }
    mapping = found["map"]["state"]["sab:w1.mapping"]
    assert mapping == {
        "order_id": "Order No", "customer_name": "Cust. name", "product": "Product", "quantity": "Qty",
        "unit_price": "Unit price", "order_date": "Order date", "status": "Status",
    }  # fmt: skip
    metrics = found["validate"]["metrics"]
    assert metrics["Rows"] == "12" and int(metrics["Problems"]) >= 4  # quantity 0 and 12, the misspelt status
    assert found["validate"]["state"]["sab:w1.valid"]["rows"] == int(metrics["Rows that pass"])
    trip = found["round_trip"]
    assert trip["metrics"] == {"Added": "0", "Changed": "0", "Removed": "0", "Problems": "0"}
    assert trip["state"]["sab:w1.saved"] == {"added": [], "changed": [], "removed": []}
