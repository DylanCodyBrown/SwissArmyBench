# The real-world test bed

Real databases, made-up files and stand-ins for the cloud services, so the owner's real-world use cases
run end to end (`tests/e2e/test_real_world.py`: by the agent's commands, then run as they run outside the app). Made-up data only: a small company,
Quillmere Supply (`company.py`), with no real names or addresses.

## Run it

```bash
sudo apt-get install postgresql mariadb-server libmariadb-dev   # once (Ubuntu); test machinery only
uv pip install --python .venv/bin/python "psycopg[binary]" mariadb pymysql nbclient nbformat keyrings.alt openpyxl
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

Use case 11 (a widget on a canvas, played and exported) needs a Python with Streamlit and ipykernel:
`SWISSARMYBENCH_STREAMLIT_PYTHON=<that python>`; without one it skips. The headless runs (2, 3, 5, 11)
build the client wheel and a plain Python with `uv` (pandas, psycopg, nbconvert, Streamlit: from PyPI).
`SWISSARMYBENCH_SHOTS=<folder>` keeps a screenshot of each use case (and use case 9's PDF);
`SAB_TESTBED_COUNTS=<file>` writes the action counts as JSON.

## The use cases

| | What the user does | Actions |
| --- | --- | --- |
| 1 | orders from PostgreSQL cleaned in the grid (trim, lower case, no test orders, each once), the notebook saved | 35 |
| 2 | that notebook run headless by `jupyter nbconvert`, the app closed, the password the keyring's | 1 |
| 3 | the same as an Azure Function would: the connection's exported file, SHOP_PASSWORD | 5 |
| 4 | Excel statements, one workbook per customer with open invoices, from the template, with the Excel starters | 24 |
| 5 | a daily CSV export, saved, then run as the scheduled task runs it | 12 |
| 6 | the daily CSV folder (Files combine CSVs), both workbook sheets and MariaDB's customers; the joins found | 35 |
| 7 | the Power BI workspace added (its app registration from the vault); a dataset's relationships and 5 tables read in | 26 |
| 8 | Power BI's Invoices tied out against PostgreSQL's on the Analyze page: the regions of the day the refresh missed are off | 10 |
| 9 | a forecast of invoiced amounts by month on the Analyze page (November's one day left out, said), Page view, Print to PDF | 11 |
| 10 | a story notebook: figures, a Markdown cell with live values, a table and a Mermaid diagram, an HTML cell | 20 |
| 11 | a widget written in the Widgets window (its table PostgreSQL's invoices, open in the grid) and previewed, placed on a Streamlit project's canvas (Desktop and Phone), played, exported; the export run by AppTest in a plain Python | 33 |

The table is the use cases as they were clicked through the classic pages, their actions counted under a
ceiling; those runs went with the classic pages (2026-11-23). Today use cases 1, 4 and 11 run through the
agent's MCP commands only (`test_1a`, `test_4a`, `test_11a`), and 2 and 3 run the notebook 1a saved: headless on
this computer, and as an Azure Function would (the connection's file from `GET /blades/{name}/export`).

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

## A large made-up business: Larkfield Goods

`large_company.py` makes a retail and wholesale business of 14 tables (regions, stores, categories, suppliers,
products, customers, employees, orders, order_lines, returns, inventory_snapshots, shipments, support_tickets and
data_quality_issues, which lists its deliberate problems) with DuckDB SQL alone, the same rows for the same seed:

```bash
python -m tools.testbed.large_company --scale small  --out /tmp/larkfield   # about 10k order lines, under a second
python -m tools.testbed.large_company --scale medium --out /tmp/larkfield   # about 1M, a few seconds
python -m tools.testbed.large_company --scale large  --out /tmp/larkfield --duckdb   # about 10M, about 30 s
```

From Python: `build(out, scale, seed, duckdb_file)` writes the Parquet files and returns the row counts and the
time; `generate(connection, scale, seed)` makes the tables in a DuckDB connection of your own. It refuses a folder
inside the repository. Tests: `tests/test_large_company.py` (medium with `SWISSARMYBENCH_TEST_MEDIUM=1`, large's
timing with `SWISSARMYBENCH_TEST_SLOW=1`).
