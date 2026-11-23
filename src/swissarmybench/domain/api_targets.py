"""A local sandbox API exported for its framework target (the owner, 2026-11-21: "select from these options based on
the framework target, and get API code that is ready to go for that platform. Start with fast API, azure function app
Linux python, or lambda Linux python; extensions can add new frameworks in the future").

Every target is data: an id, its words, and `render(bundle)`: the project's files for that platform, the
fewest that run it (Plans/adapter.plan.md "The exported project: the fewest files"): API.py as it is (the
endpoints never change), adapter.py, connections.py, requirements.txt, README.md and the platform's one framework
file, which carries sab_api (server/api_runtime.py: what API.py imports, the one request handler every target
calls) folded in as a module of its own; api_adapter.py only when API.py calls another API. connections.py is each connection the endpoints use as its own portable code (the export's
connections, as a script export writes them: its variables read from the environment, a vault's secrets by the
platform's managed identity), so deploying is credentials, not a rewrite ("Export targets use the REAL client
code"). `connection("Sandbox")` (a table from a file, or made empty) is a copy of the sandbox, bundled as
data/sandbox.duckdb only on the user's tick, copied to the platform's temporary folder at start (their package
folders are read-only). No secret goes in any file: README.md lists the variables to set.

  fastapi          main.py (a route per endpoint, its OpenAPI document inside)
  azure_functions  function_app.py (the Python v2 model: @app.route per endpoint), and the platform's own
                   host.json (no route prefix) and .funcignore
  aws_lambda       lambda_function.py (API Gateway's REST and HTTP events, Function URLs), and SAM's own
                   template.yaml (an HTTP API, Python 3.12 on Linux)

Pure text: standard library only.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import script_runtime

EXPORT_FOLDER = "exports/api"  # the project's made folder: exports/api/<target>/
SANDBOX_FILE = "data/sandbox.duckdb"


@dataclass(frozen=True)
class Route:
    name: str
    method: str
    path: str  # with the base path
    summary: str


@dataclass(frozen=True)
class Bundle:
    """What a target is made from."""

    name: str
    description: str
    api: str  # API.py as it is
    runtime: str  # sab_api.py
    connections: str  # connections.py
    openapi: dict[str, Any]
    routes: tuple[Route, ...]
    base_path: str = ""
    requirements: tuple[str, ...] = ()  # the connections' own
    variables: tuple[str, ...] = ()  # the settings to set where it runs (names only)
    notes: tuple[dict[str, Any], ...] = ()  # what only works on this computer (domain/portability.py)
    sandbox: bool = False  # data/sandbox.duckdb bundled
    uses_sandbox: bool = False  # an endpoint asks for connection("Sandbox")
    adapter: str = ""  # adapter.py (Plans/adapter.plan.md): every data call and payload goes through it
    api_adapter: str = ""  # api_adapter.py (Plans/api-adapter.plan.md): every API call goes through it


@dataclass(frozen=True)
class Target:
    id: str
    label: str
    words: str  # one line: what it makes
    render: Callable[[Bundle], dict[str, str]]
    run_hint: str = ""  # how to run it on this computer, for the README and the page
    extension: str = ""  # the extension that adds it ("" for the base's)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "words": self.words,
            "run": self.run_hint,
            "extension": self.extension,
        }


# ===== what every target shares =====

_SANDBOX_COPY = """

# ===== connection("Sandbox"): the sandbox's tables, bundled as data/sandbox.duckdb =====
# The platform's package folder is read-only: the copy works in a temporary folder, so writes last until the
# instance is recycled. For data that lasts, point an endpoint at a real connection instead.
import hashlib as _hashlib
import shutil as _shutil
import tempfile as _tempfile
from pathlib import Path as _Path

_BUNDLED = _Path(__file__).resolve().parent / "data" / "sandbox.duckdb"
_SANDBOX = []


