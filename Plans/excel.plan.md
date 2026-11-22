# One way to make Excel (the owner, 2026-11-21)

Status: built (2026-11-22, branch excel): adapter.py 1.4.0's Excel source, `src/swissarmybench/sab_excel.py`,
openpyxl only, three starters, the widgets as thin callers, a workbook in any contract.json. What was decided
while building is in docs/ideas.md ("The one Excel module, as built"); the numbers in docs/verified.md.

## The owner's answers
- **Reading and writing a workbook's rows is the adapter's, like every connection** (the owner: "All connection
  transformations are in the adapter"). An Excel workbook (a path, an upload's bytes, a SharePoint document) is one
  more source in `adapter.py`: `tables` lists its sheets and named tables, `read` gives Arrow batches (one set of
  type rules, replacing the three readers today: the datasets loader, sab.sql over sheets, the upload widget),
  `write` puts rows into a sheet (inserted or replaced, the other sheets kept, by safe file replacement). Nothing
  else in the app reads or writes a sheet's rows.
- **The workbook as a deliverable is the one separate piece: `sab_excel.build(grids, design, template)`.** It takes
  grids (Arrow, from the adapter) and lays them out: the design is today's Accounting runtime design as plain data
  (title, text, table, pivot by DuckDB, Excel's own charts, formats, conditional colours, print setup, a template
  whose tables grow, one workbook per group with numbering and a register). It never reads a connection.
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
- An uploaded file becomes a grid like any table (read through the adapter).

## The export of a project that makes a workbook
adapter.py, connections.py (used ones only), data.py, workbook.py, templates/<name>.xlsx (only if bound),
requirements.txt, README.md; API.py only with endpoints.

Design survey (the Fable agent, 2026-11-21): five writers and three readers today; about 1,100 lines move and 1,500
go; no new page.
