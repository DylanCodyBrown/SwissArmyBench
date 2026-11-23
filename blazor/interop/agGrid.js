// agGrid.js: AG Grid Community (blazor/package.json's pinned version), wrapped for the <AgGrid> component.
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
import { Corner, Header, hideCard, profilesOn, setProfiles } from "./gridHeader.js";
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

function columnDefs(columns, own) {
  return [
    {
      colId: ROW_NUMBER,
      headerName: "",
      width: 64,
      pinned: "left",
      sortable: false,
      resizable: false,
      headerComponent: Corner,
      headerComponentParams: { sab: own },
      valueGetter: (p) => (p.node.rowIndex == null ? "" : p.node.rowIndex + 1),
      cellClass: "grid-rownum",
      cellClassRules: { "row-selected": (p) => p.node.rowIndex != null && own.selection.kind === "rows" && own.selection.hasCell(p.node.rowIndex, "") },
    },
    ...columns.map((c, at) => ({
      colId: c.name,
      headerName: c.name,
      headerTooltip: `${c.name} · ${c.type}`,
      headerComponent: Header,
      headerComponentParams: { sab: own, type: c.type },
      field: String(at), // a row is an array: its value by position
      valueGetter: (p) => (p.data ? p.data[at] : undefined),
      sortable: true,
      resizable: true,
      type: NUMERIC.test(c.type) ? "rightAligned" : undefined,
      cellClassRules: {
        "cell-selected": (p) => p.node.rowIndex != null && own.selection.hasCell(p.node.rowIndex, c.name),
        "cell-diff": (p) => p.node.rowIndex != null && own.diffs.has(`${p.node.rowIndex}:${at}`),
      },
    })),
  ];
}

