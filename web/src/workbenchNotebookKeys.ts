/**
 * workbenchNotebookKeys.ts: a notebook's command mode: Jupyter's keys on the selected cell while the focus
 * is on the cell, not its editor (which key does what is notebookCells.ts's commandFor), and a snippet
 * dropped between or after the cells. A part of workbenchNotebook.ts's notebookView
 * (workbenchNotebookState.ts says how the parts fit). [VIEW]
 */
import { commandFor } from "./notebookCells";
import { draggedSnippet, SNIPPET_DRAG } from "./starters";
import { copy, edit, insertAt, next, paste, removeCell, setKind, toggleOutput, undo } from "./workbenchNotebookEdits";
import { run } from "./workbenchNotebookRuns";
import { dropSnippet } from "./workbenchNotebookSnippets";
import { indexOf, type Notebook, toCommandMode } from "./workbenchNotebookState";
import { toggleFold } from "./workbenchNotebookTables";

/** Listen on the cells' list: command mode's keys, and a snippet dropped on the list itself. */
export function commandKeys(nb: Notebook): void {
  // A snippet dropped between or after the cells: a new cell of its kind at the end.
  nb.list.addEventListener("dragover", (e) => {
    if (e.dataTransfer?.types.includes(SNIPPET_DRAG)) e.preventDefault();
  });
  nb.list.addEventListener("drop", (e) => {
    const snippet = draggedSnippet(e.dataTransfer);
    if (!snippet) return;
    e.preventDefault();
    void dropSnippet(nb, null, snippet);
  });
  // Command mode: Jupyter's keys on the selected cell when the focus is on the cell, not its editor.
  nb.list.addEventListener("keydown", (e) => {
    const target = e.target as HTMLElement;
    if (!target.matches(".wb-cell, .wb-tcell") || !nb.selected) return;
    const cell = nb.selected;
    const at = indexOf(nb, cell);
    const command = commandFor({ key: e.key, shift: e.shiftKey, ctrl: e.ctrlKey, meta: e.metaKey, alt: e.altKey }, cell.role);
    if (!command) return;
    e.preventDefault();
    e.stopPropagation();
    if (command === "runNext") void run(nb, cell).then(() => next(nb, cell));
    else if (command === "run") void run(nb, cell);
    else if (command === "fold") toggleFold(nb, cell);
    else if (command === "edit") edit(nb, cell);
    else if (command === "above") insertAt(nb, at, "code");
    else if (command === "below") insertAt(nb, at + 1, "code");
    else if (command === "d") {
      if (Date.now() - nb.pendingD < 800) {
        nb.pendingD = 0;
        removeCell(nb, cell);
      } else nb.pendingD = Date.now();
    } else if (command === "copy") void copy(cell);
    else if (command === "paste") void paste(nb, cell);
    else if (command === "undo") undo(nb);
    else if (command === "down") {
      const below = nb.cells.slice(at + 1).find((c) => !c.element.hidden); // a folded group's cells are passed over
      if (below) toCommandMode(nb, below);
    } else if (command === "up") {
      const above = nb.cells.slice(0, at).reverse().find((c) => !c.element.hidden);
      if (above) toCommandMode(nb, above);
    } else if (command === "output") toggleOutput(cell);
    else setKind(nb, cell, command);
  });
}

