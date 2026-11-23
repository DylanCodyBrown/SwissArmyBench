"""Write the Blazor front end's answer records from the server's own answers (standard library only).

    python blazor/tools/generate_api.py           writes Api/<Area>/Generated/*.cs (the C# project's)
    python blazor/tools/generate_api.py --check   exit 1 naming each file that differs from the committed

The server has no OpenAPI document: its routes answer `json_response(dict)` with no schema (server/http.py),
so there is nothing typed to read. This script reads the answers themselves instead. It starts a server of
its own the way the browser tests do (a temporary state folder, made-up data only: the sample store and a
small made-up notebook), calls each route listed in ANSWERS, and writes one C# record per JSON object it
sees: its fields in the server's order, snake_case as PascalCase, each typed by its value (text, a whole
number, a number, true or false, a list, an object). What a value cannot tell (a number that may have a
fraction, a field that may be null, a free-form object) is said in the answer's `types`. A field the server
renames or drops changes the generated file, so `--check` (tests/test_blazor_api_types.py) fails and the C#
that read it no longer builds: a renamed field is a build error, not a blank on screen.

Answers whose shape no sample can pin (free-form, or needing a running kernel or a connection) keep their
hand-written records: HAND_WRITTEN names each one and why.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "blazor" / "SwissArmyBench.Web" / "Api"
NAMESPACE = "SwissArmyBench.Web.Api"
JSON = "System.Text.Json.JsonElement"


@dataclass(frozen=True)
class Answer:
    """One route's answer, written as the record `name` in Api/<area>/Generated/.

    nested: a field holding an object (or a list of objects) -> the record its object is written as.
    types:  a field -> its C# type as written (a number that may have a fraction, a free-form value, a list of
            lists). A trailing "?" says the field may be null or missing.
    path:   the route, {grid} and {notebook} filled from the made-up data; body: what a POST sends.
    """

    area: str
    name: str
    method: str
    path: str
    summary: str
    body: dict[str, Any] | None = None
    nested: dict[str, str] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)  # "field" or "Record.field" -> its C# type


ANSWERS: list[Answer] = [
    Answer(
        "Grids",
        "GridInfo",
        "GET",
        "/grids/{grid}",
        "GET /grids/{id}: a grid's dataset, columns, steps and whether a change can be undone or redone; "
        "the columns entering each step (StageColumns) and how its filters compare text (Settings).",
        nested={
            "columns": "GridColumn",
            "source_columns": "GridColumn",
            "steps": "GridStep",
            "settings": "TextMatching",
            "step_error": "StepError",
        },
        types={
            "stage_columns": "IReadOnlyList<IReadOnlyList<GridColumn>>",
            "step_error": "StepError?",
            "query": "string?",
            "query_connection": "string?",
            "opened": f"{JSON}?",
            "selected_rows": f"{JSON}?",
            "highlights": f"{JSON}?",
            "budget": f"{JSON}?",
            "params": JSON,
        },
    ),
    Answer(
        "Grids",
        "SelectionStats",
        "POST",
        "/grids/{grid}/selection-stats",
        "POST /grids/{id}/selection-stats: Excel's status bar over the whole selection, counted by the "
        "server; IdLike names the number columns that look like identifiers, whose sum would mean nothing.",
        body={"selection": {"rows": [[0, 4]], "columns": ["amount", "order_id"]}},
        types={"sum": "double?", "mean": "double?", "min": "double?", "max": "double?", "digits": f"{JSON}?"},
    ),
    Answer(
        "Grids",
        "TableProfile",
        "GET",
        "/grids/{grid}/profile",
        "GET /grids/{id}/profile (no column): every column's counts, blanks and range, and the duplicate "
        "rows.",
        nested={"columns": "TableProfileColumn"},
        types={"min": f"{JSON}?", "max": f"{JSON}?", "blank_percent": "double"},
    ),
    Answer(
        "Grids",
        "ValueList",
        "GET",
        "/grids/{grid}/values?column=status",
        "GET /grids/{id}/values: a column's values with their row counts (the filter's checklist), whether "
        "there are more than listed, and how many are blank.",
        nested={"values": "ValueCount"},
        types={"value": JSON},
    ),
    Answer(
        "Grids",
        "KeyFinderTargets",
        "GET",
        "/grids/{grid}/key-finder",
        "GET /grids/{id}/key-finder: the open grids the Key Finder can compare with (Self is this one).",
        nested={"grids": "KeyFinderTarget"},
    ),
    Answer(
        "Grids",
        "KeyFinderResult",
        "POST",
        "/grids/{grid}/key-finder",
        "POST /grids/{id}/key-finder: the likely join keys with another grid, best first.",
        body={"target": "{customers}", "options": {}},
        nested={"pairs": "KeyPair"},
        types={
            "source_found": "double",
            "target_found": "double",
            "score": "double",
            "suggested_key": f"{JSON}?",
            "skipped": f"{JSON}?",
            "targets": f"IReadOnlyList<{JSON}>",
            "unique_key": f"{JSON}?",
        },
    ),
    Answer(
        "Grids",
        "TableConnection",
        "GET",
        "/tables/orders/connection",
        "GET /tables/{name}/connection: the connection a table is read from (none: a file, a paste, a "
        "push), and whether its last change can be undone.",
        types={
            "connection": "string?",
            "place": f"{JSON}?",
            "sql": "string?",
            "others": f"IReadOnlyList<{JSON}>",
            "undo_connection": "string?",
        },
    ),
    Answer(
        "Workbench",
        "WorkbenchHome",
        "GET",
        "/workbench/home",
        "GET /workbench/home: where Save as starts, and the recent files.",
        nested={"recent": "RecentFile"},
        types={"opened": "double"},
    ),
    Answer(
        "Workbench",
        "OpenedNotebook",
        "POST",
        "/workbench/open",
        "POST /workbench/open of a notebook: its cells, the number the next new cell gets, its Python and "
        "session.",
        body={"path": "{notebook}"},
        nested={"cells": "NotebookCell", "session": "SessionInfo"},
        types={
            "modified": "double",
            "outputs": f"IReadOnlyList<{JSON}>",
            "execution_count": "int?",
            "number": "int?",
            "connection": "string?",
            "table": "string?",
            "steps": f"{JSON}?",
            "height": "int?",
            "name": "string?",
            "session": "SessionInfo?",
            "kernel": "string?",
            "dictionary": f"{JSON}?",
            "python": "string?",
            "next_cell": "int",
            "hash": "string?",
        },
    ),
    Answer(
        "Workbench",
        "OpenedScript",
        "POST",
        "/workbench/open",
        "POST /workbench/open of a script: its text, its Python and session.",
        body={"path": "{script}"},
        nested={"session": "SessionInfo"},
        types={
            "modified": "double",
            "session": "SessionInfo?",
            "kernel": "string?",
            "python": "string?",
            "hash": "string?",
        },
    ),
]

ANSWERS.append(
    Answer(
        "Workbench",
        "ArrangedNotebook",
        "POST",
        "/workbench/tables/arrange",
        "POST /workbench/tables/arrange: a notebook's cells as they should be, its Tables group in place, "
        "and the number the next new cell gets.",
        body={
            "kind": "notebook",
            "cells": [
                {"kind": "code", "source": "x = 1", "number": 1, "role": "", "table": None, "grouped": False}
            ],
            "tables": ["orders"],
            "next_cell": 2,
            "move": True,
        },
        nested={"cells": "ArrangedCell", "tables": "TableLine"},
        types={
            "table": "string?",
            "uses": "string?",
            "steps": f"{JSON}?",
            "maker": "int?",
            "note": "string?",
            "cell": "int?",
            "number": "int",
            "next_cell": "int",
        },
    )
)

ANSWERS += [
    Answer(
        "Analyze",
        "AnalyzeToolbar",
        "GET",
        "/analyze?front={grid}",
        "GET /analyze: the toolbar's groups and every analysis (its question, its name, what you get); the "
        "open tables and the one a form starts on.",
        nested={"analyses": "AnalysisEntry", "tables": "AnalyzeTable"},
        types={"current": "string?"},
    ),
    Answer(
        "Analyze",
        "AnalyzePlan",
        "POST",
        "/analyze/plan",
        "POST /analyze/plan: the one form, planned by the server: each slot's columns that fit and the "
        "ones that do not (with why), the picks, the options, what is missing in one sentence, the fixes, "
        "the sentence of what will run. The page has no rule of its own.",
        body={"analysis": "outliers", "table": "{grid}"},
        nested={
            "slots": "PlanSlot",
            "offered": "OfferedColumn",
            "rejected": "RejectedColumn",
            "options": "PlanOption",
            "fixes": "PlanFix",
        },
        types={
            "value": f"{JSON}?",
            "default": f"{JSON}?",
            "columns": JSON,
            "settings": JSON,
            "missing": "string?",
            "said": "string?",
            "cautions": "IReadOnlyList<string>",
            "gone": f"IReadOnlyList<{JSON}>",
            "refused": f"IReadOnlyList<{JSON}>",
            "choices": "IReadOnlyList<IReadOnlyList<string>>",
            "preview": "IReadOnlyList<string>",
            "PlanFix.steps": f"IReadOnlyList<{JSON}>",
            "fills": f"{JSON}?",
            "slot": "string?",
            "column": "string?",
            "rows": "long",
            "count": "long?",
        },
    ),
    Answer(
        "Analyze",
        "AnalyzeRun",
        "POST",
        "/analyze/run",
        "POST /analyze/run: what ran (its run, its table, its columns and options, its sentence), the "
        "cards it put at the top of the board, the actions a result offers, and the result's numbers.",
        body={"analysis": "outliers", "table": "{grid}", "columns": {"column": "amount"}},
        types={
            "columns": JSON,
            "options": JSON,
            "applied": f"IReadOnlyList<{JSON}>",
            "cautions": "IReadOnlyList<string>",
            "result": f"{JSON}?",
        },
    ),
    Answer(
        "Analyze",
        "BoardCards",
        "GET",
        "/cards",
        "GET /cards: the Analyze board's cards, newest first by their order: a note (Markdown), a Plotly "
        "figure, a picture, a diagram, each with the analysis it came from.",
        nested={"cards": "BoardCard"},
        types={
            "body": "string?",
            "size": f"{JSON}?",
            "key": "string?",
            "grid": "string?",
            "dataset": "string?",
            "created": "double",
            "order": "double",
            "analysis": f"{JSON}?",
        },
    ),
    Answer(
        "Analyze",
        "RunMath",
        "GET",
        "/analyze/runs/{run}/math",
        "GET /analyze/runs/{run}/math: Show the math, a result as a step-by-step proof in Markdown.",
    ),
    Answer(
        "Analyze",
        "RunCode",
        "GET",
        "/analyze/runs/{run}/code",
        "GET /analyze/runs/{run}/code: Copy code, the analysis as Python with its imports.",
    ),
    Answer(
        "Analyze",
        "RunInputs",
        "GET",
        "/analyze/runs/{run}",
        "GET /analyze/runs/{run}: what a run ran with (Run again fills the form from it).",
        types={"columns": JSON, "options": JSON},
    ),
]

ANSWERS += [
    Answer(
        "Apis",
        "ApiCards",
        "GET",
        "/apis",
        "GET /apis: the library's APIs as cards (their operations, sign-in, tables, calls, where their "
        "document came from) and older API connections.",
        nested={"apis": "ApiCard", "source": "ApiSource"},
        types={
            "calls": JSON,
            "tables": f"IReadOnlyList<{JSON}>",
            "older": f"IReadOnlyList<{JSON}>",
            "problem": "string?",
            "file": "string?",
            "version": "string?",
        },
    ),
    Answer(
        "Apis",
        "ApiExplorer",
        "GET",
        "/apis/Store",
        "GET /apis/{name}: an API read for people: each operation's inputs, body and answers (as schema "
        "trees with made-up examples), and its named schemas with where each is used.",
        nested={
            "operations": "ApiOperation",
            "parameters": "ApiParameter",
            "responses": "ApiResponse",
            "schemas": "ApiSchema",
            "source": "ExplorerSource",
        },
        types={
            "ApiOperation.schemas": "IReadOnlyList<string>",
            "ApiOperation.body": f"{JSON}?",
            "schema": f"{JSON}?",
            "example": f"{JSON}?",
            "default": f"{JSON}?",
            "enum": f"IReadOnlyList<{JSON}>",
            "table": f"{JSON}?",
            "inputs": f"{JSON}?",
            "body_saved": f"{JSON}?",
            "sql_name": "string?",
            "tags": "IReadOnlyList<string>",
            "used_by": "IReadOnlyList<string>",
            "uses": "IReadOnlyList<string>",
            "folder": "string?",
        },
    ),
    Answer(
        "Structures",
        "StructureList",
        "GET",
        "/structures",
        "GET /structures: the structures open now and the project's structure files.",
        nested={"open": "StructureEntry"},
        types={
            "files": f"IReadOnlyList<{JSON}>",
            "path": "string?",
            "origin": f"{JSON}?",
            "steps": f"IReadOnlyList<{JSON}>",
            "hash": "string?",
            "text_error": "string?",
        },
    ),
    Answer(
        "Structures",
        "StructureDocument",
        "GET",
        "/structures/{structure}",
        "GET /structures/{id}: a structure's value (through its steps), its own text as typed and its parse "
        "error, its format, where it came from and whether it is saved.",
        types={
            "path": "string?",
            "origin": f"{JSON}?",
            "steps": f"IReadOnlyList<{JSON}>",
            "hash": "string?",
            "text_error": "string?",
            "error": "string?",
            "value": f"{JSON}?",
        },
    ),
]

# A made-up API's OpenAPI document (Add API reads it as text): orders by status, one order, a new order.
STORE_SPEC: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Store", "version": "1.0"},
    "servers": [{"url": "http://127.0.0.1:9/v1"}],
    "paths": {
        "/orders": {
            "get": {
                "operationId": "list_orders",
                "summary": "The orders",
                "parameters": [{"name": "status", "in": "query", "schema": {"type": "string"}}],
                "responses": {
                    "200": {
                        "description": "The orders",
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"$ref": "#/components/schemas/Order"}}
                            }
                        },
                    }
                },
            },
            "post": {
                "operationId": "create_order",
                "summary": "A new order",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}},
                },
                "responses": {"201": {"description": "Made"}},
            },
        }
    },
    "components": {
        "schemas": {
            "Order": {
                "type": "object",
                "properties": {"order_id": {"type": "integer"}, "amount": {"type": "number"}},
            }
        }
    },
}

# Answers kept by hand, and why no sample pins their shape.
HAND_WRITTEN: dict[str, str] = {
    "Workbench/StartedKernel": "needs a running IPython kernel (seconds to start; the answer is three "
    "fields)",
    "Workbench/SessionInfo": "null outside a project (the made-up notebook is a loose file)",
    "Workbench/TableInfo": "an open table's cell text: its fields depend on where the table came from",
    "Workbench/CodeTree": "the Files pane's groups differ by page and project (made files, library groups)",
    "Workbench/BladeSummary": "a blade's fields depend on its kind (connection, vault, web call)",
    "Analyze/a table card's columns and rows": "only a card Python sends carries them (read from the card's "
    "body on the page)",
    "Apis/ApiCallAnswer": "a call's answer needs the API's service to answer (the made-up API is offline)",
    "Grids/StepError": "null unless a step fails (the made-up data has no failing step)",
    "Grids/ConnectionSwap": "one of four answers (swapped, pick, review, failed), each free-form",
    "Grids/MadeTable": "shared by the query and the sandbox variant, each answering different fields",
    "Connections/*": "each connection kind's form is data drawn by the page (its fields are the kind's)",
    "Environment/*": "each tab's rows carry the kind's own fields",
    "Projects/*, Settings/*, SessionLog/*, Catalog/*, Relationships/*, App/*": "written before the "
    "generator; moved to it area by area",
}


def pascal(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)


@dataclass
class Record:
    name: str
    summary: str
    fields: list[tuple[str, str, str]]  # (json name, C# type, default)


def type_of(key: str, value: Any, answer: Answer, records: dict[str, Record], parent: str) -> tuple[str, str]:
    """A field's C# type and its default, from the answer's say first ("Record.field" before "field"), else
    from its value."""
    said = answer.types.get(f"{parent}.{key}", answer.types.get(key))
    if said is not None:
        typed = said
        if key in answer.nested and value is not None:
            items = value if isinstance(value, list) else [value]
            for item in (v for v in items if isinstance(v, dict)):
                walk(answer.nested[key], item, answer, records, f"One {pascal(key)} item of {parent}.")
        return typed, default_of(typed)
    if isinstance(value, bool):
        return "bool", ""
    if isinstance(value, int):
        return "long", ""
    if isinstance(value, float):
        return "double", ""
    if isinstance(value, str):
        return "string", "string.Empty"
    if isinstance(value, dict):
        if key in answer.nested:
            walk(answer.nested[key], value, answer, records, f"The {pascal(key)} of {parent}.")
            return answer.nested[key], "new()"
        return JSON, ""
    if isinstance(value, list):
        sample = next((v for v in value if v is not None), None)
        if isinstance(sample, dict) and key in answer.nested:
            # Every item is read: a field only some items carry (a table cell's steps) is still a field.
            for item in (v for v in value if isinstance(v, dict)):
                walk(answer.nested[key], item, answer, records, f"One of {parent}'s {pascal(key)}.")
            return f"IReadOnlyList<{answer.nested[key]}>", "[]"
        plain = {str: "string", bool: "bool", int: "long", float: "double"}
        listed = plain.get(type(sample), JSON) if sample is not None else JSON
        return f"IReadOnlyList<{listed}>", "[]"
    return f"{JSON}?", ""  # null in the sample and not said: kept loose, never guessed


def default_of(typed: str) -> str:
    if typed.endswith("?"):
        return ""
    if typed == "string":
        return "string.Empty"
    if typed.startswith("IReadOnlyList<"):
        return "[]"
    return ""


def walk(name: str, sample: dict[str, Any], answer: Answer, records: dict[str, Record], summary: str) -> None:
    known = records.get(name)
    fields = known.fields if known else []
    seen = {f[0] for f in fields}
    for key, value in sample.items():
        if key in seen:
            continue
        typed, default = type_of(key, value, answer, records, name)
        fields.append((key, typed, default))
    if not known:
        records[name] = Record(name, summary, fields)


def csharp(area: str, record: Record) -> str:
    lines = [
        "// <auto-generated>",
        "// Written by blazor/tools/generate_api.py from the server's own answers: change the server or that",
        "// script, never this file (tests/test_blazor_api_types.py checks it is current).",
        "// </auto-generated>",
        "#nullable enable",
    ]
    if any(JSON in t for _, t, _ in record.fields):
        lines += ["using System.Text.Json;", ""]
    else:
        lines += [""]
    lines += [f"namespace {NAMESPACE}.{area};", "", *summary_lines(record.summary)]
    lines += [f"public sealed record {record.name}", "{"]
    for at, (key, typed, default) in enumerate(record.fields):
        shown = typed.replace(f"{JSON}", "JsonElement")
        suffix = f" = {default};" if default else ""
        if at:
            lines.append("")
        lines.append(f"    public {shown} {pascal(key)} {{ get; init; }}{suffix}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def summary_lines(words: str, width: int = 112) -> list[str]:
    """The record's summary as doc comment lines, wrapped at the code's width."""
    if len(words) + 24 <= width:
        return [f"/// <summary>{words}</summary>"]
    lines, line = ["/// <summary>"], "///"
    for word in words.split():
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = "///"
        line += " " + word
    return [*lines, line, "/// </summary>"]


# ===== the server, its made-up data, and the answers =====


def start_server(tmp: Path) -> dict[str, Any]:
    env = os.environ | {
        "PYTHONPATH": str(ROOT / "src"),
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(tmp / "projects"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "workbench"),
        "SWISSARMYBENCH_NO_BROWSER": "1",
        "SWISSARMYBENCH_PROJECT_VENV": "off",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "swissarmybench.server", "--port", "0"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(300):
        try:
            info: dict[str, Any] = json.loads((tmp / "server.json").read_text())
            return info | {"process": process}
        except (OSError, ValueError):
            time.sleep(0.1)
    process.kill()
    raise RuntimeError("The server did not start.")


def call(info: dict[str, Any], method: str, path: str, body: Any = None) -> Any:
    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}",
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as answer:  # noqa: S310
        return json.loads(answer.read() or b"null")


def made_up(info: dict[str, Any], tmp: Path) -> dict[str, str]:
    """The sample store's grids, a made-up notebook (a code cell and a markdown cell) and a script."""
    tables = {t["name"]: t["grid"] for t in call(info, "POST", "/samples/store", {})["tables"]}
    # One step on orders, so a grid's steps have a sample (it keeps every row).
    step = {"kind": "filter", "params": {"column": "amount", "op": "not_blank"}}
    call(info, "POST", f"/grids/{tables['orders']}/step-ops", {"op": "add", "step": step})
    notebook = str(tmp / "workbench" / "made_up.ipynb")
    script = str(tmp / "workbench" / "made_up.py")
    cells = [
        {"kind": "code", "source": "total = 1 + 1", "number": 1},
        {"kind": "markdown", "source": "# Made-up notes", "number": 2},
    ]
    call(info, "POST", "/workbench/save", {"path": notebook, "cells": cells, "next_cell": 3})
    call(info, "POST", "/workbench/save", {"path": script, "text": "print('made up')\n"})
    # A made-up API (its document as text: no network) and a made-up structure.
    call(info, "POST", "/apis", {"spec": json.dumps(STORE_SPEC), "auth": {"type": "none"}})
    value = {"orders": [{"order_id": 1, "amount": 2.5}], "region": "North"}
    made = call(info, "POST", "/structures", {"kind": "object", "name": "made_up", "value": value})
    # A run on the Analyze board, so its cards and its run's math and code have a sample.
    columns = {"column": "amount"}
    run = call(
        info, "POST", "/analyze/run", {"analysis": "outliers", "table": tables["orders"], "columns": columns}
    )
    return {
        "grid": tables["orders"],
        "customers": tables["customers"],
        "notebook": notebook,
        "script": script,
        "run": run["run"],
        "structure": made["id"],
    }


