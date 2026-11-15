"""The real-world test bed: real databases and made-up files, set up with one command and torn down with one.

    python tools/testbed/testbed.py up        # start PostgreSQL and MariaDB, load them; write the files
    python tools/testbed/testbed.py status    # what is running, where (the same JSON the tests read)
    python tools/testbed/testbed.py down      # stop both databases, remove the folder

Everything goes in one folder (SAB_TESTBED_DIR, else swissarmybench-testbed in the system's temporary
folder): the databases' own data folders, SQLite and DuckDB files, CSVs, workbooks, Parquet and JSON, and
`testbed.json`, which says where each one is and the made-up passwords. Nothing is written anywhere else.

PostgreSQL and MariaDB are this machine's own servers (`apt-get install postgresql mariadb-server` on
Ubuntu), started here on ports of their own (55432 and 53306) for 127.0.0.1 only, so a server the machine
already runs is not touched. Either one missing is left out and said so; the tests that need it skip.
They are test machinery: the app does not depend on them, and the drivers the app's connections use
(psycopg, mariadb) go into the test environment only.

The data is tools/testbed/company.py's made-up company. The cloud services (Power BI, Azure Key Vault)
are stand-ins the tests start themselves (tools/testbed/standins.py).
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.testbed.company import Company, line_amount, make_company

PG_PORT = 55432
MARIA_PORT = 53306
PG_PASSWORD = "made-up-postgres-password"  # noqa: S105 (a made-up password for a test database)
MARIA_PASSWORD = "made-up-mariadb-password"  # noqa: S105 (as above)
USER = "bench_reader"
DAILY_DAYS = 14


def folder() -> Path:
    return Path(os.environ.get("SAB_TESTBED_DIR") or Path(tempfile.gettempdir()) / "swissarmybench-testbed")


def state_file() -> Path:
    return folder() / "testbed.json"


def read_state() -> dict[str, Any] | None:
    """What `up` wrote, or None when the test bed is not set up."""
    try:
        state: dict[str, Any] = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return state


# ===== the files =====


def _text(value: Any) -> str:
    return "" if value is None else value.isoformat() if isinstance(value, date) else str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({k: _text(v) for k, v in row.items()} for row in rows)


def daily_exports(company: Company, last: date) -> dict[str, list[dict[str, Any]]]:
    """The web shop's daily CSV export, one file a day for the last two weeks: each order line."""
    products = {p["product_id"]: p for p in company.products}
    by_day: dict[str, list[dict[str, Any]]] = {}
    dates = {o["order_id"]: o for o in company.clean_orders()}
    for line in company.order_lines:
        order = dates.get(line["order_id"])
        if order is None or order["order_date"] <= last - timedelta(days=DAILY_DAYS):
            continue
        by_day.setdefault(order["order_date"].isoformat(), []).append(
            {
                "order_id": line["order_id"],
                "line_no": line["line_no"],
                "customer_id": order["customer_id"],
                "order_date": order["order_date"],
                "sku": products[line["product_id"]]["sku"],
                "quantity": line["quantity"],
                "amount": line_amount(line),
            }
        )
    return dict(sorted(by_day.items()))


