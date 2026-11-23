/**
 * workbenchNotebookState.ts: a notebook's state as one record (`Notebook`), and the small things every part
 * of it asks: which cell has a number, a table's cell and its state, the selection, "the document changed",
 * the connection marks, a cell's label. Pulled out of workbenchNotebook.ts's notebookView (the craft review
 * of 2026-11-22, refactor 8): what was the closure's shared variables is this record, handed to each part
 * (workbenchNotebook<Part>.ts) as its first argument. [VIEW]
 *
 * The parts are layered: a part imports the ones below it (state, text, tables, runs, edits, snippets,
 * errors, cell, keys) and reaches the ones above it only through `nb.act` (run a cell, make a cell), which
 * the view fills once.
 */
import { cellConnections, markConnections } from "./connectionColours";
import { namedConnections } from "./connectionSql";
import { h, icon } from "./dom";
import type { CodeEditor } from "./lazy/codeEditor";
import { type CellRoute, cellRoute } from "./modes";
import { cellData, runTime } from "./notebookCells";
import type { pythonCompleter } from "./workbenchCompletion";
import type { Fix } from "./workbenchErrors";
import { type DesignPane, htmlNames, type HtmlRun, type HtmlState } from "./workbenchHtml";
import type { Kernel } from "./workbenchKernel";
import type { ErrorHooks, Output, OutputArea } from "./workbenchOutputs";
import { type RunRecord, type TableInfo, type TableLine, type TableState, tableState, type UsesForm } from "./workbenchTables";

export type CellKind = "code" | "sql" | "dax" | "html" | "markdown" | "typescript" | "tsx";
export interface CellData {
  kind: CellKind;
  source: string;
  connection: string | null;
  outputs: Output[];
  execution_count: number | null;
  /** The cell's own number: never changes, never reused (not the run count). */
  number?: number | null;
  /** Its part in the Tables group: "tables" and "table" (headings), "maker", "imports",
   *  "transformations" (a table's read-only cell); "" for a cell of the user's own. */
  role?: string;
  table?: string | null;
  grouped?: boolean;
  /** A transformations cell's steps as the grid holds them. */
  steps?: unknown[] | null;
  /** An HTML cell's pane, or a live Python cell's, in pixels (null: the usual height). */
  height?: number | null;
  /** A Python cell that calls Streamlit, by the server's word when the file was opened: shown live. */
  live?: boolean;
  /** The cell's own name (docs/ideas.md, named cells): a label; its number stays its identity. */
  name?: string | null;
}

/** An HTML cell, with its state: for the agent. */
export interface HtmlReport {
  /** The cell's own number. */
  number: number | null;
  /** A notebook cell's place, from 0 (a script: its marker's line). */
  index: number;
  html: string;
  /** The names it asks to have filled. */
  names: string[];
  state: HtmlState["kind"];
  label: string;
  /** The pane's saved height (null: the design's own). */
  height: number | null;
  /** What the design shows instead of a name's value, and why. */
  notes: string[];
}

/** A table of the notebook, with its cell's state: for the folded lines and the agent. */
export interface TableReport extends TableLine {
  state: TableState["kind"];
  label: string;
}

export interface Cell extends Omit<CellData, "outputs" | "number" | "role" | "table" | "grouped" | "steps" | "height" | "name"> {
  /** Its own name (null: none). */
  name: string | null;
  /** The head's name, typed in place (a heading and a table's cell have none). */
  nameButton: HTMLInputElement | null;
  number: number;
  role: string;
  table: string | null;
  grouped: boolean;
  steps: unknown[] | null;
  /** A heading's line (the Tables group's, a table's). */
  bar: HTMLElement | null;
  /** A table cell's state: "Out of date · last run 10:42". */
  status: HTMLElement | null;
  /** A word about the cell's part: "makes orders". */
  part: HTMLElement;
  element: HTMLElement;
  editor: CodeEditor | null;
  area: OutputArea;
  /** A Markdown cell drawn as text. */
  view: HTMLElement;
  /** A Markdown cell's line above its text, when it has names: its state and Run (empty when current). */
  textBar: { element: HTMLElement; status: HTMLElement; run: HTMLElement };
  count: HTMLElement;
  kindPicker: HTMLSelectElement;
  connectionPicker: HTMLSelectElement;
  /** Give it the keyboard once its editor exists, unless the focus went elsewhere meanwhile. */
  wantsFocus: boolean;
  /** An HTML cell's design (null: a heading). */
  design: DesignPane | null;
  editorHost: HTMLElement;
  /** What an HTML cell's last run gave. */
  htmlRun: HtmlRun | undefined;
  /** What the design left out, and the names the kernel does not hold. */
  htmlNotes: string[];
  /** Counts the design's drawings: an older one that answers late is dropped. */
  drawn: number;
  /** Notebook mode: "edited" or "out of date" in its head (empty when current). */
  flow: HTMLElement;
  /** Its code when it last ran in this kernel, and when (the order of runs). */
  ranSource: string | null;
  runOrder: number | null;
}

