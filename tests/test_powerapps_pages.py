# ruff: noqa: E501 (the TypeScript is written as a person types it)
"""A code app's pages (the owner, 2026-11-17: each page owns everything it needs; "Lanes should be pages"):
a page's names and files, the list of pages, the starter files, the rule that a page never imports from
another page, through the door and the agent's commands; and, where a code app with its packages is on this
computer, the starter files and a new page compiled by the template's own TypeScript. Made-up data only."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench import extensions
from swissarmybench.cli import api as cli_api
from swissarmybench_powerapps.domain import pages
from tests import powerapps_fakes as fakes
from tests.conftest import AGENT, AUTH, make_client
from tests.test_powerapps import new_app, ok

SERVICE = (
    "export interface Orders { orderid: string; total?: number }\n"
    "export class OrdersService { static async getAll(): Promise<{ data?: Orders[] }> { return { data: [] }; } }\n"
)

# ===== the rules =====


def test_a_pages_names() -> None:
    n = pages.names_of("open orders")
    assert (n["folder"], n["component"], n["id"], n["hook"], n["entry"], n["row"]) == (
        "OpenOrders", "OpenOrdersPage", "open-orders", "useOpenOrders", "openOrdersPage", "OpenOrdersRow",
    )  # fmt: skip
    for bad in ("", "2nd", "App", "OrdersPage", "x" * 61):
        with pytest.raises(pages.PageError):
            pages.names_of(bad)


def test_a_page_owns_its_files() -> None:
    made = pages.page_files("Accounts")
    assert sorted(made) == [
        "src/pages/Accounts/AccountsPage.tsx", "src/pages/Accounts/components/AccountsDetail.tsx",
        "src/pages/Accounts/components/AccountsList.tsx", "src/pages/Accounts/hooks/useAccounts.ts",
        "src/pages/Accounts/index.ts", "src/pages/Accounts/state.ts", "src/pages/Accounts/types.ts",
    ]  # fmt: skip
    # Made-up rows until it has a source; only shared code and its own folder are imported.
    assert "Contoso" in made["src/pages/Accounts/hooks/useAccounts.ts"]
    for path, text in made.items():
        assert pages.cross_page_imports(path, text) == []
    assert (
        'export const accountsPage: Page = { id: "accounts", title: "Accounts", component: AccountsPage };'
        in made["src/pages/Accounts/index.ts"]
    )
    # Its state is the page's own, lifted to its root.
    assert "useReducer(accountsReducer, initialAccountsState)" in made["src/pages/Accounts/AccountsPage.tsx"]
    # Over a generated service: its read-all method as the file spells it, its rows' type the service's.
    over = pages.page_files("Orders", "src/generated/services/OrdersService.ts", SERVICE)
    assert "await OrdersService.getAll();" in over["src/pages/Orders/hooks/useOrders.ts"]
    assert "typeof OrdersService.getAll" in over["src/pages/Orders/types.ts"]
    lower = pages.page_files(
        "Orders", "src/generated/services/OrdersService.ts", SERVICE.replace("getAll", "getall")
    )
    assert "OrdersService.getall()" in lower["src/pages/Orders/hooks/useOrders.ts"]
    actions = pages.page_files(
        "Orders", "src/generated/services/OrdersService.ts", "export class OrdersService {}"
    )
    assert "MADE_UP" in actions["src/pages/Orders/hooks/useOrders.ts"]


def test_the_list_of_pages_takes_one_line_each() -> None:
    first = pages.register(None, "Accounts")
    second = pages.register(first, "Open orders")
    assert 'import { openOrdersPage } from "./pages/OpenOrders";' in second
    assert second.count("accountsPage,") == 1 and "  openOrdersPage,\n];" in second
    assert pages.register(second, "Open orders") == second  # there already: unchanged
    assert pages.registered(second) == ["Accounts", "OpenOrders"]


def test_the_starter_files_never_replace_a_persons_own() -> None:
    nothing: dict[str, str | None] = dict.fromkeys(pages.scaffold_paths())
    planned = pages.scaffold_plan(
        nothing | {"src/App.tsx": "import x from 'y' // Vite + React demo"}, None, ""
    )
    assert {
        "src/shared/page.ts",
        "src/shared/useLoad.ts",
        "src/pages.ts",
        "src/App.tsx",
        "src/pages/Accounts/index.ts",
    } <= set(planned)
    assert 'import { pages } from "./pages.ts";' in planned["src/App.tsx"]
    own = nothing | {
        "src/App.tsx": "export default function App() { return null; }",
        "src/shared/useLoad.ts": "// mine",
    }
    kept = pages.scaffold_plan(own, None, "")
    assert "src/App.tsx" not in kept and "src/shared/useLoad.ts" not in kept
    with_accounts = own | {"src/pages/Accounts/index.ts": "// mine", "src/pages.ts": "// mine"}
    assert not any(p.startswith("src/pages") for p in pages.scaffold_plan(with_accounts, None, ""))


def test_a_page_importing_another_page_is_flagged_with_the_fix() -> None:
    text = (
        'import { useState } from "react";\n'
        'import { OrdersList } from "../Orders/components/OrdersList";\n'
        'import { ordersPage } from "../Orders";\n'
        'import { DataTable } from "../../shared/components/DataTable";\n'
        'import type { AccountsRow } from "./types";\n'
        'const lazy = import("../Orders/OrdersPage");\n'
    )
    found = pages.cross_page_imports("src/pages/Accounts/AccountsPage.tsx", text)
    assert [(p["line"], p["imported"]) for p in found] == [
        (2, "../Orders/components/OrdersList"), (3, "../Orders"), (6, "../Orders/OrdersPage"),
    ]  # fmt: skip
    first = found[0]
    assert (
        first["message"]
        == "The Accounts page imports from the Orders page: a page never imports another page's code."
    )
    assert first["fixes"] == [
        {
            "kind": "move",
            "title": "Move it to src/shared/",
            "target": "src/pages/Orders/components/OrdersList",
        }
    ]
    assert (first["col"], first["endCol"]) == (29, 29 + len("../Orders/components/OrdersList"))
    assert pages.cross_page_imports("src/shared/x.ts", 'import { a } from "../pages/Orders";')[0][
        "message"
    ].startswith("A shared file")
    assert pages.cross_page_imports("src/App.tsx", 'import { pages } from "./pages.ts";') == []
    assert (
        pages.cross_page_imports("src/pages/Accounts/x.ts", 'import { b } from "src/pages/Orders/y";')[0][
            "line"
        ]
        == 1
    )


TEMPLATE = os.environ.get("SWISSARMYBENCH_TEST_CODEAPP")  # a code app folder with its node_modules installed


@pytest.mark.skipif(
    not TEMPLATE or not shutil.which("node"),
    reason="no code app with its packages here (SWISSARMYBENCH_TEST_CODEAPP), or no Node.js",
)
def test_the_starter_files_and_a_new_page_compile_and_lint(tmp_path: Path) -> None:
    """The template's own TypeScript (tsc -p tsconfig.app.json) and its own ESLint pass them."""
    app = Path(str(TEMPLATE))
    work = tmp_path / "app"
    shutil.copytree(app, work, ignore=shutil.ignore_patterns("node_modules"))
    (work / "node_modules").symlink_to(app / "node_modules", target_is_directory=True)
    (work / "src" / "generated" / "services").mkdir(parents=True)
    (work / "src" / "generated" / "services" / "OrdersService.ts").write_text(SERVICE)
    existing = {p: ((work / p).read_text() if (work / p).exists() else None) for p in pages.scaffold_paths()}
    files = pages.scaffold_plan(existing, None, "") | pages.page_files(
        "Open orders", "src/generated/services/OrdersService.ts", SERVICE
    )
    for path, text in files.items():
        (work / path).parent.mkdir(parents=True, exist_ok=True)
        (work / path).write_text(text)
    (work / "src" / "pages.ts").write_text(
        pages.register((work / "src" / "pages.ts").read_text(), "Open orders")
    )
    node = str(shutil.which("node"))
    tsc = subprocess.run(
        [node, str(app / "node_modules/typescript/bin/tsc"), "-p", "tsconfig.app.json", "--noEmit"],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )  # noqa: S603
    assert tsc.returncode == 0, tsc.stdout + tsc.stderr
    eslint = app / "node_modules" / "eslint" / "bin" / "eslint.js"
    if eslint.is_file():
        linted = subprocess.run(
            [node, str(eslint), "src/pages", "src/shared", "src/App.tsx", "src/pages.ts"],
            cwd=work,
            capture_output=True,
            text=True,
            check=False,
        )  # noqa: S603
        assert linted.returncode == 0, linted.stdout


