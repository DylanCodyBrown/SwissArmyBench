# forms_recon

A Swiss Army Bench project: open this folder with Swiss Army Bench (Open project), or work on its files
in any editor. It is ordinary files, so it can be a Git repository.

- `data.ipynb` makes the tables; `data.py` is its export (do not edit it by hand).
- `.sab/` is the app's own state: `project.json` (each table's source and steps, the tabs and windows),
  `visualizations.json` and `visualizations/` (Visualizations and its saved dashboards), `model.json`
  (the relationships).
- `.sab/data/` holds a table's rows only when you ticked Keep its rows; `.sab/sandbox/` the sandbox's tables
  (Add to sandbox), for the local sandbox APIs. Data is sensitive, so
  `.gitignore` and `.sab/.gitignore` keep it out of Git; remove those lines to commit data on purpose.
- No password, token or secret is ever written here: a connection is named, and each computer finds its
  password in its own keyring, environment or key vault.
- Export outline (the project's menu) writes `ARCHITECTURE.md`: the project for someone joining it.
