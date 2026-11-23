"""Every piece of Python the app writes for a connection is checked as code (docs/reviews/craft-review-
2026-11-22.md: "the text modules are run but never linted"): no undefined name, no unused import, no
import made twice, no local assigned and never read.

About 4,900 lines of the domain are Python kept as text (lake_code.py, api_clients.py, sql_server.py,
sharepoint.py, dataverse.py, entra.py, keystores.py, script_runtime.py). Ruff, mypy and the import test see a
string; the tests run that text against stand-ins, which finds only the lines a stand-in reaches (a name
read only against real Azure was undefined, and no test said so). Here each assembled code is checked whole:
by pyflakes when this Python has it, else by Ruff's own pyflakes rules, and always by the editors' own lint
(domain/intellisense.py), so the check never depends on a tool being installed.

What is checked: each starter of the Add connection forms in each way it signs in (with its List the tables
and Read a table boxes, which run in the same names), SQL Server's and Azure SQL's sign-ins, Dataverse's, the
lakes' and SharePoint's, Add API's made file for a made-up API in every auth type, the starter pack's
Python blades, connections.py as the project scaffold and an API's export write it for saved connections,
and the sandbox mirror.
"""

from __future__ import annotations

import dataclasses
import itertools
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from starlette.testclient import TestClient

from swissarmybench.domain import (
    api_clients,
    api_targets,
    apis,
    dataverse,
    intellisense,
    lakes,
    scaffold,
    script_runtime,
    sharepoint,
    sql_server,
)
from swissarmybench.domain.blades import read_blade
from swissarmybench.server.blade_templates import TEMPLATES
from tests.conftest import AUTH

ROOT = Path(__file__).resolve().parents[1]
STARTERS = ROOT / "src" / "swissarmybench" / "starters"
# What a blade's code is run with (adapters/blade_run.py): `secret`; Read a table's box also gets these.
RUN_NAMES = frozenset({"secret"})
READ_NAMES = frozenset({"schema", "table", "limit", "columns", "filters", "frame"})
# pyflakes' rules as Ruff numbers them: unused import, import made twice, undefined name, unused local.
RULES = "F401,F811,F821,F841"


@dataclasses.dataclass(frozen=True)
class Code:
    name: str
    text: str
    known: frozenset[str] = RUN_NAMES


# ===== the checkers =====


def _noqa(text: str, line: int) -> bool:
    lines = text.split("\n")
    return 0 < line <= len(lines) and "# noqa" in lines[line - 1]


def by_the_editors_lint(code: Code) -> list[str]:
    """The app's own lint: Python's compile, undefined names, unused top-level imports."""
    found = intellisense.lint(code.text, known=code.known)
    return [
        f"{code.name}:{p.line}: {p.message}"
        for p in found
        if (p.severity == "error" or p.code in ("F401", "F821")) and not _noqa(code.text, p.line)
    ]


def _with_known(code: Code) -> str:
    """The names the app gives the code, defined before it (so many lines, taken off each line said)."""
    return "".join(f"{name} = None\n" for name in sorted(code.known)) + code.text


def by_pyflakes(codes: list[Code]) -> list[str] | None:
    """pyflakes' own messages (None: not in this Python)."""
    try:
        from pyflakes import checker, messages
    except ImportError:
        return None
    import ast

    wanted = (
        messages.UnusedImport,
        messages.RedefinedWhileUnused,
        messages.UndefinedName,
        messages.UnusedVariable,
    )
    out: list[str] = []
    for code in codes:
        text = _with_known(code)
        for message in checker.Checker(ast.parse(text), filename=code.name).messages:
            if isinstance(message, wanted) and not _noqa(text, message.lineno):
                line = message.lineno - len(code.known)
                out.append(f"{code.name}:{line}: {message.message % message.message_args}")
    return out


