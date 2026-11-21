# Blades and starters

A blade is the user's saved Python that reaches outside Python: a database connection, a file, an
API, a vault, or an analysis. In any Python, `conn = sab.blade("Warehouse")` runs it there. The blades
page is Blades on the rail. A blade's screen is an IDE (the owner, 2026-11-21: "This is an IDE not a save
form"): the code editable with the Workbench's intelligence, Run with its output, result and problems below,
Properties (name, description, tags, table name) at the right. The code's bytes are its file's (a
`.blade.py` in the library or a blade folder): Save writes the file, only when it changes.

## Using and making blades
- `blades_list` (never a secret's value) and `blades_get`: reuse one before making another.
- `blades_templates`: starters for connections (databases, files, vaults) and analyses; `id=` gives one's code.
- `blades_inspect`: what code makes, asks for (secrets), imports and needs; its settings (server,
  database, path). `blades_fill` gives the code with values at those settings (a connection's form
  uses it); nothing is saved or run.
- `blades_new` (no template: the choices; `table`, `code`, `secret`, `snippet`, an analysis): a new
  `.blade.py` in the library's blades/ folder. Connections are made with `connections_create`.
- `blades_update(code=, stamp=)`: its code, written into its file after the header (its variable follows a
  renamed function); `stamp` (from `blades_get`) refuses the save with 409 when the file changed on disk
  since. Name, description, tags and table name are the header's. A starter's or a pack's is refused:
  `blades_copy(name, new_name, code=)` (Save as, Copy as your own). An edit made in the user's own editor
  shows at once; an open IDE with unsaved changes asks Reload or Keep mine.
- `blades_run(name, code=)`: the IDE's Run (a child process, as Test): `output` (stdout and stderr),
  `result` (a table's columns, first rows and `total`, or a value's `text`), on a failure `error` and
  `error_detail` (the error panel's: frames, line), and `problems`. `open=true` opens a table result as a
  grid; `cancel=<run id>` stops a run. `blades_problems(name, code=)`: the lint alone.
- A table blade (a function or code that makes a DataFrame) has a table name of its own (`table` in its
  header; none: the name its code makes). `blades_table_name_check(name, blade)` says `available` or why
  not (already a table, a connection, another blade's table, not a valid name); `blades_update(table=)`
  refuses a taken one. `sab.blade(...)` in a kernel makes its result (a function's, each call) the
  variable of that name: DuckDB SQL, the Variables panel and the Open list name it so; the Data Explorer
  inserts it under that name.
- A connection's tables are always listed: its listing query (`blades_get`'s `catalog`, read-only) is its
  starter's when it had none.
- `blades_test` runs one in a child process; `blades_refresh` loads its catalog; `blades_install`
  installs its packages into the app's Python.
- `blades_pin`, `blades_delete`, `blades_folders` (folders searched for `.blade.py` files),
  `blades_export` (portable text, no secrets), `blades_import` (without apply: a review; nothing runs).
- Analysis blades: `def analyze(df, columns): ...` returning markdown, a DataFrame or a figure; they
  show on the Analyze toolbar (Yours). `blades_analyses` lists them, `blades_run_analysis` runs one on a grid.

## Starters (read-only, shipped with the app)
- `blades_starters`: the pack by family: Power BI (refresh a dataset, its status, parameters...), Excel
  (sheets, formats, tables), Files (combine or split CSVs), DAX, HTML, Markdown and Streamlit snippets, Components (your own HTML and JavaScript as Streamlit pieces, one way or two way), and Write (a Python cell that writes to a connection: dry run first; `guide(topic="writing")`).
- A Python starter makes one function: run it in a kernel,
  `refresh = sab.blade("Power BI refresh dataset")`, then `refresh("Finance/Sales model")`.
- `blades_copy` makes one the user's own to change.
- A snippet goes into a cell of its language: `blades_snippet` gives its blanks and their choices (or,
  with values, its text); `workbench_snippet_insert` puts it in the front document. A Streamlit piece
  becomes a named Python cell, ready for a canvas.

## Packs (blades and relationship sets from a Claude Code marketplace)
- `packs_list`: installed packs (read-only; Save a copy to change one) and editable clones.
- `packs_new` makes a marketplace folder; `packs_add` copies saved blades and relationship sets into an editable pack.