# ===== through the door, and the agent's commands =====


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(extensions.VARIABLE, "powerapps")
    tools = fakes.install(tmp_path / "fake-tools")
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ.get("PATH", ""))
    with make_client(tmp_path) as test_client:
        yield test_client


def test_a_new_code_app_has_the_starter_files_and_new_page_adds_one(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = Path(ok(new_app(client, tmp_path))["folder"])
    assert (folder / "src" / "pages" / "Accounts" / "AccountsPage.tsx").is_file()
    assert pages.registered((folder / "src" / "pages.ts").read_text()) == ["Accounts"]
    assert (
        (folder / "src" / "App.tsx").read_text().startswith("export default function App()")
    )  # its own: kept
    listed = ok(client.get("/powerapps/pages", headers=AUTH))
    assert listed["pages"] == [{"name": "Accounts", "folder": "src/pages/Accounts", "listed": True}]
    # New page over a data source's generated service.
    ok(client.post("/powerapps/sources", json={"kind": "dataverse", "table": "account"}, headers=AUTH))
    service = folder / "src" / "generated" / "services" / "AccountsService.ts"
    assert service.is_file()
    made = ok(
        client.post("/powerapps/pages", json={"name": "Key accounts", "source": "accounts"}, headers=AUTH)
    )
    assert made["open"] == "src/pages/KeyAccounts/KeyAccountsPage.tsx" and made["page"] == "Key accounts"
    hook = (folder / "src" / "pages" / "KeyAccounts" / "hooks" / "useKeyAccounts.ts").read_text()
    assert "AccountsService.getAll()" in hook
    assert pages.registered((folder / "src" / "pages.ts").read_text()) == ["Accounts", "KeyAccounts"]
    again = client.post("/powerapps/pages", json={"name": "Key accounts"}, headers=AUTH)
    assert again.status_code == 409
    assert client.post("/powerapps/pages", json={"name": "2nd"}, headers=AUTH).status_code == 400
    assert (
        client.post("/powerapps/pages", json={"name": "Other", "source": "nope"}, headers=AUTH).status_code
        == 404
    )
    # The rule over the app, and over one file as typed.
    assert ok(client.post("/powerapps/project/lint", json={}, headers=AUTH)) == {"problems": []}
    page = folder / "src" / "pages" / "KeyAccounts" / "KeyAccountsPage.tsx"
    page.write_text(
        'import { AccountsList } from "../Accounts/components/AccountsList";\n' + page.read_text()
    )
    found = ok(client.post("/powerapps/project/lint", json={}, headers=AUTH))["problems"]
    assert [(p["path"], p["line"]) for p in found] == [("src/pages/KeyAccounts/KeyAccountsPage.tsx", 1)]
    typed = ok(
        client.post(
            "/powerapps/project/lint",
            json={"path": "src/pages/Accounts/x.ts", "text": 'import "../KeyAccounts";'},
            headers=AUTH,
        )
    )
    assert typed["problems"][0]["fixes"][0]["title"] == "Move it to src/shared/"
    # The starter files again: nothing to write (each is there).
    assert ok(client.post("/powerapps/project/scaffold", json={}, headers=AUTH))["written"] == []

    # The agent: the same pages, New page, the rule.
    from swissarmybench_powerapps import extension

    def through_client(
        method: str, path: str, body: Any = None, params: Any = None, timeout: float = 0
    ) -> Any:
        answer = client.request(
            method,
            path,
            json=body,
            params={k: v for k, v in (params or {}).items() if v is not None} or None,
            headers=AGENT,
        )
        if answer.status_code >= 400:
            raise cli_api.CommandError(answer.text)
        return answer.json()

    monkeypatch.setattr(cli_api, "call", through_client)
    commands = extension.commands()
    assert [p["name"] for p in commands["powerapps_pages"].run({})["pages"]] == ["Accounts", "KeyAccounts"]
    assert (
        commands["powerapps_pages"].run({"name": "Invoices"})["open"] == "src/pages/Invoices/InvoicesPage.tsx"
    )
    assert len(commands["powerapps_lint"].run({})["problems"]) == 1
    assert commands["powerapps_scaffold"].run({})["written"] == []
    session = ok(client.get("/session-log", headers=AUTH))
    assert "Made the page Invoices" in str(session)
