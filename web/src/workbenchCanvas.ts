/**
 * workbenchCanvas.ts: a Streamlit app's canvas (docs/ideas.md, the Streamlit canvas, 2026-11-15): a
 * Workbench document of its own (sales.stapp.json), beside notebooks and scripts. [WIRE]
 *
 *   [BLOCKS]  before Play the canvas shows blocks on a 12-column grid. A block is a LINK to a Python
 *             cell of a notebook or script: drag a cell here (from this window or another Workbench
 *             window), or copy it and paste (Ctrl+V). It shows the cell's first comment or first
 *             line, its file and @cell number, what it makes and reads; in red when the cell or its
 *             file is gone. Drag a block to move it (or the arrow keys), drag its corner to resize it
 *             (arrow keys too; a double-click fits its height), Delete takes it off the page
 *   [PAGES]   the app's pages as tabs: add, rename (double-click or F2), remove
 *   [PLAY]    Play runs the app from the linked cells as they are now (saved or not) and shows the
 *             page live, in place (a frame of this server's, sandboxed without the app's origin).
 *             Edit goes back to the blocks. When a linked cell's code, a table it reads or the layout
 *             changes, the page says "Out of date · Play". Nothing runs by itself
 *   [SAVE]    the canvas's file holds pages, blocks, links and places: no code. Export… writes an app
 *             that runs alone (the data as Parquet); Save as… zips the project (data.py, pages/*.py,
 *             the sources): no rows
 *
 * The server holds the app (services/streamlit.py): every action here is a route, so the agent's
 * streamlit_* commands do the same, and a change made anywhere shows here at once.
 *
 * ROUTING: /streamlit/apps/{app}... (routes_streamlit.py); the `streamlit_changed` notice
 */
import { agentApi, api, ApiError } from "./api";
import { button, clear, h, toast } from "./dom";
import { FRAME_SANDBOX } from "./workbenchHtml";
import { type BlockState, type CanvasPage, type CanvasState, type CellLink, CELL_DRAG, copiedCell, draggedLink, type ExportResult, frameAddress, partsOf, problemText, type SaveAsResult, type SavedPage, savedPages } from "./workbenchStreamlit";

const COLUMNS = 12;
const GAP = 8;
const ROW = 40; // pixels a unit of a block's height stands for (domain/streamlit_cells.py ROW_HEIGHT)
const MIN_WIDTH = 2;
const MAX_ROWS = 30;
const DEFAULT_WIDTH = 6;
const BLOCK_DRAG = "application/x-swissarmybench-block";

export interface CanvasHost {
  title: () => string;
  path: () => string | null;
  window: string;
  /** The pages changed (true: they are not the ones last saved). */
  changed: (dirty: boolean) => void;
  /** Every open notebook and script has told the server its cells as they stand (before Play). */
  settle: () => Promise<void>;
  /** A folder for Export, a zip's path for Save as (null: the user closed the chooser). */
  chooseFolder: () => Promise<string | null>;
  chooseZip: () => Promise<string | null>;
  /** Save the app's file (true: it is saved): Save as needs its folder. */
  save: () => Promise<boolean>;
  /** The canvas was drawn again (its state, or Play starting): the status bar follows. */
  drew: () => void;
}

export interface CanvasView {
  element: HTMLElement;
  /** Play, Edit, Export, Save as: the page puts them in the document's row of controls. */
  tools: HTMLElement;
  app: () => string | null;
  state: () => CanvasState | null;
  /** The pages, as the app's file keeps them. */
  pages: () => SavedPage[];
  mode: () => "edit" | "live";
  /** Play is starting the app. */
  busy: () => boolean;
  /** Play: run the app, then show the page live. */
  play: (page?: string) => Promise<CanvasState | null>;
  edit: () => void;
  /** Place a cell's link on the page in front (a new page when there is none). */
  place: (link: CellLink, where?: { row: number; column: number; insert?: boolean }) => Promise<boolean>;
  /** Paste the copied cell's link (false: nothing was copied). */
  paste: () => Promise<boolean>;
  /** `agent`: the agent asked (workbench_window): the export is its request, which the server holds
   * for the user's Allow (the rows leave the app). The user's own click asks nothing. */
  exportApp: (folder?: string, agent?: boolean) => Promise<ExportResult | null>;
  saveAs: (path?: string, agent?: boolean) => Promise<SaveAsResult | null>;
  /** The file was saved (at this path): the server knows, and these pages are the saved ones. */
  saved: (path: string) => void;
  noticed: (app: string) => void;
  tablesChanged: () => void;
  focus: () => void;
  /** What it shows, for the agent. */
  report: () => unknown;
  close: () => void;
}

