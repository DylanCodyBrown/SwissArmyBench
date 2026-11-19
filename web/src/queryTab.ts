/**
 * queryTab.ts: the "+" tab: a new table from one SELECT over the open tables. [WIRE + EXPORT]
 *
 * The "+" after the last tab opens a draft: a SQL tray over a blank grid. A table name in the
 * query reads that table as its tab shows it, after its steps (a table with no tab open reads its
 * rows as loaded). Run stores the result as a new dataset (POST /datasets/{name}/query), and the
 * draft becomes an ordinary grid tab on it, with every tool a pushed table has.
 *
 * That tab keeps the tray, so the query can change and Run again: the table is rebuilt in place
 * and the tab's own steps apply to the new rows. The tray is the table's source, like a view
 * definition; the steps are everything after it, and the SQL box in Table Transformations is one
 * more step on top.
 *
 * Query from (the owner, 2026-11-17: "add a connection and query from that connection or choose Grids to
 * query local"): Grids runs the query in DuckDB over the open tables; a connection runs it there, in its own
 * SQL (POST /datasets/{name}/connection-query), and the table remembers where, so Run again goes back there;
 * Add a connection… opens the Connections page's types, and the new one is offered when it is saved.
 *
 * ROUTING: [TRAY TOGGLE]  -> setOpen()                  (one row, or the editor too)
 *          [QUERY FROM]   -> sourcePicker()             (Grids, each connection that runs SQL, Add a connection…)
 *          [TABLE NAME]   -> panes.renameDraft()        (the draft only; a built table keeps its name)
 *          [RUN]          -> runDraft() / runAgain()    (Ctrl+Enter in the editor too)
 *          [STATUS]       -> report(): the rows built, or the server's reason
 *          [EDITOR]       Monaco (a text box if it fails to load); autocomplete -> refreshNames()
 *          [BLANK GRID]   -> read-only, empty until the draft's first Run
 */
import { createGrid, type GridApi } from "ag-grid-community";
import { api, onNotice } from "./api";
import { openConnectionTypes } from "./connectionsWindow";
import { button, clear, formatCount, h, icon, toast } from "./dom";
import { contextOf, currentDraft, finishDraft, gridList, onAgentView, onPaneCreated, onPaneDropped, renameDraft, viewingQuery, type Context } from "./panes";
import { effectiveTheme, gridTheme, onThemeChange } from "./theme";
import type { SqlEditor } from "./lazy/codeEditor";
import { markBusy } from "./loading";

/** What POST /datasets/{name}/query answers. */
interface Built {
  grid: string;
  dataset: string;
  version: number;
  rows: number;
  /** The connections' tables the query named ([Finance Captive].Sales), each read once a session. */
  /** The connection the query ran on (Query from), when not the grids. */
  connection?: string;
  connection_reads?: { connection: string; as: string; rows: number; cut: boolean; read_at: string; cached: boolean; sent?: { filters: string; limit: number | null } }[];
}

/** Where the connections' tables came from and when, for the tray's status line. */
function readsText(built: Built): string {
  const reads = built.connection_reads ?? [];
  return reads.map((r) => ` ${r.as}: ${formatCount(r.rows)} rows, read ${r.read_at.slice(11)}${r.sent?.filters ? ` (filters sent: ${r.sent.filters})` : ""}.`).join("");
}

/** Refresh: the connections' tables are read again on the next Run. */
function offerRefresh(built: Built): void {
  const reads = built.connection_reads ?? [];
  if (!reads.length) return;
  const names = [...new Set(reads.map((r) => r.connection))];
  toast(`Read from ${names.join(", ")}`, "info", {
    label: "Refresh",
    run: () => void Promise.all(names.map((connection) => api("/connections/sql/refresh", "POST", { connection }))).then(() => toast("Run again reads them anew.")),
  });
}

/** Where a query runs: "" is Grids (DuckDB over the open tables), else a connection's name. */
interface Source {
  connection: string;
  /** A Power BI workspace's dataset, for DAX. */
  dataset: string;
}

/** A connection the picker offers: one that runs a query in its own SQL. */
interface QueryConnection {
  name: string;
  dax: boolean;
}

interface Tray {
  element: HTMLElement;
  editor: SqlEditor;
  report: (message: string, error?: boolean) => void;
  busy: (on: boolean) => void;
}

const NAME = /^[A-Za-z0-9_-]{1,64}$/;

