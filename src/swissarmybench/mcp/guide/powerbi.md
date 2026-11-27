# Power BI

Built in (an extension of its own before 2026-11-27): on every install, with its rail page.

- `powerbi_export`: Export to Power BI… as the ERD page does it: the tables (default: the ERD's), their
  relationships and each table's Power Query as a Power BI Project in the open project's `powerbi/` (no project
  open: a zip in the export folder). `dry_run=true` says what would go: each table going or not and why (a
  source Power Query cannot read: `include_rows` sends its rows as Parquet, and waits for the user's Allow), its
  steps carried as the source's own SQL or not, the relationships made inactive (Power BI keeps one active path
  between two tables) or left out (two-column joins, types that differ). A variable reference becomes a Power
  Query parameter; no password or secret is ever written. Opening it in Power BI Desktop is the user's click.
- **Another report's pages:** `report` (a .pbix, .pbit or .pbip path) writes that report's pages, visuals, themes
  and bookmarks into the export's report, pointed at this model. With `dry_run` the answer's `report.fields`
  is the mapping it proposes (each field the visuals, filters and slicers name, matched by name in any case);
  pass `mapping` ({"Table.Field": "Table.Field", or null to leave a field broken}) to change it. The report's
  model measures come along (a .pbit's or .pbip's; a .pbix's through pbixray), rewritten through the mapping;
  one naming an unmapped column is said in `report.said`, not written. The dropped file is never changed.

## A Power BI project (the Power BI extension, part 2)

- **Reading a .pbix is pbixray's only; editing is the live Power BI Desktop link only.** They never cross.
- `powerbi_import_project(path, dry_run=true)` plans a .pbix as a project: one back-end connection per distinct
  source (an existing one with the same server and database reused), Power Query parameters as plain variables,
  the published dataset (a thin report's own, else one named like the file; several or none: pass `dataset`),
  the .pbix file connection, data.ipynb (a `%%sql` and a `%%dax` cell per table), relationships into the ERD,
  measures and each table's M kept in `.sab/powerbi.json`. Without `dry_run` it makes it (the user's Allow).
  `powerbi_export` then writes that round trip: an untouched table's M byte for byte, a table whose notebook
  `%%sql` cell changed as the new native query, the measures with their folders and formats.
  Every table opens twice: `<Table>_Source` and `<Table>_PowerBI`, with a Compare between them.
- `powerbi_setup_status`: the To finish setting up rows and their fixes (`action`: dataset, not_published,
  registration); passwords and sign-ins are the user's (Set up this computer).
- `powerbi_source(source=published|local)`: what the project's ONE dataset connection (named after the model)
  reads: the `_PowerBI` tabs, DuckDB SQL `[Sales model].Sales` (`steps_run_sql`, a `%%sql` cell), a
  `%%dax 'Sales model'` cell and the Compares all follow it with no code change; the file is the fallback, said
  (it answers whole tables only: `EVALUATE 'Sales'`).
- `powerbi_file(name, path)`: a .pbix as a read-only connection (pbixray), "as of" its last refresh.
- `app_registration_add` (three VARIABLE names, never values), `app_registration_check` (an access report:
  read-only calls, kept as names and marks: Power BI's workspaces and datasets, Azure SQL's databases and a
  SELECT TOP 0 per table, Dataverse's WhoAmI and roles, SharePoint's site, lists and libraries, a lake's path),
  `powerbi_app_registration(registration, dry_run)` re-points the project's Microsoft sources (Azure SQL, SQL
  Server with Entra, Dataverse, SharePoint, OneLake, Data Lake; the user's Allow). A connection's part is
  `GET /connections/{name}/access` (its Access section) and one line in context.md's Connections.
- `powerbi_edit_files`, `powerbi_edit_model`, `powerbi_edit_plan`, `powerbi_edit_apply`: Edit in Power BI
  Desktop (Windows): our relationships and measures, measures, calculated columns and tables, calculation
  groups; a dry run first; Apply waits for the user's Allow. A refresh or a table's Power Query is refused: export
  a Power BI Project instead.
- `app_gates`: the features a project type keeps closed (a Power BI project's); your tools stay open (the
  user's palette, New entries and addresses show the one line instead). context.md's Project says them.
