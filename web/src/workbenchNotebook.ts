/**
 * workbenchNotebook.ts: a notebook in the Workbench: cells of Python, SQL on a connection, DAX on a
 * Power BI workspace's dataset, HTML, Streamlit or Markdown, run in the document's IPython kernel. [WIRE]
 *
 *   [CELL]     its kind (Python, SQL, DAX, HTML, Streamlit, Markdown); a SQL cell's connection, a DAX cell's
 *              dataset (`Finance/Sales model`: only Power BI workspaces' datasets); Run; More: run above, run
 *              below, insert above or below, duplicate, clear or hide its output; move up and down; delete
 *   [EDIT]     Shift+Enter runs and goes to the next cell (a new one after the last); Ctrl+Enter runs in
 *              place; Escape leaves the editor for command mode; a Markdown cell shows as text until
 *              double-clicked (or Enter)
 *   [COMMAND]  Jupyter's keys on the selected cell: Enter edits; A and B insert above and below; D D
 *              deletes; Y, M, S, X, H and T make it Python, Markdown, SQL, DAX, HTML or Streamlit; J and K (or Down and Up) move the
 *              selection; Z undoes a delete or move; Shift+Enter and Ctrl+Enter run
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
 *              the group. A changed cell turns yellow (Out of date · Run); nothing runs by itself
 *   [USES]     one of the user's cells that names a table starts with `# uses orders @cell3`, kept by
 *              the app as they type
 *   [HTML]     an HTML cell (docs/ideas.md, 2026-11-14; workbenchHtml.ts) has two faces: its HTML in the
 *              editor while it is being edited, the design when it is not. It draws by itself when the
 *              editor is left; `{{ name }}` is filled from the kernel when the cell runs, and such a
 *              cell turns yellow (Out of date · Run) when its HTML or a variable it names changes. A
 *              click inside the design goes to the design (its buttons work): the cell's head, its Edit
 *              button or Enter open the HTML
 *   [STREAMLIT] a Streamlit cell (docs/ideas.md, 2026-11-15; workbenchStreamlit.ts) is a piece of a page:
 *              Python that draws with st.*. It has two faces too: its code while it is edited, the piece
 *              live (its widgets working) when it is not. It runs in the document's Streamlit app, not in
 *              the kernel; it turns yellow when its code or a table it names changes. Push to page sends
 *              it to the page designer
 *
 * ROUTING: POST /workbench/tables/arrange (the rules are the server's: domain/table_cells.py)
 */
import { api } from "./api";
import { button, clear, h, toast } from "./dom";
import type { CodeEditor } from "./lazy/codeEditor";
import { renderMarkdown } from "./markdown";
import { codeItem, currentDocument, sendToAgent } from "./workbenchAgent";
import { loadEditors } from "./workbenchConsole";
import { datasetsWanted, daxCompleter, isWorkspace, pythonCompleter, sqlCompleter } from "./workbenchCompletion";
import { type ErrorDetail, type Fix, type Frame, problemsFor, sqlProblems, yourFrame } from "./workbenchErrors";
import { type Kernel, runInto } from "./workbenchKernel";
import { changedNames, type DesignPane, designPane, fillHtml, htmlNames, type HtmlRun, htmlState, type HtmlState, runFromOutputs, runHtml } from "./workbenchHtml";
import { type ErrorHooks, type Output, type OutputArea, outputArea, resultName } from "./workbenchOutputs";
import { PIECE_HEIGHT, type PieceTools, pieceTools, pieceView, type PieceSource, type StreamlitHost } from "./workbenchStreamlit";
import { type ArrangedCell, firstLine, groupLineText, noteParts, type RunRecord, type TableInfo, type TableLine, tableLineText, type TableState, tableState, type UsesForm, withUses } from "./workbenchTables";

/** A SQL cell's first line as the kernel runs it (domain/notebooks.py sql_line). */
export function sqlLine(connection: string | null): string {
  if (!connection) return "%%sql";
  return /\s/.test(connection) ? `%%sql '${connection.replace(/'/g, "'\"'\"'")}'` : `%%sql ${connection}`;
}

