/**
 * workbenchNotebookEdits.ts: what is done to a notebook's cells: a cell's kind changed, opened for editing,
 * the next one after a run, inserted, moved, named, copied and pasted (in any notebook), deleted and put
 * back (Undo), duplicated, its output cleared or hidden. A part of workbenchNotebook.ts's notebookView
 * (workbenchNotebookState.ts says how the parts fit). [VIEW]
 */
import { cleanName, copiedCell, copyCell } from "./cellClipboard";
import { namedConnections } from "./connectionSql";
import { toast } from "./dom";
import { drawn, hasSource, isApp, isHeading, twoFaced } from "./notebookCells";
import { knowTypes } from "./workbenchNotebookRuns";
import { type Cell, type CellKind, dataOf, drawNamed, edited, empty, focusEditor, indexOf, infoOf, KINDS, LANGUAGE, type Notebook, relabel, ROUTED, select, sourceOf, sources, toCommandMode, usesForm } from "./workbenchNotebookState";
import { arrange, typedSoon } from "./workbenchNotebookTables";
import { editHtml, editMarkdown } from "./workbenchNotebookText";
import { withUses } from "./workbenchTables";

export function setKind(nb: Notebook, cell: Cell, kind: CellKind): void {
  if (cell.kind === kind) return;
  if (cell.kind === "markdown" && cell.element.classList.contains("rendered")) editMarkdown(cell);
  // The uses line changes its form with the kind (`# uses` in Python, `<!-- uses -->` in HTML): the
  // old one goes, and the next arrangement writes the new one.
  const bare = withUses(sourceOf(cell), null, usesForm(cell.kind));
  if (bare !== sourceOf(cell)) {
    if (cell.editor) cell.editor.replaceText(bare);
    cell.source = bare;
  }
  const wasHtml = twoFaced(cell);
  cell.kind = kind;
  cell.kindPicker.value = kind;
  cell.part.textContent = "";
  cell.element.classList.remove("kind-code", "kind-sql", "kind-dax", "kind-markdown", "kind-html", "kind-typescript", "kind-tsx", "previewed", "stale");
  cell.element.classList.add(`kind-${kind}`);
  if (cell.htmlRun && (kind === "markdown" || kind === "html")) cell.htmlRun = undefined; // the other kind's values
  if (wasHtml || drawn(kind)) {
    // Its outputs were the other kind's: an HTML cell keeps a design, not a run's output.
    cell.element.classList.remove("rendered");
    cell.area.set([]);
    cell.htmlRun = undefined;
    cell.htmlNotes = [];
    setTimeout(() => cell.editor?.layout(), 0);
  }
  cell.connectionPicker.hidden = !hasSource(kind);
  drawNamed(nb, cell);
  // A SQL cell's connection is not a DAX cell's dataset: one that is not this kind's goes.
  const duck = kind === "sql" && !cell.connection && namedConnections(sourceOf(cell), nb.connections()).length > 0;
  if (hasSource(kind) && !duck && (!cell.connection || !sources(nb, kind).includes(cell.connection))) cell.connection = sources(nb, kind)[0] ?? null;
  // The box shows the connection the cell runs on (it is drawn again on focus; once showed the
  // %sql_connect placeholder while the cell ran on the first connection).
  if (hasSource(kind)) cell.connectionPicker.dispatchEvent(new Event("focus"));
  cell.editor?.setLanguage(LANGUAGE[kind]);
  if (ROUTED.includes(kind)) knowTypes(kind);
  relabel(nb);
  edited(nb);
  typedSoon(nb);
}

export function edit(nb: Notebook, cell: Cell): void {
  select(nb, cell);
  if (cell.kind === "markdown" && cell.element.classList.contains("rendered")) editMarkdown(cell);
  else if (twoFaced(cell) && cell.element.classList.contains("rendered")) editHtml(cell);
  else focusEditor(cell);
}

export function next(nb: Notebook, cell: Cell): void {
  const following = nb.cells[indexOf(nb, cell) + 1] ?? nb.act.make(empty(cell.kind === "markdown" || cell.kind === "html" ? "code" : cell.kind, cell.connection), nb.cells.length);
  select(nb, following);
  following.element.scrollIntoView({ block: "nearest" });
  focusEditor(following);
}

export function insertAt(nb: Notebook, at: number, kind: CellKind = "code", source = ""): Cell {
  // A SQL cell whose query names a connection's tables ([Finance].Sales) runs in DuckDB: no connection.
  const duck = kind === "sql" && namedConnections(source, nb.connections()).length > 0;
  const cell = nb.act.make({ ...empty(kind, hasSource(kind) && !duck ? (sources(nb, kind)[0] ?? null) : null), source }, Math.max(0, Math.min(at, nb.cells.length)));
  select(nb, cell);
  cell.element.scrollIntoView({ block: "nearest" });
  focusEditor(cell);
  edited(nb);
  if (source) typedSoon(nb);
  return cell;
}

export function place(nb: Notebook, cell: Cell, to: number): void {
  nb.cells.splice(indexOf(nb, cell), 1);
  nb.cells.splice(to, 0, cell);
  nb.list.insertBefore(cell.element, nb.cells[to + 1]?.element ?? null);
  relabel(nb);
}

