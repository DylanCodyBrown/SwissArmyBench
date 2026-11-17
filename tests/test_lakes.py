# ruff: noqa: E501 (the connections' code is text, written as it runs; its lines are its own)
"""Lakes and SharePoint as connections (domain/lakes.py, domain/sharepoint.py, domain/entra.py), against
the stand-ins on this computer (tests/lake_standins.py): OneLake, Azure Data Lake Storage, Delta Lake,
SharePoint lists and SharePoint documents each list their tables and read one through the one contract,
by name in DuckDB SQL, with what the query sends them (columns, filters) said. No real tenant, account or
site is reached; every value is made up."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import connection_tables as ct
from swissarmybench.domain import lakes, sharepoint
from swissarmybench.domain.connection_swap import Place
from swissarmybench.server.blade_templates import BY_ID
from tests import lake_standins as made_up
from tests.conftest import AGENT, AUTH
from tests.fake_keyring import memory_keyring

SITE = f"https://{made_up.SITE_HOST}{made_up.SITE_PATH}"


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture
def standin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    """The made-up lake on disk and the stand-in serving it (a child process gets the variables too)."""
    made_up.make_lake(tmp_path / "storage")
    running = made_up.StandIn(tmp_path / "storage").start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def way(template: str, label: str) -> str:
    """A starter's code for one way to sign in, by the start of its label."""
    return next(code for name, _, code in BY_ID[template].sign_ins if name.startswith(label))


def filled(code: str, **values: str) -> str:
    for old, new in values.items():
        code = code.replace(old, new)
    return code


ENTRA = {"my-tenant-id": made_up.TENANT, "my-client-id": made_up.CLIENT}


def datalake_code(sign_in: str = "App registration") -> str:
    return filled(
        way("datalake", sign_in),
        **ENTRA,
        **{"my-storage-account": made_up.ACCOUNT, "my-container": made_up.CONTAINER},
        **{'folder_in_container = ""': 'folder_in_container = "lake"'},
    )


def onelake_code() -> str:
    return filled(way("onelake", "Managed identity"), **{"My Workspace": made_up.WORKSPACE})


def sharepoint_code(template: str = "sharepoint", user: str = made_up.USERNAME) -> str:
    code = way(template, "Username and password (ROPC)")
    return filled(
        code,
        **ENTRA,
        **{"my-user@my-company.com": user, "https://my-company.sharepoint.com/sites/my-site": SITE},
    )


def save(
    client: TestClient, name: str, template: str, code: str, secrets: dict[str, str] | None = None
) -> None:
    body: dict[str, Any] = {"name": name, "kind": "sql", "template": template, "dialect": template}
    body |= {"code": code, "variable": "conn", "catalog": {"language": "python", "command": lakes.CATALOG}}
    if secrets:
        body["secrets"] = secrets
    ok(client.post("/connections", json=body, headers=AUTH))


ASKED = [0]


def query(client: TestClient, sql: str) -> tuple[list[list[Any]], dict[str, Any]]:
    ASKED[0] += 1
    made = ok(client.post(f"/datasets/q{ASKED[0]}/query", json={"sql": sql}, headers=AUTH))
    rows = ok(client.get(f"/grids/{made['grid']}/rows", headers=AUTH))["rows"]
    return rows, made


def tree_names(client: TestClient, name: str) -> dict[str, dict[str, Any]]:
    tree = ok(client.get(f"/connections/{name}/tree", headers=AGENT))
    return {t["sql"]: t for g in tree["groups"] for t in g["tables"]}


# ===== the forms =====


