/**
 * workbenchNotebookRuns.ts: running a notebook's cells: one cell by its kind (Python, SQL and DAX in the
 * document's kernel; a Markdown or HTML cell's names; a table's read-only cell; a TypeScript, TSX or DuckDB
 * SQL cell on the route the open project's mode names: routedCells.ts), several in order, up to a cell.
 * A part of workbenchNotebook.ts's notebookView (workbenchNotebookState.ts says how the parts fit). [VIEW]
 */
import { loadEditors } from "./lazyLoad";
import { busy } from "./loading";
import { type CellRoute, cellRoute } from "./modes";
import { hasSource, isHeading } from "./notebookCells";
import { previewRouted, routedTypes, runRouted } from "./routedCells";
import { htmlNames } from "./workbenchHtml";
import { runInto } from "./workbenchKernel";
import { type Cell, type CellKind, edited, indexOf, KIND_NAMES, type Notebook, ROUTED, routeOf, select, timeRun } from "./workbenchNotebookState";
import { arrange, runTransformations } from "./workbenchNotebookTables";
import { runHtmlCell, showMarkdown } from "./workbenchNotebookText";

export async function run(nb: Notebook, cell: Cell): Promise<boolean> {
  if (cell.editor) cell.source = cell.editor.value();
  for (const c of nb.cells) c.editor?.setProblems([]); // the last failure's marks describe code that ran before
  if (isHeading(cell.role)) return true;
  if (cell.kind === "markdown") {
    if (htmlNames(cell.source).length) return runHtmlCell(nb, cell); // its names, from the kernel
    showMarkdown(nb, cell);
    return true;
  }
  if (cell.role === "transformations") return runTransformations(nb, cell);
  if (cell.kind === "html") return runHtmlCell(nb, cell);
  if (cell.kind === "tsx") return runPreview(nb, cell);
  const route = routeOf(cell);
  if (route) return runOnRoute(nb, cell, route);
  if (ROUTED.includes(cell.kind)) {
    cell.area.set([]);
    cell.area.notice(`${KIND_NAMES[cell.kind]} cells run in a project whose mode has them (a code app's data notebook).`, "error");
    return false;
  }
  if (!cell.source.trim()) return true;
  cell.area.set([]);
  cell.element.classList.remove("output-hidden");
  cell.count.textContent = "[*]";
  cell.element.classList.add("running");
  // The first run starts Python (seconds): the cell is gated with words until it is up (8.12).
  if (nb.kernel.state === "off" || nb.kernel.state === "starting") {
    try {
      await busy(cell.element, "Starting Python…", nb.kernel.ensure(), { errorIn: false });
    } catch (e) {
      cell.element.classList.remove("running");
      cell.count.textContent = "[!]";
      cell.area.notice((e as Error).message, "error");
      return false;
    }
  }
  const ended = timeRun(cell);
  try {
    const ranCode = cell.source;
    const done = await runInto(nb.kernel, { code: cell.source, kind: hasSource(cell.kind) ? cell.kind : "code", connection: cell.connection }, cell.area);
    cell.ranSource = ranCode;
    cell.runOrder = ++nb.runs;
    nb.hooks.ran?.();
    cell.execution_count = done.execution_count;
    cell.count.textContent = done.error ? "[!]" : done.execution_count ? `[${done.execution_count}]` : "[ ]";
    cell.element.classList.toggle("failed", !done.ok);
    edited(nb);
    // A calm moment: a cell that now makes a table joins the Tables group.
    if (done.ok && cell.kind === "code" && (nb.tableInfos.length || nb.cells.some((c) => c.role))) void arrange(nb, true);
    return done.ok;
  } finally {
    ended();
    cell.element.classList.remove("running");
  }
}

// ===== cells another kernel runs (the mode's routes: routedCells.ts) =====

/** A TypeScript cell, or a DuckDB SQL cell where the mode runs SQL in its kernel: run on the route. */
export async function runOnRoute(nb: Notebook, cell: Cell, route: CellRoute): Promise<boolean> {
  if (!cell.source.trim()) return true;
  cell.area.set([]);
  cell.element.classList.remove("output-hidden");
  cell.count.textContent = "[*]";
  cell.element.classList.add("running");
  const ended = timeRun(cell);
  try {
    const ranCode = cell.source;
    const body = { path: nb.kernel.intel().path, kind: cell.kind === "sql" ? "sql" : "typescript", code: cell.source, cell: cell.number };
    let done;
    try {
      done = await runRouted(route, body, (o) => cell.area.add(o), () => void run(nb, cell));
    } catch (e) {
      cell.area.notice((e as Error).message, "error");
      done = { ok: false, execution_count: null, error: (e as Error).message };
    }
    cell.area.finish();
    cell.ranSource = ranCode;
    cell.runOrder = ++nb.runs;
    nb.hooks.ran?.();
    cell.execution_count = done.execution_count;
    cell.count.textContent = !done.ok ? "[!]" : done.execution_count ? `[${done.execution_count}]` : "[ ]";
    cell.element.classList.toggle("failed", !done.ok);
    edited(nb);
    return done.ok;
  } finally {
    ended();
    cell.element.classList.remove("running");
  }
}

/** A TSX cell: drawn with the project's own React in the HTML cells' frame, under its code. */
export async function runPreview(nb: Notebook, cell: Cell): Promise<boolean> {
  const route = cellRoute("tsx");
  cell.area.set([]);
  if (!route?.preview) {
    cell.area.notice("TSX cells are drawn in a project whose mode has them (a code app's data notebook).", "error");
    return false;
  }
  if (!cell.source.trim()) return true;
  cell.count.textContent = "[*]";
  cell.element.classList.add("running");
  try {
    const html = await previewRouted(route, { path: nb.kernel.intel().path, source: cell.source, cell: cell.number }, () => void run(nb, cell));
    if (html === null) return false;
    cell.design?.show(html);
    cell.element.classList.add("previewed");
    cell.element.classList.remove("failed");
    cell.count.textContent = "[ ]";
    cell.ranSource = cell.source;
    cell.runOrder = ++nb.runs;
    return true;
  } catch (e) {
    cell.element.classList.remove("previewed");
    cell.element.classList.add("failed");
    cell.count.textContent = "[!]";
    cell.area.notice((e as Error).message, "error");
    return false;
  } finally {
    cell.element.classList.remove("running");
  }
}

/** The route's declarations known to the editor's TypeScript service (once). */
export function knowTypes(kind: CellKind): void {
  const route = cellRoute(kind);
  if (!route) return;
  void Promise.all([routedTypes(route), loadEditors()]).then(([text, m]) => {
    if (text) m.typescriptNotebook(text);
  });
}

/** Run cells in order, stopping at the first that fails (or a stopped kernel), as Jupyter does. */
/** Run up to here: the user's cells from the top to this one, in order (a table's cell too). */
export async function runUpTo(nb: Notebook, cell: Cell): Promise<void> {
  select(nb, cell);
  await runEach(nb, nb.cells.slice(0, indexOf(nb, cell) + 1).filter((c) => !isHeading(c.role)));
}

export async function runEach(nb: Notebook, some: Cell[]): Promise<void> {
  for (const cell of some) if (!(await run(nb, cell))) return;
}
