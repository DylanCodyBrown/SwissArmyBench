/**
 * workbenchScript.ts: a Python script in the Workbench: the editor, in the source pane; its runs show
 * in the document's console (workbenchConsole.ts), on the document's IPython kernel. [WIRE]
 *
 *   Run file (F5)        the file as Python would run it (`%run`: __name__ is "__main__", __file__ and
 *                        sys.argv are set, multiprocessing works), saved first when it has a path; an
 *                        unsaved script runs from a private copy
 *   Run statement        Ctrl+Enter, Shift+Enter or F9: the whole statement at the cursor (a `for`
 *                        block, a function, a call over several lines), then the cursor moves to the
 *                        next one (RStudio's run line); with a selection, its whole lines (a part of one
 *                        line runs as it is: an expression to look at)
 *   Run to here, from here   the script's top to the cursor's statement, or from it to the end
 *   Help (F1)            the name at the cursor, in the Help pane
 *
 *   [CELLS]    `# %%` starts a cell (VS Code, Spyder, PyCharm and Jupytext read it too); each cell has
 *              a number that never changes, on its marker (`# %% [7]`); `@cell7` in a comment links
 *              to it. The code before the first marker is the script's main code, not a cell
 *   [TABLES]   every table open in the grid has a read-only cell here (docs/ideas.md, 2026-11-14):
 *              `# %% [8] [transformations] orders`, the grid's steps as one DuckDB query. All tables
 *              sit at the top between `# region Tables` and `# endregion`, each with the user's cell
 *              that makes it (`# %% [7] [table] orders`); the editor folds the group, each table and
 *              each cell, and says each table's state beside its marker. Out of date is yellow;
 *              Ctrl+Enter in a table's cell runs it. Nothing runs by itself
 *   [USES]     a `# %%` cell that names a table starts with `# uses orders @cell8`, kept as they type
 *   [HTML]     an HTML cell (docs/ideas.md, 2026-11-14; workbenchHtml.ts): `# %% [9] [html] height=320`,
 *              then the HTML as one Python string that does nothing when the file runs. With the cursor
 *              in the cell its lines show; with the cursor elsewhere they are put away and the design
 *              shows under the marker, in a pane that resizes (the height is written on the marker).
 *              `{{ name }}` is filled from the kernel when the cell runs (Ctrl+Enter in it, or Run
 *              file); such a cell says Out of date when its HTML or a variable it names changes
 *   [LIVE]     there is no Streamlit kind of cell (docs/ideas.md, the Streamlit canvas, 2026-11-15;
 *              workbenchStreamlit.ts). A cell that calls Streamlit (the server's outline says so) is
 *              shown live: it runs in the document's Streamlit app, not in the kernel (Run file leaves
 *              its lines out). With the cursor elsewhere its lines are put away and its page shows
 *              under the marker
 *   [LINK]     any numbered Python cell goes on a Streamlit app's canvas as a link: Copy cell (the
 *              palette) with the cursor in it, then paste on the canvas
 *
 * ROUTING: POST /workbench/statement {code, line}: the statement's lines
 *          POST /workbench/tables/arrange {kind: "script", text, tables, move}: the text as it should
 *          be and where its cells are (the rules are the server's: domain/table_cells.py)
 */
import { api } from "./api";
import { h, toast } from "./dom";
import type { CodeEditor, LineNote, ScriptOutline } from "./lazy/codeEditor";
import { codeItem, currentDocument, sendToAgent } from "./workbenchAgent";
import { type ConsoleView, loadEditors, type RunOrigin } from "./workbenchConsole";
import { pythonCompleter } from "./workbenchCompletion";
import { type ErrorDetail, type Fix, type Frame, problemsFor, yourFrame } from "./workbenchErrors";
import type { Kernel } from "./workbenchKernel";
import { changedNames, type DesignPane, designPane, fillHtml, htmlNames, type HtmlRun, htmlState, type HtmlState, runHtml, scriptBody } from "./workbenchHtml";
import type { HtmlReport, TableReport } from "./workbenchNotebook";
import type { ErrorHooks } from "./workbenchOutputs";
import { cleanName, copyCell, markerName, markerWordsOf, PIECE_HEIGHT, type PieceSource, type PieceTools, pieceTools, pieceView, type StreamlitHost, withMarkerName } from "./workbenchStreamlit";
import { groupLineText, plural, type RunRecord, type TableInfo, type TableLine, tableLineRest, tableState } from "./workbenchTables";

export interface ScriptView {
  element: HTMLElement;
  text: () => string;
  runFile: () => Promise<void>;
  runSelection: () => Promise<void>;
  runToHere: () => Promise<void>;
  runFromHere: () => Promise<void>;
  /** The help for the name at the cursor ("" when there is none). */
  helpAtCursor: () => Promise<string>;
  focus: () => void;
  /** The cursor to a line (a frame clicked in another document's error panel). */
  reveal: (line: number) => void;
  setTheme: (theme: string) => void;
  /** What a run's error panel does here: marks this script's lines, fixes them, goes to a frame. */
  errorHooks: (origin?: RunOrigin) => ErrorHooks;
  /** The open tables that belong to this script: their cells follow, the Tables group is arranged. */
  setTables: (tables: TableInfo[]) => void;
  holdsTable: (name: string) => boolean;
  tables: () => TableReport[];
  runTable: (name: string) => Promise<boolean>;
  runOutOfDate: () => Promise<number>;
  /** Go to the cell with this number (false: there is none). */
  goTo: (number: number) => boolean;
  foldTables: (folded: boolean, table?: string) => void;
  renameTable: (from: string, to: string) => void;
  /** Add an HTML cell after the cursor's cell (at the end without one), with the cursor in it. */
  addHtml: (source?: string, height?: number | null) => Promise<void>;
  /** Add a DAX cell after the cell at the cursor: `# %% [dax]` over one sab.dax() call, plain Python. */
  addDax: (dataset: string, source?: string) => Promise<void>;
  /** Add a Python cell after the cursor's cell, named on its marker (a Streamlit piece, say). */
  addCode: (source: string, name?: string) => Promise<void>;
  /** Its HTML cells and each one's state. */
  htmlCells: () => HtmlReport[];
  /** Run an HTML cell by its number (without one: every one that is not up to date). */
  runHtml: (number?: number) => Promise<HtmlReport[]>;
  /** Size an HTML cell's pane (null: the design's own height): written on its marker. */
  resizeHtml: (number: number, height: number | null) => void;
  /** The cursor into an HTML cell's lines, so they show. */
  editHtml: (number: number) => void;
  /** Its numbered Python cells, in order: any of them can go on a canvas. */
  pieces: () => PieceSource[];
  /** The app's state changed: each live cell is drawn again. */
  drawPieces: () => void;
  /** Size a live cell's pane (null: the usual height): written on its marker. */
  resizePiece: (number: number, height: number | null) => void;
  /** Copy the cell the cursor is in (or the numbered one): its link, for a canvas. */
  copy: (number?: number) => { cell: number; document: string | null } | null;
  /** Name a cell: its marker's own words ("" takes the name away); without a number, the cursor's cell. */
  nameCell: (number: number | undefined, name: string) => { cell: number; name: string | null };
  /** The cursor to the end of the cursor's cell's marker line, where its name is typed. */
  editName: () => void;
}