export type CellKind = "code" | "sql" | "dax" | "html" | "streamlit" | "markdown";
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
  /** An HTML or Streamlit cell's pane, in pixels (null: the design's own height, the usual one). */
  height?: number | null;
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

interface Cell extends Omit<CellData, "outputs" | "number" | "role" | "table" | "grouped" | "steps" | "height"> {
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
  count: HTMLElement;
  kindPicker: HTMLSelectElement;
  connectionPicker: HTMLSelectElement;
  /** Give it the keyboard once its editor exists, unless the focus went elsewhere meanwhile. */
  wantsFocus: boolean;
  /** An HTML cell's design, or a Streamlit cell's live piece (null: a heading). */
  design: DesignPane | null;
  /** A Streamlit cell's own tools in its pane's bar. */
  tools: PieceTools | null;
  editorHost: HTMLElement;
  /** What an HTML cell's last run gave. */
  htmlRun: HtmlRun | undefined;
  /** What the design left out, and the names the kernel does not hold. */
  htmlNotes: string[];
  /** Counts the design's drawings: an older one that answers late is dropped. */
  drawn: number;
}

/** What Undo puts back. */
type Undo = { kind: "delete"; data: CellData; at: number; filler: Cell | null } | { kind: "move"; cell: Cell; from: number };

const LANGUAGE: Record<CellKind, "python" | "sql" | "dax" | "markdown" | "html"> = { code: "python", sql: "sql", dax: "dax", markdown: "markdown", html: "html", streamlit: "python" };
const KIND_NAMES: Record<CellKind, string> = { code: "Python", sql: "SQL", dax: "DAX", html: "HTML", streamlit: "Streamlit", markdown: "Markdown" };
const KINDS: CellKind[] = ["code", "sql", "dax", "html", "streamlit", "markdown"];
/** The kinds with two faces: the code while it is edited, what it draws when it is not. */
const drawn = (kind: CellKind): boolean => kind === "html" || kind === "streamlit";
// A DAX cell names its dataset's own tables, never the kernel's: it gets no uses line (a `-- uses` one it has goes).
const usesForm = (kind: CellKind): UsesForm => (kind === "sql" || kind === "dax" ? "sql" : kind === "html" ? "html" : "python");
/** A cell that runs on a source picked in its head: SQL on a connection, DAX on a dataset. */
const hasSource = (kind: CellKind): kind is "sql" | "dax" => kind === "sql" || kind === "dax";
const empty = (kind: CellKind = "code", connection: string | null = null): CellData => ({ kind, source: "", connection, outputs: [], execution_count: null });

export interface NotebookView {
  element: HTMLElement;
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
  /** Go to the cell with this number (false: there is none). */
  goTo: (number: number) => boolean;
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
  /** Its Streamlit cells, in order: each a piece of the document's app. */
  pieces: () => PieceSource[];
  /** The app's state changed: each Streamlit cell is drawn again. */
  drawPieces: () => void;
  /** Size a Streamlit cell's pane (null: the usual height). */
  resizePiece: (number: number, height: number | null) => void;
  /** The place (from 0) of the cell with this number, or -1. */
  indexOfNumber: (number: number) => number;
}

