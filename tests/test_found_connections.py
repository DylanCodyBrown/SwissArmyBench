"""Find connections on this computer: the known tools' readers, the hint scan, the list and the import's body
(domain/found_connections.py, domain/found_readers.py), and the finder over a made-up home folder
(adapters/found_connections.py). Every fixture is made up; no made-up password may be in any answer."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from swissarmybench.adapters import found_connections as finder_module
from swissarmybench.adapters.found_connections import ConnectionFinder
from swissarmybench.domain import blades as blade_rules
from swissarmybench.domain import found_connections as rules
from swissarmybench.domain import found_readers as readers
from swissarmybench.domain import portability
from swissarmybench.server.blade_templates import TEMPLATES
from tests import found_fixtures as fx

TEMPLATE = {t.id: t.to_json() for t in TEMPLATES}
LABELS = {t.id: t.label for t in TEMPLATES}


def no_password(value: object) -> None:
    text = repr(value)
    assert [p for p in fx.PASSWORDS if p in text] == []


def by_name(found: list[rules.Found]) -> dict[str, rules.Found]:
    return {f.name: f for f in found}


# ===== the parts tools write a connection in =====


def test_a_connection_string_keeps_its_braces_and_never_its_password() -> None:
    pairs = rules.connection_pairs(
        "Driver={ODBC Driver 18 for SQL Server};Server=tcp:sales.corp.internal,1444;Database=Sales;"
        "UID=reader;PWD={MadeUpPw-Odbc-6};Encrypt=yes"
    )
    assert pairs["driver"] == "ODBC Driver 18 for SQL Server"
    assert "pwd" not in pairs
    found = rules.from_pairs(pairs)
    assert found is not None
    assert (found.kind, found.server, found.port, found.database, found.user) == (
        "sqlserver",
        "sales.corp.internal",
        1444,
        "Sales",
        "reader",
    )


def test_a_named_instance_and_windows_sign_in() -> None:
    found = rules.from_pairs(
        rules.connection_pairs(r"Data Source=fin01\LEDGER;Initial Catalog=Ledger;Integrated Security=SSPI"),
        kind="sqlserver",
    )
    assert found is not None
    assert (found.server, found.instance, found.database, found.windows) == (
        "fin01",
        "LEDGER",
        "Ledger",
        True,
    )


@pytest.mark.parametrize(
    ("url", "kind", "server", "port", "database", "user"),
    [
        (
            "jdbc:postgresql://pg.shop.internal:5432/shop?user=analyst",
            "postgres",
            "pg.shop.internal",
            5432,
            "shop",
            "analyst",
        ),
        (
            "jdbc:sqlserver://fin01\\LEDGER:1433;databaseName=Ledger;user=reader;password=MadeUpPw-Jdbc-12",
            "sqlserver",
            "fin01",
            1433,
            "Ledger",
            "reader",
        ),
        ("jdbc:jtds:sqlserver://fin01:1433/Ledger", "sqlserver", "fin01", 1433, "Ledger", ""),
        (
            "jdbc:oracle:thin:@//ora.orders.internal:1521/ORDERS",
            "oracle",
            "ora.orders.internal",
            1521,
            "ORDERS",
            "",
        ),
        ("jdbc:oracle:thin:clerk/MadeUpPw-Jdbc-12@ora01:1521:ORCL", "oracle", "ora01", 1521, "ORCL", "clerk"),
        (
            "jdbc:oracle:thin:@(DESCRIPTION=(ADDRESS=(HOST=ora02)(PORT=1522))(CONNECT_DATA=(SERVICE_NAME=HR)))",
            "oracle",
            "ora02",
            1522,
            "HR",
            "",
        ),
        (
            "postgresql://metrics:MadeUpPw-Url-5@metrics.corp.internal/metrics",
            "postgres",
            "metrics.corp.internal",
            None,
            "metrics",
            "metrics",
        ),
        (
            "mysql+pymysql://app@mysql.shop.internal:3307/shop",
            "mysql",
            "mysql.shop.internal",
            3307,
            "shop",
            "app",
        ),
        (
            "mongodb+srv://u:MadeUpPw-Url-5@cluster0.events.internal/events",
            "mongodb",
            "cluster0.events.internal",
            None,
            "events",
            "u",
        ),
        (
            "snowflake://loader@acme-made-up/ANALYTICS?warehouse=WH",
            "snowflake",
            "acme-made-up",
            None,
            "ANALYTICS",
            "loader",
        ),
        ("jdbc:trino://trino.corp.internal:8443/hive", "trino", "trino.corp.internal", 8443, "hive", ""),
    ],
)
def test_urls(url: str, kind: str, server: str, port: int | None, database: str, user: str) -> None:
    found = rules.parse_url(url)
    assert found is not None
    found = rules.clean(found)
    assert (found.kind, found.server, found.port, found.database, found.user) == (
        kind,
        server,
        port,
        database,
        user,
    )
    no_password(found)


def test_a_file_database_url() -> None:
    found = rules.parse_url("jdbc:sqlite:C:\\data\\cache.sqlite")
    assert found is not None and (found.kind, found.path) == ("sqlite", "C:\\data\\cache.sqlite")


def test_scrub_cuts_every_password_shape() -> None:
    text = "Server=a;Password=MadeUpPw-Hint-4;Pwd={MadeUpPw-Odbc-6};x postgres://u:MadeUpPw-Url-5@h/db"
    cleaned = rules.scrub(text)
    no_password(cleaned)
    assert "postgres://u@h/db" in cleaned and "Server=a" in cleaned


def test_clean_scrubs_every_text_field() -> None:
    found = rules.clean(rules.Found(kind="postgres", name="Server=x;Password=MadeUpPw-Hint-4", server="h"))
    no_password(found)


# ===== the known tools' readers =====


def test_dbeaver() -> None:
    found = by_name(readers.read("dbeaver", fx.DBEAVER))
    assert found["Shop (dev)"].kind == "postgres"
    assert (found["Shop (dev)"].server, found["Shop (dev)"].port, found["Shop (dev)"].user) == (
        "pg.shop.internal",
        5432,
        "analyst",
    )
    assert found["Finance ledger"].kind == "sqlserver" and found["Finance ledger"].windows
    assert found["Local cache"].path == "C:\\data\\cache.sqlite"
    assert found["Events"].kind == "mongodb"
    no_password(found)


def test_ssms_registered_servers_and_recent_connections() -> None:
    found = by_name(readers.read("regsrvr", fx.REGSRVR))
    assert set(found) == {"Sales warehouse", "Finance"}  # the Analysis Services one is not a database engine
    sales = found["Sales warehouse"]
    assert (sales.server, sales.instance, sales.database, sales.user) == (
        "sales-sql02.corp.internal",
        "WAREHOUSE",
        "SalesDW",
        "report_reader",
    )
    assert found["Finance"].windows
    recent = readers.read("ssms_recent", fx.SSMS_RECENT)
    assert [(f.server, f.user, f.database, f.windows) for f in recent] == [
        ("hr-sql03.corp.internal", "hr_viewer", "People", False)
    ]


def test_editor_settings_with_comments() -> None:
    ads = readers.read("editor_settings", fx.ADS_SETTINGS)
    assert [(f.kind, f.name, f.server, f.user) for f in ads] == [
        ("azuresql", "Ops on Azure", "ops-made-up.database.windows.net", "ops_reader")
    ]
    code = by_name(readers.read("editor_settings", fx.VSCODE_SETTINGS))
    assert code["Ledger (VS Code)"].windows
    assert (code["Shop reporting"].kind, code["Shop reporting"].port) == ("mysql", 3306)
    assert code["Notes"].path == "/home/someone/notes.db"
    no_password([ads, code])


def test_jetbrains_with_its_local_file_and_projects() -> None:
    found = readers.read("jetbrains", fx.JETBRAINS, local=fx.JETBRAINS_LOCAL)
    assert [(f.kind, f.database, f.user) for f in found] == [("postgres", "inventory", "stock_clerk")]
    no_password(found)
    assert readers.jetbrains_projects(fx.JETBRAINS_RECENT) == ["$USER_HOME$/IdeaProjects/orders-service"]
    oracle = readers.read("jetbrains", fx.PROJECT_SOURCES)
    assert [(f.kind, f.server, f.port, f.database) for f in oracle] == [
        ("oracle", "ora.orders.internal", 1521, "ORDERS")
    ]


def test_pgadmin_rows() -> None:
    found = readers.read_pgadmin(
        [{"name": "Shop", "host": "pg.shop.internal", "port": 5432, "username": "u"}]
    )
    assert [(f.kind, f.server, f.port) for f in found] == [("postgres", "pg.shop.internal", 5432)]


def test_mysql_workbench_and_heidisql() -> None:
    found = readers.read("mysql_workbench", fx.WORKBENCH)
    assert [(f.name, f.server, f.database, f.user) for f in found] == [
        ("Shop reporting (Workbench)", "mysql.shop.internal", "reporting", "reporter")
    ]
    heidi = readers.read("heidisql", fx.HEIDI_PORTABLE)
    assert [(f.kind, f.name, f.server, f.database, f.user) for f in heidi] == [
        ("mysql", "Shop", "maria.shop.internal", "shop", "shop_app")
    ]
    assert "Password" not in readers.heidisql_portable(fx.HEIDI_PORTABLE)["Shop"]
    no_password([found, heidi])


def test_odbc_ini_and_dsn_files() -> None:
    found = by_name(readers.read("odbc_ini", fx.ODBC_INI))
    # A driver we have a connection for, with its server: that kind (portable); else the data source itself.
    assert (found["Inventory"].kind, found["Inventory"].server, found["Inventory"].user) == (
        "postgres",
        "pg.shop.internal",
        "stock_clerk",
    )
    assert (found["Legacy"].kind, found["Legacy"].dsn) == ("odbc", "Legacy")
    dsn = readers.read("dsn", fx.DSN_FILE, "CRM")
    assert [(f.kind, f.name, f.server, f.database, f.windows) for f in dsn] == [
        ("sqlserver", "CRM", "crm-sql06.corp.internal", "Crm", True)
    ]
    no_password(found)


def test_office_odc_and_udl() -> None:
    odc = readers.read("odc", fx.ODC, "Budget")
    assert [(f.kind, f.server, f.database, f.user) for f in odc] == [
        ("sqlserver", "plan-sql04.corp.internal", "Budget", "budget_reader")
    ]
    udl = readers.read("udl", fx.UDL, "Payroll")
    assert [(f.kind, f.server, f.database, f.windows) for f in udl] == [
        ("sqlserver", "pay-sql05", "Payroll", True)
    ]
    no_password(odc)


def test_the_registrys_odbc_and_heidisql_values() -> None:
    found = by_name(
        readers.read_odbc(
            {
                "Stock": {
                    "Driver": "SQLSRV32.dll",
                    "Server": "stock01",
                    "Database": "Stock",
                    "PWD": "MadeUpPw-Odbc-6",
                }
            },
            {"Stock": "SQL Server"},
        )
    )
    assert (found["Stock"].kind, found["Stock"].server, found["Stock"].dsn) == (
        "sqlserver",
        "stock01",
        "Stock",
    )
    heidi = readers.read_heidisql(
        {"Reports": {"Host": "r01", "NetType": "8", "Password": "MadeUpPw-Heidi-7"}}
    )
    assert [(f.kind, f.server) for f in heidi] == [("postgres", "r01")]
    no_password([found, heidi])


def test_a_file_that_is_not_its_tools_is_no_connections() -> None:
    assert readers.read("dbeaver", "not json") == []
    assert readers.read("regsrvr", "<!DOCTYPE x [<!ENTITY a 'b'>]><x>&a;</x>") == []
    assert readers.read("jetbrains", "<unclosed") == []


# ===== the hint scan =====


def test_hints_in_a_config_and_a_json_file() -> None:
    config = readers.hints(fx.HINT_CONFIG, "app.config")
    assert [(f.kind, f.server, f.database, f.user) for f in config] == [
        ("sqlserver", "orders-sql07.corp.internal", "Orders", "orders_app")
    ]
    found = readers.hints(fx.HINT_JSON, "settings.json")
    assert {(f.kind, f.server, f.database) for f in found} == {
        ("postgres", "metrics.corp.internal", "metrics"),
        ("redshift", "wh.corp.internal", "dw"),  # host, port and database: its port says its kind
    }
    no_password([config, found])


def test_placeholders_are_no_hints() -> None:
    text = '{"a": "Server=your-server;Database=my_database", "b": "postgres://user@${DB_HOST}/db"}'
    assert readers.hints(text, "x.json") == []


def test_a_snowflake_address_is_a_hint() -> None:
    found = readers.hints('url = "https://acme-made-up.snowflakecomputing.com"', "x.toml")
    assert [(f.kind, f.server) for f in found] == [("snowflake", "acme-made-up")]


@pytest.mark.parametrize(
    "parts",
    [
        ("Google", "Chrome", "User Data"),
        ("Mozilla", "Firefox"),
        ("Bitwarden",),
        (".ssh",),
        ("Microsoft", "Credentials"),
        ("Microsoft", "Edge"),
        ("SwissArmyBench", "library"),
        ("tool", "node_modules"),
        ("tool", ".git"),
        ("Dropbox",),
        ("1Password",),
    ],
)
def test_folders_never_looked_in(parts: tuple[str, ...]) -> None:
    assert readers.skip_folder(parts)


def test_the_files_the_hint_scan_opens() -> None:
    assert readers.hint_file("app.config", 300)
    assert not readers.hint_file("app.config", readers.MAX_FILE_BYTES + 1)
    assert not readers.hint_file("credentials-config.json", 10)
    assert not readers.hint_file("tokens.json", 10)
    assert not readers.hint_file("state.db", 10)


# ===== the list =====


def test_merge_and_already_added() -> None:
    dbeaver = rules.Source("DBeaver")
    pgadmin = rules.Source("pgAdmin 4")
    a = rules.Found(
        kind="postgres", name="Shop (dev)", server="PG.shop.internal", database="shop", sources=(dbeaver,)
    )
    b = rules.Found(
        kind="postgres", server="pg.shop.internal", database="Shop", user="analyst", sources=(pgadmin,)
    )
    merged = rules.merge([a, b])
    assert len(merged) == 1
    assert merged[0].user == "analyst" and [s.tool for s in merged[0].sources] == ["DBeaver", "pgAdmin 4"]
    # The library has it: its starter's code filled in the same server and database.
    code = blade_rules.apply_settings(
        TEMPLATE["postgres"]["code"],
        {
            s.id: v
            for s in blade_rules.detect_settings(TEMPLATE["postgres"]["code"])
            for v in [{"server": "pg.shop.internal", "database": "shop"}.get(s.name)]
            if v
        },
    )
    saved = rules.found_from_settings("postgres", [s.to_json() for s in blade_rules.detect_settings(code)])
    assert saved is not None
    listed = rules.rows(merged, {rules.key_of(saved): "Shop"})
    assert listed[0].already == "Shop"


def test_a_kind_we_have_no_connection_for_is_listed_not_supported() -> None:
    listed = rules.rows([rules.clean(rules.Found(kind="mongodb", server="m1", database="e"))], {})
    row = listed[0].to_json(LABELS)
    assert row["supported"] is False and row["why"] == "Swiss Army Bench has no MongoDB connection yet"


def test_azure_sql_is_told_by_its_address() -> None:
    found = rules.clean(rules.Found(kind="sqlserver", server="ops.database.windows.net"))
    assert found.kind == "azuresql"


def test_unique_names_and_variables() -> None:
    assert rules.unique_name("pg@localhost", []) == "pg localhost"
    assert rules.unique_name("Shop", ["shop"]) == "Shop 2"
    assert rules.unique_name("#$%", []) == "Found connection"
    assert rules.unique_variable("Shop (dev)", []) == "SHOP_DEV_PASSWORD"
    assert rules.unique_variable("Shop (dev)", ["SHOP_DEV_PASSWORD"]) == "SHOP_DEV_PASSWORD_2"


# ===== the import's body: the starter's code filled in =====


def test_a_postgres_connection_from_its_starter() -> None:
    found = rules.Found(
        kind="postgres", server="pg.shop.internal", port=5433, database="shop", user="analyst"
    )
    body, used = rules.connection_body(found, TEMPLATE["postgres"], "Shop", "SHOP_PASSWORD")
    assert used == "SHOP_PASSWORD"
    assert 'host="pg.shop.internal"' in body["code"] and "port=5433" in body["code"]
    assert 'dbname="shop"' in body["code"] and 'user="analyst"' in body["code"]
    assert 'secret("SHOP_PASSWORD")' in body["code"]
    assert (body["template"], body["kind"], body["dialect"]) == ("postgres", "sql", "postgres")


def test_sql_server_with_windows_sign_in_keeps_the_amber_note() -> None:
    found = rules.Found(kind="sqlserver", server="fin01", instance="LEDGER", database="Ledger", windows=True)
    body, used = rules.connection_body(found, TEMPLATE["sqlserver"], "Finance", "FINANCE_PASSWORD")
    assert used is None  # Windows sign-in: no password
    assert 'sign_in="windows"' in body["code"] and 'server="fin01"' in body["code"]
    assert 'instance="LEDGER"' in body["code"] and 'database="Ledger"' in body["code"]
    assert "import pyodbc" not in body["code"]  # mssql-python, no ODBC driver
    notes = portability.check(body["code"], "sqlserver")
    assert [n.key for n in notes] == ["windows"]


def test_sql_server_with_a_login_on_mssql_python() -> None:
    found = rules.Found(kind="sqlserver", server="sales01", database="Sales", user="reader")
    body, used = rules.connection_body(found, TEMPLATE["sqlserver"], "Sales", "SALES_PASSWORD")
    assert used == "SALES_PASSWORD" and 'secret("SALES_PASSWORD")' in body["code"]
    assert portability.check(body["code"], "sqlserver") == []


def test_an_odbc_data_source_and_a_file_database() -> None:
    body, used = rules.connection_body(
        rules.Found(kind="odbc", dsn="Legacy"), TEMPLATE["odbc"], "Legacy", "X"
    )
    assert "DSN=Legacy" in body["code"] and used is None
    assert [n.key for n in portability.check(body["code"], "odbc")] == ["odbc"]
    body, _ = rules.connection_body(
        rules.Found(kind="sqlite", path="/data/cache.sqlite"), TEMPLATE["sqlite"], "C", "X"
    )
    assert "/data/cache.sqlite" in body["code"]


def test_oracle_data_source() -> None:
    found = rules.Found(kind="oracle", server="ora01", port=1521, database="ORDERS", user="clerk")
    body, _ = rules.connection_body(found, TEMPLATE["oracle"], "Orders", "ORDERS_PASSWORD")
    assert '"ora01:1521/ORDERS"' in body["code"] and 'user="clerk"' in body["code"]


# ===== the finder over a made-up home folder =====


@pytest.fixture
def windows(tmp_path: Path) -> Path:
    return fx.windows_home(tmp_path / "home")


def test_the_finder_reads_every_known_tool_on_windows(windows: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[Path] = []
    real = finder_module._text

    def recording(path: Path, limit: int) -> str | None:
        opened.append(path)
        return real(path, limit)

    monkeypatch.setattr(finder_module, "_text", recording)
    registry = fx.FakeRegistry(fx.REGISTRY)
    scan = ConnectionFinder(home=windows, system="windows", registry=registry, skip=lambda: ()).scan()
    tools = {s.tool for f in scan.found for s in f.sources}
    assert {
        "DBeaver",
        "SSMS",
        "Azure Data Studio",
        "VS Code",
        "JetBrains",
        "pgAdmin 4",
        "MySQL Workbench",
        "HeidiSQL",
        "ODBC",
        "Office",
        "OrdersTool",
        "MetricsAgent",
    } <= tools
    assert readers.SKIPPED_BINARY in scan.notes
    names = {rules.name_for(f) for f in scan.found}
    assert {"Stock", "Reports", "orders", "CRM", "Payroll", "Budget"} <= names
    no_password(scan.found)
    # The decoys were never opened: a browser's profile, a password manager, .ssh, a big file, this app's own.
    for path in opened:
        text = str(path).casefold()
        assert not any(
            w in text for w in ("chrome", "mozilla", "bitwarden", ".ssh", "huge.json", "swissarmybench")
        )
        assert path.name != "credentials-config.json"
    hosts = {f.server for f in scan.found}
    assert not any(h.startswith("decoy") for h in hosts)
    # The registry: only named values asked for (the list key of data sources aside).
    assert all(names is not None or path.endswith("ODBC Data Sources") for _, path, names in registry.asked)
    hint = next(f for f in scan.found if f.server == "orders-sql07.corp.internal")
    assert hint.sources[0].searched and hint.sources[0].where == "AppData\\Roaming\\OrdersTool"


def test_the_finder_on_linux(tmp_path: Path) -> None:
    home = fx.linux_home(tmp_path / "home")
    scan = ConnectionFinder(home=home, system="linux").scan()
    found = by_name(scan.found)
    assert found["Inventory"].sources[0].tool == "ODBC"
    assert "Shop (pgAdmin)" in found or any(s.tool == "pgAdmin 4" for f in scan.found for s in f.sources)
    assert any(s.where.startswith(".config/OrdersTool") for f in scan.found for s in f.sources)
    assert not any(f.server.startswith("decoy") for f in scan.found)
    no_password(scan.found)


def test_cancel_and_the_time_limit(windows: Path) -> None:
    cancel = threading.Event()
    cancel.set()
    assert ConnectionFinder(home=windows, system="windows").scan(cancel).stopped == "cancel"
    times = iter([0.0, *([10.0] * 1000)])
    late = ConnectionFinder(home=windows, system="windows", seconds=4.0, clock=lambda: next(times)).scan()
    assert late.stopped == "time"


def test_the_known_tools_only(windows: Path) -> None:
    scan = ConnectionFinder(home=windows, system="windows").scan(hints=False)
    assert not any(s.searched for f in scan.found for s in f.sources)
