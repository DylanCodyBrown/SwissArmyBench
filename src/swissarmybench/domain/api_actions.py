"""An API's actions in the app (Plans/api-adapter.plan.md): every API, the library's and the project's own
local sandbox API, as api_adapter's actions; Build's code and widget, by the endpoint's learned shape.

  names     the local sandbox API's one name (`local`), an action's place (an API and an action's name)
  build     what an endpoint builds into, by its shape: a notebook cell or a script function (sab.run's
            text), a widget on a canvas page (which prebuilt widget, its values and its wire); why one
            cannot be
  words     the drift note said once ("Orders list_orders: 2 fields new since 2026-11-20")

Standard library only; no I/O.
"""

from __future__ import annotations

import json
import keyword
import re
from collections.abc import Mapping
from typing import Any

LOCAL = "local"  # the project's local sandbox API among the actions (its own name is its header's)
BUILDS = ("cell", "function", "widget")
SHAPES_FOLDER = "shapes"  # beside an API in the library: apis/<name>/shapes/<action>.json
LOCAL_SHAPES = ".sab/api-shapes"  # the project's local sandbox API's, in its .sab


class BuildError(ValueError):
    """What an endpoint cannot be built into, in one sentence."""


def python_name(name: str) -> str:
    """An action's name as a Python name (list_orders; listOrders kept as it is)."""
    found = re.sub(r"\W+", "_", name).strip("_") or "answer"
    found = "_" + found if found[0].isdigit() else found
    return found + "_" if keyword.iskeyword(found) else found


def _literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _inputs_text(inputs: Mapping[str, Any]) -> str:
    return ", ".join(f"{_literal(k)}: {_literal(v)}" for k, v in inputs.items())


def cell(api: str, action: Mapping[str, Any], inputs: Mapping[str, Any], kind: str) -> str:
    """A notebook cell that runs the action through api_adapter (sab.run) and keeps its answer by its kind."""
    name = python_name(str(action["name"]))
    head = f"# {api} · {action['name']}: {action['method']} {action['path']}, through api_adapter (sab.run)"
    call = f"answer = sab.run({_literal(api)}, {_literal(action['name'])}, {{{_inputs_text(inputs)}}})"
    keep = {
        "records": f"{name} = sab.records(answer)  # its records as a table (fields by path: customer.id)",
        "record": f'{name} = answer["record"]  # the one record, whole',
        "value": f'{name} = answer["value"]',
        "file": f'{name} = answer["file"]  # name, type, size and its bytes as base64',
    }.get(kind, f"{name} = answer")
    return "\n".join(
        ["import swissarmybench as sab", "", head, call, 'answer["ok"] or print(answer["error"])', keep]
    )


def function(api: str, action: Mapping[str, Any], kind: str) -> str:
    """A script function over the action: its inputs as arguments, its answer by kind; a refusal raised."""
    name = python_name(str(action["name"]))
    taken = [i for i in action.get("inputs") or [] if i.get("in") != "header"]
    taken += [i for i in action.get("body") or []]
    required = [i for i in taken if i.get("required")]
    optional = [i for i in taken if not i.get("required")]
    params = [python_name(str(i["name"])) for i in required] + [
        f"{python_name(str(i['name']))}=None" for i in optional
    ]
    passed = ", ".join(f"{_literal(i['name'])}: {python_name(str(i['name']))}" for i in taken)
    answer_of = {
        "records": 'answer["records"]',
        "record": 'answer["record"]',
        "value": 'answer["value"]',
        "file": 'answer["file"]',
    }.get(kind, "answer")
    return "\n".join(
        [
            "import swissarmybench as sab",
            "",
            "",
            f"def {name}({', '.join(params)}):",
            f'    """{api}: {action["method"]} {action["path"]}, through api_adapter (sab.run)."""',
            f"    answer = sab.run({_literal(api)}, {_literal(action['name'])}, {{{passed}}})",
            '    if not answer["ok"]:',
            '        raise RuntimeError(answer["error"]["error"])',
            f"    return {answer_of}",
            "",
        ]
    )


def widget(api: str, action: Mapping[str, Any], kind: str, local: bool) -> dict[str, Any]:
    """The widget an endpoint builds on a canvas page: which prebuilt widget, its values and its wire. A list
    of records a table (the local API's GET wired; another API's as [API].action); a write the
    local API's form; one value or record the local API's metric."""
    endpoint = f"{action['method']} {action['path']}"
    if action.get("writes"):
        if not local:
            raise BuildError(
                "A widget sends only to the project's local sandbox API: build a script function."
            )
        return {"widget": "api_form", "values": {"endpoint": endpoint}, "wire": None}
    if kind == "records":
        if local:
            return {
                "widget": "data_table",
                "values": {},
                "wire": {"port": "table_name", "wire": {"endpoint": endpoint}},
            }
        return {
            "widget": "data_table",
            "values": {"table_name": f"[{api}].{action['name']}"},
            "wire": None,
            "as_table": True,
        }
    if kind in ("value", "record") and local:
        return {"widget": "api_metric", "values": {"endpoint": endpoint}, "wire": None}
    if not kind:
        raise BuildError("Its shape is not learned yet: run it once, or Discover the API.")
    raise BuildError(
        f"A {kind} answer of another API has no widget: build a notebook cell or a script function."
    )


def drift_said(api: str, action: str, words: str) -> str:
    return f"{api} {action}: {words}"
