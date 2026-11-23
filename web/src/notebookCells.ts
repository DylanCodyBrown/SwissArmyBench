/**
 * notebookCells.ts: a notebook cell's rules that need no page: what each kind is, a cell's role in the Tables
 * group, how a run's time is said, a cell as it is saved, which snippets a cell takes, whether code makes a
 * name, what a key does in command mode, a SQL cell's first line. Pulled out of workbenchNotebook.ts's
 * notebookView (the craft review of 2026-11-22: what needs no closure state), so the notebook is tested in
 * parts (tests/test_notebook_cells.py runs these in Node). Pure: no DOM, no request.
 * [FUNCTION]
 */
import type { SnippetLanguage } from "./starters";
import type { CellData, CellKind } from "./workbenchNotebookState";

/** A SQL cell's first line as the kernel runs it (domain/notebooks.py sql_line). */
export function sqlLine(connection: string | null): string {
  if (!connection) return "%%sql";
  return /\s/.test(connection) ? `%%sql '${connection.replace(/'/g, "'\"'\"'")}'` : `%%sql ${connection}`;
}

/** Whether Python code makes `name`: assigns, defines or imports it (the fix "Run the cell that makes x"). */
export function makesName(name: string, code: string): boolean {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const makes = new RegExp(`^\\s*(?:${escaped}\\s*(?:,[^=\\n]*)?=(?!=)|(?:[\\w\\s,]*,\\s*)${escaped}\\s*=(?!=)|def ${escaped}\\b|class ${escaped}\\b|import\\s.*\\bas\\s+${escaped}\\b|from\\s.*\\bimport\\s.*\\b${escaped}\\b|import\\s+${escaped}\\b|for\\s.*\\b${escaped}\\b.*\\bin\\b)`, "m");
  return makes.test(code);
}

/** What a key does in command mode (the focus on the cell, not its editor). */
export type CellCommand = "runNext" | "run" | "fold" | "edit" | "above" | "below" | "d" | "code" | "markdown" | "sql" | "dax" | "html" | "copy" | "paste" | "undo" | "down" | "up" | "output";

/** Jupyter's keys on the selected cell: Enter edits (a heading's line folds), Shift+Enter and Ctrl+Enter run;
 *  A and B insert above and below; D is half of D D; Y, M, S, X and H make a cell of the user's Python,
 *  Markdown, SQL, DAX or HTML; C and V copy and paste; Z undoes; J and K (or Down and Up) move the selection;
 *  O hides the output. Null: not a key of command mode (the browser keeps it). */
export function commandFor(pressed: { key: string; shift: boolean; ctrl: boolean; meta: boolean; alt: boolean }, role: string): CellCommand | null {
  const key = pressed.key.toLowerCase();
  const plain = !pressed.ctrl && !pressed.meta && !pressed.alt;
  const own = !isApp(role);
  if (pressed.key === "Enter" && pressed.shift) return "runNext";
  if (pressed.key === "Enter" && (pressed.ctrl || pressed.meta)) return "run";
  if (pressed.key === "Enter" && plain) return isHeading(role) ? "fold" : "edit";
  if (!plain) return null;
  if (!pressed.shift && key === "a") return "above";
  if (!pressed.shift && key === "b") return "below";
  if (key === "d") return "d";
  if (key === "y" && own) return "code";
  if (key === "m" && own) return "markdown";
  if (key === "s" && own) return "sql";
  if (!pressed.shift && key === "x" && own) return "dax";
  if (!pressed.shift && key === "h" && own) return "html";
  if (!pressed.shift && key === "c") return "copy";
  if (!pressed.shift && key === "v") return "paste";
  if (key === "z") return "undo";
  if (key === "j" || pressed.key === "ArrowDown") return "down";
  if (key === "k" || pressed.key === "ArrowUp") return "up";
  if (key === "o") return "output";
  return null;
}

/** Notebook mode: a cell's mark in its head from the run order's state ("edited", "out of date", else
 *  nothing), and why (the names made again since it ran). */
export function flowWords(said: { state: string; because: string[] } | undefined): { words: string; title: string } {
  const state = said?.state ?? "current";
  const words = state === "edited" ? "edited" : state === "outOfDate" ? "out of date" : "";
  const title = state === "outOfDate" && said?.because.length ? `Made again since it ran: ${said.because.join(", ")}` : "";
  return { words, title };
}

/** The kinds with two faces: the code while it is edited, what it draws when it is not. */
export const drawn = (kind: CellKind): boolean => kind === "html";

/** A cell that shows something drawn in place of its code while it is not being edited. */
export const twoFaced = (cell: { kind: CellKind }): boolean => drawn(cell.kind);

/** A cell that runs on a source picked in its head: SQL on a connection, DAX on a dataset. */
export const hasSource = (kind: CellKind): kind is "sql" | "dax" => kind === "sql" || kind === "dax";

/** One of the app's own cells in the Tables group (a heading's line, a table's read-only cell), never the
 *  user's. */
export const isApp = (role: string): boolean => role === "tables" || role === "table" || role === "transformations";

/** A heading's line of the Tables group (the group's, or one table's). */
export const isHeading = (role: string): boolean => role === "tables" || role === "table";

/** How long a run took, as its head says it: "320 ms", "4.2 s", "2 min 5 s". */
export function runTime(ms: number): string {
  if (ms < 1000) return `${Math.max(1, Math.round(ms))} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)} min ${s % 60} s`;
}

/** What of a drawn cell its saved form reads (the notebook's Cell has these and more). */
export interface SavedCell {
  kind: CellKind;
  connection: string | null;
  execution_count: number | null;
  number: number;
  role: string;
  table: string | null;
  grouped: boolean;
  steps: unknown[] | null;
  name: string | null;
  htmlRun?: { output?: CellData["outputs"][number] | null } | null;
  area: { outputs: () => CellData["outputs"] };
  design?: { height: () => number | null } | null;
}

/** A cell as it is saved and sent, with its text as it stands now (`source`). */
export function cellData(c: SavedCell, source: string): CellData {
  return {
    kind: c.kind,
    source,
    connection: hasSource(c.kind) ? c.connection : null,
    // An HTML cell keeps its last run's output: the filled design (what plain Jupyter shows) and the values.
    // A table's cell: its table is drawn again on opening (it runs by itself), so no rows go in the file.
    outputs: c.kind === "markdown" || c.role === "transformations" ? [] : c.kind === "html" ? (c.htmlRun?.output ? [c.htmlRun.output] : []) : c.area.outputs(),
    execution_count: c.execution_count,
    number: c.number,
    role: c.role,
    table: c.table,
    grouped: c.grouped,
    steps: c.role === "transformations" ? c.steps : null,
    height: twoFaced(c) || c.kind === "tsx" ? (c.design?.height() ?? null) : null,
    ...(c.name ? { name: c.name } : {}),
  };
}

/** The snippets a cell takes, by its kind (null: none; never one of the app's own cells). */
export const snippetLanguage = (cell: { kind: CellKind; role: string }): SnippetLanguage | null =>
  isApp(cell.role) ? null : cell.kind === "dax" ? "dax" : cell.kind === "html" ? "html" : cell.kind === "markdown" ? "markdown" : cell.kind === "code" ? "streamlit" : null;