/** A cell as Notebook mode's run order reads it. */
export interface FlowCell {
  number: number;
  kind: CellKind;
  source: string;
  ran: string | null;
  order: number | null;
  name: string | null;
}

/** What Undo puts back. */
export type Undo = { kind: "delete"; data: CellData; at: number; filler: Cell | null } | { kind: "move"; cell: Cell; from: number };

export const LANGUAGE: Record<CellKind, "python" | "sql" | "dax" | "markdown" | "html" | "typescript" | "tsx"> = { code: "python", sql: "sql", dax: "dax", markdown: "markdown", html: "html", typescript: "typescript", tsx: "tsx" };
export const KIND_NAMES: Record<CellKind, string> = { code: "Python", sql: "SQL", dax: "DAX", html: "HTML", markdown: "Markdown", typescript: "TypeScript", tsx: "TSX" };
/** A new notebook's first Python cell, empty: how it works, in one faint line (gone at the first key). */
export const FIRST_HINT = "Shift+Enter runs · %%sql for DuckDB SQL · drag a table here";
export const KINDS: CellKind[] = ["code", "sql", "dax", "html", "markdown", "typescript", "tsx"];
/** Kinds another kernel runs, offered only where the open project's mode names a route for them (modes.ts). */
export const ROUTED: CellKind[] = ["typescript", "tsx"];
/** The kinds a cell's picker offers: the Python kernel's, the mode's own, and the cell's own kind. */
export const offeredKinds = (own: CellKind): CellKind[] => KINDS.filter((k) => !ROUTED.includes(k) || k === own || cellRoute(k) !== null);
/** Where a cell runs when not in the Python kernel: a TypeScript or TSX cell by its kind, a DuckDB SQL cell
 *  (no connection of its own) where the mode runs SQL in its kernel; null: the Python kernel. */
export const routeOf = (cell: { kind: CellKind; connection: string | null }): CellRoute | null =>
  cell.kind === "sql" ? (cell.connection ? null : cellRoute("sql")) : ROUTED.includes(cell.kind) ? cellRoute(cell.kind) : null;
/** A Markdown or HTML cell: it goes on a Streamlit page as text (docs/ideas.md, text cells on the canvas). */
export const isText = (kind: CellKind): boolean => kind === "markdown" || kind === "html";
/** A cell whose `{{ name }}` values are filled from the kernel: an HTML cell, or a Markdown cell with names. */
export const filledCell = (cell: { kind: CellKind; source: string; editor: CodeEditor | null }): boolean =>
  cell.kind === "html" || (cell.kind === "markdown" && htmlNames(cell.editor ? cell.editor.value() : cell.source).length > 0);
// A DAX cell names its dataset's own tables, never the kernel's: it gets no uses line (a `-- uses` one it has goes).
export const usesForm = (kind: CellKind): UsesForm => (kind === "sql" || kind === "dax" ? "sql" : kind === "html" ? "html" : "python");
export const empty = (kind: CellKind = "code", connection: string | null = null): CellData => ({ kind, source: "", connection, outputs: [], execution_count: null });


/** A run's time beside its count (feel-b, 2026-11-19): "Running… 3 s" once it has taken a second, then the
 *  time it took. The returned function ends it. The cell keeps its head's name box shown from then on. */
