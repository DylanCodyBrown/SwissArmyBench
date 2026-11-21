/**
 * workbenchTables.ts: every table has a read-only cell (docs/ideas.md, 2026-11-14): what a notebook
 * and a script share. [FUNCTION]
 *
 *   [TABLES]   the open tables as their cells' text (GET /workbench/tables): the grid's steps as one
 *              DuckDB query whose result is the table's own name
 *   [ARRANGE]  a document with its Tables group as it should be (POST /workbench/tables/arrange): the
 *              rules are the server's (domain/table_cells.py); the page applies what comes back
 *   [STATE]    a table's cell compares its text with the text it last ran. Only a state that needs
 *              the user to act is said (the owner, 2026-11-14: no confirmation labels): out of date
 *              (yellow, with Run), not run yet, not run since opening. A cell that is current says
 *              nothing. Nothing runs by itself
 *   [USES]     the one line the app keeps at the top of a cell that names a table
 */
import { plural } from "./dom";
import { api } from "./api";

/** An open table, as the server lists it. */
export interface TableInfo {
  name: string;
  /** Its name as a Python variable. */
  variable: string;
  grid: string | null;
  source_kind: string;
  /** python, file, dropped, paste, connection, query or unknown. */
  origin: string;
  /** Where it came from, in a word or two: orders.csv, Warehouse, Python (the Data panel's). */
  source?: string;
  /** The connection it was read from (null: not a connection's): its colour. */
  connection?: string | null;
  rows?: number;
  /** The Workbench kernel that sent it to the grid (null: no kernel did). */
  kernel: string | null;
  steps: number;
  step_list: unknown[];
  /** Each step in plain words (the Scripts and Notebooks pages' cards). */
  step_words?: string[];
  problem: string | null;
  code: string;
  loaded: string;
}

/** A table of a document's group, as the arrangement gives it. */
export interface TableLine {
  name: string;
  /** Its transformations cell's number. */
  cell: number | null;
  /** The number of the user's cell that makes it (null: no cell does). */
  maker: number | null;
  /** Its cells sit in the Tables group. */
  moved: boolean;
  /** "orders is made at @cell7 (it needs make_dates)". */
  note: string | null;
  steps: number | null;
  /** It is open in the grid. */
  open: boolean;
  code: string;
}

export interface ArrangedCell {
  number: number;
  kind: "code" | "sql" | "dax" | "html" | "markdown";
  source: string;
  role: string;
  table: string | null;
  grouped: boolean;
  /** The uses line the cell should start with (null: none). */
  uses: string | null;
  steps?: unknown[];
}

export async function fetchTables(): Promise<TableInfo[]> {
  return (await api<{ tables: TableInfo[] }>("/workbench/tables")).tables;
}

/** What a table's cell last ran, and when; `opened`: the cell came with the file (or a reload). */
export interface RunRecord {
  code: string | null;
  at: Date | null;
  opened: boolean;
}

export type TableStateKind = "upToDate" | "outOfDate" | "notRun" | "notRunSinceOpening" | "noSteps" | "closed";

export interface TableState {
  kind: TableStateKind;
  /** "Out of date · last run 10:42". Empty: nothing needs doing, so nothing is said. */
  label: string;
  /** Short, for a folded line: "out of date" (empty: nothing to say). */
  short: string;
  /** Run would change the variable. */
  runnable: boolean;
}

