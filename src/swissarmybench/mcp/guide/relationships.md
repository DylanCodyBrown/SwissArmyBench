# Keys and relationships

One relationship model: each table's primary key and the joins between tables. Known joins line up a
compare by themselves; the ERD draws the model of the open tables.

- Tangs are saved, shared sets of relationships (`.tang` files). `relationships_library` lists them
  (the user's and the team's) and `relationships_apply_library` applies one. Check here first.
- `relationships_find`: how the open tables join, worked out from the data: each suggestion with its
  match share, orphans and reasons. Show the evidence; set the ones the user agrees to with
  `relationships_set`. `relationships_reject` stops one being offered.
- `relationships_check`: the current model, or a tang, against the open tables: holds, orphans or broken.
- `relationships_path(start, end)`: the chain of joins between two tables.
- `key_finder_run`: likely join columns between two grids and the grid's likely primary key (counts
  only). `key_finder_candidates`, `key_finder_sample`.
- Prove a key before you set it: `count(*) = count(DISTINCT key)` with no blanks (`steps_run_sql`).
- `relationships_get`, `relationships_save_tang`, `relationships_export_tang`,
  `relationships_import_tang` (without apply: what it would change).
- A Power BI dataset's own relationships: `connections_import_relationships` (topic connections).
- `erd_text`: the model as Mermaid. `erd_draw`: a diagram card in Visualizations.

## Compare (two grids side by side)
- `compare_grids`: matched, left-only and right-only counts, without touching the page.
- `compare_create(left, right, keys, mode, show)`: modes outer, anti, cross, diff; `show=true` puts the
  two grids side by side on the user's page. `compare_list` finds the user's running compare.
- `compare_change`, `compare_read`, `compare_rows`, `compare_key_group`, `compare_set_focus` and
  `compare_clear_focus` (cross mode), `compare_remove`.
- Diff mode keeps the rows that differ; `diff` options: tolerance (percent too), trim, ignore_case,
  skip, column, only_differing.
- `compare_tie_out`: do both add up the same per group? Without group or measures it suggests them;
  with them, each group ties or is off, off first. `compare_tie_out_show` filters both grids to one
  group. A total that ties can hide groups that cancel out.
