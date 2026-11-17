# Power Apps (an extension)

When the Power Apps extension is installed (`app_mode(all=true)` lists the `codeapp` type), its `powerapps_`
tools build Power Apps code apps (React and TypeScript apps that run in Power Platform). Microsoft's own
command lines do the work: the Power Apps CLI (`pa`) for the app, the Power Platform CLI (`pac`) for the
environments list and custom connectors. Every run is on the Code App page's Runs and the Session page.

## Before anything
- `powerapps_state`: the tools (Node.js 22 or later, npm, `pa`, `pac`), who is signed in, the open code app.
- A missing tool answers with `missing` (its install command); `powerapps_tools(install=...)` installs it
  and waits for the user's Allow. A `sudo` command is the user's to run.
- `powerapps_auth`: who `pa` is signed in as; `sign_in=true` opens the browser. `powerapps_environments`
  (`pac env list`); `powerapps_profiles` (pac's sign-ins: `create`, `select`).

## The code app
- `powerapps_new(name, environment_id, parent)`: Microsoft's Vite template, `npm install`, `pa app init`;
  then it is the open project and the mode is the code app's (TypeScript, React blades, Push).
  `powerapps_open(folder)` opens one (`close=true` closes it).
- `powerapps_project`: its data sources and the generated models and services. `powerapps_files`: the
  files a person edits (`src/App.tsx`, `src/pages.ts`, `src/pages/**`, `src/shared/**`; `all=true` lists the
  rest, which stays in the folder); `path` reads any file; `path` and `text` save it. Survey the generated
  code by path when you need it; do not list or change configs, `power.config.json` or `src/generated/`.

## Pages (each page owns everything it needs)
- `src/pages/<Page>/`: `<Page>Page.tsx` (its state in useReducer, handed down), `components/`, `hooks/`
  (`use<Page>`: loading, error, refresh over the generated service), `state.ts`, `types.ts`, `index.ts`.
  `src/pages.ts` lists them. A page never imports another page: shared pieces go in `src/shared/`.
- `powerapps_pages`: the pages; `name` (and `source`, a data source) makes a New page and lists it.
  `powerapps_scaffold`: the starter files where none is. `powerapps_lint`: imports across pages.
- `powerapps_add_source(table)` adds a Dataverse table; with `connector` and `connection_id`
  (`powerapps_connections`) a connector; `dataset`, `table` or `as` for a tabular one.
  `powerapps_remove_source(name)`.

## Connectors
- `powerapps_connectors(q)`: the environment's connectors; `powerapps_connector(name)`: its operations,
  inputs and outputs (read-only; `operation_id` is the generated service's method).

## The data notebook (TypeScript and SQL on one DuckDB)
- `powerapps_notebook(open=true)`: the code app's `data.ipynb` (made the first time); `interrupt`, `restart`,
  `stop` its kernel. Deno runs it (missing: the `missing` answer; `powerapps_tools(install="deno")`).
- `powerapps_ts_run(code, kind="typescript"|"sql")`: one kernel, one DuckDB. The open tables are views by
  name; ``await sab.sql`SELECT ... ${value}` `` binds values; `sab.table("name", rows)`; a query naming
  `[Connection].table` reads it first. A table output: columns, types, first rows, `total`, `id`.
- `powerapps_ts_grid(id, name)`: that result, every row, as a grid.
- `powerapps_data_ts`: data.ts from the saved notebook (its TypeScript exported, typed results, SOURCES,
  small results as constants; never DuckDB: code apps' security policy forbids it);
  `use_in_app=true` writes `src/shared/data.ts`.
- `powerapps_tsx_preview(source)`: a TSX cell (its `export default`, `// props: {...}` on line 1) as one page
  for the HTML cells' frame, with the app's own React (`npm install` first).
- `powerapps_dataverse_grid(source)`: a Dataverse source as a grid through the library's Dataverse
  connection for the app's environment; with none, `needs` says which to add.

## Run, push, custom connectors
- `powerapps_run_live`: the dev server, in the Code App page's pane; its `play_url` opens in the user's own
  browser (connectors answer only inside Power Apps). `stop=true` stops it.
- `powerapps_push(dry_run=true)` says what runs; without it, `npm run build` then `pa app push`, after the
  user's Allow. `powerapps_versions`: the environment's code apps and this session's pushes.
- `powerapps_custom_connector(api)`: an API's two connector files (a dry run); `dry_run=false` writes them
  and runs `pac connector create` after the user's Allow. No secret goes in them.
- `powerapps_runs(run?)`: each run's words, exit code and output. Never a token or a password in them.
