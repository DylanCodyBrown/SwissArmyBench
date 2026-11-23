/**
 * workbenchNotebookMode.ts: Notebook mode (2026-11-15) in a notebook: the user's cells as the run order
 * reads them, each cell's "edited" or "out of date" mark in its head (domain/notebook_flow.py works them
 * out), and Present: the notebook as a document (its text and outputs, no code). A part of
 * workbenchNotebook.ts's notebookView (workbenchNotebookState.ts says how the parts fit). [VIEW]
 */
import { flowWords, isApp, isHeading } from "./notebookCells";
import { type FlowCell, type Notebook, sourceOf } from "./workbenchNotebookState";
import { showMarkdown } from "./workbenchNotebookText";

/** The user's cells as the run order reads them: what each last ran, and when. */
export function flowCells(nb: Notebook): FlowCell[] {
  return nb.cells
    .filter((c) => !isApp(c.role) && !isHeading(c.role))
    .map((c) => ({ number: c.number, kind: c.kind, source: sourceOf(c), ran: c.ranSource, order: c.runOrder, name: c.name }));
}

/** Each cell's state from the run order: "edited", "outOfDate" (with the names), else nothing shown. */
export function markFlow(nb: Notebook, states: { number: number; state: string; because: string[] }[]): void {
  const by = new Map(states.map((s) => [s.number, s]));
  for (const c of nb.cells) {
    const said = flowWords(by.get(c.number));
    c.flow.textContent = said.words;
    c.flow.title = said.title;
    c.flow.hidden = !said.words;
    c.element.classList.toggle("flow-stale", !!said.words);
  }
}

/** Present: the notebook as a document (its text and outputs, no code). Whether it is on now. */
export function present(nb: Notebook, on?: boolean): boolean {
  nb.presenting = on ?? !nb.presenting;
  nb.list.classList.toggle("presenting", nb.presenting);
  if (nb.presenting) for (const c of nb.cells) if (c.kind === "markdown" && !c.element.classList.contains("rendered")) showMarkdown(nb, c);
  // A code cell shows only what it drew: one that drew nothing is left out of the document.
  for (const c of nb.cells) {
    const drew = !!c.area.element.textContent?.trim() || !!c.area.element.querySelector("img, svg, iframe, canvas, table");
    c.element.classList.toggle("present-empty", nb.presenting && c.kind !== "markdown" && c.kind !== "html" && !drew);
  }
  return nb.presenting;
}