let host: HTMLElement;
let draftTray: Promise<Tray> | null = null;
let nameInput: HTMLInputElement;
let blankGrid: GridApi | null = null;
let drawnSerial = 0;
/** The draft's Query from: Grids until the user picks a connection. */
const draftSource: Source = { connection: "", dataset: "" };
let drawPicker: (() => Promise<void>) | null = null;
// Monaco has one theme for every editor, so any editor can switch it.
let lastEditor: SqlEditor | null = null;
// Each built table's tray, by grid id, so a closed tab frees its editor.
const trays = new Map<string, Promise<Tray>>();

export function mountQueryTab(element: HTMLElement): void {
  host = element;
  onAgentView(() => { if (viewingQuery()) void showDraft(); });
  onPaneCreated(attachTray);
  onPaneDropped((ctx) => dropTray(ctx.id));
  onNotice((notice) => { if (notice.type === "blades_changed") void drawPicker?.(); });
  onThemeChange(() => {
    lastEditor?.setTheme(effectiveTheme());
    blankGrid?.setGridOption("theme", gridTheme());
  });
}

// ===== THE DRAFT: a tray over a blank grid, until its first Run =====

async function showDraft(): Promise<void> {
  const draft = currentDraft();
  if (!draft) return;
  draftTray ??= buildDraft();
  const tray = await draftTray;
  if (drawnSerial !== draft.serial) {
    // A new draft: its own name, and a fresh query (a closed draft's text is not carried over).
    drawnSerial = draft.serial;
    nameInput.value = draft.name;
    tray.editor.setValue(firstQuery());
    tray.report(hint());
  }
  tray.editor.focus();
  await refreshNames(tray.editor);
}

async function buildDraft(): Promise<Tray> {
  nameInput = h("input", {
    type: "text",
    class: "query-name mono",
    "aria-label": "Name of the new table",
    spellcheck: "false",
    maxlength: "64",
    oninput: () => renameDraft(nameInput.value.trim()),
  });
  const picker = sourcePicker();
  const tray = await createTray("", () => void runDraft(), hint(), nameInput, picker.element);
  drawPicker = picker.draw;
  void picker.draw();
  const gridHost = h("div", { class: "query-blank" });
  clear(
    host,
    // ===== QUERY TRAY =====
    tray.element,
    // ===== BLANK GRID =====
    gridHost,
  );
  blankGrid = createGrid<unknown[]>(gridHost, {
    theme: gridTheme(),
    columnDefs: [],
    rowData: [],
    // Fixed text: no data reaches this template.
    overlayNoRowsTemplate: "<span>No rows</span>",
  });
  return tray;
}

async function runDraft(): Promise<void> {
  const tray = await draftTray!;
  const name = nameInput.value.trim();
  if (!NAME.test(name)) {
    tray.report("Name: 1 to 64 letters, digits, _ or -.", true);
    nameInput.focus();
    return;
  }
  const built = await build(tray, name, false, { ...draftSource });
  if (!built) return;
  toast(`Built ${built.dataset}: ${rowsText(built.rows)}${built.connection ? ` from ${built.connection}` : ""}.`);
  await finishDraft(built.grid, built.dataset);
}

// ===== A BUILT TABLE'S PANE: its tray, to change the query and Run again =====

function attachTray(ctx: Context): void {
  const slot = ctx.pane!.querySelector<HTMLElement>(".query-slot")!;
  let loaded: string | null = null; // the query the tray last took from the server
  const sync = async (): Promise<void> => {
    const query = ctx.state.info?.query ?? null;
    const on = (ctx.state.info as { query_connection?: string | null } | null)?.query_connection ?? "";
    if (query === null) {
      // Not a query's table (or a push under its name replaced it): no tray.
      clear(slot);
      dropTray(ctx.id);
      loaded = null;
      return;
    }
    const tray = trays.get(ctx.id);
    if (!tray) {
      loaded = query;
      const label = on ? h("span", { class: "query-from fixed", title: `This query runs on ${on}, in its own SQL` }, `on ${on}`) : undefined;
      const pending = createTray(query, () => void pending.then((t) => runAgain(ctx, t)), on ? `Runs on ${on}` : hint(ctx.dataset), undefined, label);
      trays.set(ctx.id, pending);
      const created = await pending;
      if (trays.get(ctx.id) === pending) slot.append(created.element);
      await refreshNames(created.editor);
      return;
    }
    // Rebuilt (here, or from another tab on the same table): show the query that built it.
    if (query !== loaded) {
      loaded = query;
      const current = await tray;
      if (current.editor.value() !== query) current.editor.setValue(query);
    }
  };
  ctx.state.onOwn("info", () => void sync());
  void sync();
}

