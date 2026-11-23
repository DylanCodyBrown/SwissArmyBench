// agGrid.js: AG Grid Community (the classic front end's same version), wrapped for the <AgGrid> component.
//
// The infinite row model asks the server for windows of rows as the user scrolls (GET /grids/{id}/rows, as the
// classic gridView.ts does): the rows go straight from the server into the grid, never through C#. A sort from a
// header's arrow is the server's header-sort.
//
// Selection works like Excel and like the classic grid (selection.ts): the row numbers select rows, a header
// selects its column (Shift extends, Ctrl adds), a drag or Shift+click across cells selects a block, Ctrl+A
// everything. AG Grid Community has no range selection, so the selection is drawn with cell classes and told to C#
// (SelectionChanged) as the server's descriptor ({rows, columns}); the server counts, sums and copies it, so rows
// never loaded count too. Right-clicks are told to C# (CellMenu, HeaderMenu), which draws the menus.
import {
  CellStyleModule,
  ColumnApiModule,
  ColumnAutoSizeModule,
  InfiniteRowModelModule,
  ModuleRegistry,
  RenderApiModule,
  RowApiModule,
  RowStyleModule,
  ScrollApiModule,
  TooltipModule,
  createGrid,
  themeQuartz,
} from "ag-grid-community";

ModuleRegistry.registerModules([CellStyleModule, RenderApiModule, RowApiModule, InfiniteRowModelModule, ColumnApiModule, ColumnAutoSizeModule, RowStyleModule, ScrollApiModule, TooltipModule]);

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
const COPY_CAP = 1_000_000;

/** What is selected, as the classic GridSelection keeps it: rows as view positions, columns by name. */
class Selection {
  constructor() {
    this.kind = "none";
    this.rows = [];
    this.columns = [];
    this.anchor = null;
    this.order = [];
  }
  clear() {
    this.kind = "none";
    this.rows = [];
    this.columns = [];
    this.anchor = null;
  }
  all() {
    this.kind = "all";
    this.rows = [];
    this.columns = [];
  }
  selectRows(row, mode) {
    if (mode === "extend" && this.kind === "rows" && this.anchor) {
      this.rows = [...this.rows.slice(0, -1), sorted(this.anchor.row, row)];
    } else {
      this.rows = mode === "add" && this.kind === "rows" ? [...this.rows, [row, row]] : [[row, row]];
      this.anchor = { row, col: 0 };
    }
    this.kind = "rows";
    this.columns = [];
  }
  selectColumns(name, mode) {
    const at = this.order.indexOf(name);
    if (at < 0) return;
    if (mode === "extend" && this.kind === "columns" && this.anchor) {
      const [a, b] = sorted(this.anchor.col, at);
      this.columns = this.order.slice(a, b + 1);
    } else if (mode === "add" && this.kind === "columns") {
      const picked = this.columns.includes(name) ? this.columns.filter((c) => c !== name) : [...this.columns, name];
      this.columns = this.order.filter((c) => picked.includes(c));
      if (!this.columns.length) return this.clear();
    } else {
      this.columns = [name];
      this.anchor = { row: 0, col: at };
    }
    this.kind = "columns";
    this.rows = [];
  }
  selectCells(row, name, extend) {
    const col = this.order.indexOf(name);
    if (col < 0) return;
    if (!extend || !this.anchor || this.kind !== "cells") this.anchor = { row, col };
    const [c0, c1] = sorted(this.anchor.col, col);
    this.kind = "cells";
    this.rows = [sorted(this.anchor.row, row)];
    this.columns = this.order.slice(c0, c1 + 1);
  }
  hasCell(row, name) {
    if (this.kind === "all") return true;
    const inRows = this.rows.some(([a, b]) => row >= a && row <= b);
    if (this.kind === "rows") return inRows;
    if (this.kind === "columns") return this.columns.includes(name);
    if (this.kind === "cells") return inRows && this.columns.includes(name);
    return false;
  }
  /** The shape the server reads (server/selection.py); null rows or columns mean all of them. */
  descriptor() {
    if (this.kind === "none") return null;
    if (this.kind === "all") return { rows: null, columns: null };
    if (this.kind === "columns") return { rows: null, columns: this.columns };
    return { rows: merge(this.rows), columns: this.kind === "rows" ? null : this.columns };
  }
  rowCount(total) {
    if (this.kind === "none") return 0;
    if (this.kind === "all" || this.kind === "columns") return total;
    return merge(this.rows).reduce((n, [a, b]) => n + Math.max(0, Math.min(b, total - 1) - a + 1), 0);
  }
}

