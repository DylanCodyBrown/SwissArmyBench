/**
 * excelCanvas.ts: the Excel canvas (the Accounting extension's front-end plug-in; Plans/editions.plan.md):
 * a workbook's design (workbook.design.json) as a Workbench document, shown only when the extension is
 * on and the open project's mode offers it. Its machinery is the Streamlit canvas's, shared through
 * canvasKit.ts (Undo and Redo, the tabs, the resize grip), never a fork. [EXCEL]
 *
 *   [SHEETS]  the workbook's sheets as tabs: add, rename (double-click or F2), remove
 *   [BLOCKS]  blocks on a grid of cells: a title, text, a table (bound to an open table or a DuckDB
 *             query; headers, number formats, widths, a total row, colour rules), a pivot (a summary
 *             DuckDB computes: rows, columns, values; written as a formatted table, never a real Excel
 *             pivot), a chart (Excel's own: bar, column, line, pie, combo, its series from a table or a
 *             pivot block). Drag a block to move it (or the arrow keys), drag its corner to size it,
 *             Delete takes it off. A click selects it: Properties edits it; the sheet's own (freeze
 *             panes, print setup) when none is selected
 *   [PLAY]    Play builds the workbook from the open tables (each through its grid's steps) and shows each
 *             sheet as built; Download gives the .xlsx. "Out of date" once the design changed
 *   [EXPORT]  Export workbook.py: the automation that builds the same workbook from data.py, anywhere
 *   [MORE]    Templates… (excelTemplates.ts: import an existing workbook, bind its places) and
 *             Statements… (build statements and invoices: dry run first, the register)
 *
 * The server holds the design (the extension's service.py): every action is a route, so the agent's
 * workbook_* commands do the same and a change made anywhere shows here at once (workbook_changed).
 *
 * ROUTING: /accounting/designs/{id}... (the extension's routes.py)
 */
import { api, ApiError, download as fetchFile } from "./api";
import { history, pageTabs, resizeGrip } from "./canvasKit";
import { button, clear, h, icon, toast } from "./dom";
import { cellAt, drawSheet, letters, type Preview } from "./excelPreview";
import { openStatements, openTemplates } from "./excelTemplates";
import { busy as gate, markBusy } from "./loading";
import { menuButton } from "./workbenchMenu";
import { errorHere } from "./errorNote";

export const WORKBOOK_ENDING = ".design.json";
const COL_W = 76;
const ROW_H = 24;
const HEAD_W = 40;
const HEAD_H = 22;

export interface ColumnSpec {
  name: string;
  label?: string;
  format?: string;
  width?: number;
  total?: string;
}

export interface Block {
  id: string;
  kind: "title" | "text" | "table" | "pivot" | "chart";
  cell: string;
  w: number;
  h: number;
  text?: string;
  source?: { table?: string; query?: string };
  columns?: (ColumnSpec | string)[];
  total_row?: boolean;
  conditional?: { column: string; op: string; value: unknown; to?: unknown; fill?: string }[];
  rows?: string[];
  values?: { column?: string; agg: string; format?: string; label?: string }[];
  totals?: boolean;
  chart?: string;
  from?: string;
  category?: string;
  series?: string[];
  line_series?: string[];
  title?: string;
  style?: Record<string, unknown>;
}

export interface Sheet {
  id: string;
  name: string;
  freeze?: string;
  tab_colour?: string;
  print?: { orientation?: string; paper?: string; fit_width?: boolean; header?: string; footer?: string };
  blocks: Block[];
}

export interface Design {
  format: number;
  kind: "workbook";
  title: string;
  sheets: Sheet[];
}

export interface WorkbookState {
  id: string;
  path: string | null;
  title: string;
  design: Design;
  tables: string[];
  missing: string[];
  problems: string[];
  played: boolean;
  out_of_date: boolean;
  problem: string | null;
  unsaved: boolean;
  preview?: Preview;
  sheet?: string;
  block?: string;
  modified?: number;
}

export interface ExcelHost {
  path: () => string | null;
  title: () => string;
  /** Unsaved changes (true) or none. */
  changed: (dirty: boolean) => void;
  /** Where Save as puts the design (null: the chooser was closed). */
  chooseSave: () => Promise<string | null>;
  /** Saved at this path. */
  saved: (path: string, modified: number | null) => void;
  /** The canvas drew itself again: the status bar follows. */
  drew: () => void;
}

