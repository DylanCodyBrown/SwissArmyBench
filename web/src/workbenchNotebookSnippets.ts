/**
 * workbenchNotebookSnippets.ts: snippets in a notebook: text for a cell, from the starter pack or the user's
 * own (starters.ts), filled by its form and put where it was dropped or at the cursor; the cell's menu's
 * Insert a snippet…, and the agent's insert. A part of workbenchNotebook.ts's notebookView
 * (workbenchNotebookState.ts says how the parts fit). [VIEW]
 */
import { api } from "./api";
import { errorHere } from "./errorNote";
import { isApp, snippetLanguage } from "./notebookCells";
import { type FilledSnippet, fillSnippet, pickSnippet, refusal, SNIPPET_CELL, type SnippetLanguage } from "./starters";
import { insertAt, setName } from "./workbenchNotebookEdits";
import { byNumber, type Cell, type CellKind, edited, indexOf, type Notebook, select, sourceOf } from "./workbenchNotebookState";
import { typedSoon } from "./workbenchNotebookTables";
import { showDesign, showMarkdown } from "./workbenchNotebookText";

// ===== snippets: text for a cell, from the starter pack or the user's own (starters.ts) =====

/** The language of the snippets a cell of this kind takes (none: Markdown, SQL, the app's cells). */

/** Put a filled snippet into a cell, where it was dropped or at the cursor (an empty cell takes it
 *  whole). A Streamlit piece names the cell it goes into, unless it has a name. */
export function putSnippet(nb: Notebook, cell: Cell, filled: FilledSnippet, x?: number, y?: number): void {
  if (!sourceOf(cell).trim()) {
    if (cell.editor) cell.editor.setValue(filled.text);
    else cell.source = filled.text;
  } else if (cell.editor) {
    cell.editor.insertAt(filled.text, x, y);
  } else {
    cell.source = `${cell.source.replace(/\n*$/, "")}\n${filled.text}`;
  }
  if (filled.cell_name && !cell.name) setName(nb, cell, filled.cell_name);
  select(nb, cell);
  edited(nb);
  typedSoon(nb);
  if (cell.kind === "html" && !cell.editor?.hasFocus()) showDesign(cell);
  if (cell.kind === "markdown" && !cell.editor?.hasFocus()) showMarkdown(nb, cell);
}

/** A snippet dropped on a cell (or the list, `cell` null: a new cell of its kind at the end). A cell
 *  of another language refuses it; a Streamlit piece on a Python cell that holds code makes a cell
 *  of its own below it. */
export async function dropSnippet(nb: Notebook, cell: Cell | null, snippet: { name: string; language: SnippetLanguage }, x?: number, y?: number): Promise<void> {
  const no = cell ? refusal(snippet.language, cell.kind) ?? (isApp(cell.role) ? "This cell follows the grid: drop it on a cell of yours." : null) : null;
  if (no) return errorHere(no);
  const filled = await fillSnippet(snippet.name, cell?.kind === "dax" ? cell.connection : null);
  if (!filled) return;
  const kind = SNIPPET_CELL[filled.language];
  // A Streamlit piece or a Python snippet (a Write starter) is a whole cell: a cell of its own below one that holds code.
  const own = !cell || ((filled.language === "streamlit" || filled.language === "python") && sourceOf(cell).trim());
  const target = own ? insertAt(nb, cell ? indexOf(nb, cell) + 1 : nb.cells.length, kind) : cell;
  putSnippet(nb, target, filled, own ? undefined : x, own ? undefined : y);
}

/** A cell's menu: Insert a snippet… (the snippets of its language), filled, at the cursor. */
export async function insertSnippetInto(nb: Notebook, cell: Cell): Promise<void> {
  const language = snippetLanguage(cell);
  if (!language) return;
  const name = await pickSnippet(language);
  if (name) await dropSnippet(nb, cell, { name, language });
}

/** The agent's (workbench_snippet_insert): filled with `values` (each placeholder's own otherwise),
 *  into the cell numbered `number`, else the selected cell when it is of the snippet's kind (an empty
 *  one for a Streamlit piece), else a new cell of its kind below the selected one. */
export async function insertSnippet(nb: Notebook, name: string, values: Record<string, unknown>, number?: number): Promise<{ cell: number; kind: CellKind; name: string | null }> {
  const filled = await api<FilledSnippet>(`/blades/${encodeURIComponent(name)}/snippet`, "POST", { values });
  const kind = SNIPPET_CELL[filled.language];
  let cell = number === undefined ? nb.selected : byNumber(nb, number);
  if (number !== undefined) {
    if (!cell || isApp(cell.role)) throw new Error(`This notebook has no cell ${number} of yours.`);
    const no = refusal(filled.language, cell.kind);
    if (no) throw new Error(no);
  }
  if (!cell || cell.kind !== kind || isApp(cell.role) || (number === undefined && (filled.language === "streamlit" || filled.language === "python") && sourceOf(cell).trim())) {
    cell = insertAt(nb, nb.selected ? indexOf(nb, nb.selected) + 1 : nb.cells.length, kind);
  }
  putSnippet(nb, cell, filled);
  return { cell: cell.number, kind: cell.kind, name: cell.name };
}

/** The Data Explorer's Insert: a result's code at the selected cell's cursor, as the cell's language writes
 *  it (a SQL cell's SQL, a Python cell's Python); else a new cell below of the kind it has code for. The
 *  cell it went into. */
export function insertCode(nb: Notebook, insert: { sql?: string; python?: string }): { cell: number; kind: CellKind } {
  let cell = nb.selected && !isApp(nb.selected.role) ? nb.selected : null;
  const code = cell?.kind === "sql" ? insert.sql : cell?.kind === "code" ? insert.python : undefined;
  if (!cell || code === undefined) {
    const kind: CellKind = insert.python === undefined ? "sql" : "code";
    cell = insertAt(nb, cell ? indexOf(nb, cell) + 1 : nb.selected ? indexOf(nb, nb.selected) + 1 : nb.cells.length, kind);
  }
  const text = (cell.kind === "sql" ? insert.sql : insert.python) ?? "";
  if (!sourceOf(cell).trim()) {
    if (cell.editor) cell.editor.setValue(text);
    else cell.source = text;
  } else if (cell.editor) cell.editor.insertAt(text);
  else cell.source = `${cell.source.replace(/\n*$/, "")}\n${text}`;
  select(nb, cell);
  edited(nb);
  typedSoon(nb);
  return { cell: cell.number, kind: cell.kind };
}
