/**
 * workbenchNotebook.ts: a notebook in the Workbench: cells of Python, SQL on a connection, DAX on a
 * Power BI workspace's dataset, HTML or Markdown, run in the document's IPython kernel. [WIRE]
 *
 *   [CELL]     its kind (Python, SQL, DAX, HTML, Markdown); a SQL cell's connection, a DAX cell's
 *              dataset (`Finance/Sales model`: only Power BI workspaces' datasets); Run; More: run above, run
 *              below, insert above or below, duplicate, clear or hide its output; move up and down; delete
 *   [EDIT]     Shift+Enter runs and goes to the next cell (a new one after the last); Ctrl+Enter runs in
 *              place; Escape leaves the editor for command mode; a Markdown cell shows as text until
 *              double-clicked (or Enter)
 *   [COMMAND]  Jupyter's keys on the selected cell: Enter edits; A and B insert above and below; D D
 *              deletes; Y, M, S, X and H make it Python, Markdown, SQL, DAX or HTML; J and K (or Down and
 *              Up) move the selection; Z undoes a delete or move; C copies the cell and V pastes it
 *              below; Shift+Enter and Ctrl+Enter run
 *   [OUTPUTS]  as the run streams them (workbenchOutputs.ts), kept with the cell and saved with it; a
 *              box when the code asks for a line (input()); a word when the kernel stopped or restarted
 *   [ERRORS]   the error panel in the cell's output (workbenchErrors.ts); the failing expression marked
 *              in its cell (and the calls that led there in theirs), with a hover card and Ctrl+. fixes;
 *              a frame or "In your code" goes to its cell and line; "Run the cell that makes x" finds it
 *
 * A SQL cell runs as `%%sql <connection>` (client/sql_cell.py) in the kernel: its connection's own SQL,
 * or DuckDB over a file's tables. A DAX cell (docs/ideas.md, 2026-11-15) runs as `%%dax <connection>/<dataset>`
 * the same way; a SQL cell saved on a Power BI connection before DAX cells opens as a DAX cell.
 *
 *   [NUMBERS]  every cell has a number that never changes (#7 in its head; not the run count): given
 *              when the cell is made, never reused; `@cell7` in a comment is a link to it
 *   [TABLES]   every table open in the grid has a read-only cell here (docs/ideas.md, 2026-11-14): its
 *              transformations, which follow the grid's steps. All tables sit at the top in a Tables
 *              group, each with the user's cell that makes it; a table folds to one line and so does
 *              the group. A table's cell opens unfolded, and one the app wrote whole (no cell of the
 *              user's makes its table) runs by itself once, its table as its output (the owner,
 *              2026-11-16: "Shouldnt cell 1 have the table inside of it?"): the kernel starts for it.
 *              The output is not saved with the file (it is drawn again on opening). A changed cell
 *              turns yellow (Out of date · Run); a user's cell never runs by itself
 *   [USES]     one of the user's cells that names a table starts with `# uses orders @cell3`, kept by
 *              the app as they type
 *   [HTML]     an HTML cell (docs/ideas.md, 2026-11-14; workbenchHtml.ts) has two faces: its HTML in the
 *              editor while it is being edited, the design when it is not. It draws by itself when the
 *              editor is left; `{{ name }}` is filled from the kernel when the cell runs, and such a
 *              cell turns yellow (Out of date · Run) when its HTML or a variable it names changes. A
 *              click inside the design goes to the design (its buttons work): the cell's head, its Edit
 *              button or Enter open the HTML
 *   [COPY]     a cell is copied (C, or More: Copy) and pasted in any notebook (V); dragged by its number
 *              or its head, it drops its `@cell` link as text. No live Streamlit cells: app notebooks and
 *              their canvases were replaced by widgets on the Canvas (2026-11-21)
 *   [MODE]     Notebook mode (2026-11-15): each cell remembers what it last ran and when, so the page
 *              marks it "edited" or "out of date" (a name it reads was made again: domain/notebook_
 *              flow.py); the selected cell offers Run up to here; Present shows the notebook as a
 *              document (its text and outputs, no code)
 *
 * ROUTING: POST /workbench/tables/arrange (the rules are the server's: domain/table_cells.py)
 */
import { cellData, drawn, hasSource, isApp, isHeading, runTime, snippetLanguage, twoFaced } from "./notebookCells";
import { inlineSource } from "./inlineCompletion";
import { cellConnections, markConnections, onConnectionColours } from "./connectionColours";
import { api } from "./api";
import { button, clear, h, icon, type MenuItem, showMenu, toast } from "./dom";
import { busy } from "./loading";
import type { CodeEditor } from "./lazy/codeEditor";
import { renderMarkdown } from "./markdown";
import { draggedSnippet, type FilledSnippet, fillSnippet, pickSnippet, refusal, SNIPPET_CELL, SNIPPET_DRAG, type SnippetLanguage } from "./starters";
import { codeItem, currentDocument, sendToAgent } from "./workbenchAgent";
import { type CellRoute, cellRoute } from "./modes";
import { openRoutedTable, previewRouted, routedTypes, runRouted } from "./routedCells";
import { namedConnections } from "./connectionSql";
import { datasetsWanted, daxCompleter, isWorkspace, pythonCompleter, sqlCompleter } from "./workbenchCompletion";
import { pythonIntel, showProblems } from "./workbenchIntel";
import { type ErrorDetail, type Fix, type Frame, problemsFor, sqlProblems, yourFrame } from "./workbenchErrors";
import { type Kernel, runInto } from "./workbenchKernel";
import { changedNames, type DesignPane, designPane, fillHtml, fillMarkdown, htmlNames, type HtmlRun, htmlState, type HtmlState, runFromOutputs, runHtml } from "./workbenchHtml";
import { type ErrorHooks, type Output, type OutputArea, outputArea, resultName } from "./workbenchOutputs";
import { cleanName, copiedCell, copyCell, MAX_CELL_NAME } from "./cellClipboard";
import { type ArrangedCell, firstLine, groupLineText, noteParts, type RunRecord, type TableInfo, type TableLine, tableLineText, type TableState, tableState, type UsesForm, withUses } from "./workbenchTables";
import { errorHere, errorNote } from "./errorNote";
import { loadDiagrams, loadEditors } from "./lazyLoad";

/** A SQL cell's first line as the kernel runs it (domain/notebooks.py sql_line). */
export function sqlLine(connection: string | null): string {
  if (!connection) return "%%sql";
  return /\s/.test(connection) ? `%%sql '${connection.replace(/'/g, "'\"'\"'")}'` : `%%sql ${connection}`;
}

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

