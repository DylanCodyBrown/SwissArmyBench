# Power BI (an extension)

On only where the Power BI extension is installed (`extensions_install` with `powerbi`); else its door says
which extension it needs.

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