def _sandbox():
    if not _SANDBOX:
        import duckdb

        if not _BUNDLED.exists():
            raise RuntimeError("This export has no sandbox copy (data/sandbox.duckdb): export it with its rows.")
        # The working copy is this bundle's own (named by where the bundle is and when it was made): another
        # export on the same computer, or this one exported again, never reads an older copy's rows.
        made = _BUNDLED.stat()
        mark = _hashlib.sha256(f"{_BUNDLED}|{made.st_size}|{made.st_mtime_ns}".encode()).hexdigest()[:12]
        working = _Path(
            os.environ.get("SAB_SANDBOX_PATH") or _Path(_tempfile.gettempdir()) / f"sab_sandbox_{mark}.duckdb"
        )
        if not working.exists():
            _shutil.copyfile(_BUNDLED, working)
        _SANDBOX.append(duckdb.connect(str(working)))
    return _SANDBOX[0]
"""


def connections_module(registry: str, uses_sandbox: bool, names: Sequence[str]) -> str:
    """connections.py: the connections' code (`registry`: the script export's pieces and their MADE and
    connection()), then the adapter pointed at it: each name's own client wrapped in its backend
    (adapter.source_from), so connection(name) in API.py is the adapter's calls on the real source, the
    same code that ran on the sandbox."""
    head = (
        '"""Written by Swiss Army Bench: each connection the API\'s endpoints use, as its own code (its passwords\n'
        "read from the environment or a key vault, never written here). Change the connections in the app and\n"
        'export again, not this file."""\n\n'
        "from __future__ import annotations\n\nimport os\n\nimport adapter\n"
    )
    body = registry.strip("\n")
    hook = [
        "",
        "",
        "def _source(name: str):",
        '    """The adapter\'s source for a connection: its own client, in its backend."""',
    ]
    if uses_sandbox:
        hook += [
            '    if name.strip().casefold() == "sandbox":',
            '        return adapter.source_from(_sandbox(), name="Sandbox")',
        ]
    if names:
        hook += ["    return adapter.source_from(connection(name), name=name)"]
    else:
        hook += ['    raise RuntimeError(f"This export has no connection named {name}.")']
    # connection(name) in API.py is then the adapter's Connection over it (sab_api's own fallback).
    hook += ["", "", "adapter.use(_source)", ""]
    whole = head + ("\n\n" + body if body else "") + (_SANDBOX_COPY if uses_sandbox else "") + "\n".join(hook)
    return script_runtime.without_unused_imports(whole)  # the head's one list of imports: only those read


NO_ROWS = (
    'connection("Sandbox") has no rows in this export: its endpoints answer an error there until it is '
    "exported with the sandbox's rows, or they use a real connection."
)


def warnings(bundle: Bundle) -> list[str]:
    """What the person exporting should know before deploying, each one sentence (the dialog's amber notes,
    the agent's answer; README.md's checklist says the same)."""
    return [NO_ROWS] if bundle.uses_sandbox and not bundle.sandbox else []


def requirements_txt(base: Sequence[str], bundle: Bundle) -> str:
    wanted = list(
        dict.fromkeys(
            [
                *base,
                *bundle.requirements,
                *(["duckdb>=1.1"] if bundle.uses_sandbox or bundle.adapter else []),
                *(["pyarrow>=15"] if bundle.adapter else []),  # the adapter's Arrow
            ]
        )
    )
    return "\n".join(wanted) + "\n"


def _checklist(bundle: Bundle, where: str) -> str:
    lines = [
        "## Before it goes live",
        "",
        f"- Set each variable below in the {where} (never in a file of this folder): a key vault reference for a",
        "  password, so the platform's managed identity reads it.",
        "- The connections sign in without a person: a managed identity, an app registration or a vault; nothing",
        "  here needs an installed driver, a desktop or this computer's disk.",
        "- Put the API behind its platform's sign-in (see Deploy): it reads and writes real data once deployed.",
    ]
    if bundle.uses_sandbox:
        lines.append(
            "- `connection(\"Sandbox\")` is a copy of the sandbox"
            + (" (data/sandbox.duckdb): made-up test data, writes reset when the instance recycles."
               if bundle.sandbox else ": it was exported without its rows, so those endpoints answer an error.")
        )  # fmt: skip
    for note in bundle.notes:
        lines.append(
            f"- Only works on your machine: {note.get('reason', '')}. {note.get('instead', '')}".rstrip()
        )
    listed = [f"- `{v}`" for v in bundle.variables] or ["None."]
    lines += ["", "## Variables to set", "", *listed, ""]
    return "\n".join(lines)