def by_ruff(codes: list[Code], folder: Path) -> list[str] | None:
    """Ruff's pyflakes rules over each code as a file (None: no Ruff beside this Python or on the path)."""
    ruff = shutil.which("ruff", path=str(Path(sys.executable).parent)) or shutil.which("ruff")
    if ruff is None:
        return None
    names: dict[str, Code] = {}
    for number, code in enumerate(codes):
        names[f"code_{number}.py"] = code
        (folder / f"code_{number}.py").write_text(_with_known(code), encoding="utf-8")
    ran = subprocess.run(  # noqa: S603 (this environment's own Ruff over made-up files in a test's folder)
        [ruff, "check", "--isolated", "--no-cache", "--select", RULES, "--output-format", "concise", "."],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = []
    for line in ran.stdout.splitlines():
        file, _, rest = line.partition(":")
        at, _, words = rest.partition(":")
        if file in names and at.isdigit():
            out.append(f"{names[file].name}:{int(at) - len(names[file].known)}:{words}")
    assert ran.returncode in (0, 1), ran.stderr[-2000:]
    return out


def problems(codes: list[Code], folder: Path) -> list[str]:
    assert codes
    found = list(itertools.chain.from_iterable(by_the_editors_lint(code) for code in codes))
    flakes = by_pyflakes(codes)
    if flakes is None:
        flakes = by_ruff(codes, folder)
    return found + (flakes or [])


def said(found: list[str]) -> str:
    return f"{len(found)} problems in generated code:\n" + "\n".join(found[:60])


# ===== the starters of the Add connection forms =====


def starter_codes() -> list[Code]:
    """Each starter in each way it signs in, with the boxes that run after it in the same names."""
    out = []
    for template in TEMPLATES:
        ways = template.sign_ins or ((template.label, "", template.code),)
        for label, _, text in ways:
            known = RUN_NAMES
            if template.catalog_language == "python" and template.catalog_command:
                text += "\n" + template.catalog_command
            if template.read_command:
                text += "\n" + template.read_command
                known |= READ_NAMES
            out.append(Code(f"{template.id} ({label})", text, known))
    return out


def kind_codes() -> list[Code]:
    """The kinds' own modules, asked directly (a way a starter might not list)."""
    out = [
        Code(f"sql_server {template} ({label})", text)
        for template in sorted(sql_server.TEMPLATES)
        for label, _, text in sql_server.sign_ins(template)
    ]
    out += [
        Code(f"dataverse ({label})", text + "\n" + dataverse.CATALOG) for label, _, text in dataverse.SIGN_INS
    ]
    for kind, ways in (
        ("onelake", lakes.ONELAKE_SIGN_INS),
        ("datalake", lakes.DATALAKE_SIGN_INS),
        ("delta", lakes.DELTA_SIGN_INS),
        ("sharepoint", sharepoint.LISTS_SIGN_INS),
        ("sharepoint_docs", sharepoint.DOCS_SIGN_INS),
    ):
        out += [
            Code(f"{kind} ({label})", f"{text}\n{lakes.CATALOG}\n{lakes.READ}\n", RUN_NAMES | READ_NAMES)
            for label, _, text in ways
        ]
    return out


def test_every_starter_in_every_way_it_signs_in_is_clean_code(tmp_path: Path) -> None:
    codes = starter_codes()
    assert len(codes) > 60 and {"sqlserver", "dataverse", "onelake", "sharepoint", "trino"} <= {
        t.id for t in TEMPLATES
    }
    found = problems(codes, tmp_path)
    assert not found, said(found)


def test_each_kinds_own_code_is_clean(tmp_path: Path) -> None:
    found = problems(kind_codes(), tmp_path)
    assert not found, said(found)


def test_a_lake_carries_only_what_it_reads() -> None:
    """OneLake's class names its SQL endpoint's client, so only OneLake's code carries it (and `struct`,
    which packs its token); no lake reads a workbook, so none imports zipfile."""
    onelake, datalake = lakes.ONELAKE_SIGN_INS[0][2], lakes.DATALAKE_SIGN_INS[0][2]
    assert "class OneLake(Lake)" in onelake and "class Tds" in onelake and "import struct\n" in onelake
    assert "class OneLake" not in datalake and "import struct" not in datalake
    assert "class OneLake" not in lakes.DELTA_LOCAL and "class DeltaLake(Lake)" in lakes.DELTA_LOCAL
    assert not any("import zipfile" in text for _, _, text in lakes.ONELAKE_SIGN_INS + lakes.DELTA_SIGN_INS)
    assert "import zipfile\n" in sharepoint.DOCS


# ===== the starter pack's Python blades =====


def test_the_starter_packs_python_blades_are_clean_code(tmp_path: Path) -> None:
    codes = []
    for file in sorted(STARTERS.glob("*.blade.py")):
        blade = read_blade(file.read_text(encoding="utf-8"))
        if blade["kind"] == "snippet":  # a cell's text with <<placeholders>>: DAX, HTML, a piece of a cell
            continue
        codes.append(Code(file.name, blade["code"]))
    assert len(codes) > 20
    found = problems(codes, tmp_path)
    assert not found, said(found)


# ===== Add API's made file =====

ORDERS: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Orders", "version": "1.0", "description": "A made-up orders service."},
    "servers": [{"url": "https://orders.example.com/v1"}],
    "paths": {
        "/orders": {
            "get": {
                "operationId": "listOrders",
                "parameters": [
                    {"name": "status", "in": "query", "schema": {"type": "string"}},
                    {"name": "pageToken", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {
                        "description": "The orders.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "items": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Order"},
                                        },
                                        "nextPageToken": {"type": "string"},
                                    },
                                }
                            }
                        },
                    }
                },
            },
            "post": {
                "operationId": "createOrder",
                "requestBody": {
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}}
                },
                "responses": {"201": {"description": "Made."}},
            },
        },
        "/orders/{order_id}": {
            "get": {
                "operationId": "getOrder",
                "parameters": [
                    {"name": "order_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                ],
                "responses": {
                    "200": {
                        "description": "One order.",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}},
                    }
                },
            }
        },
    },
    "components": {
        "schemas": {
            "Order": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer"},
                    "amount": {"type": "number"},
                    "status": {"type": "string"},
                },
            }
        }
    },
}


