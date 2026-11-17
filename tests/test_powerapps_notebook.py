# ruff: noqa: E501 (the cells are written as a user types them)
"""The Power Apps extension's data notebook (phase 2) through its door: TypeScript and SQL cells on Deno's
Jupyter kernel (stood in by tests/deno_fake.py: a real Jupyter kernel answering with what Deno 2.9.6 gave for
the same cells), the open tables as views, Open as grid, errors in the panel's shape, data.ts and Use in app,
TSX previews in the HTML cells' frame, Dataverse sources into grids, the kernel's own route, the agent's
commands; and, where a real Deno is on this computer, the same cells on it. Made-up data only."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench import extensions
from swissarmybench.cli import api as cli_api
from swissarmybench.cli import commands as base_commands
from swissarmybench.domain.html_cells import FRAME_POLICY
from tests import deno_fake
from tests import powerapps_fakes as fakes
from tests.conftest import AGENT, AUTH, make_client
from tests.test_powerapps import new_app, ok

REAL_DENO = os.environ.get("SWISSARMYBENCH_TEST_DENO") or shutil.which("deno")


@pytest.fixture
def tools_dir(tmp_path: Path) -> Path:
    folder = fakes.install(tmp_path / "fake-tools")
    return deno_fake.install(folder)


@pytest.fixture
def client(tmp_path: Path, tools_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(extensions.VARIABLE, "powerapps")
    monkeypatch.setenv("PATH", str(tools_dir) + os.pathsep + os.environ.get("PATH", ""))
    with make_client(tmp_path) as test_client:
        yield test_client


@pytest.fixture
def app_folder(client: TestClient, tmp_path: Path) -> Path:
    made = ok(new_app(client, tmp_path))
    return Path(made["folder"])


def run(client: TestClient, code: str, kind: str = "typescript", headers: Any = AUTH, **more: Any) -> Any:
    return ok(
        client.post("/powerapps/notebook/run", json={"code": code, "kind": kind} | more, headers=headers)
    )


def stream(client: TestClient, code: str, kind: str = "typescript", **more: Any) -> list[dict[str, Any]]:
    body = {"code": code, "kind": kind, "stream": True} | more
    answer = client.post("/powerapps/notebook/run", json=body, headers=AUTH)
    assert answer.status_code == 200, answer.text
    assert answer.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in answer.text.splitlines() if line.strip()]


# ===== the data notebook and its kernel =====


def test_the_data_notebook_is_made_once_with_a_sql_and_a_typescript_cell(
    client: TestClient, app_folder: Path
) -> None:
    opened = ok(client.post("/powerapps/notebook/open", headers=AUTH))
    path = Path(opened["path"])
    assert path == app_folder / "data.ipynb" and path.is_file()
    cells = ok(client.post("/workbench/open", json={"path": str(path)}, headers=AUTH))["cells"]
    assert [c["kind"] for c in cells] == ["markdown", "sql", "typescript"]
    path.write_text(path.read_text().replace("North", "East"))
    assert ok(client.post("/powerapps/notebook/open", headers=AUTH))["path"] == str(path)
    assert "East" in path.read_text()  # made the first time only
    assert ok(client.get("/powerapps/notebook", headers=AUTH))["data_notebook"] == str(path)


def test_a_typescript_cell_runs_and_its_table_is_one_bundle(client: TestClient, app_folder: Path) -> None:
    said = run(client, "const byRegion = await sab.sql`SELECT region, total FROM sales`;\nbyRegion", cell=3)
    assert said["done"]["ok"] is True
    (table,) = [o for o in said["outputs"] if o["output_type"] == "execute_result"]
    bundle = table["data"]["application/vnd.swissarmybench.table+json"]
    assert bundle["columns"] == ["region", "total"] and bundle["types"] == ["VARCHAR", "DOUBLE"]
    assert bundle["rows"][0] == {"region": "North", "total": 12.5} and bundle["total"] == 2
    assert bundle["id"] == "r1" and table["data"]["text/plain"] == "2 rows, 2 columns"
    plain = run(client, "1 + 41")["outputs"][0]
    assert plain["data"]["text/plain"] == "42"  # Deno's colour codes taken out
    printed = run(client, "console.log('hello')")["outputs"]
    assert printed == [{"output_type": "stream", "name": "stdout", "text": "hello\n"}]
    state = ok(client.get("/powerapps/notebook", headers=AUTH))
    assert state["kernels"][0]["running"] and state["kernels"][0]["runs"] == 3


def test_a_run_streams_and_an_error_comes_with_the_panels_detail(
    client: TestClient, app_folder: Path
) -> None:
    lines = stream(client, "nope + 1", cell=4)
    error = next(x for x in lines if x.get("output_type") == "error")
    assert error["ename"] == "ReferenceError" and error["evalue"] == "nope is not defined"
    detail = next(x for x in lines if "error_detail" in x)["error_detail"]
    (entry,) = detail["chain"]
    assert entry["title"] == "A name that is not defined" and "`nope`" in entry["explanation"]
    assert entry["fixes"] == [{"kind": "define", "title": "Run the cell that makes `nope`", "name": "nope"}]
    assert entry["frames"][0]["cell"] == 4 and entry["frames"][0]["line"] == 1
    assert detail["where"] == "cell [4], line 1"
    assert lines[-1] == {"done": {"ok": False, "execution_count": lines[-1]["done"]["execution_count"]}}
    sql = stream(client, "select * from missing_table", kind="sql", cell=5)
    entry = next(x for x in sql if "error_detail" in x)["error_detail"]["chain"][0]
    assert entry["title"] == "DuckDB could not run the query" and entry["sql"]["line"] == 1
    assert entry["sql"]["missing"] == "missing_table"


def test_the_open_tables_are_views_a_sql_cell_reads(client: TestClient, app_folder: Path) -> None:
    ok(client.post("/datasets/sales/paste", content=b"region\ttotal\nWest\t5\nEast\t9\n", headers=AUTH))
    said = run(client, "SELECT region, total FROM sales ORDER BY total", kind="sql")
    bundle = said["outputs"][0]["data"]["application/vnd.swissarmybench.table+json"]
    assert [r["region"] for r in bundle["rows"]] == ["West", "East"]  # the grid's rows, through Parquet
    temp = ok(client.get("/powerapps/notebook", headers=AUTH))["kernels"][0]
    assert temp["running"]
    assert not list(app_folder.rglob("*.parquet"))  # never in the project


def test_open_as_grid_writes_the_result_whole(client: TestClient, app_folder: Path) -> None:
    said = run(client, "const byRegion = await sab.sql`SELECT 1`;\nbyRegion")
    ident = said["outputs"][0]["data"]["application/vnd.swissarmybench.table+json"]["id"]
    opened = ok(
        client.post("/powerapps/notebook/grid", json={"id": ident, "name": "by_region"}, headers=AUTH)
    )
    grid = ok(client.get(f"/grids/{opened['grid']}", headers=AUTH))
    assert grid["row_count"] == 2 and [c["name"] for c in grid["columns"]][:2] == ["region", "total"]
    refused = client.post("/powerapps/notebook/grid", json={"id": "drop table x"}, headers=AUTH)
    assert refused.status_code == 400 and "r and a number" in refused.text
    gone = client.post("/powerapps/notebook/grid", json={"id": "r99"}, headers=AUTH)
    assert gone.status_code == 409 and "run its cell again" in gone.text


def test_deno_missing_is_the_missing_package_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tools = fakes.install(tmp_path / "no-deno")
    monkeypatch.setenv(extensions.VARIABLE, "powerapps")
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + "/usr/bin:/bin")
    with make_client(tmp_path) as client:
        ok(new_app(client, tmp_path))
        answer = client.post("/powerapps/notebook/run", json={"code": "1", "stream": True}, headers=AUTH)
        assert answer.status_code == 422
        missing = answer.json()["missing"]
        assert missing["feature"] == "TypeScript cells" and missing["packages"] == ["Deno"]
        assert missing["python"] == "tool" and missing["tool"] == "deno"
        assert missing["command"] in ("npm install --global deno", "brew install deno")


def test_the_kernel_stops_and_its_folder_goes(client: TestClient, app_folder: Path) -> None:
    run(client, "1")
    assert ok(client.post("/powerapps/notebook/restart", json={}, headers=AUTH)) == {"restarted": True}
    path = str(app_folder / "data.ipynb")
    assert ok(client.post("/powerapps/notebook/stop", json={"path": path}, headers=AUTH)) == {"stopped": True}
    assert ok(client.get("/powerapps/notebook", headers=AUTH))["kernels"] == []


# ===== the kernel's own route: a connection's tables for a query =====


def test_the_kernels_route_takes_its_key_only(client: TestClient, app_folder: Path) -> None:
    run(client, "1")
    refused = client.post("/powerapps/notebook/prepare/not-the-key", json={"sql": "SELECT 1"})
    assert refused.status_code == 403
    notebook = _service(client)
    key = next(iter(notebook._books.values())).key
    answer = client.post(f"/powerapps/notebook/prepare/{key}", json={"sql": "SELECT 1 AS a"})
    assert answer.status_code == 200 and answer.json() == {"sql": "SELECT 1 AS a", "tables": {}, "reads": []}


def _service(client: TestClient) -> Any:
    """The notebook service the extension built for this app (the composition root's services)."""
    return client.app.state.ctx.powerapps_notebook  # type: ignore[attr-defined]


# ===== data.ts and Use in app =====

CELLS: list[dict[str, Any]] = [
    {"kind": "markdown", "source": "# Data", "number": 1},
    {"kind": "sql", "source": "SELECT 1", "number": 2},
    {
        "kind": "typescript",
        "source": "const byRegion = await sab.sql`SELECT region, total FROM sales`;\nbyRegion",
        "number": 3,
        "name": "by region",
    },
    {
        "kind": "typescript",
        "source": (
            'import { sum } from "npm:lodash-es@4";\n'
            "type Total = { region: string; total: number };\n"
            "function grandTotal(rows: Total[]): number {\n  return sum(rows.map((r) => r.total));\n}\n"
        ),
        "number": 4,
    },
]


def test_data_ts_exports_the_typescript_and_types_the_results(client: TestClient, app_folder: Path) -> None:
    run(client, CELLS[2]["source"])  # byRegion holds a table now: its row type comes with it
    said = ok(client.post("/powerapps/notebook/data-ts", json={"cells": CELLS}, headers=AUTH))
    text = said["text"]
    assert text.startswith("// data.ts: made from the data notebook's TypeScript cells")
    assert 'import { sum } from "lodash-es";' in text
    assert "export interface ByRegionRow {\n  region: string;\n  total: number;\n}" in text
    assert "export type ByRegion = ByRegionRow[];" in text
    assert "export type Total = " in text and "export function grandTotal(rows: Total[]): number {" in text
    assert "// [3] by region: stays in the notebook" in text and "sab.sql" not in text
    assert said["left"] == [{"cell": 3, "why": "it uses the notebook's kernel (sab, Deno or DuckDB)"}]
    assert said["target"] == "src/data.ts" and said["types"] == ["ByRegionRow"]
    assert not (app_folder / "src" / "data.ts").exists()  # a look only
    used = ok(client.post("/powerapps/notebook/use-in-app", json={"cells": CELLS}, headers=AGENT))
    written = app_folder / "src" / "data.ts"
    assert used["written"] == str(written) and written.read_text() == text
    session = ok(client.get("/session-log", headers=AUTH))
    assert "Wrote data.ts into the code app (Use in app)" in json.dumps(session)


# ===== TSX previews =====

TSX = (
    '// props: { rows: byRegion, title: "Sales by region" }\n'
    "export default function Totals({ rows, title }: { rows: { region: string; total: number }[]; title: string }) {\n"
    "  return <section><h2>{title}</h2>{rows.map((r) => <p key={r.region}>{r.region}</p>)}</section>;\n"
    "}\n"
)


def _react(folder: Path) -> None:
    for name in ("react", "react-dom"):
        (folder / "node_modules" / name).mkdir(parents=True, exist_ok=True)
        (folder / "node_modules" / name / "package.json").write_text(json.dumps({"name": name}))


def test_a_tsx_cell_is_one_page_for_the_html_cells_frame(
    client: TestClient, app_folder: Path, tools_dir: Path
) -> None:
    lacking = client.post("/powerapps/notebook/preview", json={"source": TSX}, headers=AUTH)
    assert lacking.status_code == 409 and "npm install" in lacking.text
    _react(app_folder)
    drawn = ok(client.post("/powerapps/notebook/preview", json={"source": TSX, "cell": 6}, headers=AGENT))
    assert drawn["policy"] == FRAME_POLICY and drawn["props"] == ["rows", "title"]
    html = drawn["html"]
    assert html.startswith("<!doctype html>") and '<div id="root"></div>' in html
    assert '"title": "Sales by region"' in html and '<script type="module">' in html
    assert "http" not in html.split('<script type="module">')[1]  # nothing loaded over the network
    assert "bundle --platform" in deno_fake.calls(tools_dir)
    no_default = client.post("/powerapps/notebook/preview", json={"source": "const a = 1"}, headers=AUTH)
    assert no_default.status_code == 400 and "export default" in no_default.text
    broken = TSX.replace("export default", "// does-not-compile\nexport default")
    failed = client.post("/powerapps/notebook/preview", json={"source": broken}, headers=AUTH)
    assert failed.status_code == 409 and "could not be parsed" in failed.text


# ===== Dataverse sources into grids =====


def test_a_dataverse_source_says_which_connection_to_add(client: TestClient, app_folder: Path) -> None:
    ok(client.post("/powerapps/sources", json={"kind": "dataverse", "table": "account"}, headers=AUTH))
    sources = ok(client.get("/powerapps/project", headers=AUTH))["sources"]
    name = next(s["name"] for s in sources if s["kind"] == "dataverse")
    said = ok(client.post("/powerapps/dataverse/grid", json={"source": name}, headers=AUTH))
    assert said["opened"] is False and said["needs"]["kind"] == "dataverse"
    assert said["needs"]["url"] == "https://contoso-made-up.crm.dynamics.com"
    assert "Add a Dataverse connection for https://contoso-made-up.crm.dynamics.com" in said["message"]
    missing = client.post("/powerapps/dataverse/grid", json={"source": "nope"}, headers=AUTH)
    assert missing.status_code == 404


def test_a_dataverse_source_opens_through_the_matching_connection(
    client: TestClient, app_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ok(client.post("/powerapps/sources", json={"kind": "dataverse", "table": "account"}, headers=AUTH))
    notebook = _service(client)
    opened: list[tuple[str, dict[str, Any]]] = []

    async def open_table(name: str, body: dict[str, Any], who: str) -> dict[str, Any]:
        opened.append((name, body))
        return {"grid": "g-made-up", "dataset": body["table"]}

    monkeypatch.setattr(
        notebook,
        "_connections",
        lambda: [
            {"name": "Other CRM", "kind": "dataverse", "url": "https://other-made-up.crm.dynamics.com"},
            {"name": "Contoso CRM", "kind": "dataverse", "url": "https://CONTOSO-made-up.crm.dynamics.com/"},
        ],
    )
    monkeypatch.setattr(notebook, "_open_connection_table", open_table)
    name = next(s["name"] for s in ok(client.get("/powerapps/project", headers=AUTH))["sources"])
    said = ok(client.post("/powerapps/dataverse/grid", json={"source": name}, headers=AGENT))
    assert said["opened"] is True and said["connection"] == "Contoso CRM" and said["grid"] == "g-made-up"
    assert opened == [("Contoso CRM", {"table": "account"})]


# ===== the agent's commands =====


def test_the_agents_commands_drive_the_same_door(
    client: TestClient, app_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from swissarmybench_powerapps import extension

    def through_client(
        method: str, path: str, body: Any = None, params: Any = None, timeout: float = 0
    ) -> Any:
        answer = client.request(method, path, json=body, params=params or None, headers=AGENT)
        if answer.status_code >= 400:
            raise cli_api.CommandError(answer.text)
        return answer.json()

    monkeypatch.setattr(cli_api, "call", through_client)
    commands = extension.commands()
    assert set(commands) >= {
        "powerapps_notebook", "powerapps_ts_run", "powerapps_ts_grid", "powerapps_data_ts",
        "powerapps_tsx_preview", "powerapps_dataverse_grid",
    }  # fmt: skip
    for name in commands:
        assert base_commands.REGISTRY.get(name) is None or base_commands.REGISTRY[name] is commands[name]
    path = commands["powerapps_notebook"].run({"open": True})["path"]
    said = commands["powerapps_ts_run"].run({"code": "SELECT 1", "kind": "sql"})
    ident = said["outputs"][0]["data"]["application/vnd.swissarmybench.table+json"]["id"]
    grid = commands["powerapps_ts_grid"].run({"id": ident, "name": "from_agent"})
    assert grid["dataset"] == "from_agent"
    built = commands["powerapps_data_ts"].run({"use_in_app": True})
    assert built["written"].endswith(os.path.join("src", "data.ts")) and built["path"] == path
    _react(app_folder)
    drawn = commands["powerapps_tsx_preview"].run({"source": TSX})
    assert drawn["policy"] == FRAME_POLICY
    assert commands["powerapps_notebook"].run({"stop": True}) == {"stopped": True}


# ===== a real Deno, where this computer has one =====


@pytest.mark.skipif(not REAL_DENO, reason="Deno is not on this computer (SWISSARMYBENCH_TEST_DENO names one)")
def test_the_cells_on_a_real_deno(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tools = fakes.install(tmp_path / "fake-tools")
    monkeypatch.setenv(extensions.VARIABLE, "powerapps")
    deno_folder = str(Path(str(REAL_DENO)).resolve().parent)
    monkeypatch.setenv("PATH", os.pathsep.join([str(tools), deno_folder, os.environ.get("PATH", "")]))
    with make_client(tmp_path) as client:
        ok(new_app(client, tmp_path))
        ok(client.post("/datasets/sales/paste", content=b"region\ttotal\nWest\t5\nEast\t9\n", headers=AUTH))
        said = run(client, "SELECT region, total * 2 AS doubled FROM sales ORDER BY doubled", kind="sql")
        assert said["done"]["ok"], said
        bundle = said["outputs"][0]["data"]["application/vnd.swissarmybench.table+json"]
        assert [r["region"] for r in bundle["rows"]] == ["West", "East"]
        made = run(client, "const people = await sab.table('people', [{name: 'Ada', age: 36}]);\npeople")
        assert made["outputs"][0]["data"]["application/vnd.swissarmybench.table+json"]["total"] == 1
        shared = run(client, "SELECT count(*)::INTEGER AS n FROM people", kind="sql")  # one DuckDB
        assert shared["outputs"][0]["data"]["application/vnd.swissarmybench.table+json"]["rows"] == [{"n": 1}]
        typed = run(
            client, "const byRegion = await sab.sql`SELECT region FROM sales WHERE total > ${4}`;\nbyRegion"
        )
        ident = typed["outputs"][0]["data"]["application/vnd.swissarmybench.table+json"]["id"]
        grid = ok(client.post("/powerapps/notebook/grid", json={"id": ident, "name": "big"}, headers=AUTH))
        assert ok(client.get(f"/grids/{grid['grid']}", headers=AUTH))["row_count"] == 2
        cells = [{"kind": "typescript", "source": "const byRegion = 1;", "number": 1}]
        text = ok(client.post("/powerapps/notebook/data-ts", json={"cells": cells}, headers=AUTH))["text"]
        assert "export interface ByRegionRow {\n  region: string;\n}" in text
        failed = run(client, "nope + 1")
        assert failed["outputs"][0]["ename"] == "ReferenceError"
        react = os.environ.get("SWISSARMYBENCH_TEST_REACT")  # a node_modules with react and react-dom
        if react:
            app = Path(ok(client.get("/powerapps/project", headers=AUTH))["folder"])
            shutil.rmtree(app / "node_modules", ignore_errors=True)
            (app / "node_modules").symlink_to(react, target_is_directory=True)
            source = "// props: { name: 'Ada' }\nexport default function Hi({ name }: { name: string }) {\n  return <b>Hi {name}</b>;\n}\n"
            drawn = ok(client.post("/powerapps/notebook/preview", json={"source": source}, headers=AUTH))
            assert "createRoot" in drawn["html"] or "render" in drawn["html"]
        ok(client.post("/powerapps/notebook/stop", json={}, headers=AUTH))
