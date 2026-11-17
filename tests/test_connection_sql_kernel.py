# ruff: noqa: F811
"""A notebook's %%sql cell with no connection, in a real Workbench kernel against a running server: DuckDB
in the kernel, a connection's table named by the connection ([Shop].orders) joined with the kernel's own
DataFrame; sab.sql(query) the same way; an unknown table said in the app's words. Made-up data only."""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any

from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_connection_tables import CATALOG


def lines(live: Live, path: str, body: Any) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{live.port}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {live.token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (the test's own server)
        return [json.loads(line) for line in response.read().decode().splitlines() if line.strip()]


def test_a_cell_with_no_connection_names_a_connections_table(live: Live, tmp_path: Path) -> None:
    path = tmp_path / "shop.sqlite"
    with sqlite3.connect(path) as made:
        made.execute("CREATE TABLE orders (order_id INTEGER, region TEXT, amount REAL)")
        made.executemany(
            "INSERT INTO orders VALUES (?, ?, ?)", [(1, "North", 10.5), (2, "South", 7.0), (3, "North", 2.5)]
        )
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{path}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    body = {"name": "Shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code}
    live.user("POST", "/connections", body | {"catalog": {"language": "sql", "command": CATALOG}})
    kernel = live.user("POST", "/workbench/kernels", {"path": str(tmp_path / "report.ipynb")})["kernel"]
    execute = f"/workbench/kernels/{kernel}/execute"

    def said(code: str) -> tuple[bool, str]:
        out = lines(live, execute, {"code": code})
        text = "".join(str(o.get("text", "")) + str(o.get("evalue", "")) for o in out)
        return bool(out[-1]["done"]["ok"]), text

    try:
        made_here = (
            "import pandas as pd\n"
            "managers = pd.DataFrame({'region': ['North', 'South'], 'manager': ['Ann', 'Bo']})"
        )
        assert said(made_here)[0]
        cell = (
            "%%sql -> by_manager\n"
            "SELECT m.manager, sum(o.amount) AS amount FROM [Shop].orders o "
            "JOIN managers m USING (region) GROUP BY ALL ORDER BY 1"
        )
        assert said(cell)[0]
        ok, text = said("print(by_manager.values.tolist())")
        assert ok and text.strip() == "[['Ann', 13.0], ['Bo', 7.0]]", text
        ok, text = said(
            "import swissarmybench as sab\n"
            "print(len(sab.sql('SELECT * FROM \"Shop\".main.orders JOIN managers USING (region)')))"
        )
        assert ok and text.strip() == "3", text
        ok, text = said("%%sql\nSELECT * FROM [Shop].invoices")
        assert "Shop has no table invoices" in text and "orders" in text, (ok, text)
    finally:
        live.user("DELETE", f"/workbench/kernels/{kernel}")