/** A script's live cell (it calls Streamlit) as the page holds it: its place in the outline, its page. */
interface PieceCell {
  key: string;
  cell: ScriptOutline["cells"][number];
  pane: DesignPane;
  tools: PieceTools;
  /** The live piece shows (it has run). */
  shown: boolean;
  room: number;
}

const PIECE_MARKER = /^# ?%% \[(\d+)\](?! \[(?:html|table|transformations)\])(?:\s|$)/;
const HTML_MARKER = /^# ?%% \[(\d+)\] \[html\](?:\s|$)/;

/** A script's numbered cells from its text: each Python `# %% [n]` cell's lines, and each HTML cell's
 *  lines as `form: "script"` (the server reads the HTML from its string: they go on a page too). The
 *  Tables group's own cells are left out. */
export function scriptPieces(text: string): PieceSource[] {
  const found: PieceSource[] = [];
  let current: { cell: number; name: string; lines: string[]; html: boolean } | null = null;
  let grouped = false;
  const close = (): void => {
    if (current && current.lines.some((l) => l.trim())) {
      const html = current.html ? ({ kind: "html", form: "script" } as const) : {};
      found.push({ cell: current.cell, code: current.lines.join("\n").replace(/\s+$/, ""), ...html, ...(current.name ? { name: current.name } : {}) });
    }
    current = null;
  };
  for (const line of text.split("\n")) {
    if (/^# ?region Tables\s*$/.test(line)) grouped = true;
    else if (/^# ?endregion\b/.test(line)) grouped = false;
    if (/^# ?(%%|region Tables\s*$|endregion\b)/.test(line)) {
      close();
      const marker = grouped ? null : (PIECE_MARKER.exec(line) ?? HTML_MARKER.exec(line));
      // The cell's name: its marker's own words (`# %% [7] Region filter`).
      if (marker) current = { cell: Number(marker[1]), name: markerName(markerWordsOf(line) ?? ""), lines: [], html: HTML_MARKER.test(line) };
    } else if (current) current.lines.push(line);
  }
  close();
  return found;
}

/** A script's HTML cell as the page holds it: its place in the outline, its design, its last run. */
interface HtmlCell {
  key: string;
  cell: ScriptOutline["cells"][number];
  pane: DesignPane;
  run: HtmlRun | undefined;
  notes: string[];
  /** What the design was last drawn from. */
  drawnFrom: string | null;
  drawn: number;
  /** The pane's height on screen, for the room the editor makes. */
  room: number;
}

export interface ScriptFile {
  /** The file's path (null: never saved). */
  path: () => string | null;
  /** Save it before Run file when it has changes (false: not saved, so do not run). */
  saveFirst: () => Promise<boolean>;
}

/** The indent every non-blank line shares (what dedent takes off). */
export function sharedIndent(code: string): number {
  const indents = code.split("\n").filter((l) => l.trim()).map((l) => /^[ \t]*/.exec(l)![0].length);
  return indents.length ? Math.min(...indents) : 0;
}

/** Python's own dedent for lines run from inside a block: they lose their shared indent. */
export function dedent(code: string): string {
  const cut = sharedIndent(code);
  return code.split("\n").map((l) => l.slice(cut)).join("\n");
}

const sameFile = (a: string | null, b: string | null): boolean => !!a && !!b && a.replace(/\\/g, "/").toLowerCase() === b.replace(/\\/g, "/").toLowerCase();

interface Statement {
  start: number | null;
  end: number | null;
  next: number | null;
}

export function scriptView(
  initial: string,
  kernel: Kernel,
  console: ConsoleView,
  theme: () => string,
  changed: () => void,
  names: () => { connections: string[]; blades: string[]; codeNames?: { name: string; connection: string; kind: string }[]; datasets?: string[] },
  file: ScriptFile,
  hooks: { cursor?: (line: number, column: number) => void; help?: () => void; fix?: (fix: Fix) => boolean; openFile?: (path: string, line: number) => void; openGrid?: (name: string) => void; openResult?: (count: number, name?: string) => void; tablesChanged?: () => void; streamlit?: StreamlitHost } = {},
): ScriptView {
  const editorHost = h("div", { class: "wb-script-editor" });
  let editor: CodeEditor | null = null;
  let text = initial;

  // ===== the Tables group: arranged by the server's rules, folded and drawn here =====
  let tableInfos: TableInfo[] = [];
  let tableLines: TableLine[] = [];
  let outline: ScriptOutline = { region: null, cells: [] };
  const records = new Map<string, RunRecord>();
  let version = 0; // counts every change: an arrangement worked out for an older text is dropped
  let asked = 0;
  let quiet: number | null = null;
  let applying = false;
  // The first look at a script only gives its cells their numbers: that does not count as a change
  // (the numbers come out the same the next time it opens; they are saved when the user saves).
  let quietly = true;
  // A file that came with a Tables group: it starts folded, and its tables have not run since.
  const cameWithGroup = /^# ?region Tables\s*$/m.test(initial);
  let foldOnce = cameWithGroup;
  // ===== HTML cells =====
  const htmlCells = new Map<string, HtmlCell>();
  let outlineVersion = -1; // the text version the outline describes (hidden lines are only set from a fresh one)
  let laidOut = "";
  let marksTimer: number | null = null;
  // ===== Streamlit cells =====
  const pieceCells = new Map<string, PieceCell>();
  const dark = (): boolean => theme().endsWith("dark");
  const stateOf = (line: TableLine) => tableState(line.code, records.get(line.name));
  const variableOf = (name: string): string => tableInfos.find((t) => t.name === name)?.variable ?? name.replace(/\W/g, "_");
  /** The line each table of the group folds at: its maker's marker, or its own cell's. */
  const tableStarts = (): Map<string, number> => {
    const starts = new Map<string, number>();
    for (const cell of outline.cells) {
      if (cell.grouped && cell.table && (cell.role === "maker" || cell.role === "transformations") && !starts.has(cell.table)) starts.set(cell.table, cell.line);
    }
    return starts;
  };

  const draw = (): void => {
    if (!editor) return;
    const notes: LineNote[] = [];
    if (outline.region) {
      const group = groupLineText(tableLines.map(stateOf));
      notes.push({ line: outline.region[0], text: group.text.replace(/^Tables · /, ""), tone: group.stale ? "stale" : "plain", marker: true });
      notes.push({ line: outline.region[1], text: "", tone: "plain", marker: true });
      notes.push({ line: outline.region[1] + 1, text: "", tone: "plain", marker: true }); // the plain marker that closes the group
    }
    const starts = tableStarts();
    for (const cell of outline.cells) {
      const line = tableLines.find((l) => l.name === cell.table);
      const state = line ? stateOf(line) : null;
      let words = "";
      if (line && state && cell.role === "transformations") {
        const steps = (starts.get(line.name) === cell.line || !cell.grouped) && line.steps !== null && line.steps > 0 ? plural(line.steps, "step") : line.steps === null ? "not open in the grid" : "";
        words = [steps, "read-only: it follows the grid", state.label, state.runnable ? "Ctrl+Enter runs it" : ""].filter(Boolean).join(" · ");
      } else if (line && state && cell.role === "maker" && cell.grouped) words = tableLineRest(line, state);
      const piece = cell.kind === "streamlit" ? [...pieceCells.values()].find((e) => e.cell === cell) : undefined;
      if (piece) {
        const view = pieceView(hooks.streamlit?.state() ?? null, cell.number ?? -1, true);
        const shown = piece.shown && !inPiece(piece);
        words = ["Streamlit", view.part, shown ? "click this line to edit" : "", view.state.label, view.state.runnable ? "Ctrl+Enter runs it" : "", ...(shown ? [] : view.notes)].filter(Boolean).join(" · ");
        notes.push({ line: cell.line, text: words, tone: view.state.kind === "outOfDate" ? "stale" : "plain", marker: true });
        continue;
      }
      const held = cell.kind === "html" ? [...htmlCells.values()].find((e) => e.cell === cell) : undefined;
      if (held) {
        const now = htmlStateOf(held);
        const shown = !isActive(held) && held.cell.html !== null;
        words = ["HTML", shown ? "click this line to edit" : held.cell.problem ? held.cell.problem : "the design shows when the cursor leaves", now.label, now.runnable ? "Ctrl+Enter runs it" : ""].filter(Boolean).join(" · ");
        notes.push({ line: cell.line, text: words, tone: now.kind === "outOfDate" ? "stale" : "plain", marker: true });
        continue;
      }
      notes.push({ line: cell.line, text: words, tone: state?.kind === "outOfDate" && cell.table ? "stale" : "plain", marker: true });
    }
    editor.setLineNotes(notes);
    hooks.tablesChanged?.();
  };

  // A kernel that starts (again) or stops holds no table any more: no cell has run in it.
  kernel.onState(() => {
    if (kernel.state !== "starting" && kernel.state !== "off") return;
    let any = false;
    for (const [name, record] of records) {
      if (record.code === null) continue;
      records.set(name, { code: null, at: null, opened: record.opened });
      any = true;
    }
    if (any) draw();
    // An HTML cell's names were that kernel's variables: it has not run in the new one.
    for (const held of htmlCells.values()) {
      if (!held.run || held.run.code === null) continue;
      held.run = { ...held.run, code: null, at: null, changed: [] };
      drawHtmlState(held);
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

  // ===== HTML cells: each one's design under its marker while the cursor is elsewhere =====

  const htmlStateOf = (held: HtmlCell): HtmlState => htmlState(held.cell.html ?? "", held.run);
  /** The cursor is in the cell (and the editor has the keyboard): its lines show, not its design. */
  const isActive = (held: HtmlCell): boolean => {
    if (!editor?.hasFocus()) return false;
    const line = editor.cursorLine();
    return line >= held.cell.line && line <= Math.max(held.cell.html_end ?? held.cell.end, held.cell.line);
  };

  function drawHtmlState(held: HtmlCell): void {
    held.pane.setState(htmlStateOf(held), held.cell.problem ? [held.cell.problem] : held.notes);
    draw();
  }

  /** Draw a cell's design from its HTML as it is now, its names filled with what its last run gave. */
  const drawDesign = async (held: HtmlCell): Promise<void> => {
    const html = held.cell.html;
    if (html === null || html === undefined) return drawHtmlState(held);
    const mine = ++held.drawn;
    let filled: { html: string; missing: string[]; notes: string[] };
    try {
      filled = await fillHtml(html, held.run?.values ?? {});
    } catch {
      filled = { html, missing: [], notes: ["The server is away: the design shows as written."] };
    }
    if (mine !== held.drawn) return;
    held.notes = [...filled.missing.map((n) => `{{ ${n} }} was not found in the kernel.`), ...filled.notes];
    held.drawnFrom = html;
    held.pane.show(filled.html);
    drawHtmlState(held);
  };

  /** The marker of an HTML cell with its pane's height on it (`height=320`), or without one. */
  const writeHeight = (held: { cell: ScriptOutline["cells"][number] }, height: number | null): void => {
    if (!editor) return;
    const lines = editor.value().split("\n");
    const numbered = held.cell.number === null ? null : new RegExp(`^# ?%% \\[${held.cell.number}\\](?:\\s|$)`);
    const at = numbered ? lines.findIndex((l) => numbered.test(l)) : held.cell.line - 1;
    // (`[streamlit]` was a kind of cell once: the word goes when the marker is written.)
    const found = /^(# ?%%(?: \[\d+\])?(?: \[html\])?)(?: \[streamlit\])?(?: height=\d+)?(.*)$/.exec(lines[at] ?? "");
    if (!found) return;
    lines[at] = `${found[1]}${height === null ? "" : ` height=${height}`}${found[2]}`;
    editor.replaceText(lines.join("\n"));
  };

  // ===== Streamlit cells: each piece live under its marker while the cursor is elsewhere =====

  /** The cursor is in the piece's cell (and the editor has the keyboard): its lines show. */
  function inPiece(held: PieceCell): boolean {
    if (!editor?.hasFocus()) return false;
    const line = editor.cursorLine();
    return line >= held.cell.line && line <= Math.max(held.cell.end, held.cell.line);
  }

  function drawPiece(held: PieceCell): void {
    const view = pieceView(hooks.streamlit?.state() ?? null, held.cell.number ?? -1, true);
    held.pane.showAddress(view.address);
    held.pane.setState(view.state, view.notes);
    held.tools.draw(view);
    held.shown = view.address !== null;
  }

  /** The Streamlit cells as the outline has them: each keeps its pane by its number. */
  function syncPieces(): void {
    const seen = new Set<string>();
    for (const cell of outline.cells) {
      if (cell.kind !== "streamlit" || cell.number === null) continue;
      const key = `p${cell.number}`;
      seen.add(key);
      let held = pieceCells.get(key);
      if (!held) {
        const tools = pieceTools(hooks.streamlit);
        const made: PieceCell = {
          key,
          cell,
          tools,
          shown: false,
          room: PIECE_HEIGHT + 40,
          pane: designPane({ dark, height: cell.height ?? null, fit: PIECE_HEIGHT, tools: tools.elements, resized: (height) => writeHeight(made, height), run: () => void runPieces() }),
        };
        made.pane.element.classList.add("in-script");
        new ResizeObserver(() => {
          const room = Math.ceil(made.pane.element.getBoundingClientRect().height);
          if (room && room !== made.room) {
            made.room = room;
            layoutHtml();
          }
        }).observe(made.pane.element);
        pieceCells.set(key, (held = made));
      }
      held.cell = cell;
      if ((cell.height ?? null) !== held.pane.height() && !held.pane.element.classList.contains("dragging")) held.pane.setHeight(cell.height ?? null);
      drawPiece(held);
    }
    for (const [key, held] of pieceCells) {
      if (seen.has(key)) continue;
      held.pane.dispose();
      pieceCells.delete(key);
    }
  }

  /** Run the document's Streamlit app (every piece: they share it). */
  const runPieces = async (): Promise<boolean> => {
    if (!hooks.streamlit) return false;
    if (outlineVersion !== version) await arrange(false); // a cell just typed has its number first
    try {
      return await hooks.streamlit.run();
    } catch (e) {
      console.note((e as Error).message);
      return false;
    }
  };

  const pieceAt = (line: number): PieceCell | undefined => [...pieceCells.values()].find((e) => line >= e.cell.line && line <= Math.max(e.cell.end, e.cell.line));

  /** Which lines are put away and which designs show, from the outline (only a fresh one: lines are
   *  never hidden by an outline of an older text). */
  function layoutHtml(): void {
    if (!editor || outlineVersion !== version) return;
    const zones: { id: string; afterLine: number; height: number; element: HTMLElement }[] = [];
    const hidden: [number, number][] = [];
    for (const held of pieceCells.values()) {
      const show = held.shown && !inPiece(held);
      held.pane.element.hidden = !show;
      if (!show) continue;
      zones.push({ id: held.key, afterLine: held.cell.line, height: held.room, element: held.pane.element });
      if (held.cell.end > held.cell.line) hidden.push([held.cell.line + 1, held.cell.end]);
    }
    for (const held of htmlCells.values()) {
      const cell = held.cell;
      const active = isActive(held);
      const drawn = cell.html !== null && cell.html !== undefined && cell.html.trim() !== "";
      held.pane.element.hidden = active || (!drawn && !cell.problem);
      if (active || (!drawn && !cell.problem)) continue;
      zones.push({ id: held.key, afterLine: cell.line, height: held.room, element: held.pane.element });
      // A cell that is not one string yet keeps its lines in view, to be mended.
      if (drawn && (cell.html_end ?? 0) > cell.line) hidden.push([cell.line + 1, cell.html_end!]);
    }
    const now = JSON.stringify([zones.map((z) => [z.id, z.afterLine, z.height]), hidden]);
    if (now === laidOut) return;
    laidOut = now;
    editor.setHidden(hidden);
    editor.setZones(zones);
    draw();
  }

  /** The HTML cells as the outline has them: each keeps its pane and its last run by its number. */
  function syncHtml(): void {
    const seen = new Set<string>();
    let unnumbered = 0;
    for (const cell of outline.cells) {
      if (cell.kind !== "html") continue;
      const key = cell.number !== null ? `n${cell.number}` : `u${unnumbered++}`;
      seen.add(key);
      let held = htmlCells.get(key);
      if (!held) {
        const made: HtmlCell = {
          key,
          cell,
          run: undefined,
          notes: [],
          drawnFrom: null,
          drawn: 0,
          room: 200,
          pane: designPane({ dark, height: cell.height ?? null, resized: (height) => writeHeight(made, height), run: () => void runHtmlCell(made) }),
        };
        made.pane.element.classList.add("in-script");
        new ResizeObserver(() => {
          const room = Math.ceil(made.pane.element.getBoundingClientRect().height);
          if (room && room !== made.room) {
            made.room = room;
            layoutHtml();
          }
        }).observe(made.pane.element);
        htmlCells.set(key, (held = made));
      }
      held.cell = cell;
      if ((cell.height ?? null) !== held.pane.height() && !held.pane.element.classList.contains("dragging")) held.pane.setHeight(cell.height ?? null);
      if (cell.html !== held.drawnFrom && cell.html !== null && cell.html !== undefined) void drawDesign(held);
      else drawHtmlState(held);
    }
    for (const [key, held] of htmlCells) {
      if (seen.has(key)) continue;
      held.pane.dispose();
      htmlCells.delete(key);
    }
    layoutHtml();
  }

  /** Run an HTML cell: plain HTML only draws; with names, each is read from the kernel's variables. */
  const runHtmlCell = async (held: HtmlCell): Promise<boolean> => {
    const html = held.cell.html;
    if (html === null || html === undefined) {
      console.note(held.cell.problem ?? "This HTML cell holds no HTML yet.");
      return false;
    }
    if (!htmlNames(html).length) {
      await drawDesign(held);
      return true;
    }
    let said = "";
    try {
      const done = await runHtml(kernel, html, (item) => {
        if (item.output_type === "error") said = `${String(item.ename ?? "Error")}: ${String(item.evalue ?? "")}`;
      });
      if (done.run) held.run = done.run;
      else console.note(`The HTML cell did not run${said ? `: ${said}` : "."}`);
      held.drawnFrom = null;
      await drawDesign(held);
      return done.ok;
    } catch (e) {
      console.note((e as Error).message);
      return false;
    }
  };

  const checkMarks = async (): Promise<void> => {
    const ran = [...htmlCells.values()].filter((held) => held.run && held.run.code !== null);
    if (!ran.length) return;
    const changed = await changedNames(kernel, ran.map((held) => held.run!));
    if (!changed) return;
    for (const held of ran) {
      const now = held.run ? changed.get(held.run) : undefined;
      if (!held.run || !now || now.join("\n") === held.run.changed.join("\n")) continue;
      held.run.changed = now;
      drawHtmlState(held);
    }
  };

  const htmlReport = (held: HtmlCell): HtmlReport => {
    const now = htmlStateOf(held);
    const html = held.cell.html ?? "";
    return { number: held.cell.number, index: held.cell.line, html, names: htmlNames(html), state: now.kind, label: now.label, height: held.cell.height ?? null, notes: held.cell.problem ? [held.cell.problem] : held.notes };
  };
  const htmlByNumber = (number: number): HtmlCell => {
    const held = [...htmlCells.values()].find((e) => e.cell.number === number);
    if (!held) throw new Error(`This script has no HTML cell ${number}.`);
    return held;
  };
  /** The HTML cell whose lines hold this line. */
  const htmlAt = (line: number): HtmlCell | undefined => [...htmlCells.values()].find((e) => line >= e.cell.line && line <= Math.max(e.cell.html_end ?? e.cell.end, e.cell.line));

  const relevant = (): boolean => tableInfos.length > 0 || /^# ?(%%|region Tables)/m.test(editor ? editor.value() : text);

  /** Ask the server for the script as it should be, and where its cells are. `move` false while the
   *  user types: nothing is added or moved; only the tables' cells and the uses lines follow. */
  const arrange = async (move: boolean): Promise<void> => {
    if (!editor) return;
    if (!relevant()) {
      if (outline.cells.length || outline.region) {
        outline = { region: null, cells: [] };
        tableLines = [];
        editor.setOutline(null);
        draw();
      }
      outlineVersion = version;
      syncPieces();
      syncHtml();
      return;
    }
    const mine = ++asked;
    const at = version;
    try {
      const done = await api<{ text: string; tables: TableLine[]; outline: ScriptOutline }>("/workbench/tables/arrange", "POST", { kind: "script", text: editor.value(), tables: tableInfos.map((t) => t.name), move });
      if (mine !== asked) return; // a newer question is on its way
      if (at !== version) return void (move ? arrange(true) : typedSoon()); // typed meanwhile: ask again
      applying = true;
      quietly = quietly && tableInfos.length === 0;
      try {
        editor.replaceText(done.text);
      } finally {
        applying = false;
        quietly = false;
      }
      outline = done.outline;
      outlineVersion = version; // the text just written is the one the outline describes
      tableLines = done.tables;
      editor.setOutline(outline);
      draw();
      syncPieces();
      syncHtml();
      // A piece just given its number is one the app can know now.
      hooks.streamlit?.changed();
      if (foldOnce && outline.region) {
        foldOnce = false;
        // Once Monaco has the folds: each table, then the group (a file's group starts folded).
        setTimeout(() => {
          editor?.fold([...tableStarts().values()]);
          if (outline.region) editor?.fold([outline.region[0]]);
        }, 600);
      }
    } catch {
      /* the server is away: the text stays as it is */
    }
  };

  function typedSoon(): void {
    if (quiet !== null) window.clearTimeout(quiet);
    quiet = window.setTimeout(() => {
      quiet = null;
      void arrange(false);
    }, 600);
  }

  /** The table whose read-only cell this line is in (its marker or its code). */
  const tableAt = (line: number): string | null => outline.cells.find((c) => c.role === "transformations" && line >= c.line && line <= c.end)?.table ?? null;

  /** Lines of the script as they run: a table's cell inside them goes through the kernel's safe run
   *  (client/table_cells.py), on the same lines, so it never transforms a transformed table. */
  const safeLines = (start: number, end: number): string => {
    if (!editor) return "";
    const lines = editor.lines(start, end).split("\n");
    // A Streamlit cell is a piece of a page: it runs in the document's app, never in the kernel.
    for (const cell of outline.cells) {
      if (cell.kind !== "streamlit") continue;
      for (let at = Math.max(cell.line + 1, start); at <= Math.min(cell.end, end); at++) lines[at - start] = "";
    }
    for (const cell of outline.cells) {
      if (cell.role !== "transformations" || !cell.table || cell.line + 1 < start || cell.end > end || cell.end <= cell.line) continue;
      const from = cell.line + 1 - start;
      const to = cell.end - start;
      const body = lines.slice(from, to + 1).join("\n");
      if (!body.trim()) continue;
      lines[from] = `__import__('swissarmybench.client.table_cells', fromlist=['run']).run(${JSON.stringify(variableOf(cell.table))}, ${JSON.stringify(body)})`;
      for (let k = from + 1; k <= to; k++) lines[k] = "";
    }
    return lines.join("\n");
  };

  const runTable = async (name: string): Promise<boolean> => {
    const line = tableLines.find((l) => l.name === name);
    if (!line) throw new Error(`This script has no table named ${name}.`);
    const ok = await console.run({ code: line.code, kind: "table", table: variableOf(name) }, `# ${name}: its transformations`);
    if (ok) records.set(name, { code: line.code, at: new Date(), opened: false });
    draw();
    return ok;
  };

  const goTo = (number: number): boolean => {
    const cell = outline.cells.find((c) => c.number === number);
    if (!cell || !editor) {
      toast(`There is no cell ${number} in this script.`, "error");
      return false;
    }
    if (cell.grouped && outline.region) editor.unfold([outline.region[0], cell.line]);
    editor.reveal(cell.line);
    return true;
  };

  /** The marker of the cell a line is in ("" when it is in none). */
  const lineAbove = (line: number): string => {
    const lines = (editor ? editor.value() : text).split("\n");
    for (let at = Math.min(line, lines.length); at >= 1; at--) if (/^# ?(%%|region Tables|endregion)/.test(lines[at - 1]!)) return lines[at - 1]!;
    return "";
  };

  const statementAt = async (line: number): Promise<Statement> => {
    try {
      return await api<Statement>("/workbench/statement", "POST", { code: editor ? editor.value() : text, line });
    } catch {
      return { start: line, end: line, next: line + 1 };
    }
  };

  const runFile = async (): Promise<void> => {
    const code = editor ? editor.value() : text;
    if (!code.trim()) return console.note("Empty script");
    if (!(await file.saveFirst())) return;
    const path = file.path();
    const name = path ? (path.split(/[\\/]/).pop() ?? path) : null;
    const lines = code.split("\n").length;
    const ran = tableLines.map((l) => ({ name: l.name, code: l.code }));
    const ok = await console.run({ code, kind: "file", path }, name ? `%run ${name}` : `# the script (${lines} line${lines === 1 ? "" : "s"}, not saved)`, { kind: "file", path });
    // The file ran to its end: so did its tables' cells (each the safe way, in the kernel).
    if (ok) for (const table of ran) records.set(table.name, { code: table.code, at: new Date(), opened: false });
    // And its HTML cells' names are read from what the run left.
    if (ok) for (const held of [...htmlCells.values()]) if (htmlNames(held.cell.html ?? "").length) await runHtmlCell(held);
    // Its pieces run in the document's Streamlit app (the file's own run leaves their lines out).
    if (ok && pieceCells.size) await runPieces();
    draw();
    if (ok) void arrange(true);
  };

  /** The whole statement at the cursor, then the cursor on to the next (the selection's lines when
   *  there is one). The cursor moves at once: pressing again queues the next statement. */
  const runSelection = async (): Promise<void> => {
    if (!editor) return;
    const chosen = editor.selected();
    if (chosen) {
      const part = chosen.startLine === chosen.endLine && chosen.text.trim() !== chosen.wholeLines.trim();
      const code = part ? chosen.text.trim() : dedent(safeLines(chosen.startLine, chosen.endLine));
      const indent = part ? Math.max(0, chosen.wholeLines.indexOf(code)) : sharedIndent(chosen.wholeLines);
      await console.run({ code }, code.trimEnd(), { kind: "lines", start: chosen.startLine, indent });
      return;
    }
    const line = editor.cursorLine();
    // In a table's read-only cell: its Run.
    const table = tableAt(line);
    if (table) return void (await runTable(table));
    // In an HTML cell: its Run (its names filled, its design drawn).
    const held = outlineVersion === version ? htmlAt(line) : undefined;
    if (held) return void (await runHtmlCell(held));
    // In a Streamlit cell: the app runs (every piece), and the cursor leaves so the piece shows.
    const piece = outlineVersion === version ? pieceAt(line) : undefined;
    if (piece !== undefined) return void (await runPieces());
    const found = await statementAt(line);
    if (found.start === null || found.end === null) {
      // A blank line or a comment: on to the next line with code.
      const lines = editor.value().split("\n");
      let next = line + 1;
      while (next <= lines.length && (!lines[next - 1]!.trim() || lines[next - 1]!.trim().startsWith("#"))) next++;
      editor.moveTo(Math.min(next, lines.length));
      return;
    }
    const block = editor.lines(found.start, found.end);
    const code = dedent(block);
    editor.moveTo(found.next ?? Math.min(found.end + 1, editor.lineCount()));
    await console.run({ code }, code.trimEnd(), { kind: "lines", start: found.start, indent: sharedIndent(block) });
  };

  /** The script's top to the end of the cursor's statement, or from its start to the end. */
  const runPart = async (to: boolean): Promise<void> => {
    if (!editor) return;
    const line = editor.cursorLine();
    const found = await statementAt(line);
    const last = editor.lineCount();
    const code = to ? safeLines(1, found.end ?? line) : safeLines(found.start ?? line, last);
    if (!code.trim()) return console.note("Nothing to run");
    await console.run({ code }, to ? `# lines 1 to ${found.end ?? line}` : `# lines ${found.start ?? line} to ${last}`, { kind: "lines", start: to ? 1 : (found.start ?? line), indent: 0 });
  };

  void loadEditors().then((m) => {
    editor = m.createCodeEditor(editorHost, {
      language: "python",
      value: initial,
      theme: theme(),
      keys: { f5: () => void runFile(), ctrlEnter: () => void runSelection(), shiftEnter: () => void runSelection(), f1: hooks.help },
      complete: pythonCompleter(kernel, names),
      help: (code, offset) => kernel.help(code, offset),
      sendToAgent: (what, ask) =>
        sendToAgent(codeItem(`${currentDocument()}, ${what.startLine === what.endLine ? `line ${what.startLine}` : `lines ${what.startLine} to ${what.endLine}`}`, what, "python"), ask),
      cellLinks: { first: (n) => outline.cells.find((c) => c.number === n)?.first ?? null, go: (n) => void goTo(n) },
    });
    editor.onChange((change) => {
      text = editor!.value();
      version++;
      for (const held of htmlCells.values()) if (held.run) drawHtmlState(held);
      if (!(applying && quietly)) changed();
      hooks.streamlit?.changed();
      // The uses lines and the cells' places follow the typing, after a short pause (never an undo).
      if (!applying && !change.undo) typedSoon();
    });
    if (hooks.cursor) editor.onCursor(hooks.cursor);
    // An HTML cell shows its lines while the cursor is in it, its design when it is not. Leaving a
    // cell just typed in: the outline is asked for at once, not after the pause.
    const moved = (): void => {
      if (outlineVersion === version) return layoutHtml();
      if (quiet !== null) {
        window.clearTimeout(quiet);
        quiet = null;
        void arrange(false);
      }
    };
    editor.onCursor(moved);
    editor.onFocus(moved);
    editor.onBlur(() => setTimeout(() => document.hasFocus() && moved(), 0));
    // A table's cell is read-only: it follows the grid.
    editor.onCursor((line) => editor!.setReadOnly(outline.cells.some((c) => c.role === "transformations" && line > c.line && line <= c.end)));
    if (cameWithGroup) for (const match of initial.matchAll(/^# ?%%(?: \[\d+\])? \[transformations\] ([A-Za-z_][\w-]*)/gm)) records.set(match[1]!, { code: null, at: null, opened: true });
    void arrange(true);
  });

  /** A frame of this run, as this script's line and the columns the dedent took off (null: elsewhere). */
  const placeIn = (origin: RunOrigin | undefined, detail: ErrorDetail) => (frame: Pick<Frame, "where" | "cell" | "file" | "line">): { line: number; colShift: number } | null => {
    if (!origin) return null;
    if (origin.kind === "file") {
      const path = origin.path ?? file.path();
      const mine = frame.where === "file" && (sameFile(frame.file, path) || (!origin.path && /[\\/]untitled\.py$/.test(frame.file ?? "")));
      return mine ? { line: frame.line, colShift: 0 } : null;
    }
    const numbers = detail.chain.flatMap((e) => e.frames.map((f) => f.cell ?? 0).concat(e.syntax?.cell ?? 0));
    return frame.where === "cell" && frame.cell === Math.max(...numbers) ? { line: origin.start + frame.line - 1, colShift: origin.indent } : null;
  };

  const errorHooks = (origin?: RunOrigin): ErrorHooks => {
    let shown: ErrorDetail | null = null;
    const yours = (): { line: number; colShift: number } | null => {
      const entry = shown?.chain[shown.chain.length - 1];
      const frame = yourFrame(entry) ?? (entry?.syntax ? ({ where: entry.syntax.where, cell: entry.syntax.cell, file: entry.syntax.file, line: entry.syntax.line } as Frame) : null);
      return frame && shown ? placeIn(origin, shown)(frame) : null;
    };
    return {
      shown: (detail) => {
        shown = detail;
        editor?.setProblems(problemsFor(detail, placeIn(origin, detail)));
      },
      fix: (fix) => {
        if (fix.kind === "replace" || fix.kind === "import") {
          if (!editor?.applyFix(fix, fix.kind === "import" ? 1 : (yours()?.line ?? editor.cursorLine()))) console.note(`${fix.target ?? "That"} is no longer in the script.`);
          else editor.focus(); // back in the code, ready to run it again
          return;
        }
        if (!hooks.fix?.(fix)) console.note(fix.kind === "define" ? `Nothing defines ${fix.name}` : "Fix not available here");
      },
      goTo: (frame) => {
        const at = shown ? placeIn(origin, shown)(frame) : null;
        if (at && editor) {
          editor.reveal(at.line, (frame.col ?? 1) + at.colShift);
          return true;
        }
        if (frame.where === "file" && frame.file && hooks.openFile) {
          hooks.openFile(frame.file, frame.line);
          return true;
        }
        return false;
      },
      openGrid: hooks.openGrid,
      openResult: hooks.openResult,
    };
  };

  return {
    errorHooks,
    element: h("div", { class: "wb-script" }, editorHost),
    text: () => (editor ? editor.value() : text),
    runFile,
    runSelection,
    runToHere: () => runPart(true),
    runFromHere: () => runPart(false),
    helpAtCursor: async () => (editor ? kernel.help(editor.value(), editor.cursorOffset()) : ""),
    focus: () => editor?.focus(),
    reveal: (line) => editor?.reveal(line),
    setTheme: (t) => editor?.setTheme(t),
    setTables: (tables) => {
      tableInfos = tables;
      void arrange(true);
    },
    holdsTable: (name) => tableLines.some((l) => l.name === name) || new RegExp(`^# ?%%(?: \\[\\d+\\])? \\[transformations\\] ${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "m").test(editor ? editor.value() : text),
    tables: () =>
      tableLines.map((line) => {
        const state = stateOf(line);
        return { ...line, state: state.kind, label: state.label };
      }),
    runTable,
    runOutOfDate: async () => {
      let ran = 0;
      for (const line of [...tableLines]) {
        if (!stateOf(line).runnable) continue;
        ran++;
        if (!(await runTable(line.name))) break;
      }
      return ran;
    },
    goTo,
    foldTables: (folded, table) => {
      if (!editor || !outline.region) return;
      const start = table ? tableStarts().get(table) : outline.region[0];
      if (start === undefined) return;
      if (folded) editor.fold([start]);
      else editor.unfold(table ? [outline.region[0], start] : [start]);
    },
    addHtml: async (source = "", height = null) => {
      if (!editor) throw new Error("The script's editor is not ready yet.");
      const lines = editor.value().split("\n");
      if (lines[lines.length - 1] === "") lines.pop();
      const here = outlineVersion === version ? outline.cells.find((c) => editor!.cursorLine() >= c.line && editor!.cursorLine() <= c.end && !c.grouped) : undefined;
      const at = here ? Math.min(here.end, lines.length) : lines.length;
      // What follows it in the file is the user's Python: a plain marker keeps it a cell of its own.
      const after = lines.slice(at);
      const closing = after.some((l) => l.trim()) && !/^# ?%%/.test(after.find((l) => l.trim()) ?? "") ? ["# %%"] : [];
      const marker = `# %% [html]${height === null ? "" : ` height=${Math.max(60, Math.min(2000, Math.round(height)))}`}`;
      const body = scriptBody(source).replace(/\n$/, "").split("\n");
      editor.replaceText([...lines.slice(0, at), marker, ...body, ...closing, ...after].join("\n") + "\n");
      editor.focus();
      editor.moveTo(at + 3); // the first line of the HTML
      if (quiet !== null) window.clearTimeout(quiet);
      quiet = null;
      await arrange(true);
    },
    addCode: async (source, name = "") => {
      if (!editor) throw new Error("The script's editor is not ready yet.");
      const lines = editor.value().split("\n");
      if (lines[lines.length - 1] === "") lines.pop();
      const here = outlineVersion === version ? outline.cells.find((c) => editor!.cursorLine() >= c.line && editor!.cursorLine() <= c.end && !c.grouped) : undefined;
      const at = here ? Math.min(here.end, lines.length) : lines.length;
      const after = lines.slice(at);
      const closing = after.some((l) => l.trim()) && !/^# ?%%/.test(after.find((l) => l.trim()) ?? "") ? ["# %%"] : [];
      // The name is the marker's own words (written after a backslash when it would read as its grammar).
      const marker = withMarkerName("# %%", cleanName(name));
      editor.replaceText([...lines.slice(0, at), marker, ...source.replace(/\n$/, "").split("\n"), ...closing, ...after].join("\n") + "\n");
      editor.reveal(at + 2, 1);
      if (quiet !== null) window.clearTimeout(quiet);
      quiet = null;
      await arrange(true);
    },
    addDax: async (dataset, source = "") => {
      if (!editor) throw new Error("The script's editor is not ready yet.");
      const lines = editor.value().split("\n");
      if (lines[lines.length - 1] === "") lines.pop();
      const here = outlineVersion === version ? outline.cells.find((c) => editor!.cursorLine() >= c.line && editor!.cursorLine() <= c.end && !c.grouped) : undefined;
      const at = here ? Math.min(here.end, lines.length) : lines.length;
      const after = lines.slice(at);
      const closing = after.some((l) => l.trim()) && !/^# ?%%/.test(after.find((l) => l.trim()) ?? "") ? ["# %%"] : [];
      // The file runs as plain Python: the cell is one sab.dax() call, its DAX a string.
      const imported = /^\s*import swissarmybench as sab\b/m.test(editor.value()) ? [] : ["import swissarmybench as sab"];
      const dax = (source.trim() || "EVALUATE ").replace(/\\/g, "\\\\").replace(/"""/g, '\\"\\"\\"');
      const body = [...imported, `result = sab.dax(${JSON.stringify(dataset)}, """`, ...dax.split("\n"), '""")'];
      editor.replaceText([...lines.slice(0, at), "# %% [dax]", ...body, ...closing, ...after].join("\n") + "\n");
      editor.reveal(at + 3 + imported.length, dax.split("\n")[0]!.length + 1); // in the DAX
      if (quiet !== null) window.clearTimeout(quiet);
      quiet = null;
      await arrange(true);
    },
    htmlCells: () => [...htmlCells.values()].sort((a, b) => a.cell.line - b.cell.line).map(htmlReport),
    runHtml: async (number) => {
      if (outlineVersion !== version) await arrange(false);
      const some = number === undefined ? [...htmlCells.values()].filter((held) => htmlStateOf(held).runnable) : [htmlByNumber(number)];
      for (const held of some) {
        if (!(await runHtmlCell(held))) break;
      }
      return some.map(htmlReport);
    },
    resizeHtml: (number, height) => {
      const held = htmlByNumber(number);
      const size = height === null ? null : Math.max(60, Math.min(2000, Math.round(height)));
      held.pane.setHeight(size);
      writeHeight(held, size);
    },
    editHtml: (number) => {
      const held = htmlByNumber(number);
      editor?.focus();
      editor?.moveTo(Math.min(held.cell.line + 1, held.cell.end));
    },
    pieces: () => scriptPieces(editor ? editor.value() : text),
    drawPieces: () => {
      for (const held of pieceCells.values()) drawPiece(held);
      laidOut = "";
      layoutHtml();
      draw();
    },
    resizePiece: (number, height) => {
      const held = pieceCells.get(`p${number}`);
      if (!held) throw new Error(`This script has no live cell ${number} (a cell that calls Streamlit).`);
      const size = height === null ? null : Math.max(60, Math.min(2000, Math.round(height)));
      held.pane.setHeight(size);
      writeHeight(held, size);
    },
    copy: (number) => {
      const line = editor?.cursorLine() ?? 0;
      const cell = outline.cells.find((c) => (number === undefined ? line >= c.line && line <= c.end : c.number === number) && !c.grouped);
      if (!cell || cell.number === null) throw new Error(number === undefined ? "The cursor is not in a numbered cell (a `# %%` cell)." : `This script has no Python or HTML cell ${number}.`);
      // An HTML cell is copied as its HTML: a canvas places its link, a notebook pastes an HTML cell.
      const html = cell.kind === "html";
      if (html && cell.html == null) throw new Error(cell.problem ?? "This HTML cell's string is not whole yet.");
      const source = html ? (cell.html ?? "") : (scriptPieces(editor ? editor.value() : text).find((c) => c.cell === cell.number)?.code ?? "");
      const where = hooks.streamlit?.link() ?? { document: null, title: "this script" };
      copyCell({ document: where.document, cell: cell.number, title: where.title, kind: html ? "html" : "code", source, connection: null, height: cell.height ?? null });
      return { cell: cell.number, document: where.document };
    },
    nameCell: (number, name) => {
      const line = editor?.cursorLine() ?? 0;
      const cell = outline.cells.find((c) => (number === undefined ? line >= c.line && line <= c.end : c.number === number) && !c.grouped && !c.role);
      if (!cell || cell.number === null || !editor) throw new Error(number === undefined ? "The cursor is not in a numbered cell (a `# %%` cell)." : `This script has no cell ${number} of yours.`);
      const lines = editor.value().split("\n");
      const numbered = new RegExp(`^# ?%% \\[${cell.number}\\](?:\\s|$)`);
      const at = lines.findIndex((l) => numbered.test(l));
      if (at < 0) throw new Error(`This script has no cell ${number}.`);
      const said = cleanName(name);
      lines[at] = withMarkerName(lines[at]!, said);
      editor.replaceText(lines.join("\n"));
      return { cell: cell.number, name: said || null };
    },
    editName: () => {
      const line = editor?.cursorLine() ?? 0;
      const cell = outline.cells.find((c) => line >= c.line && line <= c.end && !c.grouped && !c.role);
      if (!cell || !editor) throw new Error("The cursor is not in a cell of yours (a `# %%` cell).");
      editor.reveal(cell.line, (editor.value().split("\n")[cell.line - 1] ?? "").length + 1);
    },
    renameTable: (from, to) => {
      const record = records.get(from);
      if (record) records.set(to, record);
      records.delete(from);
      // Its markers carry the name: `# %% [8] [transformations] orders`.
      const marker = new RegExp(`^(# ?%%(?: \\[\\d+\\])? \\[(?:table|transformations)\\] )${from.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\w-])`, "gm");
      if (editor) editor.replaceText(editor.value().replace(marker, `$1${to}`));
    },
  };
}
