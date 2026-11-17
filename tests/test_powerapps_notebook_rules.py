# ruff: noqa: E501 (the cells are written as a user types them)
"""The data notebook's rules (phase 2), no I/O: TypeScript and SQL cells for Deno's kernel, the open tables'
views, a result's id, outputs cleaned, errors as the panel's detail (Deno 2.9.6's records, as it gave them
here), data.ts, TSX previews (the HTML cells' frame policy), the notebook's new kinds and the mode's cell
routes. Made-up data only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from swissarmybench import extensions
from swissarmybench.domain import notebooks
from swissarmybench.domain.html_cells import FRAME_POLICY
from swissarmybench_powerapps import extension
from swissarmybench_powerapps.domain import data_ts, shown, tools, tsx_preview
from swissarmybench_powerapps.domain import ts_notebook as rules

# ===== the kernel's code =====


def test_the_prelude_names_duckdbs_node_package_and_the_kernels_variables() -> None:
    assert rules.PRELUDE.startswith(
        'import { DuckDBInstance as __SabDuckDB } from "npm:@duckdb/node-api@2.0.0-r.1";'
    )
    for word in ("__PACKAGE__", "__MIME__", "__SHOWN__", "__PREPARE__", "__TEMP__"):
        assert word not in rules.PRELUDE
    assert rules.TABLE_MIME in rules.PRELUDE and "SWISSARMYBENCH_TS_PREPARE" in rules.PRELUDE
    assert "const SHOWN = 200;" in rules.PRELUDE
    # A tagged template's values are bound as parameters, never written into the SQL.
    assert "params[`p${i + 1}`] = value;" in rules.PRELUDE


def test_a_sql_cell_is_one_call_in_the_kernel() -> None:
    assert rules.sql_cell("SELECT 1;\n") == 'await sab.sql("SELECT 1")'
    assert rules.sql_cell("SELECT '</script>' AS a") == "await sab.sql(\"SELECT '<\\/script>' AS a\")"
    with pytest.raises(rules.TsCellError, match="empty"):
        rules.sql_cell("  ;  ")
    with pytest.raises(rules.TsCellError, match="TypeScript"):
        rules.check_code(None)


def test_views_and_a_results_id_are_checked() -> None:
    code = rules.sync_code({"sales": "/work/a.parquet", "orders": "/work/b.parquet"})
    assert code == 'await sab.sync({"orders": "/work/b.parquet", "sales": "/work/a.parquet"});'
    with pytest.raises(rules.TsCellError):
        rules.sync_code({"drop table x; --": "/work/a.parquet"})
    assert rules.save_code("r12", "/work/r.parquet") == 'await sab.save("r12", "/work/r.parquet");'
    for bad in ("r", "x1", "r1); Deno.exit(", None):
        with pytest.raises(rules.TsCellError):
            rules.save_code(bad, "/work/r.parquet")


# ===== outputs and errors (Deno 2.9.6's records) =====

DENO_REFERENCE = {
    "output_type": "error",
    "ename": "ReferenceError",
    "evalue": "nope is not defined",
    "traceback": ["ReferenceError: nope is not defined", "    at <anonymous>:2:5"],
}
DENO_CATALOG = {
    "output_type": "error",
    "ename": "Error",
    "evalue": 'Catalog Error: Table with name missing_table does not exist!\nDid you mean "pg_tables"?\n\n'
    "LINE 1: select * from missing_table\n                      ^^^^^^^^^^^^^",
    "traceback": ["Error: Catalog Error: Table with name missing_table does not exist!"],
}


def test_colour_codes_are_taken_out() -> None:
    record = {
        "output_type": "execute_result",
        "data": {"text/plain": "\x1b[33m42\x1b[39m"},
        "execution_count": 1,
    }
    assert rules.clean(record)["data"]["text/plain"] == "42"
    assert rules.clean({"output_type": "stream", "text": "\x1b[1mhi\x1b[0m"})["text"] == "hi"
    bundle = {"data": {rules.TABLE_MIME: {"id": "r1", "columns": []}}}
    assert rules.table_of(bundle) == {"id": "r1", "columns": []} and rules.table_of({"data": {}}) is None


def test_an_error_is_the_panels_detail() -> None:
    detail = rules.error_detail(DENO_REFERENCE, 7, "const a = 1;\nnope + 1")
    (entry,) = detail["chain"]
    assert entry["frames"][0] | {"values": []} == entry["frames"][0]
    assert (entry["frames"][0]["line"], entry["frames"][0]["col"], entry["frames"][0]["code"]) == (
        2,
        5,
        "nope + 1",
    )
    assert entry["your_frame"] == 0 and detail["where"] == "cell [7], line 2"
    assert entry["fixes"][0]["kind"] == "define" and entry["fixes"][0]["name"] == "nope"
    sql = rules.error_detail(DENO_CATALOG, 3, "select * from missing_table", sql=True)["chain"][0]
    assert sql["frames"] == [] and sql["title"] == "DuckDB could not run the query"
    assert sql["sql"]["line"] == 1 and sql["sql"]["missing"] == "missing_table"
    assert sql["sql"]["candidates"] == ["pg_tables"]


# ===== data.ts =====


def test_typescript_declarations_are_exported_and_kernel_cells_stay() -> None:
    cells = [
        {"kind": "typescript", "source": "const rows = await sab.sql`SELECT 1`;", "number": 1},
        {
            "kind": "typescript",
            "source": 'import dayjs from "npm:dayjs@1.11.13";\nexport const label = (d: string) => dayjs(d).format("D MMM");\n'
            "interface Sale { region: string }\n  const inner = 1;\nenum Kind { A }",
            "number": 2,
            "name": "labels",
        },
        {"kind": "typescript", "source": 'import { x } from "jsr:@std/x";\nx()', "number": 3},
        {
            "kind": "typescript",
            "source": 'import dayjs from "npm:dayjs@1.11.13";\nconst y = Deno.env',
            "number": 4,
        },
        {"kind": "sql", "source": "SELECT 1", "number": 5},
    ]
    built = data_ts.build(cells)
    text = built["text"]
    assert text.count('import dayjs from "dayjs";') == 1
    assert "export const label = " in text and "export interface Sale" in text and "export enum Kind" in text
    assert "  const inner = 1;" in text and "export   const" not in text  # only the top level
    assert "// [2] labels" in text and "// [1]: stays in the notebook" in text
    assert [c["cell"] for c in built["left"]] == [1, 3, 4]
    assert built["cells"] == [{"cell": 2, "names": ["label", "Sale", "Kind"]}]
    assert "SELECT 1" not in text


def test_typed_results_from_duckdbs_types() -> None:
    results: dict[str, dict[str, Any]] = {
        "by_region": {"columns": ["region", "total", "orders", "first day", "ok"],
                      "types": ["VARCHAR", "DOUBLE", "BIGINT", "DATE", "BOOLEAN"]},
        "empty": {"columns": [], "types": []},
    }  # fmt: skip
    text = data_ts.build([], results)["text"]
    assert (
        "export interface ByRegionRow {\n  region: string;\n  total: number;\n  orders: string;\n"
        '  "first day": string;\n  ok: boolean;\n}\nexport type ByRegion = ByRegionRow[];'
    ) in text
    assert "EmptyRow" not in text
    assert data_ts.ts_type("DECIMAL(18,2)") == "string" and data_ts.ts_type("INTEGER[]") == "number[]"
    assert (
        data_ts.ts_type("STRUCT(a INTEGER)") == "unknown"
        and data_ts.interface_name("2024 sales") == "T2024SalesRow"
    )


# ===== TSX previews =====


def test_a_tsx_cells_props_and_its_component() -> None:
    source = "// props: { rows: byRegion }\nexport default function T() { return <b/>; }"
    assert tsx_preview.props_expression(source) == "{ rows: byRegion }"
    assert tsx_preview.props_expression("export default () => null") is None
    code = tsx_preview.props_code("{ rows: byRegion }")
    assert code.startswith("await (async () => { const __sabProps = await ({ rows: byRegion });")
    assert '"application/json"' in tsx_preview.props_code(None)
    assert tsx_preview.check_component(source) == source
    with pytest.raises(tsx_preview.PreviewError, match="default export"):
        tsx_preview.check_component("const a = 1")
    assert tsx_preview.missing_react({"react": True, "react-dom": True}) is None
    assert "no react-dom" in str(tsx_preview.missing_react({"react": True}))


def test_the_bundlers_config_resolves_the_projects_own_react() -> None:
    said = json.loads(tsx_preview.config("C:\\apps\\sales\\node_modules"))
    assert said["imports"]["react"] == "file:///C:/apps/sales/node_modules/react/index.js"
    assert said["imports"]["react-dom/client"] == "file:///C:/apps/sales/node_modules/react-dom/client.js"
    assert json.loads(tsx_preview.config("/home/a/app/node_modules"))["imports"]["react/"] == (
        "file:///home/a/app/node_modules/react/"
    )
    assert said["compilerOptions"]["jsx"] == "react-jsx"
    argv = tsx_preview.bundle_argv("deno", "/t/entry.tsx", "/t/out.js", "/t/deno.json")
    assert (
        argv[:4] == ["deno", "bundle", "--platform", "browser"]
        and "--no-remote" in argv
        and "--no-npm" in argv
    )


def test_the_page_is_one_document_in_the_html_cells_frame() -> None:
    assert tsx_preview.POLICY == FRAME_POLICY
    page = tsx_preview.page("console.log('</script><script>alert(1)')", {"t": "</script>\u2028"}, "A <b>")
    assert "</script><script>alert" not in page and "<\\/script>" in page
    assert '{"t": "\\u003c/script>\\u2028"}' in page and "<title>A b</title>" in page
    with pytest.raises(tsx_preview.PreviewError, match="too large"):
        tsx_preview.page("x" * (tsx_preview.MAX_BUNDLE_CHARS + 1), {})
    assert (
        tsx_preview.bundle_error("\x1b[33mWarning\x1b[0m deno bundle is experimental\nerror: bad")
        == "error: bad"
    )


# ===== the notebook's kinds, the mode, the tools =====


def test_typescript_and_tsx_cells_round_trip_through_the_ipynb() -> None:
    cells = [
        notebooks.Cell("typescript", "const a = 1;"),
        notebooks.Cell("tsx", "export default () => null", height=240),
    ]
    text = notebooks.write_notebook(cells)
    raw = json.loads(text)["cells"]
    assert (
        raw[0]["source"] == ["const a = 1;"] and raw[0]["metadata"]["swissarmybench"]["kind"] == "typescript"
    )
    assert raw[1]["metadata"]["swissarmybench"]["height"] == 240
    back = notebooks.read_notebook(text)
    assert [(c.kind, c.source, c.height) for c in back] == [
        ("typescript", "const a = 1;", None), ("tsx", "export default () => null", 240),
    ]  # fmt: skip
    assert notebooks.code_of(back[0]) == ""  # the Python kernel runs none of it
    sent = notebooks.read_cells(
        [{"kind": "typescript", "source": "1"}, {"kind": "tsx", "source": "x", "height": 99}]
    )
    assert [c.kind for c in sent] == ["typescript", "tsx"] and sent[1].height == 99


def test_the_code_app_mode_says_where_each_cell_kind_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(extensions.VARIABLE, "powerapps")
    mode = extensions.mode_of("codeapp")
    assert mode["cell_routes"]["typescript"] == {
        "name": "TypeScript", "language": "typescript", "run": "/powerapps/notebook/run",
        "grid": "/powerapps/notebook/grid", "types": "/powerapps/notebook/types",
        "install": "/powerapps/tools/install",
    }  # fmt: skip
    assert "declare const sab" in rules.DECLARATIONS
    assert mode["cell_routes"]["tsx"]["preview"] == "/powerapps/notebook/preview"
    assert mode["cell_routes"]["sql"]["run"] == "/powerapps/notebook/run"
    assert extensions.mode_of(None)["cell_routes"] == {}
    assert "/powerapps/notebook/prepare/" in extension.SECRET_PATHS


def test_deno_is_installed_without_a_shell() -> None:
    assert tools.NEEDED["typescript"] == ("deno",) and tools.FEATURES["typescript"] == "TypeScript cells"
    assert tools.install_argv("deno", "linux") == ["npm", "install", "--global", "deno"]
    assert tools.install_argv("deno", "windows") == ["winget", "install", "--id", "DenoLand.Deno", "-e"]


# ===== the files a person edits (the owner, 2026-11-17: "only .ts files") =====

# What Microsoft's template (degit, 2026-11-17), `pa app init` and `pa app add data-source` wrote: the survey.
SURVEY = [
    ".gitignore", "README.md", "eslint.config.js", "index.html", "package.json", "package-lock.json",
    "public/vite.svg", "src/App.css", "src/App.tsx", "src/assets/react.svg", "src/index.css", "src/main.tsx",
    "tsconfig.app.json", "tsconfig.json", "tsconfig.node.json", "vite.config.ts", "power.config.json",
    "src/generated/models/AccountsModel.ts", "src/generated/services/AccountsService.ts",
    ".power/schemas/appschemas/dataSourcesInfo.ts", ".power/schemas/shared_contosotasks/x.Schema.json",
    ".sab/project.json", "src/shared/data.ts", "src/vite-env.d.ts", "src/features/totals.ts", "data.ipynb",
    "src/pages.ts", "src/pages/Accounts/AccountsPage.tsx", "src/shared/components/DataTable.tsx",
]  # fmt: skip


def test_only_the_files_a_person_edits_are_shown() -> None:
    assert set(shown.shown_files(SURVEY)) == {
        "src/App.tsx", "src/pages/Accounts/AccountsPage.tsx", "src/pages.ts", "src/shared/components/DataTable.tsx",
        "src/shared/data.ts",
    }  # fmt: skip
    assert shown.shown("src\\pages\\Home\\HomePage.tsx") and not shown.shown("src/generated/x.ts")
    assert not shown.shown("src/main.tsx") and not shown.shown("vite.config.ts")


TEMPLATE = os.environ.get("SWISSARMYBENCH_TEST_CODEAPP")  # a code app folder with its node_modules installed


@pytest.mark.skipif(
    not TEMPLATE or not shutil.which("node"),
    reason="no code app with its packages here (SWISSARMYBENCH_TEST_CODEAPP), or no Node.js",
)
def test_data_ts_compiles_under_the_templates_own_settings(tmp_path: Path) -> None:
    """data.ts with exports and row types, checked by the template's own TypeScript (tsc -p tsconfig.app.json)."""
    app = Path(str(TEMPLATE))
    work = tmp_path / "app"
    shutil.copytree(app, work, ignore=shutil.ignore_patterns("node_modules"))
    (work / "node_modules").symlink_to(app / "node_modules", target_is_directory=True)
    cells = [
        {
            "kind": "typescript",
            "number": 1,
            "source": "type Sale = { total: number };\nconst sum = (rows: Sale[]): number => rows.reduce((a, r) => a + r.total, 0);",
        }
    ]
    results: dict[str, dict[str, Any]] = {
        "by_region": {"columns": ["region", "n"], "types": ["VARCHAR", "BIGINT"]}
    }
    (work / "src" / "data.ts").write_text(data_ts.build(cells, results)["text"])
    tsc = app / "node_modules" / "typescript" / "bin" / "tsc"
    ran = subprocess.run(  # noqa: S603 (Node.js on this computer, the template's own tsc)
        [str(shutil.which("node")), str(tsc), "-p", "tsconfig.app.json", "--noEmit"],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr
