/**
 * workbenchScriptState.ts: a script's state as one record (`Script`), and what every part of it asks: its
 * text, a table's state and its name in Python, where each table of the group folds, the connection stripes
 * in the margin, and the line notes drawn on the markers (a table's words, an HTML cell's). Pulled out of
 * workbenchScript.ts's scriptView (the craft review of 2026-11-22, refactor 8): what was the closure's
 * shared variables is this record, handed to each part (workbenchScript<Part>.ts) as its first argument;
 * a part imports the ones below it (state, html, runs, errors, cells). [VIEW]
 */
import { cellConnections, colourOf } from "./connectionColours";
import type { CodeEditor, IdeMoves, LineNote, ScriptOutline } from "./lazy/codeEditor";
import type { ConsoleView } from "./workbenchConsole";
import type { Fix } from "./workbenchErrors";
import { type DesignPane, type HtmlRun, htmlState, type HtmlState } from "./workbenchHtml";
import type { Kernel } from "./workbenchKernel";
import { groupLineText, plural, type RunRecord, type TableInfo, type TableLine, tableLineRest, type TableState, tableState } from "./workbenchTables";

/** A script's HTML cell as the page holds it: its place in the outline, its design, its last run. */
export interface HtmlCell {
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

/** What the page hands a script: where its cursor, its fixes, its files and its tables go. */
export interface ScriptHooks {
  cursor?: (line: number, column: number) => void;
  help?: () => void;
  fix?: (fix: Fix) => boolean;
  openFile?: (path: string, line: number) => void;
  openGrid?: (name: string) => void;
  openResult?: (count: number, name?: string) => void;
  tablesChanged?: () => void;
  lineage?: (number: number) => void;
  arguments?: () => string;
  ide?: IdeMoves;
  breakpoints?: { toggle: (line: number) => void; menu: (line: number, x: number, y: number) => void };
  editorReady?: (editor: CodeEditor) => void;
}

/** The names Python's completion offers beside the kernel's. */
export type ScriptNames = () => { connections: string[]; blades: string[]; codeNames?: { name: string; connection: string; kind: string }[]; datasets?: string[] };

/** A script's state: what every part of it reads and writes. */
export interface Script {
  editorHost: HTMLElement;
  /** Null until Monaco is there. */
  editor: CodeEditor | null;
  /** The script's text as last heard from the editor (the file's, before it). */
  text: string;
  /** This script's key for the ghost text's provider (inlineCompletion.ts): one a window, made up. */
  inlineKey: string;
  kernel: Kernel;
  console: ConsoleView;
  theme: () => string;
  dark: () => boolean;
  /** The document changed (the page's unsaved mark). */
  changed: () => void;
  names: ScriptNames;
  file: ScriptFile;
  hooks: ScriptHooks;
  // ----- the Tables group: arranged by the server's rules, folded and drawn here
  tableInfos: TableInfo[];
  tableLines: TableLine[];
  outline: ScriptOutline;
  records: Map<string, RunRecord>;
  /** Counts every change: an arrangement worked out for an older text is dropped. */
  version: number;
  asked: number;
  quiet: number | null;
  applying: boolean;
  disposed: boolean;
  /** The first look at a script only gives its cells their numbers: that does not count as a change
   *  (the numbers come out the same the next time it opens; they are saved when the user saves). */
  quietly: boolean;
  /** A file that came with a Tables group: it starts folded, and its tables have not run since. */
  foldOnce: boolean;
  // ----- HTML cells
  htmlCells: Map<string, HtmlCell>;
  /** The text version the outline describes (hidden lines are only set from a fresh one). */
  outlineVersion: number;
  laidOut: string;
  marksTimer: number | null;
  // ----- the connection stripes
  striping: number;
  stripeTimer: number | undefined;
}

/** The script's text: the editor's once it is there. */
export const textOf = (sc: Script): string => (sc.editor ? sc.editor.value() : sc.text);
export const stateOf = (sc: Script, line: TableLine): TableState => tableState(line.code, sc.records.get(line.name));
export const variableOf = (sc: Script, name: string): string => sc.tableInfos.find((t) => t.name === name)?.variable ?? name.replace(/\W/g, "_");
/** The line each table of the group folds at: its maker's marker, or its own cell's. */
export function tableStarts(sc: Script): Map<string, number> {
  const starts = new Map<string, number>();
  for (const cell of sc.outline.cells) {
    if (cell.grouped && cell.table && (cell.role === "maker" || cell.role === "transformations") && !starts.has(cell.table)) starts.set(cell.table, cell.line);
  }
  return starts;
}

// Connection colours (connectionColours.ts): each `# %%` cell (or the whole script, with none) that
// names a connection wears its colour in the margin; two connections, two stripes. Nothing runs.
export async function stripeNow(sc: Script): Promise<void> {
  if (!sc.editor) return;
  const mine = ++sc.striping;
  const count = sc.editor.lineCount();
  const runs = sc.outline.cells.length ? sc.outline.cells.map((c) => [c.line, Math.min(c.end, count)] as const) : [[1, count] as const];
  const found = await cellConnections(runs.map(([a, b]) => ({ kind: "code", source: sc.editor!.lines(a, b) })));
  if (mine !== sc.striping || !sc.editor) return;
  sc.editor.setStripes(
    runs
      .map(([start, end], i) => ({ start, end, colours: (found[i] ?? []).map((n) => colourOf(n)).filter((c): c is string => !!c) }))
      .filter((s) => s.colours.length),
  );
}
export function stripesSoon(sc: Script): void {
  window.clearTimeout(sc.stripeTimer);
  sc.stripeTimer = window.setTimeout(() => void stripeNow(sc), 400);
}

export const htmlStateOf = (held: HtmlCell): HtmlState => htmlState(held.cell.html ?? "", held.run);
/** The cursor is in the cell (and the editor has the keyboard): its lines show, not its design. */
export function isActive(sc: Script, held: HtmlCell): boolean {
  if (!sc.editor?.hasFocus()) return false;
  const line = sc.editor.cursorLine();
  return line >= held.cell.line && line <= Math.max(held.cell.html_end ?? held.cell.end, held.cell.line);
}

/** The line notes on the markers: the Tables group's line, each table's words and state, each HTML cell's. */
export function draw(sc: Script): void {
  if (!sc.editor) return;
  stripesSoon(sc);
  const notes: LineNote[] = [];
  if (sc.outline.region) {
    const group = groupLineText(sc.tableLines.map((line) => stateOf(sc, line)));
    notes.push({ line: sc.outline.region[0], text: group.text.replace(/^Tables · /, ""), tone: group.stale ? "stale" : "plain", marker: true });
    notes.push({ line: sc.outline.region[1], text: "", tone: "plain", marker: true });
    notes.push({ line: sc.outline.region[1] + 1, text: "", tone: "plain", marker: true }); // the plain marker that closes the group
  }
  const starts = tableStarts(sc);
  for (const cell of sc.outline.cells) {
    const line = sc.tableLines.find((l) => l.name === cell.table);
    const state = line ? stateOf(sc, line) : null;
    let words = "";
    if (line && state && cell.role === "transformations") {
      const steps = (starts.get(line.name) === cell.line || !cell.grouped) && line.steps !== null && line.steps > 0 ? plural(line.steps, "step") : line.steps === null ? "not open in the grid" : "";
      words = [steps, "read-only: it follows the grid", state.label, state.runnable ? "Ctrl+Enter runs it" : ""].filter(Boolean).join(" · ");
    } else if (line && state && cell.role === "maker" && cell.grouped) words = tableLineRest(line, state);
    const held = cell.kind === "html" ? [...sc.htmlCells.values()].find((e) => e.cell === cell) : undefined;
    if (held) {
      const now = htmlStateOf(held);
      const shown = !isActive(sc, held) && held.cell.html !== null;
      words = ["HTML", shown ? "click this line to edit" : held.cell.problem ? held.cell.problem : "the design shows when the cursor leaves", now.label, now.runnable ? "Ctrl+Enter runs it" : ""].filter(Boolean).join(" · ");
      notes.push({ line: cell.line, text: words, tone: now.kind === "outOfDate" ? "stale" : "plain", marker: true });
      continue;
    }
    notes.push({ line: cell.line, text: words, tone: state?.kind === "outOfDate" && cell.table ? "stale" : "plain", marker: true });
  }
  sc.editor.setLineNotes(notes);
  sc.hooks.tablesChanged?.();
}
