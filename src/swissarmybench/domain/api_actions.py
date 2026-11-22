"""An API's actions in the app (Plans/api-adapter.plan.md): every API, the library's and the project's own
local sandbox API, as api_adapter's actions; Build's code and widget, by the endpoint's learned shape.

  names     the local sandbox API's one name (`local`), an action's place (an API and an action's name)
  build     what an endpoint builds into, by its shape: a notebook cell or a script function (sab.run's
            text), a widget on a canvas page (which prebuilt widget, its values and its wire); why one
            cannot be; ref(): an action as the canvas names it
  words     the drift note said once ("Orders list_orders: 2 fields new since 2026-11-20")
  tried     Try it's form filled from the learned shape (made-up values by learned type; no value kept)
  allow     Discover's Allow remembered per API (allow_text, allowed_since: its small file)
  insert    Build's cell put at the end of a notebook (with_cell), its function at the end of a script the
            user picks (script_path, with_function)

Standard library only; no I/O.
"""

from __future__ import annotations

import itertools
import json
import keyword
import re
from collections.abc import Mapping
from typing import Any

from swissarmybench.domain import api_scaffold, notebooks

LOCAL = "local"  # the project's local sandbox API among the actions (its own name is its header's)
BUILDS = ("cell", "function", "widget")
SHAPES_FOLDER = "shapes"  # beside an API in the library: apis/<name>/shapes/<action>.json
LOCAL_SHAPES = ".sab/api-shapes"  # the project's local sandbox API's, in its .sab
# Discover's Allow, remembered per API until it is taken back: beside the API in the library
# (apis/<name>/discover.json), the local sandbox API's in the project's .sab. Who allowed it is not kept.
ALLOW_FILE = "discover.json"
LOCAL_ALLOW = ".sab/api-discover.json"


def ref(api: str, method: str, path: str) -> str:
    """An action as the canvas names it: "GET /orders" (the local sandbox API's endpoint), "[Orders] GET
    /orders" (the library API called Orders)."""
    return f"{method} {path}" if api.casefold() == LOCAL else f"[{api}] {method} {path}"


# The files of a project a built function never goes into: the app makes them, or they are the API itself.
NOT_SCRIPTS = ("API.py", "data.py", "adapter.py", "api_adapter.py", "connections.py", "sab_api.py")
DATA_NOTEBOOK = "data.ipynb"  # where a built cell goes: the project's data notebook
SAB_IMPORT = "import swissarmybench as sab"


class BuildError(ValueError):
    """What an endpoint cannot be built into, in one sentence."""


def with_cell(text: str, code: str) -> tuple[str, int]:
    """A notebook's text with one more Python cell at its end, and the cell's own number (never reused: the
    notebook's next number moves on). The rest of the file is kept as it is."""
    _cells, number = notebooks.read_document(text)  # a file that is not a notebook is refused here
    raw = json.loads(text)
    cells = raw.setdefault("cells", [])
    used = {c.get("id") for c in cells if isinstance(c, dict)}
    cell_id = next(f"cell-{n}" for n in itertools.count(len(cells) + 1) if f"cell-{n}" not in used)
    cells.append(
        {
            "id": cell_id,
            "metadata": {notebooks.OWN_KEY: {"number": number}},
            "cell_type": "code",
            "source": code.splitlines(keepends=True),
            "outputs": [],
            "execution_count": None,
        }
    )
    own = raw.setdefault("metadata", {}).setdefault(notebooks.OWN_KEY, {})
    own["next_cell"] = number + 1
    return json.dumps(raw, indent=1, ensure_ascii=False) + "\n", number


def script_path(path: Any) -> str:
    """The script a built function goes into, as its path inside the project: a .py of the user's own."""
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        raise BuildError("Name the script it goes into, as scripts/orders.py.")
    if text.startswith("/") or ":" in text or ".." in text.split("/"):
        raise BuildError("The script is a path inside the project, as scripts/orders.py.")
    if not text.endswith(".py"):
        raise BuildError("A function goes into a script: a .py file.")
    name = text.rsplit("/", 1)[-1]
    if name in NOT_SCRIPTS or re.fullmatch(r"API_\w+\.py", name):
        raise BuildError(f"{name} is the app's to write (or the API itself): pick a script of your own.")
    return text