def filled(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def generate() -> dict[Path, str]:
    with tempfile.TemporaryDirectory(prefix="sab-api-") as folder:
        tmp = Path(folder)
        info = start_server(tmp)
        try:
            values = made_up(info, tmp)
            files: dict[Path, str] = {}
            for answer in ANSWERS:
                body = json.loads(filled(json.dumps(answer.body), values)) if answer.body else None
                sample = call(info, answer.method, filled(answer.path, values), body)
                records: dict[str, Record] = {}
                walk(answer.name, sample, answer, records, answer.summary)
                for record in records.values():
                    files[API / answer.area / "Generated" / f"{record.name}.cs"] = csharp(answer.area, record)
            return files
        finally:
            info["process"].terminate()
            info["process"].wait(timeout=20)


def main() -> int:
    files = generate()
    if "--check" in sys.argv:
        stale = [p for p, text in files.items() if not p.is_file() or p.read_text(encoding="utf-8") != text]
        written = {p for folder in API.glob("*/Generated") for p in folder.glob("*.cs")}
        extra = sorted(written - set(files))
        for path in stale + extra:
            print(f"Not current: {path.relative_to(ROOT)}")
        return 1 if stale or extra else 0
    for folder in API.glob("*/Generated"):
        for old in folder.glob("*.cs"):
            if old not in files:
                old.unlink()
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {len(files)} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
