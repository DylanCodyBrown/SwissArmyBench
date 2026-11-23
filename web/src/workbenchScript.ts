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
 *   [COPY]     any numbered Python or HTML cell is copied (Copy cell, the palette) with the cursor in it
 *              and pasted into a notebook. No live Streamlit cells: app notebooks were replaced by widgets
 *              on the Canvas (2026-11-21), so every cell runs in the kernel
 *
 * ROUTING: POST /workbench/statement {code, line}: the statement's lines
 *          POST /workbench/tables/arrange {kind: "script", text, tables, move}: the text as it should
 *          be and where its cells are (the rules are the server's: domain/table_cells.py)
 *
 * The script is in parts (the craft review of 2026-11-22, refactor 8): its state is one record
 * (workbenchScriptState.ts: the stripes and the line notes too) handed to each part: its HTML cells (…Html),
 * the arrangement and the runs (…Runs), errors (…Errors), cells changed as text (…Cells; the text's own
 * rules are scriptCells.ts's). This file is the view: the state made, the editor mounted, and what the page
 * and the agent ask of a script.
 */
import { onConnectionColours } from "./connectionColours";
import { h } from "./dom";
import { errorHere } from "./errorNote";
import { inlineSource } from "./inlineCompletion";
import { loadEditors } from "./lazyLoad";
import { holdsTableCell, paneHeight, tablesInFile } from "./scriptCells";
import { codeItem, currentDocument, sendToAgent } from "./workbenchAgent";
import { pythonCompleter } from "./workbenchCompletion";
import { type ConsoleView, type RunOrigin } from "./workbenchConsole";
import { pythonIntel, showProblems } from "./workbenchIntel";
import type { Kernel } from "./workbenchKernel";
import type { HtmlReport, TableReport } from "./workbenchNotebookState";
import type { ErrorHooks } from "./workbenchOutputs";
import { addCode, addDax, addHtml, copy, editName, foldTables, nameCell, renameTable, setSource } from "./workbenchScriptCells";
import { errorHooks } from "./workbenchScriptErrors";
import { checkMarks, drawHtmlState, forgetHtmlRuns, htmlByNumber, htmlReport, layoutHtml, runHtmlCell, writeHeight } from "./workbenchScriptHtml";
import { arrange, goTo, runFile, runPart, runSelection, runTable, typedSoon } from "./workbenchScriptRuns";
import { draw, type HtmlCell, htmlStateOf, type Script, type ScriptFile, type ScriptHooks, type ScriptNames, stateOf, stripesSoon, textOf } from "./workbenchScriptState";
import type { TableInfo } from "./workbenchTables";

export { dedent, scriptPieces, sharedIndent } from "./scriptCells";
export type { ScriptFile } from "./workbenchScriptState";

export interface ScriptView {
  element: HTMLElement;
  /** Check the text again (the lint: Ruff came in). */
  relint: () => void;
  text: () => string;
  /** The whole text replaced, as an edit (unsaved until Save): a swap's code pointed at another connection. */
  replaceText: (text: string) => void;
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
  /** Go to the cell with this number (false: there is none); `line`: that line of the cell, from 1. */
  goTo: (number: number, line?: number | null) => boolean;
  foldTables: (folded: boolean, table?: string) => void;
  renameTable: (from: string, to: string) => void;
  /** Add an HTML cell after the cursor's cell (at the end without one), with the cursor in it. */
  addHtml: (source?: string, height?: number | null) => Promise<void>;
  /** Add a DAX cell after the cell at the cursor: `# %% [dax]` over one sab.dax() call, plain Python. */
  addDax: (dataset: string, source?: string) => Promise<void>;
  /** Add a Python cell after the cursor's cell, named on its marker. */
  addCode: (source: string, name?: string) => Promise<void>;
  /** Its HTML cells and each one's state. */
  htmlCells: () => HtmlReport[];
  /** Run an HTML cell by its number (without one: every one that is not up to date). */
  runHtml: (number?: number) => Promise<HtmlReport[]>;
  /** Size an HTML cell's pane (null: the design's own height): written on its marker. */
  resizeHtml: (number: number, height: number | null) => void;
  /** The cursor into an HTML cell's lines, so they show. */
  editHtml: (number: number) => void;
  /** Copy the cell the cursor is in (or the numbered one), for a paste into a notebook. */
  copy: (number?: number) => { cell: number; document: string | null } | null;
  /** Name a cell: its marker's own words ("" takes the name away); without a number, the cursor's cell. */
  nameCell: (number: number | undefined, name: string) => { cell: number; name: string | null };
  /** The cursor to the end of the cursor's cell's marker line, where its name is typed. */
  editName: () => void;
  /** Put this text as the lines of the cell numbered `number`, under its marker (a thin cell's move). */
  setSource: (number: number, source: string) => void;
  /** The own number of the cell the cursor is in (null: not in a numbered cell). */
  cursorCell: () => number | null;
  /** The Data Explorer's Insert: text at the cursor (a script is Python). */
  insertText: (text: string) => void;
  /** The document closed: free its editor and its panes. */
  dispose: () => void;
}

/** The script's editor, once Monaco is there: Python with the Workbench's intelligence, the Scripts IDE's
 *  moves, the debugger's gutter; what it hears (typing, the cursor, the focus). */
function mountEditor(sc: Script, initial: string, cameWithGroup: boolean): void {
  void loadEditors().then((m) => {
    if (sc.disposed) return; // closed before the editor loaded
    const python = pythonCompleter(sc.kernel, sc.names);
    const docName = (): string => sc.kernel.intel().path ?? "Untitled script";
    const intel = pythonIntel(sc.kernel, { notebook: false, document: docName });
    const intelKey = `${Math.random()}`;
    const editor = m.createCodeEditor(sc.editorHost, {
      pageZoom: true, // the page's code zoom (Ctrl+wheel, Ctrl+= - 0)
      language: "python",
      value: initial,
      theme: sc.theme(),
      inline: inlineSource(() => ({
        key: sc.inlineKey,
        name: (sc.kernel.intel().path ?? "Untitled script.py").split(/[\\/]/).pop() ?? "script.py",
        kind: "script",
        language: "python",
        text: sc.editor?.value() ?? initial,
      })),
      keys: { f5: () => void runFile(sc), ctrlEnter: () => void runSelection(sc), shiftEnter: () => void runSelection(sc), f1: sc.hooks.help },
      ide: sc.hooks.ide, // the Scripts IDE's F12, Shift+F12, F2, Shift+Alt+F (workbenchIde.ts)
      breakpoints: sc.hooks.breakpoints, // the debugger's gutter (workbenchDebug.ts)
      complete: (text, offset) => intel.complete(text, offset).then((found) => found ?? python(text, offset)),
      intel: {
        signature: intel.signature,
        hover: intel.hover,
        lint: intel.lint,
        onLint: (problems) => showProblems(`${docName()}\u0000${intelKey}`, sc.disposed ? null : { document: docName(), place: "", problems, reveal: (line, column) => sc.editor?.reveal(line, column) }),
      },
      help: (code, offset) => sc.kernel.help(code, offset),
      sendToAgent: (what, ask) =>
        sendToAgent(codeItem(`${currentDocument()}, ${what.startLine === what.endLine ? `line ${what.startLine}` : `lines ${what.startLine} to ${what.endLine}`}`, what, "python"), ask),
      cellLinks: { first: (n) => sc.outline.cells.find((c) => c.number === n)?.first ?? null, go: (n) => void goTo(sc, n) },
      // Right-click: the lineage of the cell the line is in.
      actions: sc.hooks.lineage
        ? [
            {
              id: "sab.lineage",
              label: "Lineage",
              run: (line) => {
                const found = sc.outline.cells.find((c) => line >= c.line && line <= c.end && c.number !== null);
                if (found?.number) sc.hooks.lineage!(found.number);
                else errorHere("Lineage starts from a numbered cell (a `# %%` cell).");
              },
            },
          ]
        : [],
    });
    sc.editor = editor;
    sc.hooks.editorReady?.(editor);
    editor.onChange((change) => {
      sc.text = editor.value();
      sc.version++;
      for (const held of sc.htmlCells.values()) if (held.run) drawHtmlState(sc, held);
      if (!(sc.applying && sc.quietly)) sc.changed();
      stripesSoon(sc);
      // The uses lines and the cells' places follow the typing, after a short pause (never an undo).
      if (!sc.applying && !change.undo) typedSoon(sc);
    });
    if (sc.hooks.cursor) editor.onCursor(sc.hooks.cursor);
    stripesSoon(sc);
    // An HTML cell shows its lines while the cursor is in it, its design when it is not. Leaving a
    // cell just typed in: the outline is asked for at once, not after the pause.
    const moved = (): void => {
      if (sc.outlineVersion === sc.version) return layoutHtml(sc);
      if (sc.quiet !== null) {
        window.clearTimeout(sc.quiet);
        sc.quiet = null;
        void arrange(sc, false);
      }
    };
    editor.onCursor(moved);
    editor.onFocus(moved);
    editor.onBlur(() => setTimeout(() => document.hasFocus() && moved(), 0));
    // A table's cell is read-only: it follows the grid.
    editor.onCursor((line) => editor.setReadOnly(sc.outline.cells.some((c) => c.role === "transformations" && line > c.line && line <= c.end)));
    if (cameWithGroup) for (const name of tablesInFile(initial)) sc.records.set(name, { code: null, at: null, opened: true });
    void arrange(sc, true);
  });
}

export function scriptView(
  initial: string,
  kernel: Kernel,
  console: ConsoleView,
  theme: () => string,
  changed: () => void,
  names: ScriptNames,
  file: ScriptFile,
  hooks: ScriptHooks = {},
): ScriptView {
  // A file that came with a Tables group: it starts folded, and its tables have not run since.
  const cameWithGroup = /^# ?region Tables\s*$/m.test(initial);
  const sc: Script = {
    editorHost: h("div", { class: "wb-script-editor" }),
    editor: null,
    text: initial,
    inlineKey: `sc-${Math.random().toString(36).slice(2, 10)}`,
    kernel,
    console,
    theme,
    dark: () => theme().endsWith("dark"),
    changed,
    names,
    file,
    hooks,
    tableInfos: [],
    tableLines: [],
    outline: { region: null, cells: [] },
    records: new Map(),
    version: 0,
    asked: 0,
    quiet: null,
    applying: false,
    disposed: false,
    quietly: true,
    foldOnce: cameWithGroup,
    htmlCells: new Map(),
    outlineVersion: -1,
    laidOut: "",
    marksTimer: null,
    striping: 0,
    stripeTimer: undefined,
  };
  onConnectionColours(() => {
    if (!sc.disposed) stripesSoon(sc);
  });
  // A kernel that starts (again) or stops holds no table any more: no cell has run in it.
  kernel.onState(() => {
    if (kernel.state !== "starting" && kernel.state !== "off") return;
    let any = false;
    for (const [name, record] of sc.records) {
      if (record.code === null) continue;
      sc.records.set(name, { code: null, at: null, opened: record.opened });
      any = true;
    }
    if (any) draw(sc);
    forgetHtmlRuns(sc);
  });
  // A run ended: a variable an HTML cell names may have changed.
  kernel.onState(() => {
    if (kernel.state !== "idle") return;
    if (sc.marksTimer !== null) window.clearTimeout(sc.marksTimer);
    sc.marksTimer = window.setTimeout(() => {
      sc.marksTimer = null;
      void checkMarks(sc);
    }, 300);
  });
  mountEditor(sc, initial, cameWithGroup);

  const reports = (some: HtmlCell[]): HtmlReport[] => some.map(htmlReport);
  return {
    relint: () => sc.editor?.lint(),
    errorHooks: (origin) => errorHooks(sc, origin),
    element: h("div", { class: "wb-script" }, sc.editorHost),
    text: () => textOf(sc),
    replaceText: (next) => {
      if (!sc.editor) throw new Error("The script's editor is not ready yet.");
      sc.editor.replaceText(next);
    },
    runFile: () => runFile(sc),
    runSelection: () => runSelection(sc),
    runToHere: () => runPart(sc, true),
    runFromHere: () => runPart(sc, false),
    helpAtCursor: async () => (sc.editor ? kernel.help(sc.editor.value(), sc.editor.cursorOffset()) : ""),
    focus: () => sc.editor?.focus(),
    reveal: (line) => sc.editor?.reveal(line),
    setTheme: (t) => {
      sc.editor?.setTheme(t);
      stripesSoon(sc); // each theme shows a connection's colour of its own
    },
    setTables: (tables) => {
      sc.tableInfos = tables;
      void arrange(sc, true);
    },
    holdsTable: (name) => sc.tableLines.some((l) => l.name === name) || holdsTableCell(textOf(sc), name),
    tables: () =>
      sc.tableLines.map((line) => {
        const state = stateOf(sc, line);
        return { ...line, state: state.kind, label: state.label };
      }),
    runTable: (name) => runTable(sc, name),
    runOutOfDate: async () => {
      let ran = 0;
      for (const line of [...sc.tableLines]) {
        if (!stateOf(sc, line).runnable) continue;
        ran++;
        if (!(await runTable(sc, line.name))) break;
      }
      return ran;
    },
    goTo: (number, line) => goTo(sc, number, line),
    foldTables: (folded, table) => foldTables(sc, folded, table),
    addHtml: (source, height) => addHtml(sc, source, height),
    addCode: (source, name) => addCode(sc, source, name),
    addDax: (dataset, source) => addDax(sc, dataset, source),
    htmlCells: () => reports([...sc.htmlCells.values()].sort((a, b) => a.cell.line - b.cell.line)),
    runHtml: async (number) => {
      if (sc.outlineVersion !== sc.version) await arrange(sc, false);
      const some = number === undefined ? [...sc.htmlCells.values()].filter((held) => htmlStateOf(held).runnable) : [htmlByNumber(sc, number)];
      for (const held of some) {
        if (!(await runHtmlCell(sc, held))) break;
      }
      return reports(some);
    },
    resizeHtml: (number, height) => {
      const held = htmlByNumber(sc, number);
      const size = height === null ? null : paneHeight(height);
      held.pane.setHeight(size);
      writeHeight(sc, held, size);
    },
    editHtml: (number) => {
      const held = htmlByNumber(sc, number);
      sc.editor?.focus();
      sc.editor?.moveTo(Math.min(held.cell.line + 1, held.cell.end));
    },
    insertText: (text) => {
      sc.editor?.insertAt(text);
      sc.editor?.focus();
    },
    cursorCell: () => {
      const line = sc.editor?.cursorLine() ?? 0;
      return sc.outline.cells.find((c) => line >= c.line && line <= c.end && c.number !== null)?.number ?? null;
    },
    copy: (number) => copy(sc, number),
    nameCell: (number, name) => nameCell(sc, number, name),
    setSource: (number, source) => setSource(sc, number, source),
    editName: () => editName(sc),
    renameTable: (from, to) => renameTable(sc, from, to),
    dispose: () => {
      sc.disposed = true;
      if (sc.quiet !== null) window.clearTimeout(sc.quiet);
      if (sc.marksTimer !== null) window.clearTimeout(sc.marksTimer);
      sc.quiet = sc.marksTimer = null;
      for (const held of sc.htmlCells.values()) held.pane.dispose();
      sc.htmlCells.clear();
      sc.editor?.dispose();
    },
  };
}
