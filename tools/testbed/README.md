# The real-world test bed

Real databases, made-up files and stand-ins for the cloud services, so the owner's real-world use cases
run end to end in a real browser (`tests/e2e/test_real_world.py`). Made-up data only: a small company,
Quillmere Supply (`company.py`), with no real names or addresses.

## Run it

```bash
sudo apt-get install postgresql mariadb-server libmariadb-dev   # once (Ubuntu); test machinery only
uv pip install --python .venv/bin/python "psycopg[binary]" mariadb pymysql nbclient nbformat keyrings.alt
python tools/testbed/testbed.py up       # start and load PostgreSQL and MariaDB, write the files
python -m pytest -q tests/e2e/test_real_world.py
python tools/testbed/testbed.py down     # stop both databases, remove the folder
```

`up` puts everything in one folder (`SAB_TESTBED_DIR`, else `swissarmybench-testbed` in the system's
temporary folder) and writes `testbed.json` there: where each database listens, the made-up passwords,
and each file's path. `status` prints it. PostgreSQL listens on 127.0.0.1:55432 and MariaDB on
127.0.0.1:53306, as their own processes with their own data folders, so a database the machine already
runs is not touched. The drivers and `keyrings.alt` (a keyring for a machine without one) go into the test
environment, never into the app's dependencies.

Without the test bed up (Windows CI, a laptop without the databases), the use cases skip and say why.

## What is in it

| Where | What |
| --- | --- |
| PostgreSQL `shop`, schema `sales` | customers, products, orders (as they land: a status written several ways, test orders, rows sent twice), order_lines, invoices |
| MariaDB `warehouse` | customers, stock, order_lines |
| SQLite `finance.sqlite` | invoices, customers |
| DuckDB `planning.duckdb` | budgets, stock |
| `files/daily_orders/` | the web shop's daily CSV export, one file a day for two weeks |
| `files/catalogue.xlsx` | the buyers' workbook: sheets Products and Categories |
| `files/invoice_template.xlsx` | an invoice template, for one workbook per customer |
| `files/products.parquet`, `files/returns.json`, `files/customers.csv` | the same company in other formats |

The cloud services are stand-ins on 127.0.0.1, started by the tests themselves:

- **Power BI**: `tests/powerbi_standin.py`, with one more dataset, "Company model", read from the same
  rows as PostgreSQL but refreshed a day early (`standins.py`), so a tie-out finds the month that is off.
- **Azure Key Vault**: `standins.py`'s `KeyVault`, the Key Vault REST shape (list the secrets, get one)
  behind a made-up bearer token.