const isApp = (role: string): boolean => role === "tables" || role === "table" || role === "transformations";
const isHeading = (role: string): boolean => role === "tables" || role === "table";

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
    /** The document's Streamlit app, for its Streamlit cells. */
    streamlit?: StreamlitHost;
    /** What a DAX cell runs on: each Power BI workspace's datasets, as `Finance/Sales model`. */
    datasets?: () => string[];
  } = {},
): NotebookView {
  const datasets = (): string[] => hooks.datasets?.() ?? [];
  /** The sources a cell of this kind picks from. */
  const sources = (kind: CellKind): string[] => (kind === "dax" ? datasets() : connections());
  const python = pythonCompleter(kernel, () => ({ connections: connections(), blades: blades(), codeNames: codeNames() }));
  const list = h("div", { class: "wb-cells", role: "list", "aria-label": "Cells" });
  const cells: Cell[] = [];
  let selected: Cell | null = null;
  const undos: Undo[] = [];
  let pendingD = 0; // the first D of D D, and when
  const dark = (): boolean => theme().endsWith("dark");
  const indexOf = (cell: Cell): number => cells.indexOf(cell);
  // ----- numbers, tables
  let nextNumber = Math.max(hooks.nextCell ?? 1, 1 + Math.max(0, ...initial.map((c) => c.number ?? 0)));
  let tableInfos: TableInfo[] = [];
  let tableLines: TableLine[] = [];
  const records = new Map<string, RunRecord>();
  const restored = new Set<string>();
  const cameWithFile = new Set<string>(); // the tables whose cell the file (or a reload) brought
  let groupFolded = true; // the group starts folded when a file opens
  const unfolded = new Set<string>(); // the tables opened
  let version = 0; // counts every change: an arrangement worked out for an older one is dropped
  let asked = 0;
  let quiet: number | null = null;
  let building = true;
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
    if (hadPieces || cells.some((c) => c.kind === "streamlit")) {
      hadPieces = cells.some((c) => c.kind === "streamlit");
      hooks.streamlit?.changed();
    }
  };
  let hadPieces = false;

  const label = (cell: Cell): string => `Cell ${indexOf(cell) + 1} of ${cells.length}, ${KIND_NAMES[cell.kind]}`;
  const relabel = (): void => {
    for (const c of cells) c.element.setAttribute("aria-label", label(c));
  };

  const select = (cell: Cell): void => {
    if (selected && selected !== cell) selected.element.classList.remove("selected");
    selected = cell;
    cell.element.classList.add("selected");
  };

  const showMarkdown = (cell: Cell): void => {
    cell.view.replaceChildren(renderMarkdown(cell.editor?.value() ?? cell.source));
    cell.element.classList.add("rendered");
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

  /** Run an HTML cell: plain HTML only draws; with names, each is read from the kernel's variables. */
  const runHtmlCell = async (cell: Cell): Promise<boolean> => {
    const html = cell.source;
    cell.area.set([]);
    if (!html.trim()) return true;
    if (!htmlNames(html).length) {
      showDesign(cell);
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
      showDesign(cell);
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
    const ran = cells.filter((c) => c.kind === "html" && c.htmlRun && c.htmlRun.code !== null);
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

  // ===== Streamlit cells: the piece live, its state, its run =====

  const pane = (kind: CellKind, height: number | null, cell: () => Cell): { design: DesignPane; tools: PieceTools | null } => {
    const tools = kind === "streamlit" ? pieceTools(hooks.streamlit, () => cell().number) : null;
    const design = designPane({
      dark,
      height: drawn(kind) ? height : null,
      resized: () => edited(),
      run: () => void run(cell()),
      ...(tools ? { fit: PIECE_HEIGHT, tools: tools.elements } : {}),
    });
    return { design, tools };
  };

  /** Draw a Streamlit cell from the app's state: the piece live once it has run, what needs doing. */
  const drawPiece = (cell: Cell): void => {
    if (cell.kind !== "streamlit" || !cell.design) return;
    const view = pieceView(hooks.streamlit?.state() ?? null, cell.number, !!sourceOf(cell).trim());
    cell.design.showAddress(view.address);
    cell.design.setState(view.state, view.notes);
    cell.tools?.draw(view);
    cell.part.textContent = view.part;
    cell.element.classList.toggle("stale", view.state.kind === "outOfDate");
    // Its code shows while it is being edited, and while there is nothing to show yet.
    if (!view.address) cell.element.classList.remove("rendered");
    else if (!cell.editorHost.contains(document.activeElement)) cell.element.classList.add("rendered");
  };

  /** Run the document's Streamlit app (every piece: they share it). */
  const runPieces = async (from: Cell | null): Promise<boolean> => {
    const some = cells.filter((c) => c.kind === "streamlit");
    for (const c of some) c.element.classList.add("running");
    try {
      const ok = hooks.streamlit ? await hooks.streamlit.run() : false;
      if (from) from.element.classList.toggle("failed", !ok);
      if (ok && from && sourceOf(from).trim()) {
        toCommandMode(from); // out of the code: the piece shows
        drawPiece(from);
      }
      return ok;
    } catch (e) {
      toast((e as Error).message, "error");
      return false;
    } finally {
      for (const c of some) c.element.classList.remove("running");
    }
  };

  const run = async (cell: Cell): Promise<boolean> => {
    if (cell.editor) cell.source = cell.editor.value();
    for (const c of cells) c.editor?.setProblems([]); // the last failure's marks describe code that ran before
    if (isHeading(cell.role)) return true;
    if (cell.kind === "markdown") {
      showMarkdown(cell);
      return true;
    }
    if (cell.role === "transformations") return runTransformations(cell);
    if (cell.kind === "html") return runHtmlCell(cell);
    if (cell.kind === "streamlit") return runPieces(cell);
    if (!cell.source.trim()) return true;
    cell.area.set([]);
    cell.element.classList.remove("output-hidden");
    cell.count.textContent = "[*]";
    cell.element.classList.add("running");
    try {
      const done = await runInto(kernel, { code: cell.source, kind: hasSource(cell.kind) ? cell.kind : "code", connection: cell.connection }, cell.area);
      cell.execution_count = done.execution_count;
      cell.count.textContent = done.error ? "[!]" : done.execution_count ? `[${done.execution_count}]` : "[ ]";
      cell.element.classList.toggle("failed", !done.ok);
      edited();
      // A calm moment: a cell that now makes a table joins the Tables group.
      if (done.ok && cell.kind === "code" && (tableInfos.length || cells.some((c) => c.role))) void arrange(true);
      return done.ok;
    } finally {
      cell.element.classList.remove("running");
    }
  };

  /** A table's read-only cell: run so that running it again changes nothing (it starts from the table
   *  as its maker made it: client/table_cells.py). */
  const runTransformations = async (cell: Cell): Promise<boolean> => {
    const code = sourceOf(cell);
    const table = cell.table ?? "";
    const variable = infoOf(table)?.variable ?? table.replace(/\W/g, "_");
    cell.area.set([]);
    cell.count.textContent = "[*]";
    cell.element.classList.add("running");
    try {
      const done = await runInto(kernel, { code, kind: "table", table: variable }, cell.area);
      cell.execution_count = done.execution_count;
      cell.count.textContent = done.error ? "[!]" : done.execution_count ? `[${done.execution_count}]` : "[ ]";
      cell.element.classList.toggle("failed", !done.ok);
      if (done.ok) records.set(table, { code, at: new Date(), opened: false });
      edited();
      redraw();
      return done.ok;
    } finally {
      cell.element.classList.remove("running");
    }
  };

  /** Run cells in order, stopping at the first that fails (or a stopped kernel), as Jupyter does. */
  const runEach = async (some: Cell[]): Promise<void> => {
    let pieces = false;
    for (const cell of some) {
      // The pieces run together, once, in the document's Streamlit app: after the cells before them.
      if (cell.kind === "streamlit" && sourceOf(cell).trim()) pieces = true;
      else if (!(await run(cell))) return;
    }
    if (pieces) await runPieces(null);
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
    const wasHtml = drawn(cell.kind);
    if (cell.design && (cell.kind === "streamlit" || kind === "streamlit")) {
      // A piece's pane has its own tools: the pane is made anew for the new kind.
      const made = pane(kind, null, () => cell);
      cell.design.element.replaceWith(made.design.element);
      cell.design.dispose();
      cell.design = made.design;
      cell.tools = made.tools;
    }
    cell.kind = kind;
    cell.kindPicker.value = kind;
    cell.part.textContent = "";
    cell.element.classList.remove("kind-code", "kind-sql", "kind-dax", "kind-markdown", "kind-html", "kind-streamlit", "stale");
    cell.element.classList.add(`kind-${kind}`);
    if (wasHtml || drawn(kind)) {
      // Its outputs were the other kind's: an HTML cell keeps a design, not a run's output.
      cell.element.classList.remove("rendered");
      cell.area.set([]);
      cell.htmlRun = undefined;
      cell.htmlNotes = [];
      setTimeout(() => cell.editor?.layout(), 0);
    }
    cell.connectionPicker.hidden = !hasSource(kind);
    // A SQL cell's connection is not a DAX cell's dataset: one that is not this kind's goes.
    if (hasSource(kind) && (!cell.connection || !sources(kind).includes(cell.connection))) cell.connection = sources(kind)[0] ?? null;
    // The box shows the connection the cell runs on (it is drawn again on focus; once showed the
    // %sql_connect placeholder while the cell ran on the first connection).
    if (hasSource(kind)) cell.connectionPicker.dispatchEvent(new Event("focus"));
    cell.editor?.setLanguage(LANGUAGE[kind]);
    relabel();
    edited();
    typedSoon();
    drawPiece(cell);
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
          if (!target.editor?.applyFix(fix, near)) toast(`${fix.target ?? "That"} is no longer in the cell.`, "error");
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
        if (fix.kind === "define" && fix.name) {
          const maker = definingCell(fix.name, running);
          if (maker) {
            void run(maker).then((ok) => ok && toast(`Ran cell ${indexOf(maker) + 1}`));
          } else toast(`No cell above defines ${fix.name}`, "error");
          return;
        }
        if (!hooks.fix?.(fix)) toast("Fix not available here", "error");
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
    const data: CellData = old ? { ...given, kind: "dax" } : given;
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
    });
    const view = h("div", { class: "wb-markdown-view" });
    const count = h("span", { class: "wb-count" }, data.execution_count ? `[${data.execution_count}]` : "[ ]");
    const kindPicker = h("select", { "aria-label": "Cell kind" }, ...KINDS.map((k) => h("option", { value: k, selected: k === data.kind }, KIND_NAMES[k]))) as HTMLSelectElement;
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
        dax ? (current ? null : h("option", { value: "" }, "")) : h("option", { value: "" }, "(%sql_connect)"),
        ...names.map((n) => h("option", { value: n, selected: n === current }, n)),
        ...(current && !names.includes(current) ? [h("option", { value: current, selected: true }, `${current} (not found)`)] : []),
      );
    };
    const more = button("More actions", () => cellMenu(cell, more), { icon: "more", iconOnly: true, class: "ghost" });
    const hiddenNote = h("button", { type: "button", class: "link wb-output-hidden", onclick: () => toggleOutput(cell) }, "Show output");
    const numberLabel = h("span", { class: "wb-number", title: `Cell ${number}: this number never changes. @cell${number} in a comment links here.` }, `#${number}`);
    const part = h("span", { class: "wb-part hint" });
    const status = role === "transformations" ? h("span", { class: "wb-table-state", role: "status" }) : null;
    const bar = isHeading(role) ? h("div", { class: "wb-group-bar" }) : null;
    const runButton = button("Run cell", () => void run(cell), { icon: "play", iconOnly: true, class: "ghost", title: "Run cell (Ctrl+Enter)" });
    // An HTML cell that shows its design: back to its HTML.
    const editButton = button("Edit HTML", () => edit(cell), { icon: "edit", iconOnly: true, class: "ghost wb-edit-html", title: "Edit the HTML (Enter)" });
    const { design, tools } = isHeading(role) ? { design: null, tools: null } : pane(data.kind, data.height ?? null, () => cell);
    const head =
      role === "transformations"
        ? h("div", { class: "wb-cell-head" }, numberLabel, count, part, h("span", { class: "spacer" }), status, runButton, button("Delete cell", () => removeCell(cell), { icon: "trash", iconOnly: true, class: "ghost wb-delete-table" }))
        : h(
            "div",
            { class: "wb-cell-head" },
            numberLabel,
            count,
            kindPicker,
            connectionPicker,
            part,
            h("span", { class: "spacer" }),
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
      tools,
      editorHost,
      htmlRun: data.kind === "html" ? runFromOutputs(data.outputs) : undefined,
      htmlNotes: [],
      drawn: 0,
    };
    self = cell;
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
    const sql = sqlCompleter(kernel, () => cell.connection);
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
    });
    kindPicker.addEventListener("change", () => setKind(cell, kindPicker.value as CellKind));
    element.addEventListener("focusin", () => select(cell));
    element.addEventListener("dblclick", () => {
      if (cell.kind === "markdown" && element.classList.contains("rendered")) editMarkdown(cell);
    });
    // An HTML cell that shows its design (a Streamlit cell its piece): a click on the cell itself (its
    // head, not a button, and not the design, whose clicks are the design's own) opens its code.
    element.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (!drawn(cell.kind) || !element.classList.contains("rendered")) return;
      if (target.closest(".wb-design, button, select, a, input")) return;
      editHtml(cell);
    });
    // Left: it draws by itself. (Another window in front is not leaving: the HTML stays open.)
    editorHost.addEventListener("focusout", () => {
      setTimeout(() => {
        if (!drawn(cell.kind) || element.classList.contains("rendered") || !cells.includes(cell)) return;
        const now = document.activeElement as HTMLElement | null;
        if (!document.hasFocus() || (now && (editorHost.contains(now) || now.closest(".context-view, .monaco-menu, .overflowingContentWidgets")))) return;
        if (cell.kind === "streamlit") drawPiece(cell);
        else if (sourceOf(cell).trim()) showDesign(cell);
      }, 0);
    });
    if (role === "transformations") kindPicker.hidden = true;
    void loadEditors().then((m) => {
      if (!cells.includes(cell)) return; // deleted before its editor loaded
      cell.editor = m.createCodeEditor(editorHost, {
        language: LANGUAGE[cell.kind],
        value: cell.source,
        theme: theme(),
        grow: true,
        readOnly: cell.role === "transformations",
        cellLinks: { first: (n) => (byNumber(n) ? firstLine(sourceOf(byNumber(n)!)) : null), go: (n) => void goTo(n) },
        placeholder: cell.kind === "sql" ? "SQL" : cell.kind === "dax" ? "DAX" : cell.kind === "html" ? "HTML" : cell.kind === "streamlit" ? "Python that draws with st.*" : undefined,
        // By the cell's kind as it is now: Python from the kernel, SQL from the connection's catalog,
        // DAX from its dataset's part of the workspace's catalog.
        complete: (text, offset) => (cell.kind === "sql" ? sql(text, offset) : cell.kind === "dax" ? dax(text, offset) : cell.kind === "code" || cell.kind === "streamlit" ? python(text, offset) : Promise.resolve([])),
        help: (text, offset) => (cell.kind === "code" || cell.kind === "streamlit" ? kernel.help(text, offset) : Promise.resolve("")),
        sendToAgent: (what, ask) => sendToAgent(codeItem(`cell ${indexOf(cell) + 1} of ${currentDocument()}${what.startLine === what.endLine ? `, line ${what.startLine}` : `, lines ${what.startLine} to ${what.endLine}`}`, what, LANGUAGE[cell.kind]), ask),
        keys: {
          shiftEnter: () => void run(cell).then(() => next(cell)),
          ctrlEnter: () => void run(cell),
          escape: () => toCommandMode(cell),
          f1: hooks.help,
        },
      });
      cell.editor.onChange((change) => {
        edited();
        // The uses line follows the typing, after a short pause (never an undo: that would undo the undo).
        if (!change.undo && !isApp(cell.role)) typedSoon();
        if (cell.role === "transformations") redraw();
        if (cell.kind === "html") drawHtmlState(cell);
      });
      if (hooks.cursor) cell.editor.onCursor(hooks.cursor);
      if (cell.wantsFocus) focusEditor(cell);
    });
    if (cell.kind === "markdown" && cell.source.trim()) showMarkdown(cell);
    else if (cell.kind === "html") {
      if (cell.source.trim()) showDesign(cell);
    } else if (cell.kind === "streamlit") drawPiece(cell);
    else area.set(data.outputs);
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
    else if (drawn(cell.kind) && cell.element.classList.contains("rendered")) editHtml(cell);
    else focusEditor(cell);
  };

  const next = (cell: Cell): void => {
    const following = cells[indexOf(cell) + 1] ?? make(empty(cell.kind === "markdown" || cell.kind === "html" ? "code" : cell.kind, cell.connection), cells.length);
    if (following.kind === "streamlit" && following.element.classList.contains("rendered")) return toCommandMode(following);
    select(following);
    following.element.scrollIntoView({ block: "nearest" });
    focusEditor(following);
  };

  const insertAt = (at: number, kind: CellKind = "code", source = ""): Cell => {
    const cell = make({ ...empty(kind, hasSource(kind) ? (sources(kind)[0] ?? null) : null), source }, Math.max(0, Math.min(at, cells.length)));
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

  const dataOf = (c: Cell): CellData => ({
    kind: c.kind,
    source: sourceOf(c),
    connection: hasSource(c.kind) ? c.connection : null,
    // An HTML cell keeps its last run's output: the filled design (what plain Jupyter shows) and the values.
    outputs: c.kind === "markdown" || c.kind === "streamlit" ? [] : c.kind === "html" ? (c.htmlRun?.output ? [c.htmlRun.output] : []) : c.area.outputs(),
    execution_count: c.execution_count,
    number: c.number,
    role: c.role,
    table: c.table,
    grouped: c.grouped,
    steps: c.role === "transformations" ? c.steps : null,
    height: drawn(c.kind) ? (c.design?.height() ?? null) : null,
  });

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
    else if (plain && !e.shiftKey && key === "t" && !isApp(cell.role)) setKind(cell, "streamlit");
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

  const goTo = (number: number): boolean => {
    const cell = byNumber(number);
    if (!cell) {
      toast(`There is no cell ${number} in this notebook.`, "error");
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
      // A group made while working shows its tables (a file's group starts folded).
      if (!hadGroup && !building && cells.some((c) => c.role === "tables")) groupFolded = false;
      // A cell the user was just working in is not folded away under them: its table shows open.
      if (movedIn.length && !building) for (const name of movedIn) unfolded.add(name);
    }
    for (const a of done.cells) {
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
  };

  /** Ask the server for the notebook as it should be. `move` false while the user types: nothing is
   *  added or moved, only the tables' cells and the uses lines follow. */
  const arrange = async (move: boolean): Promise<void> => {
    const relevant = tableInfos.length > 0 || cells.some((c) => c.role !== "") || cells.some((c) => c.kind !== "markdown" && withUses(sourceOf(c), null, usesForm(c.kind)) !== sourceOf(c));
    if (!relevant) return;
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
      if (cell.kind !== "html" || !cell.htmlRun || cell.htmlRun.code === null) continue;
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
  window.addEventListener("blur", () => {
    setTimeout(() => {
      const frame = document.activeElement;
      const cell = frame instanceof HTMLIFrameElement ? cells.find((c) => c.element.contains(frame)) : undefined;
      if (cell) select(cell);
    }, 0);
  });

  for (const data of initial.length ? initial : [empty()]) make(data, cells.length);
  building = false;
  redraw();
  if (cells.some((c) => c.role)) void arrange(true);

  const at = (index?: number): Cell | null => (index === undefined ? selected ?? cells[0] ?? null : cells[index] ?? null);
  return {
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
    htmlCells: () => cells.filter((c) => c.kind === "html").map(htmlReport),
    runHtml: async (number) => {
      const some = number === undefined ? cells.filter((c) => c.kind === "html" && htmlStateOf(c).runnable) : cells.filter((c) => c.kind === "html" && c.number === number);
      if (number !== undefined && !some.length) throw new Error(`This notebook has no HTML cell ${number}.`);
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
    pieces: () => cells.filter((c) => c.kind === "streamlit" && sourceOf(c).trim()).map((c) => ({ cell: c.number, code: sourceOf(c) })),
    drawPieces: () => {
      for (const c of cells) drawPiece(c);
    },
    resizePiece: (number, height) => {
      const cell = cells.find((c) => c.kind === "streamlit" && c.number === number);
      if (!cell?.design) throw new Error(`This notebook has no Streamlit cell ${number}.`);
      cell.design.setHeight(height);
      edited();
    },
    indexOfNumber: (number) => cells.findIndex((c) => c.number === number),
  };
}
