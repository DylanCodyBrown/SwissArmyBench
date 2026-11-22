# field_service

A Swiss Army Bench project: open this folder with Swiss Army Bench (Open project), or work on its files
in any editor. It is ordinary files, so it can be a Git repository.

- `data.ipynb` makes the tables; `data.py` is its export (do not edit it by hand).
- `.sab/` is the app's own state: `project.json` (each table's source and steps, the tabs and windows),
  `visualizations.json` and `visualizations/` (the Analyze board and its saved dashboards), `model.json`
  (the relationships).
- `.sab/data/` holds a table's rows only when you ticked Keep its rows; `sandbox/` the sandbox's tables
  (Add to sandbox), for the local sandbox APIs, described by `sandbox_data.py` and stood in for by
  `sandbox_connections.py` (Remove the sandbox deletes those three, and nothing else). Data is sensitive, so
  `.gitignore` and `.sab/.gitignore` keep the rows out of Git; remove those lines to commit data on purpose.
- No password, token or secret is ever written here: a connection is named, and each computer finds its
  password in its own keyring, environment or key vault.
- Export outline (the project's menu) writes `ARCHITECTURE.md`: the project for someone joining it.

<!-- swissarmybench: variables (written by the app: names only, never a value) -->
## Variables

Set each one where the project runs (the terminal, the Function App's or hosted app's settings); no value is ever written in this folder.

| Variable | Where it comes from | What uses it |
|---|---|---|
| `DEPOT_PASSWORD` | This computer's keyring | connection Depot |
<!-- /swissarmybench: variables -->
