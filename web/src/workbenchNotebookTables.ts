/**
 * workbenchNotebookTables.ts: a notebook's Tables group: every open table's read-only cell, arranged by the
 * server's rules (POST /workbench/tables/arrange; domain/table_cells.py), drawn and folded here; each
 * table's line and state, the uses line the app keeps on a user's cell, a table's cell run (by itself once,
 * when the app wrote it whole), and going to a cell by its number. A part of workbenchNotebook.ts's
 * notebookView (workbenchNotebookState.ts says how the parts fit). [VIEW]
 */
import { api } from "./api";
import { button, clear, h } from "./dom";
import { errorHere } from "./errorNote";
import { cellRoute } from "./modes";
import { isApp, isHeading } from "./notebookCells";
import { runInto } from "./workbenchKernel";
import { byNumber, type Cell, edited, infoOf, lineOf, type Notebook, relabel, select, sourceOf, stateOf, tableCell, type TableReport, timeRun, usesForm } from "./workbenchNotebookState";
import { type ArrangedCell, firstLine, groupLineText, noteParts, type TableInfo, type TableLine, tableLineText, withUses } from "./workbenchTables";

/** A table's read-only cell: run so that running it again changes nothing (it starts from the table
 *  as its maker made it: client/table_cells.py). */
export async function runTransformations(nb: Notebook, cell: Cell, quietly = false): Promise<boolean> {
  const code = sourceOf(cell);
  const table = cell.table ?? "";
  const variable = infoOf(nb, table)?.variable ?? table.replace(/\W/g, "_");
  cell.area.set([]);
  cell.count.textContent = "[*]";
  cell.element.classList.add("running");
  const ended = timeRun(cell);
  try {
    const done = await runInto(nb.kernel, { code, kind: "table", table: variable }, cell.area);
    cell.execution_count = done.execution_count;
    cell.count.textContent = done.error ? "[!]" : done.execution_count ? `[${done.execution_count}]` : "[ ]";
    cell.element.classList.toggle("failed", !done.ok);
    if (done.ok) nb.records.set(table, { code, at: new Date(), opened: false });
    // Run by itself on opening: the document is as it was (no unsaved mark for it).
    if (!quietly) edited(nb);
    redraw(nb);
    return done.ok;
  } finally {
    ended();
    cell.element.classList.remove("running");
  }
}

// ===== the Tables group: arranged by the server's rules, drawn and folded here =====

export function goTo(nb: Notebook, number: number, line?: number | null): boolean {
  const cell = byNumber(nb, number);
  if (!cell) {
    errorHere(`There is no cell ${number} in this notebook.`);
    return false;
  }
  // Open what hides it.
  if (cell.grouped && cell.role !== "tables") nb.groupFolded = false;
  if (cell.grouped && cell.table && (cell.role === "maker" || cell.role === "transformations")) nb.unfolded.add(cell.table);
  redraw(nb);
  select(nb, cell);
  cell.element.scrollIntoView({ block: "center" });
  cell.element.focus();
  cell.element.classList.add("wb-arrived");
  setTimeout(() => cell.element.classList.remove("wb-arrived"), 1200);
  if (line && cell.editor) {
    cell.editor.focus();
    cell.editor.moveTo(line);
  }
  return true;
}

export function toggleFold(nb: Notebook, cell: Cell): void {
  if (cell.role === "tables") nb.groupFolded = !nb.groupFolded;
  else if (cell.table) {
    if (nb.unfolded.has(cell.table)) nb.unfolded.delete(cell.table);
    else nb.unfolded.add(cell.table);
  }
  redraw(nb);
}

/** A note with its cell links as buttons: "orders is made at [@cell7] (it needs make_dates)". */
export const noteElement = (nb: Notebook, note: string): HTMLElement =>
  h(
    "span",
    { class: "wb-table-note" },
    ...noteParts(note).map((part) =>
      typeof part === "string" ? part : h("button", { type: "button", class: "link wb-cell-link", title: firstLine(byNumber(nb, part.cell) ? sourceOf(byNumber(nb, part.cell)!) : "") || `Cell ${part.cell}`, onclick: (e: Event) => { e.stopPropagation(); goTo(nb, part.cell); } }, `@cell${part.cell}`),
    ),
  );