export interface ExcelView {
  element: HTMLElement;
  tools: HTMLElement;
  id: () => string | null;
  state: () => WorkbookState | null;
  mode: () => "edit" | "play";
  play: () => Promise<WorkbookState | null>;
  edit: () => void;
  save: (path?: string) => Promise<boolean>;
  exportPy: () => Promise<unknown>;
  noticed: (id: string) => void;
  report: () => Record<string, unknown>;
  close: () => void;
  select: (block: string | null) => void;
  addBlock: (kind: Block["kind"], fields?: Partial<Block>) => Promise<string | null>;
}

const KIND_ICONS: Record<Block["kind"], string> = { title: "rename", text: "note", table: "table", pivot: "group", chart: "chart" };
const KIND_WORDS: Record<Block["kind"], string> = { title: "Title", text: "Text", table: "Table", pivot: "Pivot", chart: "Chart" };
const FORMATS = ["", "general", "integer", "number", "currency", "accounting", "percent", "date", "month", "text"];

/** What a block says on the canvas: its text, its table, its pivot's shape, its chart. */
function blockWords(b: Block, every: Block[]): string {
  if (b.kind === "title" || b.kind === "text") return b.text || "(empty)";
  if (b.kind === "chart") {
    const from = every.find((x) => x.id === b.from);
    return `${b.chart ?? "column"} chart${from ? ` of ${from.source?.table ?? "a query"}` : ""}${b.title ? `: ${b.title}` : ""}`;
  }
  const source = b.source?.table ?? (b.source?.query ? "query" : "?");
  if (b.kind === "pivot") return `${source}: ${(b.rows ?? []).join(", ") || "—"} by ${((b.columns ?? []) as string[]).join(", ") || "—"}, ${(b.values ?? []).map((v) => `${v.agg} ${v.column ?? ""}`.trim()).join(", ")}`;
  const cols = (b.columns ?? []).map((c) => (typeof c === "string" ? c : c.label || c.name));
  return `${source}${cols.length ? `: ${cols.join(", ")}` : ""}${b.total_row ? " · total row" : ""}`;
}