/** Free a tray's editor: its tab closed, or its table is no longer a query's. */
function dropTray(id: string): void {
  void trays.get(id)?.then((tray) => tray.editor.dispose());
  trays.delete(id);
}

async function runAgain(ctx: Context, tray: Tray): Promise<void> {
  // The server tells every page (dataset_updated); main.ts reloads this grid, steps and all.
  const on = (ctx.state.info as { query_connection?: string | null } | null)?.query_connection ?? "";
  await build(tray, ctx.dataset, true, { connection: on, dataset: "" });
}

// ===== QUERY FROM: Grids, a connection, or a new one =====

/** The draft's picker: Grids (the open tables, in DuckDB), each connection that runs SQL, Add a connection…;
 *  a Power BI workspace asks for its dataset beside it. */
function sourcePicker(): { element: HTMLElement; draw: () => Promise<void> } {
  const ADD = "\u0000add";
  const select = h("select", { class: "query-source", "aria-label": "Query from" });
  const dataset = h("input", { type: "text", class: "query-dataset", "aria-label": "Power BI dataset", placeholder: "Dataset", spellcheck: "false", hidden: true });
  let known: QueryConnection[] = [];
  const sync = (): void => {
    const picked = known.find((c) => c.name === draftSource.connection);
    dataset.hidden = !picked?.dax;
    select.title = picked ? `The query runs on ${picked.name}, in its own SQL` : "The query runs in DuckDB over the open grids";
    void draftTray?.then((tray) => tray.report(picked ? `Runs on ${picked.name}, in its own SQL${picked.dax ? " (DAX)" : ""}` : hint()));
  };
  const draw = async (): Promise<void> => {
    try {
      const { connections } = await api<{ connections: { name: string; connection: string; tables_kind?: string | null }[] }>("/connections");
      // A database connection runs a query in its own SQL; Dataverse's Web API side does not (only its SQL endpoint).
      known = connections
        .filter((c) => c.connection === "database" && c.tables_kind !== "dataverse_web")
        .map((c) => ({ name: c.name, dax: c.tables_kind === "powerbi" }));
    } catch {
      known = [];
    }
    if (draftSource.connection && !known.some((c) => c.name === draftSource.connection)) draftSource.connection = "";
    clear(
      select,
      h("option", { value: "" }, "Grids (the open tables)"),
      ...(known.length ? [h("optgroup", { label: "Connections" }, ...known.map((c) => h("option", { value: c.name }, c.name)))] : []),
      h("option", { value: ADD }, "Add a connection…"),
    );
    select.value = draftSource.connection;
    sync();
  };
  select.addEventListener("change", () => {
    if (select.value === ADD) {
      select.value = draftSource.connection;
      void openConnectionTypes();
      return;
    }
    draftSource.connection = select.value;
    void draftTray?.then((tray) => {
      // A connection's own SQL: start from a plain SELECT, not the grids' table names.
      if (draftSource.connection && tray.editor.value().trim() === firstQuery().trim()) tray.editor.setValue("SELECT *\nFROM ");
      else if (!draftSource.connection && tray.editor.value().trim() === "SELECT *\nFROM") tray.editor.setValue(firstQuery());
      tray.editor.focus();
    });
    sync();
  });
  dataset.addEventListener("input", () => { draftSource.dataset = dataset.value.trim(); });
  return { element: h("span", { class: "query-from" }, h("span", { class: "query-from-label" }, "from"), select, dataset), draw };
}

// ===== THE TRAY =====

/** A bar (collapse, the draft's name, the green Run, the status) over the SQL editor. */
async function createTray(initial: string, onRun: () => void, firstStatus: string, name?: HTMLInputElement, from?: HTMLElement): Promise<Tray> {
  const element = h("section", { class: "query-tray", "data-open": "true", "aria-label": "The query that builds this table" });
  const editorHost = h("div", { class: "sql-editor" });
  const status = h("span", { class: "sql-status", role: "status" }, firstStatus);
  const run = button("Run", onRun, { icon: "play", class: "run", title: "Run (Ctrl+Enter)" });
  let restoreRun = (): void => undefined;
  const toggle = button("Hide the query", () => setOpen(element.dataset.open !== "true"), { icon: "up", iconOnly: true, class: "ghost" });
  toggle.setAttribute("aria-expanded", "true");
  const setOpen = (open: boolean): void => {
    const label = open ? "Hide the query" : "Show the query";
    element.dataset.open = String(open);
    toggle.replaceChildren(icon(open ? "up" : "down"));
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.title = label;
  };
  element.append(h("div", { class: "query-tray-bar" }, toggle, h("strong", {}, name ? "New table" : "Query"), name ?? null, from ?? null, run, status), editorHost);
  const editor = await openEditor(editorHost, initial, onRun);
  lastEditor = editor;
  return {
    element,
    editor,
    report: (message, error = false) => {
      status.textContent = message;
      status.className = error ? "sql-status error" : "sql-status";
    },
    busy: (on) => {
      // The Run button is busy while the query runs (loading.ts); its result or error follows in the status.
      restoreRun();
      restoreRun = () => undefined;
      if (on) {
        restoreRun = markBusy(run, "Running…");
        status.textContent = "";
        status.className = "sql-status";
      }
    },
  };
}

