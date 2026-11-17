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
  tree; `path` reads a file; `path` and `text` save it.
- `powerapps_add_source(table)` adds a Dataverse table; with `connector` and `connection_id`
  (`powerapps_connections`) a connector; `dataset`, `table` or `as` for a tabular one.
  `powerapps_remove_source(name)`.

## Connectors
- `powerapps_connectors(q)`: the environment's connectors; `powerapps_connector(name)`: its operations,
  inputs and outputs (read-only; `operation_id` is the generated service's method).

## Run, push, custom connectors
- `powerapps_run_live`: the dev server, in the Code App page's pane; its `play_url` opens in the user's own
  browser (connectors answer only inside Power Apps). `stop=true` stops it.
- `powerapps_push(dry_run=true)` says what runs; without it, `npm run build` then `pa app push`, after the
  user's Allow. `powerapps_versions`: the environment's code apps and this session's pushes.
- `powerapps_custom_connector(api)`: an API's two connector files (a dry run); `dry_run=false` writes them
  and runs `pac connector create` after the user's Allow. No secret goes in them.
- `powerapps_runs(run?)`: each run's words, exit code and output. Never a token or a password in them.
