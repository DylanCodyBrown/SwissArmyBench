# ruff: noqa: E501 (the recorded programs' lines are written as the stand-ins run them)
"""Recorded stand-ins for the Power Platform tools, written by the tests onto a PATH of their own.

`install(folder, tools=...)` writes one small program per tool (pa, pac, npm, npx, node), each answering
the commands the Power Apps extension runs with recorded, made-up output in the shape the real tools print
(docs/verified.md: the Power Apps CLI 1.4.2's JSON, the Power Platform CLI's tables). They keep a little
state of their own (signed in or not) in the folder, and change a code app's folder as the real ones do
(the template, power.config.json, the generated models and services, .power/schemas). Never a real tenant:
every name, id and address is made up (Contoso, Fabrikam and Northwind are Microsoft's made-up companies).
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

ENVIRONMENT_ID = "11111111-2222-3333-4444-555555555555"
OTHER_ENVIRONMENT_ID = "66666666-7777-8888-9999-000000000000"
APP_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TOKEN = "made-up-token-" + "x" * 60  # what the fake pac auth token prints: never a real one
ACCOUNT = "maker@contoso.example"

CONNECTORS = [
    {
        "id": "/providers/Microsoft.PowerApps/apis/shared_contosotasks",
        "name": "shared_contosotasks",
        "displayName": "Contoso Tasks",
        "description": "Made-up tasks service: lists, tasks and owners.",
        "isTabular": False,
    },
    {
        "id": "/providers/Microsoft.PowerApps/apis/shared_fabrikamtickets",
        "name": "shared_fabrikamtickets",
        "displayName": "Fabrikam Tickets",
        "description": "Made-up help desk tickets, as tables.",
        "isTabular": True,
    },
    {
        "id": "/providers/Microsoft.PowerApps/apis/shared_northwindorders",
        "name": "shared_northwindorders",
        "displayName": "Northwind Orders",
        "description": "Made-up orders and customers.",
        "isTabular": True,
    },
]
CONNECTIONS = [
    {
        "name": "c0ffee00000011112222333344445555",
        "properties": {
            "displayName": "maker@contoso.example",
            "apiId": "/providers/Microsoft.PowerApps/apis/shared_contosotasks",
            "statuses": [{"status": "Connected"}],
        },
    },
    {
        "name": "beef0000000011112222333344445555",
        "properties": {
            "displayName": "Fabrikam help desk",
            "apiId": "/providers/Microsoft.PowerApps/apis/shared_fabrikamtickets",
            "statuses": [{"status": "Connected"}],
        },
    },
]


def tasks_swagger() -> dict[str, object]:
    """Contoso Tasks' made-up definition (Swagger 2.0, as connectors are), one operation internal."""
    return {
        "swagger": "2.0",
        "info": {"title": "Contoso Tasks", "version": "1.0", "description": "Made-up tasks."},
        "host": "tasks.contoso.example",
        "basePath": "/",
        "schemes": ["https"],
        "paths": {
            "/{connectionId}/lists/{list}/tasks": {
                "get": {
                    "operationId": "ListTasks",
                    "summary": "List the tasks of a list",
                    "tags": ["Tasks"],
                    "parameters": [
                        {
                            "name": "connectionId",
                            "in": "path",
                            "required": True,
                            "type": "string",
                            "x-ms-visibility": "internal",
                        },
                        {
                            "name": "list",
                            "in": "path",
                            "required": True,
                            "type": "string",
                            "description": "The list's id",
                        },
                        {"name": "top", "in": "query", "type": "integer", "default": 20},
                    ],
                    "responses": {
                        "200": {
                            "description": "The tasks",
                            "schema": {"type": "array", "items": {"$ref": "#/definitions/Task"}},
                        }
                    },
                },
                "post": {
                    "operationId": "CreateTask",
                    "summary": "Add a task",
                    "tags": ["Tasks"],
                    "parameters": [
                        {"name": "connectionId", "in": "path", "required": True, "type": "string"},
                        {"name": "list", "in": "path", "required": True, "type": "string"},
                        {
                            "name": "body",
                            "in": "body",
                            "required": True,
                            "schema": {"$ref": "#/definitions/Task"},
                        },
                    ],
                    "responses": {"201": {"description": "Made", "schema": {"$ref": "#/definitions/Task"}}},
                },
            },
            "/{connectionId}/internal/ping": {
                "get": {
                    "operationId": "Ping",
                    "x-ms-visibility": "internal",
                    "parameters": [
                        {"name": "connectionId", "in": "path", "required": True, "type": "string"}
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
        "definitions": {
            "Task": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string", "example": "Order more made-up widgets"},
                    "done": {"type": "boolean"},
                    "owner": {"type": "string", "format": "email"},
                },
            }
        },
    }


def aligned(header: list[str], rows: list[list[str]]) -> str:
    """A table as the Power Platform CLI prints one: each column as wide as its longest cell, two spaces
    between columns."""
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]

    def line(cells: list[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)).rstrip()

    return "\n".join([line(header), *(line(r) for r in rows)]) + "\n"


ENV_LIST = f"Connected as {ACCOUNT}\n\n" + aligned(
    ["Active", "Display Name", "Environment ID", "Environment URL", "Unique Name"],
    [
        [
            "*",
            "Contoso (default)",
            ENVIRONMENT_ID,
            "https://contoso-made-up.crm.dynamics.com/",
            "unq11111111",
        ],
        [
            "",
            "Contoso Test",
            OTHER_ENVIRONMENT_ID,
            "https://contoso-test-made-up.crm.dynamics.com/",
            "unq66666666",
        ],
    ],
)
AUTH_LIST = aligned(
    ["Index", "Active", "Kind", "Name", "Friendly Name", "Url", "User", "Cloud", "Type"],
    [
        [
            "[1]",
            "*",
            "UNIVERSAL",
            "",
            "Contoso (default)",
            "https://contoso-made-up.crm.dynamics.com/",
            ACCOUNT,
            "Public",
            "User",
        ],
        [
            "[2]",
            "",
            "UNIVERSAL",
            "",
            "Contoso Test",
            "https://contoso-test-made-up.crm.dynamics.com/",
            ACCOUNT,
            "Public",
            "User",
        ],
    ],
)

FAKE = r"""
import json, os, sys, time, http.server, socketserver, threading
from pathlib import Path

STATE = Path(__file__).with_name("fake_state.json")
RECORDED = json.loads(Path(__file__).with_name("recorded.json").read_text())


def state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"signed_in": True}


def save(s):
    STATE.write_text(json.dumps(s))


def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        return args[i + 1] if i + 1 < len(args) else default
    return default


def opts(args, name):
    return [args[i + 1] for i, a in enumerate(args) if a == name and i + 1 < len(args)]


def log(args):
    with Path(__file__).with_name("calls.log").open("a") as out:
        out.write(json.dumps(args) + "\n")


def config():
    return json.loads(Path("power.config.json").read_text())


def write_config(c):
    Path("power.config.json").write_text(json.dumps(c, indent=2))


def generated(name):
    models = Path("src/generated/models"); services = Path("src/generated/services")
    models.mkdir(parents=True, exist_ok=True); services.mkdir(parents=True, exist_ok=True)
    (models / f"{name}Model.ts").write_text(f"export interface {name} {{ id: string; name: string }}\n")
    (services / f"{name}Service.ts").write_text(
        f"import type {{ {name} }} from '../models/{name}Model';\n"
        f"export class {name}Service {{ static async getAll(): Promise<{{ data: {name}[] }}> {{ return {{ data: [] }}; }} }}\n"
    )


def pa(args):
    s = state()
    if args[:1] == ["--version"]:
        print("1.4.2"); return 0
    if args[:2] == ["auth", "status"]:
        signed = s.get("signed_in", True)
        print(json.dumps({"signedIn": signed,
                          "activeAccount": {"username": RECORDED["account"], "homeAccountId": "h1"} if signed else None,
                          "accounts": [{"username": RECORDED["account"], "homeAccountId": "h1", "isActive": True}] if signed else []}))
        return 0
    if args[:2] == ["auth", "login"]:
        s["signed_in"] = True; save(s); print("Signed in as " + RECORDED["account"]); return 0
    if args[:2] == ["auth", "switch"]:
        print("Active account: " + opt(args, "--account", "")); return 0
    if not s.get("signed_in", True):
        print("Not signed in. Run `pa auth login` to authenticate."); return 1
    if args[:2] == ["connector", "list"]:
        found = RECORDED["connectors"]
        q = opt(args, "--search")
        if q:
            found = [c for c in found if q.lower() in (c["name"] + c["displayName"]).lower()]
        print(json.dumps(found)); return 0
    if args[:2] == ["connection", "list"]:
        print(json.dumps(RECORDED["connections"])); return 0
    if args[:2] == ["app", "init"]:
        env = opt(args, "--environment-id")
        if env == RECORDED["disabled_environment"]:
            print("Error: Code apps are not enabled in this environment. Ask an administrator."); return 1
        write_config({"version": "1.0", "appId": None, "appDisplayName": opt(args, "--display-name"),
                      "appType": "CodeApp", "description": opt(args, "--description"),
                      "environmentId": env, "buildPath": "./dist", "buildEntryPoint": "index.html",
                      "localAppUrl": "http://localhost:3000", "connectionReferences": {}, "databaseReferences": {}})
        print("Code app initialized."); return 0
    if args[:3] == ["app", "add", "data-source"]:
        c = config(); connector = opt(args, "--connector")
        if connector == "dataverse":
            table = opt(args, "--table"); name = table.capitalize() + "s"
            ref = c["databaseReferences"].setdefault("default.cds", {"dataSources": {}, "environmentVariableName": ""})
            ref["dataSources"][name.lower()] = {"entitySetName": name.lower(), "logicalName": table, "isHidden": False}
            generated(name)
        else:
            if not opt(args, "--connection-id"):
                print("Error: --connection-id is needed in non-interactive mode."); return 1
            api = connector.removeprefix("shared_"); name = api.capitalize()
            ref = c["connectionReferences"].setdefault(api, {"id": "/providers/Microsoft.PowerApps/apis/" + connector,
                "displayName": connector, "dataSources": [], "sharedConnectionId": opt(args, "--connection-id"), "dataSets": {}})
            tables = opts(args, "--table")
            if tables:
                ds = ref["dataSets"].setdefault(opt(args, "--dataset", "default"), {"dataSources": {}})
                for t in tables:
                    ref["dataSources"].append(t); ds["dataSources"][t] = {"tableName": t}
            else:
                ref["dataSources"].append(name)
            generated(name)
            schemas = Path(".power/schemas") / api; schemas.mkdir(parents=True, exist_ok=True)
            if connector == "shared_contosotasks":
                (schemas / f"{api}.Schema.json").write_text(json.dumps(RECORDED["tasks_swagger"]))
        write_config(c); print(f"Added {connector} to the app."); return 0
    if args[:3] == ["app", "remove", "data-source"]:
        c = config(); name = opt(args, "--name")
        for ref in c["databaseReferences"].values():
            ref["dataSources"].pop(name, None)
        for ref in c["connectionReferences"].values():
            if name in ref["dataSources"]:
                ref["dataSources"].remove(name)
        write_config(c); print(f"Removed {name}."); return 0
    if args[:2] == ["app", "push"]:
        if not Path("dist/index.html").exists():
            print("Error: build the app first (dist/index.html is missing)."); return 1
        c = config(); c["appId"] = RECORDED["app_id"]; write_config(c)
        print("Publishing...")
        print(f"App pushed successfully. You can play your app at https://apps.powerapps.com/play/e/{c['environmentId']}/a/{c['appId']}")
        return 0
    if args[:2] == ["app", "list"]:
        apps = [{"appId": RECORDED["app_id"], "name": "Expense Tracker"}, {"appId": "99999999-0000-0000-0000-000000000000", "name": "Another made-up app"}]
        print(json.dumps(apps)); return 0
    print("Unknown command: " + " ".join(args)); return 2


def pac(args):
    if not args:
        print("Microsoft PowerPlatform CLI"); print("Version: 1.47.1+gfa1e2b3"); return 0
    if args[:2] == ["env", "list"]:
        print(RECORDED["env_list"]); return 0
    if args[:2] == ["auth", "list"]:
        print(RECORDED["auth_list"]); return 0
    if args[:2] == ["auth", "select"]:
        print("New default profile: " + opt(args, "--index", "")); return 0
    if args[:2] == ["auth", "create"]:
        print("Authentication profile created"); return 0
    if args[:2] == ["auth", "token"]:
        print(RECORDED["token"]); return 0
    if args[:2] == ["connector", "create"] or args[:2] == ["connector", "update"]:
        for name in ("--api-definition-file", "--api-properties-file"):
            json.loads(Path(opt(args, name)).read_text())
        print("Connector created with ID 12345678-aaaa-bbbb-cccc-1234567890ab"); return 0
    print("Unknown: " + " ".join(args)); return 2


def npm(args):
    if args[:1] == ["--version"]:
        print("10.9.0"); return 0
    if args[:1] == ["install"]:
        Path("node_modules").mkdir(exist_ok=True); print("added 214 packages in 3s"); return 0
    if args[:2] == ["run", "build"]:
        Path("dist").mkdir(exist_ok=True); Path("dist/index.html").write_text("<p>built</p>")
        print("vite v7.2.4 building for production..."); print("built in 1.2s"); return 0
    if args[:2] == ["run", "dev"]:
        port = int(opt(args, "--port")); base = opt(args, "--base", "/")
        page = (Path("index.html").read_text() if Path("index.html").exists() else "<p>app</p>").encode()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if not self.path.startswith(base):
                    self.send_response(404); self.end_headers(); return
                self.send_response(200); self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(page))); self.end_headers(); self.wfile.write(page)

            def log_message(self, *a):
                pass

        server = socketserver.TCPServer(("127.0.0.1", port), Handler)
        print("  VITE v7.2.4  ready in 300 ms", flush=True)
        print(f"  ➜  Local:   http://127.0.0.1:{port}{base}", flush=True)
        env = json.loads(Path("power.config.json").read_text()).get("environmentId")
        print(f"  ➜  Play:    https://make.powerapps.com/play/e/{env}/app/local?_localAppUrl=http://localhost:{port}{base}", flush=True)
        server.serve_forever()
    print("npm: unknown " + " ".join(args)); return 1


def npx(args):
    if "degit" in args:
        name = args[-1]; root = Path(name); (root / "src").mkdir(parents=True)
        (root / "package.json").write_text(json.dumps({"name": "vite", "scripts": {"dev": "vite", "build": "tsc -b && vite build"}}))
        (root / "vite.config.ts").write_text('import { powerApps } from "@microsoft/power-apps-vite/plugin"\nexport default {}\n')
        (root / "index.html").write_text("<!doctype html><title>Made-up code app</title><h1>Expense Tracker</h1>")
        (root / "src" / "App.tsx").write_text("export default function App() { return <h1>Expense Tracker</h1>; }\n")
        print(f"> cloned microsoft/PowerAppsCodeApps#HEAD to {name}"); return 0
    return 1


def node(args):
    print(RECORDED.get("node_version", "v22.11.0")); return 0


def main(tool):
    args = sys.argv[1:]
    log([tool, *args])
    sys.exit({"pa": pa, "pac": pac, "npm": npm, "npx": npx, "node": node}[tool](args))
"""


def install(
    folder: Path, tools: tuple[str, ...] = ("pa", "pac", "npm", "npx", "node"), **recorded: object
) -> Path:
    """Write the stand-ins into `folder` (one program per tool) and return it, for the front of PATH."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "fake_cli.py").write_text(FAKE, encoding="utf-8")
    data = {
        "account": ACCOUNT,
        "connectors": CONNECTORS,
        "connections": CONNECTIONS,
        "tasks_swagger": tasks_swagger(),
        "env_list": ENV_LIST,
        "auth_list": AUTH_LIST,
        "token": TOKEN,
        "app_id": APP_ID,
        "disabled_environment": OTHER_ENVIRONMENT_ID,
        **recorded,
    }
    (folder / "recorded.json").write_text(json.dumps(data), encoding="utf-8")
    for tool in tools:
        script = folder / tool
        script.write_text(
            f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(folder)!r})\n"
            f"import fake_cli\nfake_cli.main({tool!r})\n",
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if os.name == "nt":
            (folder / f"{tool}.cmd").write_text(f'@"{sys.executable}" "%~dp0{tool}" %*\n', encoding="utf-8")
    return folder


def calls(folder: Path) -> list[list[str]]:
    log = folder / "calls.log"
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def sign_out(folder: Path) -> None:
    (folder / "fake_state.json").write_text(json.dumps({"signed_in": False}))
