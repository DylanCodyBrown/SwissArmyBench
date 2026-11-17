# Swiss Army Bench Accounting

An optional extension of Swiss Army Bench whose deliverable is an Excel workbook built by a Python
automation: connection, data (the data notebook), then the workbook.

- **The Accounting project:** `data.ipynb`, `workbook.design.json` (the design: sheets, blocks, bindings; no
  data) and `workbook.py` (the automation Export writes from the design; it runs anywhere with openpyxl and
  duckdb, the app not needed).
- **The Excel canvas:** sheets as tabs; title, text, table, pivot (a summary DuckDB computes, written as a
  formatted table: never a real Excel pivot table) and chart blocks (Excel's own: bar, column, line, pie,
  combo) on a grid of cells; number formats, conditional colours, freeze panes, print setup. Play builds the
  workbook and shows each sheet; Download gives the file.
- **Templates from existing workbooks:** Import keeps the layout, formats, merged cells and named ranges;
  bind a place (a named range, a cell, a table area) to data.
- **Statements and invoices:** one workbook (or sheet) per group, named from columns, numbered, dated; a
  dry run first; a register of what was built.

Install it beside the base: `uv tool install --with swissarmybench-accounting "swissarmybench[server]"`. From a
checkout, `SWISSARMYBENCH_EXTENSIONS=accounting` turns it on with `extensions/accounting/src` on the path.