interface Cell extends Omit<CellData, "outputs" | "number" | "role" | "table" | "grouped" | "steps" | "height" | "name"> {
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
type Undo = { kind: "delete"; data: CellData; at: number; filler: Cell | null } | { kind: "move"; cell: Cell; from: number };

const LANGUAGE: Record<CellKind, "python" | "sql" | "dax" | "markdown" | "html" | "typescript" | "tsx"> = { code: "python", sql: "sql", dax: "dax", markdown: "markdown", html: "html", typescript: "typescript", tsx: "tsx" };
const KIND_NAMES: Record<CellKind, string> = { code: "Python", sql: "SQL", dax: "DAX", html: "HTML", markdown: "Markdown", typescript: "TypeScript", tsx: "TSX" };
/** A new notebook's first Python cell, empty: how it works, in one faint line (gone at the first key). */
const FIRST_HINT = "Shift+Enter runs · %%sql for DuckDB SQL · drag a table here";
const KINDS: CellKind[] = ["code", "sql", "dax", "html", "markdown", "typescript", "tsx"];
/** Kinds another kernel runs, offered only where the open project's mode names a route for them (modes.ts). */
const ROUTED: CellKind[] = ["typescript", "tsx"];
/** The kinds a cell's picker offers: the Python kernel's, the mode's own, and the cell's own kind. */
const offeredKinds = (own: CellKind): CellKind[] => KINDS.filter((k) => !ROUTED.includes(k) || k === own || cellRoute(k) !== null);
/** Where a cell runs when not in the Python kernel: a TypeScript or TSX cell by its kind, a DuckDB SQL cell
 *  (no connection of its own) where the mode runs SQL in its kernel; null: the Python kernel. */
const routeOf = (cell: { kind: CellKind; connection: string | null }): CellRoute | null =>
  cell.kind === "sql" ? (cell.connection ? null : cellRoute("sql")) : ROUTED.includes(cell.kind) ? cellRoute(cell.kind) : null;
/** A Markdown or HTML cell: it goes on a Streamlit page as text (docs/ideas.md, text cells on the canvas). */
const isText = (kind: CellKind): boolean => kind === "markdown" || kind === "html";
/** A cell whose `{{ name }}` values are filled from the kernel: an HTML cell, or a Markdown cell with names. */
const filledCell = (cell: { kind: CellKind; source: string; editor: CodeEditor | null }): boolean =>
  cell.kind === "html" || (cell.kind === "markdown" && htmlNames(cell.editor ? cell.editor.value() : cell.source).length > 0);
// A DAX cell names its dataset's own tables, never the kernel's: it gets no uses line (a `-- uses` one it has goes).
const usesForm = (kind: CellKind): UsesForm => (kind === "sql" || kind === "dax" ? "sql" : kind === "html" ? "html" : "python");
const empty = (kind: CellKind = "code", connection: string | null = null): CellData => ({ kind, source: "", connection, outputs: [], execution_count: null });


/** A run's time beside its count (feel-b, 2026-11-19): "Running… 3 s" once it has taken a second, then the
 *  time it took. The returned function ends it. The cell keeps its head's name box shown from then on. */
function timeRun(cell: { count: HTMLElement; element: HTMLElement }): () => void {
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

export interface NotebookView {
  element: HTMLElement;
  /** Check every cell again (the lint: Ruff came in). */
  relint: () => void;
  cells: () => CellData[];
  /** Add a cell after the selected one (`first`: at the top). */
  add: (kind: CellKind, source?: string, first?: boolean) => void;
  /** Add a cell above or below the selected one, and select it. */
  insert: (where: "above" | "below", kind?: CellKind, source?: string) => void;
  runAll: () => Promise<void>;
  /** Run the selected cell (or the one at `index`, from 0). */
  runCell: (index?: number) => Promise<boolean>;
  runAbove: () => Promise<void>;
  runBelow: () => Promise<void>;
  selected: () => number;
  select: (index: number, edit?: boolean) => void;
  remove: (index?: number) => void;
  move: (by: -1 | 1) => void;
  setKind: (kind: CellKind) => void;
  /** Put the selected SQL cell on a connection, or the selected DAX cell on a dataset. */
  setConnection: (name: string) => void;
  duplicate: () => void;
  clearOutput: (index?: number) => void;
  clearAll: () => void;
  toggleOutput: () => void;
  /** Leave the editor for command mode (the keys act on the cell). */
  commandMode: () => void;
  /** Put back the last deleted or moved cell (false: nothing to undo). */
  undo: () => boolean;
  /** The help for the name at the cursor in the selected cell. */
  helpAtCursor: () => Promise<string>;
  setTheme: (theme: string) => void;
  /** The open tables that belong to this notebook: their cells follow, the Tables group is arranged. */
  setTables: (tables: TableInfo[]) => void;
  /** It holds this table's cell (from its file, say). */
  holdsTable: (name: string) => boolean;
  /** Its tables and each cell's state. */
  tables: () => TableReport[];
  /** Run a table's cell (false: it failed, or there is no such table). */
  runTable: (name: string) => Promise<boolean>;
  /** Run every table's cell that is not up to date; how many ran. */
  runOutOfDate: () => Promise<number>;
  /** Go to the cell with this number (false: there is none); `line`: that line of its code, from 1. */
  goTo: (number: number, line?: number | null) => boolean;
  /** The number the next new cell gets (saved with the file, so none is ever reused). */
  nextCell: () => number;
  /** Fold or unfold the Tables group (or one table of it). */
  foldTables: (folded: boolean, table?: string) => void;
  /** A table was renamed in the grid. */
  renameTable: (from: string, to: string) => void;
  /** Its HTML cells and each one's state. */
  htmlCells: () => HtmlReport[];
  /** Run an HTML cell by its number: fill its names from the kernel and draw it (without a number:
   *  every one that is not up to date). The cells as they are after. */
  runHtml: (number?: number) => Promise<HtmlReport[]>;
  /** Size an HTML cell's pane (null: the design's own height). */
  resizeHtml: (number: number, height: number | null) => void;
  /** Open the selected cell's code (an HTML or Markdown cell that shows as drawn). */
  editSelected: () => void;
  /** Copy a cell (the selected one), for a paste in any notebook (C). */
  copy: (number?: number) => { cell: number; document: string | null } | null;
  /** Paste the copied cell below the selected one (V). False: nothing was copied. */
  paste: () => boolean;
  /** Name a cell ("" takes its name away); without a number, the selected cell. */
  nameCell: (number: number | undefined, name: string) => { cell: number; name: string | null };
  /** Type a name for the selected cell in its head (Enter keeps it, Escape leaves it). */
  editName: () => void;
  /** The place (from 0) of the cell with this number, or -1. */
  indexOfNumber: (number: number) => number;
  /** Put this text in the user's cell numbered `number` (a thin cell's move to data.ipynb). */
  setSource: (number: number, source: string) => void;
  /** The same as a user's edit: only the lines that differ change, and the editor's Undo takes it back
   *  (the canvas's property pane writing a default, a key, a cache setting or a handler). */
  editSource: (number: number, source: string) => void;
  /** The text of the user's cell numbered `number` (null: there is none). */
  sourceOf: (number: number) => string | null;
  /** A SQL or DAX cell of the user's (by its number) run on another connection (a swap's code). */
  setCellConnection: (number: number, name: string) => void;
  /** A new named Python cell at the end (data.ipynb's cell for a moved model); its number. */
  appendNamed: (source: string, name: string, kind?: CellKind, connection?: string | null) => number;
  /** Insert a snippet, filled with `values` (the agent's): into the cell numbered `number`, else the
   *  selected one of its kind, else a new one. Which cell took it. */
  insertSnippet: (name: string, values: Record<string, unknown>, number?: number) => Promise<{ cell: number; kind: CellKind; name: string | null }>;
  /** The palette's Insert a snippet…: pick one for the selected cell's language, fill its form. */
  insertSnippetHere: () => void;
  /** The selected cell's own number (null: none). */
  selectedNumber: () => number | null;
  /** The Data Explorer's Insert: a result's code at the selected cell's cursor, as the cell's language
   *  writes it (a SQL cell's SQL, a Python cell's Python); else a new cell below of the kind it has code
   *  for. The cell it went into. */
  insertCode: (insert: { sql?: string; python?: string }) => { cell: number; kind: CellKind };
  /** The document closed: free its editors, its designs' frames and its window listener. */
  dispose: () => void;
  // ----- Notebook mode
  /** The user's cells as the run order reads them: what each last ran, and when. */
  flowCells: () => FlowCell[];
  /** Each cell's state from the run order: "edited", "outOfDate" (with the names), else nothing shown. */
  markFlow: (states: { number: number; state: string; because: string[] }[]) => void;
  /** Run every cell of the user's from the top to this one (default: the selected one). */
  runUpTo: (number?: number) => Promise<void>;
  /** Present: the notebook as a document (its text and outputs, no code). */
  present: (on?: boolean) => boolean;
}


// Mermaid (lazy/diagram.ts), loaded the first time a Markdown cell holds a ```mermaid block.

export function notebookView(
  initial: CellData[],
  kernel: Kernel,
  connections: () => string[],
  theme: () => string,
  changed: () => void,
  blades: () => string[] = () => [],
  codeNames: () => { name: string; connection: string; kind: string }[] = () => [],
  hooks: {
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
  } = {},
): NotebookView {
  const datasets = (): string[] => hooks.datasets?.() ?? [];
  /** The sources a cell of this kind picks from. */
  const sources = (kind: CellKind): string[] => (kind === "dax" ? datasets() : connections());
  const python = pythonCompleter(kernel, () => ({ connections: connections(), blades: blades(), codeNames: codeNames() }));
  const list = h("div", { class: "wb-cells", role: "list", "aria-label": "Cells" });
  const cells: Cell[] = [];
  // This notebook's key for the ghost text's provider (inlineCompletion.ts): one a window, made up.
  const inlineKey = `nb-${Math.random().toString(36).slice(2, 10)}`;
  let selected: Cell | null = null;
  const undos: Undo[] = [];
  let pendingD = 0; // the first D of D D, and when
  let runs = 0; // the kernel's runs from this notebook, in order (Notebook mode's run order)
  let presenting = false;
  const dark = (): boolean => theme().endsWith("dark");
  const indexOf = (cell: Cell): number => cells.indexOf(cell);
  // ----- a DuckDB SQL cell's connections, in its head
  const namedHosts = new WeakMap<Cell, HTMLElement>();
  const drawNamed = (cell: Cell): void => {
    const host = namedHosts.get(cell);
    if (!host) return;
    const names = cell.kind === "sql" && !cell.connection ? namedConnections(sourceOf(cell), connections()) : [];
    host.replaceChildren(...names.map((n) => h("span", { class: "wb-sql-conn", "data-connection": n, title: n }, icon("plug"), n)));
  };
  // ----- numbers, tables
  let nextNumber = Math.max(hooks.nextCell ?? 1, 1 + Math.max(0, ...initial.map((c) => c.number ?? 0)));
  let tableInfos: TableInfo[] = [];
  let tableLines: TableLine[] = [];
  const records = new Map<string, RunRecord>();
  const restored = new Set<string>();
  const cameWithFile = new Set<string>(); // the tables whose cell the file (or a reload) brought
  let groupFolded = false; // the group opens unfolded (2026-11-16: the table is the first thing seen)
  const unfolded = new Set<string>(); // the tables opened
  const seenTables = new Set<string>(); // each table opens unfolded once; the user's fold then stays
  const autoRan = new Set<string>(); // the tables whose cell ran by itself (once each)
  let version = 0; // counts every change: an arrangement worked out for an older one is dropped
  let asked = 0;
  let quiet: number | null = null;
  let building = true;
  let disposed = false;
  const sourceOf = (c: Cell): string => (c.editor ? c.editor.value() : c.source);
  const byNumber = (number: number): Cell | undefined => cells.find((c) => c.number === number);
  const infoOf = (table: string | null): TableInfo | undefined => tableInfos.find((t) => t.name === table);
  const lineOf = (table: string | null): TableLine | undefined => tableLines.find((t) => t.name === table);
  const stateOf = (cell: Cell): TableState => tableState(sourceOf(cell), cell.table ? records.get(cell.table) : undefined);
  const tableCell = (table: string | null): Cell | undefined => cells.find((c) => c.role === "transformations" && c.table === table);
  /** Every change goes through here: the document is changed, and what the server works out next is
   *  for this text. */
  const edited = (): void => {
    version++;
    changed();
    connectionsSoon();
  };

  // Connection colours (connectionColours.ts): a cell that names a connection (%%sql, %%dax, sab.sql,
  // sab.read, sab.dax, sab.blade, sab.connection; a table's read-only cell by its load) wears its colour,
  // two connections two marks. The server reads the cells (ast); nothing runs.
  let marking = 0;
  let markTimer: number | undefined;
  const markConnectionsNow = async (): Promise<void> => {
    const mine = ++marking;
    const these = cells.filter((c) => !c.bar && (c.kind === "code" || c.kind === "sql" || c.kind === "dax"));
    const found = await cellConnections(these.map((c) => ({ kind: c.kind, source: c.editor?.value() ?? c.source, connection: c.connection })));
    if (mine !== marking) return;
    these.forEach((c, i) => {
      c.element.classList.add("conn-cell");
      markConnections(c.element, found[i] ?? []);
    });
    for (const c of cells) if (!these.includes(c)) markConnections(c.element, []);
  };
  const connectionsSoon = (): void => {
    window.clearTimeout(markTimer);
    markTimer = window.setTimeout(() => void markConnectionsNow(), 400);
  };
  onConnectionColours(() => {
    if (list.isConnected) connectionsSoon();
  });

  const label = (cell: Cell): string => `Cell ${indexOf(cell) + 1} of ${cells.length}, ${KIND_NAMES[cell.kind]}`;
  const relabel = (): void => {
    for (const c of cells) c.element.setAttribute("aria-label", label(c));
    connectionsSoon();
  };

  const select = (cell: Cell): void => {
    if (selected && selected !== cell) selected.element.classList.remove("selected");
    selected = cell;
    cell.element.classList.add("selected");
  };

  /** A Markdown cell as text. With `{{ name }}` (docs/ideas.md, text cells on the canvas, 2026-11-15)
   *  its names are filled from its last run's values by the server's rules (a value is always text),
   *  and the line above says when it is out of date, as an HTML cell's design does. */
  const showMarkdown = (cell: Cell): void => {
    const text = cell.editor?.value() ?? cell.source;
    cell.element.classList.add("rendered");
    if (!htmlNames(text).length) {
      cell.htmlNotes = [];
      cell.view.replaceChildren(renderMarkdown(text));
      drawDiagrams(cell);
      return;
    }
    void drawMarkdown(cell, text);
  };

  /** A Markdown cell's ```mermaid blocks drawn as diagrams (the owner, 2026-11-15), by the app's own
   *  Mermaid (loaded when first needed, strict, its drawing cleaned: nothing from the internet). A
   *  broken diagram says why in its place. */
  const drawDiagrams = (cell: Cell): void => {
    for (const block of cell.view.querySelectorAll<HTMLElement>("pre.md-code[data-lang='mermaid']")) {
      const text = block.textContent ?? "";
      const host = h("div", { class: "md-mermaid", role: "img", "aria-label": "Diagram" });
      block.replaceWith(host);
      void loadDiagrams()
        .then((m) => m.drawDiagram(host, text, dark()))
        .catch((e: unknown) => host.replaceChildren(errorNote(e, { dismiss: false })));
    }
  };

  const drawMarkdown = async (cell: Cell, text: string): Promise<void> => {
    const mine = ++cell.drawn;
    let filled: { markdown: string; missing: string[]; notes: string[] };
    try {
      filled = await fillMarkdown(text, cell.htmlRun?.values ?? {});
    } catch {
      filled = { markdown: text, missing: [], notes: ["The server is away: the names show as written."] };
    }
    if (mine !== cell.drawn || cell.kind !== "markdown" || !cell.element.classList.contains("rendered")) return;
    cell.htmlNotes = [...filled.missing.map((n) => `{{ ${n} }} was not found in the kernel.`), ...filled.notes];
    const notes = cell.htmlNotes.length ? h("div", { class: "wb-design-notes hint" }, ...cell.htmlNotes.map((n) => h("div", {}, n))) : null;
    cell.view.replaceChildren(cell.textBar.element, renderMarkdown(filled.markdown), ...(notes ? [notes] : []));
    drawDiagrams(cell);
    drawMarkdownState(cell);
  };

  /** A Markdown cell's state line: only what needs the user (out of date, not run), with Run. */
  const drawMarkdownState = (cell: Cell): void => {
    const state = htmlState(sourceOf(cell), cell.htmlRun);
    cell.textBar.element.hidden = !state.label;
    cell.textBar.status.textContent = state.label;
    cell.textBar.status.className = `wb-design-state ${state.kind}`;
    cell.textBar.run.hidden = !state.runnable;
    cell.element.classList.toggle("stale", state.kind === "outOfDate");
  };

  const editMarkdown = (cell: Cell): void => {
    cell.element.classList.remove("rendered");
    cell.view.replaceChildren();
    setTimeout(() => cell.editor?.focus(), 0);
  };

  // ===== HTML cells: the design, its state, its run =====

  /** An HTML cell's HTML without the app's own first line (so that line never makes it out of date). */
  const htmlOf = (cell: Cell): string => withUses(sourceOf(cell), null, "html");
  const htmlStateOf = (cell: Cell): HtmlState => htmlState(htmlOf(cell), cell.htmlRun);

  const drawHtmlState = (cell: Cell): void => {
    if (cell.kind === "markdown") return drawMarkdownState(cell);
    if (!cell.design) return;
    const state = htmlStateOf(cell);
    cell.design.setState(state, cell.htmlNotes);
    cell.element.classList.toggle("stale", cell.kind === "html" && state.kind === "outOfDate");
  };

  /** Draw the design from the cell's HTML as it is now, its names filled with what its last run gave. */
  const drawDesign = async (cell: Cell): Promise<void> => {
    if (!cell.design) return;
    const html = sourceOf(cell);
    const mine = ++cell.drawn;
    let filled: { html: string; missing: string[]; notes: string[] };
    try {
      filled = await fillHtml(html, cell.htmlRun?.values ?? {});
    } catch {
      filled = { html, missing: [], notes: ["The server is away: the design shows as written."] }; // names unfilled
    }
    if (mine !== cell.drawn || cell.kind !== "html") return;
    cell.htmlNotes = [...filled.missing.map((n) => `{{ ${n} }} was not found in the kernel.`), ...filled.notes];
    cell.design.show(filled.html);
    drawHtmlState(cell);
  };

  const showDesign = (cell: Cell): void => {
    cell.element.classList.add("rendered");
    void drawDesign(cell);
  };

  const editHtml = (cell: Cell): void => {
    cell.element.classList.remove("rendered");
    // At once, so what is typed next goes into the HTML; again once the editor has its size.
    cell.editor?.layout();
    if (cell.editor) cell.editor.focus();
    else focusEditor(cell);
    setTimeout(() => cell.editor?.layout(), 0);
  };

  /** Run an HTML cell: plain HTML only draws; with names, each is read from the kernel's variables. A
   *  Markdown cell with names runs the same way (its values are an HTML cell's), and shows as text. */
  const runHtmlCell = async (cell: Cell): Promise<boolean> => {
    const html = cell.source;
    const face = (c: Cell): void => (c.kind === "markdown" ? showMarkdown(c) : showDesign(c));
    cell.area.set([]);
    if (!html.trim()) return true;
    if (!htmlNames(html).length) {
      face(cell);
      return true;
    }
    cell.count.textContent = "[*]";
    cell.element.classList.add("running");
    try {
      const done = await runHtml(kernel, html, (item) => {
        if (!item.input_request) cell.area.add(item);
      });
      cell.area.finish();
      cell.execution_count = done.execution_count;
      cell.count.textContent = !done.ok ? "[!]" : done.execution_count ? `[${done.execution_count}]` : "[ ]";
      cell.element.classList.toggle("failed", !done.ok);
      if (done.run) cell.htmlRun = { ...done.run, code: withUses(html, null, "html") };
      edited();
      face(cell);
      return done.ok;
    } catch (e) {
      cell.area.finish();
      cell.area.notice((e as Error).message, "error");
      cell.count.textContent = "[!]";
      return false;
    } finally {
      cell.element.classList.remove("running");
    }
  };

  const htmlReport = (cell: Cell): HtmlReport => {
    const state = htmlStateOf(cell);
    return { number: cell.number, index: indexOf(cell), html: sourceOf(cell), names: htmlNames(sourceOf(cell)), state: state.kind, label: state.label, height: cell.design?.height() ?? null, notes: cell.htmlNotes };
  };

  /** After a run: which HTML cells name a variable that would now draw something else. */
  let marksTimer: number | null = null;
  const checkMarks = async (): Promise<void> => {
    const ran = cells.filter((c) => (c.kind === "html" || c.kind === "markdown") && c.htmlRun && c.htmlRun.code !== null);
    if (!ran.length) return;
    const changed = await changedNames(kernel, ran.map((c) => c.htmlRun!));
    if (!changed) return;
    for (const cell of ran) {
      const run = cell.htmlRun;
      const now = run ? changed.get(run) : undefined;
      if (!run || !now || now.join("\n") === run.changed.join("\n")) continue;
      run.changed = now;
      drawHtmlState(cell);
    }
  };

  // ===== a cell's design pane (an HTML cell's drawing, a TSX cell's preview) =====

  const pane = (kind: CellKind, height: number | null, cell: () => Cell): { design: DesignPane } => {
    const design = designPane({
      dark,
      height: drawn(kind) || kind === "code" || kind === "tsx" ? height : null,
      resized: () => edited(),
      run: () => void run(cell()),
    });
    return { design };
  };

  const run = async (cell: Cell): Promise<boolean> => {
    if (cell.editor) cell.source = cell.editor.value();
    for (const c of cells) c.editor?.setProblems([]); // the last failure's marks describe code that ran before
    if (isHeading(cell.role)) return true;
    if (cell.kind === "markdown") {
      if (htmlNames(cell.source).length) return runHtmlCell(cell); // its names, from the kernel
      showMarkdown(cell);
      return true;
    }
    if (cell.role === "transformations") return runTransformations(cell);
    if (cell.kind === "html") return runHtmlCell(cell);
    if (cell.kind === "tsx") return runPreview(cell);
    const route = routeOf(cell);
    if (route) return runOnRoute(cell, route);
    if (ROUTED.includes(cell.kind)) {
      cell.area.set([]);
      cell.area.notice(`${KIND_NAMES[cell.kind]} cells run in a project whose mode has them (a code app's data notebook).`, "error");
      return false;
    }
    if (!cell.source.trim()) return true;
    cell.area.set([]);
    cell.element.classList.remove("output-hidden");
    cell.count.textContent = "[*]";
    cell.element.classList.add("running");
    // The first run starts Python (seconds): the cell is gated with words until it is up (8.12).
    if (kernel.state === "off" || kernel.state === "starting") {
      try {
        await busy(cell.element, "Starting Python…", kernel.ensure(), { errorIn: false });
      } catch (e) {
        cell.element.classList.remove("running");
        cell.count.textContent = "[!]";
        cell.area.notice((e as Error).message, "error");
        return false;
      }
    }
    const ended = timeRun(cell);
    try {
      const ranCode = cell.source;
      const done = await runInto(kernel, { code: cell.source, kind: hasSource(cell.kind) ? cell.kind : "code", connection: cell.connection }, cell.area);
      cell.ranSource = ranCode;
      cell.runOrder = ++runs;
      hooks.ran?.();
      cell.execution_count = done.execution_count;
      cell.count.textContent = done.error ? "[!]" : done.execution_count ? `[${done.execution_count}]` : "[ ]";
      cell.element.classList.toggle("failed", !done.ok);
      edited();
      // A calm moment: a cell that now makes a table joins the Tables group.
      if (done.ok && cell.kind === "code" && (tableInfos.length || cells.some((c) => c.role))) void arrange(true);
      return done.ok;
    } finally {
      ended();
      cell.element.classList.remove("running");
    }
  };

  // ===== cells another kernel runs (the mode's routes: routedCells.ts) =====

  /** A TypeScript cell, or a DuckDB SQL cell where the mode runs SQL in its kernel: run on the route. */
  const runOnRoute = async (cell: Cell, route: CellRoute): Promise<boolean> => {
    if (!cell.source.trim()) return true;
    cell.area.set([]);
    cell.element.classList.remove("output-hidden");
    cell.count.textContent = "[*]";
    cell.element.classList.add("running");
    const ended = timeRun(cell);
    try {
      const ranCode = cell.source;
      const body = { path: kernel.intel().path, kind: cell.kind === "sql" ? "sql" : "typescript", code: cell.source, cell: cell.number };
      let done;
      try {
        done = await runRouted(route, body, (o) => cell.area.add(o), () => void run(cell));
      } catch (e) {
        cell.area.notice((e as Error).message, "error");
        done = { ok: false, execution_count: null, error: (e as Error).message };
      }
      cell.area.finish();
      cell.ranSource = ranCode;
      cell.runOrder = ++runs;
      hooks.ran?.();
      cell.execution_count = done.execution_count;
      cell.count.textContent = !done.ok ? "[!]" : done.execution_count ? `[${done.execution_count}]` : "[ ]";
      cell.element.classList.toggle("failed", !done.ok);
      edited();
      return done.ok;
    } finally {
      ended();
      cell.element.classList.remove("running");
    }
  };

  /** A TSX cell: drawn with the project's own React in the HTML cells' frame, under its code. */
  const runPreview = async (cell: Cell): Promise<boolean> => {
    const route = cellRoute("tsx");
    cell.area.set([]);
    if (!route?.preview) {
      cell.area.notice("TSX cells are drawn in a project whose mode has them (a code app's data notebook).", "error");
      return false;
    }
    if (!cell.source.trim()) return true;
    cell.count.textContent = "[*]";
    cell.element.classList.add("running");
    try {
      const html = await previewRouted(route, { path: kernel.intel().path, source: cell.source, cell: cell.number }, () => void run(cell));
      if (html === null) return false;
      cell.design?.show(html);
      cell.element.classList.add("previewed");
      cell.element.classList.remove("failed");
      cell.count.textContent = "[ ]";
      cell.ranSource = cell.source;
      cell.runOrder = ++runs;
      return true;
    } catch (e) {
      cell.element.classList.remove("previewed");
      cell.element.classList.add("failed");
      cell.count.textContent = "[!]";
      cell.area.notice((e as Error).message, "error");
      return false;
    } finally {
      cell.element.classList.remove("running");
    }
  };

  /** The route's declarations known to the editor's TypeScript service (once). */
  const knowTypes = (kind: CellKind): void => {
    const route = cellRoute(kind);
    if (!route) return;
    void Promise.all([routedTypes(route), loadEditors()]).then(([text, m]) => {
      if (text) m.typescriptNotebook(text);
    });
  };

  /** A table's read-only cell: run so that running it again changes nothing (it starts from the table
   *  as its maker made it: client/table_cells.py). */
  const runTransformations = async (cell: Cell, quietly = false): Promise<boolean> => {
    const code = sourceOf(cell);
    const table = cell.table ?? "";
    const variable = infoOf(table)?.variable ?? table.replace(/\W/g, "_");
    cell.area.set([]);
    cell.count.textContent = "[*]";
    cell.element.classList.add("running");
    const ended = timeRun(cell);
    try {
      const done = await runInto(kernel, { code, kind: "table", table: variable }, cell.area);
      cell.execution_count = done.execution_count;
      cell.count.textContent = done.error ? "[!]" : done.execution_count ? `[${done.execution_count}]` : "[ ]";
      cell.element.classList.toggle("failed", !done.ok);
      if (done.ok) records.set(table, { code, at: new Date(), opened: false });
      // Run by itself on opening: the document is as it was (no unsaved mark for it).
      if (!quietly) edited();
      redraw();
      return done.ok;
    } finally {
      ended();
      cell.element.classList.remove("running");
    }
  };

  /** Run cells in order, stopping at the first that fails (or a stopped kernel), as Jupyter does. */
  /** Run up to here: the user's cells from the top to this one, in order (a table's cell too). */
  const runUpTo = async (cell: Cell): Promise<void> => {
    select(cell);
    await runEach(cells.slice(0, indexOf(cell) + 1).filter((c) => !isHeading(c.role)));
  };

  const runEach = async (some: Cell[]): Promise<void> => {
    for (const cell of some) if (!(await run(cell))) return;
  };

  const setKind = (cell: Cell, kind: CellKind): void => {
    if (cell.kind === kind) return;
    if (cell.kind === "markdown" && cell.element.classList.contains("rendered")) editMarkdown(cell);
    // The uses line changes its form with the kind (`# uses` in Python, `<!-- uses -->` in HTML): the
    // old one goes, and the next arrangement writes the new one.
    const bare = withUses(sourceOf(cell), null, usesForm(cell.kind));
    if (bare !== sourceOf(cell)) {
      if (cell.editor) cell.editor.replaceText(bare);
      cell.source = bare;
    }
    const wasHtml = twoFaced(cell);
    cell.kind = kind;
    cell.kindPicker.value = kind;
    cell.part.textContent = "";
    cell.element.classList.remove("kind-code", "kind-sql", "kind-dax", "kind-markdown", "kind-html", "kind-typescript", "kind-tsx", "previewed", "stale");
    cell.element.classList.add(`kind-${kind}`);
    if (cell.htmlRun && (kind === "markdown" || kind === "html")) cell.htmlRun = undefined; // the other kind's values
    if (wasHtml || drawn(kind)) {
      // Its outputs were the other kind's: an HTML cell keeps a design, not a run's output.
      cell.element.classList.remove("rendered");
      cell.area.set([]);
      cell.htmlRun = undefined;
      cell.htmlNotes = [];
      setTimeout(() => cell.editor?.layout(), 0);
    }
    cell.connectionPicker.hidden = !hasSource(kind);
    drawNamed(cell);
    // A SQL cell's connection is not a DAX cell's dataset: one that is not this kind's goes.
    const duck = kind === "sql" && !cell.connection && namedConnections(sourceOf(cell), connections()).length > 0;
    if (hasSource(kind) && !duck && (!cell.connection || !sources(kind).includes(cell.connection))) cell.connection = sources(kind)[0] ?? null;
    // The box shows the connection the cell runs on (it is drawn again on focus; once showed the
    // %sql_connect placeholder while the cell ran on the first connection).
    if (hasSource(kind)) cell.connectionPicker.dispatchEvent(new Event("focus"));
    cell.editor?.setLanguage(LANGUAGE[kind]);
    if (ROUTED.includes(kind)) knowTypes(kind);
    relabel();
    edited();
    typedSoon();
  };

  const cellMenu = (cell: Cell, anchor: HTMLElement): void => {
    document.querySelector(".menu")?.remove();
    const item = (text: string, act: () => void): HTMLElement =>
      h("button", { type: "button", role: "menuitem", onclick: () => { menu.remove(); select(cell); act(); } }, text);
    const at = (): number => indexOf(cell);
    const menu = h(
      "div",
      { class: "menu", role: "menu", "aria-label": "Cell actions" },
      item("Run the cells above", () => void runEach(cells.slice(0, at()))),
      item("Run this cell and the ones below", () => void runEach(cells.slice(at()))),
      item("Insert a cell above", () => insertAt(at(), cell.kind === "markdown" ? "code" : cell.kind)),
      item("Insert a cell below", () => insertAt(at() + 1, cell.kind === "markdown" ? "code" : cell.kind)),
      item("Name…", () => editName(cell)),
      ...(hooks.lineage && !isHeading(cell.role) ? [item("Lineage", () => hooks.lineage!(cell.number))] : []),
      ...(snippetLanguage(cell) ? [item("Insert a snippet…", () => void insertSnippetInto(cell))] : []),
      item("Copy", () => void copy(cell)),
      item("Paste below", () => void paste(cell)),
      item("Duplicate", () => duplicate(cell)),
      item("Clear the output", () => clearOutput(cell)),
      item(cell.element.classList.contains("output-hidden") ? "Show the output" : "Hide the output", () => toggleOutput(cell)),
    );
    document.body.append(menu);
    const box = anchor.getBoundingClientRect();
    menu.style.top = `${box.bottom + 4}px`;
    menu.style.left = `${Math.max(8, Math.min(box.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 8))}px`;
    (menu.querySelector("button") as HTMLButtonElement | null)?.focus();
    setTimeout(() => document.addEventListener("mousedown", function away(e) { if (!menu.contains(e.target as Node)) { menu.remove(); document.removeEventListener("mousedown", away); } }));
    menu.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        menu.remove();
        anchor.focus();
      }
    });
  };

  // ===== errors: which cell a frame is in, its marks, its fixes =====

  /** The cell a frame ran in: the one with that run number, or `running` for the newest number. */
  const cellOf = (frame: Pick<Frame, "where" | "cell">, detail: ErrorDetail, running: Cell): Cell | null => {
    if (frame.where !== "cell" || frame.cell === null) return null;
    const numbers = detail.chain.flatMap((e) => e.frames.map((f) => f.cell ?? 0)).concat(detail.chain.map((e) => e.syntax?.cell ?? 0));
    if (frame.cell === Math.max(...numbers)) return running;
    return cells.find((c) => c !== running && c.execution_count === frame.cell) ?? null;
  };

  const errorHooks = (running: Cell): ErrorHooks => {
    let shown: ErrorDetail | null = null;
    const where = (): Cell => {
      const entry = shown?.chain[shown.chain.length - 1];
      const frame = yourFrame(entry) ?? (entry?.syntax ? ({ where: "cell", cell: entry.syntax.cell } as Frame) : null);
      return (frame && shown && cellOf(frame, shown, running)) || running;
    };
    return {
      shown: (detail) => {
        shown = detail;
        if (hasSource(running.kind)) {
          running.editor?.setProblems(sqlProblems(detail));
          return;
        }
        for (const c of cells) {
          const list = problemsFor(detail, (f) => (cellOf(f, detail, running) === c ? { line: f.line, colShift: 0 } : null));
          if (list.length) c.editor?.setProblems(list);
        }
      },
      fix: (fix) => {
        if (fix.kind === "replace") {
          const target = where();
          const entry = shown?.chain[shown.chain.length - 1];
          const near = hasSource(running.kind) ? (entry?.sql?.line ?? 1) : (yourFrame(entry)?.line ?? entry?.syntax?.line ?? 1);
          if (!target.editor?.applyFix(fix, near)) errorHere(`${fix.target ?? "That"} is no longer in the cell.`);
          else {
            select(target);
            target.editor.focus(); // back in the code, ready to run it again
          }
          return;
        }
        if (fix.kind === "import") {
          const first = cells.find((c) => c.kind === "code") ?? running;
          first.editor?.applyFix(fix, 1);
          select(first);
          first.editor?.focus();
          toast(`Added to cell ${indexOf(first) + 1}`);
          return;
        }
        if (fix.kind === "cell" && fix.text) {
          // A cell that does what the failing one could not (reading a Dataverse table instead of SQL).
          const made = insertAt(indexOf(running) + 1, "code", fix.text);
          select(made);
          made.editor?.focus();
          return;
        }
        if (fix.kind === "define" && fix.name) {
          const maker = definingCell(fix.name, running);
          if (maker) {
            void run(maker).then((ok) => ok && toast(`Ran cell ${indexOf(maker) + 1}`));
          } else errorHere(`No cell above defines ${fix.name}`);
          return;
        }
        // Installed, the cell runs again (the missing-package prompt's retry).
        const again = fix.kind === "install" ? { again: () => void run(running) } : {};
        if (!hooks.fix?.({ ...fix, ...again })) errorHere("Fix not available here");
      },
      goTo: (frame) => {
        const target = shown ? cellOf(frame, shown, running) : null;
        if (!target) return false;
        select(target);
        target.element.scrollIntoView({ block: "nearest" });
        target.editor?.reveal(frame.line, frame.col ?? 1);
        return true;
      },
      openGrid: hooks.openGrid,
    };
  };

  const kept = new WeakMap<Cell, ErrorHooks>();
  const hooksOf = (cell: Cell): ErrorHooks => {
    let found = kept.get(cell);
    if (!found) kept.set(cell, (found = errorHooks(cell)));
    return found;
  };

  /** The cell above `before` that makes `name` (assigns, defines or imports it), nearest first. */
  const definingCell = (name: string, before: Cell): Cell | null => {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const makes = new RegExp(`^\\s*(?:${escaped}\\s*(?:,[^=\\n]*)?=(?!=)|(?:[\\w\\s,]*,\\s*)${escaped}\\s*=(?!=)|def ${escaped}\\b|class ${escaped}\\b|import\\s.*\\bas\\s+${escaped}\\b|from\\s.*\\bimport\\s.*\\b${escaped}\\b|import\\s+${escaped}\\b|for\\s.*\\b${escaped}\\b.*\\bin\\b)`, "m");
    const above = cells.slice(0, Math.max(0, indexOf(before)));
    for (const c of [...above].reverse()) {
      if (c.kind === "code" && makes.test(c.editor?.value() ?? c.source)) return c;
    }
    return null;
  };

  const make = (given: CellData, at: number): Cell => {
    // A SQL cell saved on a Power BI connection (before DAX cells) is a DAX cell.
    const old = given.kind === "sql" && !!given.connection && isWorkspace(given.connection.split("/")[0]!.trim());
    // A window that still holds a Streamlit cell from before the canvas: a Python cell, shown live.
    const once = (given.kind as string) === "streamlit";
    const data: CellData = old ? { ...given, kind: "dax" } : once ? { ...given, kind: "code", live: true } : given;
    const number = data.number && !byNumber(data.number) ? data.number : nextNumber;
    nextNumber = Math.max(nextNumber, number + 1);
    const role = data.role ?? "";
    const editorHost = h("div", { class: "wb-editor" });
    // The hooks need the cell, made just below: they look it up when an error comes.
    let self: Cell | null = null;
    const area = outputArea(dark, () => undefined, {
      shown: (d) => self && hooksOf(self).shown?.(d),
      fix: (f, d) => self && hooksOf(self).fix(f, d),
      goTo: (f) => (self ? hooksOf(self).goTo(f) : false),
      openGrid: hooks.openGrid,
      openResult: (n) => hooks.openResult?.(n, resultName(self?.editor?.value() ?? self?.source ?? "")),
      openTable: (id) => {
        const route = self ? routeOf(self) : null;
        if (route) void openRoutedTable(route, kernel.intel().path, id, self?.name ? self.name.replace(/\W+/g, "_") : undefined);
      },
    });
    const view = h("div", { class: "wb-markdown-view" });
    // A Markdown cell with names: its state above its text, as an HTML cell's design bar.
    const textStatus = h("span", { class: "wb-design-state", role: "status" });
    const textRun = button("Run", () => void run(cell), { icon: "play", class: "ghost wb-design-run", title: "Run: fill the names from the kernel (Ctrl+Enter)" });
    const textBar = { element: h("div", { class: "wb-design-bar wb-text-bar" }, textStatus, h("span", { class: "spacer" }), textRun), status: textStatus, run: textRun };
    const count = h("span", { class: "wb-count" }, data.execution_count ? `[${data.execution_count}]` : "[ ]");
    const kindPicker = h("select", { "aria-label": "Cell kind" }, ...offeredKinds(data.kind).map((k) => h("option", { value: k, selected: k === data.kind }, KIND_NAMES[k]))) as HTMLSelectElement;
    const connectionPicker = h("select", { "aria-label": "Connection", class: "wb-connection", title: "Connection" }) as HTMLSelectElement;
    const fillConnections = (): void => {
      // A DAX cell: only Power BI workspaces' datasets; a SQL cell: every other connection.
      const dax = cell.kind === "dax";
      const names = sources(cell.kind);
      const current = cell.connection;
      const what = dax ? "Dataset" : "Connection";
      connectionPicker.setAttribute("aria-label", what);
      connectionPicker.title = what;
      clear(
        connectionPicker,
        // No connection: DuckDB here, a connection's tables named by the connection ([Finance].Sales).
        dax ? (current ? null : h("option", { value: "" }, "")) : h("option", { value: "" }, "DuckDB"),
        ...names.map((n) => h("option", { value: n, selected: n === current }, n)),
        ...(current && !names.includes(current) ? [h("option", { value: current, selected: true }, `${current} (not found)`)] : []),
      );
    };
    const more = button("More actions", () => cellMenu(cell, more), { icon: "more", iconOnly: true, class: "ghost" });
    // A DuckDB cell's connections, as its SQL names them ([Finance Captive].Sales): each in its head.
    const namedHost = h("span", { class: "wb-sql-named" });
    const hiddenNote = h("button", { type: "button", class: "link wb-output-hidden", onclick: () => toggleOutput(cell) }, "Show output");
    const numberLabel = h("span", { class: "wb-number", title: `Cell ${number}: this number never changes. @cell${number} in a comment links here.` }, `#${number}`);
    // The cell's name, typed in place (or More: Name…). Without one, the area shows only on hover.
    const nameButton = h("input", { type: "text", class: "wb-cell-name", maxlength: MAX_CELL_NAME, placeholder: "Name", "aria-label": "Cell name", spellcheck: "false" }) as HTMLInputElement;
    nameButton.addEventListener("keydown", (e) => {
      e.stopPropagation(); // Jupyter's keys stay out of the name
      if (e.key === "Enter" || e.key === "Escape") {
        e.preventDefault();
        if (e.key === "Escape") nameButton.value = cell.name ?? "";
        nameButton.blur();
      }
    });
    nameButton.addEventListener("change", () => setName(cell, nameButton.value));
    nameButton.addEventListener("blur", () => setName(cell, nameButton.value));
    nameButton.addEventListener("click", (e) => e.stopPropagation());
    // A Python cell of the user's is dragged by its number (or its head): it drops its `@cell` link as text.
    const draggable = (data.kind === "code" || isText(data.kind)) && !isApp(role);
    if (draggable) numberLabel.draggable = true;
    const part = h("span", { class: "wb-part hint" });
    const flowMark = h("span", { class: "wb-flow", role: "status" });
    const runTo = button("Run up to here", () => void runUpTo(cell), { icon: "runTo", class: "ghost wb-run-to", title: "Run every cell from the top to this one" });
    const status = role === "transformations" ? h("span", { class: "wb-table-state", role: "status" }) : null;
    const bar = isHeading(role) ? h("div", { class: "wb-group-bar" }) : null;
    const runButton = button("Run cell", () => void run(cell), { icon: "play", iconOnly: true, class: "ghost", title: "Run cell (Ctrl+Enter)" });
    // An HTML cell that shows its design: back to its HTML.
    const editButton = button("Edit HTML", () => edit(cell), { icon: "edit", iconOnly: true, class: "ghost wb-edit-html", title: "Edit the HTML (Enter)" });
    const { design } = isHeading(role) ? { design: null } : pane(data.kind, data.height ?? null, () => cell);
    const head =
      role === "transformations"
        ? h("div", { class: "wb-cell-head" }, numberLabel, count, part, h("span", { class: "spacer" }), status, runButton, button("Delete cell", () => removeCell(cell), { icon: "trash", iconOnly: true, class: "ghost wb-delete-table" }))
        : h(
            "div",
            { class: "wb-cell-head" },
            numberLabel,
            nameButton,
            count,
            kindPicker,
            connectionPicker,
            namedHost,
            part,
            flowMark,
            h("span", { class: "spacer" }),
            runTo,
            editButton,
            runButton,
            button("Move up", () => moveCell(cell, -1), { icon: "up", iconOnly: true, class: "ghost" }),
            button("Move down", () => moveCell(cell, 1), { icon: "down", iconOnly: true, class: "ghost" }),
            more,
            button("Delete cell", () => removeCell(cell), { icon: "trash", iconOnly: true, class: "ghost" }),
          );
    // The app's own cells (a heading's line, a table's read-only cell) are `wb-tcell`; `wb-cell` is a
    // cell of the user's.
    const element = bar
      ? h("section", { class: `wb-tcell wb-heading role-${role}`, tabindex: -1, role: "listitem" }, bar)
      : h("section", { class: `${role === "transformations" ? "wb-tcell role-transformations" : "wb-cell"} kind-${data.kind}`, tabindex: -1, role: "listitem" }, head, editorHost, view, design?.element ?? null, area.element, hiddenNote);
    const cell: Cell = {
      kind: data.kind,
      source: data.source,
      connection: data.connection,
      execution_count: data.execution_count,
      element,
      editor: null,
      area,
      view,
      textBar,
      count,
      kindPicker,
      connectionPicker,
      wantsFocus: false,
      number,
      role,
      table: data.table ?? null,
      grouped: data.grouped ?? false,
      steps: data.steps ?? null,
      bar,
      status,
      part,
      design,
      editorHost,
      name: data.name ? cleanName(data.name) || null : null,
      nameButton: role === "transformations" || bar ? null : nameButton,
      htmlRun: data.kind === "html" ? runFromOutputs(data.outputs) : undefined,
      htmlNotes: [],
      drawn: 0,
      flow: flowMark,
      ranSource: null,
      runOrder: null,
    };
    self = cell;
    drawName(cell);
    // A table's cell that came with the file (or a reload) has not run since.
    if (role === "transformations" && cell.table && building && hooks.opened && !records.has(cell.table)) {
      records.set(cell.table, { code: null, at: null, opened: true });
      cameWithFile.add(cell.table);
    }
    if (bar) {
      element.addEventListener("focusin", () => select(cell));
      cells.splice(at, 0, cell);
      list.insertBefore(element, list.children[at] ?? null);
      relabel();
      return cell;
    }
    const sql = sqlCompleter(kernel, () => cell.connection, connections);
    const dax = daxCompleter(() => cell.connection);
    connectionPicker.hidden = !hasSource(data.kind);
    fillConnections();
    connectionPicker.addEventListener("focus", () => {
      // First use: a workspace whose datasets are not listed yet loads its catalog; the list follows.
      if (cell.kind === "dax") datasetsWanted();
      fillConnections();
    });
    connectionPicker.addEventListener("change", () => {
      cell.connection = connectionPicker.value || null;
      changed();
      connectionsSoon();
      drawNamed(cell);
      cell.editor?.lint();
    });
    namedHosts.set(cell, namedHost);
    drawNamed(cell);
    kindPicker.addEventListener("change", () => {
      setKind(cell, kindPicker.value as CellKind);
      cell.editor?.lint();
    });
    if (draggable) {
      // The head drags the cell too, but not from its buttons and pickers.
      let pressed: HTMLElement | null = null;
      head.draggable = true;
      head.addEventListener("mousedown", (e) => (pressed = e.target as HTMLElement));
      head.addEventListener("dragstart", (e) => {
        if ((cell.kind !== "code" && !isText(cell.kind)) || (e.target === head && pressed?.closest("button, select, input, a"))) return e.preventDefault();
        e.dataTransfer?.setData("text/plain", `@cell${cell.number}`);
        if (e.dataTransfer) e.dataTransfer.effectAllowed = "copyLink";
        element.classList.add("dragging");
      });
      head.addEventListener("dragend", () => element.classList.remove("dragging"));
    }
    element.addEventListener("focusin", () => select(cell));
    // Right-click the cell (its head, its output; the editor has its own menu): Lineage.
    element.addEventListener("contextmenu", (e) => {
      const at = e.target as HTMLElement;
      // An error panel, the editor, a box have menus of their own; selected text keeps the browser's.
      if (e.defaultPrevented || at.closest(".monaco-editor, .wb-err, input, textarea, select, iframe") || window.getSelection()?.toString()) return;
      e.preventDefault();
      select(cell);
      const items: MenuItem[] = [];
      if (hooks.lineage) items.push(["lineage", "Lineage", () => hooks.lineage!(cell.number)]);
      showMenu(e.clientX, e.clientY, cell.name ?? `Cell ${cell.number}`, items);
    });
    // A snippet dragged from the blade list: taken before the editor's own drop (which would paste
    // its name), filled by its form, then put where it was dropped.
    element.addEventListener("dragover", (e) => {
      if (!e.dataTransfer?.types.includes(SNIPPET_DRAG)) return;
      e.preventDefault();
      e.stopPropagation();
      element.classList.add("snippet-over");
    }, true);
    element.addEventListener("dragleave", () => element.classList.remove("snippet-over"));
    element.addEventListener("drop", (e) => {
      const snippet = draggedSnippet(e.dataTransfer);
      element.classList.remove("snippet-over");
      if (!snippet) return;
      e.preventDefault();
      e.stopPropagation();
      void dropSnippet(cell, snippet, e.clientX, e.clientY);
    }, true);
    element.addEventListener("dblclick", () => {
      if (cell.kind === "markdown" && element.classList.contains("rendered")) editMarkdown(cell);
    });
    // An HTML cell that shows its design: a click on the cell itself (its
    // head, not a button, and not the design, whose clicks are the design's own) opens its code.
    element.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (!twoFaced(cell) || !element.classList.contains("rendered")) return;
      if (target.closest(".wb-design, button, select, a, input")) return;
      editHtml(cell);
    });
    // Left: it draws by itself. (Another window in front is not leaving: the HTML stays open.)
    editorHost.addEventListener("focusout", () => {
      setTimeout(() => {
        if (!twoFaced(cell) || element.classList.contains("rendered") || !cells.includes(cell)) return;
        const now = document.activeElement as HTMLElement | null;
        if (!document.hasFocus() || (now && (editorHost.contains(now) || now.closest(".context-view, .monaco-menu, .overflowingContentWidgets")))) return;
        if (sourceOf(cell).trim()) showDesign(cell);
      }, 0);
    });
    if (role === "transformations") kindPicker.hidden = true;
    // The editors' intelligence: Jedi with the cells before this one (or the kernel's names once it runs),
    // the cells after it for the lint (an import here they use is used).
    const codeOf = (list: Cell[]): string[] => list.filter((c) => c.kind === "code" || c.kind === "sql").map((c) => (c.kind === "sql" ? `${sqlLine(c.connection)}\n${sourceOf(c)}` : sourceOf(c)));
    const docName = (): string => kernel.intel().path ?? "Untitled notebook";
    const intel = pythonIntel(kernel, {
      notebook: true,
      before: () => codeOf(cells.slice(0, Math.max(0, cells.indexOf(cell)))),
      after: () => codeOf(cells.slice(cells.indexOf(cell) + 1)),
      language: () => (cell.kind === "code" && cell.role !== "transformations" ? "python" : cell.kind === "sql" ? "sql" : "other"),
      connection: () => cell.connection,
      document: docName,
      place: () => `cell ${cell.number}`,
    });
    const intelKey = `${Math.random()}`;
    void loadEditors().then((m) => {
      if (disposed || !cells.includes(cell)) return; // deleted (or the notebook closed) before its editor loaded
      cell.editor = m.createCodeEditor(editorHost, {
        pageZoom: true, // the page's code zoom (Ctrl+wheel, Ctrl+= - 0)
        intel: {
          signature: (text, offset) => (cell.kind === "code" ? intel.signature(text, offset) : Promise.resolve(null)),
          hover: (text, offset) => (cell.kind === "code" ? intel.hover(text, offset) : Promise.resolve("")),
          lint: (text) => intel.lint(text),
          onLint: (problems) =>
            showProblems(`${docName()}\u0000${intelKey}`, cells.includes(cell) ? { document: docName(), place: `cell ${cell.number}`, problems, reveal: (line, column) => { select(cell); cell.editor?.reveal(line, column); } } : null),
        },
        language: LANGUAGE[cell.kind],
        value: cell.source,
        theme: theme(),
        grow: true,
        // Ghost text: this cell with the notebook's other code cells (their text only, never outputs).
        inline: inlineSource(() => {
          const coded = (c: Cell): boolean => (c.kind === "code" || c.kind === "sql") && c.role !== "transformations";
          if (!coded(cell)) return null;
          const name = (kernel.intel().path ?? "Untitled notebook.ipynb").split(/[\\/]/).pop() ?? "notebook.ipynb";
          return {
            key: inlineKey,
            name,
            kind: "notebook",
            cells: cells.filter(coded).map((c) => ({ id: String(c.number), text: sourceOf(c), language: c.kind === "sql" ? "sql" : "python" })),
            cell: String(cell.number),
          };
        }),
        readOnly: cell.role === "transformations",
        cellLinks: { first: (n) => (byNumber(n) ? firstLine(sourceOf(byNumber(n)!)) : null), go: (n) => void goTo(n) },
        placeholder: cell.kind === "sql" ? "SQL" : cell.kind === "dax" ? "DAX" : cell.kind === "html" ? "HTML" : cell.kind === "typescript" ? "TypeScript" : cell.kind === "tsx" ? "TSX: export default function ..." : cell.kind === "code" && !cells.some((c) => c !== cell && c.kind === "code" && c.role !== "transformations" && sourceOf(c).trim()) ? FIRST_HINT : undefined,
        // By the cell's kind as it is now: Python from the kernel, SQL from the connection's catalog,
        // DAX from its dataset's part of the workspace's catalog.
        complete: (text, offset) =>
          cell.kind === "sql" ? sql(text, offset)
          : cell.kind === "dax" ? dax(text, offset)
          : cell.kind === "code" ? intel.complete(text, offset).then((found) => found ?? python(text, offset))
          : Promise.resolve([]),
        help: (text, offset) => (cell.kind === "code" ? kernel.help(text, offset) : Promise.resolve("")),
        sendToAgent: (what, ask) => sendToAgent(codeItem(`cell ${indexOf(cell) + 1} of ${currentDocument()}${what.startLine === what.endLine ? `, line ${what.startLine}` : `, lines ${what.startLine} to ${what.endLine}`}`, what, LANGUAGE[cell.kind]), ask),
        actions: hooks.lineage ? [{ id: "sab.lineage", label: "Lineage", run: () => hooks.lineage!(cell.number) }] : [],
        keys: {
          shiftEnter: () => void run(cell).then(() => next(cell)),
          ctrlEnter: () => void run(cell),
          escape: () => toCommandMode(cell),
          f1: hooks.help,
        },
      });
      cell.editor.onChange((change) => {
        edited();
        drawNamed(cell);
        // The uses line follows the typing, after a short pause (never an undo: that would undo the undo).
        if (!change.undo && !isApp(cell.role)) typedSoon();
        if (cell.role === "transformations") redraw();
        if (cell.kind === "html" || cell.kind === "markdown") drawHtmlState(cell);
      });
      if (hooks.cursor) cell.editor.onCursor(hooks.cursor);
      if (cell.wantsFocus) focusEditor(cell);
    });
    if (ROUTED.includes(cell.kind)) knowTypes(cell.kind);
    if (cell.kind === "markdown" && cell.source.trim()) showMarkdown(cell);
    else if (cell.kind === "html") {
      if (cell.source.trim()) showDesign(cell);
    } else {
      area.set(data.outputs);
    }
    cells.splice(at, 0, cell);
    list.insertBefore(element, list.children[at] ?? null);
    relabel();
    return cell;
  };

  /** The keyboard into a cell's editor: now if it exists, else as soon as it does. A user who clicked
   *  somewhere else in the meantime keeps their focus (a delayed focus once split typed text between
   *  two cells). */
  const focusEditor = (cell: Cell): void => {
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
  };

  const toCommandMode = (cell: Cell): void => {
    select(cell);
    cell.element.focus();
  };

  const edit = (cell: Cell): void => {
    select(cell);
    if (cell.kind === "markdown" && cell.element.classList.contains("rendered")) editMarkdown(cell);
    else if (twoFaced(cell) && cell.element.classList.contains("rendered")) editHtml(cell);
    else focusEditor(cell);
  };

  const next = (cell: Cell): void => {
    const following = cells[indexOf(cell) + 1] ?? make(empty(cell.kind === "markdown" || cell.kind === "html" ? "code" : cell.kind, cell.connection), cells.length);
    select(following);
    following.element.scrollIntoView({ block: "nearest" });
    focusEditor(following);
  };

  const insertAt = (at: number, kind: CellKind = "code", source = ""): Cell => {
    // A SQL cell whose query names a connection's tables ([Finance].Sales) runs in DuckDB: no connection.
    const duck = kind === "sql" && namedConnections(source, connections()).length > 0;
    const cell = make({ ...empty(kind, hasSource(kind) && !duck ? (sources(kind)[0] ?? null) : null), source }, Math.max(0, Math.min(at, cells.length)));
    select(cell);
    cell.element.scrollIntoView({ block: "nearest" });
    focusEditor(cell);
    edited();
    if (source) typedSoon();
    return cell;
  };

  const place = (cell: Cell, to: number): void => {
    cells.splice(indexOf(cell), 1);
    cells.splice(to, 0, cell);
    list.insertBefore(cell.element, cells[to + 1]?.element ?? null);
    relabel();
  };

  const moveCell = (cell: Cell, by: number): void => {
    const from = indexOf(cell);
    const to = from + by;
    if (to < 0 || to >= cells.length) return;
    place(cell, to);
    undos.push({ kind: "move", cell, from });
    cell.element.scrollIntoView({ block: "nearest" });
    edited();
  };

  const dataOf = (c: Cell): CellData => cellData(c, sourceOf(c)); // notebookCells.ts: a cell as it is saved

  // ===== a cell's name (docs/ideas.md, named cells): shown in its head, kept in its metadata =====

  const drawName = (cell: Cell): void => {
    const input = cell.nameButton;
    if (!input) return;
    if (document.activeElement !== input) input.value = cell.name ?? "";
    input.classList.toggle("unnamed", !cell.name);
    input.title = cell.name ?? "Name the cell";
  };

  const setName = (cell: Cell, typed: string): void => {
    const name = cleanName(typed) || null;
    if (cell.nameButton && document.activeElement !== cell.nameButton) cell.nameButton.value = name ?? "";
    if (name === cell.name) return drawName(cell);
    cell.name = name;
    drawName(cell);
    edited(); // saved with the cell
  };

  const editName = (cell: Cell): void => {
    const input = cell.nameButton;
    if (!input || !input.isConnected) return;
    select(cell);
    input.focus();
    input.select();
  };

  // ===== snippets: text for a cell, from the starter pack or the user's own (starters.ts) =====

  /** The language of the snippets a cell of this kind takes (none: Markdown, SQL, the app's cells). */

  /** Put a filled snippet into a cell, where it was dropped or at the cursor (an empty cell takes it
   *  whole). A Streamlit piece names the cell it goes into, unless it has a name. */
  const putSnippet = (cell: Cell, filled: FilledSnippet, x?: number, y?: number): void => {
    if (!sourceOf(cell).trim()) {
      if (cell.editor) cell.editor.setValue(filled.text);
      else cell.source = filled.text;
    } else if (cell.editor) {
      cell.editor.insertAt(filled.text, x, y);
    } else {
      cell.source = `${cell.source.replace(/\n*$/, "")}\n${filled.text}`;
    }
    if (filled.cell_name && !cell.name) setName(cell, filled.cell_name);
    select(cell);
    edited();
    typedSoon();
    if (cell.kind === "html" && !cell.editor?.hasFocus()) showDesign(cell);
    if (cell.kind === "markdown" && !cell.editor?.hasFocus()) showMarkdown(cell);
  };

  /** A snippet dropped on a cell (or the list, `cell` null: a new cell of its kind at the end). A cell
   *  of another language refuses it; a Streamlit piece on a Python cell that holds code makes a cell
   *  of its own below it. */
  const dropSnippet = async (cell: Cell | null, snippet: { name: string; language: SnippetLanguage }, x?: number, y?: number): Promise<void> => {
    const no = cell ? refusal(snippet.language, cell.kind) ?? (isApp(cell.role) ? "This cell follows the grid: drop it on a cell of yours." : null) : null;
    if (no) return errorHere(no);
    const filled = await fillSnippet(snippet.name, cell?.kind === "dax" ? cell.connection : null);
    if (!filled) return;
    const kind = SNIPPET_CELL[filled.language];
    // A Streamlit piece or a Python snippet (a Write starter) is a whole cell: a cell of its own below one that holds code.
    const own = !cell || ((filled.language === "streamlit" || filled.language === "python") && sourceOf(cell).trim());
    const target = own ? insertAt(cell ? indexOf(cell) + 1 : cells.length, kind) : cell;
    putSnippet(target, filled, own ? undefined : x, own ? undefined : y);
  };

  /** A cell's menu: Insert a snippet… (the snippets of its language), filled, at the cursor. */
  const insertSnippetInto = async (cell: Cell): Promise<void> => {
    const language = snippetLanguage(cell);
    if (!language) return;
    const name = await pickSnippet(language);
    if (name) await dropSnippet(cell, { name, language });
  };

  /** The agent's (workbench_snippet_insert): filled with `values` (each placeholder's own otherwise),
   *  into the cell numbered `number`, else the selected cell when it is of the snippet's kind (an empty
   *  one for a Streamlit piece), else a new cell of its kind below the selected one. */
  const insertSnippet = async (name: string, values: Record<string, unknown>, number?: number): Promise<{ cell: number; kind: CellKind; name: string | null }> => {
    const filled = await api<FilledSnippet>(`/blades/${encodeURIComponent(name)}/snippet`, "POST", { values });
    const kind = SNIPPET_CELL[filled.language];
    let cell = number === undefined ? selected : byNumber(number);
    if (number !== undefined) {
      if (!cell || isApp(cell.role)) throw new Error(`This notebook has no cell ${number} of yours.`);
      const no = refusal(filled.language, cell.kind);
      if (no) throw new Error(no);
    }
    if (!cell || cell.kind !== kind || isApp(cell.role) || (number === undefined && (filled.language === "streamlit" || filled.language === "python") && sourceOf(cell).trim())) {
      cell = insertAt(selected ? indexOf(selected) + 1 : cells.length, kind);
    }
    putSnippet(cell, filled);
    return { cell: cell.number, kind: cell.kind, name: cell.name };
  };

  // ===== a cell copied: pasted in any notebook =====

  const linkOf = (cell: Cell): { document: string | null; cell: number; title: string } => ({ document: null, cell: cell.number, title: "this notebook" });

  /** Copy: the cell's link and the cell itself, for every Workbench window. */
  const copy = (cell: Cell): { cell: number; document: string | null } | null => {
    if (isApp(cell.role)) return null;
    const data = dataOf(cell);
    const link = linkOf(cell);
    copyCell({ ...link, kind: data.kind, source: data.source, connection: data.connection, height: data.height ?? null });
    return { cell: link.cell, document: link.document };
  };

  /** Paste: the copied cell as a new cell below (its own number; nothing of the Tables group). */
  const paste = (after: Cell | null): boolean => {
    const held = copiedCell();
    if (!held) return false;
    const kind = (KINDS as string[]).includes(held.kind) ? (held.kind as CellKind) : "code";
    const made = make({ ...empty(kind, held.connection), source: held.source, height: held.height }, after ? indexOf(after) + 1 : cells.length);
    select(made);
    made.element.scrollIntoView({ block: "nearest" });
    toCommandMode(made);
    edited();
    typedSoon();
    return true;
  };

  const removeCell = (cell: Cell): void => {
    // The app's own cells go when their table does: a heading is never deleted, a table's cell only
    // once the table is closed in the grid (an open table always has its cell).
    if (isHeading(cell.role)) return;
    if (cell.role === "transformations" && infoOf(cell.table)) {
      toast(`${cell.table} is open in the grid, so it keeps its cell. Close the table there first.`);
      return;
    }
    const at = indexOf(cell);
    const data = dataOf(cell);
    cells.splice(at, 1);
    cell.editor?.dispose();
    cell.design?.dispose();
    cell.element.remove();
    // The last cell gone: an empty one in its place (Undo takes it away again if still empty).
    const filler = cells.length ? null : make(empty(), 0);
    undos.push({ kind: "delete", data, at, filler });
    if (undos.length > 100) undos.shift();
    const after = cells[Math.min(at, cells.length - 1)];
    if (after) {
      select(after);
      if (document.activeElement === document.body) after.element.focus();
    }
    relabel();
    edited();
    if (cell.role === "transformations") void arrange(true);
    toast("Cell deleted.", "info", { label: "Undo", run: () => void undo() });
  };

  const undo = (): boolean => {
    const last = undos.pop();
    if (!last) return false;
    if (last.kind === "move") {
      if (cells.includes(last.cell)) place(last.cell, Math.min(last.from, cells.length - 1));
    } else {
      // The empty cell made when the last one went is replaced by the one coming back.
      const lone = last.filler && cells.includes(last.filler) && !(last.filler.editor?.value() ?? last.filler.source).trim() ? last.filler : null;
      const back = make(last.data, Math.min(last.at, cells.length));
      if (lone) {
        cells.splice(indexOf(lone), 1);
        lone.editor?.dispose();
        lone.element.remove();
        relabel();
      }
      select(back);
      back.element.scrollIntoView({ block: "nearest" });
    }
    edited();
    return true;
  };

  const duplicate = (cell: Cell): void => {
    if (isApp(cell.role)) return;
    // A copy is a new cell: its own number, and no part in the Tables group.
    const copy = make({ ...dataOf(cell), outputs: [], execution_count: null, number: null, role: "", table: null, grouped: false, steps: null }, indexOf(cell) + 1);
    select(copy);
    edited();
  };

  const clearOutput = (cell: Cell): void => {
    if (isHeading(cell.role)) return;
    cell.area.set([]);
    cell.execution_count = null;
    cell.count.textContent = "[ ]";
    cell.element.classList.remove("failed", "output-hidden");
    edited();
  };

  const toggleOutput = (cell: Cell): void => {
    cell.element.classList.toggle("output-hidden");
  };

  // Command mode: Jupyter's keys on the selected cell when the focus is on the cell, not its editor.
  // A snippet dropped between or after the cells: a new cell of its kind at the end.
  list.addEventListener("dragover", (e) => {
    if (e.dataTransfer?.types.includes(SNIPPET_DRAG)) e.preventDefault();
  });
  list.addEventListener("drop", (e) => {
    const snippet = draggedSnippet(e.dataTransfer);
    if (!snippet) return;
    e.preventDefault();
    void dropSnippet(null, snippet);
  });
  list.addEventListener("keydown", (e) => {
    const target = e.target as HTMLElement;
    if (!target.matches(".wb-cell, .wb-tcell") || !selected) return;
    const cell = selected;
    const at = indexOf(cell);
    const key = e.key.toLowerCase();
    const plain = !e.ctrlKey && !e.metaKey && !e.altKey;
    let handled = true;
    if (e.key === "Enter" && e.shiftKey) void run(cell).then(() => next(cell));
    else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void run(cell);
    else if (e.key === "Enter" && plain && isHeading(cell.role)) toggleFold(cell);
    else if (e.key === "Enter" && plain) edit(cell);
    else if (plain && !e.shiftKey && key === "a") insertAt(at, "code");
    else if (plain && !e.shiftKey && key === "b") insertAt(at + 1, "code");
    else if (plain && key === "d") {
      if (Date.now() - pendingD < 800) {
        pendingD = 0;
        removeCell(cell);
      } else pendingD = Date.now();
    } else if (plain && key === "y" && !isApp(cell.role)) setKind(cell, "code");
    else if (plain && key === "m" && !isApp(cell.role)) setKind(cell, "markdown");
    else if (plain && key === "s" && !isApp(cell.role)) setKind(cell, "sql");
    else if (plain && !e.shiftKey && key === "x" && !isApp(cell.role)) setKind(cell, "dax");
    else if (plain && !e.shiftKey && key === "h" && !isApp(cell.role)) setKind(cell, "html");
    else if (plain && !e.shiftKey && key === "c") void copy(cell);
    else if (plain && !e.shiftKey && key === "v") void paste(cell);
    else if (plain && key === "z") undo();
    else if (plain && (key === "j" || e.key === "ArrowDown")) {
      const below = cells.slice(at + 1).find((c) => !c.element.hidden); // a folded group's cells are passed over
      if (below) toCommandMode(below);
    } else if (plain && (key === "k" || e.key === "ArrowUp")) {
      const above = cells.slice(0, at).reverse().find((c) => !c.element.hidden);
      if (above) toCommandMode(above);
    } else if (plain && key === "o") toggleOutput(cell);
    else handled = false;
    if (handled) {
      e.preventDefault();
      e.stopPropagation();
    }
  });

  // ===== the Tables group: arranged by the server's rules, drawn and folded here =====

  const goTo = (number: number, line?: number | null): boolean => {
    const cell = byNumber(number);
    if (!cell) {
      errorHere(`There is no cell ${number} in this notebook.`);
      return false;
    }
    // Open what hides it.
    if (cell.grouped && cell.role !== "tables") groupFolded = false;
    if (cell.grouped && cell.table && (cell.role === "maker" || cell.role === "transformations")) unfolded.add(cell.table);
    redraw();
    select(cell);
    cell.element.scrollIntoView({ block: "center" });
    cell.element.focus();
    cell.element.classList.add("wb-arrived");
    setTimeout(() => cell.element.classList.remove("wb-arrived"), 1200);
    if (line && cell.editor) {
      cell.editor.focus();
      cell.editor.moveTo(line);
    }
    return true;
  };

  const toggleFold = (cell: Cell): void => {
    if (cell.role === "tables") groupFolded = !groupFolded;
    else if (cell.table) {
      if (unfolded.has(cell.table)) unfolded.delete(cell.table);
      else unfolded.add(cell.table);
    }
    redraw();
  };

  /** A note with its cell links as buttons: "orders is made at [@cell7] (it needs make_dates)". */
  const noteElement = (note: string): HTMLElement =>
    h(
      "span",
      { class: "wb-table-note" },
      ...noteParts(note).map((part) =>
        typeof part === "string" ? part : h("button", { type: "button", class: "link wb-cell-link", title: firstLine(byNumber(part.cell) ? sourceOf(byNumber(part.cell)!) : "") || `Cell ${part.cell}`, onclick: (e: Event) => { e.stopPropagation(); goTo(part.cell); } }, `@cell${part.cell}`),
      ),
    );

  /** Draw the folded lines, each table cell's state, and what is folded away. */
  const redraw = (): void => {
    const tables = cells.filter((c) => c.role === "transformations");
    const states = new Map(tables.map((c) => [c.table, stateOf(c)]));
    for (const cell of cells) {
      const inTable = cell.grouped && !!cell.table && (cell.role === "maker" || cell.role === "transformations");
      cell.element.hidden = (cell.grouped && cell.role !== "tables" && groupFolded) || (inTable && !unfolded.has(cell.table!));
      cell.element.classList.toggle("in-tables", cell.grouped && !isHeading(cell.role));
      cell.element.classList.toggle("role-maker", cell.role === "maker");
      cell.element.classList.toggle("role-imports", cell.role === "imports");
      cell.part.textContent = cell.role === "maker" && cell.table ? `makes ${cell.table}` : cell.role === "imports" ? "imports the tables need" : cell.role === "transformations" ? `${cell.table} · transformations · read-only: it follows the grid` : "";
      if (cell.role === "tables" && cell.bar) {
        const line = groupLineText([...states.values()]);
        cell.element.classList.toggle("stale", line.stale);
        clear(cell.bar, h("button", { type: "button", class: "wb-fold", "aria-expanded": String(!groupFolded), onclick: () => toggleFold(cell) }, h("span", { class: "wb-chevron", "aria-hidden": "true" }, groupFolded ? "▸" : "▾"), line.text));
      } else if (cell.role === "table" && cell.bar) {
        const line = lineOf(cell.table);
        const state = states.get(cell.table);
        const own = tables.find((c) => c.table === cell.table);
        const foldable = !!own?.grouped;
        const open = unfolded.has(cell.table ?? "");
        const words = line && state ? tableLineText(line, state) : (cell.table ?? "");
        const note = line?.note ?? cell.source.split("\n").slice(1).join(" ").trim();
        cell.element.classList.toggle("stale", state?.kind === "outOfDate");
        clear(
          cell.bar,
          foldable
            ? h("button", { type: "button", class: "wb-fold", "aria-expanded": String(open), onclick: () => toggleFold(cell) }, h("span", { class: "wb-chevron", "aria-hidden": "true" }, open ? "▾" : "▸"), words)
            : h("span", { class: "wb-fold still" }, words),
          note ? noteElement(note) : null,
          h("span", { class: "spacer" }),
          own && state?.runnable ? button("Run", () => void run(own), { icon: "play", class: "ghost wb-run-table", title: `Run ${cell.table}'s cell` }) : null,
        );
      } else if (cell.role === "transformations" && cell.status) {
        const state = states.get(cell.table)!;
        cell.status.textContent = state.label;
        cell.status.hidden = !state.label; // a cell that is current says nothing
        cell.status.className = `wb-table-state ${state.kind}`;
        cell.element.classList.toggle("stale", state.kind === "outOfDate");
        cell.element.classList.toggle("closed", !infoOf(cell.table));
      }
    }
    relabel();
    hooks.tablesChanged?.();
  };

  /** A cell's uses line as it should be. The cursor stays on its text, and that text stays where it is
   *  on screen when the line above it comes or goes. */
  const applyUses = (cell: Cell, line: string | null): void => {
    const current = sourceOf(cell);
    const next = withUses(current, line, usesForm(cell.kind));
    if (next === current) return;
    if (!cell.editor) {
      cell.source = next;
      edited();
      return;
    }
    const typing = cell.element.contains(document.activeElement);
    const before = cell.element.getBoundingClientRect().height;
    cell.editor.replaceText(next);
    cell.editor.layout();
    if (typing) {
      const grew = cell.element.getBoundingClientRect().height - before;
      let scroller: HTMLElement | null = list.parentElement;
      while (scroller && scroller.scrollHeight <= scroller.clientHeight) scroller = scroller.parentElement;
      if (scroller && grew) scroller.scrollTop += grew;
    }
  };

  const apply = (done: { cells: ArrangedCell[]; tables: TableLine[]; next_cell: number }, move: boolean): void => {
    nextNumber = Math.max(nextNumber, done.next_cell);
    tableLines = done.tables;
    if (move) {
      const left = new Map(cells.map((c) => [c.number, c]));
      const wanted: Cell[] = [];
      const hadGroup = cells.some((c) => c.role === "tables");
      const movedIn: string[] = [];
      for (const a of done.cells) {
        let cell = left.get(a.number);
        // The app's cells are made and unmade as a whole (a heading is never turned into code).
        if (cell && isApp(cell.role) !== isApp(a.role)) cell = undefined;
        if (!cell) cell = make({ kind: a.kind, source: a.source, connection: null, outputs: [], execution_count: null, number: a.number, role: a.role, table: a.table, grouped: a.grouped, steps: a.steps ?? null }, cells.length);
        else left.delete(a.number);
        if (a.role === "maker" && a.grouped && !(cell.role === "maker" && cell.grouped) && a.table) movedIn.push(a.table);
        cell.role = a.role;
        cell.table = a.table;
        cell.grouped = a.grouped;
        wanted.push(cell);
      }
      for (const gone of left.values()) {
        if (isApp(gone.role)) {
          gone.editor?.dispose();
          gone.element.remove();
          if (selected === gone) selected = null;
        } else wanted.push(gone); // never lose a cell of the user's
      }
      const focused = wanted.find((c) => c.editor?.hasFocus());
      const moved = wanted.length !== cells.length || wanted.some((c, i) => cells[i] !== c);
      cells.splice(0, cells.length, ...wanted);
      wanted.forEach((c, i) => {
        if (list.children[i] !== c.element) list.insertBefore(c.element, list.children[i] ?? null);
      });
      focused?.editor?.focus();
      if (moved) edited();
      // A group made while working shows its tables.
      if (!hadGroup && !building && cells.some((c) => c.role === "tables")) groupFolded = false;
      // A cell the user was just working in is not folded away under them: its table shows open.
      if (movedIn.length && !building) for (const name of movedIn) unfolded.add(name);
    }
    for (const a of done.cells) {
      // A table seen for the first time opens unfolded (its cell, then its output).
      if (a.role === "transformations" && a.table && !seenTables.has(a.table)) {
        seenTables.add(a.table);
        unfolded.add(a.table);
      }
      const cell = byNumber(a.number);
      if (!cell) continue;
      if (isHeading(a.role)) {
        if (cell.source !== a.source) {
          cell.source = a.source;
          edited();
        }
      } else if (a.role === "transformations") {
        if (a.steps) cell.steps = a.steps;
        if (sourceOf(cell) !== a.source) {
          if (cell.editor) cell.editor.replaceText(a.source);
          cell.source = a.source;
          edited();
        }
      } else if (cell.kind !== "markdown") applyUses(cell, a.uses);
    }
    redraw();
    void runOwnTables();
  };

  /** The tables' cells the app wrote whole (no cell of the user's makes the table: its load and its
   *  transformations, both the app's) run by themselves, once each, so the cell shows its table. A
   *  table a cell of the user's makes waits for the user's Run (their code never runs by itself). */
  const runOwnTables = async (): Promise<void> => {
    for (const cell of cells.filter((c) => c.role === "transformations" && c.table)) {
      const table = cell.table!;
      if (disposed || autoRan.has(table) || !infoOf(table)) continue;
      const line = lineOf(table);
      const state = stateOf(cell);
      if (!line || line.maker !== null || (state.kind !== "notRun" && state.kind !== "notRunSinceOpening")) continue;
      autoRan.add(table);
      if (cell.editor) cell.source = cell.editor.value();
      await runTransformations(cell, true);
    }
  };

  /** Ask the server for the notebook as it should be. `move` false while the user types: nothing is
   *  added or moved, only the tables' cells and the uses lines follow. */
  const arrange = async (move: boolean): Promise<void> => {
    const relevant = tableInfos.length > 0 || cells.some((c) => c.role !== "") || cells.some((c) => c.kind !== "markdown" && withUses(sourceOf(c), null, usesForm(c.kind)) !== sourceOf(c));
    // A mode whose SQL runs in its own kernel (a code app's data notebook): the open tables are that kernel's
    // views already, so the Python kernel's Tables group is not made here.
    if (!relevant || cellRoute("sql")) return;
    const mine = ++asked;
    const at = version;
    const body = {
      kind: "notebook",
      cells: cells.map((c) => ({ kind: c.kind, source: sourceOf(c), number: c.number, role: c.role, table: c.table, grouped: c.grouped })),
      tables: tableInfos.map((t) => t.name),
      next_cell: nextNumber,
      move,
    };
    try {
      const done = await api<{ cells: ArrangedCell[]; tables: TableLine[]; next_cell: number }>("/workbench/tables/arrange", "POST", body);
      if (mine !== asked) return; // a newer question is on its way
      if (at !== version) return void (move ? arrange(true) : typedSoon()); // the text changed meanwhile: ask again
      apply(done, move);
    } catch {
      /* the server is away: the cells stay as they are */
    }
  };

  function typedSoon(): void {
    if (quiet !== null) window.clearTimeout(quiet);
    quiet = window.setTimeout(() => {
      quiet = null;
      void arrange(false);
    }, 600);
  }

  // A kernel that starts (again) or stops holds no table any more: no cell has run in it.
  kernel.onState(() => {
    if (kernel.state !== "starting" && kernel.state !== "off") return;
    let any = false;
    for (const [name, record] of records) {
      if (record.code === null) continue;
      records.set(name, { code: null, at: null, opened: record.opened });
      any = true;
    }
    if (any) redraw();
    // An HTML cell's names were that kernel's variables: it has not run in the new one.
    for (const cell of cells) {
      if ((cell.kind !== "html" && cell.kind !== "markdown") || !cell.htmlRun || cell.htmlRun.code === null) continue;
      cell.htmlRun = { ...cell.htmlRun, code: null, at: null, changed: [] };
      drawHtmlState(cell);
    }
  });
  // A run ended: a variable an HTML cell names may have changed.
  kernel.onState(() => {
    if (kernel.state !== "idle") return;
    if (marksTimer !== null) window.clearTimeout(marksTimer);
    marksTimer = window.setTimeout(() => {
      marksTimer = null;
      void checkMarks();
    }, 300);
  });
  // A click inside a design goes to the design; its cell is the selected one from then on.
  const designClicked = (): void => {
    setTimeout(() => {
      const frame = document.activeElement;
      const cell = frame instanceof HTMLIFrameElement ? cells.find((c) => c.element.contains(frame)) : undefined;
      if (cell) select(cell);
    }, 0);
  };
  window.addEventListener("blur", designClicked);

  for (const data of initial.length ? initial : [empty()]) make(data, cells.length);
  building = false;
  redraw();
  if (cells.some((c) => c.role)) void arrange(true);

  const at = (index?: number): Cell | null => (index === undefined ? selected ?? cells[0] ?? null : cells[index] ?? null);
  return {
    relint: () => {
      for (const c of cells) c.editor?.lint();
    },
    flowCells: () =>
      cells
        .filter((c) => !isApp(c.role) && !isHeading(c.role))
        .map((c) => ({ number: c.number, kind: c.kind, source: sourceOf(c), ran: c.ranSource, order: c.runOrder, name: c.name })),
    markFlow: (states) => {
      const by = new Map(states.map((s) => [s.number, s]));
      for (const c of cells) {
        const said = by.get(c.number);
        const state = said?.state ?? "current";
        const words = state === "edited" ? "edited" : state === "outOfDate" ? "out of date" : "";
        c.flow.textContent = words;
        c.flow.title = state === "outOfDate" && said?.because.length ? `Made again since it ran: ${said.because.join(", ")}` : "";
        c.flow.hidden = !words;
        c.element.classList.toggle("flow-stale", !!words);
      }
    },
    runUpTo: async (number) => {
      const cell = number === undefined ? selected : byNumber(number);
      if (!cell) throw new Error(number === undefined ? "Select a cell first." : `This notebook has no cell ${number}.`);
      await runUpTo(cell);
    },
    present: (on) => {
      presenting = on ?? !presenting;
      list.classList.toggle("presenting", presenting);
      if (presenting) for (const c of cells) if (c.kind === "markdown" && !c.element.classList.contains("rendered")) showMarkdown(c);
      // A code cell shows only what it drew: one that drew nothing is left out of the document.
      for (const c of cells) {
        const drew = !!c.area.element.textContent?.trim() || !!c.area.element.querySelector("img, svg, iframe, canvas, table");
        c.element.classList.toggle("present-empty", presenting && c.kind !== "markdown" && c.kind !== "html" && !drew);
      }
      return presenting;
    },
    element: list,
    cells: () => cells.map(dataOf),
    add: (kind, source = "", first = false) => void insertAt(first ? 0 : selected ? indexOf(selected) + 1 : cells.length, kind, source),
    insert: (where, kind = "code", source = "") => {
      const here = selected ? indexOf(selected) : cells.length - 1;
      insertAt(where === "above" ? here : here + 1, kind, source);
    },
    runAll: () => runEach([...cells]),
    runCell: async (index) => {
      const cell = at(index);
      if (!cell) throw new Error(`There is no cell ${index === undefined ? "selected" : index + 1}.`);
      select(cell);
      return run(cell);
    },
    runAbove: () => runEach(selected ? cells.slice(0, indexOf(selected)) : []),
    runBelow: () => runEach(selected ? cells.slice(indexOf(selected)) : [...cells]),
    selected: () => (selected ? indexOf(selected) : -1),
    selectedNumber: () => selected?.number ?? null,
    insertCode: (insert) => {
      let cell = selected && !isApp(selected.role) ? selected : null;
      const code = cell?.kind === "sql" ? insert.sql : cell?.kind === "code" ? insert.python : undefined;
      if (!cell || code === undefined) {
        const kind: CellKind = insert.python === undefined ? "sql" : "code";
        cell = insertAt(cell ? indexOf(cell) + 1 : selected ? indexOf(selected) + 1 : cells.length, kind);
      }
      const text = (cell.kind === "sql" ? insert.sql : insert.python) ?? "";
      if (!sourceOf(cell).trim()) {
        if (cell.editor) cell.editor.setValue(text);
        else cell.source = text;
      } else if (cell.editor) cell.editor.insertAt(text);
      else cell.source = `${cell.source.replace(/\n*$/, "")}\n${text}`;
      select(cell);
      edited();
      typedSoon();
      return { cell: cell.number, kind: cell.kind };
    },
    select: (index, editIt = false) => {
      const cell = cells[index];
      if (!cell) throw new Error(`There is no cell ${index + 1}: the notebook has ${cells.length}.`);
      cell.element.scrollIntoView({ block: "nearest" });
      if (editIt) edit(cell);
      else toCommandMode(cell);
    },
    remove: (index) => {
      const cell = at(index);
      if (cell) removeCell(cell);
    },
    move: (by) => {
      if (selected) moveCell(selected, by);
    },
    setKind: (kind) => {
      if (selected) setKind(selected, kind);
    },
    setConnection: (name) => {
      if (!selected || !hasSource(selected.kind)) return;
      selected.connection = name || null;
      selected.connectionPicker.dispatchEvent(new Event("focus")); // drawn again, with this one picked
      edited();
    },
    duplicate: () => {
      if (selected) duplicate(selected);
    },
    clearOutput: (index) => {
      const cell = at(index);
      if (cell) clearOutput(cell);
    },
    clearAll: () => {
      for (const c of cells) clearOutput(c);
    },
    toggleOutput: () => {
      if (selected) toggleOutput(selected);
    },
    commandMode: () => {
      if (selected) toCommandMode(selected);
    },
    undo,
    helpAtCursor: async () => {
      const cell = selected;
      if (!cell?.editor || cell.kind !== "code") return "";
      return kernel.help(cell.editor.value(), cell.editor.cursorOffset());
    },
    setTheme: (t) => {
      for (const c of cells) c.editor?.setTheme(t);
    },
    setTables: (tables) => {
      tableInfos = tables;
      // A table opened again whose cell came with the file: the grid gets its steps back first, and
      // the cell follows the grid from then on.
      for (const info of tables) {
        const cell = tableCell(info.name);
        if (info.grid && !info.step_list.length && cell?.steps?.length && cameWithFile.has(info.name) && !restored.has(info.name)) {
          restored.add(info.name);
          hooks.restoreSteps?.(info.grid, cell.steps);
          return; // the grid's change brings the tables back here
        }
        restored.add(info.name);
      }
      void arrange(true);
    },
    holdsTable: (name) => !!tableCell(name),
    tables: () =>
      cells
        .filter((c) => c.role === "transformations" && c.table)
        .map((c) => {
          const state = stateOf(c);
          const line = lineOf(c.table);
          return { name: c.table!, cell: c.number, maker: line?.maker ?? null, moved: c.grouped, note: line?.note ?? null, steps: line?.steps ?? null, open: !!infoOf(c.table), code: sourceOf(c), state: state.kind, label: state.label };
        }),
    runTable: async (name) => {
      const cell = tableCell(name);
      if (!cell) throw new Error(`This notebook has no table named ${name}.`);
      return run(cell);
    },
    runOutOfDate: async () => {
      let ran = 0;
      for (const cell of cells.filter((c) => c.role === "transformations")) {
        if (!stateOf(cell).runnable) continue;
        ran++;
        if (!(await run(cell))) break;
      }
      return ran;
    },
    goTo,
    nextCell: () => nextNumber,
    foldTables: (folded, table) => {
      if (table) {
        if (folded) unfolded.delete(table);
        else {
          unfolded.add(table);
          groupFolded = false;
        }
      } else groupFolded = folded;
      redraw();
    },
    renameTable: (from, to) => {
      for (const c of cells) if (c.table === from) c.table = to;
      const record = records.get(from);
      if (record) records.set(to, record);
      records.delete(from);
    },
    // A Markdown cell with names runs as an HTML cell does (text cells on the canvas, 2026-11-15).
    htmlCells: () => cells.filter(filledCell).map(htmlReport),
    runHtml: async (number) => {
      const some = number === undefined ? cells.filter((c) => filledCell(c) && htmlStateOf(c).runnable) : cells.filter((c) => filledCell(c) && c.number === number);
      if (number !== undefined && !some.length) throw new Error(`This notebook has no HTML cell (or Markdown cell with names) ${number}.`);
      for (const cell of some) {
        if (!(await run(cell))) break;
      }
      return some.map(htmlReport);
    },
    resizeHtml: (number, height) => {
      const cell = cells.find((c) => c.kind === "html" && c.number === number);
      if (!cell?.design) throw new Error(`This notebook has no HTML cell ${number}.`);
      cell.design.setHeight(height);
      edited();
    },
    editSelected: () => {
      if (selected) edit(selected);
    },
    copy: (number) => {
      const cell = number === undefined ? selected : byNumber(number);
      if (!cell) throw new Error(number === undefined ? "No cell is selected." : `This notebook has no cell ${number}.`);
      return copy(cell);
    },
    paste: () => paste(selected),
    nameCell: (number, name) => {
      const cell = number === undefined ? selected : byNumber(number);
      if (!cell || !cell.nameButton) throw new Error(number === undefined ? "No cell is selected." : `This notebook has no cell ${number} of yours.`);
      setName(cell, name);
      return { cell: cell.number, name: cell.name };
    },
    editName: () => {
      if (selected) editName(selected);
    },
    indexOfNumber: (number) => cells.findIndex((c) => c.number === number),
    setSource: (number, source) => {
      const cell = byNumber(number);
      if (!cell || isApp(cell.role)) throw new Error(`This notebook has no cell ${number} of yours.`);
      if (cell.editor) cell.editor.setValue(source);
      else cell.source = source;
      edited();
      typedSoon();
    },
    editSource: (number, source) => {
      const cell = byNumber(number);
      if (!cell || isApp(cell.role)) throw new Error(`This notebook has no cell ${number} of yours.`);
      if (cell.editor) cell.editor.replaceText(source);
      else cell.source = source;
      edited();
      typedSoon();
    },
    sourceOf: (number) => {
      const cell = byNumber(number);
      return cell && !isApp(cell.role) ? sourceOf(cell) : null;
    },
    setCellConnection: (number, name) => {
      const cell = byNumber(number);
      if (!cell || isApp(cell.role) || !hasSource(cell.kind)) throw new Error(`This notebook has no SQL or DAX cell ${number} of yours.`);
      cell.connection = name || null;
      cell.connectionPicker.dispatchEvent(new Event("focus")); // drawn again, with this one picked
      edited();
    },
    appendNamed: (source, name, kind = "code", connection = null) => {
      const cell = insertAt(cells.length, kind, source);
      if (connection) cell.connection = connection;
      setName(cell, name);
      return cell.number;
    },
    insertSnippet,
    insertSnippetHere: () => {
      if (!selected || !snippetLanguage(selected)) return errorHere("Select a Python, DAX or HTML cell of yours first.");
      void insertSnippetInto(selected);
    },
    dispose: () => {
      disposed = true;
      window.removeEventListener("blur", designClicked);
      if (quiet !== null) window.clearTimeout(quiet);
      if (marksTimer !== null) window.clearTimeout(marksTimer);
      quiet = marksTimer = null;
      for (const cell of cells) {
        cell.editor?.dispose();
        cell.design?.dispose();
      }
    },
  };
}