export function timeRun(cell: { count: HTMLElement; element: HTMLElement }): () => void {
  let label = cell.count.parentElement?.querySelector<HTMLElement>(":scope > .wb-elapsed") ?? null;
  if (!label) {
    label = h("span", { class: "wb-elapsed", role: "status" });
    cell.count.after(label);
  }
  const shown = label;
  const started = performance.now();
  shown.textContent = "";
  shown.classList.add("running");
  const timer = window.setInterval(() => {
    const ms = performance.now() - started;
    if (ms >= 1000) shown.textContent = `Running… ${Math.floor(ms / 1000)} s`;
  }, 250);
  return () => {
    window.clearInterval(timer);
    shown.classList.remove("running");
    shown.textContent = runTime(performance.now() - started);
    shown.title = `Ran at ${new Date().toLocaleTimeString()}`;
    cell.element.classList.add("has-run");
  };
}

/** What the page hands a notebook: where its cursor, its fixes and its tables go. */
export interface NotebookHooks {
  cursor?: (line: number, column: number) => void;
  help?: () => void;
  fix?: (fix: Fix) => boolean;
  openGrid?: (name: string) => void;
  openResult?: (count: number, name?: string) => void;
  /** The number the next new cell gets (from the file). */
  nextCell?: number;
  /** The cells came from a file or a reload: a table's cell says "Not run since opening". */
  opened?: boolean;
  /** Give a grid its saved steps back (a table opened again whose cell the file holds). */
  restoreSteps?: (grid: string, steps: unknown[]) => void;
  /** The tables' state changed (for the toolbar). */
  tablesChanged?: () => void;
  /** What a DAX cell runs on: each Power BI workspace's datasets, as `Finance/Sales model`. */
  datasets?: () => string[];
  /** Lineage: the overlay for the cell with this number. */
  lineage?: (number: number) => void;
  /** A cell ran (Notebook mode's run order follows). */
  ran?: () => void;
}

/** A notebook's state: what every part of it reads and writes. */
export interface Notebook {
  /** The cells' list on the page, and the cells in its order. */
  list: HTMLElement;
  cells: Cell[];
  kernel: Kernel;
  hooks: NotebookHooks;
  connections: () => string[];
  theme: () => string;
  dark: () => boolean;
  /** The document changed (the page's unsaved mark). */
  changed: () => void;
  /** Python's completion from the kernel, with the app's names. */
  python: ReturnType<typeof pythonCompleter>;
  /** This notebook's key for the ghost text's provider (inlineCompletion.ts): one a window, made up. */
  inlineKey: string;
  selected: Cell | null;
  undos: Undo[];
  /** The first D of D D, and when. */
  pendingD: number;
  /** The kernel's runs from this notebook, in order (Notebook mode's run order). */
  runs: number;
  presenting: boolean;
  /** A DuckDB SQL cell's connections, in its head. */
  namedHosts: WeakMap<Cell, HTMLElement>;
  // ----- numbers, tables
  nextNumber: number;
  tableInfos: TableInfo[];
  tableLines: TableLine[];
  records: Map<string, RunRecord>;
  restored: Set<string>;
  /** The tables whose cell the file (or a reload) brought. */
  cameWithFile: Set<string>;
  /** The group opens unfolded (2026-11-16: the table is the first thing seen). */
  groupFolded: boolean;
  /** The tables opened. */
  unfolded: Set<string>;
  /** Each table opens unfolded once; the user's fold then stays. */
  seenTables: Set<string>;
  /** The tables whose cell ran by itself (once each). */
  autoRan: Set<string>;
  /** Counts every change: an arrangement worked out for an older one is dropped. */
  version: number;
  asked: number;
  quiet: number | null;
  building: boolean;
  disposed: boolean;
  // ----- the connection marks, the HTML cells' marks, each cell's error hooks
  marking: number;
  markTimer: number | undefined;
  marksTimer: number | null;
  kept: WeakMap<Cell, ErrorHooks>;
  /** What a part asks of the parts above it. */
  act: {
    /** Run a cell, whatever its kind (false: it failed). */
    run: (cell: Cell) => Promise<boolean>;
    /** Make a cell from its data and put it at `at`. */
    make: (data: CellData, at: number) => Cell;
  };
}

