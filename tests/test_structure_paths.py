"""A structure's paths as words and as code, its search and which files are a structure's tab, in the page
(web/src/structurePaths.ts: pure functions) as the page runs them: bundled by the page's own esbuild and
called by Node, against the server's own rules (domain/structures.py) and the
shared cases (tests/golden/structure_code.json). Skipped where Node or the page's packages are not there.
Made-up data."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import structures as rules

WEB = Path(__file__).resolve().parents[1] / "web"
ESBUILD = WEB / "node_modules" / ".bin" / "esbuild"
GOLDEN = Path(__file__).resolve().parent / "golden" / "structure_code.json"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not ESBUILD.exists(), reason="Node and the page's packages are needed"
)

CALLS = """
import * as paths from "./paths.mjs";
const asked = JSON.parse(process.argv[2]);
console.log(JSON.stringify(asked.map(([name, ...args]) => paths[name](...args))));
"""

ORDERS = {
    "orders": [
        {"id": 1, "status": "open", "lines": [{"sku": "A-1", "qty": 2}]},
        {"id": 2, "status": "Shipped", "lines": [{"sku": "B-7", "qty": 1}, {"sku": "A-1", "qty": 5}]},
    ],
    "note": None,
    "paid": True,
}


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    folder = tmp_path_factory.mktemp("paths")
    built = subprocess.run(  # noqa: S603
        [
            str(ESBUILD),
            str(WEB / "src" / "structurePaths.ts"),
            "--bundle",  # with pageRules.ts, which it re-exports (tests/test_page_rules.py covers that part)
            "--format=esm",
            f"--outfile={folder / 'paths.mjs'}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    (folder / "calls.mjs").write_text(CALLS, encoding="utf-8")

    def call(*asked: list[Any]) -> list[Any]:
        done = subprocess.run(  # noqa: S603
            ["node", str(folder / "calls.mjs"), json.dumps(asked)],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        return list(json.loads(done.stdout))

    return call


def test_the_page_writes_a_path_and_its_code_as_the_server_does(run: Any) -> None:
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))
    said = run(*[["pathText", c["parts"]] for c in cases], *[["accessCode", c["parts"]] for c in cases])
    assert said[: len(cases)] == [c["path"] for c in cases]
    assert said[len(cases) :] == [c["code"] for c in cases]
    assert run(["accessCode", ["orders", 0], "orders"]) == ['orders["orders"][0]']


def test_the_pages_search_finds_what_the_servers_finds_in_the_same_order(run: Any) -> None:
    for words in ("a-1", "STATUS", "shipped", "lines", "true", "null", "nothing at all", ""):
        page = run(["matchPaths", ORDERS, words])[0]
        server = [f["path"] for f in rules.search(ORDERS, words)["found"]]
        assert [rules.format_path(tuple(p)) for p in page] == server, words
    assert len(run(["matchPaths", {"items": list(range(50))}, "1", 3])[0]) == 3


def test_the_page_reads_a_files_format_and_an_errors_place(run: Any) -> None:
    assert run(["formatOfPath", "a.yml"], ["formatOfPath", "a.toml"], ["formatOfPath", "a.py"]) == [
        "yaml",
        "toml",
        None,
    ]
    assert run(["errorPlace", "Not JSON: line 3, column 7: Expecting value."]) == [{"line": 3, "column": 7}]
    assert run(["errorPlace", "Not TOML: Invalid value (at line 2, column 5)."]) == [{"line": 2, "column": 5}]
    assert run(["errorPlace", "Not XML: no element found."]) == [None]
