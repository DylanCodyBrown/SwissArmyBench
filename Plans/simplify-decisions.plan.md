# The simplicity pass: the owner's decisions (2026-11-21)

From the simplicity critic's list (docs/ideas.md "Simplicity pass, 2026-11-21"). Nothing here is built yet.

## Cleanups (no feature lost): all four
1. Guard every page request in one place; remove the old app-canvas leftovers in the base.
2. Split the 1,422-line startup function (bootstrap.py) by area; the eight hand-written "save only when changed"
   use write_atomic(if_changed=True).
3. One date helper and one plural helper in the page (some formats shift slightly: accepted).
4. Real classes over interfaces: a port (Protocol) stays only where a test swaps in a fake; REFACTOR.md changes to say
   so. (Last: it touches everything; after the adapter merges.)

## Removed
- The 54 Write call snippets become one per target with a mode choice.
- The old-name aliases (SwissArmyGrid, renamed.py, src/swissarmygrid/, OLD_NAMES and GONE_NAMES whose release passed).
- The old tray's one-time cleanup (legacy_tray.py).
- Settings' Panels.
- Custom kind colours (fixed notebook and script colours stay).
- The tour's matching game (the tour stays).
- ECharts and Graphviz (Plotly and Mermaid stay).
- Packs (the team library shares blades).
- Approved outputs; Run as scheduled and its run history.
- The VS Code extension.

## Kept
The Analyze board's 20 themes; connection swap; Find connections; system file dialogs; the Queries window; Share;
the statistics; app registrations.

## Merged into one universal tool
- One way to browse tables: the Data Explorer (Open all and Import relationships move into it).
- One code editor screen for every code box, each with its own Properties.
- One `sab.write(connection, table, rows, mode)` through the adapter (after the adapter).
- One project picture: context.md, ARCHITECTURE.md and Launch Claude's folder from one live outline.
- One log with filters (audit and Session; the beta log stays).
- One way to make Excel (which one: to be designed with the owner first).
- Accounting's and the Power Apps notebook's DuckDB onto the shared one through the adapter (after the adapter).
- Not merged: Add API and the local sandbox API stay two tools.

## A visual change
The owner: "when you name a connection's color it doesn't need to be a little dot, it needs to be the highlighting
for the box of the connection itself": the connection's card (and its box wherever it is drawn) wears its colour
as its highlight; the dot goes.

## Order
Now (beside the adapter, files apart): the removals, cleanups 1 to 3, the connection colour. After the adapter: one
sab.write, the extensions' DuckDB, cleanup 4. Then the merges, the Excel one after a design talk.