def with_function(text: str | None, code: str, name: str) -> tuple[str, int]:
    """A script's text with the built function at its end, and the line its `def` is on. A new script is the
    function's own text; an existing one keeps every line, takes `import swissarmybench as sab` among its own
    imports when it has none, and refuses a name it already defines."""
    made = code if code.endswith("\n") else code + "\n"
    text = text or ""
    if not text.strip():
        written = made
    else:
        if re.search(rf"^(?:async\s+)?def\s+{re.escape(name)}\b|^{re.escape(name)}\s*=", text, re.M):
            raise BuildError(f"The script has {name} already: rename it there, or pick another script.")
        body = made.split(SAB_IMPORT + "\n", 1)[-1].lstrip("\n")
        left = ""
        if not re.search(rf"^{re.escape(SAB_IMPORT)}\b", text, re.M):
            text, left = api_scaffold.with_imports(text, SAB_IMPORT + "\n")
        written = text.rstrip("\n") + "\n\n\n" + (left + "\n\n" if left else "") + body
    line = next(
        (i for i, row in enumerate(written.split("\n"), start=1) if row.startswith(f"def {name}(")), 1
    )
    return written, line


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
    of records a table (the local API's GET wired; another API's as [API].action); a write an API form; one
    value or record an API metric: any API's action, named as the canvas's one picker names it (ref) and
    called through api_adapter."""
    endpoint = ref(LOCAL if local else api, str(action["method"]), str(action["path"]))
    if action.get("writes"):
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
    if kind in ("value", "record"):
        return {"widget": "api_metric", "values": {"endpoint": endpoint}, "wire": None}
    if not kind:
        raise BuildError("Its shape is not learned yet: run it once, or Discover the API.")
    raise BuildError(f"A {kind} answer has no widget: build a notebook cell or a script function.")


_MADE_UP: dict[str, Any] = {
    "integer": 1,
    "number": 12.5,
    "boolean": True,
    "date": "2026-01-15",
    "datetime": "2026-01-15T09:30:00",
    "list": [],
    "object": {},
}


def made_up(kind: str, name: str) -> Any:
    """A made-up value of a learned type (never a request's or an answer's own: no value is ever kept)."""
    return _MADE_UP.get(kind, f"made-up {name.rsplit('.', 1)[-1]}")


def tried(
    start: Mapping[str, Any], contract: Mapping[str, Any] | None, sent: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Try it's form filled from the learned shape (the owner, 2026-11-22: values are never kept, so there is
    no kept example). `start`: the endpoint's made-up request as its definition gives it ({"path", "query",
    "body"}); over it, what the endpoint was last sent (`sent`: a shape's own paths and types, as query.status
    and body.customer.id): a query input or a body field the definition does not name gets a made-up value of
    its learned type; and the contract's closed sets: an input or a body field with choices starts from the
    first one. Answers the request, and `learned`: whether a learned shape filled any of it."""
    out: dict[str, Any] = {
        "path": dict(start.get("path") or {}),
        "query": dict(start.get("query") or {}),
        "body": json.loads(json.dumps(start.get("body"), default=str)),
    }
    filled = False
    for path, known in sorted(((sent or {}).get("fields") or {}).items()):
        place, _, name = str(path).partition(".")
        kind = str((known or {}).get("type") or "text")
        if place == "query" and name and name not in out["query"]:
            out["query"][name], filled = made_up(kind, name), True
        elif place == "body" and name and (out["body"] is None or isinstance(out["body"], dict)):
            holder = out["body"] = out["body"] if isinstance(out["body"], dict) else {}
            *parents, last = name.split(".")
            for part in parents:
                inner = holder.get(part)
                if not isinstance(inner, dict):
                    if part in holder:
                        break
                    inner = holder[part] = {}
                holder = inner
            else:
                if last not in holder:
                    holder[last], filled = made_up(kind, name), True
    for one in (contract or {}).get("inputs") or []:
        spot = out.get(str(one.get("in") or "query"))
        if one.get("choices") and isinstance(spot, dict) and spot.get(one["name"]) not in one["choices"]:
            if one["name"] in spot or one.get("required"):
                spot[one["name"]], filled = one["choices"][0], True
    for one in (contract or {}).get("body") or []:
        body = out["body"]
        if one.get("choices") and isinstance(body, dict) and one["name"] in body:
            if body[one["name"]] not in one["choices"]:
                body[one["name"]], filled = one["choices"][0], True
    return out | {"learned": filled}


def allow_text(since: str) -> str:
    """Discover's Allow as its small file's text: the day it was given (same day, same bytes)."""
    return json.dumps({"allowed": True, "since": since}, indent=2, sort_keys=True) + "\n"


def allowed_since(text: str | None) -> str | None:
    """The day Discover was allowed, read from its file (None: not allowed, or a file that does not read)."""
    try:
        found = json.loads(text) if text else None
    except ValueError:
        return None
    if not isinstance(found, dict) or found.get("allowed") is not True:
        return None
    return str(found.get("since") or "") or "an earlier day"


def drift_said(api: str, action: str, words: str) -> str:
    return f"{api} {action}: {words}"