/** Draw the folded lines, each table cell's state, and what is folded away. */
export function redraw(nb: Notebook): void {
  const tables = nb.cells.filter((c) => c.role === "transformations");
  const states = new Map(tables.map((c) => [c.table, stateOf(nb, c)]));
  for (const cell of nb.cells) {
    const inTable = cell.grouped && !!cell.table && (cell.role === "maker" || cell.role === "transformations");
    cell.element.hidden = (cell.grouped && cell.role !== "tables" && nb.groupFolded) || (inTable && !nb.unfolded.has(cell.table!));
    cell.element.classList.toggle("in-tables", cell.grouped && !isHeading(cell.role));
    cell.element.classList.toggle("role-maker", cell.role === "maker");
    cell.element.classList.toggle("role-imports", cell.role === "imports");
    cell.part.textContent = cell.role === "maker" && cell.table ? `makes ${cell.table}` : cell.role === "imports" ? "imports the tables need" : cell.role === "transformations" ? `${cell.table} · transformations · read-only: it follows the grid` : "";
    if (cell.role === "tables" && cell.bar) {
      const line = groupLineText([...states.values()]);
      cell.element.classList.toggle("stale", line.stale);
      clear(cell.bar, h("button", { type: "button", class: "wb-fold", "aria-expanded": String(!nb.groupFolded), onclick: () => toggleFold(nb, cell) }, h("span", { class: "wb-chevron", "aria-hidden": "true" }, nb.groupFolded ? "▸" : "▾"), line.text));
    } else if (cell.role === "table" && cell.bar) {
      const line = lineOf(nb, cell.table);
      const state = states.get(cell.table);
      const own = tables.find((c) => c.table === cell.table);
      const foldable = !!own?.grouped;
      const open = nb.unfolded.has(cell.table ?? "");
      const words = line && state ? tableLineText(line, state) : (cell.table ?? "");
      const note = line?.note ?? cell.source.split("\n").slice(1).join(" ").trim();
      cell.element.classList.toggle("stale", state?.kind === "outOfDate");
      clear(
        cell.bar,
        foldable
          ? h("button", { type: "button", class: "wb-fold", "aria-expanded": String(open), onclick: () => toggleFold(nb, cell) }, h("span", { class: "wb-chevron", "aria-hidden": "true" }, open ? "▾" : "▸"), words)
          : h("span", { class: "wb-fold still" }, words),
        note ? noteElement(nb, note) : null,
        h("span", { class: "spacer" }),
        own && state?.runnable ? button("Run", () => void nb.act.run(own), { icon: "play", class: "ghost wb-run-table", title: `Run ${cell.table}'s cell` }) : null,
      );
    } else if (cell.role === "transformations" && cell.status) {
      const state = states.get(cell.table)!;
      cell.status.textContent = state.label;
      cell.status.hidden = !state.label; // a cell that is current says nothing
      cell.status.className = `wb-table-state ${state.kind}`;
      cell.element.classList.toggle("stale", state.kind === "outOfDate");
      cell.element.classList.toggle("closed", !infoOf(nb, cell.table));
    }
  }
  relabel(nb);
  nb.hooks.tablesChanged?.();
}

/** A cell's uses line as it should be. The cursor stays on its text, and that text stays where it is
 *  on screen when the line above it comes or goes. */
export function applyUses(nb: Notebook, cell: Cell, line: string | null): void {
  const current = sourceOf(cell);
  const next = withUses(current, line, usesForm(cell.kind));
  if (next === current) return;
  if (!cell.editor) {
    cell.source = next;
    edited(nb);
    return;
  }
  const typing = cell.element.contains(document.activeElement);
  const before = cell.element.getBoundingClientRect().height;
  cell.editor.replaceText(next);
  cell.editor.layout();
  if (typing) {
    const grew = cell.element.getBoundingClientRect().height - before;
    let scroller: HTMLElement | null = nb.list.parentElement;
    while (scroller && scroller.scrollHeight <= scroller.clientHeight) scroller = scroller.parentElement;
    if (scroller && grew) scroller.scrollTop += grew;
  }
}