const clock = (at: Date): string => `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;

/** Whether the cell's text does anything when run (a cell with no steps is a comment). */
export function runsSomething(code: string): boolean {
  return code.split("\n").some((line) => line.trim() && !line.trim().startsWith("#"));
}

/** A table cell's state: its text against the text it last ran (so undoing a change in the grid
 *  clears the yellow by itself). */
export function tableState(code: string, record: RunRecord | undefined): TableState {
  const ran = record?.code ?? null;
  const when = record?.at ? ` · last run ${clock(record.at)}` : "";
  if (ran !== null && ran === code) return { kind: "upToDate", label: "", short: "", runnable: false };
  if (ran !== null) return { kind: "outOfDate", label: `Out of date${when}`, short: "out of date", runnable: true };
  if (!runsSomething(code)) return { kind: "noSteps", label: "", short: "", runnable: false };
  if (record?.opened) return { kind: "notRunSinceOpening", label: "Not run since opening", short: "not run since opening", runnable: true };
  return { kind: "notRun", label: "Not run yet", short: "not run yet", runnable: true };
}

export { plural };

/** A table's folded line: its name, its steps when it has some, and its state only when that needs
 *  the user to act: "orders · 3 steps", "orders · 3 steps · out of date", "customers". */
export function tableLineText(line: TableLine, state: TableState): string {
  const steps = line.steps === null ? "not open in the grid" : line.steps > 0 ? plural(line.steps, "step") : "";
  return [line.name, steps, state.short].filter(Boolean).join(" · ");
}

/** The words after a table's name on its folded line ("" when there are none). */
export function tableLineRest(line: TableLine, state: TableState): string {
  return tableLineText(line, state).slice(line.name.length).replace(/^ · /, "");
}

/** The group's folded line: "Tables · 4 tables", and "Tables · 4 tables · 1 out of date" when one is. */
export function groupLineText(states: TableState[]): { text: string; stale: boolean } {
  const stale = states.filter((s) => s.kind === "outOfDate").length;
  const waiting = states.filter((s) => s.kind === "notRun" || s.kind === "notRunSinceOpening").length;
  const parts = ["Tables", plural(states.length, "table")];
  if (stale) parts.push(`${stale} out of date`);
  else if (waiting) parts.push(`${waiting} not run`);
  return { text: parts.join(" · "), stale: stale > 0 };
}

// The app's own first line, exactly in its format (domain/table_cells.py USES_PYTHON, USES_SQL).
const USE = "[A-Za-z_]\\w*(?: @cell\\d+)?";
const USES_PYTHON = new RegExp(`^# uses ${USE}(?:, ${USE})*$`);
const USES_SQL = new RegExp(`^-- uses ${USE}(?:, ${USE})*$`);
const USES_HTML = new RegExp(`^<!-- uses ${USE}(?:, ${USE})* -->$`);

/** How a cell writes its uses line: a Python comment, a SQL one, or an HTML one. */
export type UsesForm = "python" | "sql" | "html";

/** A cell's source with its uses line as it should be: added, changed or taken away. Only a first
 *  line in exactly the app's format is ever touched. */
export function withUses(source: string, line: string | null, form: UsesForm): string {
  const at = source.indexOf("\n");
  const first = at < 0 ? source : source.slice(0, at);
  const own = (form === "html" ? USES_HTML : form === "sql" ? USES_SQL : USES_PYTHON).test(first);
  const rest = own ? (at < 0 ? "" : source.slice(at + 1)) : source;
  return line === null ? rest : `${line}\n${rest}`;
}

/** The first line of a cell's code, for a link's hover (not the app's uses line). */
export function firstLine(source: string): string {
  for (const line of source.split("\n")) {
    if (line.trim() && !USES_PYTHON.test(line) && !USES_SQL.test(line) && !USES_HTML.test(line)) return line.trim().slice(0, 160);
  }
  return "";
}

/** The parts of a note with its cell links: "orders is made at ", {cell: 7}, " (it needs ...)". */
export function noteParts(note: string): (string | { cell: number })[] {
  const parts: (string | { cell: number })[] = [];
  let at = 0;
  for (const match of note.matchAll(/@cell(\d+)\b/g)) {
    if (match.index > at) parts.push(note.slice(at, match.index));
    parts.push({ cell: Number(match[1]) });
    at = match.index + match[0].length;
  }
  if (at < note.length) parts.push(note.slice(at));
  return parts;
}