def _endpoints_table(bundle: Bundle) -> str:
    rows = ["| Method | Path | Function | What |", "|---|---|---|---|"]
    rows += [f"| {r.method} | `{r.path}` | `{r.name}` | {r.summary} |" for r in bundle.routes]
    return "\n".join(rows)


def _readme(bundle: Bundle, title: str, files: str, run: str, deploy: str, where: str) -> str:
    head = f"# {bundle.name}: {title}\n\n" + (f"{bundle.description}\n\n" if bundle.description else "")
    return (
        head
        + "Exported by Swiss Army Bench from the project's API.py (a made folder: export again rather than edit\n"
        "it; a file edited by hand is kept from the next export until you replace it).\n\n"
        f"## The endpoints\n\n{_endpoints_table(bundle)}\n\n"
        f"## The files\n\n{files}\n\n"
        f"## Run it on this computer\n\n{run}\n\n"
        f"## Deploy\n\n{deploy}\n\n" + _checklist(bundle, where)
    )


_COMMON_FILES = (
    "- `API.py`: the endpoints, as written in the app (never changed by an export).\n"
    "- `adapter.py`: the adapter every read, write and payload goes through (Arrow in and out).\n"
    "- `connections.py`: each connection's own code, a section each; `connection(name)` is the adapter's calls\n"
    "  on it."
)
_API_ADAPTER_FILE = "\n- `api_adapter.py`: every call API.py makes to another API: `run(action, inputs)` and its one envelope."


def calls_apis(api: str) -> bool:
    """API.py calls another API through api_adapter (only then does the export carry it)."""
    return "api_adapter" in api


def _files_words(bundle: Bundle, own: str) -> str:
    return _COMMON_FILES + (_API_ADAPTER_FILE if bundle.api_adapter and calls_apis(bundle.api) else "") + own


def _common(bundle: Bundle) -> dict[str, str]:
    return {
        "API.py": bundle.api,
        **({"adapter.py": bundle.adapter} if bundle.adapter else {}),
        **({"api_adapter.py": bundle.api_adapter} if bundle.api_adapter and calls_apis(bundle.api) else {}),
        "connections.py": bundle.connections,
    }


def _literal(text: str) -> str:
    """Text as a Python string that reads as the text: a raw triple-quoted string when it can be."""
    if "'''" not in text and not text.endswith(("\\", "'")) and "\r" not in text:
        return "r'''" + text + "'''"
    return repr(text)


def runtime_module(bundle: Bundle) -> str:
    """sab_api folded into the framework file: what API.py imports (`from sab_api import endpoint, ...`) made a
    module of its own from its text and registered before connections.py and API.py are imported, so the
    export needs no sab_api.py and its names never meet the framework file's."""
    return (
        "# ===== sab_api: @endpoint, connection(), records(), ApiError and the one request handler, as API.py\n"
        "# imports them (Swiss Army Bench's runtime, folded in so the export is the fewest files) =====\n"
        "import sys as _sys\nimport types as _types\n\n"
        f"_SAB_API = {_literal(bundle.runtime)}\n"
        'sab_api = _types.ModuleType("sab_api")\n'
        "sab_api.__file__ = __file__\n"
        '_sys.modules["sab_api"] = sab_api\n'
        'exec(compile(_SAB_API, "sab_api", "exec"), sab_api.__dict__)  # noqa: S102 (the runtime above)\n\n'
    )


_IMPORTS = (
    "import connections  # noqa: F401  (connection() gives each connection's own client)\nimport sab_api\n"
)


def _with_runtime(text: str, bundle: Bundle) -> str:
    assert _IMPORTS in text  # noqa: S101 (each target's own text)
    return text.replace(
        _IMPORTS, runtime_module(bundle) + "import connections  # noqa: F401,E402  (each connection)\n", 1
    )


def _python_name(name: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name) or "endpoint"


# ===== FastAPI =====


