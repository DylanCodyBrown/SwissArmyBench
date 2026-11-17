# The library

Connections, APIs, key vaults, blades, tangs, variables and connection colours are this computer's library,
shared by every project (a project names them; it never holds them). The library is one folder of text
files made to be a Git repository: `~/.swissarmybench/library` unless the user pointed Settings' Library
folder at another (a clone of a team's library).

```
connections/<name>.blade.py   vaults/<name>.blade.py   blades/<name>.blade.py
apis/<name>/                  tangs/<name>.tang        variables.toml   colours.toml
local/                        this computer only (git-ignored): plain values marked local
```

- `library_info`: the folder, what is in it (counts), whether it is a Git working copy, what stays on this
  computer, what never goes in, and any notice the page is showing (the move into the library).
- `library_set_folder(folder)`: point it at another folder, or back at the default (no folder). Every
  connection, API, vault, blade and variable then comes from there, so it waits for the user's Allow.
- The usual commands act on it: `connections_create`, `blades_new`, `blades_update`, `variables_set`,
  `connections_api_add`, `apis_save_call`,
  `relationships_save_tang`, `connections_colours`. Each save writes one file; a save that changes nothing
  changes no byte.
- Never in it: a password or secret's value, a token, a row of data. Secrets stay in each computer's keyring
  (`connections_password_source`). On another computer a cloned library's connections say which passwords
  they need (`connections_list`: `needs_password`), and local values are missing until set there.
- The app never runs git: the user commits and pushes the folder with their own tools.
- An older project with its own connections and blades (.sab/blades): opening it copies them into the
  library (the same one skipped; a different one of the same name kept as `<name> from <project>`), and
  its next save leaves them out. `project_import` of connections or blades from another project does the same.