def test_the_five_kinds_are_connection_types_with_their_own_sign_ins(client: TestClient) -> None:
    types = {t["id"]: t for t in ok(client.get("/connections/types", headers=AUTH))["types"]}
    for kind in lakes.KINDS:
        form = types[kind]
        assert (form["connection"], form["dialect"], form["group"]) == ("database", kind, lakes.GROUP)
        assert form["catalog"] == {"language": "python", "command": lakes.CATALOG}

    def labels(kind: str) -> list[str]:
        return [s["label"] for s in types[kind]["sign_ins"]]

    # SharePoint offers its username and password first (the owner's own connection: Graph via ROPC).
    assert labels("sharepoint")[:2] == [
        "Username and password (ROPC)",
        "Username and password, with the app's client secret (ROPC)",
    ]
    assert labels("sharepoint_docs") == labels("sharepoint")
    assert labels("onelake")[0] == "As you (Azure command line or browser)" and len(labels("onelake")) == 3
    assert "Account key, from a key vault" in labels("datalake") and "SAS token, from a key vault" in labels(
        "datalake"
    )
    assert labels("delta")[0] == "A folder on this computer" and any(
        "Amazon S3" in s for s in labels("delta")
    )
    # Each way's code holds its own mark only (the form tells them apart by it).
    for kind in lakes.KINDS:
        ways = types[kind]["sign_ins"]
        for w in ways:
            assert [o["label"] for o in ways if o["mark"].lower() in w["code"].lower()] == [w["label"]], (
                kind,
                w["label"],
            )
    # No password in any starter: a secret("...") names where it comes from.
    assert 'password = secret("password")' in sharepoint.LISTS
    fields = {f["name"] for f in types["sharepoint"]["fields"]}
    assert {"tenant", "client id", "username", "site"} <= fields


# ===== each kind through the contract, by name in DuckDB SQL =====


def test_a_data_lake_lists_files_delta_and_partitioned_folders_and_reads_them_by_name(
    client: TestClient, standin: made_up.StandIn
) -> None:
    save(client, "Sales Lake", "datalake", datalake_code(), {"client secret": made_up.SECRET})
    names = tree_names(client, "Sales%20Lake")
    assert set(names) == {"[Sales Lake].orders", '[Sales Lake]."customers.parquet"', '[Sales Lake]."returns.csv"',
                          "[Sales Lake].events"}  # fmt: skip
    assert names["[Sales Lake].orders"]["title"] == "Delta v1 · 3.2 KB · partitioned by region"
    assert names["[Sales Lake].events"]["title"].endswith("partitioned by day")
    rows, made = query(client, "SELECT count(*) FROM [Sales Lake].orders")
    assert rows == [[5]]
    assert made["connection_reads"][0]["read_with"] == "its Delta log, read here, and DuckDB's read_parquet"
    rows, _ = query(
        client, "SELECT name FROM [Sales Lake].customers ORDER BY customer_id"
    )  # without .parquet
    assert rows == [["Avery Made-up"], ["Blake Made-up"], ["Casey Made-up"]]
    rows, _ = query(client, "SELECT o.order_id, r.reason FROM [Sales Lake].orders o JOIN [Sales Lake].returns r "
                            "USING (order_id) ORDER BY 1")  # fmt: skip
    assert rows == [[2, "damaged"], [4, "late"]]
    rows, _ = query(client, "SELECT day, count(*) FROM [Sales Lake].events GROUP BY day ORDER BY day")
    assert [[str(r[0]), r[1]] for r in rows] == [["2026-11-01", 2], ["2026-11-02", 1]]


def test_a_filter_on_a_partition_column_reads_only_its_files(
    client: TestClient, standin: made_up.StandIn
) -> None:
    save(client, "Sales Lake", "datalake", datalake_code(), {"client secret": made_up.SECRET})
    tree_names(client, "Sales%20Lake")
    before = len(standin.requests)
    rows, made = query(
        client, "SELECT order_id, amount FROM [Sales Lake].orders WHERE region = 'South' ORDER BY 1"
    )
    assert rows == [[3, 42.0], [4, 300.0]]
    sent = made["connection_reads"][0]["sent"]
    assert sent["filters"] == "region = 'South'" and sent["columns"] == ["order_id", "amount", "region"]
    read = [
        r["path"]
        for r in standin.requests[before:]
        if r["what"] == "storage" and r["path"].endswith(".parquet")
    ]
    assert read and all("region=South" in p for p in read), read


def test_a_delta_tables_version_or_time_is_named_after_an_at(
    client: TestClient, standin: made_up.StandIn
) -> None:
    save(client, "Sales Lake", "datalake", datalake_code(), {"client secret": made_up.SECRET})
    assert query(client, 'SELECT count(*) FROM [Sales Lake]."orders@v0"')[0] == [[3]]
    assert query(client, "SELECT count(*) FROM [Sales Lake].orders@v1")[0] == [[5]]  # quoted for you
    assert query(client, "SELECT count(*) FROM [Sales Lake].orders@2026-11-01")[0] == [[3]]  # that day's end
    assert query(client, "SELECT count(*) FROM [Sales Lake].orders@2026-11-02")[0] == [[5]]
    refused = client.post(
        "/datasets/q/query", json={"sql": "SELECT * FROM [Sales Lake].orders@v9"}, headers=AUTH
    )
    assert refused.status_code != 200 and "versions 0 to 1" in refused.text
    refused = client.post(
        "/datasets/q/query", json={"sql": 'SELECT * FROM [Sales Lake]."returns@v1"'}, headers=AUTH
    )
    assert refused.status_code != 200 and "no versions" in refused.text


