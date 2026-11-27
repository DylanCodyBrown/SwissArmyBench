"""The Power Apps extension's rules: each command line, what each command printed, the project's files, the
connectors in the explorer's model, custom connector files, the tools and the code app mode. Made-up
names only (tests/powerapps_fakes.py)."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from swissarmybench import extensions
from swissarmybench_powerapps.domain import cli_lines, connectors, project, tools
from swissarmybench_powerapps.domain.cli_lines import CliError
from tests import powerapps_fakes as fakes

# ===== command lines =====


def test_each_action_is_its_documented_command_line() -> None:
    assert cli_lines.app_init("Expense Tracker", fakes.ENVIRONMENT_ID) == [
        "pa", "app", "init", "--display-name", "Expense Tracker", "--environment-id", fakes.ENVIRONMENT_ID,
    ]  # fmt: skip
    assert cli_lines.add_dataverse_table("account") == [
        "pa", "app", "add", "data-source", "--connector", "dataverse", "--table", "account",
    ]  # fmt: skip
    assert cli_lines.add_connector(
        "shared_fabrikamtickets", "beef01", dataset="Help desk", tables=["Tickets", "Agents"]
    )[-6:] == ["--dataset", "Help desk", "--table", "Tickets", "--table", "Agents"]
    assert cli_lines.remove_source("dataverse", "accounts")[-1] == "--force"
    assert cli_lines.connector_list("tasks") == ["pa", "connector", "list", "--json", "--search", "tasks"]
    assert cli_lines.app_push("sol-1") == ["pa", "app", "push", "--solution-id", "sol-1"]
    assert cli_lines.pac_auth_select(2) == ["pac", "auth", "select", "--index", "2"]
    assert cli_lines.dev_server(5173, "/powerapps/live/k/")[-2:] == ["--base", "/powerapps/live/k/"]
    assert cli_lines.template("expense-tracker")[3] == "github:microsoft/PowerAppsCodeApps/templates/vite"


@pytest.mark.parametrize(
    "value",
    [
        "password=hunter22",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJtYWRlLXVwIn0.c2lnbmF0dXJl",
        "Zm9yIHRlc3RzIG9ubHk6IG5vdCBhIHJlYWwga2V5IGF0IGFsbCwgbWFkZSB1cA",
        "two\nlines",
        "--and-an-option",
    ],
)
def test_a_secret_or_an_option_never_goes_on_a_command_line(value: str) -> None:
    with pytest.raises(CliError):
        cli_lines.app_init(value, fakes.ENVIRONMENT_ID)


def test_arguments_are_checked_for_what_they_are() -> None:
    with pytest.raises(CliError, match="an id like"):
        cli_lines.app_init("Expense Tracker", "not-an-id")
    with pytest.raises(CliError, match="not both"):
        cli_lines.add_connector("shared_x", "c1", "ref_1")
    with pytest.raises(CliError, match="connection"):
        cli_lines.add_connector("shared_x")
    with pytest.raises(CliError, match="no dataset"):
        cli_lines.add_connector("shared_x", "c1", dataset="d", as_kind="action")
    with pytest.raises(CliError, match="https"):
        cli_lines.add_dataverse_table("account", "http://plain.example")
    # A path or an address is not a secret, however long.
    cli_lines.check_argv(
        ["pac", "connector", "create", "--api-definition-file", "/home/maker/" + "a" * 60 + ".json"]
    )


# ===== output =====


def test_what_the_power_apps_cli_prints_is_read() -> None:
    status = json.dumps(
        {
            "signedIn": True,
            "activeAccount": {"username": fakes.ACCOUNT, "homeAccountId": "h"},
            "accounts": [{"username": fakes.ACCOUNT, "homeAccountId": "h", "isActive": True}],
        }
    )
    assert cli_lines.accounts("Some banner\n" + status) == {
        "signed_in": True,
        "active": fakes.ACCOUNT,
        "accounts": [{"username": fakes.ACCOUNT, "active": True}],
    }
    found = cli_lines.connectors(json.dumps(fakes.CONNECTORS))
    assert [c["display_name"] for c in found] == ["Contoso Tasks", "Fabrikam Tickets", "Northwind Orders"]
    assert found[1]["tabular"] is True
    linked = cli_lines.connections(json.dumps(fakes.CONNECTIONS))
    assert linked[0] == {
        "id": "c0ffee00000011112222333344445555",
        "display_name": fakes.ACCOUNT,
        "connector": "shared_contosotasks",
        "status": "Connected",
    }
    pushed = "Publishing...\nApp pushed successfully. You can play your app at https://apps.powerapps.com/play/e/x/a/y\n"
    assert cli_lines.push_link(pushed) == "https://apps.powerapps.com/play/e/x/a/y"
    with pytest.raises(CliError):
        cli_lines.json_of("no json here")


def test_pacs_tables_are_read_by_their_headings() -> None:
    envs = cli_lines.environments(fakes.ENV_LIST)
    assert envs[0] == {
        "name": "Contoso (default)",
        "id": fakes.ENVIRONMENT_ID,
        "url": "https://contoso-made-up.crm.dynamics.com/",
        "unique_name": "unq11111111",
        "active": True,
    }
    assert envs[1]["active"] is False
    # The documented shape, with headings a single space apart ("Index Active Kind      Name Friendly Name").
    documented = (
        "Index Active Kind      Name Friendly Name                   Url                                 "
        "User                                     Cloud  Type\n"
        "[1]   *      UNIVERSAL      Personal Productivity (Default) https://x.crm.dynamics.com/         "
        "user@contoso.onmicrosoft.com             Public User\n"
    )
    profile = cli_lines.profiles(documented)[0]
    assert (
        profile["index"] == 1
        and profile["active"]
        and profile["environment"] == "Personal Productivity (Default)"
    )
    assert (
        profile["url"] == "https://x.crm.dynamics.com/" and profile["user"] == "user@contoso.onmicrosoft.com"
    )
    assert [p["index"] for p in cli_lines.profiles(fakes.AUTH_LIST)] == [1, 2]


def test_failures_are_said_plainly_where_they_are_known() -> None:
    off = cli_lines.plain_error("Error: Code apps are not enabled in this environment.", "Contoso Test")
    assert off and "switched off in Contoso Test" in off and "Enable code apps" in off
    assert "Sign in" in str(cli_lines.plain_error("Not signed in. Run `pa auth login` to authenticate."))
    assert cli_lines.plain_error("something else went wrong") is None


def test_the_dev_servers_lines_give_its_addresses() -> None:
    assert cli_lines.dev_urls("  \x1b[32m➜\x1b[0m  Local:   http://127.0.0.1:5173/powerapps/live/k/") == {
        "local": "http://127.0.0.1:5173/powerapps/live/k/"
    }
    play = cli_lines.dev_urls(
        "Play: https://make.powerapps.com/play/e/E/app/local?_localAppUrl=http://localhost:1/"
    )
    assert play["play"].startswith("https://make.powerapps.com/play/e/E/app/local")
    built = cli_lines.local_play(fakes.ENVIRONMENT_ID, "http://localhost:5173/p/k/")
    assert built == (
        f"https://make.powerapps.com/play/e/{fakes.ENVIRONMENT_ID}/app/local"
        "?_localAppUrl=http://localhost:5173/p/k/"
    )


# ===== the project =====


CONFIG: dict[str, Any] = {
    "appDisplayName": "Expense Tracker",
    "environmentId": fakes.ENVIRONMENT_ID,
    "localAppUrl": "http://localhost:3000",
    "databaseReferences": {
        "default.cds": {"dataSources": {"accounts": {"entitySetName": "accounts", "logicalName": "account"}}}
    },
    "connectionReferences": {
        "fabrikamtickets": {
            "id": "/providers/Microsoft.PowerApps/apis/shared_fabrikamtickets",
            "displayName": "Fabrikam Tickets",
            "dataSources": ["Tickets", "Fabrikamtickets"],
            "sharedConnectionId": "beef01",
            "dataSets": {"Help desk": {"dataSources": {"Tickets": {"tableName": "Tickets"}}}},
        }
    },
}


def test_the_projects_sources_come_from_power_config() -> None:
    found = project.sources(CONFIG)
    assert [(s["name"], s["kind"], s["connector"]) for s in found] == [
        ("accounts", "dataverse", "dataverse"),
        ("Fabrikamtickets", "connector", "shared_fabrikamtickets"),
        ("Tickets", "table", "shared_fabrikamtickets"),
    ]
    assert found[2]["dataset"] == "Help desk" and found[1]["connection"] == "beef01"
    assert project.summary(CONFIG)["environment_id"] == fakes.ENVIRONMENT_ID
    with pytest.raises(project.ProjectError, match="not a code app"):
        project.config(None)


def test_the_generated_files_and_the_tree() -> None:
    paths = [
        "src/App.tsx",
        "src/generated/models/AccountsModel.ts",
        "src/generated/services/AccountsService.ts",
        "node_modules/react/index.js",
        "power.config.json",
    ]
    assert [(g["name"], g["kind"]) for g in project.generated(paths)] == [
        ("AccountsModel.ts", "model"),
        ("AccountsService.ts", "service"),
    ]
    tree = project.tree(paths)
    assert [c["name"] for c in tree["children"]] == ["src", "power.config.json"]  # folders first, no packages
    assert project.language_of("src/App.tsx") == "tsx" and project.language_of("a.ts") == "typescript"
    assert project.folder_name("Expense Tracker!") == "expense-tracker"
    marked = json.loads(project.marker('{"kept": 1}'))
    assert marked == {"kept": 1, "type": "codeapp"} and project.project_type(json.dumps(marked)) == "codeapp"


# ===== connectors =====


def test_a_connector_is_read_into_the_explorers_model_read_only() -> None:
    shown = connectors.explored("shared_contosotasks", "Contoso Tasks", fakes.tasks_swagger(), "here")
    assert shown["read_only"] and shown["connector"] == "shared_contosotasks"
    ops = {o["operation_id"]: o for o in shown["operations"]}
    assert set(ops) == {"ListTasks", "CreateTask"}  # the internal one left out
    assert ops["ListTasks"]["name"] == "List the tasks of a list"
    assert {p["name"] for p in ops["ListTasks"]["parameters"]} >= {"list", "top"}
    assert ops["CreateTask"]["body"]["example"]["title"] == "Order more made-up widgets"
    assert all(o["sql_name"] is None and o["blade"] is None for o in shown["operations"])
    assert [s["name"] for s in shown["schemas"]] == ["Task"]
    assert connectors.find_swagger({"properties": {"swagger": fakes.tasks_swagger()}})
    found = cli_lines.connectors(json.dumps(fakes.CONNECTORS))
    assert [c["name"] for c in connectors.search(found, "orders made-up")] == ["shared_northwindorders"]


OPENAPI: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Made-up Orders", "version": "2.1"},
    "servers": [{"url": "https://orders.contoso.example/api/v2"}],
    "paths": {
        "/orders/{id}": {
            "get": {
                "operationId": "getOrder",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {
                    "200": {
                        "description": "One order",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}},
                    }
                },
            }
        },
        "/orders": {
            "post": {
                "operationId": "addOrder",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}},
                },
                "responses": {"201": {"description": "Made"}},
            }
        },
    },
    "components": {
        "schemas": {
            "Order": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "note": {"type": "string", "nullable": True}},
            }
        }
    },
}


def test_a_custom_connectors_files_from_an_openapi_document() -> None:
    made = connectors.custom_connector_files(
        OPENAPI, {"type": "api_key", "in": "header", "name": "X-Orders-Key"}
    )
    swagger = json.loads(made["files"]["apiDefinition.swagger.json"])
    assert swagger["swagger"] == "2.0" and swagger["host"] == "orders.contoso.example"
    assert swagger["basePath"] == "/api/v2" and swagger["schemes"] == ["https"]
    got = swagger["paths"]["/orders/{id}"]["get"]
    assert got["parameters"] == [{"name": "id", "in": "path", "required": True, "type": "integer"}]
    assert got["responses"]["200"]["schema"] == {"$ref": "#/definitions/Order"}
    body = swagger["paths"]["/orders"]["post"]["parameters"][0]
    assert body["in"] == "body" and body["schema"] == {"$ref": "#/definitions/Order"}
    assert swagger["definitions"]["Order"]["properties"]["note"]["x-nullable"] is True
    assert swagger["securityDefinitions"] == {
        "API Key": {"type": "apiKey", "in": "header", "name": "X-Orders-Key"}
    }
    props = json.loads(made["files"]["apiProperties.json"])["properties"]
    assert props["connectionParameters"]["api_key"]["type"] == "securestring"
    assert made["operations"] == 2


def test_oauth_maps_to_an_oauth_setting_with_no_secret_and_the_unmappable_is_said() -> None:
    auth = {
        "type": "oauth2",
        "flow": "authorization_code",
        "authorize_url": "https://login.contoso.example/authorize",
        "token_url": "https://login.contoso.example/token",
        "scopes": "orders.read orders.write",
    }
    made = connectors.custom_connector_files(OPENAPI, auth)
    setting = json.loads(made["files"]["apiProperties.json"])["properties"]["connectionParameters"]["token"]
    assert setting["oAuthSettings"]["clientId"] == "" and "clientSecret" not in json.dumps(setting)
    assert setting["oAuthSettings"]["scopes"] == ["orders.read", "orders.write"]
    with pytest.raises(connectors.ConnectorError, match="authorization code"):
        connectors.custom_connector_files(OPENAPI, auth | {"flow": "client_credentials"})
    with pytest.raises(connectors.ConnectorError, match="AWS Signature"):
        connectors.custom_connector_files(OPENAPI, {"type": "sigv4"})
    assert (
        connectors.custom_connector_files(fakes.tasks_swagger(), {"type": "none"})["host"]
        == "tasks.contoso.example"
    )


# ===== the tools =====


def test_tools_their_versions_and_each_systems_install() -> None:
    assert tools.parse_version("node", "v22.11.0\n") == "22.11.0"
    assert tools.parse_version("pac", "Microsoft PowerPlatform CLI\nVersion: 1.30.3+g0f0e0b9\n") == "1.30.3"
    assert tools.parse_version("deno", "deno 2.1.4 (stable, release, x86_64)") == "2.1.4"
    old = tools.tool_state("node", "/usr/bin/node", "18.19.1", "linux")
    assert not old["ok"] and "older than 22" in old["problem"]
    assert (
        tools.tool_state("pa", None, None, "windows")["install"]
        == "npm install --global @microsoft/power-apps-cli"
    )
    assert tools.TOOLS["pac"].installs["macos"] == "dotnet tool install --global Microsoft.PowerApps.CLI.Tool"
    assert tools.TOOLS["node"].installs["windows"].startswith("winget install")
    states = {t: tools.tool_state(t, f"/x/{t}", "22.0.0", "linux") for t in ("node", "npm")}
    missing = tools.missing("init", states)
    assert missing is not None and missing["missing"]["packages"] == ["Power Apps CLI"]
    assert missing["missing"]["feature"] == "A new code app" and missing["missing"]["python"] == "tool"
    assert tools.install_argv("node", "linux") is None  # sudo: the user runs it themselves
    assert tools.install_argv("pa", "linux") == ["npm", "install", "--global", "@microsoft/power-apps-cli"]
    assert tools.system_of("win32") == "windows" and tools.system_of("darwin") == "macos"


# ===== the extension's switch and its mode =====


def test_the_extension_is_off_unless_installed_or_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(extensions.VARIABLE, raising=False)
    assert not extensions.extension_on("powerapps")
    assert extensions.mode_of("codeapp") == extensions.BASE_MODE  # its type means nothing while off
    monkeypatch.setenv(extensions.VARIABLE, "powerapps")
    assert extensions.extension_on("powerapps")
    mode = extensions.mode_of("codeapp")
    assert mode["type"] == "codeapp" and mode["languages"] == ["typescript", "tsx"]
    assert mode["families"] == ["TypeScript", "React", "Connectors"]
    assert mode["cell_kinds"] == ["typescript", "tsx"] and mode["canvases"] == ["components"]
    assert mode["tools"] == ["powerapps_"] and mode["export"] == ["push"]
    assert [m["type"] for m in extensions.modes()] == ["bi", "codeapp"]
    monkeypatch.setenv(extensions.VARIABLE, "powerapps,-powerapps")  # named off wins
    assert not extensions.extension_on("powerapps")


# ===== its starters: TypeScript and React blades =====


def test_its_starters_read_and_fill_as_typescript(tmp_path: Path) -> None:
    from swissarmybench.adapters.blades import BladeStore
    from swissarmybench.domain import snippets
    from swissarmybench_powerapps import extension

    found = BladeStore(tmp_path / "blades", starters=Path(extension.STARTERS)).starters()
    assert {b.family for b in found} == {"TypeScript", "React", "Connectors"}
    assert {b.language for b in found} == {"typescript", "tsx"}
    for blade in found:
        assert "<<" not in snippets.fill(blade.code, blade.language, {})
    rows = next(b for b in found if b.name == "TypeScript Dataverse rows")
    filled = snippets.fill(rows.code, "typescript", {"filter": "name eq 'Contoso'"})
    assert "filter: \"name eq \\'Contoso\\'\"" in filled
    with pytest.raises(snippets.SnippetError, match="a TypeScript name"):
        snippets.fill(rows.code, "typescript", {"service name": "class"})
    template = snippets.fill("const s = `<<text: a>>`;", "typescript", {"text": "${secret}`"})
    assert template == "const s = `\\${secret}\\``;"
    assert snippets.CELL_WORDS["tsx"] == "a TSX file"


# ===== the extension's own layers (REFACTOR.md: imports point inwards) =====

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "swissarmybench_powerapps"
INWARD = {
    "domain": ("swissarmybench_powerapps.domain", "swissarmybench.domain"),
    "services": (
        "swissarmybench_powerapps.domain",
        "swissarmybench_powerapps.services",
        "swissarmybench.domain",
        "swissarmybench.services",
    ),
}
IO = {"asyncio", "os", "pathlib", "subprocess", "socket", "shutil", "urllib", "http", "tempfile", "importlib"}


@pytest.mark.parametrize("layer", list(INWARD))
def test_the_extensions_layers_import_inwards(layer: str) -> None:
    problems = []
    for path in sorted((PACKAGE / layer).glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top in sys.stdlib_module_names:
                    if top in (IO if layer == "domain" else IO - {"asyncio"}):
                        problems.append(f"{path.name} imports {name}")
                elif not name.startswith(INWARD[layer]):
                    problems.append(f"{path.name} imports {name}")
    assert problems == []
