/**
 * workbenchNotebookErrors.ts: a notebook's errors (workbenchErrors.ts's panel in a cell's output): which
 * cell a frame ran in, the failing expression marked in its cell (and the calls that led there in theirs),
 * the fixes (replace, import, a cell that does it another way, run the cell that makes a name, install), a
 * frame's go-to. A part of workbenchNotebook.ts's notebookView (workbenchNotebookState.ts says how the
 * parts fit). [VIEW]
 */
import { toast } from "./dom";
import { errorHere } from "./errorNote";
import { hasSource, makesName } from "./notebookCells";
import { type ErrorDetail, type Frame, problemsFor, sqlProblems, yourFrame } from "./workbenchErrors";
import { insertAt } from "./workbenchNotebookEdits";
import { run } from "./workbenchNotebookRuns";
import { type Cell, indexOf, type Notebook, select } from "./workbenchNotebookState";
import type { ErrorHooks } from "./workbenchOutputs";

// ===== errors: which cell a frame is in, its marks, its fixes =====

/** The cell a frame ran in: the one with that run number, or `running` for the newest number. */
export function cellOf(nb: Notebook, frame: Pick<Frame, "where" | "cell">, detail: ErrorDetail, running: Cell): Cell | null {
  if (frame.where !== "cell" || frame.cell === null) return null;
  const numbers = detail.chain.flatMap((e) => e.frames.map((f) => f.cell ?? 0)).concat(detail.chain.map((e) => e.syntax?.cell ?? 0));
  if (frame.cell === Math.max(...numbers)) return running;
  return nb.cells.find((c) => c !== running && c.execution_count === frame.cell) ?? null;
}

export function errorHooks(nb: Notebook, running: Cell): ErrorHooks {
  let shown: ErrorDetail | null = null;
  const where = (): Cell => {
    const entry = shown?.chain[shown.chain.length - 1];
    const frame = yourFrame(entry) ?? (entry?.syntax ? ({ where: "cell", cell: entry.syntax.cell } as Frame) : null);
    return (frame && shown && cellOf(nb, frame, shown, running)) || running;
  };
  return {
    shown: (detail) => {
      shown = detail;
      if (hasSource(running.kind)) {
        running.editor?.setProblems(sqlProblems(detail));
        return;
      }
      for (const c of nb.cells) {
        const list = problemsFor(detail, (f) => (cellOf(nb, f, detail, running) === c ? { line: f.line, colShift: 0 } : null));
        if (list.length) c.editor?.setProblems(list);
      }
    },
    fix: (fix) => {
      if (fix.kind === "replace") {
        const target = where();
        const entry = shown?.chain[shown.chain.length - 1];
        const near = hasSource(running.kind) ? (entry?.sql?.line ?? 1) : (yourFrame(entry)?.line ?? entry?.syntax?.line ?? 1);
        if (!target.editor?.applyFix(fix, near)) errorHere(`${fix.target ?? "That"} is no longer in the cell.`);
        else {
          select(nb, target);
          target.editor.focus(); // back in the code, ready to run it again
        }
        return;
      }
      if (fix.kind === "import") {
        const first = nb.cells.find((c) => c.kind === "code") ?? running;
        first.editor?.applyFix(fix, 1);
        select(nb, first);
        first.editor?.focus();
        toast(`Added to cell ${indexOf(nb, first) + 1}`);
        return;
      }
      if (fix.kind === "cell" && fix.text) {
        // A cell that does what the failing one could not (reading a Dataverse table instead of SQL).
        const made = insertAt(nb, indexOf(nb, running) + 1, "code", fix.text);
        select(nb, made);
        made.editor?.focus();
        return;
      }
      if (fix.kind === "define" && fix.name) {
        const maker = definingCell(nb, fix.name, running);
        if (maker) {
          void run(nb, maker).then((ok) => ok && toast(`Ran cell ${indexOf(nb, maker) + 1}`));
        } else errorHere(`No cell above defines ${fix.name}`);
        return;
      }
      // Installed, the cell runs again (the missing-package prompt's retry).
      const again = fix.kind === "install" ? { again: () => void run(nb, running) } : {};
      if (!nb.hooks.fix?.({ ...fix, ...again })) errorHere("Fix not available here");
    },
    goTo: (frame) => {
      const target = shown ? cellOf(nb, frame, shown, running) : null;
      if (!target) return false;
      select(nb, target);
      target.element.scrollIntoView({ block: "nearest" });
      target.editor?.reveal(frame.line, frame.col ?? 1);
      return true;
    },
    openGrid: nb.hooks.openGrid,
  };
}

export function hooksOf(nb: Notebook, cell: Cell): ErrorHooks {
  let found = nb.kept.get(cell);
  if (!found) nb.kept.set(cell, (found = errorHooks(nb, cell)));
  return found;
}

/** The cell above `before` that makes `name` (assigns, defines or imports it), nearest first. */
export function definingCell(nb: Notebook, name: string, before: Cell): Cell | null {
  const above = nb.cells.slice(0, Math.max(0, indexOf(nb, before)));
  for (const c of [...above].reverse()) {
    if (c.kind === "code" && makesName(name, c.editor?.value() ?? c.source)) return c;
  }
  return null;
}