/** Monaco when it loads (it is optional), else a plain text box that does the same job. */
async function openEditor(editorHost: HTMLElement, initial: string, onRun: () => void): Promise<SqlEditor> {
  try {
    const m = (await import(/* external */ "/static/build/lazy/codeEditor.js" as string)) as typeof import("./lazy/codeEditor");
    ensureMonacoCss();
    return m.createSqlEditor(editorHost, initial, onRun, effectiveTheme());
  } catch {
    const box = h("textarea", { "aria-label": "SQL query", spellcheck: "false", class: "mono" });
    box.value = initial;
    box.addEventListener("keydown", (e) => { if (e.ctrlKey && e.key === "Enter") onRun(); });
    editorHost.append(box);
    return {
      value: () => box.value,
      setValue: (text) => { box.value = text; },
      focus: () => box.focus(),
      setTheme: () => undefined,
      setNames: () => undefined,
      dispose: () => box.remove(),
    };
  }
}

/** POST the tray's query; the tray says Running…, then the rows built or the server's reason. */
async function build(tray: Tray, name: string, replace: boolean, source: Source = { connection: "", dataset: "" }): Promise<Built | null> {
  const sql = tray.editor.value().trim();
  if (!sql) return null;
  tray.busy(true);
  try {
    const built = source.connection
      ? await api<Built>(`/datasets/${encodeURIComponent(name)}/connection-query`, "POST", { connection: source.connection, sql, replace, ...(source.dataset ? { dataset: source.dataset } : {}) })
      : await api<Built>(`/datasets/${encodeURIComponent(name)}/query`, "POST", { sql, replace });
    tray.report(`${rowsText(built.rows)} in ${built.dataset} (version ${built.version}).${readsText(built)}`);
    offerRefresh(built);
    return built;
  } catch (e) {
    tray.report((e as Error).message, true);
    return null;
  } finally {
    tray.busy(false);
  }
}

// ===== names: the open tables, for the first query, the hint and autocomplete =====

function openTables(): string[] {
  return [...new Set(gridList().map((g) => contextOf(g.id)?.dataset).filter((d): d is string => !!d))];
}

/** A new draft starts on the first open table. */
function firstQuery(): string {
  const first = openTables()[0];
  return first ? `SELECT *\nFROM ${/^[A-Za-z_][A-Za-z0-9_]*$/.test(first) ? first : `"${first}"`}` : "";
}

/** `own`: a built table's own name, which its query can't read. */
function hint(own?: string): string {
  const tables = openTables().filter((t) => t !== own);
  return tables.length
    ? `Tables: ${tables.join(", ")}`
    : "No tables open";
}

/** Autocomplete: every dataset's name, and the columns of the open tabs as they show them. */
async function refreshNames(editor: SqlEditor): Promise<void> {
  try {
    const { datasets } = await api<{ datasets: { name: string }[] }>("/datasets");
    const open = gridList().map((g) => contextOf(g.id)).filter((c): c is Context => !!c);
    // A tab never opened has no description yet; load it (nothing redraws: it isn't active).
    await Promise.all(open.filter((c) => !c.state.info).map((c) => c.state.load()));
    const columns = new Set(open.flatMap((c) => (c.state.info?.columns ?? []).map((column) => column.name)));
    editor.setNames([...columns], datasets.map((d) => d.name));
  } catch {
    // Autocomplete is a convenience; the query runs without it.
  }
}

function rowsText(rows: number): string {
  return `${formatCount(rows)} ${rows === 1 ? "row" : "rows"}`;
}

/** Monaco's stylesheet, loaded once, the first time an editor is shown. */
function ensureMonacoCss(): void {
  if (document.querySelector('link[href="/static/build/lazy/codeEditor.css"]')) return;
  document.head.append(h("link", { rel: "stylesheet", href: "/static/build/lazy/codeEditor.css" }));
}