def test_onelake_reads_a_lakehouses_tables_and_files(client: TestClient, standin: made_up.StandIn) -> None:
    save(client, "Fabric", "onelake", onelake_code())
    names = tree_names(client, "Fabric")
    assert set(names) == {"[Fabric].orders", "[Fabric].products", '[Fabric].Files.raw."regions.csv"'}
    rows, _ = query(client, "SELECT region, sum(amount) FROM [Fabric].orders GROUP BY 1 ORDER BY 1")
    assert rows == [["North", 200.5], ["South", 342.0], ["West", 15.25]]  # its checkpoint, then the log
    rows, _ = query(client, "SELECT manager FROM [Fabric].Files.raw.regions WHERE region = 'North'")
    assert rows == [["Avery"]]
    assert {r["what"] for r in standin.requests} >= {"managed identity", "storage"}


def test_a_delta_lake_on_this_computer_is_read_with_duckdbs_delta_scan(
    client: TestClient, standin: made_up.StandIn
) -> None:
    root = standin.root / made_up.ACCOUNT / made_up.CONTAINER
    code = filled(way("delta", "A folder on this computer"), **{'r"C:\\lake"': f'r"{root}"'})
    save(client, "Lake", "delta", code)
    names = tree_names(client, "Lake")
    assert set(names) == {"[Lake].lake.orders"}  # only folders holding a _delta_log
    rows, made = query(client, "SELECT count(*) FROM [Lake].lake.orders WHERE region <> 'North'")
    assert rows == [[3]] and made["connection_reads"][0]["read_with"] == "DuckDB's delta_scan"
    assert query(client, "SELECT count(*) FROM [Lake].orders@v0")[0] == [[3]]


def test_sharepoint_lists_are_typed_tables_with_lookups_people_and_filters_sent(
    client: TestClient, standin: made_up.StandIn
) -> None:
    save(client, "Team", "sharepoint", sharepoint_code(), {"password": made_up.PASSWORD})
    names = tree_names(client, "Team")
    assert set(names) == {"[Team].Tasks", "[Team].Customers"}  # lists only: no library, no hidden list
    columns = ok(client.get("/catalogs/Team/columns?schema=&table=Tasks", headers=AUTH))["columns"]
    assert {c["column"]: c["type"] for c in columns}["Due"] == "TIMESTAMP"
    rows, made = query(client, 'SELECT id, Title, Customer, Customer_id, "Assigned To", Hours FROM [Team].Tasks '
                               "WHERE Status = 'Open' ORDER BY id")  # fmt: skip
    assert rows[0] == [3, "Made-up task 03", "Northwind Made-up", 1, "Avery Made-up", 4.5] and len(rows) == 3
    graph = [r for r in standin.seen("graph") if r["path"].endswith("list-tasks/items")]
    assert "fields/Status eq 'Open'" in graph[-1]["query"]["$filter"]
    assert made["connection_reads"][0]["read_with"] == "Microsoft Graph ($filter sent)"
    # A column Graph will not filter (not indexed) is filtered by DuckDB instead.
    rows, made = query(client, "SELECT count(*) FROM [Team].Tasks WHERE Notes = 'made-up note 4'")
    assert rows == [[1]] and made["connection_reads"][0]["read_with"] == "Microsoft Graph"


def test_sharepoint_documents_index_and_tabular_documents_are_tables(
    client: TestClient, standin: made_up.StandIn
) -> None:
    save(
        client,
        "Team Docs",
        "sharepoint_docs",
        sharepoint_code("sharepoint_docs"),
        {"password": made_up.PASSWORD},
    )
    names = tree_names(client, "Team%20Docs")
    assert {
        "[Team Docs].Documents",
        '[Team Docs].Documents.Finance."Budget 2026.xlsx".Summary',
        '[Team Docs].Documents.Finance."Budget 2026.xlsx".Targets',
        '[Team Docs].Documents.Finance."regions.csv"',
        '[Team Docs].Documents.Reports."q3.parquet"',
    } <= set(names)
    assert not any("Travel" in n or "logo" in n for n in names)  # a Word document, a picture: not tables
    rows, _ = query(client, "SELECT name, Department FROM [Team Docs].Documents WHERE extension = 'xlsx'")
    assert rows == [["Budget 2026.xlsx", "Finance"]]
    rows, _ = query(client, 'SELECT sum(budget) FROM [Team Docs].Finance."Budget 2026.xlsx".Summary')
    assert [[str(r[0]) for r in rows]] == [["2250"]]  # the library is optional when the rest names one table
    rows, _ = query(client, 'SELECT goal FROM [Team Docs]."Budget 2026.xlsx".Targets ORDER BY 1')
    assert rows == [["Growth"], ["Margin"]]
    assert query(client, "SELECT count(*) FROM [Team Docs].Reports.q3")[0] == [[1]]


