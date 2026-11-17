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
 *   [CONTROL] a block whose maker is not on the page reads that maker's contract default (`# Makes:
 *             region: str = "All"`), said quietly on the block; a contract its code breaks is red.
 *             Test this page runs Streamlit's AppTest with each controller's values; a block that
 *             failed turns red with the value that broke it. A view that filters, groups or joins a
 *             table shows its thin-cell hint: Move to data.ipynb (the window changes its documents)
 *   [APP]     App mode (2026-11-15): a click selects a block (its outline violet) and Properties shows it;
 *             its wiring is drawn over the board (violet arrows from it to each block that reads what
 *             it makes). Edit's tools: undo, redo, align, duplicate, zoom. Play's: Desktop, Tablet or
 *             Phone, and Light or Dark for the app only. The page settings (title, icon, layout, logo,
 *             theme colours) are the app's and saved in its file
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
import { history, pageTabs, resizeGrip } from "./canvasKit";
import { button, clear, h, icon, showMenu, toast } from "./dom";
import { kindIcon, kindOfPath } from "./kindColours";
import { type PromptOptions, promptInstall } from "./missingPackages";
import { effectiveTheme } from "./theme";
import { FRAME_SANDBOX } from "./workbenchHtml";
import { menuButton } from "./workbenchMenu";
import { type AppProblem, type AppSettings, type BlockState, type CanvasPage, type CanvasState, type CellLink, CELL_DRAG, copiedCell, draggedLink, type ExportResult, frameAddress, type LocalNotes, type MovePlan, type PageTest, partsOf, problemText, type SaveAsResult, type SavedPage, savedPages, type SessionRow } from "./workbenchStreamlit";

/** What Test this page answers: its counts and each block's failures, or the Python's problem. */
export type TestResult = (PageTest & { page: string; name: string; failures: Record<string, { case: string; error: string }[]> }) | { page: string; problem: AppProblem };

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
  /** A thin cell's move: its model work into a named cell of data.ipynb, its cell left with one read
   *  (the window changes its open documents, opening them when they are not). */
  moveToData: (plan: MovePlan) => Promise<void>;
  /** Lineage: the overlay for a block of a page (its cell back to the data, with the values). */
  lineage?: (page: string, block: string) => void;
  /** A block was selected (null: none): Properties follows. */
  selected?: (block: string | null) => void;
  /** A starter dropped on the board (from App mode's Starters panel): written into a cell, then placed. */
  starter?: (name: string, where: { row: number; column: number; insert?: boolean } | undefined) => void;
}

export type Device = "desktop" | "tablet" | "phone";
export type Align = "left" | "centre" | "right" | "full";
/** A starter's drag (App mode's Starters panel): its name. */
export const STARTER_DRAG = "application/x-swissarmybench-starter";

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
  /** Test this page (the one in front, or `page`): each controller's values tried; failures on the blocks. */
  test: (page?: string) => Promise<TestResult | null>;
  /** A block's thin-cell move to data.ipynb (its hint's button). */
  moveToData: (block: string) => Promise<MovePlan | null>;
  /** The file was saved (at this path): the server knows, and these pages are the saved ones. */
  saved: (path: string) => void;
  noticed: (app: string) => void;
  tablesChanged: () => void;
  focus: () => void;
  /** What it shows, for the agent. */
  report: () => unknown;
  close: () => void;
  // ----- App mode
  /** The selected block (null: none, so Properties shows the page settings). */
  selected: () => BlockState | null;
  select: (block: string | null) => void;
  /** The page in front. */
  page: () => CanvasPage | null;
  /** The blocks on the page that read what this block makes. */
  feeds: (block: string) => BlockState[];
  /** Move or size a block of the page in front. */
  changeBlock: (block: string, body: Record<string, unknown>) => Promise<boolean>;
  settings: () => AppSettings;
  setSettings: (changed: Record<string, unknown>) => Promise<boolean>;
  /** What the live page's session holds (the State panel). */
  session: () => Promise<SessionRow[]>;
  /** Start the live page again with a fresh session. */
  resetState: () => void;
  undo: () => Promise<boolean>;
  redo: () => Promise<boolean>;
  duplicate: (block?: string) => Promise<boolean>;
  align: (how: Align, block?: string) => Promise<boolean>;
  /** The board's zoom, in per cent (50 to 150). */
  zoom: (percent?: number) => number;
  /** Play's preview: the device's width, and Light or Dark for the app only (null: as the Workbench). */
  preview: (device?: Device, theme?: "light" | "dark" | null) => { device: Device; theme: "light" | "dark" | null };
}

export const DEFAULT_SETTINGS: AppSettings = { title: "", icon: "", layout: "wide", logo: "", colours: {} };

/** The pages and the page settings as the file keeps them: a change to either is unsaved. */
function signatureOf(pages: (CanvasPage | SavedPage)[], settings: AppSettings): string {
  return JSON.stringify({ pages: savedPages(pages).map(({ name, blocks }) => ({ name, blocks: blocks.map(({ id: _, ...rest }) => rest) })), settings });
}

export function canvasView(initial: SavedPage[], host: CanvasHost, initialSettings: AppSettings = DEFAULT_SETTINGS): CanvasView {
  let state: CanvasState | null = null;
  let selectedId: string | null = null;
  let zoomed = 100;
  let device: Device = "desktop";
  let previewTheme: "light" | "dark" | null = null;
  let freshSession = 0; // Reset state: the live page is opened again with a new session
  const changes = history<SavedPage[]>(); // Undo and Redo (canvasKit.ts, shared with the Excel canvas)
  let id: string | null = null;
  let opening: Promise<string> | null = null;
  let pageId: string | null = null;
  let mode: "edit" | "live" = "edit";
  let busy = false;
  let testing: string | null = null; // the page Test this page is running on
  let gone = false;
  let kept = signatureOf(initial, initialSettings);
  let frame: HTMLIFrameElement | null = null;
  let shown: string | null = null;
  let refocus: string | null = null; // the block (or its grip) the keyboard was on before a change

  const top = h("div", { class: "cv-top" });
  const tools = h("span", { class: "cv-tools" });
  const notes = h("div", { class: "cv-notes" });
  const board = h("div", { class: "cv-board", role: "list", "aria-label": "Blocks" });
  const live = h("div", { class: "cv-live" });
  const element = h("div", { class: "cv", tabindex: -1 }, top, notes, board, live);

  const signature = (pages: (CanvasPage | SavedPage)[]): string => signatureOf(pages, state?.settings ?? initialSettings);
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
      opening = api<CanvasState>("/streamlit/apps", "POST", { canvas: true, title: host.title(), document: host.path(), window: host.window, pages, settings: state?.settings ?? initialSettings })
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

  /** A change of the layout: sent, and the state that comes back drawn. Undo can take it back. */
  async function change(path: string, method: string, body?: unknown): Promise<(CanvasState & { page?: string; block?: string }) | null> {
    const before = state ? savedPages(state.pages) : null;
    try {
      const done = await call(path, method, body);
      if (before) changes.push(before);
      return done;
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
      // Streamlit missing from the app's Python: the prompt in the user's face; installed, Play again.
      if (ran.problem?.kind === "missing") void promptInstall(ran.problem, installing(() => void play(page)));
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

  /** Into the app's own Python (its document's environment), through the app's install; then `again`. */
  function installing(again: () => void): PromptOptions {
    return {
      install: async () => {
        await ensure();
        const done = await api<{ ok: boolean; output: string }>(`${base()}/install`, "POST");
        if (!done.ok) throw new Error(done.output.trim().split("\n").slice(-6).join("\n") || "The install failed.");
      },
      then: again,
    };
  }

  /** The note's Install: the prompt again, asked for (after Not now). */
  function install(): void {
    const problem = state?.problem;
    if (problem?.kind === "missing") void promptInstall(problem, { ...installing(() => void play()), force: true });
  }

  /** The user's word before an export writes, when a connection it names runs only on this computer. */
  async function goesAnyway(route: string): Promise<boolean> {
    const looked = await api<LocalNotes>(`${base()}/${route}`, "POST", { check: true });
    if (!looked.local_words || confirm(`${looked.local_words}\n\nExport it anyway?`)) return true;
    toast("Nothing was exported.");
    return false;
  }

  async function exportApp(folder?: string, agent = false): Promise<ExportResult | null> {
    const chosen = folder ?? (await host.chooseFolder());
    if (!chosen) return null;
    await ensure();
    await host.settle();
    if (!agent && !(await goesAnyway("export"))) return null;
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
    if (!agent && !(await goesAnyway("save-as"))) return null;
    const done = await (agent ? agentApi : api)<SaveAsResult>(`${base()}/save-as`, "POST", { path: chosen });
    toast(done.path, done.problems.length ? "error" : "info");
    for (const problem of done.problems) toast(problem, "error");
    return done;
  }

  // ===== Test this page, and a thin cell's move (domain/controllers.py, domain/thin_cells.py) =====

  async function test(page?: string): Promise<TestResult | null> {
    const target = page ?? pageId;
    if (testing || !target) return null;
    testing = target;
    draw();
    try {
      await host.settle(); // the linked cells as they are typed, saved or not
      await ensure();
      const done = await api<TestResult>(`${base()}/pages/${encodeURIComponent(target)}/test`, "POST");
      if ("problem" in done && done.problem && typeof done.problem === "object") {
        if (done.problem.kind === "missing") void promptInstall(done.problem, installing(() => void test(target)));
        else toast(problemText(done.problem), "error");
      }
      else if ("tries" in done) {
        const blocks = Object.keys(done.failures).length + (done.outside.length ? 1 : 0);
        const said = done.problem ?? (blocks ? `${blocks} ${blocks === 1 ? "block" : "blocks"} failed` : "Every block ran");
        const untried = done.untried.length ? ` · ${done.untried.length} not tried` : "";
        toast(`Tested ${done.tries} ${done.tries === 1 ? "value" : "values"}: ${said}${untried}`, blocks || done.problem ? "error" : "info");
      }
      await call("", "GET").catch(() => undefined);
      return done;
    } catch (e) {
      toast((e as Error).message, "error");
      return null;
    } finally {
      testing = null;
      draw();
    }
  }

  async function moveToData(blockId: string): Promise<MovePlan | null> {
    const page = current();
    if (!page) return null;
    await host.settle();
    await ensure();
    const plan = await api<MovePlan>(`${base()}/pages/${encodeURIComponent(page.id)}/blocks/${encodeURIComponent(blockId)}/move-to-data`);
    await host.moveToData(plan);
    await host.settle();
    await call("", "GET").catch(() => undefined);
    return plan;
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

  function drawTop(): void {
    const pages = state?.pages ?? [];
    const page = current();
    // The pages as tabs (canvasKit.ts): a cell dropped on a page's tab goes to the end of that page.
    const tabs = pageTabs({
      pages,
      current: pageId,
      label: "Pages",
      noun: "page",
      select: (p) => {
        pageId = p.id;
        draw();
      },
      rename: (p, name) => void change(`/pages/${p.id}`, "PATCH", { name }),
      holds: (p) => p.blocks.length > 0,
      remove: (p) => void change(`/pages/${p.id}`, "DELETE"),
      add: () =>
        void change("/pages", "POST", {}).then((next) => {
          if (next?.page) {
            pageId = next.page;
            draw();
          }
        }),
      decorate: (tab, p) => {
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
      },
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
    const testButton = button(testing ? "Testing…" : "Test this page", () => void test(), { icon: "check", class: "cv-test", title: "Run the page with each filter's values (Streamlit's own test runner)" });
    testButton.disabled = !!testing || busy || !page?.blocks.length;
    clear(top, tabs);
    clear(tools, modes, testButton, ...(mode === "live" ? previewTools() : editTools()), exportButton, saveAsButton);
  }

  // ===== App mode: Edit's tools, Play's preview =====

  function editTools(): HTMLElement[] {
    const page = current();
    const undoButton = button("Undo", () => void undo(), { icon: "undo", iconOnly: true, class: "ghost cv-undo", title: "Undo (Ctrl+Z)" });
    const redoButton = button("Redo", () => void redo(), { icon: "redo", iconOnly: true, class: "ghost cv-redo", title: "Redo (Ctrl+Shift+Z)" });
    undoButton.disabled = !changes.canUndo();
    redoButton.disabled = !changes.canRedo();
    const alignButton = h("button", { type: "button", class: "btn ghost cv-align", "aria-label": "Align", title: selectedId ? "Align the selected block" : "Select a block to align it" }, icon("align"), icon("down")) as HTMLButtonElement;
    alignButton.disabled = !selectedId;
    menuButton(alignButton, "Align", () => [
      { label: "Left edge", run: () => void align("left") },
      { label: "Centre", run: () => void align("centre") },
      { label: "Right edge", run: () => void align("right") },
      { label: "Full width", run: () => void align("full") },
    ]);
    const duplicateButton = button("Duplicate", () => void duplicate(), { icon: "duplicate", iconOnly: true, class: "ghost cv-duplicate", title: selectedId ? "Duplicate the selected block" : "Select a block to duplicate it" });
    duplicateButton.disabled = !selectedId || !page;
    const zoomOut = button("Zoom out", () => zoom(zoomed - 10), { icon: "minus", iconOnly: true, class: "ghost" });
    const zoomIn = button("Zoom in", () => zoom(zoomed + 10), { icon: "plus", iconOnly: true, class: "ghost" });
    const percent = h("button", { type: "button", class: "btn ghost cv-zoom-level", title: "Zoom: back to 100%", onclick: () => zoom(100) }, `${zoomed}%`);
    return [
      h("span", { class: "cv-group", role: "group", "aria-label": "Undo and redo" }, undoButton, redoButton),
      h("span", { class: "cv-group", role: "group", "aria-label": "Arrange" }, alignButton, duplicateButton),
      h("span", { class: "cv-group cv-zoom", role: "group", "aria-label": "Zoom" }, zoomOut, percent, zoomIn),
    ];
  }

  function previewTools(): HTMLElement[] {
    const pick = (label: string, ic: string, on: boolean, run: () => void): HTMLButtonElement => button(label, run, { icon: ic, pressed: on, class: `cv-preview-${label.toLowerCase()}` });
    const devices = h(
      "span",
      { class: "cv-mode cv-devices", role: "group", "aria-label": "Preview size" },
      pick("Desktop", "desktop", device === "desktop", () => preview("desktop")),
      pick("Tablet", "tablet", device === "tablet", () => preview("tablet")),
      pick("Phone", "phone", device === "phone", () => preview("phone")),
    );
    const shown = previewTheme ?? (effectiveTheme().endsWith("dark") ? "dark" : "light");
    const themes = h(
      "span",
      { class: "cv-mode cv-themes", role: "group", "aria-label": "The app's theme" },
      pick("Light", "sun", shown === "light", () => preview(undefined, "light")),
      pick("Dark", "moon", shown === "dark", () => preview(undefined, "dark")),
    );
    return [devices, themes];
  }

  // ===== App mode: selection, wiring, undo, align, duplicate, zoom, settings, state =====

  function select(block: string | null, redraw = true): void {
    if (selectedId === block) return;
    selectedId = block;
    if (redraw) {
      refocus = block;
      drawTop();
      drawBoard();
    } else {
      for (const el of board.querySelectorAll(".cv-block")) {
        const on = (el as HTMLElement).dataset.block === block;
        el.classList.toggle("selected", on);
        el.setAttribute("aria-selected", String(on));
      }
      drawTop();
      drawWires();
    }
    host.selected?.(block);
  }

  function feeds(block: string): BlockState[] {
    const page = current();
    const from = page?.blocks.find((b) => b.id === block);
    if (!page || !from || !from.makes.length) return [];
    return page.blocks.filter((b) => b.id !== block && [...b.reads, ...b.tables].some((name) => from.makes.includes(name)));
  }

  /** The selected block's wiring: a violet arrow to each block that reads what it makes, the names it
   *  makes in a chip under it, and its width. */
  function drawWires(): void {
    board.querySelector(".cv-wires")?.remove();
    for (const old of board.querySelectorAll(".cv-wire-label")) old.remove();
    const page = current();
    const from = page?.blocks.find((b) => b.id === selectedId);
    if (!from || mode !== "edit") return;
    const source = board.querySelector<HTMLElement>(`.cv-block[data-block="${from.id}"]`);
    if (!source) return;
    const base = board.getBoundingClientRect();
    const scale = zoomed / 100;
    const at = (el: HTMLElement): DOMRect => el.getBoundingClientRect();
    const x = (v: number): number => (v - base.left) / scale + board.scrollLeft;
    const y = (v: number): number => (v - base.top) / scale + board.scrollTop;
    const s = at(source);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "cv-wires");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("width", String(board.scrollWidth));
    svg.setAttribute("height", String(board.scrollHeight));
    svg.innerHTML = '<defs><marker id="cv-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z"/></marker></defs>';
    const sx = x(s.left + s.width / 2);
    const sy = y(s.bottom);
    for (const target of feeds(from.id)) {
      const el = board.querySelector<HTMLElement>(`.cv-block[data-block="${target.id}"]`);
      if (!el) continue;
      const t = at(el);
      const tx = x(t.left + t.width / 2);
      // A block in the same row (or above) is reached from below, the arrow pointing up into it.
      const beside = t.top < s.bottom - 2;
      const ty = beside ? y(t.bottom) + 4 : y(t.top) - 2;
      const bend = beside ? 34 : Math.max(30, Math.abs(ty - sy) / 2);
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", `M${sx},${sy} C${sx},${sy + bend} ${tx},${beside ? ty + bend : ty - bend} ${tx},${ty}`);
      path.setAttribute("marker-end", "url(#cv-arrow)");
      path.dataset.to = target.id;
      svg.append(path);
    }
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", String(sx));
    dot.setAttribute("cy", String(sy));
    dot.setAttribute("r", "4");
    svg.append(dot);
    board.append(svg);
    const label = h(
      "div",
      { class: "cv-wire-label", style: { left: `${x(s.left)}px`, top: `${y(s.bottom) + 6}px` } },
      h("span", { class: "cv-wire-size" }, `${from.w} of ${COLUMNS}`),
      ...from.makes.map((name) => h("span", { class: "cv-wire-name mono" }, name)),
    );
    board.append(label);
  }

  async function replacePages(pages: SavedPage[]): Promise<boolean> {
    if (!id) return false;
    try {
      await call("", "PUT", { pages });
      return true;
    } catch (e) {
      toast((e as Error).message, "error");
      return false;
    }
  }

  async function undo(): Promise<boolean> {
    const back = state ? changes.undo(savedPages(state.pages)) : undefined;
    return back ? replacePages(back) : false;
  }

  async function redo(): Promise<boolean> {
    const again = state ? changes.redo(savedPages(state.pages)) : undefined;
    return again ? replacePages(again) : false;
  }

  const blockOf = (block?: string): { page: CanvasPage; block: BlockState } => {
    const page = current();
    const found = page?.blocks.find((b) => b.id === (block ?? selectedId));
    if (!page || !found) throw new Error("Select a block first.");
    return { page, block: found };
  };

  async function duplicate(block?: string): Promise<boolean> {
    const { page, block: from } = blockOf(block);
    const done = await change(`/pages/${page.id}/blocks`, "POST", { document: from.document, cell: from.cell, w: from.w });
    if (!done) return false;
    if (from.h !== null && done.block) await call(`/pages/${page.id}/blocks/${done.block}`, "PATCH", { h: from.h });
    if (done.block) select(done.block);
    return true;
  }

  async function align(how: Align, block?: string): Promise<boolean> {
    const { page, block: b } = blockOf(block);
    const place = how === "full" ? { column: 1, w: COLUMNS } : { column: how === "left" ? 1 : how === "right" ? COLUMNS - b.w + 1 : Math.floor((COLUMNS - b.w) / 2) + 1 };
    if (place.column === b.column && (how !== "full" || b.w === COLUMNS)) return true;
    refocus = b.id;
    if (how === "full") return !!(await change(`/pages/${page.id}/blocks/${b.id}`, "PATCH", { row: b.row, column: 1 })) && !!(await change(`/pages/${page.id}/blocks/${b.id}`, "PATCH", { w: COLUMNS }));
    return !!(await change(`/pages/${page.id}/blocks/${b.id}`, "PATCH", { row: b.row, column: place.column }));
  }

  function zoom(percent?: number): number {
    if (percent !== undefined) {
      zoomed = Math.max(50, Math.min(150, Math.round(percent / 10) * 10));
      drawTop();
      drawBoard();
    }
    return zoomed;
  }

  function preview(next?: Device, theme?: "light" | "dark" | null): { device: Device; theme: "light" | "dark" | null } {
    if (next) device = next;
    if (theme !== undefined) previewTheme = theme;
    if (next || theme !== undefined) {
      shown = null; // the frame is opened again in its new size or theme
      drawTop();
      drawLive();
    }
    return { device, theme: previewTheme };
  }

  async function setSettings(changed: Record<string, unknown>): Promise<boolean> {
    try {
      await call("/settings", "PUT", changed);
      return true;
    } catch (e) {
      toast((e as Error).message, "error");
      return false;
    }
  }

  // ===== what needs the user: the app's problem, the page's problems =====

  function drawNotes(): void {
    const page = current();
    const problem = state?.problem ?? null;
    const said = mode === "edit" ? (page?.problems ?? []).filter((p) => !page!.blocks.some((b) => b.missing && p.includes(b.missing))) : [];
    clear(
      notes,
      problem ? h("p", { class: "cv-problem", role: "alert" }, problemText(problem), problem.kind === "missing" ? button(`Install ${problem.packages.join(", ")}`, () => install(), { class: "ghost cv-install", icon: "import", title: problem.command }) : null) : null,
      ...said.map((p) => h("p", { class: "cv-problem", role: "alert" }, p)),
      // The page's last test: an error outside every block, or the test itself not finishing.
      ...(mode === "edit" ? [...(page?.tested?.outside ?? []).map((f) => `${f.case}: ${f.error}`), ...(page?.tested?.problem ? [page.tested.problem] : [])] : []).map((p) => h("p", { class: "cv-problem cv-test-problem", role: "alert" }, p)),
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
      ...state!.pages.filter((p) => p.id !== page.id).map((p) => h("button", { type: "button", role: "menuitem", class: "km-app", onclick: () => { menu.remove(); void change(`/pages/${page.id}/blocks/${block.id}`, "PATCH", { page: p.id }); } }, `Move to ${p.name}`)),
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
        // A left edge in its source document's kind colour (notebook blue, script green); red when the page's test failed on it.
        class: `cv-block conn-block km-${kindOfPath(block.document) ?? "notebook"} ${block.missing ? "gone" : ""} ${stale ? "stale" : ""} ${block.failures?.length ? "failed" : ""} ${block.id === selectedId ? "selected" : ""}`,
        "aria-selected": String(block.id === selectedId),
        role: "listitem",
        tabindex: 0,
        draggable: "true",
        "aria-label": `${name}, ${block.where}, row ${block.row}, column ${block.column}, ${sizeWords(block)}`,
        ...(block.connections?.length ? { "data-connections": block.connections.join("|") } : {}),
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
      block.name === null ? null : h("div", { class: "hint cv-block-where", title: block.document }, icon(kindIcon(kindOfPath(block.document), block.document)), h("span", {}, block.where)),
      partsOf(block) ? h("div", { class: "cv-block-parts" }, partsOf(block)) : null,
      block.missing ? h("div", { class: "cv-block-missing", role: "alert" }, block.missing) : null,
      block.problem ? h("div", { class: "cv-block-missing", role: "alert" }, `Not whole Python yet: ${block.problem}`) : null,
      // Its controllers' contract (domain/controllers.py): a default read for a maker that is not on
      // the page (quiet), a contract its code breaks, and what the last test found (red).
      ...(block.defaults ?? []).map((d) => h("div", { class: "hint cv-block-default", title: d.maker }, `${d.name} = ${d.value}`, h("span", { class: "cv-block-default-from" }, ` · ${d.maker.split(", ")[0]} is not on this page`))),
      ...(block.contract ?? []).map((p) => h("div", { class: "cv-block-missing", role: "alert" }, p)),
      ...(block.failures ?? []).map((f) => h("div", { class: "cv-block-missing cv-block-failed", role: "alert" }, `${f.case}: ${f.error}`)),
      block.thin ? h("div", { class: "cv-block-thin" }, h("span", { class: "hint" }, block.thin.words), button("Move to data.ipynb", () => void moveToData(block.id).catch((e: Error) => toast(e.message, "error")), { icon: "notebook", class: "ghost cv-move-data", title: "Move these lines into a named cell of data.ipynb; one line here reads them back" })) : null,
      size,
      grip,
    );
    // Right-click: the block's lineage, back through every cell to the data.
    element.addEventListener("contextmenu", (e) => {
      if (!host.lineage || !id) return;
      e.preventDefault();
      const gone = block.missing ? "Its cell is gone" : undefined;
      showMenu(e.clientX, e.clientY, name, [["lineage", "Lineage", () => host.lineage!(page.id, block.id), gone]]);
    });
    // A click selects it: Properties shows it, its wiring is drawn.
    element.addEventListener("click", (e) => {
      if ((e.target as HTMLElement).closest("button")) return;
      select(block.id);
    });
    element.addEventListener("keydown", (e) => {
      if (e.target === element && (e.key === "Enter" || e.key === " ")) {
        e.preventDefault();
        select(block.id);
      }
    });
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
    // (canvasKit.ts's grip: the pointer's distance from where it went down.)
    let column = 0;
    let box = element.getBoundingClientRect();
    let from = sized();
    let startX = 0;
    resizeGrip(
      grip,
      (down) => {
        startX = down.clientX;
        column = (board.clientWidth - GAP * (COLUMNS - 1) - 2 * 12) / COLUMNS;
        box = element.getBoundingClientRect();
        from = sized();
        element.classList.add("resizing");
      },
      (dx, dy) => {
        const w = Math.max(MIN_WIDTH, Math.min(COLUMNS - block.column + 1, Math.round((startX + dx - box.left + GAP) / (column + GAP))));
        // The height changes only once the pointer has clearly moved down or up: a sideways drag keeps it.
        const rows = Math.abs(dy) < 12 ? from.h : Math.max(1, Math.min(MAX_ROWS, (from.h ?? 6) + Math.round(dy / 14)));
        show(w, rows);
      },
      () => {
        element.classList.remove("resizing");
        const now = sized();
        if (now.w !== block.w || now.h !== block.h) void change(path, "PATCH", { w: now.w, h: now.h });
      },
    );
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
    board.style.setProperty("zoom", String(zoomed / 100));
    drawWires();
    if (refocus) {
      const [blockId, part] = refocus.split(":");
      const found = board.querySelector<HTMLElement>(`.cv-block[data-block="${blockId}"]`);
      (part ? found?.querySelector<HTMLElement>(".cv-grip") : found)?.focus();
      refocus = null;
    }
  }

  board.addEventListener("dragover", (e) => {
    const types = e.dataTransfer?.types ?? [];
    if (!types.includes(BLOCK_DRAG) && !types.includes(CELL_DRAG) && !types.includes(STARTER_DRAG)) return;
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
    const starter = e.dataTransfer?.getData(STARTER_DRAG);
    markDrop(null);
    if (starter && host.starter) {
      e.preventDefault();
      host.starter(starter, current()?.blocks.length ? dropAt(e.clientX, e.clientY, DEFAULT_WIDTH) : undefined);
      return;
    }
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
  // A click on the board itself (not a block) puts the selection away: Properties shows the page settings.
  board.addEventListener("click", (e) => {
    if (!(e.target as HTMLElement).closest(".cv-block") && selectedId) select(null);
  });
  element.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && selectedId && !(e.target as HTMLElement).closest("input, textarea, select")) select(null);
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "z" && !(e.target as HTMLElement).closest("input, textarea")) {
      e.preventDefault();
      void (e.shiftKey ? redo() : undo());
    }
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
    const address = mode === "live" && state?.running && page?.address ? `${frameAddress(page.address, previewTheme)}${freshSession ? `&session=${freshSession}` : ""}` : null;
    live.dataset.device = device;
    if (address !== null) {
      if (shown === address && frame) return; // the same page: Streamlit itself follows a run
      shown = address;
      frame = h("iframe", { class: "cv-frame", sandbox: FRAME_SANDBOX, title: page!.name, src: address, referrerpolicy: "no-referrer" }) as HTMLIFrameElement;
      clear(live, h("div", { class: `cv-device cv-${device}` }, frame));
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
    test,
    moveToData,
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
      testing,
      pages: (state?.pages ?? []).map((p) => ({ id: p.id, name: p.name, out_of_date: p.out_of_date, problems: p.problems, rows: p.rows, check: p.check, tested: p.tested, blocks: p.blocks.map((b) => ({ id: b.id, document: b.document, cell: b.cell, row: b.row, column: b.column, w: b.w, h: b.h, name: b.name, makes: b.makes, reads: [...b.tables, ...b.reads], state: b.state, missing: b.missing, role: b.controller?.role ?? null, defaults: b.defaults, contract: b.contract, thin: b.thin, failures: b.failures })) })),
    }),
    close: () => {
      gone = true;
      if (id) void api(`/streamlit/apps/${id}`, "DELETE").catch(() => undefined);
    },
    selected: () => current()?.blocks.find((b) => b.id === selectedId) ?? null,
    select: (block) => select(block),
    page: current,
    feeds,
    changeBlock: async (block, body) => {
      const page = current();
      if (!page) return false;
      refocus = block;
      return !!(await change(`/pages/${page.id}/blocks/${block}`, "PATCH", body));
    },
    settings: () => state?.settings ?? initialSettings,
    setSettings,
    session: async () => {
      if (!id) return [];
      return (await api<{ state: SessionRow[] }>(`${base()}/session`)).state;
    },
    resetState: () => {
      freshSession += 1;
      shown = null;
      drawLive();
    },
    undo,
    redo,
    duplicate,
    align,
    zoom,
    preview,
  };
}
