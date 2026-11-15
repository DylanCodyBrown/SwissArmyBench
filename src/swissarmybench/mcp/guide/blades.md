# Blades and starters

A blade is the user's saved Python that reaches outside Python: a database connection, a file, an
API, a vault, or an analysis. In any Python, `conn = sab.blade("Warehouse")` runs it there. The blades
page is Blades and catalog in the Application row.

## Using and making blades
- `blades_list` (never a secret's value) and `blades_get`: reuse one before making another.
- `blades_templates`: starters for databases, files, vaults and analyses; `id=` gives one's code.
- `blades_inspect`: what code makes, asks for (secrets), imports and needs; its settings (server,
  database, path). `blades_fill` writes values at those settings. Nothing runs.
- `blades_create` (kind sql, other, vault, secret or analysis) and `blades_update`, saved as the user
  saves them. Write `secret("password")` where a password goes, and give a description and tags.
  Then tell the user which secrets to type (or `blades_secrets` saves values they give you).
- `blades_test` runs one in a child process; `blades_refresh` loads its catalog; `blades_install`
  installs its packages into the app's Python.
- `blades_pin`, `blades_delete`, `blades_folders` (folders searched for `.blade.py` files),
  `blades_export` (portable text, no secrets), `blades_import` (without apply: a review; nothing runs).
- Analysis blades: `def analyze(df, columns): ...` returning markdown, a DataFrame or a figure; they
  show in the Analyze menu. `blades_analyses` lists them, `blades_run_analysis` runs one on a grid.

## Starters (read-only, shipped with the app)
- `blades_starters`: the pack by family: Power BI (refresh a dataset, its status, parameters...), Excel
  (sheets, formats, tables), Files (combine or split CSVs), DAX, HTML and Streamlit snippets, and Components (your own HTML and JavaScript as Streamlit pieces, one way or two way).
- A Python starter makes one function: run it in a kernel,
  `refresh = sab.blade("Power BI refresh dataset")`, then `refresh("Finance/Sales model")`.
- `blades_copy` makes one the user's own to change.
- A snippet goes into a cell of its language: `blades_snippet` gives its blanks and their choices (or,
  with values, its text); `workbench_snippet_insert` puts it in the front document. A Streamlit piece
  becomes a named Python cell, ready for a canvas.

## Packs (blades and tangs from a Claude Code marketplace)
- `packs_list`: installed packs (read-only; Save a copy to change one) and editable clones.
- `packs_new` makes a marketplace folder; `packs_add` copies saved blades and tangs into an editable pack.
