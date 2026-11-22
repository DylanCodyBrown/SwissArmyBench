# bi_review: test app one

A made-up company's monthly sales review (Larkfield Goods, `tools/testbed/large_company.py`, small scale),
built as a BI project the way a user's agent builds it: every step is one of the agent's commands (the MCP
tools) against a running Swiss Army Bench. It exercises the base app end to end: a project, five kinds of
connection (a folder of Parquet files whose path is the `${LARKFIELD_DIR}` variable, a DuckDB file, a SQLite
archive, a CSV file and a Python connection), DuckDB SQL naming `[Connection].table`, every kind of grid step,
profile, compare and tie-out, the Key Finder, relationships and the ERD, exports, every Analyze contract,
data.ipynb with SQL, Python and HTML cells, a script in the same Python session, data.py and the one-file
automation, Structures, an Excel deliverable through sab_excel, the outline, the change log and statistics.

- `build.py`: the builder, `build(run, allow, data, folder)`; read its docstring for the order of the parts.
- `scripts/`: the project's two scripts (saved into the project by `workbench_save`): the month's headline
  from the warehouse, and the review workbook (`workbooks/monthly_review.xlsx`).
- `inputs/`: the structures it opens (a JSON plan, TOML thresholds, the same as YAML when PyYAML is here).

Built and checked by `tests/test_bi_review_app.py` (no browser) and played through the pages by
`tests/e2e/test_bi_review_app.py`. Nothing here is real data; no row is kept in this folder.
