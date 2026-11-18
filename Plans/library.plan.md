# The library: connections, APIs, vaults, blades and variables, outside any project

The owner, 2026-11-17:
- "Apis, Connections they live OUTSIDE of the project, I dont wanna have to go hunt an api every project."
- "so they become a library of connections" / "and apis"
- "that library is the thing I wanted to push to a github repo so it can be shared as a code base with fellow users later"
- Blades go in the library too (the owner's answer, 2026-11-17).

This replaces "everything is the project's own" (2026-11-16) for connections, APIs, vaults, blades and
variables. Projects keep their documents (notebooks, scripts, apps, Structures files), tables, grids,
Visualizations and model. A project refers to library items by name only.

## The library is a folder of text files, made to be a Git repository

Default `~/.swissarmybench/library/`; Settings can point it at any folder (a clone of a team's repository).
Every file is readable, diffs well and holds **no secret, no token, no row of data**:

```
library/
  README.md                 what this library is, made on first use (editable)
  .gitignore                this computer's files (below), made on first use
  connections/<name>.blade.py   each connection (database, file, Power BI, Dataverse, Python, vault):
                            the portable blade file (TOML header + code). Passwords name their source
                            (keyring, environment variable, vault entry), never a value.
  apis/<name>/API_<name>.py     an API's client, and its description:
  apis/<name>/openapi.json      (or .yaml) as imported; the source address in the blade's header
  blades/<name>.blade.py    functions, analyses, snippets
  tangs/<name>.tang         saved relationship sets
  variables.toml            each variable's NAME and SOURCE (vault entry, keyring, environment, a plain
                            non-secret value such as a region); never a secret's value
  colours.toml              each connection's colour
  local/                    THIS COMPUTER ONLY, git-ignored: paths that differ per computer (a keystore's
                            location, a certificate file), plain values the user marked local, which
                            library items are switched off here
```

Rules:
1. The app writes one file per item, sorted keys, stable formatting, so a save that changes nothing
   changes no file and a Git diff shows only what the user changed.
2. A secret never enters the folder. The keyring holds this computer's secrets, under the item's name.
   A person who clones the library is asked for each missing secret the first time a connection runs
   (the existing "passwords with no source on this computer" fix).
3. Per-computer values go in `local/` and are read over the shared file's defaults
   (certificate_files.py's `os.environ.get("NAME", r"<path>")` pattern stays for code that must also run
   in a function app).
4. The app itself never runs git or pushes anything (the one-request rule). The folder is a plain Git
   working copy the user commits and pushes with their own tools. Later, optionally, a "Share" page could
   call the user's own git; that is a separate decision.
5. Several libraries may be read at once later (your own plus a team's, read-only), as blade folders and
   packs already are: one writable library, the rest read-only. Same names: the writable one wins, and
   the clash is shown.

## Migration
- The current stores (`~/.swissarmybench/blades/*.json`) are rewritten once as library files.
- A project with its own `.sab/blades` is opened: its items are copied into the library (a name already
  there and identical: skipped; different: kept as `<name> (from <project>)` and said). The project then
  refers to them by name. The .sab stops carrying blades on its next save; an older app still opens it.
- Packs (Claude Code plugins with blades/ and tangs/) keep working: a library folder has the same layout,
  so a library can be turned into a pack.

## Order
1. Merge `variables-page`, `connection-colours`, `trees-apis` (Structures and APIs).
2. Then one change: the library folder, the file layout above, migration, Settings' Library folder,
   the Connections, APIs, Blades and Variables pages reading it, agent parity, tests (a library cloned to a
   second folder opens with the same items and asks only for secrets).

## Shared catalog (the owner, 2026-11-17/18; built, branch shared-catalog)

"A shared meta store on GitHub ... any connection made in a project would save to a centralized catalog it would
sync and prune in realtime" / "you point the app to a GitHub meta store folder on your machine. You push and pull
as projects are created". The library is that meta store (Settings: **Meta store folder**), and its new folder:

```
library/
  catalog/<connection>.json  each connection's tables: database, schema, name, columns (name, type, nullable,
                             key), primary key, relationships, used_by (project folder names), state (present
                             or gone since a date). Names and types only: no value, count or secret
```

- Written when a connection is saved, its tables listed, relationships change, a project opens or saves; a deleted
  connection's file goes; a table no successful listing finds is gone, then removed after 30 days; a failed
  listing changes nothing. Sorted, one table per block, the same catalog the same bytes.
- Read again when the user's pull changes the folder (looked at every few seconds), said once in the page. A file
  with merge markers is reported and left alone until it reads.
- **Set up from the meta store**: a new person's checklist (key vaults' sign-ins, values to type once, each
  connection's status, shared projects not set up here; Move to a vault for a keyring password), so "minimal
  setup is required for new people" (2026-11-18).
- **Local and shared projects**: Settings' Local and Shared projects folders; a shared project lives in a folder
  the user pushes and pulls like the meta store; Share and Make a local copy move a project between them.
- The app still never runs git (rule 4); docs/ideas.md "The meta store" has the details and decisions.
