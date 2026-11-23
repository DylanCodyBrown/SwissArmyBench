/**
 * workbenchScriptCells.ts: a script's cells changed as text (its `# %%` markers are the cells): an HTML, a
 * Python or a DAX cell added after the cursor's cell, a cell copied for a notebook, named, its lines
 * replaced, a table renamed in its markers, the Tables group folded. The text's own rules are
 * scriptCells.ts's. A part of workbenchScript.ts's scriptView (workbenchScriptState.ts says how the parts
 * fit). [VIEW]
 */
import { cleanName, copyCell, withMarkerName } from "./cellClipboard";
import type { CodeEditor } from "./lazy/codeEditor";
import { daxCell, paneHeight, renamedTable, scriptPieces, withCell, withName, withSource } from "./scriptCells";
import { scriptBody } from "./workbenchHtml";
import { arrange } from "./workbenchScriptRuns";
import { type Script, tableStarts, textOf } from "./workbenchScriptState";

const ready = (sc: Script): CodeEditor => {
  if (!sc.editor) throw new Error("The script's editor is not ready yet.");
  return sc.editor;
};

/** Where a new cell goes: the end of the cursor's cell (one of the user's, outside the Tables group) when
 *  the outline describes this text; null: the script's end. */
function cursorEnd(sc: Script, editor: CodeEditor): number | null {
  const here = sc.outlineVersion === sc.version ? sc.outline.cells.find((c) => editor.cursorLine() >= c.line && editor.cursorLine() <= c.end && !c.grouped) : undefined;
  return here ? here.end : null;
}

/** The outline asked for at once, not after the typing's pause. */
async function arrangeNow(sc: Script): Promise<void> {
  if (sc.quiet !== null) window.clearTimeout(sc.quiet);
  sc.quiet = null;
  await arrange(sc, true);
}

/** An HTML cell after the cursor's cell (or at the end): its marker, its HTML as one string. */
export async function addHtml(sc: Script, source = "", height: number | null = null): Promise<void> {
  const editor = ready(sc);
  const marker = `# %% [html]${height === null ? "" : ` height=${paneHeight(height)}`}`;
  const made = withCell(editor.value(), cursorEnd(sc, editor), [marker, ...scriptBody(source).replace(/\n$/, "").split("\n")]);
  editor.replaceText(made.text);
  editor.focus();
  editor.moveTo(made.at + 3); // the first line of the HTML
  await arrangeNow(sc);
}

/** A Python cell after the cursor's cell (or at the end), with a name on its marker. */
export async function addCode(sc: Script, source: string, name = ""): Promise<void> {
  const editor = ready(sc);
  // The name is the marker's own words (written after a backslash when it would read as its grammar).
  const marker = withMarkerName("# %%", cleanName(name));
  const made = withCell(editor.value(), cursorEnd(sc, editor), [marker, ...source.replace(/\n$/, "").split("\n")]);
  editor.replaceText(made.text);
  editor.reveal(made.at + 2, 1);
  await arrangeNow(sc);
}

/** A DAX cell after the cursor's cell (or at the end): one sab.dax() call on a dataset. */
export async function addDax(sc: Script, dataset: string, source = ""): Promise<void> {
  const editor = ready(sc);
  const dax = daxCell(editor.value(), dataset, source);
  const made = withCell(editor.value(), cursorEnd(sc, editor), dax.lines);
  editor.replaceText(made.text);
  editor.reveal(made.at + 3 + dax.imported, dax.first.length + 1); // in the DAX
  await arrangeNow(sc);
}

/** Copy the cell the cursor is in (or the numbered one), for a paste into a notebook. */
export function copy(sc: Script, number?: number): { cell: number; document: string | null } {
  const line = sc.editor?.cursorLine() ?? 0;
  const cell = sc.outline.cells.find((c) => (number === undefined ? line >= c.line && line <= c.end : c.number === number) && !c.grouped);
  if (!cell || cell.number === null) throw new Error(number === undefined ? "The cursor is not in a numbered cell (a `# %%` cell)." : `This script has no Python or HTML cell ${number}.`);
  // An HTML cell is copied as its HTML: a notebook pastes an HTML cell.
  const html = cell.kind === "html";
  if (html && cell.html == null) throw new Error(cell.problem ?? "This HTML cell's string is not whole yet.");
  const source = html ? (cell.html ?? "") : (scriptPieces(textOf(sc)).find((c) => c.cell === cell.number)?.code ?? "");
  const where = { document: null, title: "this script" };
  copyCell({ document: where.document, cell: cell.number, title: where.title, kind: html ? "html" : "code", source, connection: null, height: cell.height ?? null });
  return { cell: cell.number, document: where.document };
}

/** Name a cell: its marker's own words ("" takes the name away); without a number, the cursor's cell. */
export function nameCell(sc: Script, number: number | undefined, name: string): { cell: number; name: string | null } {
  const line = sc.editor?.cursorLine() ?? 0;
  const cell = sc.outline.cells.find((c) => (number === undefined ? line >= c.line && line <= c.end : c.number === number) && !c.grouped && !c.role);
  if (!cell || cell.number === null || !sc.editor) throw new Error(number === undefined ? "The cursor is not in a numbered cell (a `# %%` cell)." : `This script has no cell ${number} of yours.`);
  const said = cleanName(name);
  const next = withName(sc.editor.value(), cell.number, said);
  if (next === null) throw new Error(`This script has no cell ${number}.`);
  sc.editor.replaceText(next);
  return { cell: cell.number, name: said || null };
}

/** Put this text as the lines of the cell numbered `number`, under its marker (a thin cell's move). */
export function setSource(sc: Script, number: number, source: string): void {
  const editor = ready(sc);
  const next = withSource(editor.value(), number, source);
  if (next === null) throw new Error(`This script has no cell ${number}.`);
  editor.replaceText(next);
}

/** The cursor to the end of the cursor's cell's marker line, where its name is typed. */
export function editName(sc: Script): void {
  const line = sc.editor?.cursorLine() ?? 0;
  const cell = sc.outline.cells.find((c) => line >= c.line && line <= c.end && !c.grouped && !c.role);
  if (!cell || !sc.editor) throw new Error("The cursor is not in a cell of yours (a `# %%` cell).");
  sc.editor.reveal(cell.line, (sc.editor.value().split("\n")[cell.line - 1] ?? "").length + 1);
}

/** A table was renamed in the grid: its run record and its markers follow. */
export function renameTable(sc: Script, from: string, to: string): void {
  const record = sc.records.get(from);
  if (record) sc.records.set(to, record);
  sc.records.delete(from);
  if (sc.editor) sc.editor.replaceText(renamedTable(sc.editor.value(), from, to));
}

/** Fold or unfold the Tables group (or one table of it). */
export function foldTables(sc: Script, folded: boolean, table?: string): void {
  if (!sc.editor || !sc.outline.region) return;
  const start = table ? tableStarts(sc).get(table) : sc.outline.region[0];
  if (start === undefined) return;
  if (folded) sc.editor.fold([start]);
  else sc.editor.unfold(table ? [sc.outline.region[0], start] : [start]);
}