def every_auth() -> list[dict[str, str]]:
    """Each auth type, and each choice of each of its settings that has choices (a flow, a mode, a place)."""
    out: list[dict[str, str]] = []
    for kind in apis.AUTH_TYPES.values():
        out.append({"type": kind.id})
        for setting in kind.settings:
            out += [{"type": kind.id, setting.id: value} for value, _ in setting.choices if value]
    return out


def test_add_apis_made_file_is_clean_code_in_every_auth_type(tmp_path: Path) -> None:
    spec = apis.parse_spec(ORDERS, "https://orders.example.com/openapi.json")
    assert len(spec.operations) == 3
    codes = []
    for auth in every_auth():
        made = dataclasses.replace(spec, auth=apis.check_auth(auth))
        text = api_clients.write(made, apis.names_for(spec.title))
        codes.append(
            Code("API_Orders.py " + " ".join(f"{k}={v}" for k, v in auth.items()), text, frozenset())
        )
    assert {"none", "api_key", "bearer", "basic", "oauth2", "jwt", "sigv4", "google", "firebase"} <= {
        a["type"] for a in every_auth()
    }
    found = problems(codes, tmp_path)
    assert not found, said(found)


# ===== connections.py, as the project scaffold writes it =====

SAVED = ("postgres", "sqlserver", "dataverse", "onelake", "delta", "sharepoint", "csv")


