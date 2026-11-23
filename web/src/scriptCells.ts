/**
 * scriptCells.ts: a script's cells as text, the rules that need no page: its numbered cells read from its
 * `# %%` markers, the indent lines share, where a new cell goes and what closes it, a marker with a pane's
 * height or a cell's name on it, a cell's lines replaced, a table renamed in its markers, a table's cell run
 * the safe way inside lines. Pulled out of workbenchScript.ts's scriptView (the craft review of 2026-11-22,
 * refactor 8), so the script is tested in parts (tests/test_script_cells.py runs these in Node). Pure: no
 * DOM, no request. [FUNCTION]
 */

// A script cell's name is its marker's own words (domain/table_cells.py marker_words): words that
// would read as the marker's grammar are written after a backslash.
const GRAMMAR = /^(?:\[(?:\d+|table|transformations|html|streamlit)\]|height=\d|\\)/;
const MARKER = /^(# ?%%(?: \[\d+\])?(?: \[(?:table|transformations)\] [A-Za-z_][\w-]*)?(?: \[(?:html|streamlit)\])?(?: height=\d{1,5})?)((?: .*)?)$/;

export const markerWords = (name: string): string => (GRAMMAR.test(name) ? `\\${name}` : name);

export function markerName(words: string): string {
  const said = words.trim();
  return said.startsWith("\\") && GRAMMAR.test(said.slice(1)) ? said.slice(1) : said;
}

/** A marker line's own words (the cell's name as written), or null when the line is no marker. */
export function markerWordsOf(line: string): string | null {
  const found = MARKER.exec(line);
  return found ? (found[2] ?? "") : null;
}

/** A marker line with the cell's name in place of its words. */
export function withMarkerName(line: string, name: string): string {
  const found = MARKER.exec(line);
  if (!found) return line;
  return name ? `${found[1]} ${markerWords(name)}` : found[1]!;
}

/** A script's numbered cell as Copy cell takes it: its number, its code, its name. */
export interface PieceSource {
  cell: number;
  code: string;
  name?: string;
  kind?: "html";
  form?: "script";
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

/** Two paths of one file: either separator, letters without case. */
export const sameFile = (a: string | null, b: string | null): boolean => !!a && !!b && a.replace(/\\/g, "/").toLowerCase() === b.replace(/\\/g, "/").toLowerCase();

const escaped = (name: string): string => name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** The marker line of the cell numbered `number`. */
const markerOf = (number: number): RegExp => new RegExp(`^# ?%% \\[${number}\\](?:\\s|$)`);

/** An HTML cell's pane height as its marker keeps it: whole pixels, 60 to 2000. */
export const paneHeight = (height: number): number => Math.max(60, Math.min(2000, Math.round(height)));

/** A new cell (its marker and its lines) put into a script: after the cell that ends at line `end` (null:
 *  at the script's end). What follows it in the file is the user's Python: a plain marker keeps that a cell
 *  of its own. The new text, and the line (from 0) the cell's marker is on. */
export function withCell(text: string, end: number | null, cell: string[]): { text: string; at: number } {
  const lines = text.split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  const at = end === null ? lines.length : Math.min(end, lines.length);
  const after = lines.slice(at);
  const closing = after.some((l) => l.trim()) && !/^# ?%%/.test(after.find((l) => l.trim()) ?? "") ? ["# %%"] : [];
  return { text: [...lines.slice(0, at), ...cell, ...closing, ...after].join("\n") + "\n", at };
}

/** A DAX cell's lines in a script. The file runs as plain Python: the cell is one sab.dax() call, its DAX a
 *  string; `imported`: the import line it brings when the script has none. */
export function daxCell(text: string, dataset: string, source: string): { lines: string[]; imported: number; first: string } {
  const imported = /^\s*import swissarmybench as sab\b/m.test(text) ? [] : ["import swissarmybench as sab"];
  const dax = (source.trim() || "EVALUATE ").replace(/\\/g, "\\\\").replace(/"""/g, '\\"\\"\\"');
  return { lines: ["# %% [dax]", ...imported, `result = sab.dax(${JSON.stringify(dataset)}, """`, ...dax.split("\n"), '""")'], imported: imported.length, first: dax.split("\n")[0]! };
}

/** The script with an HTML cell's pane height on its marker (`height=320`), or without one (null). The
 *  cell is found by its number, else by its marker's line (from 1). Null: no such marker. */
export function withHeight(text: string, number: number | null, line: number, height: number | null): string | null {
  const lines = text.split("\n");
  const at = number === null ? line - 1 : lines.findIndex((l) => markerOf(number).test(l));
  // (`[streamlit]` was a kind of cell once: the word goes when the marker is written.)
  const found = /^(# ?%%(?: \[\d+\])?(?: \[html\])?)(?: \[streamlit\])?(?: height=\d+)?(.*)$/.exec(lines[at] ?? "");
  if (!found) return null;
  lines[at] = `${found[1]}${height === null ? "" : ` height=${height}`}${found[2]}`;
  return lines.join("\n");
}

/** The script with the cell numbered `number` named: its marker's own words ("" takes the name away).
 *  Null: no such cell. */
export function withName(text: string, number: number, name: string): string | null {
  const lines = text.split("\n");
  const at = lines.findIndex((l) => markerOf(number).test(l));
  if (at < 0) return null;
  lines[at] = withMarkerName(lines[at]!, name);
  return lines.join("\n");
}

/** The script with `source` as the lines of the cell numbered `number`, under its marker; a blank line
 *  before the next marker stays, as typed. Null: no such cell. */
export function withSource(text: string, number: number, source: string): string | null {
  const lines = text.split("\n");
  const at = lines.findIndex((l) => markerOf(number).test(l));
  if (at < 0) return null;
  let end = lines.findIndex((l, i) => i > at && /^# ?%%/.test(l));
  if (end < 0) end = lines.length;
  const gap = end < lines.length && !lines[end - 1]?.trim() ? [""] : [];
  return [...lines.slice(0, at + 1), ...source.replace(/\n+$/, "").split("\n"), ...gap, ...lines.slice(end)].join("\n");
}

/** Whether the script's text holds this table's read-only cell (`# %% [8] [transformations] orders`). */
export const holdsTableCell = (text: string, name: string): boolean => new RegExp(`^# ?%%(?: \\[\\d+\\])? \\[transformations\\] ${escaped(name)}\\b`, "m").test(text);

/** A table renamed in the grid: its markers carry the name (`# %% [8] [transformations] orders`). */
export function renamedTable(text: string, from: string, to: string): string {
  const marker = new RegExp(`^(# ?%%(?: \\[\\d+\\])? \\[(?:table|transformations)\\] )${escaped(from)}(?![\\w-])`, "gm");
  return text.replace(marker, `$1${to}`);
}

/** The tables whose cell came with the file: they have not run since it opened. */
export const tablesInFile = (text: string): string[] => [...text.matchAll(/^# ?%%(?: \[\d+\])? \[transformations\] ([A-Za-z_][\w-]*)/gm)].map((m) => m[1]!);

/** The first line with code after `line` (from 1): blank lines and comments are passed over; at most the
 *  last line. */
export function nextCodeLine(text: string, line: number): number {
  const lines = text.split("\n");
  let next = line + 1;
  while (next <= lines.length && (!lines[next - 1]!.trim() || lines[next - 1]!.trim().startsWith("#"))) next++;
  return Math.min(next, lines.length);
}

/** Lines `start` to `end` of a script as they run: a table's read-only cell inside them goes through the
 *  kernel's safe run (client/table_cells.py), on the same lines, so it never transforms a transformed
 *  table. `block`: those lines' text; `variable`: a table's name in Python. */
export function safeBlock(block: string, start: number, end: number, cells: { role: string; table: string | null; line: number; end: number }[], variable: (table: string) => string): string {
  const lines = block.split("\n");
  for (const cell of cells) {
    if (cell.role !== "transformations" || !cell.table || cell.line + 1 < start || cell.end > end || cell.end <= cell.line) continue;
    const from = cell.line + 1 - start;
    const to = cell.end - start;
    const body = lines.slice(from, to + 1).join("\n");
    if (!body.trim()) continue;
    lines[from] = `__import__('swissarmybench.client.table_cells', fromlist=['run']).run(${JSON.stringify(variable(cell.table))}, ${JSON.stringify(body)})`;
    for (let k = from + 1; k <= to; k++) lines[k] = "";
  }
  return lines.join("\n");
}
