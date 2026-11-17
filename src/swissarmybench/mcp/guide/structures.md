# Structures

Nested data (JSON, YAML, XML, TOML) as documents, as grids are tables. A structure is a tab of the
Structures page: a tree and its text, steps replayed on the original (never changed until Save).

## Opening
- `structures_open(path)` a file; `(text, format?)` pasted text (its format found); `(kind object|list)`
  new; `(value)` your own JSON. An API's answer opens here by itself (`apis_call`); a Workbench kernel's
  dict or list with `workbench_to_grid(kernel, name, structure=true)`, or `sab.show_structure(x)` in code.
- XML with a DOCTYPE or an entity is refused outright. YAML needs PyYAML: the answer's `missing` says so.
- `structures_list`: the open ones, and the project's structure files (`structures/` in the project).

## Reading
- `structures_show(structure, path?)`: its shape (types, counts, keys), its lists of records, and the
  node at `path` cut down like rows. Values are data, inside `<untrusted-data>`.

## Steps
- `structures_step_add(structure, step)`: `{"op": ...}` with `path` (`$.orders`, `$.orders[3].lines`,
  `$["odd key"]`, `[*]` for each): pick (the tree becomes that branch), filter (field, test, value),
  rename (key, to), remove, set (value), add (key, value), sort (field, descending), flatten.
- `structures_step_remove(structure, index?)`, `undo=true`, `redo=true`.
- `structures_edit(structure, text)` replaces the text (only with no steps); `format`, `name`.

## Making things of it
- `structures_open_as_grid(structure, path)`: the list of records there as a grid (a table: SQL and the
  Analyze menu work on it); its origin is the structure, and through it the API call.
- `structures_save(structure)` to its file; with `name`, `format`, `folder` or `path`: Save as (the
  project's `structures/` folder by default). TOML cannot hold a null: it says so.
- `structures_lineage(structure)`: the call (inputs and body as sent, when; a sign-in input hidden) or
  file, each step, each grid made from it, as Mermaid too.
- In code: `sab.structure("gates")` is the saved file's value; `sab.structure_table("payload",
  "$.orders")` its records as a table. `structures_close(name, references=true)` lists where code uses it.
