# One way to make Excel (the owner, 2026-11-21)

Status: decided; build after the adapter's first phase merges (it reads and writes through the adapter).

## The owner's answers
- **Shape: one module, `sab_excel`, behind the adapter.** Two halves: `read(workbook, sheet, header_row, range)` gives
  Arrow (one set of type rules, replacing the three readers today: the datasets loader, sab.sql over sheets, the upload
  widget); `build(tables, design, template)` gives a workbook. The design is today's Accounting runtime design as plain
  data (title, text, table, pivot by DuckDB, Excel's own charts, formats, conditional colours, print setup, a template
  whose tables grow, one workbook per group with numbering and a register).
- **One library: openpyxl only.** xlsxwriter goes (from the grid's export and the app's dependencies). Accepted: large
  plain exports (near a million rows) become noticeably slower; record the time before and after in docs/verified.md.
  The export's formula-injection safety and exact long numbers and early dates are kept, rewritten on openpyxl.
- **The twelve cell-level starters are removed.** Their effects become design options; the old names answer for one
  release. Starters 14 become 3: Read a workbook, Make a workbook, Fill a template, each a few lines calling the module.
- **Any project type may deliver a workbook beside its own deliverable** (the forms and reconciliation app emitting a
  monthly workbook): a workbook is a file any contract.json may declare.

## What each way becomes
- The Accounting Excel canvas stays, as the drawn editor of the design (Accounting only); its runtime.py moves into
  `sab_excel`; workbook.py in an export carries only the builder parts it uses.
- The Streamlit Excel widgets stay as thin callers (upload's reader and download's writer are the module's).
- The grid's Excel export calls `build` with no design.
- Excel is a source for the adapter: tables (sheets and named tables), read (Arrow batches), write (a sheet inserted
  or replaced, the other sheets kept, by safe file replacement). An uploaded file becomes a grid like any table.

## The export of a project that makes a workbook
sab_adapter.py, connections.py (used ones only), data.py, workbook.py, templates/<name>.xlsx (only if bound),
requirements.txt, README.md; API.py only with endpoints.

Design survey (the Fable agent, 2026-11-21): five writers and three readers today; about 1,100 lines move and 1,500
go; no new page.