def write_files(company: Company, files: Path) -> dict[str, str]:
    import openpyxl
    import pyarrow as pa
    import pyarrow.parquet as pq
    from openpyxl.styles import Font

    files.mkdir(parents=True, exist_ok=True)
    daily = files / "daily_orders"
    for day, rows in daily_exports(company, company.orders[-1]["order_date"]).items():
        write_csv(daily / f"orders_{day}.csv", rows)
    # The product catalogue as the buyers keep it: a workbook, a sheet of products and one of categories.
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Products"
    sheet.append(["sku", "product_name", "category_id", "unit_price"])
    categories = list(dict.fromkeys(p["category"] for p in company.products))
    for p in company.products:
        sheet.append([p["sku"], p["product_name"], categories.index(p["category"]) + 1, p["unit_price"]])
    sheet = book.create_sheet("Categories")
    sheet.append(["category_id", "category", "buyer"])
    for i, name in enumerate(categories, 1):
        sheet.append([i, name, f"Buyer {chr(64 + i)}"])
    book.save(files / "catalogue.xlsx")
    # An invoice template: a header, the customer's block, a table of lines, a total.
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Invoice"
    sheet["A1"] = "Quillmere Supply"
    sheet["A1"].font = Font(bold=True, size=16)
    sheet["A2"] = "Unit 4, Made-up Trading Estate"
    sheet["E1"] = "INVOICE"
    sheet["E1"].font = Font(bold=True, size=14)
    for row, label in enumerate(("Customer", "Customer id", "Statement date", "Open invoices"), 4):
        sheet.cell(row, 1, label).font = Font(bold=True)
    sheet.column_dimensions["A"].width = 18  # the open invoices go from A9 down, under their headings
    book.save(files / "invoice_template.xlsx")
    products = pa.Table.from_pylist(company.products)
    pq.write_table(products, files / "products.parquet")
    (files / "returns.json").write_text(json.dumps(company.returns, indent=1), encoding="utf-8")
    write_csv(files / "customers.csv", company.customers)
    return {
        "folder": str(files),
        "daily_orders": str(daily),
        "catalogue": str(files / "catalogue.xlsx"),
        "invoice_template": str(files / "invoice_template.xlsx"),
        "products_parquet": str(files / "products.parquet"),
        "returns_json": str(files / "returns.json"),
        "customers_csv": str(files / "customers.csv"),
    }


# ===== SQLite and DuckDB files =====

SCHEMAS: dict[str, dict[str, str]] = {
    "customers": {
        "customer_id": "INTEGER",
        "customer_name": "VARCHAR(80)",
        "segment": "VARCHAR(20)",
        "region": "VARCHAR(10)",
        "town": "VARCHAR(40)",
        "email": "VARCHAR(120)",
        "since": "DATE",
    },
    "products": {
        "product_id": "INTEGER",
        "sku": "VARCHAR(12)",
        "product_name": "VARCHAR(60)",
        "category": "VARCHAR(20)",
        "unit_price": "DECIMAL(10,2)",
        "unit_cost": "DECIMAL(10,2)",
    },
    "orders": {
        "order_id": "INTEGER",
        "customer_id": "INTEGER",
        "order_date": "DATE",
        "status": "VARCHAR(20)",
        "channel": "VARCHAR(20)",
        "region": "VARCHAR(10)",
    },
    "order_lines": {
        "order_id": "INTEGER",
        "line_no": "INTEGER",
        "product_id": "INTEGER",
        "quantity": "INTEGER",
        "unit_price": "DECIMAL(10,2)",
        "discount_pct": "INTEGER",
    },
    "invoices": {
        "invoice_id": "VARCHAR(20)",
        "order_id": "INTEGER",
        "customer_id": "INTEGER",
        "region": "VARCHAR(10)",
        "invoice_date": "DATE",
        "due_date": "DATE",
        "amount": "DECIMAL(12,2)",
        "paid_date": "DATE",
    },
    "budgets": {
        "department": "VARCHAR(20)",
        "month": "DATE",
        "category": "VARCHAR(20)",
        "planned": "DOUBLE PRECISION",
    },
    "stock": {
        "warehouse": "VARCHAR(40)",
        "product_id": "INTEGER",
        "on_hand": "INTEGER",
        "reorder_at": "INTEGER",
    },
}


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return repr(value)
    return "'" + _text(value).replace("'", "''") + "'"


def inserts(table: str, rows: list[dict[str, Any]], qualified: str, batch: int = 500) -> list[str]:
    names = ", ".join(rows[0])
    statements = []
    for start in range(0, len(rows), batch):
        values = ",\n".join(
            "(" + ", ".join(_literal(v) for v in row.values()) + ")" for row in rows[start : start + batch]
        )
        statements.append(f"INSERT INTO {qualified} ({names}) VALUES\n{values};")
    return statements


def create(table: str, qualified: str, double: str = "DOUBLE PRECISION") -> str:
    columns = ", ".join(f"{n} {t.replace('DOUBLE PRECISION', double)}" for n, t in SCHEMAS[table].items())
    return f"CREATE TABLE {qualified} ({columns});"