function sorted(a, b) {
  return a <= b ? [a, b] : [b, a];
}

function merge(ranges) {
  const out = [];
  for (const [a, b] of [...ranges].sort((x, y) => x[0] - y[0])) {
    const last = out[out.length - 1];
    if (last && a <= last[1] + 1) last[1] = Math.max(last[1], b);
    else out.push([a, b]);
  }
  return out;
}

/** A header of the app's own: the name (a click selects the column) and a small sort arrow (the server's sort). */
class Header {
  init(params) {
    const name = params.column.getColId();
    const own = params.sab;
    this.element = document.createElement("div");
    this.element.className = "sab-header";
    const label = document.createElement("span");
    label.className = "sab-header-name";
    label.textContent = params.displayName;
    label.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      own.headerDown(name, event);
    });
    label.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      own.headerMenu(name, event);
    });
    const sort = document.createElement("button");
    sort.type = "button";
    sort.className = "sab-header-sort";
    sort.title = `Sort by ${name}`;
    sort.setAttribute("aria-label", `Sort by ${name}`);
    const draw = () => {
      const now = params.column.getSort();
      sort.textContent = now === "asc" ? "▲" : now === "desc" ? "▼" : "↕";
    };
    draw();
    params.column.addEventListener("sortChanged", draw);
    sort.addEventListener("click", (event) => {
      event.stopPropagation();
      params.progressSort(event.shiftKey);
    });
    this.element.append(label, sort);
    // The whole header cell is marked (the element is put in it after init: marked again on the next frame).
    this.mark = () => (this.element.closest(".ag-header-cell") ?? this.element).classList.toggle("col-selected", own.columnSelected(name));
    own.marks.add(this.mark);
    this.own = own;
    requestAnimationFrame(this.mark);
  }
  getGui() {
    return this.element;
  }
  refresh() {
    return false;
  }
  destroy() {
    this.own.marks.delete(this.mark);
  }
}

function columnDefs(columns, own) {
  return [
    {
      colId: ROW_NUMBER,
      headerName: "",
      width: 64,
      pinned: "left",
      sortable: false,
      resizable: false,
      valueGetter: (p) => (p.node.rowIndex == null ? "" : p.node.rowIndex + 1),
      cellClass: "grid-rownum",
      cellClassRules: { "row-selected": (p) => p.node.rowIndex != null && own.selection.kind === "rows" && own.selection.hasCell(p.node.rowIndex, "") },
    },
    ...columns.map((c, at) => ({
      colId: c.name,
      headerName: c.name,
      headerTooltip: `${c.name} · ${c.type}`,
      headerComponent: Header,
      headerComponentParams: { sab: own },
      field: String(at), // a row is an array: its value by position
      valueGetter: (p) => (p.data ? p.data[at] : undefined),
      sortable: true,
      resizable: true,
      type: NUMERIC.test(c.type) ? "rightAligned" : undefined,
      cellClassRules: { "cell-selected": (p) => p.node.rowIndex != null && own.selection.hasCell(p.node.rowIndex, c.name) },
    })),
  ];
}