# ===== the sign-in: ROPC's words, and no secret anywhere =====


@pytest.mark.parametrize(
    ("user", "secret", "said"),
    [
        (made_up.USERNAME, "wrong-made-up", "refused the username or password (AADSTS50126)"),
        (made_up.MFA_USERNAME, made_up.PASSWORD, "ROPC) cannot do MFA"),
    ],
)
def test_ropc_refusals_are_said_plainly(
    client: TestClient, standin: made_up.StandIn, user: str, secret: str, said: str
) -> None:
    save(client, "Team", "sharepoint", sharepoint_code(user=user), {"password": secret})
    tested = client.post("/blades/Team/test", json={}, headers=AUTH)
    assert said in tested.text and secret not in tested.text


def test_no_secret_in_any_answer_log_or_file(
    client: TestClient, standin: made_up.StandIn, tmp_path: Path
) -> None:
    save(client, "Team", "sharepoint", sharepoint_code(), {"password": made_up.PASSWORD})
    save(client, "Keyed", "datalake", datalake_code("Account key"), {"account key": made_up.ACCOUNT_KEY})
    answers = [
        client.post("/blades/Team/test", json={}, headers=AGENT).text,
        client.post("/blades/Keyed/test", json={}, headers=AGENT).text,
        client.get("/connections", headers=AGENT).text,
        client.get("/connections/Team", headers=AGENT).text,
        client.post(
            "/datasets/q/query", json={"sql": "SELECT * FROM [Keyed].lake.customers"}, headers=AUTH
        ).text,
        client.post("/datasets/q/query", json={"sql": "SELECT * FROM [Team].Tasks"}, headers=AUTH).text,
        client.post("/datasets/q/query", json={"sql": "SELECT * FROM [Keyed].nope"}, headers=AUTH).text,
    ]
    assert '"rows"' in answers[1] or "found" in answers[1]
    for text in answers:
        assert not any(v in text for v in made_up.NOT_TO_BE_SEEN), text[:300]
        assert re.search(r"sig=(?!\*{4})[A-Za-z0-9%+/]{20,}", text) is None, text[:300]
    for file in (tmp_path / "state").rglob("*"):
        if file.is_file():
            text = file.read_text(encoding="utf-8", errors="replace")
            assert not any(v in text for v in made_up.NOT_TO_BE_SEEN), file
    # The account key signed a SAS here: the stand-in saw a signature, never the key.
    assert any("sv" in r["query"] for r in standin.seen("storage"))


# ===== the names (pure rules) =====


def test_path_names_resolve_by_their_last_parts_and_keep_an_at() -> None:
    places = [Place("", "sales", "orders"), Place("", "archive", "orders"), Place("", "", "returns.csv")]
    assert ct.resolve("Lake", "delta", ["sales", "orders"], places) == places[0]
    assert ct.resolve("Lake", "datalake", ["returns"], places) == places[2]
    assert ct.resolve("Lake", "delta", ["sales", "orders@v12"], places) == Place("", "sales", "orders@v12")
    with pytest.raises(ct.ConnectionSqlError, match=r"could be .*name its folders too"):
        ct.resolve("Lake", "delta", ["orders"], places)
    with pytest.raises(ct.ConnectionSqlError, match="no versions"):
        ct.resolve("Docs", "sharepoint_docs", ["x@v1"], [Place("", "Documents", "x")])
    assert ct.copy_name("Lake", places[0], "delta") == "[Lake].sales.orders"
    assert ct.copy_name(
        "Docs", Place("", "Documents/Finance", "Budget 2026.xlsx/Summary"), "sharepoint_docs"
    ) == ('[Docs].Documents.Finance."Budget 2026.xlsx".Summary')
    assert ct.quote_brackets("SELECT * FROM [Lake].sales.orders@v12", ["Lake"]) == (
        'SELECT * FROM "Lake".sales."orders@v12"'
    )
    assert ct.quote_brackets("SELECT * FROM [Lake].orders@2026-11-01 o", ["Lake"]) == (
        'SELECT * FROM "Lake"."orders@2026-11-01" o'
    )
    assert ct.quote_brackets("SELECT 'a@v1' FROM x", ["Lake"]) == "SELECT 'a@v1' FROM x"


