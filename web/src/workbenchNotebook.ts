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
 * The notebook is in parts (the craft review of 2026-11-22, refactor 8): its state is one record
 * (workbenchNotebookState.ts) handed to each part: the cells' text faces (…Text), the Tables group (…Tables),
 * runs (…Runs), edits (…Edits), snippets (…Snippets), errors (…Errors), one cell made and drawn (…Cell),
 * command mode's keys (…Keys), Notebook mode (…Mode). This file is the view: the state made, the listeners,
 * and what the page and the agent ask of a notebook.
 *
 * ROUTING: POST /workbench/tables/arrange (the rules are the server's: domain/table_cells.py)
 */
import { onConnectionColours } from "./connectionColours";
import { h } from "./dom";
import { errorHere } from "./errorNote";
import { hasSource, isApp, snippetLanguage } from "./notebookCells";
import { pythonCompleter } from "./workbenchCompletion";
import type { Kernel } from "./workbenchKernel";
import { make } from "./workbenchNotebookCell";
import { clearOutput, copy, duplicate, edit, editName, insertAt, moveCell, paste, removeCell, setKind, setName, toggleOutput, undo } from "./workbenchNotebookEdits";
import { commandKeys } from "./workbenchNotebookKeys";
import { flowCells, markFlow, present } from "./workbenchNotebookMode";
import { run, runEach, runUpTo } from "./workbenchNotebookRuns";
import { insertCode, insertSnippet, insertSnippetInto } from "./workbenchNotebookSnippets";
import { byNumber, type Cell, type CellData, type CellKind, connectionsSoon, dataOf, edited, empty, filledCell, type FlowCell, type HtmlReport, indexOf, type Notebook, type NotebookHooks, select, sourceOf, tableCell, type TableReport, toCommandMode } from "./workbenchNotebookState";
import { arrange, foldTables, forgetRuns, goTo, redraw, renameTable, runOutOfDate, setTables, tableReports, typedSoon } from "./workbenchNotebookTables";
import { forgetHtmlRuns, htmlReport, htmlStateOf, marksSoon } from "./workbenchNotebookText";
import type { TableInfo } from "./workbenchTables";

export type { CellData, CellKind, FlowCell, HtmlReport, TableReport } from "./workbenchNotebookState";
export { sqlLine } from "./notebookCells";

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

/** A new notebook's state: no cell yet, nothing selected, the Tables group unfolded. */
function newNotebook(initial: CellData[], kernel: Kernel, connections: () => string[], theme: () => string, changed: () => void, python: Notebook["python"], hooks: NotebookHooks): Notebook {
  const nb: Notebook = {
    list: h("div", { class: "wb-cells", role: "list", "aria-label": "Cells" }),
    cells: [],
    kernel,
    hooks,
    connections,
    theme,
    dark: () => theme().endsWith("dark"),
    changed,
    python,
    inlineKey: `nb-${Math.random().toString(36).slice(2, 10)}`,
    selected: null,
    undos: [],
    pendingD: 0,
    runs: 0,
    presenting: false,
    namedHosts: new WeakMap(),
    nextNumber: Math.max(hooks.nextCell ?? 1, 1 + Math.max(0, ...initial.map((c) => c.number ?? 0))),
    tableInfos: [],
    tableLines: [],
    records: new Map(),
    restored: new Set(),
    cameWithFile: new Set(),
    groupFolded: false,
    unfolded: new Set(),
    seenTables: new Set(),
    autoRan: new Set(),
    version: 0,
    asked: 0,
    quiet: null,
    building: true,
    disposed: false,
    marking: 0,
    markTimer: undefined,
    marksTimer: null,
    kept: new WeakMap(),
    act: { run: (cell) => run(nb, cell), make: (data, at) => make(nb, data, at) },
  };
  return nb;
}

export function notebookView(
  initial: CellData[],
  kernel: Kernel,
  connections: () => string[],
  theme: () => string,
  changed: () => void,
  blades: () => string[] = () => [],
  codeNames: () => { name: string; connection: string; kind: string }[] = () => [],
  hooks: NotebookHooks = {},
): NotebookView {
  const python = pythonCompleter(kernel, () => ({ connections: connections(), blades: blades(), codeNames: codeNames() }));
  const nb = newNotebook(initial, kernel, connections, theme, changed, python, hooks);
  const { cells } = nb;
  // Connection colours (connectionColours.ts): a cell that names a connection (%%sql, %%dax, sab.sql,
  // sab.read, sab.dax, sab.blade, sab.connection; a table's read-only cell by its load) wears its colour,
  // two connections two marks. The server reads the cells (ast); nothing runs.
  onConnectionColours(() => {
    if (nb.list.isConnected) connectionsSoon(nb);
  });
  commandKeys(nb);
  // A kernel that starts (again) or stops holds no table any more: no cell has run in it.
  kernel.onState(() => {
    if (kernel.state !== "starting" && kernel.state !== "off") return;
    forgetRuns(nb);
    forgetHtmlRuns(nb);
  });
  // A run ended: a variable an HTML cell names may have changed.
  kernel.onState(() => {
    if (kernel.state === "idle") marksSoon(nb);
  });
  // A click inside a design goes to the design; its cell is the selected one from then on.
  const designClicked = (): void => {
    setTimeout(() => {
      const frame = document.activeElement;
      const cell = frame instanceof HTMLIFrameElement ? cells.find((c) => c.element.contains(frame)) : undefined;
      if (cell) select(nb, cell);
    }, 0);
  };
  window.addEventListener("blur", designClicked);

  for (const data of initial.length ? initial : [empty()]) make(nb, data, cells.length);
  nb.building = false;
  redraw(nb);
  if (cells.some((c) => c.role)) void arrange(nb, true);

  const at = (index?: number): Cell | null => (index === undefined ? nb.selected ?? cells[0] ?? null : cells[index] ?? null);
  /** The cell with this number, or the selected one; `what` ends the sentence when there is none. */
  const numbered = (number: number | undefined, what = ""): Cell => {
    const cell = number === undefined ? nb.selected : byNumber(nb, number);
    if (!cell) throw new Error(number === undefined ? "No cell is selected." : `This notebook has no cell ${number}${what}.`);
    return cell;
  };
  /** A cell of the user's by its number. */
  const own = (number: number, what = "cell"): Cell => {
    const cell = byNumber(nb, number);
    if (!cell || isApp(cell.role)) throw new Error(`This notebook has no ${what} ${number} of yours.`);
    return cell;
  };
  /** A SQL or DAX cell put on a connection (or a dataset): its picker drawn again, with this one picked. */
  const connect = (cell: Cell, name: string): void => {
    cell.connection = name || null;
    cell.connectionPicker.dispatchEvent(new Event("focus"));
    edited(nb);
  };
  const write = (cell: Cell, source: string, how: "setValue" | "replaceText"): void => {
    if (cell.editor) cell.editor[how](source);
    else cell.source = source;
    edited(nb);
    typedSoon(nb);
  };
  // A Markdown cell with names runs as an HTML cell does (text cells on the canvas, 2026-11-15).
  const filled = (): Cell[] => cells.filter(filledCell);
  return {
    relint: () => {
      for (const c of cells) c.editor?.lint();
    },
    flowCells: () => flowCells(nb),
    markFlow: (states) => markFlow(nb, states),
    runUpTo: async (number) => {
      const cell = number === undefined ? nb.selected : byNumber(nb, number);
      if (!cell) throw new Error(number === undefined ? "Select a cell first." : `This notebook has no cell ${number}.`);
      await runUpTo(nb, cell);
    },
    present: (on) => present(nb, on),
    element: nb.list,
    cells: () => cells.map(dataOf),
    add: (kind, source = "", first = false) => void insertAt(nb, first ? 0 : nb.selected ? indexOf(nb, nb.selected) + 1 : cells.length, kind, source),
    insert: (where, kind = "code", source = "") => {
      const here = nb.selected ? indexOf(nb, nb.selected) : cells.length - 1;
      insertAt(nb, where === "above" ? here : here + 1, kind, source);
    },
    runAll: () => runEach(nb, [...cells]),
    runCell: async (index) => {
      const cell = at(index);
      if (!cell) throw new Error(`There is no cell ${index === undefined ? "selected" : index + 1}.`);
      select(nb, cell);
      return run(nb, cell);
    },
    runAbove: () => runEach(nb, nb.selected ? cells.slice(0, indexOf(nb, nb.selected)) : []),
    runBelow: () => runEach(nb, nb.selected ? cells.slice(indexOf(nb, nb.selected)) : [...cells]),
    selected: () => (nb.selected ? indexOf(nb, nb.selected) : -1),
    selectedNumber: () => nb.selected?.number ?? null,
    insertCode: (insert) => insertCode(nb, insert),
    select: (index, editIt = false) => {
      const cell = cells[index];
      if (!cell) throw new Error(`There is no cell ${index + 1}: the notebook has ${cells.length}.`);
      cell.element.scrollIntoView({ block: "nearest" });
      if (editIt) edit(nb, cell);
      else toCommandMode(nb, cell);
    },
    remove: (index) => {
      const cell = at(index);
      if (cell) removeCell(nb, cell);
    },
    move: (by) => {
      if (nb.selected) moveCell(nb, nb.selected, by);
    },
    setKind: (kind) => {
      if (nb.selected) setKind(nb, nb.selected, kind);
    },
    setConnection: (name) => {
      if (nb.selected && hasSource(nb.selected.kind)) connect(nb.selected, name);
    },
    duplicate: () => {
      if (nb.selected) duplicate(nb, nb.selected);
    },
    clearOutput: (index) => {
      const cell = at(index);
      if (cell) clearOutput(nb, cell);
    },
    clearAll: () => {
      for (const c of cells) clearOutput(nb, c);
    },
    toggleOutput: () => {
      if (nb.selected) toggleOutput(nb.selected);
    },
    commandMode: () => {
      if (nb.selected) toCommandMode(nb, nb.selected);
    },
    undo: () => undo(nb),
    helpAtCursor: async () => {
      const cell = nb.selected;
      if (!cell?.editor || cell.kind !== "code") return "";
      return kernel.help(cell.editor.value(), cell.editor.cursorOffset());
    },
    setTheme: (t) => {
      for (const c of cells) c.editor?.setTheme(t);
    },
    setTables: (tables) => setTables(nb, tables),
    holdsTable: (name) => !!tableCell(nb, name),
    tables: () => tableReports(nb),
    runTable: async (name) => {
      const cell = tableCell(nb, name);
      if (!cell) throw new Error(`This notebook has no table named ${name}.`);
      return run(nb, cell);
    },
    runOutOfDate: () => runOutOfDate(nb),
    goTo: (number, line) => goTo(nb, number, line),
    nextCell: () => nb.nextNumber,
    foldTables: (folded, table) => foldTables(nb, folded, table),
    renameTable: (from, to) => renameTable(nb, from, to),
    htmlCells: () => filled().map((c) => htmlReport(nb, c)),
    runHtml: async (number) => {
      const some = number === undefined ? filled().filter((c) => htmlStateOf(c).runnable) : filled().filter((c) => c.number === number);
      if (number !== undefined && !some.length) throw new Error(`This notebook has no HTML cell (or Markdown cell with names) ${number}.`);
      for (const cell of some) {
        if (!(await run(nb, cell))) break;
      }
      return some.map((c) => htmlReport(nb, c));
    },
    resizeHtml: (number, height) => {
      const cell = cells.find((c) => c.kind === "html" && c.number === number);
      if (!cell?.design) throw new Error(`This notebook has no HTML cell ${number}.`);
      cell.design.setHeight(height);
      edited(nb);
    },
    editSelected: () => {
      if (nb.selected) edit(nb, nb.selected);
    },
    copy: (number) => copy(numbered(number)),
    paste: () => paste(nb, nb.selected),
    nameCell: (number, name) => {
      const cell = numbered(number, " of yours");
      if (!cell.nameButton) throw new Error(number === undefined ? "No cell is selected." : `This notebook has no cell ${number} of yours.`);
      setName(nb, cell, name);
      return { cell: cell.number, name: cell.name };
    },
    editName: () => {
      if (nb.selected) editName(nb, nb.selected);
    },
    indexOfNumber: (number) => cells.findIndex((c) => c.number === number),
    setSource: (number, source) => write(own(number), source, "setValue"),
    editSource: (number, source) => write(own(number), source, "replaceText"),
    sourceOf: (number) => {
      const cell = byNumber(nb, number);
      return cell && !isApp(cell.role) ? sourceOf(cell) : null;
    },
    setCellConnection: (number, name) => {
      const cell = own(number, "SQL or DAX cell");
      if (!hasSource(cell.kind)) throw new Error(`This notebook has no SQL or DAX cell ${number} of yours.`);
      connect(cell, name);
    },
    appendNamed: (source, name, kind = "code", connection = null) => {
      const cell = insertAt(nb, cells.length, kind, source);
      if (connection) cell.connection = connection;
      setName(nb, cell, name);
      return cell.number;
    },
    insertSnippet: (name, values, number) => insertSnippet(nb, name, values, number),
    insertSnippetHere: () => {
      if (!nb.selected || !snippetLanguage(nb.selected)) return errorHere("Select a Python, DAX or HTML cell of yours first.");
      void insertSnippetInto(nb, nb.selected);
    },
    dispose: () => {
      nb.disposed = true;
      window.removeEventListener("blur", designClicked);
      if (nb.quiet !== null) window.clearTimeout(nb.quiet);
      if (nb.marksTimer !== null) window.clearTimeout(nb.marksTimer);
      nb.quiet = nb.marksTimer = null;
      for (const cell of cells) {
        cell.editor?.dispose();
        cell.design?.dispose();
      }
    },
  };
}