def render_fastapi(bundle: Bundle) -> dict[str, str]:
    routes = []
    for r in bundle.routes:
        fn = _python_name(r.name)
        routes.append(
            f"@app.{r.method.lower()}({r.path!r}, operation_id={r.name!r}, summary={r.summary!r})\n"
            f"async def {fn}(request: Request) -> Response:\n"
            f"    return await _answer(request)\n"
        )
    main = (
        f'"""{bundle.name}: the FastAPI app (exported by Swiss Army Bench). Run: uvicorn main:app"""\n\n'
        "from __future__ import annotations\n\n"
        "import json\n\n"
        "from fastapi import FastAPI, Request, Response\n"
        "from starlette.concurrency import run_in_threadpool\n\n"
        "import connections  # noqa: F401  (connection() gives each connection's own client)\n"
        "import sab_api\n"
        "import API  # noqa: F401  (its @endpoint functions register themselves)\n\n"
        f"sab_api.BASE_PATH = {bundle.base_path!r}\n"
        f"app = FastAPI(title={bundle.name!r}, description={bundle.description!r})\n"
        f"OPENAPI = json.loads({_literal(json.dumps(bundle.openapi, indent=1, sort_keys=True))})\n"
        "app.openapi = lambda: OPENAPI  # type: ignore[method-assign]\n\n\n"
        "async def _answer(request: Request) -> Response:\n"
        "    body = await request.body()\n"
        "    status, headers, payload = await run_in_threadpool(\n"
        "        sab_api.handle, request.method, request.url.path, dict(request.query_params), body\n"
        "    )\n"
        "    return Response(payload, status, headers=headers)\n\n\n" + "\n\n".join(routes)
    )
    readme = _readme(
        bundle,
        "FastAPI",
        _files_words(
            bundle,
            "\n- `main.py`: the FastAPI app, a route per endpoint, its OpenAPI document.\n- `requirements.txt`.",
        ),
        "```\npython -m venv .venv\n.venv/bin/pip install -r requirements.txt\n.venv/bin/uvicorn main:app --port 8000\n```\n"
        "Then http://127.0.0.1:8000/docs.",
        "Any host that runs a Python web app on Linux: Azure App Service (`az webapp up --runtime PYTHON:3.12`,\n"
        "startup command `uvicorn main:app --host 0.0.0.0 --port 8000`), a container (`uvicorn main:app --host\n"
        "0.0.0.0`), or a hosted Streamlit app's own server beside it. Put it behind the host's sign-in (App Service\n"
        "Authentication, an API gateway).",
        "host's application settings",
    )
    return _common(bundle) | {
        "main.py": _with_runtime(main, bundle),
        "requirements.txt": requirements_txt(("fastapi>=0.110", "uvicorn>=0.29"), bundle),
        "README.md": readme,
    }


# ===== Azure Functions (Linux, Python, the v2 programming model) =====


