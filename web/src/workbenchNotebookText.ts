/**
 * workbenchNotebookText.ts: a notebook's cells that show something drawn in place of their code: a
 * Markdown cell as text (its ```mermaid blocks as diagrams, its `{{ name }}` filled from its last run), an
 * HTML cell's design (workbenchHtml.ts), each one's state line, its run, and the design pane a cell gets.
 * A part of workbenchNotebook.ts's notebookView (workbenchNotebookState.ts says how the parts fit). [VIEW]
 */
import { h } from "./dom";
import { errorNote } from "./errorNote";
import { loadDiagrams } from "./lazyLoad";
import { renderMarkdown } from "./markdown";
import { drawn } from "./notebookCells";
import { changedNames, type DesignPane, designPane, fillHtml, fillMarkdown, htmlNames, type HtmlState, htmlState, runHtml } from "./workbenchHtml";
import { type Cell, type CellKind, edited, focusEditor, type HtmlReport, indexOf, type Notebook, sourceOf } from "./workbenchNotebookState";
import { withUses } from "./workbenchTables";

/** A Markdown cell as text. With `{{ name }}` (docs/ideas.md, text cells on the canvas, 2026-11-15)
 *  its names are filled from its last run's values by the server's rules (a value is always text),
 *  and the line above says when it is out of date, as an HTML cell's design does. */
export function showMarkdown(nb: Notebook, cell: Cell): void {
  const text = cell.editor?.value() ?? cell.source;
  cell.element.classList.add("rendered");
  if (!htmlNames(text).length) {
    cell.htmlNotes = [];
    cell.view.replaceChildren(renderMarkdown(text));
    drawDiagrams(nb, cell);
    return;
  }
  void drawMarkdown(nb, cell, text);
}

/** A Markdown cell's ```mermaid blocks drawn as diagrams (the owner, 2026-11-15), by the app's own
 *  Mermaid (loaded when first needed, strict, its drawing cleaned: nothing from the internet). A
 *  broken diagram says why in its place. */
export function drawDiagrams(nb: Notebook, cell: Cell): void {
  for (const block of cell.view.querySelectorAll<HTMLElement>("pre.md-code[data-lang='mermaid']")) {
    const text = block.textContent ?? "";
    const host = h("div", { class: "md-mermaid", role: "img", "aria-label": "Diagram" });
    block.replaceWith(host);
    void loadDiagrams()
      .then((m) => m.drawDiagram(host, text, nb.dark()))
      .catch((e: unknown) => host.replaceChildren(errorNote(e, { dismiss: false })));
  }
}

export async function drawMarkdown(nb: Notebook, cell: Cell, text: string): Promise<void> {
  const mine = ++cell.drawn;
  let filled: { markdown: string; missing: string[]; notes: string[] };
  try {
    filled = await fillMarkdown(text, cell.htmlRun?.values ?? {});
  } catch {
    filled = { markdown: text, missing: [], notes: ["The server is away: the names show as written."] };
  }
  if (mine !== cell.drawn || cell.kind !== "markdown" || !cell.element.classList.contains("rendered")) return;
  cell.htmlNotes = [...filled.missing.map((n) => `{{ ${n} }} was not found in the kernel.`), ...filled.notes];
  const notes = cell.htmlNotes.length ? h("div", { class: "wb-design-notes hint" }, ...cell.htmlNotes.map((n) => h("div", {}, n))) : null;
  cell.view.replaceChildren(cell.textBar.element, renderMarkdown(filled.markdown), ...(notes ? [notes] : []));
  drawDiagrams(nb, cell);
  drawMarkdownState(cell);
}

/** A Markdown cell's state line: only what needs the user (out of date, not run), with Run. */
export function drawMarkdownState(cell: Cell): void {
  const state = htmlState(sourceOf(cell), cell.htmlRun);
  cell.textBar.element.hidden = !state.label;
  cell.textBar.status.textContent = state.label;
  cell.textBar.status.className = `wb-design-state ${state.kind}`;
  cell.textBar.run.hidden = !state.runnable;
  cell.element.classList.toggle("stale", state.kind === "outOfDate");
}

export function editMarkdown(cell: Cell): void {
  cell.element.classList.remove("rendered");
  cell.view.replaceChildren();
  setTimeout(() => cell.editor?.focus(), 0);
}

// ===== HTML cells: the design, its state, its run =====

/** An HTML cell's HTML without the app's own first line (so that line never makes it out of date). */
export const htmlOf = (cell: Cell): string => withUses(sourceOf(cell), null, "html");
export const htmlStateOf = (cell: Cell): HtmlState => htmlState(htmlOf(cell), cell.htmlRun);

export function drawHtmlState(cell: Cell): void {
  if (cell.kind === "markdown") return drawMarkdownState(cell);
  if (!cell.design) return;
  const state = htmlStateOf(cell);
  cell.design.setState(state, cell.htmlNotes);
  cell.element.classList.toggle("stale", cell.kind === "html" && state.kind === "outOfDate");
}

