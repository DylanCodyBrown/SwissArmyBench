# Extensions as folders (the owner, 2026-11-21)

Status: decided; not built. Build after the adapter (Plans/adapter.plan.md), whose project contract it uses.

> "Extensions should be loadable as a folder in the app so users can create them with their own agents as needed
> and transform the app."

## The owner's answers
- **Where:** the library folder, `library/extensions/<name>/`, shared through the team library and Git like blades
  and connections.
- **Trust:** the library is trusted. A folder extension in it loads without asking, as blades do today. (So a team's
  pull can bring code that runs in the app's server: the same trust a team already gives its shared blades.)
- **Packages:** a missing package is offered through the one missing-package prompt (Install now / Not now),
  installed beside the app with uv like the Extensions page's Install; never by itself.

## The folder

```
library/extensions/databricks/
  contract.json  the project contract as JSON: files, IDE languages, cells, canvas, export, words
                    (today's MODE moves here)
  extension.py      the rest of the manifest as Python values: ID, NAME, DESCRIPTION, AREAS, RAIL, STARTERS,
                    API_TARGETS, SESSION_RULES; routes(services) and commands
  commands.py       its agent commands (the golden rule)
  sources.py        its sources for the adapter (tables, read, write), when it reaches data
  starters/         its blades
  README.md         what it adds, made by New extension
```

The same shape as a packaged extension (extensions/<name>/src/<package>/), so one can move between the two.
Backend and data only, as every extension (the front end draws what its manifest says).

## What the app does
- **Finds** each folder at start beside the installed packages (adapters/extensions.py: entry points, then the
  library's folders); a folder with the same id as a package loses to the package and is said once.
- **Loads** it as a module under its own name (`sab_ext_<id>`), its folder on the import path for its own files only.
  One that fails to load is listed on the Extensions page with its error and the line (never stops the app).
- **Reloads** on its Turn off / Turn on and on a restart; a change to its files is noticed (the file_changed look) and
  offered as Reload.
- **New extension** (the Extensions page and the agent's `extensions_new`) writes the folder above with one command,
  one route and an empty contract.json, so an agent has a working skeleton to grow; the Scripts page shows the library's
  extensions in its explorer like the library's other code.
- **Checks** each one against the shared shapes before it is turned on (its manifest, its contract.json against the shared schema, its sources'
  three calls, no front-end file in it); a failure is its one sentence on its card.

## Tests
A folder extension found, loaded, its command and route answering, its project type scaffolded from its contract.json, its
source read through the adapter; a broken one listed with its error while the app starts; the same id as a package;
the agent's extensions_new; nothing in web/ names it.