export function apply(nb: Notebook, done: { cells: ArrangedCell[]; tables: TableLine[]; next_cell: number }, move: boolean): void {
  nb.nextNumber = Math.max(nb.nextNumber, done.next_cell);
  nb.tableLines = done.tables;
  if (move) {
    const left = new Map(nb.cells.map((c) => [c.number, c]));
    const wanted: Cell[] = [];
    const hadGroup = nb.cells.some((c) => c.role === "tables");
    const movedIn: string[] = [];
    for (const a of done.cells) {
      let cell = left.get(a.number);
      // The app's cells are made and unmade as a whole (a heading is never turned into code).
      if (cell && isApp(cell.role) !== isApp(a.role)) cell = undefined;
      if (!cell) cell = nb.act.make({ kind: a.kind, source: a.source, connection: null, outputs: [], execution_count: null, number: a.number, role: a.role, table: a.table, grouped: a.grouped, steps: a.steps ?? null }, nb.cells.length);
      else left.delete(a.number);
      if (a.role === "maker" && a.grouped && !(cell.role === "maker" && cell.grouped) && a.table) movedIn.push(a.table);
      cell.role = a.role;
      cell.table = a.table;
      cell.grouped = a.grouped;
      wanted.push(cell);
    }
    for (const gone of left.values()) {
      if (isApp(gone.role)) {
        gone.editor?.dispose();
        gone.element.remove();
        if (nb.selected === gone) nb.selected = null;
      } else wanted.push(gone); // never lose a cell of the user's
    }
    const focused = wanted.find((c) => c.editor?.hasFocus());
    const moved = wanted.length !== nb.cells.length || wanted.some((c, i) => nb.cells[i] !== c);
    nb.cells.splice(0, nb.cells.length, ...wanted);
    wanted.forEach((c, i) => {
      if (nb.list.children[i] !== c.element) nb.list.insertBefore(c.element, nb.list.children[i] ?? null);
    });
    focused?.editor?.focus();
    if (moved) edited(nb);
    // A group made while working shows its tables.
    if (!hadGroup && !nb.building && nb.cells.some((c) => c.role === "tables")) nb.groupFolded = false;
    // A cell the user was just working in is not folded away under them: its table shows open.
    if (movedIn.length && !nb.building) for (const name of movedIn) nb.unfolded.add(name);
  }
  for (const a of done.cells) {
    // A table seen for the first time opens unfolded (its cell, then its output).
    if (a.role === "transformations" && a.table && !nb.seenTables.has(a.table)) {
      nb.seenTables.add(a.table);
      nb.unfolded.add(a.table);
    }
    const cell = byNumber(nb, a.number);
    if (!cell) continue;
    if (isHeading(a.role)) {
      if (cell.source !== a.source) {
        cell.source = a.source;
        edited(nb);
      }
    } else if (a.role === "transformations") {
      if (a.steps) cell.steps = a.steps;
      if (sourceOf(cell) !== a.source) {
        if (cell.editor) cell.editor.replaceText(a.source);
        cell.source = a.source;
        edited(nb);
      }
    } else if (cell.kind !== "markdown") applyUses(nb, cell, a.uses);
  }
  redraw(nb);
  void runOwnTables(nb);
}

/** The tables' cells the app wrote whole (no cell of the user's makes the table: its load and its
 *  transformations, both the app's) run by themselves, once each, so the cell shows its table. A
 *  table a cell of the user's makes waits for the user's Run (their code never runs by itself). */
export async function runOwnTables(nb: Notebook): Promise<void> {
  for (const cell of nb.cells.filter((c) => c.role === "transformations" && c.table)) {
    const table = cell.table!;
    if (nb.disposed || nb.autoRan.has(table) || !infoOf(nb, table)) continue;
    const line = lineOf(nb, table);
    const state = stateOf(nb, cell);
    if (!line || line.maker !== null || (state.kind !== "notRun" && state.kind !== "notRunSinceOpening")) continue;
    nb.autoRan.add(table);
    if (cell.editor) cell.source = cell.editor.value();
    await runTransformations(nb, cell, true);
  }
}

/** Ask the server for the notebook as it should be. `move` false while the user types: nothing is
 *  added or moved, only the tables' cells and the uses lines follow. */
