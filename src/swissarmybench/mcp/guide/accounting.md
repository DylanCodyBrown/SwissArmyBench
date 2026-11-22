# Accounting: an Excel workbook from a Python automation

An optional extension (`swissarmybench-accounting`). Its tools are there only when it is on:
`app_mode(all=true)` lists the project types this app can make. The workflow: connection -> data (the
data notebook) -> the workbook automation.

## The Accounting project
- `project_new(folder, name, type="accounting")`: data.ipynb, `workbook.design.json` (the design: sheets,
  blocks, bindings; never data) and `workbook.py` (the automation). No Streamlit app.
- While it is open, `app_mode` says its mode: the Excel canvas, the Excel, Write and Files families first,
  and these tools first in your list.

## The Excel canvas: a design
- `workbook_open(path)` (or a title for a new one) gives its id; `workbook_design(workbook)` reads it.
- `workbook_block(workbook, action="add", sheet, fields)`: a block at a cell. Kinds: `title`, `text`,
  `table` (`source`: `{"table": "cessions"}` or `{"query": "SELECT ..."}`; `columns` with `format`
  currency, percent, date... or an Excel code, `width`, `total` sum; `total_row`; `conditional`), `pivot`
  (`rows`, `columns`, `values` with `agg` sum, count, average, min, max; DuckDB computes it, the workbook
  gets a formatted summary table, never a real pivot table), `chart` (`chart` bar, column, line, pie,
  combo; `from`: a table's or pivot's block; `category`, `series`, `line_series`).
- `action="change"` moves (`cell`, `sheet`) and sizes (`w`, `h`); `workbook_sheet` adds, renames, sets
  `freeze` and `print` (orientation, paper, fit_width, header, footer). `workbook_set_design` writes it whole.
- `workbook_play`: the workbook built from the open tables (each with its grid's steps), each sheet's
  cells as built. A table it reads must be open (a grid); `missing` names any that is not.
- `workbook_save`, then `workbook_export`: workbook.py beside the design builds the same workbook from
  data.py anywhere (`python workbook.py`; openpyxl and duckdb). The builder is the base's `sab_excel`
  (`sab_excel.build(grids, design, template)`, the one way to make a workbook: the canvas is the drawn
  editor of its design); workbook.py carries only the parts of it its design uses.

## Templates, statements and invoices
- `template_import(source)`: an existing workbook becomes `templates/<name>.xlsx` (layout, formats,
  merged cells, named ranges kept). `template_show(name)`: its cells, named ranges and bindings.
- `template_bind(name, binding)`: a place (a named range, `B3`, `Sheet!B3`) gets a value
  (`{"column": ...}`, `{"text": "To {cedant}"}`, `{"number": true}`, `{"date": true}`) or a table of
  lines (`columns`, `rows`: its area in the template; it grows, the totals under it follow).
- `statements_build(template, data, lines, group_by, name, number, date)`: a dry run (the files, rows,
  totals; nothing written). Build for real (`dry_run=false`) only after that dry run and only when the
  user said so in their own words; it waits for their Allow too. `statements_register` lists what was
  built (`open=true`: as a grid).