/** Draw the design from the cell's HTML as it is now, its names filled with what its last run gave. */
export async function drawDesign(cell: Cell): Promise<void> {
  if (!cell.design) return;
  const html = sourceOf(cell);
  const mine = ++cell.drawn;
  let filled: { html: string; missing: string[]; notes: string[] };
  try {
    filled = await fillHtml(html, cell.htmlRun?.values ?? {});
  } catch {
    filled = { html, missing: [], notes: ["The server is away: the design shows as written."] }; // names unfilled
  }
  if (mine !== cell.drawn || cell.kind !== "html") return;
  cell.htmlNotes = [...filled.missing.map((n) => `{{ ${n} }} was not found in the kernel.`), ...filled.notes];
  cell.design.show(filled.html);
  drawHtmlState(cell);
}

export function showDesign(cell: Cell): void {
  cell.element.classList.add("rendered");
  void drawDesign(cell);
}

export function editHtml(cell: Cell): void {
  cell.element.classList.remove("rendered");
  // At once, so what is typed next goes into the HTML; again once the editor has its size.
  cell.editor?.layout();
  if (cell.editor) cell.editor.focus();
  else focusEditor(cell);
  setTimeout(() => cell.editor?.layout(), 0);
}

/** Run an HTML cell: plain HTML only draws; with names, each is read from the kernel's variables. A
 *  Markdown cell with names runs the same way (its values are an HTML cell's), and shows as text. */
export async function runHtmlCell(nb: Notebook, cell: Cell): Promise<boolean> {
  const html = cell.source;
  const face = (c: Cell): void => (c.kind === "markdown" ? showMarkdown(nb, c) : showDesign(c));
  cell.area.set([]);
  if (!html.trim()) return true;
  if (!htmlNames(html).length) {
    face(cell);
    return true;
  }
  cell.count.textContent = "[*]";
  cell.element.classList.add("running");
  try {
    const done = await runHtml(nb.kernel, html, (item) => {
      if (!item.input_request) cell.area.add(item);
    });
    cell.area.finish();
    cell.execution_count = done.execution_count;
    cell.count.textContent = !done.ok ? "[!]" : done.execution_count ? `[${done.execution_count}]` : "[ ]";
    cell.element.classList.toggle("failed", !done.ok);
    if (done.run) cell.htmlRun = { ...done.run, code: withUses(html, null, "html") };
    edited(nb);
    face(cell);
    return done.ok;
  } catch (e) {
    cell.area.finish();
    cell.area.notice((e as Error).message, "error");
    cell.count.textContent = "[!]";
    return false;
  } finally {
    cell.element.classList.remove("running");
  }
}

export function htmlReport(nb: Notebook, cell: Cell): HtmlReport {
  const state = htmlStateOf(cell);
  return { number: cell.number, index: indexOf(nb, cell), html: sourceOf(cell), names: htmlNames(sourceOf(cell)), state: state.kind, label: state.label, height: cell.design?.height() ?? null, notes: cell.htmlNotes };
}


/** After a run: which HTML cells name a variable that would now draw something else. */
export async function checkMarks(nb: Notebook): Promise<void> {
  const ran = nb.cells.filter((c) => (c.kind === "html" || c.kind === "markdown") && c.htmlRun && c.htmlRun.code !== null);
  if (!ran.length) return;
  const changed = await changedNames(nb.kernel, ran.map((c) => c.htmlRun!));
  if (!changed) return;
  for (const cell of ran) {
    const run = cell.htmlRun;
    const now = run ? changed.get(run) : undefined;
    if (!run || !now || now.join("\n") === run.changed.join("\n")) continue;
    run.changed = now;
    drawHtmlState(cell);
  }
}

// ===== a cell's design pane (an HTML cell's drawing, a TSX cell's preview) =====

export function pane(nb: Notebook, kind: CellKind, height: number | null, cell: () => Cell): { design: DesignPane } {
  const design = designPane({
    dark: nb.dark,
    height: drawn(kind) || kind === "code" || kind === "tsx" ? height : null,
    resized: () => edited(nb),
    run: () => void nb.act.run(cell()),
  });
  return { design };
}


/** A kernel that starts (again) or stops: an HTML cell's names were that kernel's variables, so it has not
 *  run in the new one. */
export function forgetHtmlRuns(nb: Notebook): void {
  for (const cell of nb.cells) {
    if ((cell.kind !== "html" && cell.kind !== "markdown") || !cell.htmlRun || cell.htmlRun.code === null) continue;
    cell.htmlRun = { ...cell.htmlRun, code: null, at: null, changed: [] };
    drawHtmlState(cell);
  }
}

/** A run ended: a variable an HTML cell names may have changed (looked at once things are calm). */
export function marksSoon(nb: Notebook): void {
  if (nb.marksTimer !== null) window.clearTimeout(nb.marksTimer);
  nb.marksTimer = window.setTimeout(() => {
    nb.marksTimer = null;
    void checkMarks(nb);
  }, 300);
}