export function canvasView(initial: SavedPage[], host: CanvasHost): CanvasView {
  let state: CanvasState | null = null;
  let id: string | null = null;
  let opening: Promise<string> | null = null;
  let pageId: string | null = null;
  let mode: "edit" | "live" = "edit";
  let busy = false;
  let gone = false;
  let kept = JSON.stringify(savedPages(initial).map(({ name, blocks }) => ({ name, blocks: blocks.map(({ id: _, ...rest }) => rest) })));
  let frame: HTMLIFrameElement | null = null;
  let shown: string | null = null;
  let refocus: string | null = null; // the block (or its grip) the keyboard was on before a change

  const top = h("div", { class: "cv-top" });
  const tools = h("span", { class: "cv-tools" });
  const notes = h("div", { class: "cv-notes" });
  const board = h("div", { class: "cv-board", role: "list", "aria-label": "Blocks" });
  const live = h("div", { class: "cv-live" });
  const element = h("div", { class: "cv", tabindex: -1 }, top, notes, board, live);

  const signature = (pages: (CanvasPage | SavedPage)[]): string => JSON.stringify(savedPages(pages).map(({ name, blocks }) => ({ name, blocks: blocks.map(({ id: _, ...rest }) => rest) })));
  const current = (): CanvasPage | null => state?.pages.find((p) => p.id === pageId) ?? null;
  const base = (): string => `/streamlit/apps/${encodeURIComponent(id ?? "")}`;

  function take(next: CanvasState, opened = false): CanvasState {
    state = next;
    if (!next.pages.some((p) => p.id === pageId)) pageId = next.pages[0]?.id ?? null;
    if (opened) kept = signature(next.pages);
    host.changed(signature(next.pages) !== kept);
    draw();
    return next;
  }

  /** The app on the server, opened when it is not (or when the server no longer knows it). */
  function ensure(): Promise<string> {
    if (id) return Promise.resolve(id);
    if (!opening) {
      const pages = state ? savedPages(state.pages) : initial;
      const was = kept;
      opening = api<CanvasState>("/streamlit/apps", "POST", { canvas: true, title: host.title(), document: host.path(), window: host.window, pages })
        .then((made) => {
          id = made.app;
          if (gone) void api(`/streamlit/apps/${made.app}`, "DELETE").catch(() => undefined);
          take(made, true);
          kept = was; // what the server made of the file's pages (ids given) is not a change
          host.changed(signature(made.pages) !== kept);
          return made.app;
        })
        .finally(() => (opening = null));
    }
    return opening;
  }

  /** A call on the app; an app the server forgot (it restarted) is opened again, once. */
  async function call<T extends CanvasState = CanvasState>(path: string, method: string, body?: unknown): Promise<T> {
    const app = await ensure();
    try {
      return take(await api<T>(`/streamlit/apps/${app}${path}`, method, body)) as T;
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 404 || id !== app || !/app is not open/.test(e.message)) throw e;
      id = null;
      const again = await ensure();
      return take(await api<T>(`/streamlit/apps/${again}${path}`, method, body)) as T;
    }
  }

  /** A change of the layout: sent, and the state that comes back drawn. */
  async function change(path: string, method: string, body?: unknown): Promise<(CanvasState & { page?: string; block?: string }) | null> {
    try {
      return await call(path, method, body);
    } catch (e) {
      toast((e as Error).message, "error");
      return null;
    }
  }

  // ===== Play, Edit =====

  async function play(page?: string): Promise<CanvasState | null> {
    if (busy) return state;
    if (page && state?.pages.some((p) => p.id === page)) pageId = page;
    busy = true;
    draw();
    try {
      await host.settle(); // the linked cells as they are typed, saved or not
      const ran = await call("/run", "POST");
      if (ran.problem?.kind === "failed") toast(problemText(ran.problem), "error");
      if (ran.running && !ran.problem) mode = "live";
      return ran;
    } catch (e) {
      toast((e as Error).message, "error");
      return null;
    } finally {
      busy = false;
      draw();
    }
  }

  function edit(): void {
    mode = "edit";
    draw();
  }

  async function install(): Promise<void> {
    if (busy || !id) return;
    busy = true;
    draw();
    try {
      const done = await api<{ ok: boolean; output: string }>(`${base()}/install`, "POST");
      if (!done.ok) throw new Error(done.output.trim().split("\n").slice(-6).join("\n") || "The install failed.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      busy = false;
    }
    await play();
  }

  async function exportApp(folder?: string, agent = false): Promise<ExportResult | null> {
    const chosen = folder ?? (await host.chooseFolder());
    if (!chosen) return null;
    await ensure();
    await host.settle();
    const done = await (agent ? agentApi : api)<ExportResult>(`${base()}/export`, "POST", { folder: chosen });
    // Where it went, and how to run it: what the user needs next.
    toast(`${done.folder}: ${done.run}`, done.problems.length ? "error" : "info");
    for (const problem of done.problems) toast(problem, "error");
    return done;
  }

  async function saveAs(path?: string, agent = false): Promise<SaveAsResult | null> {
    // The project is the folder of the app's file: it is saved first.
    if ((!host.path() || signature(state?.pages ?? initial) !== kept) && !(await host.save())) return null;
    const chosen = path ?? (await host.chooseZip());
    if (!chosen) return null;
    await ensure();
    await host.settle();
    const done = await (agent ? agentApi : api)<SaveAsResult>(`${base()}/save-as`, "POST", { path: chosen });
    toast(done.path, done.problems.length ? "error" : "info");
    for (const problem of done.problems) toast(problem, "error");
    return done;
  }

  // ===== placing a cell's link =====

  async function place(link: CellLink, where?: { row: number; column: number; insert?: boolean }): Promise<boolean> {
    if (!link.document) {
      toast(`Save ${link.title} first: a block links to a cell in a saved file.`, "error");
      return false;
    }
    await host.settle().catch(() => undefined); // a cell just typed is known to the server first
    const body = { document: link.document, cell: link.cell, ...(where ?? {}) };
    const page = current();
    const done = page ? await change(`/pages/${page.id}/blocks`, "POST", body) : await change("/pages", "POST", body);
    if (!done) return false;
    if (done.page) pageId = done.page;
    refocus = done.block ?? done.pages.find((p) => p.id === pageId)?.blocks.at(-1)?.id ?? null;
    if (mode === "live") mode = "edit"; // the new block is shown where it went
    draw();
    return true;
  }

  async function paste(): Promise<boolean> {
    const link = copiedCell();
    if (!link) return false;
    if (link.kind !== "code" && link.kind !== "markdown" && link.kind !== "html") {
      toast("A Python, Markdown or HTML cell goes on a Streamlit app's canvas.", "error");
      return true;
    }
    await place(link);
    return true;
  }

  // ===== the top: the pages as tabs, and the app's tools =====

  function renamePage(page: CanvasPage, label: HTMLElement): void {
    const input = h("input", { type: "text", class: "cv-rename", value: page.name, "aria-label": "Page name", maxlength: 80 }) as HTMLInputElement;
    let done = false;
    const finish = (keep: boolean): void => {
      if (done) return;
      done = true;
      const name = input.value.trim();
      if (keep && name && name !== page.name) void change(`/pages/${page.id}`, "PATCH", { name });
      else draw();
    };
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") finish(true);
      else if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
    label.replaceWith(input);
    input.focus();
    input.select();
  }

  function drawTop(): void {
    const pages = state?.pages ?? [];
    const page = current();
    const tabs = pages.map((p) => {
      const label = h("span", { class: "tab-label" }, p.name);
      const tab = h(
        "div",
        {
          class: `tab-item cv-tab ${p.id === pageId ? "active" : ""}`,
          role: "tab",
          "aria-selected": String(p.id === pageId),
          tabindex: p.id === pageId ? "0" : "-1",
          title: p.name,
          dataset: { page: p.id },
          onclick: () => {
            if (pageId === p.id) return;
            pageId = p.id;
            draw();
          },
          ondblclick: () => renamePage(p, label),
          onkeydown: (e: KeyboardEvent) => {
            if (e.target !== tab) return;
            if (e.key === "F2") renamePage(p, label);
            else if (e.key === "Enter" || e.key === " ") tab.click();
          },
        },
        label,
        button(`Remove ${p.name}`, (e) => {
          e.stopPropagation();
          if (p.blocks.length && !confirm(`Remove the page ${p.name}? The cells its blocks link to stay where they are.`)) return;
          void change(`/pages/${p.id}`, "DELETE");
        }, { icon: "close", iconOnly: true, class: "tab-close" }),
      );
      // A cell dropped on a page's tab goes to the end of that page.
      tab.addEventListener("dragover", (e) => {
        if (e.dataTransfer?.types.includes(CELL_DRAG)) e.preventDefault();
      });
      tab.addEventListener("drop", (e) => {
        const link = draggedLink(e.dataTransfer);
        if (!link) return;
        e.preventDefault();
        e.stopPropagation();
        pageId = p.id;
        void place(link);
      });
      return tab;
    });
    // Edit | Play: one pair, the mode in front pressed (the mockup's segmented control). Play while
    // the page shows runs it again; it says so when the page is out of date.
    const stale = mode === "live" && !!page?.out_of_date;
    const editButton = button("Edit", () => edit(), { icon: "edit", class: "cv-edit", title: "The blocks", pressed: mode === "edit" && !busy });
    const playButton = button(busy ? "Starting…" : stale ? "Out of date · Play" : "Play", () => void play(), {
      icon: "play",
      class: stale ? "cv-play cv-stale" : "cv-play",
      title: stale ? "A linked cell, a table it reads or the layout changed: Play shows it" : mode === "live" ? "Play again: the page from the linked cells as they are now" : "Play: run the page from the linked cells as they are now",
      pressed: mode === "live" || busy,
    });
    playButton.disabled = busy || !page;
    const modes = h("span", { class: "cv-mode", role: "group", "aria-label": "Edit or play" }, editButton, playButton);
    const exportButton = button("Export…", () => void exportApp().catch((e: Error) => toast(e.message, "error")), { icon: "export", class: "cv-export", title: "Export an app that runs alone: app.py, its pages, the data as Parquet" });
    const saveAsButton = button("Save as zip…", () => void saveAs().catch((e: Error) => toast(e.message, "error")), { icon: "save", class: "cv-save-as", title: "Save as: the project as one zip (data.py, pages, the sources; no rows)" });
    exportButton.disabled = saveAsButton.disabled = !pages.length;
    clear(
      top,
      h(
        "div",
        { class: "cv-tabs", role: "tablist", "aria-label": "Pages" },
        ...tabs,
        button("New page", () => void change("/pages", "POST", {}).then((next) => {
          if (next?.page) {
            pageId = next.page;
            draw();
          }
        }), { icon: "plus", class: "ghost cv-new-page" }),
      ),
    );
    clear(tools, modes, exportButton, saveAsButton);
  }

  // ===== what needs the user: the app's problem, the page's problems =====

  function drawNotes(): void {
    const page = current();
    const problem = state?.problem ?? null;
    const said = mode === "edit" ? (page?.problems ?? []).filter((p) => !page!.blocks.some((b) => b.missing && p.includes(b.missing))) : [];
    clear(
      notes,
      problem ? h("p", { class: "cv-problem", role: "alert" }, problemText(problem), problem.kind === "missing" ? button(busy ? "Installing…" : "Install", () => void install(), { class: "primary cv-install", title: problem.command }) : null) : null,
      ...said.map((p) => h("p", { class: "cv-problem", role: "alert" }, p)),
      ...(mode === "live" ? (state?.notes ?? []) : []).map((n) => h("p", { class: "cv-problem", role: "alert" }, n)),
    );
    notes.hidden = !notes.childElementCount;
  }

  // ===== the board: the page's blocks on 12 columns =====

  interface Drop {
    row: number;
    column: number;
    insert: boolean;
  }

  /** Where a drop at this point lands: the row under it (or a new one between two rows, above the
   *  first, below the last) and the column, so a block `w` wide sits centred under the pointer. */
  function dropAt(x: number, y: number, w: number): Drop {
    const rows = [...board.querySelectorAll<HTMLElement>(".cv-row")];
    const box = board.getBoundingClientRect();
    const inner = box.width - 24; // the board's own padding
    const columnWidth = (inner + GAP) / COLUMNS;
    const column = Math.max(1, Math.min(COLUMNS - w + 1, Math.round((x - box.left - 12) / columnWidth - w / 2) + 1));
    for (const [i, row] of rows.entries()) {
      const at = row.getBoundingClientRect();
      if (y < at.top - 1) return { row: i + 1, column, insert: true }; // the gap above it
      if (y <= at.bottom + 1) return { row: i + 1, column, insert: false };
    }
    return { row: rows.length + 1, column, insert: false };
  }

  let ghost: HTMLElement | null = null;
  function markDrop(drop: Drop | null, w = DEFAULT_WIDTH): void {
    ghost?.remove();
    ghost = null;
    for (const line of board.querySelectorAll(".cv-insert")) line.remove();
    board.classList.toggle("dropping", drop !== null);
    if (!drop) return;
    const rows = [...board.querySelectorAll<HTMLElement>(".cv-row")];
    ghost = h("div", { class: "cv-ghost", "aria-hidden": "true", style: { gridColumn: `${drop.column} / span ${w}`, gridRow: "1" } });
    const target = drop.insert ? undefined : rows[drop.row - 1];
    if (target) target.append(ghost);
    else {
      // A row of its own: drawn where it would be.
      const line = h("div", { class: "cv-row cv-insert" }, ghost);
      board.insertBefore(line, rows[drop.row - 1] ?? null);
    }
  }

  const sizeWords = (b: { w: number; h: number | null }): string => `${b.w} of ${COLUMNS} wide${b.h === null ? "" : ` · ${b.h * ROW}px tall`}`;

  function moveMenu(page: CanvasPage, block: BlockState, anchor: HTMLElement): void {
    document.querySelector(".menu")?.remove();
    const menu = h(
      "div",
      { class: "menu", role: "menu", "aria-label": "Move to another page" },
      ...state!.pages.filter((p) => p.id !== page.id).map((p) => h("button", { type: "button", role: "menuitem", onclick: () => { menu.remove(); void change(`/pages/${page.id}/blocks/${block.id}`, "PATCH", { page: p.id }); } }, `Move to ${p.name}`)),
    );
    document.body.append(menu);
    const box = anchor.getBoundingClientRect();
    menu.style.top = `${box.bottom + 4}px`;
    menu.style.left = `${Math.max(8, Math.min(box.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 8))}px`;
    (menu.querySelector("button") as HTMLButtonElement | null)?.focus();
    setTimeout(() => document.addEventListener("mousedown", function away(e) { if (!menu.contains(e.target as Node)) { menu.remove(); document.removeEventListener("mousedown", away); } }));
    menu.addEventListener("keydown", (e) => { if (e.key === "Escape") { menu.remove(); anchor.focus(); } });
  }

  function card(page: CanvasPage, block: BlockState): HTMLElement {
    const name = block.name ?? block.where;
    const others = state!.pages.filter((p) => p.id !== page.id);
    const size = h("span", { class: "hint cv-size" }, sizeWords(block));
    const grip = h("button", { type: "button", class: "card-grip cv-grip", title: "Resize: drag, or the arrow keys (a double-click fits its height)", "aria-label": `Resize ${name}`, "aria-valuetext": sizeWords(block) });
    const path = `/pages/${page.id}/blocks/${block.id}`;
    const stale = block.state === "outOfDate" && !!state?.running;
    const element = h(
      "article",
      {
        class: `cv-block ${block.missing ? "gone" : ""} ${stale ? "stale" : ""}`,
        role: "listitem",
        tabindex: 0,
        draggable: "true",
        "aria-label": `${name}, ${block.where}, row ${block.row}, column ${block.column}, ${sizeWords(block)}`,
        dataset: { block: block.id, cell: String(block.cell), row: String(block.row), column: String(block.column), w: String(block.w), h: block.h === null ? "" : String(block.h) },
        style: { gridColumn: `${block.column} / span ${block.w}`, gridRow: "1", minHeight: `${block.h === null ? 76 : Math.max(76, block.h * 14)}px` },
      },
      h(
        "div",
        { class: "cv-block-head" },
        // A Markdown or HTML cell's block: st.markdown or st.html on the page (text cells on the canvas).
        block.kind === "markdown" || block.kind === "html" ? h("span", { class: "wb-st-t", title: block.kind === "markdown" ? "A Markdown cell" : "An HTML cell", "aria-label": block.kind === "markdown" ? "A Markdown cell" : "An HTML cell" }, "T") : null,
        h("span", { class: "cv-block-name" }, name),
        h("span", { class: "spacer" }),
        others.length ? button("Move to another page", (e) => moveMenu(page, block, e.currentTarget as HTMLElement), { icon: "forward", iconOnly: true, class: "ghost" }) : null,
        button(`Take ${name} off the page`, () => void change(path, "DELETE"), { icon: "close", iconOnly: true, class: "ghost cv-remove" }),
      ),
      // A cell that is gone has no name: its title is already where it was.
      block.name === null ? null : h("div", { class: "hint cv-block-where", title: block.document }, block.where),
      partsOf(block) ? h("div", { class: "cv-block-parts" }, partsOf(block)) : null,
      block.missing ? h("div", { class: "cv-block-missing", role: "alert" }, block.missing) : null,
      block.problem ? h("div", { class: "cv-block-missing", role: "alert" }, `Not whole Python yet: ${block.problem}`) : null,
      size,
      grip,
    );
    // Move: drag the block, or the arrow keys on it.
    element.addEventListener("dragstart", (e) => {
      if ((e.target as HTMLElement).closest(".cv-grip")) return e.preventDefault();
      e.dataTransfer?.setData(BLOCK_DRAG, JSON.stringify({ block: block.id, w: block.w }));
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
      dragged = { w: block.w };
      element.classList.add("dragging");
    });
    element.addEventListener("dragend", () => {
      element.classList.remove("dragging");
      dragged = null;
      markDrop(null);
    });
    element.addEventListener("keydown", (e) => {
      if (e.target !== element) return;
      const rows = page.rows.length;
      if (e.key === "ArrowLeft") void change(path, "PATCH", { row: block.row, column: Math.max(1, block.column - 1) });
      else if (e.key === "ArrowRight") void change(path, "PATCH", { row: block.row, column: Math.min(COLUMNS - block.w + 1, block.column + 1) });
      else if (e.key === "ArrowUp") void change(path, "PATCH", block.row > 1 ? { row: block.row - 1, column: block.column } : { row: 1, column: block.column, insert: true });
      else if (e.key === "ArrowDown") void change(path, "PATCH", { row: Math.min(rows + 1, block.row + 1), column: block.column });
      else if (e.key === "Delete" || e.key === "Backspace") void change(path, "DELETE");
      else return;
      e.preventDefault();
      refocus = block.id;
    });
    // Resize: the corner, snapped to the grid's columns and to rows of 40 pixels.
    const show = (w: number, rows: number | null): void => {
      element.style.gridColumn = `${block.column} / span ${w}`;
      element.style.minHeight = `${rows === null ? 76 : Math.max(76, rows * 14)}px`;
      element.dataset.w = String(w);
      element.dataset.h = rows === null ? "" : String(rows);
      size.textContent = sizeWords({ w, h: rows });
    };
    const sized = (): { w: number; h: number | null } => ({ w: Number(element.dataset.w), h: element.dataset.h ? Number(element.dataset.h) : null });
    grip.addEventListener("pointerdown", (down) => {
      down.preventDefault();
      down.stopPropagation();
      grip.setPointerCapture(down.pointerId);
      const column = (board.clientWidth - GAP * (COLUMNS - 1) - 2 * 12) / COLUMNS;
      const box = element.getBoundingClientRect();
      const from = sized();
      element.classList.add("resizing");
      const move = (event: PointerEvent): void => {
        const w = Math.max(MIN_WIDTH, Math.min(COLUMNS - block.column + 1, Math.round((event.clientX - box.left + GAP) / (column + GAP))));
        const dy = event.clientY - down.clientY;
        // The height changes only once the pointer has clearly moved down or up: a sideways drag keeps it.
        const rows = Math.abs(dy) < 12 ? from.h : Math.max(1, Math.min(MAX_ROWS, (from.h ?? 6) + Math.round(dy / 14)));
        show(w, rows);
      };
      const up = (): void => {
        element.classList.remove("resizing");
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("pointerup", up);
        grip.removeEventListener("pointercancel", up);
        const now = sized();
        if (now.w !== block.w || now.h !== block.h) void change(path, "PATCH", { w: now.w, h: now.h });
      };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", up);
      grip.addEventListener("pointercancel", up);
    });
    grip.addEventListener("keydown", (e) => {
      const step: Record<string, [number, number]> = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] };
      const [dw, dh] = step[e.key] ?? [0, 0];
      if (!dw && !dh) return;
      e.preventDefault();
      e.stopPropagation();
      const w = Math.max(MIN_WIDTH, Math.min(COLUMNS - block.column + 1, block.w + dw));
      const rows = dh ? Math.max(1, Math.min(MAX_ROWS, (block.h ?? 6) + dh)) : block.h;
      refocus = `${block.id}:grip`;
      void change(path, "PATCH", { w, h: rows });
    });
    grip.addEventListener("dblclick", () => void change(path, "PATCH", { h: null }));
    return element;
  }

  let dragged: { w: number } | null = null; // the block being dragged in this window (a drag's data is not readable until the drop)

  function drawBoard(): void {
    const page = current();
    board.hidden = mode !== "edit";
    if (board.hidden) return;
    // The keyboard stays on the block it was on, however often the board is drawn again.
    const active = document.activeElement as HTMLElement | null;
    const held = active && board.contains(active) ? (active.closest(".cv-block") as HTMLElement | null) : null;
    if (!refocus && held?.dataset.block) refocus = `${held.dataset.block}${active!.classList.contains("cv-grip") ? ":grip" : ""}`;
    ghost = null;
    board.classList.toggle("empty", !page?.blocks.length);
    if (!page?.blocks.length) clear(board, h("p", { class: "cv-empty" }, "Drag a cell here: Python, Markdown or HTML"));
    else {
      const byId = new Map(page.blocks.map((b) => [b.id, b]));
      clear(board, ...page.rows.map((row) => h("div", { class: "cv-row" }, ...row.map((blockId) => card(page, byId.get(blockId)!)))));
    }
    if (refocus) {
      const [blockId, part] = refocus.split(":");
      const found = board.querySelector<HTMLElement>(`.cv-block[data-block="${blockId}"]`);
      (part ? found?.querySelector<HTMLElement>(".cv-grip") : found)?.focus();
      refocus = null;
    }
  }

  board.addEventListener("dragover", (e) => {
    const types = e.dataTransfer?.types ?? [];
    if (!types.includes(BLOCK_DRAG) && !types.includes(CELL_DRAG)) return;
    e.preventDefault();
    const w = types.includes(BLOCK_DRAG) ? (dragged?.w ?? DEFAULT_WIDTH) : DEFAULT_WIDTH;
    markDrop(dropAt(e.clientX, e.clientY, w), w);
  });
  board.addEventListener("dragleave", (e) => {
    if (!board.contains(e.relatedTarget as Node | null)) markDrop(null);
  });
  board.addEventListener("drop", (e) => {
    const link = draggedLink(e.dataTransfer);
    const raw = e.dataTransfer?.getData(BLOCK_DRAG);
    markDrop(null);
    if (link) {
      e.preventDefault();
      void place(link, current()?.blocks.length ? dropAt(e.clientX, e.clientY, DEFAULT_WIDTH) : undefined);
      return;
    }
    const page = current();
    if (!raw || !page) return;
    e.preventDefault();
    const what = JSON.parse(raw) as { block: string; w: number };
    const from = page.blocks.find((b) => b.id === what.block);
    if (!from) return;
    const drop = dropAt(e.clientX, e.clientY, from.w);
    if (drop.row === from.row && drop.column === from.column && !drop.insert) return;
    refocus = from.id;
    void change(`/pages/${page.id}/blocks/${from.id}`, "PATCH", drop);
  });
  // Paste: the copied cell's link, wherever the keyboard is on the canvas.
  element.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "v" && !(e.target as HTMLElement).closest("input")) {
      e.preventDefault();
      void paste();
    }
  });

  // ===== the live page =====

  function drawLive(): void {
    const page = current();
    live.hidden = mode !== "live";
    const address = mode === "live" && state?.running && page?.address ? frameAddress(page.address) : null;
    if (address !== null) {
      if (shown === address && frame) return; // the same page: Streamlit itself follows a run
      shown = address;
      frame = h("iframe", { class: "cv-frame", sandbox: FRAME_SANDBOX, title: page!.name, src: address, referrerpolicy: "no-referrer" }) as HTMLIFrameElement;
      clear(live, frame);
      return;
    }
    shown = null;
    frame = null;
    clear(live);
    // The app stopped (its window's kernel, the server) or the page is new: back to the blocks.
    if (mode === "live" && !busy) {
      mode = "edit";
      board.hidden = false;
      drawTop();
      drawBoard();
      live.hidden = true;
    }
  }

  function draw(): void {
    element.classList.toggle("live", mode === "live");
    drawTop();
    drawNotes();
    drawBoard();
    drawLive();
    host.drew();
  }

  draw();
  void ensure().catch((e: Error) => toast(e.message, "error"));

  return {
    element,
    tools,
    app: () => id,
    state: () => state,
    pages: () => savedPages(state ? state.pages : initial),
    mode: () => mode,
    busy: () => busy,
    play,
    edit,
    place,
    paste,
    exportApp,
    saveAs,
    saved: (path) => {
      kept = signature(state?.pages ?? initial);
      host.changed(false);
      if (id) void api(`${base()}`, "PUT", { document: path, title: host.title() }).then((next) => take(next as CanvasState), () => undefined);
    },
    noticed: (app) => {
      if (app === id) void call("", "GET").catch(() => undefined);
    },
    tablesChanged: () => {
      if (id && state?.running) void call("", "GET").catch(() => undefined);
    },
    focus: () => ((board.querySelector(".cv-block") as HTMLElement | null) ?? element).focus(),
    report: () => ({
      app: id,
      title: host.title(),
      path: host.path(),
      mode,
      page: pageId,
      running: state?.running ?? false,
      problem: state?.problem ?? null,
      pages: (state?.pages ?? []).map((p) => ({ id: p.id, name: p.name, out_of_date: p.out_of_date, problems: p.problems, rows: p.rows, blocks: p.blocks.map((b) => ({ id: b.id, document: b.document, cell: b.cell, row: b.row, column: b.column, w: b.w, h: b.h, name: b.name, makes: b.makes, reads: [...b.tables, ...b.reads], state: b.state, missing: b.missing })) })),
    }),
    close: () => {
      gone = true;
      if (id) void api(`/streamlit/apps/${id}`, "DELETE").catch(() => undefined);
    },
  };
}
