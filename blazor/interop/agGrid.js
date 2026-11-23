// agGrid.js: AG Grid Community (the classic front end's same version), wrapped for the <AgGrid> component.
//
// The infinite row model asks the server for windows of rows as the user scrolls (GET /grids/{id}/rows, as the
// classic gridView.ts does): the rows go straight from the server into the grid, never through C#. A header
// click is told to C# (its column card); a sort from the header is the server's header-sort.
import {
  CellStyleModule,
  ColumnApiModule,
  ColumnAutoSizeModule,
  InfiniteRowModelModule,
  ModuleRegistry,
  RowStyleModule,
  ScrollApiModule,
  TooltipModule,
  createGrid,
  themeQuartz,
} from "ag-grid-community";

ModuleRegistry.registerModules([CellStyleModule, InfiniteRowModelModule, ColumnApiModule, ColumnAutoSizeModule, RowStyleModule, ScrollApiModule, TooltipModule]);

// The grid's colours are the app's tokens (tokens.css), so a theme switch needs no new grid.
const theme = themeQuartz.withParams({
  backgroundColor: "var(--bg)",
  foregroundColor: "var(--fg)",
  headerBackgroundColor: "var(--surface)",
  headerTextColor: "var(--fg)",
  borderColor: "var(--border)",
  accentColor: "var(--accent)",
  selectedRowBackgroundColor: "var(--selected)",
  rowHoverColor: "var(--row-hover)",
  oddRowBackgroundColor: "var(--bg)",
  chromeBackgroundColor: "var(--surface)",
  fontFamily: '"Segoe UI", system-ui, sans-serif',
  fontSize: 13,
  headerFontSize: 13,
  rowHeight: 28,
  headerHeight: 34,
  spacing: 6,
  wrapperBorderRadius: 0,
});

const ROW_NUMBER = "__row";
const NUMERIC = /^(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|U?(TINY|SMALL|BIG)?INT|DOUBLE|FLOAT|REAL|DECIMAL)/i;

function columnDefs(columns) {
  return [
    { colId: ROW_NUMBER, headerName: "", width: 64, pinned: "left", sortable: false, resizable: false, valueGetter: (p) => (p.node.rowIndex == null ? "" : p.node.rowIndex + 1), cellClass: "grid-rownum" },
    ...columns.map((c, at) => ({
      colId: c.name,
      headerName: c.name,
      headerTooltip: `${c.name} · ${c.type}`,
      field: String(at), // a row is an array: its value by position
      valueGetter: (p) => (p.data ? p.data[at] : undefined),
      sortable: true,
      resizable: true,
      type: NUMERIC.test(c.type) ? "rightAligned" : undefined,
    })),
  ];
}

/** The grid in `host` for the server's grid `gridId`; returns its handle (refresh, destroy). */
export function mount(host, listener, gridId, columns, clientId) {
  let gen = 0;
  let sentSort = "[]";
  const base = `/grids/${encodeURIComponent(gridId)}`;
  const json = async (url, init) => {
    const answer = await fetch(url, { ...init, headers: { "Content-Type": "application/json", "X-Sab-Client": clientId } });
    if (!answer.ok) throw new Error(await answer.text());
    return answer.json();
  };
  const datasource = {
    getRows(params) {
      const sort = JSON.stringify(params.sortModel.filter((s) => s.colId !== ROW_NUMBER).map((s) => [s.colId, s.sort]));
      (async () => {
        if (sort !== sentSort) {
          gen += 1;
          sentSort = sort;
          await json(`${base}/header-sort`, { method: "POST", body: JSON.stringify({ keys: JSON.parse(sort), gen, client: clientId }) });
          listener.invokeMethodAsync("Changed");
        }
        const asked = gen;
        const body = await json(`${base}/rows?start=${params.startRow}&end=${params.endRow}&gen=${asked}&client=${clientId}`);
        if (asked !== gen) {
          params.failCallback(); // a newer view replaced this one while it loaded
          return;
        }
        params.successCallback(body.rows, body.row_count);
        listener.invokeMethodAsync("Counted", body.row_count);
      })().catch((error) => {
        params.failCallback();
        listener.invokeMethodAsync("Failed", String(error.message ?? error));
      });
    },
  };
  const api = createGrid(host, {
    theme,
    rowModelType: "infinite",
    datasource,
    cacheBlockSize: 200,
    maxBlocksInCache: 40,
    columnDefs: columnDefs(columns),
    defaultColDef: { resizable: true, minWidth: 80 },
    alwaysShowHorizontalScroll: true,
    onColumnHeaderClicked: (event) => {
      const id = event.column?.getColId?.();
      if (id && id !== ROW_NUMBER) listener.invokeMethodAsync("HeaderClicked", id);
    },
  });
  return {
    /** The grid's steps changed (a new view): its columns again, every row window asked for anew. */
    refresh(nextColumns) {
      gen += 1;
      api.setGridOption("columnDefs", columnDefs(nextColumns));
      api.purgeInfiniteCache(); // a step that adds or removes columns must purge, not only refresh
    },
    destroy() {
      api.destroy();
    },
  };
}