def test_filters_go_to_a_lake_as_column_op_value() -> None:
    sql = (
        "SELECT a, b FROM \"Lake\".orders WHERE region IN ('North', 'South') AND amount >= 10 "
        "AND day BETWEEN DATE '2026-11-01' AND DATE '2026-11-30' AND note IS NULL AND 5 < qty"
    )
    ref = ct.Reference("Lake", ("orders",))
    pushed = ct.pushdown(sql, ["Lake"], ref, ["a", "b", "region", "amount", "day", "note", "qty"], "delta")
    assert pushed.filters == (
        ("region", "in", ["North", "South"]),
        ("amount", ">=", 10),
        ("day", "between", ["2026-11-01", "2026-11-30"]),
        ("note", "is null", None),
        ("qty", ">", 5),
    )
    assert pushed.where == "" and set(pushed.columns) == {"a", "b", "region", "amount", "day", "note", "qty"}


# ===== every setting from an environment variable (the owner, 2026-11-17: "All should be mapable") =====


def test_every_setting_maps_to_an_environment_variable_and_reads_back(client: TestClient) -> None:
    code = way("sharepoint", "Username and password (ROPC)")
    inspected = ok(
        client.post("/blades/inspect", json={"code": code, "template": "sharepoint"}, headers=AUTH)
    )
    fields = {s["name"]: s for s in inspected["settings"]}
    assert {n: fields[n]["suggested_env"] for n in ("tenant", "client id", "username", "site")} == {
        "tenant": "SHAREPOINT_TENANT_ID",
        "client id": "SHAREPOINT_CLIENT_ID",
        "username": "SHAREPOINT_USERNAME",
        "site": "SHAREPOINT_SITE_URL",
    }
    pairs = (
        ("tenant", made_up.TENANT),
        ("client id", made_up.CLIENT),
        ("username", made_up.USERNAME),
        ("site", SITE),
    )
    values = {fields[n]["id"]: {"value": v, "env": fields[n]["suggested_env"]} for n, v in pairs}
    body = {"code": code, "values": values, "template": "sharepoint"}
    filled_in = ok(client.post("/blades/fill", json=body, headers=AUTH))
    mapped = filled_in["code"]
    assert f'site_url = os.environ.get("SHAREPOINT_SITE_URL", "{SITE}")' in mapped
    assert f'username = os.environ.get("SHAREPOINT_USERNAME", "{made_up.USERNAME}")' in mapped
    # Read back into the form: each field says its variable, its value this computer's default.
    back = {s["name"]: s for s in filled_in["settings"]}
    assert (back["tenant"]["env"], back["tenant"]["value"]) == ("SHAREPOINT_TENANT_ID", made_up.TENANT)
    # The mappings as the export, Run settings and the Variables page read them.
    from swissarmybench.domain.blades import env_settings

    assert {m["variable"] for m in env_settings(mapped)} == {
        "SHAREPOINT_TENANT_ID",
        "SHAREPOINT_CLIENT_ID",
        "SHAREPOINT_USERNAME",
        "SHAREPOINT_SITE_URL",
    }
    save(client, "Team", "sharepoint", mapped.replace('secret("password")', 'secret("SHAREPOINT_PASSWORD")'))
    listed = str(ok(client.get("/variables", headers=AUTH)))
    assert "SHAREPOINT_SITE_URL" in listed and "Team" in listed


# ===== writes: what the Write starters call (dry runs read; writes change the stand-ins) =====

# Where a deltalake install lives when the test Python has none (a folder put on sys.path): optional.
LAKES_SITE = os.environ.get("SAB_DELTALAKE_PATH", "")


def connected(code: str, secrets: dict[str, str] | None = None) -> Any:
    from swissarmybench.adapters.blade_run import run_code

    conn, _ = run_code(code, "conn", secrets or {}, "Lake")
    return conn