export function excelView(path: string | null, host: ExcelHost, initial?: WorkbookState): ExcelView {
  let state: WorkbookState | null = initial ?? null;
  let sheetId: string | null = initial?.design.sheets[0]?.id ?? null;
  let selected: string | null = null;
  let mode: "edit" | "play" = "edit";
  let busy = false;
  let gone = false;
  let opening: Promise<WorkbookState> | null = null;
  const changes = history<Design>(); // canvasKit.ts: the Streamlit canvas's Undo and Redo
  let openTables: string[] = [];
  const listTables = (): void =>
    void api<{ datasets: { name: string }[] }>("/datasets").then(
      (found) => {
        openTables = found.datasets.map((d) => d.name);
        if (selected) drawProps();
      },
      () => undefined,
    );

  const top = h("div", { class: "cv-top xc-top" });
  const tools = h("span", { class: "cv-tools xc-tools" });
  const notes = h("div", { class: "cv-notes" });
  const board = h("div", { class: "xc-board", role: "list", "aria-label": "Blocks", tabindex: -1 });
  const props = h("aside", { class: "xc-props", "aria-label": "Properties" });
  const played = h("div", { class: "xc-played" });
  const middle = h("div", { class: "xc-middle" }, board, played, props);
  const element = h("div", { class: "cv xc", tabindex: -1 }, top, notes, middle);

  const sheet = (): Sheet | null => state?.design.sheets.find((s) => s.id === sheetId) ?? state?.design.sheets[0] ?? null;
  const base = (): string => `/accounting/designs/${encodeURIComponent(state?.id ?? "")}`;

  function take(next: WorkbookState): WorkbookState {
    state = next;
    if (!next.design.sheets.some((s) => s.id === sheetId)) sheetId = next.design.sheets[0]?.id ?? null;
    if (selected && !next.design.sheets.some((s) => s.blocks.some((b) => b.id === selected))) selected = null;
    host.changed(next.unsaved);
    draw();
    return next;
  }

  /** The design on the server (opened from its file, or new). */
  function ensure(): Promise<WorkbookState> {
    if (state) return Promise.resolve(state);
    opening ??= api<WorkbookState>("/accounting/designs", "POST", path ? { path } : { title: host.title() })
      .then((made) => {
        if (gone) void api(`/accounting/designs/${made.id}`, "DELETE").catch(() => undefined);
        return take(made);
      })
      .finally(() => (opening = null));
    return opening;
  }

  async function call(route: string, method: string, body?: unknown): Promise<WorkbookState> {
    await ensure();
    try {
      return take(await api<WorkbookState>(`${base()}${route}`, method, body));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404 && /not open/.test(e.message) && state) {
        // The server forgot it (it restarted): opened again with the design as it is here.
        const design = state.design;
        state = null;
        await api<WorkbookState>("/accounting/designs", "POST", { design, title: host.title() }).then(take);
        return take(await api<WorkbookState>(`${base()}${route}`, method, body));
      }
      throw e;
    }
  }

  /** A change of the design: sent, the state that comes back drawn; Undo can take it back. */
  async function change(route: string, method: string, body?: unknown): Promise<WorkbookState | null> {
    const before = state ? structuredClone(state.design) : null;
    try {
      const done = await call(route, method, body);
      if (before) changes.push(before);
      return done;
    } catch (e) {
      errorHere(e);
      return null;
    }
  }

  async function replace(design: Design | undefined): Promise<boolean> {
    if (!design) return false;
    try {
      await call("", "PUT", { design });
      return true;
    } catch (e) {
      errorHere(e);
      return false;
    }
  }

  const undo = (): Promise<boolean> => replace(state ? changes.undo(structuredClone(state.design)) : undefined);
  const redo = (): Promise<boolean> => replace(state ? changes.redo(structuredClone(state.design)) : undefined);

  // ===== blocks =====

  async function addBlock(kind: Block["kind"], fields: Partial<Block> = {}): Promise<string | null> {
    const s = sheet();
    if (!s) return null;
    const defaults: Partial<Block> =
      kind === "title"
        ? { text: state?.design.title || "Title" }
        : kind === "text"
          ? { text: "" }
          : kind === "chart"
            ? { chart: "column", from: (s.blocks.find((b) => b.kind === "pivot") ?? s.blocks.find((b) => b.kind === "table"))?.id ?? "" }
            : kind === "pivot"
              ? { source: { table: state?.tables[0] ?? openTables[0] ?? "" }, rows: [], columns: [], values: [{ agg: "count" }] }
              : { source: { table: state?.tables[0] ?? openTables[0] ?? "" } };
    const done = await change(`/sheets/${encodeURIComponent(s.id)}/blocks`, "POST", { kind, ...defaults, ...fields });
    if (done?.block) select(done.block);
    return done?.block ?? null;
  }

  const blockPath = (id: string): string => `/blocks/${encodeURIComponent(id)}`;
  const patch = (id: string, body: Partial<Block> | Record<string, unknown>): Promise<WorkbookState | null> => change(blockPath(id), "PATCH", body);

  function select(id: string | null): void {
    if (id && id !== selected) listTables();
    selected = id;
    for (const el of board.querySelectorAll<HTMLElement>(".xc-block")) {
      const on = el.dataset.block === id;
      el.classList.toggle("selected", on);
      el.setAttribute("aria-selected", String(on));
    }
    drawProps();
  }

  // ===== Play, Download, Export, Save =====

  async function play(): Promise<WorkbookState | null> {
    if (busy) return state;
    busy = true;
    drawTop();
    try {
      // The canvas is gated while the workbook builds (loading.ts).
      const done = await gate(middle, "Building the workbook…", call("/play", "POST"), { errorIn: false });
      mode = "play";
      draw();
      return done;
    } catch (e) {
      errorHere(e);
      return null;
    } finally {
      busy = false;
      drawTop();
    }
  }

  function edit(): void {
    mode = "edit";
    draw();
  }

  async function download(): Promise<void> {
    const { blob, name } = await fetchFile(`${base()}/download`);
    const link = h("a", { href: URL.createObjectURL(blob), download: name || `${state?.design.title || "workbook"}.xlsx` });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 4000);
  }

  async function save(to?: string): Promise<boolean> {
    let where = to ?? state?.path ?? null;
    if (!where) where = await host.chooseSave();
    if (!where) return false;
    try {
      const done = await call("/save", "POST", { path: where });
      host.saved(done.path ?? where, done.modified ?? null);
      return true;
    } catch (e) {
      errorHere(e);
      return false;
    }
  }

  async function exportPy(): Promise<unknown> {
    if (!state?.path && !(await save())) return null;
    await ensure();
    const done = await api<{ path: string; run: string; tables: string[] }>(`${base()}/export`, "POST", {});
    toast(`${done.path}: ${done.run}`);
    return done;
  }

  // ===== drawing =====

  function drawTop(): void {
    const design = state?.design;
    const tabs = pageTabs({
      pages: design?.sheets ?? [],
      current: sheet()?.id ?? null,
      label: "Sheets",
      noun: "sheet",
      tabClass: "cv-tab xc-sheet",
      maxLength: 31,
      select: (s) => {
        sheetId = s.id;
        selected = null;
        draw();
      },
      rename: (s, name) => void change(`/sheets/${encodeURIComponent(s.id)}`, "PATCH", { name }),
      holds: (s) => s.blocks.length > 0,
      remove: (s) => void change(`/sheets/${encodeURIComponent(s.id)}`, "DELETE"),
      add: () =>
        void change("/sheets", "POST", {}).then((next) => {
          if (next?.sheet) {
            sheetId = next.sheet;
            draw();
          }
        }),
    });
    clear(top, tabs);
    const stale = mode === "play" && !!state?.out_of_date;
    const editButton = button("Edit", () => edit(), { icon: "edit", class: "cv-edit", pressed: mode === "edit" && !busy });
    const playButton = button(stale ? "Out of date · Play" : "Play", () => void play(), { icon: "play", class: stale ? "cv-play cv-stale" : "cv-play", title: "Build the workbook from the open tables", pressed: mode === "play" || busy });
    playButton.disabled = busy || !state;
    if (busy) markBusy(playButton, "Building…");
    const undoButton = button("Undo", () => void undo(), { icon: "undo", iconOnly: true, class: "ghost cv-undo", title: "Undo (Ctrl+Z)" });
    const redoButton = button("Redo", () => void redo(), { icon: "redo", iconOnly: true, class: "ghost cv-redo", title: "Redo (Ctrl+Shift+Z)" });
    undoButton.disabled = !changes.canUndo();
    redoButton.disabled = !changes.canRedo();
    const add = h("button", { type: "button", class: "btn line xc-add", "aria-label": "Add a block", title: "Add a block" }, icon("plus"), h("span", { class: "btn-label" }, "Block"), icon("down")) as HTMLButtonElement;
    menuButton(add, "Blocks", () => (["title", "text", "table", "pivot", "chart"] as Block["kind"][]).map((k) => ({ label: KIND_WORDS[k], icon: KIND_ICONS[k], run: () => void addBlock(k) })));
    add.disabled = mode !== "edit";
    const more = h("button", { type: "button", class: "btn ghost xc-more", "aria-label": "Templates and statements", title: "Templates and statements" }, icon("excel"), h("span", { class: "btn-label" }, "Templates"), icon("down")) as HTMLButtonElement;
    menuButton(more, "Templates and statements", () => [
      { label: "Templates…", icon: "excel", run: () => void openTemplates() },
      { label: "Statements and invoices…", icon: "copy", run: () => void openStatements() },
    ]);
    const exportButton = button("Export workbook.py", () => void exportPy().catch((e: Error) => errorHere(e)), { icon: "export", class: "xc-export", title: "The automation that builds this workbook from data.py, without the app" });
    const downloadButton = button("Download", () => void download().catch((e: Error) => errorHere(e)), { icon: "import", class: "ghost xc-download", title: "The workbook Play built (.xlsx)" });
    downloadButton.disabled = !state?.played;
    clear(
      tools,
      h("span", { class: "cv-mode", role: "group", "aria-label": "Edit or play" }, editButton, playButton),
      h("span", { class: "cv-group", role: "group", "aria-label": "Undo and redo" }, undoButton, redoButton),
      add,
      more,
      exportButton,
      downloadButton,
    );
  }

  function drawNotes(): void {
    const said = [
      ...(state?.problem ? [state.problem] : []),
      ...(state?.missing.length ? [`Not open: ${state.missing.join(", ")}`] : []),
      ...(state?.problems ?? []),
    ];
    clear(notes, ...said.map((p) => h("p", { class: "cv-problem", role: "alert" }, p)));
    notes.hidden = !said.length;
  }

  function drawBoard(): void {
    const s = sheet();
    board.hidden = mode !== "edit";
    if (board.hidden || !s) return;
    const right = Math.max(18, ...s.blocks.map((b) => cellAt(b.cell)[1] + b.w + 3));
    const bottom = Math.max(36, ...s.blocks.map((b) => cellAt(b.cell)[0] + b.h + 6));
    const width = HEAD_W + right * COL_W;
    const height = HEAD_H + bottom * ROW_H;
    const heads = h(
      "div",
      { class: "xc-heads", "aria-hidden": "true" },
      ...Array.from({ length: right }, (_, i) => h("span", { class: "xc-colhead", style: { left: `${HEAD_W + i * COL_W}px`, width: `${COL_W}px` } }, letters(i + 1))),
      ...Array.from({ length: bottom }, (_, i) => h("span", { class: "xc-rowhead", style: { top: `${HEAD_H + i * ROW_H}px`, height: `${ROW_H}px` } }, String(i + 1))),
    );
    const freeze = s.freeze ? cellAt(s.freeze) : null;
    const lines = freeze ? [h("span", { class: "xc-freeze xc-freeze-row", style: { top: `${HEAD_H + (freeze[0] - 1) * ROW_H}px`, width: `${width}px` } }), h("span", { class: "xc-freeze xc-freeze-col", style: { left: `${HEAD_W + (freeze[1] - 1) * COL_W}px`, height: `${height}px` } })] : [];
    const sheetEl = h("div", { class: "xc-cells", style: { width: `${width}px`, height: `${height}px`, "--col": `${COL_W}px`, "--row": `${ROW_H}px` } }, heads, ...lines, ...s.blocks.map((b) => card(b, s.blocks)));
    clear(board, sheetEl);
    if (!s.blocks.length) board.append(h("p", { class: "cv-empty xc-empty" }, "Add a block: a title, a table, a pivot, a chart"));
  }

  function card(b: Block, every: Block[]): HTMLElement {
    const [row, col] = cellAt(b.cell);
    const grip = h("button", { type: "button", class: "card-grip cv-grip xc-grip", "aria-label": `Resize ${KIND_WORDS[b.kind]} at ${b.cell}`, title: "Resize: drag, or the arrow keys" });
    const size = h("span", { class: "hint xc-size" }, `${b.cell} · ${b.w}×${b.h}`);
    const el = h(
      "article",
      {
        class: `xc-block xc-${b.kind} ${b.id === selected ? "selected" : ""}`,
        role: "listitem",
        tabindex: 0,
        "aria-selected": String(b.id === selected),
        "aria-label": `${KIND_WORDS[b.kind]} at ${b.cell}, ${b.w} columns by ${b.h} rows`,
        dataset: { block: b.id, cell: b.cell, kind: b.kind },
        style: { left: `${HEAD_W + (col - 1) * COL_W}px`, top: `${HEAD_H + (row - 1) * ROW_H}px`, width: `${b.w * COL_W - 2}px`, height: `${b.h * ROW_H - 2}px` },
      },
      h("div", { class: "xc-block-head" }, icon(KIND_ICONS[b.kind]), h("span", { class: `xc-block-kind ${b.kind === "title" ? "xc-title-words" : ""}` }, b.kind === "title" ? b.text || "Title" : KIND_WORDS[b.kind]), h("span", { class: "spacer" }), button(`Remove the ${KIND_WORDS[b.kind].toLowerCase()} at ${b.cell}`, () => void change(blockPath(b.id), "DELETE"), { icon: "close", iconOnly: true, class: "ghost xc-remove" })),
      b.kind === "title" ? null : h("div", { class: "xc-block-words" }, blockWords(b, every)),
      size,
      grip,
    );
    // A click selects it; a drag moves it, snapped to the cells.
    el.addEventListener("pointerdown", (down) => {
      if ((down.target as HTMLElement).closest("button") || down.button !== 0) return;
      select(b.id);
      const startLeft = el.offsetLeft;
      const startTop = el.offsetTop;
      let moved = false;
      let at: [number, number] = [row, col];
      el.setPointerCapture(down.pointerId);
      const move = (e: PointerEvent): void => {
        const dx = e.clientX - down.clientX;
        const dy = e.clientY - down.clientY;
        if (!moved && Math.abs(dx) + Math.abs(dy) < 5) return;
        moved = true;
        el.classList.add("dragging");
        const c = Math.max(1, Math.round((startLeft + dx - HEAD_W) / COL_W) + 1);
        const r = Math.max(1, Math.round((startTop + dy - HEAD_H) / ROW_H) + 1);
        at = [r, c];
        el.style.left = `${HEAD_W + (c - 1) * COL_W}px`;
        el.style.top = `${HEAD_H + (r - 1) * ROW_H}px`;
        size.textContent = `${letters(c)}${r} · ${b.w}×${b.h}`;
      };
      const up = (): void => {
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerup", up);
        el.removeEventListener("pointercancel", up);
        el.classList.remove("dragging");
        if (moved && (at[0] !== row || at[1] !== col)) void patch(b.id, { cell: `${letters(at[1])}${at[0]}` });
      };
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
      el.addEventListener("pointercancel", up);
    });
    el.addEventListener("keydown", (e) => {
      if (e.target !== el) return;
      const step: Record<string, [number, number]> = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] };
      if (step[e.key]) {
        e.preventDefault();
        const [dr, dc] = step[e.key] ?? [0, 0];
        if (row + dr >= 1 && col + dc >= 1) void patch(b.id, { cell: `${letters(col + dc)}${row + dr}` }).then(() => focusBlock(b.id));
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        void change(blockPath(b.id), "DELETE");
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        select(b.id);
      }
    });
    // Resize: the corner (canvasKit.ts), snapped to whole cells.
    resizeGrip(
      grip,
      () => el.classList.add("resizing"),
      (dx, dy) => {
        const w = Math.max(1, Math.round((b.w * COL_W + dx) / COL_W));
        const hh = Math.max(1, Math.round((b.h * ROW_H + dy) / ROW_H));
        el.style.width = `${w * COL_W - 2}px`;
        el.style.height = `${hh * ROW_H - 2}px`;
        el.dataset.w = String(w);
        el.dataset.h = String(hh);
        size.textContent = `${b.cell} · ${w}×${hh}`;
      },
      () => {
        el.classList.remove("resizing");
        const w = Number(el.dataset.w ?? b.w);
        const hh = Number(el.dataset.h ?? b.h);
        if (w !== b.w || hh !== b.h) void patch(b.id, { w, h: hh });
      },
    );
    grip.addEventListener("keydown", (e) => {
      const step: Record<string, [number, number]> = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] };
      const [dw, dh] = step[e.key] ?? [0, 0];
      if (!dw && !dh) return;
      e.preventDefault();
      e.stopPropagation();
      void patch(b.id, { w: Math.max(1, b.w + dw), h: Math.max(1, b.h + dh) });
    });
    return el;
  }

  function focusBlock(id: string): void {
    board.querySelector<HTMLElement>(`.xc-block[data-block="${id}"]`)?.focus();
  }

  // ===== Properties: the selected block's fields, or the sheet's =====

  function field(label: string, input: HTMLElement): HTMLElement {
    return h("label", { class: "xc-field" }, h("span", {}, label), input);
  }

  function text(value: string, done: (v: string) => void, attrs: Record<string, unknown> = {}): HTMLInputElement {
    const input = h("input", { type: "text", value, spellcheck: "false", ...attrs }) as HTMLInputElement;
    input.addEventListener("change", () => done(input.value));
    input.addEventListener("keydown", (e) => e.stopPropagation());
    return input;
  }

  function choice(value: string, options: string[], done: (v: string) => void, attrs: Record<string, unknown> = {}): HTMLSelectElement {
    const select = h("select", attrs, ...options.map((o) => h("option", { value: o, selected: o === value }, o || "—"))) as HTMLSelectElement;
    select.addEventListener("change", () => done(select.value));
    return select;
  }

  function names(value: string[] | undefined, done: (v: string[]) => void, attrs: Record<string, unknown> = {}): HTMLInputElement {
    return text((value ?? []).join(", "), (v) => done(v.split(",").map((x) => x.trim()).filter(Boolean)), attrs);
  }

  function drawProps(): void {
    const s = sheet();
    props.hidden = mode !== "edit";
    if (props.hidden || !s || !state) return clear(props);
    const b = s.blocks.find((x) => x.id === selected);
    if (!b) {
      const p = s.print ?? {};
      const setPrint = (k: string, v: unknown): void => void change(`/sheets/${encodeURIComponent(s.id)}`, "PATCH", { print: { ...p, [k]: v } });
      return clear(
        props,
        h("h3", {}, s.name),
        field("Freeze panes at", text(s.freeze ?? "", (v) => void change(`/sheets/${encodeURIComponent(s.id)}`, "PATCH", { freeze: v.trim() || null }), { placeholder: "A2", class: "xc-freeze-at" })),
        field("Orientation", choice(p.orientation ?? "", ["", "portrait", "landscape"], (v) => setPrint("orientation", v || undefined), { class: "xc-orientation" })),
        field("Paper", choice(p.paper ?? "", ["", "A4", "Letter"], (v) => setPrint("paper", v || undefined))),
        h("label", { class: "xc-check" }, (() => {
          const box = h("input", { type: "checkbox", checked: !!p.fit_width, class: "xc-fit" }) as HTMLInputElement;
          box.addEventListener("change", () => setPrint("fit_width", box.checked));
          return box;
        })(), "Fit to width"),
        field("Header", text(p.header ?? "", (v) => setPrint("header", v || undefined))),
        field("Footer", text(p.footer ?? "", (v) => setPrint("footer", v || undefined), { placeholder: "Page &P of &N" })),
      );
    }
    const set = (body: Record<string, unknown>): void => void patch(b.id, body);
    const parts: HTMLElement[] = [h("h3", {}, `${KIND_WORDS[b.kind]} · ${b.cell}`), field("Cell", text(b.cell, (v) => set({ cell: v.trim().toUpperCase() }), { class: "xc-cell-at" }))];
    if (b.kind === "title" || b.kind === "text") {
      const area = h("textarea", { rows: b.kind === "text" ? 4 : 2, class: "xc-text" }, b.text ?? "") as HTMLTextAreaElement;
      area.addEventListener("change", () => set({ text: area.value }));
      area.addEventListener("keydown", (e) => e.stopPropagation());
      parts.push(field("Text", area));
    }
    if (b.kind === "table" || b.kind === "pivot") {
      const byQuery = !!b.source?.query;
      const tables = [...new Set([...openTables, ...(state.tables ?? []), ...(b.source?.table ? [b.source.table] : [])])];
      parts.push(field("Reads", choice(byQuery ? "a query" : "a table", ["a table", "a query"], (v) => set({ source: v === "a query" ? { query: `SELECT * FROM ${b.source?.table || tables[0] || "t"}` } : { table: tables[0] ?? "" } }))));
      if (byQuery) {
        const area = h("textarea", { rows: 4, class: "xc-query mono", spellcheck: "false" }, b.source?.query ?? "") as HTMLTextAreaElement;
        area.addEventListener("change", () => set({ source: { query: area.value } }));
        area.addEventListener("keydown", (e) => e.stopPropagation());
        parts.push(field("DuckDB query", area));
      } else parts.push(field("Table", text(b.source?.table ?? "", (v) => set({ source: { table: v.trim() } }), { class: "xc-source", list: "xc-open-tables" })));
    }
    if (b.kind === "table") {
      const specs = (b.columns ?? []).map((c) => (typeof c === "string" ? { name: c } : c));
      parts.push(field("Columns", names(specs.map((c) => c.name), (v) => set({ columns: v.map((n) => specs.find((c) => c.name === n) ?? { name: n }) }), { placeholder: "every column", class: "xc-columns" })));
      for (const c of specs) {
        const row = h(
          "div",
          { class: "xc-column", dataset: { column: c.name } },
          h("span", { class: "mono" }, c.name),
          choice(c.format ?? "", FORMATS, (v) => set({ columns: specs.map((x) => (x.name === c.name ? { ...x, format: v || undefined } : x)) }), { "aria-label": `${c.name}'s format` }),
          choice(c.total ?? "", ["", "sum", "count", "average", "min", "max"], (v) => set({ columns: specs.map((x) => (x.name === c.name ? { ...x, total: v || undefined } : x)), total_row: v ? true : b.total_row }), { "aria-label": `${c.name}'s total` }),
        );
        parts.push(row);
      }
      parts.push(
        h("label", { class: "xc-check" }, (() => {
          const box = h("input", { type: "checkbox", checked: !!b.total_row, class: "xc-total-row" }) as HTMLInputElement;
          box.addEventListener("change", () => set({ total_row: box.checked }));
          return box;
        })(), "Total row"),
      );
      const rule = b.conditional?.[0];
      parts.push(
        field("Colour when", h(
          "span",
          { class: "xc-rule" },
          choice(rule?.column ?? "", ["", ...specs.map((c) => c.name)], (v) => set({ conditional: v ? [{ column: v, op: rule?.op ?? ">", value: rule?.value ?? 0, fill: rule?.fill ?? "#F8D7DA" }] : [] }), { "aria-label": "Column" }),
          choice(rule?.op ?? ">", [">", ">=", "<", "<=", "=", "!="], (v) => rule && set({ conditional: [{ ...rule, op: v }] }), { "aria-label": "Rule" }),
          text(rule ? String(rule.value ?? "") : "", (v) => rule && set({ conditional: [{ ...rule, value: Number.isFinite(Number(v)) && v.trim() !== "" ? Number(v) : v }] }), { "aria-label": "Value", class: "xc-rule-value" }),
        )),
      );
    }
    if (b.kind === "pivot") {
      parts.push(field("Rows", names(b.rows, (v) => set({ rows: v }), { class: "xc-rows" })));
      parts.push(field("Columns", names(b.columns as string[] | undefined, (v) => set({ columns: v }), { class: "xc-pivot-columns" })));
      const values = b.values ?? [{ agg: "count" }];
      values.forEach((v, i) =>
        parts.push(
          h(
            "div",
            { class: "xc-value" },
            choice(v.agg, ["sum", "count", "average", "min", "max"], (agg) => set({ values: values.map((x, j) => (j === i ? { ...x, agg } : x)) }), { "aria-label": "Summary" }),
            text(v.column ?? "", (column) => set({ values: values.map((x, j) => (j === i ? { ...x, column: column.trim() || undefined } : x)) }), { "aria-label": "Of", placeholder: "column", class: "xc-value-column" }),
            choice(v.format ?? "", FORMATS, (format) => set({ values: values.map((x, j) => (j === i ? { ...x, format: format || undefined } : x)) }), { "aria-label": "Format" }),
          ),
        ),
      );
      parts.push(button("Value", () => set({ values: [...values, { agg: "sum", column: "" }] }), { icon: "plus", class: "ghost xc-add-value" }));
    }
    if (b.kind === "chart") {
      const sources = state.design.sheets.flatMap((x) => x.blocks).filter((x) => x.kind === "table" || x.kind === "pivot");
      parts.push(field("Chart", choice(b.chart ?? "column", ["column", "bar", "line", "pie", "combo"], (v) => set({ chart: v }), { class: "xc-chart-kind" })));
      const shows = h("select", { class: "xc-chart-from" }, h("option", { value: "" }, "—"), ...sources.map((x) => h("option", { value: x.id, selected: x.id === b.from }, `${KIND_WORDS[x.kind]} at ${x.cell}${x.source?.table ? ` (${x.source.table})` : ""}`))) as HTMLSelectElement;
      shows.addEventListener("change", () => set({ from: shows.value }));
      parts.push(field("Shows", shows));
      parts.push(field("Title", text(b.title ?? "", (v) => set({ title: v || undefined }))));
      parts.push(field("Category", text(b.category ?? "", (v) => set({ category: v.trim() || undefined }), { placeholder: "its first column" })));
      parts.push(field("Series", names(b.series, (v) => set({ series: v }), { placeholder: "every number column" })));
      if (b.chart === "combo") parts.push(field("As lines", names(b.line_series, (v) => set({ line_series: v }))));
    }
    const sizes = h("div", { class: "xc-sizes" }, field("Width", text(String(b.w), (v) => set({ w: Number(v) || b.w }), { inputmode: "numeric" })), field("Height", text(String(b.h), (v) => set({ h: Number(v) || b.h }), { inputmode: "numeric" })));
    clear(props, ...parts, sizes, h("datalist", { id: "xc-open-tables" }, ...[...new Set([...openTables, ...state.tables])].map((t) => h("option", { value: t }))));
  }

  function drawPlayed(): void {
    played.hidden = mode !== "play";
    if (played.hidden) return clear(played);
    const shown = state?.preview?.sheets.find((s) => s.name === sheet()?.name) ?? state?.preview?.sheets[0];
    clear(played, shown ? drawSheet(shown, { names: state?.preview?.names }) : h("p", { class: "cv-empty" }, "Play builds the workbook"));
  }

  function draw(): void {
    element.classList.toggle("live", mode === "play");
    drawTop();
    drawNotes();
    drawBoard();
    drawProps();
    drawPlayed();
    host.drew();
  }

  element.addEventListener("keydown", (e) => {
    if ((e.target as HTMLElement).closest("input, textarea, select")) return;
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "z") {
      e.preventDefault();
      void (e.shiftKey ? redo() : undo());
    } else if (e.key === "Escape" && selected) select(null);
  });
  board.addEventListener("pointerdown", (e) => {
    if (!(e.target as HTMLElement).closest(".xc-block") && selected) select(null);
  });

  draw();
  listTables();
  void ensure().catch((e: Error) => errorHere(e));

  return {
    element,
    tools,
    id: () => state?.id ?? null,
    state: () => state,
    mode: () => mode,
    play,
    edit,
    save,
    exportPy,
    noticed: (id) => {
      // Another window's or the agent's change: drawn again only when the design is not the one shown
      // (this window's own changes came back with their answer).
      if (id !== state?.id) return;
      void api<WorkbookState>(base()).then((next) => {
        if (JSON.stringify(next.design) !== JSON.stringify(state?.design) || next.played !== state?.played) take(next);
      }, () => undefined);
    },
    report: () => ({ id: state?.id ?? null, path: state?.path ?? null, mode, sheet: sheet()?.name ?? null, selected, played: state?.played ?? false, out_of_date: state?.out_of_date ?? false, missing: state?.missing ?? [], problems: state?.problems ?? [], design: state?.design ?? null }),
    close: () => {
      gone = true;
      if (state) void api(`/accounting/designs/${state.id}`, "DELETE").catch(() => undefined);
    },
    select: (id) => select(id),
    addBlock,
  };
}