def test_connections_py_for_saved_connections_is_clean_code(client: TestClient, tmp_path: Path) -> None:
    """A connection of each family saved from its starter, then connections.py as an export and the
    project scaffold make it (services/script_export.py connections_code, domain/scaffold.py)."""
    by_id = {t.id: t for t in TEMPLATES}
    names = []
    for template_id in SAVED:
        template = by_id[template_id]
        body = {
            "name": f"Made up {template_id}",
            "kind": template.kind,
            "template": template.id,
            "dialect": template.dialect,
            "code": template.code,
        }
        saved = client.post("/connections", json=body, headers=AUTH)
        assert saved.status_code == 200, saved.text
        names.append(body["name"])
    made = client.app.state.ctx.script_exports.connections_code(names)  # type: ignore[attr-defined]
    text = scaffold.connections_py(str(made["text"]))
    assert all(f"connection: {name}" in text for name in names)
    folder = tmp_path / "lint"
    folder.mkdir()
    # `adapter` is the file beside it in a project; everything else it names it must define or import.
    codes = [Code("connections.py", text, frozenset())]
    # The same connections as a local sandbox API's export carries them, with and without the sandbox's copy.
    for sandbox in (False, True):
        exported = api_targets.connections_module(str(made["text"]), sandbox, names)
        codes.append(Code(f"an export's connections.py (sandbox {sandbox})", exported, frozenset()))
    found = problems(codes, folder)
    assert not found, said(found)
    # Only what its own connections read is imported: the one list of a made file's head, cut to them.
    assert (
        "\nimport shlex\n" not in text and "\nimport os\n" in text and text.count("\nimport adapter\n") == 1
    )


def test_the_sandbox_mirror_is_clean_code(tmp_path: Path) -> None:
    tables: dict[str, dict[str, Any]] = {
        "customers": {
            "source": {"kind": "connection", "connection": "Shop", "table": "customers"},
            "client": {"connection": "Shop", "kind": "sql", "dialect": "sqlite"},
            "key": ["customer_id"],
        },
        "notes": {"source": {"kind": "file", "file": "notes.csv"}, "client": {}},
    }
    data = scaffold.sandbox_data_py(tables, "2026-11-22T10:00:00Z", ["before the demo"])
    mirror = scaffold.sandbox_connections_py(tables)
    assert data is not None and mirror is not None
    codes = [Code("sandbox_data.py", data, frozenset()), Code("sandbox_connections.py", mirror, frozenset())]
    found = problems(codes, tmp_path)
    assert not found, said(found)


# ===== a made file's imports cut to the ones it reads (domain/script_runtime.py) =====


def test_only_the_imports_a_made_file_reads_are_kept() -> None:
    text = (
        '"""Made."""\n\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "import os\n"
        "import os\n"  # said twice: once is enough
        "import re\n"
        "import shlex\n"
        "import urllib.error\n"
        "import urllib.request\n"
        "import duckdb  # noqa: F401 (a package this needs)\n"
        "from collections.abc import Callable\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n\n"
        "def connect():\n"
        "    import json\n"  # the function's own: the top one is not read by it
        "    from pathlib import Path\n\n"
        "    return json.loads(Path(os.environ['MADE_UP']).read_text())\n\n\n"
        "def fetch(url: str) -> Any:\n"
        "    return urllib.request.urlopen(url)\n\n\n"
        "MADE: dict[str, Callable[[], Any]] = {'x': lambda re: re}\n"  # a lambda's own argument
    )
    made = script_runtime.without_unused_imports(text)
    kept = [line for line in made.split("\n") if line.startswith(("import ", "from "))]
    assert kept == [
        "from __future__ import annotations",
        "import os",
        "import urllib.request",
        "import duckdb  # noqa: F401 (a package this needs)",
        "from collections.abc import Callable",
        "from typing import Any",
    ]
    compile(made, "made.py", "exec")
    assert script_runtime.without_unused_imports(made) == made  # nothing more to take
    # A package read past what any import names keeps every import of it; text that does not parse is left.
    both = "import os.path\nimport os.errno\nprint(os.getcwd())\n"
    assert script_runtime.without_unused_imports(both) == both
    assert script_runtime.without_unused_imports("import os\ndef (:\n") == "import os\ndef (:\n"
    # Several names on a line, a star and anything under an `if` or a `try` are never touched.
    odd = "import json, re\nfrom os import *\ntry:\n    import tomllib\nexcept ImportError:\n    pass\n"
    assert script_runtime.without_unused_imports(odd) == odd