def local_lake(standin: made_up.StandIn) -> Any:
    root = standin.root / made_up.ACCOUNT / made_up.CONTAINER
    return connected(way("delta", "A folder on this computer").replace('r"C:\\lake"', f'r"{root}"'))


def test_a_data_lake_writes_parquet_and_csv_files_through_the_adls_api(standin: made_up.StandIn) -> None:
    import pyarrow as pa

    conn = connected(datalake_code(), {"client secret": made_up.SECRET})
    rows = pa.table({"region": ["North", "South"], "target": [10.5, 20.0]})
    assert conn.write_file("targets.parquet", rows, "parquet") == {"written": conn.write_file(
        "targets.parquet", rows, "parquet")["written"], "path": "targets.parquet", "rows": 2}  # fmt: skip
    conn.write_file("exports/targets.csv", rows, "csv")
    writes = [r["action"] for r in standin.seen("storage write")]
    assert writes[:3] == ["file", "append", "flush"]
    assert conn.rows("targets")[0].to_pylist() == [
        {"region": "North", "target": 10.5},
        {"region": "South", "target": 20.0},
    ]
    assert conn.rows("exports/targets")[1] == 2


def test_a_delta_writes_dry_runs_count_without_writing(standin: made_up.StandIn) -> None:
    import pyarrow as pa

    conn = local_lake(standin)
    incoming = pa.table({"order_id": [5, 6], "amount": [1.0, 2.0], "region": ["West", "West"]})
    assert conn.count_matches("orders", incoming, ["order_id"]) == (1, 5)  # one update, five rows now
    assert conn.count_where("orders", "region = 'North'") == 2
    assert conn.optimize_delta("lake/orders", dry_run=True) == {"files": 4, "small": 4, "version": 1}
    with pytest.raises(Exception, match=r"at least 168 hours \(7 days\)"):
        conn.vacuum_delta("lake/orders", retention_hours=24)
    assert conn.rows("orders")[1] == 5  # nothing changed


def test_delta_writes_with_the_deltalake_package(
    standin: made_up.StandIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pyarrow as pa

    if LAKES_SITE and Path(LAKES_SITE).is_dir():
        monkeypatch.syspath_prepend(LAKES_SITE)
    pytest.importorskip("deltalake")
    conn = local_lake(standin)
    incoming = pa.table({"order_id": [5, 6], "amount": [99.0, 7.5], "region": ["West", "West"]})
    assert conn.write_delta("lake/orders", incoming, "merge", ["order_id"]) == {"inserted": 1, "updated": 1}
    assert conn.rows("orders")[1] == 6
    assert conn.write_delta("lake/orders", incoming.slice(1), "append") == {"written": 1}
    assert conn.delete_delta("lake/orders", "order_id = 6") == {"deleted": 2}
    assert conn.rows("orders", filters=[["order_id", "=", 5]])[0].to_pylist()[0]["amount"] == 99.0
    assert conn.history("orders")[0]["version"] == 4  # merge, append, delete: three commits
    assert conn.rows("orders@v1")[1] == 5  # time travel still reads the table as it was
    assert conn.vacuum_delta("lake/orders", dry_run=True)["dry_run"] is True
    assert conn.optimize_delta("lake/orders", dry_run=False)["added"] >= 1


def test_sharepoint_list_writes_are_batched_and_retried_on_429(standin: made_up.StandIn) -> None:
    conn = connected(sharepoint_code(), {"password": made_up.PASSWORD})
    standin.refuse_once.add("all")  # the first answer to each request: 429, Retry-After 0
    assert conn.create("Tasks", [{"Title": "Made-up new task", "Status": "Open", "Hours": 2}] * 25) == {
        "done": 25
    }
    assert [r["count"] for r in standin.seen("batch")] == [20, 20, 5]  # 20 a batch; the refused ones again
    assert len(standin.tasks) == 35
    assert conn.update("Tasks", [{"Title": "Made-up task 02", "Status": "Done"}], key="Title") == {"done": 1}
    assert standin.tasks[2]["Status"] == "Done"
    assert conn.update("Tasks", [{"id": 3, "Customer_id": 2}]) == {"done": 1}
    assert standin.tasks[3]["CustomerLookupId"] == 2
    assert conn.delete("Tasks", [1, 4]) == {"done": 2}
    assert 1 not in standin.tasks and len(standin.tasks) == 33
    with pytest.raises(Exception, match="No item has Title"):
        conn.update("Tasks", [{"Title": "nope", "Status": "Done"}], key="Title")