export const datasets = (nb: Notebook): string[] => nb.hooks.datasets?.() ?? [];
/** The sources a cell of this kind picks from. */
export const sources = (nb: Notebook, kind: CellKind): string[] => (kind === "dax" ? datasets(nb) : nb.connections());

export const indexOf = (nb: Notebook, cell: Cell): number => nb.cells.indexOf(cell);

export function drawNamed(nb: Notebook, cell: Cell): void {
  const host = nb.namedHosts.get(cell);
  if (!host) return;
  const names = cell.kind === "sql" && !cell.connection ? namedConnections(sourceOf(cell), nb.connections()) : [];
  host.replaceChildren(...names.map((n) => h("span", { class: "wb-sql-conn", "data-connection": n, title: n }, icon("plug"), n)));
}

export const sourceOf = (c: Cell): string => (c.editor ? c.editor.value() : c.source);
export const byNumber = (nb: Notebook, number: number): Cell | undefined => nb.cells.find((c) => c.number === number);
export const infoOf = (nb: Notebook, table: string | null): TableInfo | undefined => nb.tableInfos.find((t) => t.name === table);
export const lineOf = (nb: Notebook, table: string | null): TableLine | undefined => nb.tableLines.find((t) => t.name === table);
export const stateOf = (nb: Notebook, cell: Cell): TableState => tableState(sourceOf(cell), cell.table ? nb.records.get(cell.table) : undefined);
export const tableCell = (nb: Notebook, table: string | null): Cell | undefined => nb.cells.find((c) => c.role === "transformations" && c.table === table);
/** Every change goes through here: the document is changed, and what the server works out next is
 *  for this text. */
export function edited(nb: Notebook): void {
  nb.version++;
  nb.changed();
  connectionsSoon(nb);
}

export async function markConnectionsNow(nb: Notebook): Promise<void> {
  const mine = ++nb.marking;
  const these = nb.cells.filter((c) => !c.bar && (c.kind === "code" || c.kind === "sql" || c.kind === "dax"));
  const found = await cellConnections(these.map((c) => ({ kind: c.kind, source: c.editor?.value() ?? c.source, connection: c.connection })));
  if (mine !== nb.marking) return;
  these.forEach((c, i) => {
    c.element.classList.add("conn-cell");
    markConnections(c.element, found[i] ?? []);
  });
  for (const c of nb.cells) if (!these.includes(c)) markConnections(c.element, []);
}
export function connectionsSoon(nb: Notebook): void {
  window.clearTimeout(nb.markTimer);
  nb.markTimer = window.setTimeout(() => void markConnectionsNow(nb), 400);
}

export const label = (nb: Notebook, cell: Cell): string => `Cell ${indexOf(nb, cell) + 1} of ${nb.cells.length}, ${KIND_NAMES[cell.kind]}`;
export function relabel(nb: Notebook): void {
  for (const c of nb.cells) c.element.setAttribute("aria-label", label(nb, c));
  connectionsSoon(nb);
}

export function select(nb: Notebook, cell: Cell): void {
  if (nb.selected && nb.selected !== cell) nb.selected.element.classList.remove("selected");
  nb.selected = cell;
  cell.element.classList.add("selected");
}

/** The keyboard into a cell's editor: now if it exists, else as soon as it does. A user who clicked
 *  somewhere else in the meantime keeps their focus (a delayed focus once split typed text between
 *  two cells). */
export function focusEditor(cell: Cell): void {
  if (!cell.editor) {
    cell.wantsFocus = true;
    const asked = document.activeElement;
    const moved = (): void => {
      if (document.activeElement !== asked) cell.wantsFocus = false;
    };
    document.addEventListener("focusin", moved, { once: true });
    return;
  }
  if (cell.wantsFocus || !cell.editor.hasFocus()) {
    cell.wantsFocus = false;
    cell.editor.focus();
  }
}

export function toCommandMode(nb: Notebook, cell: Cell): void {
  select(nb, cell);
  cell.element.focus();
}

export const dataOf = (c: Cell): CellData => cellData(c, sourceOf(c)); // notebookCells.ts: a cell as it is saved