def render_azure(bundle: Bundle) -> dict[str, str]:
    functions = []
    for r in bundle.routes:
        fn = _python_name(r.name)
        route = r.path.lstrip("/")
        functions.append(
            f"@app.function_name(name={fn!r})\n"
            f"@app.route(route={route!r}, methods=[{r.method!r}])\n"
            f"def {fn}(req: func.HttpRequest) -> func.HttpResponse:\n"
            f'    """{r.summary or r.name}"""\n'
            f"    return _answer(req)\n"
        )
    app = (
        f'"""{bundle.name}: an Azure Functions app (Python, the v2 programming model; exported by Swiss Army\n'
        'Bench). Run here: func start. Each endpoint is one HTTP function; the key is the function app\'s."""\n\n'
        "import urllib.parse\n\n"
        "import azure.functions as func\n\n"
        "import connections  # noqa: F401  (connection() gives each connection's own client)\n"
        "import sab_api\n"
        "import API  # noqa: F401  (its @endpoint functions register themselves)\n\n"
        f"sab_api.BASE_PATH = {bundle.base_path!r}\n"
        "app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)\n\n\n"
        "def _answer(req: func.HttpRequest) -> func.HttpResponse:\n"
        "    path = urllib.parse.urlsplit(req.url).path\n"
        "    status, headers, payload = sab_api.handle(req.method, path, dict(req.params), req.get_body())\n"
        '    return func.HttpResponse(payload, status_code=status, headers=headers, mimetype=headers.get("Content-Type"))\n\n\n'
        + "\n\n".join(functions)
    )
    host = {
        "version": "2.0",
        "extensions": {"http": {"routePrefix": ""}},
        "extensionBundle": {"id": "Microsoft.Azure.Functions.ExtensionBundle", "version": "[4.*, 5.0.0)"},
        "logging": {"applicationInsights": {"samplingSettings": {"isEnabled": True}}},
    }
    local = {
        "IsEncrypted": False,
        "Values": {"FUNCTIONS_WORKER_RUNTIME": "python", "AzureWebJobsStorage": "UseDevelopmentStorage=true"}
        | {v: "" for v in bundle.variables},
    }
    readme = _readme(
        bundle,
        "Azure Functions (Linux, Python)",
        _files_words(
            bundle,
            "\n- `function_app.py`: one HTTP function per endpoint (`@app.route`).\n"
            "- `host.json`: no route prefix, so the paths are API.py's.\n"
            "- `requirements.txt`.",
        ),
        "With Azure Functions Core Tools 4 (set the variables below in your shell, or in a local.settings.json of\n"
        "your own: it is never deployed):\n\n```\npython -m venv .venv\n.venv/bin/pip install -r requirements.txt\n"
        "func start\n```",
        "```\naz functionapp create --name <app> --resource-group <group> --storage-account <storage> \\\n"
        "  --consumption-plan-location <region> --runtime python --runtime-version 3.12 --functions-version 4 \\\n"
        "  --os-type Linux\nfunc azure functionapp publish <app>\n```\n"
        "Turn on its managed identity (`az functionapp identity assign`) for the key vault and the connections; "
        "callers send the function key (`?code=` or `x-functions-key`), or put Easy Auth in front.",
        "function app's Application settings",
    )
    del local  # the variables' names are README.md's list (a local.settings.json is the user's own)
    return _common(bundle) | {
        "function_app.py": _with_runtime(app, bundle),
        "host.json": json.dumps(host, indent=2) + "\n",
        "requirements.txt": requirements_txt(("azure-functions",), bundle),
        "README.md": readme,
        ".funcignore": ".venv\n__pycache__\nlocal.settings.json\n",
    }


# ===== AWS Lambda (Linux, Python) =====