def write_sqlite(company: Company, path: Path) -> None:
    import sqlite3

    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as db:
        for table in ("invoices", "customers"):
            db.execute(create(table, table, "REAL"))
            db.executescript("\n".join(inserts(table, company.tables()[table], table)))


def write_duckdb(company: Company, path: Path) -> None:
    import duckdb

    path.unlink(missing_ok=True)
    db = duckdb.connect(str(path))
    try:
        for table in ("budgets", "stock"):
            db.execute(create(table, table))
            for statement in inserts(table, company.tables()[table], table):
                db.execute(statement)
    finally:
        db.close()


# ===== PostgreSQL =====


def _free(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


def _as_postgres(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    prefix = ["runuser", "-u", "postgres", "--"] if os.geteuid() == 0 else []
    return subprocess.run(prefix + command, check=True, text=True, capture_output=True, **kwargs)


def _pg_bin() -> Path | None:
    found = shutil.which("pg_ctl")
    if found:
        return Path(found).parent
    versions = sorted(Path("/usr/lib/postgresql").glob("*/bin/pg_ctl"))
    return versions[-1].parent if versions else None


def start_postgres(company: Company, data: Path, port: int) -> dict[str, Any]:
    bin = _pg_bin()
    if bin is None:
        return {"missing": "PostgreSQL is not installed (apt-get install postgresql)."}
    if not _free(port):
        raise SystemExit(f"Port {port} is taken: run `down` first, or set another port.")
    data.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        shutil.chown(data.parent, "postgres")
        shutil.chown(data, "postgres")
    secret = data.parent / "pg_password.txt"
    secret.write_text(PG_PASSWORD, encoding="utf-8")
    if os.geteuid() == 0:
        shutil.chown(secret, "postgres")
    _as_postgres(
        [
            str(bin / "initdb"),
            "-D",
            str(data),
            "-U",
            "postgres",
            "--auth-host=scram-sha-256",
            "--auth-local=trust",
            "-E",
            "UTF8",
        ]
    )
    log = data.parent / "postgres.log"
    log.touch()
    if os.geteuid() == 0:
        shutil.chown(log, "postgres")
    options = f"-p {port} -c listen_addresses=127.0.0.1 -k {data}"
    _as_postgres([str(bin / "pg_ctl"), "-D", str(data), "-l", str(log), "-o", options, "-w", "start"])
    sql = [
        f"CREATE ROLE {USER} LOGIN PASSWORD '{PG_PASSWORD}';",
        "CREATE DATABASE shop;",
    ]
    psql = [
        str(bin / "psql"),
        "-h",
        str(data),
        "-p",
        str(port),
        "-U",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-q",
    ]
    _as_postgres([*psql, "-d", "postgres"], input="\n".join(sql))
    load = ["CREATE SCHEMA sales;"]
    for table in ("customers", "products", "orders", "order_lines", "invoices"):
        load.append(create(table, f"sales.{table}"))
        load += inserts(table, company.tables()[table], f"sales.{table}")
    load += [
        f"GRANT USAGE ON SCHEMA sales TO {USER};",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA sales TO {USER};",
    ]
    _as_postgres([*psql, "-d", "shop"], input="\n".join(load))
    return {
        "host": "127.0.0.1",
        "port": port,
        "database": "shop",
        "schema": "sales",
        "user": USER,
        "password": PG_PASSWORD,
        "data": str(data),
        "bin": str(bin),
    }


def stop_postgres(info: dict[str, Any]) -> None:
    if "data" not in info:
        return
    try:
        _as_postgres([str(Path(info["bin"]) / "pg_ctl"), "-D", info["data"], "-m", "fast", "-w", "stop"])
    except subprocess.CalledProcessError as error:
        print(f"PostgreSQL did not stop cleanly: {error.stderr.strip()}")


# ===== MariaDB =====


def start_mariadb(company: Company, data: Path, port: int) -> dict[str, Any]:
    server = shutil.which("mariadbd") or (shutil.which("mariadbd", path="/usr/sbin:/usr/local/sbin"))
    install = shutil.which("mariadb-install-db")
    client = shutil.which("mariadb")
    if not (server and install and client):
        return {"missing": "MariaDB is not installed (apt-get install mariadb-server)."}
    if not _free(port):
        raise SystemExit(f"Port {port} is taken: run `down` first, or set another port.")
    data.mkdir(parents=True, exist_ok=True)
    user = "mysql" if os.geteuid() == 0 else os.environ.get("USER", "")
    if os.geteuid() == 0:
        shutil.chown(data, "mysql")
    subprocess.run(
        [
            install,
            f"--datadir={data}",
            f"--user={user}",
            "--auth-root-authentication-method=normal",
            "--skip-test-db",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    socket_path = data / "mariadb.sock"
    log = data.parent / "mariadb.log"
    process = subprocess.Popen(
        [
            server,
            "--no-defaults",
            f"--datadir={data}",
            f"--port={port}",
            "--bind-address=127.0.0.1",
            f"--socket={socket_path}",
            f"--pid-file={data / 'mariadb.pid'}",
            f"--user={user}",
            f"--log-error={log}",
            "--skip-name-resolve",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    base = [client, "--no-defaults", f"--socket={socket_path}", "-u", "root"]
    for _ in range(150):
        if subprocess.run([*base, "-e", "SELECT 1"], capture_output=True).returncode == 0:
            break
        if process.poll() is not None:
            raise SystemExit(f"MariaDB did not start: see {log}")
        time.sleep(0.2)
    else:
        raise SystemExit(f"MariaDB did not answer: see {log}")
    load = [
        "CREATE DATABASE warehouse;",
        f"CREATE USER '{USER}'@'127.0.0.1' IDENTIFIED BY '{MARIA_PASSWORD}';",
        f"GRANT SELECT ON warehouse.* TO '{USER}'@'127.0.0.1';",
        "USE warehouse;",
    ]
    for table in ("customers", "stock", "order_lines"):
        load.append(create(table, table, "DOUBLE"))
        load += inserts(table, company.tables()[table], table)
    subprocess.run(base, input="\n".join(load), check=True, capture_output=True, text=True)
    return {
        "host": "127.0.0.1",
        "port": port,
        "database": "warehouse",
        "user": USER,
        "password": MARIA_PASSWORD,
        "data": str(data),
        "pid": process.pid,
        "socket": str(socket_path),
    }


def stop_mariadb(info: dict[str, Any]) -> None:
    pid_file = Path(info.get("data", "")) / "mariadb.pid"
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        pid = int(info.get("pid") or 0)
    if not pid:
        return
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        return
    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)


# ===== up, down, status =====


def up() -> dict[str, Any]:
    if read_state() is not None:
        down()
    root = folder()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    company = make_company()
    state: dict[str, Any] = {"folder": str(root), "files": write_files(company, root / "files")}
    write_sqlite(company, root / "finance.sqlite")
    write_duckdb(company, root / "planning.duckdb")
    state["sqlite"] = str(root / "finance.sqlite")
    state["duckdb"] = str(root / "planning.duckdb")
    state_file().write_text(json.dumps(state, indent=1), encoding="utf-8")  # so `down` finds a half start
    state["postgres"] = start_postgres(company, root / "postgres" / "data", PG_PORT)
    state_file().write_text(json.dumps(state, indent=1), encoding="utf-8")
    state["mariadb"] = start_mariadb(company, root / "mariadb" / "data", MARIA_PORT)
    state_file().write_text(json.dumps(state, indent=1), encoding="utf-8")
    return state


def down() -> None:
    state = read_state() or {}
    stop_postgres(state.get("postgres") or {})
    stop_mariadb(state.get("mariadb") or {})
    root = folder()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


def main(argv: list[str]) -> int:
    what = argv[1] if len(argv) > 1 else "status"
    if what == "up":
        state = up()
        for name in ("postgres", "mariadb"):
            if "missing" in state[name]:
                print(f"{name}: {state[name]['missing']}")
            else:
                print(f"{name}: 127.0.0.1:{state[name]['port']}")
        print(f"files: {state['files']['folder']}")
        print(f"state: {state_file()}")
        return 0
    if what == "down":
        down()
        print("The test bed is down.")
        return 0
    if what == "status":
        found = read_state()
        print(json.dumps(found, indent=1) if found else "The test bed is not up.")
        return 0 if found else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
