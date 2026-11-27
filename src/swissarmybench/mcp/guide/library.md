# The library and the team

Connections, APIs, key vaults, blades, relationship sets, variables and connection colours are this computer's library,
shared by every project (a project names them; it never holds them). The library is one folder of text
files made to be a Git repository: `~/.swissarmybench/library` unless the computer is in a team (below), or
Settings' Team box, Advanced, points it at another folder.

## A team (Settings' Team box)
A team is ONE GitHub repository: the team library at its top, the team's shared projects in its `projects/`.
The screen calls it the Team library. GitHub sync is built in (nothing to install first). Signing in to GitHub is
the user's own.
- `team_status(remote?, repositories?, search?, owners?)`: `state` none or joined; joined: `team.repository`,
  `team.folder` (the local copy), `team.projects`, `team.sync` (only when something is to do: Pull, changes to
  push, conflicts); `signed_in`, `pending` (a Join or Start step kept over Install's restart).
- `team_join(repository)`: the local copy made in `~/.swissarmybench/team/<owner>-<repo>/` (no path asked),
  the library pointed at it and the shared projects folder at its `projects/`, then the Set up checklist
  (`setup`). Allow.
- `team_start(name, owner?, private?)`: a new private repository with README.md, .gitignore (local/,
  .sab/data/) and projects/; this computer's library copied in and pushed; then joined. Allow.
- `team_leave(keep)`: without keep, the question; then the library and the shared projects folder go back to
  what they were before joining (keep: the team's items this library lacks copied in first; one it has, kept).
  The local copy stays on disk. Allow.
- Pull and Push: `github_pull`, `github_push` (which library). A shared project's card pushes only its own
  files (`github_push(which="shared", path=...)`).

```
connections/<name>.blade.py   vaults/<name>.blade.py   blades/<name>.blade.py
apis/<name>/                  relationship-sets/<name>.relationships.json
variables.toml                colours.toml
catalog/<connection>.json     the shared catalog: each connection's tables (below)
local/                        this computer only (git-ignored): plain values marked local
```

- `library_info`: the folder, what is in it (counts), whether it is a Git working copy, what stays on this
  computer, what never goes in, and any notice the page is showing (the move into the library).
- `library_set_folder(folder)`: point it at another folder, or back at the default (no folder). Every
  connection, API, vault, blade and variable then comes from there, so it waits for the user's Allow.
- The usual commands act on it: `connections_create`, `blades_new`, `blades_update`, `variables_set`,
  `connections_api_add`, `apis_save_call`,
  `relationships_save_set`, `connections_colours`. Each save writes one file; a save that changes nothing
  changes no byte.
- Never in it: a password or secret's value, a token, a row of data. Secrets stay in each computer's keyring
  (`connections_password_source`). On another computer a cloned library's connections say which passwords
  they need (`connections_list`: `needs_password`), and local values are missing until set there.
- The app never runs git: GitHub sync (a team) or the user's own tools move the folder.

## The shared catalog (catalog/)
One file per connection: each table's database, schema and name, its columns (name, type, nullable, key),
primary key, the relationships whose ends are its tables, `used_by` (the project folders' names using it) and
`state` (present, or gone with `gone_since`). Names and types only: never a row count, a value or a secret.
- Written by the events, for you as for the user: a connection saved, its tables listed (Refresh, a catalog
  loading itself, the Connections page's tree), relationships imported or changed, a project opened or saved.
  A deleted connection's file goes; a table a successful listing no longer finds is gone, removed after 30
  days; a failed listing changes nothing.
- `catalog_shared(search?)`: every connection's tables, state and used_by, and `here` (whether this
  computer has the connection: a teammate's catalog arrives before their connection is set up).
  `catalog_shared_table(connection, table)`: one table's columns, keys, relationships.
- `catalog_shared_refresh`: read the folder again now (what the user's `git pull` brought; it is also looked
  at every few seconds). A file with merge conflict markers is listed in `problems` and left alone until the
  user fixes it. `explorer_search` and `explorer_browse` (section "From the shared catalog"), the ERD's All
  tables (`erd_text(scope="all")`) and `app_context` read it too.

## Set up this computer
`library_setup(check?)`: a new person's checklist against a team library: `count` and `words` ("3 things
to set up", "Ready: 9 connections work"); `vaults` (readable here or not, the sign-in that fixes it, how many
variables it gives); `values` (a keyring or local variable with no value here, a connection's password with
no source here: the user types each once, never you); `connections` (works, needs <thing>, or only works on
your machine, with the portability rule's words); `projects` (shared projects whose connections are not set
up here). A connection whose password is in this computer's keyring offers `move_to_vault`:
`library_setup_move_to_vault(connection, secret, vault, vault_secret)` maps it to a vault's secret, so the
next person needs nothing.

- An older project with its own connections and blades (.sab/blades): opening it copies them into the
  library (the same one skipped; a different one of the same name kept as `<name> from <project>`), and
  its next save leaves them out. `project_import` of connections or blades from another project does the same.