export async function arrange(nb: Notebook, move: boolean): Promise<void> {
  const relevant = nb.tableInfos.length > 0 || nb.cells.some((c) => c.role !== "") || nb.cells.some((c) => c.kind !== "markdown" && withUses(sourceOf(c), null, usesForm(c.kind)) !== sourceOf(c));
  // A mode whose SQL runs in its own kernel (a code app's data notebook): the open tables are that kernel's
  // views already, so the Python kernel's Tables group is not made here.
  if (!relevant || cellRoute("sql")) return;
  const mine = ++nb.asked;
  const at = nb.version;
  const body = {
    kind: "notebook",
    cells: nb.cells.map((c) => ({ kind: c.kind, source: sourceOf(c), number: c.number, role: c.role, table: c.table, grouped: c.grouped })),
    tables: nb.tableInfos.map((t) => t.name),
    next_cell: nb.nextNumber,
    move,
  };
  try {
    const done = await api<{ cells: ArrangedCell[]; tables: TableLine[]; next_cell: number }>("/workbench/tables/arrange", "POST", body);
    if (mine !== nb.asked) return; // a newer question is on its way
    if (at !== nb.version) return void (move ? arrange(nb, true) : typedSoon(nb)); // the text changed meanwhile: ask again
    apply(nb, done, move);
  } catch {
    /* the server is away: the cells stay as they are */
  }
}

export function typedSoon(nb: Notebook): void {
  if (nb.quiet !== null) window.clearTimeout(nb.quiet);
  nb.quiet = window.setTimeout(() => {
    nb.quiet = null;
    void arrange(nb, false);
  }, 600);
}

// ===== what the page and the agent ask about the tables =====

/** The open tables that belong to this notebook: their cells follow, the Tables group is arranged. */
export function setTables(nb: Notebook, tables: TableInfo[]): void {
  nb.tableInfos = tables;
  // A table opened again whose cell came with the file: the grid gets its steps back first, and
  // the cell follows the grid from then on.
  for (const info of tables) {
    const cell = tableCell(nb, info.name);
    if (info.grid && !info.step_list.length && cell?.steps?.length && nb.cameWithFile.has(info.name) && !nb.restored.has(info.name)) {
      nb.restored.add(info.name);
      nb.hooks.restoreSteps?.(info.grid, cell.steps);
      return; // the grid's change brings the tables back here
    }
    nb.restored.add(info.name);
  }
  void arrange(nb, true);
}

/** Its tables and each cell's state. */
export function tableReports(nb: Notebook): TableReport[] {
  return nb.cells
    .filter((c) => c.role === "transformations" && c.table)
    .map((c) => {
      const state = stateOf(nb, c);
      const line = lineOf(nb, c.table);
      return { name: c.table!, cell: c.number, maker: line?.maker ?? null, moved: c.grouped, note: line?.note ?? null, steps: line?.steps ?? null, open: !!infoOf(nb, c.table), code: sourceOf(c), state: state.kind, label: state.label };
    });
}

/** Run every table's cell that is not up to date; how many ran. */
export async function runOutOfDate(nb: Notebook): Promise<number> {
  let ran = 0;
  for (const cell of nb.cells.filter((c) => c.role === "transformations")) {
    if (!stateOf(nb, cell).runnable) continue;
    ran++;
    if (!(await nb.act.run(cell))) break;
  }
  return ran;
}

/** Fold or unfold the Tables group (or one table of it). */
export function foldTables(nb: Notebook, folded: boolean, table?: string): void {
  if (table) {
    if (folded) nb.unfolded.delete(table);
    else {
      nb.unfolded.add(table);
      nb.groupFolded = false;
    }
  } else nb.groupFolded = folded;
  redraw(nb);
}

/** A table was renamed in the grid. */
export function renameTable(nb: Notebook, from: string, to: string): void {
  for (const c of nb.cells) if (c.table === from) c.table = to;
  const record = nb.records.get(from);
  if (record) nb.records.set(to, record);
  nb.records.delete(from);
}

/** A kernel that starts (again) or stops holds no table any more: no cell has run in it. */
export function forgetRuns(nb: Notebook): void {
  let any = false;
  for (const [name, record] of nb.records) {
    if (record.code === null) continue;
    nb.records.set(name, { code: null, at: null, opened: record.opened });
    any = true;
  }
  if (any) redraw(nb);
}