export function moveCell(nb: Notebook, cell: Cell, by: number): void {
  const from = indexOf(nb, cell);
  const to = from + by;
  if (to < 0 || to >= nb.cells.length) return;
  place(nb, cell, to);
  nb.undos.push({ kind: "move", cell, from });
  cell.element.scrollIntoView({ block: "nearest" });
  edited(nb);
}

// ===== a cell's name (docs/ideas.md, named cells): shown in its head, kept in its metadata =====

export function drawName(cell: Cell): void {
  const input = cell.nameButton;
  if (!input) return;
  if (document.activeElement !== input) input.value = cell.name ?? "";
  input.classList.toggle("unnamed", !cell.name);
  input.title = cell.name ?? "Name the cell";
}

export function setName(nb: Notebook, cell: Cell, typed: string): void {
  const name = cleanName(typed) || null;
  if (cell.nameButton && document.activeElement !== cell.nameButton) cell.nameButton.value = name ?? "";
  if (name === cell.name) return drawName(cell);
  cell.name = name;
  drawName(cell);
  edited(nb); // saved with the cell
}

export function editName(nb: Notebook, cell: Cell): void {
  const input = cell.nameButton;
  if (!input || !input.isConnected) return;
  select(nb, cell);
  input.focus();
  input.select();
}

// ===== a cell copied: pasted in any notebook =====

export const linkOf = (cell: Cell): { document: string | null; cell: number; title: string } => ({ document: null, cell: cell.number, title: "this notebook" });

/** Copy: the cell's link and the cell itself, for every Workbench window. */
export function copy(cell: Cell): { cell: number; document: string | null } | null {
  if (isApp(cell.role)) return null;
  const data = dataOf(cell);
  const link = linkOf(cell);
  copyCell({ ...link, kind: data.kind, source: data.source, connection: data.connection, height: data.height ?? null });
  return { cell: link.cell, document: link.document };
}

/** Paste: the copied cell as a new cell below (its own number; nothing of the Tables group). */
export function paste(nb: Notebook, after: Cell | null): boolean {
  const held = copiedCell();
  if (!held) return false;
  const kind = (KINDS as string[]).includes(held.kind) ? (held.kind as CellKind) : "code";
  const made = nb.act.make({ ...empty(kind, held.connection), source: held.source, height: held.height }, after ? indexOf(nb, after) + 1 : nb.cells.length);
  select(nb, made);
  made.element.scrollIntoView({ block: "nearest" });
  toCommandMode(nb, made);
  edited(nb);
  typedSoon(nb);
  return true;
}

export function removeCell(nb: Notebook, cell: Cell): void {
  // The app's own cells go when their table does: a heading is never deleted, a table's cell only
  // once the table is closed in the grid (an open table always has its cell).
  if (isHeading(cell.role)) return;
  if (cell.role === "transformations" && infoOf(nb, cell.table)) {
    toast(`${cell.table} is open in the grid, so it keeps its cell. Close the table there first.`);
    return;
  }
  const at = indexOf(nb, cell);
  const data = dataOf(cell);
  nb.cells.splice(at, 1);
  cell.editor?.dispose();
  cell.design?.dispose();
  cell.element.remove();
  // The last cell gone: an empty one in its place (Undo takes it away again if still empty).
  const filler = nb.cells.length ? null : nb.act.make(empty(), 0);
  nb.undos.push({ kind: "delete", data, at, filler });
  if (nb.undos.length > 100) nb.undos.shift();
  const after = nb.cells[Math.min(at, nb.cells.length - 1)];
  if (after) {
    select(nb, after);
    if (document.activeElement === document.body) after.element.focus();
  }
  relabel(nb);
  edited(nb);
  if (cell.role === "transformations") void arrange(nb, true);
  toast("Cell deleted.", "info", { label: "Undo", run: () => void undo(nb) });
}

export function undo(nb: Notebook): boolean {
  const last = nb.undos.pop();
  if (!last) return false;
  if (last.kind === "move") {
    if (nb.cells.includes(last.cell)) place(nb, last.cell, Math.min(last.from, nb.cells.length - 1));
  } else {
    // The empty cell made when the last one went is replaced by the one coming back.
    const lone = last.filler && nb.cells.includes(last.filler) && !(last.filler.editor?.value() ?? last.filler.source).trim() ? last.filler : null;
    const back = nb.act.make(last.data, Math.min(last.at, nb.cells.length));
    if (lone) {
      nb.cells.splice(indexOf(nb, lone), 1);
      lone.editor?.dispose();
      lone.element.remove();
      relabel(nb);
    }
    select(nb, back);
    back.element.scrollIntoView({ block: "nearest" });
  }
  edited(nb);
  return true;
}

export function duplicate(nb: Notebook, cell: Cell): void {
  if (isApp(cell.role)) return;
  // A copy is a new cell: its own number, and no part in the Tables group.
  const copy = nb.act.make({ ...dataOf(cell), outputs: [], execution_count: null, number: null, role: "", table: null, grouped: false, steps: null }, indexOf(nb, cell) + 1);
  select(nb, copy);
  edited(nb);
}

export function clearOutput(nb: Notebook, cell: Cell): void {
  if (isHeading(cell.role)) return;
  cell.area.set([]);
  cell.execution_count = null;
  cell.count.textContent = "[ ]";
  cell.element.classList.remove("failed", "output-hidden");
  edited(nb);
}

export function toggleOutput(cell: Cell): void {
  cell.element.classList.toggle("output-hidden");
}
