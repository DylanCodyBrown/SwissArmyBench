# Structures

Nested data (JSON, YAML, XML, TOML) as documents, as the Tables page holds tables. A structure is a tab of the
Structures page: a tree and its text, steps replayed on the original (never changed until Save).

## Beside the code (2026-11-22)
- A project's `.json`, `.yaml`, `.yml`, `.xml` or `.toml` file (its top and `structures/`; never an app's
  `*.canvas.json`, a `.design.json` or `.sab/`) opens as a tab on the Notebooks or Scripts page, beside the
  code: the page it was opened from, else Scripts. The Files pane lists them under Structures.
- It is an IDE: the file's text editable at all times (kept as typed; a parse error is its `text_error` with
  its line, squiggled), the tree and the text in step both ways, Format, Save (the text, only changed bytes),
  Save as, Cancel. The steps are a separate view for making tables (Transform): they never lock the text.
- In the window (`workbench_window`): "structure.open" {path, at?}, "structure.search" {words},
  "structure.next" {back?}, "structure.select" {at}, "structure.view" {view: tree|text|both},
  "structure.format", "structure.state" (its view, selection and its code, search, matches, problems);
  "documents" lists each one's state.
- Without the window: `structures_show(structure, search)` (each match's path and Python code,
  `data["orders"][3]`), `structures_edit(structure, edit={"op": set|rename|remove|add|duplicate|move, ...})`
  or `(format_text=true)`, `structures_save(structure, as_text=true)` (refused when the file changed on disk:
  `disk=reload` or `disk=keep_mine` first).

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
- `structures_edit(structure, text)` replaces the text (kept as typed, steps or not); `format`, `name`.

## Making things of it
- `structures_open_as_grid(structure, path)`: the list of records there on the Tables page (a table: SQL and the
  the Analyze page work on it); its origin is the structure, and through it the API call.
- `structures_save(structure)` to its file; with `name`, `format`, `folder` or `path`: Save as (the
  project's `structures/` folder by default). TOML cannot hold a null: it says so.
- `structures_lineage(structure)`: the call (inputs and body as sent, when; a sign-in input hidden) or
  file, each step, each table made from it, the cells that read it (sab.structure, sab.structure_table), as
  Mermaid too.
- In code: `sab.structure("gates")` is the saved file's value; `sab.structure_table("payload",
  "$.orders")` its records as a table. `structures_close(name, references=true)` lists where code uses it.