/** The grid in `host` for the server's grid `gridId`; returns its handle. */
export function mount(host, listener, gridId, firstColumns, clientId) {
  let columns = firstColumns;
  let gen = 0;
  let sentSort = "[]";
  let total = 0;
  let names = columns.map((c) => c.name);
  let dragging = null; // "cells", "rows" or "columns" while the mouse is down
  let focused = null; // the cell clicked last: {row, column}
  // Compare mode (the page sets it): rows come from the compare, aligned with the other grid. A placeholder row is
  // a key this side has no row for; a diff cell differs from the aligned row on the other side.
  let compare = null; // {id, side}
  let keyRows = null; // {first, last}: rows sharing the picked row's key
  let only = null; // diff mode: the columns shown (null: all)
  let upto = null; // a step's preview: the rows after the first `upto` steps (null: the whole view)
  const placeholders = new Set();
  let shownFrame = 0;
  const diffs = new Set();
  const selection = new Selection();
  selection.order = names;
  const base = `/grids/${encodeURIComponent(gridId)}`;
  const json = async (url, init) => {
    const answer = await fetch(url, { ...init, headers: { "Content-Type": "application/json", "X-Sab-Client": clientId } });
    if (!answer.ok) throw new Error(await answer.text());
    return answer.json();
  };
  let gridApi = null; // the grid's api once made (a header drawn while it is made asks before it exists)
  const profiles = new Map(); // a column's profile, kept for this view (a second hover draws at once)
  const own = {
    selection,
    diffs,
    stats: {},
    sparks: {},
    marks: new Set(),
    sortedCount: () => gridApi?.getColumnState().filter((c) => c.sort).length ?? 0,
    selectAll: () => {
      selection.all();
      changed();
    },
    renamed: (name, to) => listener.invokeMethodAsync("RenameColumn", name, to),
    profile: (column) => {
      if (!profiles.has(column)) {
        const asked = json(`${base}/profile?column=${encodeURIComponent(column)}`);
        asked.catch(() => profiles.delete(column));
        profiles.set(column, asked);
      }
      return profiles.get(column);
    },
    profilesChanged: () => {
      loadStats().finally(redrawHeaders);
    },
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
  const compareWindow = async (params, cmp) => {
    const body = await json(`/compares/${encodeURIComponent(cmp.id)}/rows?side=${cmp.side}&start=${params.startRow}&end=${params.endRow}`);
    if (compare?.id !== cmp.id || compare.side !== cmp.side) {
      params.failCallback(); // the compare changed while this window loaded
      return;
    }
    for (const offset of body.placeholders) placeholders.add(params.startRow + offset);
    for (const [r, c] of body.diffs) diffs.add(`${params.startRow + r}:${c}`);
    total = body.row_count;
    params.successCallback(body.rows, body.row_count);
    listener.invokeMethodAsync("Counted", body.row_count);
  };
  const datasource = {
    getRows(params) {
      if (compare) {
        compareWindow(params, compare).catch((error) => {
          params.failCallback();
          listener.invokeMethodAsync("Failed", String(error.message ?? error));
        });
        return;
      }
      const sort = JSON.stringify(params.sortModel.filter((s) => s.colId !== ROW_NUMBER).map((s) => [s.colId, s.sort]));
      (async () => {
        if (sort !== sentSort) {
          gen += 1;
          sentSort = sort;
          await json(`${base}/header-sort`, { method: "POST", body: JSON.stringify({ keys: JSON.parse(sort), gen, client: clientId }) });
          listener.invokeMethodAsync("Changed");
        }
        const asked = gen;
        const preview = upto === null ? "" : `&upto=${upto}`;
        const body = await json(`${base}/rows?start=${params.startRow}&end=${params.endRow}&gen=${asked}&client=${clientId}${preview}`);
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
    onViewportChanged: (event) => {
      // The rows on screen, for the status bar's "Rows 1–22 of 120" (once a frame, however fast the scroll).
      if (shownFrame) return;
      shownFrame = requestAnimationFrame(() => {
        shownFrame = 0;
        listener.invokeMethodAsync("Shown", Math.max(0, event.firstRow), Math.max(0, event.lastRow)).catch(() => {});
      });
    },
    getRowClass: (p) => {
      if (p.node.rowIndex == null) return "";
      const marks = [];
      if (placeholders.has(p.node.rowIndex)) marks.push("row-placeholder");
      if (keyRows && p.node.rowIndex >= keyRows.first && p.node.rowIndex <= keyRows.last) marks.push("row-key-match");
      return marks.join(" ");
    },
    onCellDoubleClicked: (event) => {
      if (event.rowIndex == null || event.column.getColId() === ROW_NUMBER) return;
      const mouse = event.event;
      listener.invokeMethodAsync("CellOpened", event.rowIndex, event.column.getColId(), mouse?.clientX ?? 0, mouse?.clientY ?? 0);
    },
    onCellClicked: (event) => {
      // A compared grid: a row picked lights up its key's rows (aligned) or filters the other side (cross).
      if (compare && event.rowIndex != null) listener.invokeMethodAsync("RowPicked", event.rowIndex);
    },
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
  gridApi = api;
  /** The headers' profile lines (Column profiles in the headers): distinct and blank share, and a tiny histogram
   *  for up to twelve number columns. Off by default: these queries run only while the headers show them. */
  const loadStats = async () => {
    if (!profilesOn()) return;
    try {
      own.stats = await json(`${base}/header-stats?gen=${gen}&client=${clientId}`);
      const numbers = columns.filter((c) => NUMERIC.test(c.type)).slice(0, 12);
      await Promise.all(numbers.map(async (c) => {
        const p = await own.profile(c.name);
        const counts = (p.histogram ?? []).map((b) => b.count);
        const top = Math.max(1, ...counts);
        own.sparks[c.name] = counts.map((n) => Math.round((100 * n) / top));
      }));
    } catch {
      // A convenience: the grid works without them.
    }
  };
  /** The headers drawn again (their profile lines on or off): new column definitions make AG Grid build them anew. */
  function redrawHeaders() {
    api.setGridOption("columnDefs", columnDefs(columns, own));
    if (only) api.setColumnsVisible(names.filter((n) => !only.has(n)), false);
  }
  loadStats().then(() => profilesOn() && redrawHeaders());
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
    } else if ((event.key === "Enter" || event.key === "F2") && !ctrl && focused) {
      // Enter or F2 on a cell opens its value, as a double-click does.
      event.preventDefault();
      listener.invokeMethodAsync("CellOpened", focused.row, focused.column, 0, 0);
    } else if (event.key === " " && event.shiftKey && focused) {
      // Shift+Space selects the cell's row (Excel's).
      event.preventDefault();
      selection.selectRows(focused.row, "replace");
      changed();
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
    /** The column profiles in the headers on or off (the Column row's Profiles in headers; remembered). */
    setProfiles(on) {
      setProfiles(on);
      own.profilesChanged();
    },
    /** Whether the headers show the column profiles now. */
    profiles() {
      return profilesOn();
    },
    refresh(nextColumns) {
      gen += 1;
      names = nextColumns.map((c) => c.name);
      selection.order = names;
      selection.clear();
      focused = null;
      profiles.clear();
      columns = nextColumns;
      hideCard();
      api.setGridOption("columnDefs", columnDefs(nextColumns, own));
      only = null;
      loadStats().then(() => profilesOn() && redrawHeaders());
      api.purgeInfiniteCache(); // a step that adds or removes columns must purge, not only refresh
      changed();
    },
    /** Compare mode on ({id, side}) or off (null): every row window asked for anew. */
    setCompare(next) {
      if (JSON.stringify(next) === JSON.stringify(compare)) return;
      compare = next;
      keyRows = null;
      placeholders.clear();
      diffs.clear();
      selection.clear();
      gen += 1;
      api.purgeInfiniteCache();
      changed();
    },
    /** A step's preview: the rows after the first `n` steps (null: back to the full view). */
    setUpto(n) {
      if (n === upto) return;
      upto = n;
      gen += 1;
      api.purgeInfiniteCache();
    },
    /** The rows sharing the picked row's key, lit up ({first, last}, or null). */
    setKeyRows(rows) {
      keyRows = rows;
      api.redrawRows();
    },
    /** Diff mode: only these columns shown (null: every column). */
    showOnly(shown) {
      const next = shown ? new Set(shown) : null;
      if (JSON.stringify(next && [...next].sort()) === JSON.stringify(only && [...only].sort())) return;
      only = next;
      api.setColumnsVisible(names.filter((n) => !only || only.has(n)), true);
      api.setColumnsVisible(names.filter((n) => only && !only.has(n)), false);
    },
    /** Scroll sideways to a column (diff mode's first column that differs). */
    revealColumn(name) {
      if (names.includes(name)) api.ensureColumnVisible(name, "start");
    },
    /** The element that scrolls up and down (the two compared grids keep one position). */
    scroller() {
      return host.querySelector(".ag-grid-viewport");
    },
    /** Each column (or the ones named) as wide as its values. */
    autoSize(only) {
      api.autoSizeColumns(only && only.length ? only : names);
    },
    /** One cell's value (from the rows loaded, else asked of the server). */
    cell(row, column) {
      return cellValue(row, column);
    },
    /** A loaded row's values as [column, value] pairs in the view's order (Send the row to Analyze). */
    rowValues(row) {
      const data = api.getDisplayedRowAtIndex(row)?.data;
      return names.map((name, at) => [name, data ? (data[at] ?? null) : null]);
    },
    /** The selected rows' positions (rows or cells selected), up to `most`: a sandbox table's Delete rows. */
    selectedRows(most) {
      const rows = [];
      if (selection.kind === "rows" || selection.kind === "cells") {
        for (const [first, last] of selection.rows) for (let r = first; r <= last && rows.length < most; r++) rows.push(r);
      }
      return rows;
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

/**
 * Two aligned grids keep one vertical position (a compare): whichever scrolls, the other takes its exact scrollTop
 * in the same frame, so row N on the left stays beside row N on the right. Returns what lets go.
 */
export function lockScroll(a, b) {
  const elements = [a.scroller(), b.scroller()].filter((e) => e);
  const offs = elements.map((element) => {
    const follow = () => {
      for (const other of elements) if (other !== element && other.scrollTop !== element.scrollTop) other.scrollTop = element.scrollTop;
    };
    element.addEventListener("scroll", follow, { passive: true });
    return () => element.removeEventListener("scroll", follow);
  });
  return { release: () => offs.forEach((off) => off()) };
}