def render_lambda(bundle: Bundle) -> dict[str, str]:
    handler = (
        f'"""{bundle.name}: an AWS Lambda function (Python, Linux; exported by Swiss Army Bench). One handler for every\n'
        'endpoint: API Gateway\'s REST (payload 1.0) and HTTP (2.0) events and Lambda function URLs."""\n\n'
        "import base64\n\n"
        "import connections  # noqa: F401  (connection() gives each connection's own client)\n"
        "import sab_api\n"
        "import API  # noqa: F401  (its @endpoint functions register themselves)\n\n"
        f"sab_api.BASE_PATH = {bundle.base_path!r}\n\n\n"
        "def handler(event, context):\n"
        '    context_of = event.get("requestContext") or {}\n'
        '    method = (context_of.get("http") or {}).get("method") or event.get("httpMethod") or "GET"\n'
        '    path = event.get("rawPath") or event.get("path") or "/"\n'
        '    stage = context_of.get("stage")\n'
        '    if event.get("rawPath") and stage and stage != "$default" and path.startswith(f"/{stage}/"):\n'
        "        path = path[len(stage) + 1 :]\n"
        '    query = event.get("queryStringParameters") or {}\n'
        '    body = event.get("body")\n'
        '    if body is not None and event.get("isBase64Encoded"):\n'
        "        body = base64.b64decode(body)\n"
        "    status, headers, payload = sab_api.handle(method, path, query, body)\n"
        '    kind = headers.get("Content-Type", "application/json")\n'
        '    if kind.startswith(("application/json", "text/")):\n'
        '        return {"statusCode": status, "headers": headers, "body": payload.decode("utf-8"), "isBase64Encoded": False}\n'
        "    # A file to save that is not text (an Excel workbook): API Gateway takes it as base64.\n"
        '    packed = base64.b64encode(payload).decode("ascii")\n'
        '    return {"statusCode": status, "headers": headers, "body": packed, "isBase64Encoded": True}\n'
    )
    env = "\n".join(f'          {v}: ""' for v in bundle.variables) or '          SAB_NOTHING_TO_SET: ""'
    template = (
        "AWSTemplateFormatVersion: '2010-09-09'\n"
        "Transform: AWS::Serverless-2016-10-31\n"
        f"Description: {json.dumps(bundle.name)}\n\n"
        "Resources:\n"
        "  Api:\n"
        "    Type: AWS::Serverless::Function\n"
        "    Properties:\n"
        "      CodeUri: .\n"
        "      Handler: lambda_function.handler\n"
        "      Runtime: python3.12\n"
        "      Architectures: [x86_64]\n"
        "      Timeout: 30\n"
        "      MemorySize: 512\n"
        "      Environment:\n"
        "        Variables:\n"
        f"{env}\n"
        "      Events:\n"
        "        Http:\n"
        "          Type: HttpApi\n"
        "          Properties:\n"
        "            Path: /{proxy+}\n"
        "            Method: ANY\n\n"
        "Outputs:\n"
        "  Address:\n"
        "    Value: !Sub 'https://${ServerlessHttpApi}.execute-api.${AWS::Region}.amazonaws.com'\n"
    )
    readme = _readme(
        bundle,
        "AWS Lambda (Linux, Python)",
        _files_words(
            bundle,
            "\n- `lambda_function.py`: the one handler (API Gateway REST and HTTP events, function URLs).\n"
            "- `template.yaml`: AWS SAM: the function (Python 3.12) and an HTTP API in front of it.\n"
            "- `requirements.txt`.",
        ),
        "With the AWS SAM CLI and Docker:\n\n```\nsam build\nsam local start-api\n```",
        "```\nsam build\nsam deploy --guided\n```\n"
        "Give the function's role what the connections need (Secrets Manager or Parameter Store for a password, set\n"
        "as its variables); add an authorizer (IAM, JWT or Cognito) to the HTTP API before it holds real data.",
        "function's environment (template.yaml's Variables, or the console)",
    )
    return _common(bundle) | {
        "lambda_function.py": _with_runtime(handler, bundle),
        "template.yaml": template,
        "requirements.txt": requirements_txt((), bundle),
        "README.md": readme,
    }


TARGETS: dict[str, Target] = {
    "fastapi": Target(
        "fastapi", "FastAPI", "main.py, a route per endpoint, uvicorn", render_fastapi, "uvicorn main:app"
    ),
    "azure_functions": Target(
        "azure_functions",
        "Azure Functions (Linux, Python)",
        "function_app.py on the v2 model, host.json, .funcignore",
        render_azure,
        "func start",
    ),
    "aws_lambda": Target(
        "aws_lambda",
        "AWS Lambda (Linux, Python)",
        "lambda_function.py for API Gateway and function URLs, a SAM template.yaml",
        render_lambda,
        "sam local start-api",
    ),
}


@dataclass
class Registry:
    """The targets: the base's three, then what each extension that is on adds (its API_TARGETS)."""

    targets: dict[str, Target] = field(default_factory=lambda: dict(TARGETS))

    def add(self, target: Target) -> None:
        self.targets[target.id] = target

    def get(self, wanted: str) -> Target:
        found = self.targets.get(wanted)
        if found is None:
            raise ValueError(f"The target is one of: {', '.join(self.targets)}.")
        return found

    def ids(self) -> list[str]:
        return list(self.targets)


def from_extension(raw: Mapping[str, Any], extension: str) -> Target:
    """An extension's API_TARGETS item: {id, label, words, render, run}."""
    render = raw.get("render")
    if not callable(render) or not str(raw.get("id") or "").strip():
        raise ValueError(f"{extension}'s API target needs an id and a render(bundle).")
    return Target(
        str(raw["id"]), str(raw.get("label") or raw["id"]), str(raw.get("words") or ""), render,
        str(raw.get("run") or ""), extension,
    )  # fmt: skip