/** The grid in `host` for the server's grid `gridId`; returns its handle. */
export function mount(host, listener, gridId, columns, clientId) {
  let gen = 0;
  let sentSort = "[]";
  let total = 0;
  let names = columns.map((c) => c.name);
  let dragging = null; // "cells", "rows" or "columns" while the mouse is down
  let focused = null; // the cell clicked last: {row, column}
  const selection = new Selection();
  selection.order = names;
  const base = `/grids/${encodeURIComponent(gridId)}`;
  const json = async (url, init) => {
    const answer = await fetch(url, { ...init, headers: { "Content-Type": "application/json", "X-Sab-Client": clientId } });
    if (!answer.ok) throw new Error(await answer.text());
    return answer.json();
  };
  const own = {
    selection,
    marks: new Set(),
    columnSelected: (name) => selection.kind === "all" || (selection.kind === "columns" && selection.columns.includes(name)),
    headerDown: (name, event) => {
      selection.selectColumns(name, event.shiftKey ? "extend" : event.ctrlKey || event.metaKey ? "add" : "replace");
      dragging = "columns";
      changed();
      listener.invokeMethodAsync("HeaderClicked", name);
    },
    headerMenu: (name, event) => {
      if (!own.columnSelected(name)) {
        selection.selectColumns(name, "replace");
        changed();
      }
      listener.invokeMethodAsync("HeaderMenu", name, event.clientX, event.clientY);
    },
  };
  const changed = () => {
    api.refreshCells({ force: true });
    for (const mark of own.marks) mark();
    const target = selection.kind === "columns" || selection.kind === "cells" ? selection.columns : focused && selection.kind === "none" ? [focused.column] : [];
    listener.invokeMethodAsync("SelectionChanged", { kind: selection.kind, descriptor: selection.descriptor(), target }).catch(() => {});
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
        total = body.row_count;
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
    columnDefs: columnDefs(columns, own),
    defaultColDef: { resizable: true, minWidth: 80 },
    alwaysShowHorizontalScroll: true,
    suppressCellFocus: false,
    preventDefaultOnContextMenu: true,
    onCellMouseDown: (event) => {
      const mouse = event.event;
      if (event.rowIndex == null || mouse.button !== 0) return;
      const column = event.column.getColId();
      if (column === ROW_NUMBER) {
        selection.selectRows(event.rowIndex, mouse.shiftKey ? "extend" : mouse.ctrlKey || mouse.metaKey ? "add" : "replace");
        dragging = "rows";
      } else {
        focused = { row: event.rowIndex, column };
        selection.selectCells(event.rowIndex, column, mouse.shiftKey);
        dragging = "cells";
      }
      changed();
    },
    onCellMouseOver: (event) => {
      if (!dragging || event.rowIndex == null) return;
      const column = event.column.getColId();
      if (dragging === "rows") selection.selectRows(event.rowIndex, "extend");
      else if (dragging === "cells" && column !== ROW_NUMBER) selection.selectCells(event.rowIndex, column, true);
      else return;
      changed();
    },
    onCellContextMenu: (event) => {
      if (event.rowIndex == null) return;
      const column = event.column.getColId();
      if (column === ROW_NUMBER) return;
      if (!selection.hasCell(event.rowIndex, column)) {
        focused = { row: event.rowIndex, column };
        selection.selectCells(event.rowIndex, column, false);
        changed();
      }
      const mouse = event.event;
      listener.invokeMethodAsync("CellMenu", event.rowIndex, column, mouse.clientX, mouse.clientY);
    },
  });
  const up = () => {
    dragging = null;
  };
  window.addEventListener("mouseup", up);
  const keys = (event) => {
    const ctrl = event.ctrlKey || event.metaKey;
    if (ctrl && event.key === "a") {
      event.preventDefault();
      selection.all();
      changed();
    } else if (ctrl && event.key === "c") {
      event.preventDefault();
      handle.copy("plain").then((words) => words && listener.invokeMethodAsync("Said", words));
    } else if (event.key === "Escape" && selection.kind !== "none") {
      selection.clear();
      changed();
    }
  };
  host.addEventListener("keydown", keys);

  /** The value of one cell: from the rows loaded, else asked of the server. */
  const cellValue = async (row, column) => {
    const at = names.indexOf(column);
    const data = api.getDisplayedRowAtIndex(row)?.data;
    if (data && at >= 0) return data[at];
    return (await json(`${base}/cell?row=${row}&column=${encodeURIComponent(column)}`)).value;
  };

  const writeClipboard = async (text) => {
    if (typeof ClipboardItem !== "undefined") {
      // A ClipboardItem built from a promise keeps the click's permission while the server builds the text.
      await navigator.clipboard.write([new ClipboardItem({ "text/plain": text.then((t) => new Blob([t], { type: "text/plain" })) })]);
    } else {
      await navigator.clipboard.writeText(await text);
    }
  };

  const handle = {
    /** The grid's steps changed (a new view): its columns again, every row window asked for anew. */
    refresh(nextColumns) {
      gen += 1;
      names = nextColumns.map((c) => c.name);
      selection.order = names;
      selection.clear();
      focused = null;
      api.setGridOption("columnDefs", columnDefs(nextColumns, own));
      api.purgeInfiniteCache(); // a step that adds or removes columns must purge, not only refresh
      changed();
    },
    /** Each column (or the ones named) as wide as its values. */
    autoSize(only) {
      api.autoSizeColumns(only && only.length ? only : names);
    },
    /** The selection's distinct values in one column, from the rows loaded (Keep these, Exclude these). */
    async values(column) {
      if (selection.kind === "none" || (selection.kind === "cells" && selection.rows.length === 1 && selection.rows[0][0] === selection.rows[0][1])) {
        const row = selection.kind === "cells" ? selection.rows[0][0] : focused?.row;
        return row == null ? [] : [await cellValue(row, column)];
      }
      const at = names.indexOf(column);
      const seen = new Map();
      api.forEachNode((node) => {
        if (node.data && node.rowIndex != null && selection.hasCell(node.rowIndex, column) && seen.size < 500) seen.set(JSON.stringify(node.data[at]), node.data[at]);
      });
      return [...seen.values()];
    },
    /**
     * The selection on the clipboard, built by the server (rows never loaded copy too): plain is Excel's way (a block
     * of cells without its header row), headers puts the names first, markdown a pipe table. Its words, or null.
     */
    async copy(style) {
      let descriptor = selection.descriptor();
      if (!descriptor) {
        if (!focused) return null;
        if (style === "plain") {
          const value = await cellValue(focused.row, focused.column);
          await writeClipboard(Promise.resolve(value == null ? "" : String(value)));
          return "Copied the cell.";
        }
        descriptor = { rows: [[focused.row, focused.row]], columns: [focused.column] };
      }
      const rows = selection.kind === "none" ? 1 : selection.rowCount(total);
      if (rows > COPY_CAP) throw new Error(`Too many rows to copy (up to ${COPY_CAP.toLocaleString()}).`);
      const query = new URLSearchParams({
        scope: "selection",
        selection: JSON.stringify(descriptor),
        format: style === "markdown" ? "md" : "txt",
        delimiter: "tab",
        header: style === "plain" && selection.kind === "cells" ? "0" : "1",
        provenance: "0",
        neutralize_formulas: "0",
        line_ending: "windows",
      });
      const text = fetch(`${base}/export?${query}`, { headers: { "X-Sab-Client": clientId } }).then(async (answer) => {
        if (!answer.ok) throw new Error(await answer.text());
        return answer.text();
      });
      await writeClipboard(text);
      const cells = descriptor.columns ? descriptor.columns.length : names.length;
      const what = style === "markdown" ? " as Markdown" : style === "headers" ? " with headers" : "";
      return `Copied ${rows.toLocaleString()} row${rows === 1 ? "" : "s"} × ${cells.toLocaleString()} column${cells === 1 ? "" : "s"}${what}.`;
    },
    destroy() {
      window.removeEventListener("mouseup", up);
      host.removeEventListener("keydown", keys);
      api.destroy();
    },
  };
  return handle;
}
