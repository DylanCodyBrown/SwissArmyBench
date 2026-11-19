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
import { pageTabs, resizeGrip } from "./canvasKit";
import type { CodePlan } from "./canvasPane";
import { equalGaps, guides, inBand, type Rect, sameSize } from "./canvasSnap";
import { button, clear, h, icon, type MenuItem, showMenu, toast } from "./dom";
import { kindIcon, kindOfPath } from "./kindColours";
import { busy as gate, markBusy } from "./loading";
import { type PromptOptions, promptInstall } from "./missingPackages";
import { effectiveTheme } from "./theme";
import { FRAME_SANDBOX } from "./workbenchHtml";
import { menuButton } from "./workbenchMenu";
import { type AppProblem, type AppSettings, type BlockState, type CanvasPage, type CanvasState, type CellLink, type ContainerState, CELL_DRAG, copiedCell, draggedLink, type ExportResult, frameAddress, type LocalNotes, type MovePlan, type PageTest, partsOf, problemText, type SaveAsResult, type SavedPage, savedPages, type SessionRow } from "./workbenchStreamlit";
import { errorHere, errorNote, problemsHere } from "./errorNote";

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
  /** A change to a cell's code made again or taken back (Undo, Redo): in the open document, like typing. */
  applyCode?: (plan: CodePlan) => Promise<boolean>;
  /** A starter dropped on the board (from App mode's Starters panel): written into a cell, then placed. */
  starter?: (name: string, where: Where | undefined) => void;
  /** A Toolbox element dropped on the board: its cell written into the app notebook, then placed. */
  toolbox?: (element: string, where: Where | undefined) => Promise<unknown>;
}

export type Device = "desktop" | "tablet" | "phone";
export type Align = "left" | "centre" | "right" | "full";
/** A starter's drag (App mode's Starters panel): its name. */
export const STARTER_DRAG = "application/x-swissarmybench-starter";
/** A Toolbox item's drag: {"id", "kind": "element" | "container"}; a container's carries the second type too
 *  (a drag's data is not readable until the drop: its types are). */
export const TOOLBOX_DRAG = "application/x-swissarmybench-toolbox";
export const TOOLBOX_CONTAINER = "application/x-swissarmybench-toolbox-container";
/** Where something is put on a page: a place in a grid, and the container and slot whose grid it is. */
export interface Where {
  row?: number;
  column?: number;
  insert?: boolean;
  parent?: string | null;
  slot?: number;
}
export type Arrange = "left" | "right" | "centre" | "top" | "bottom" | "same_width" | "same_height" | "distribute" | "reset";
export type DesignWidth = "wide" | "centered" | "phone";

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
  place: (link: CellLink, where?: Where) => Promise<boolean>;
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
  /** The property pane changed a cell's code: Undo takes it back with the layout's changes. */
  codeChanged: (plan: CodePlan) => void;
  /** Every selected block (the first is the one Properties shows). */
  selection: () => BlockState[];
  /** Every selected item's id (blocks and containers), the first the one Properties shows. */
  selectedIds: () => string[];
  /** The selected container, when the first selected is one. */
  selectedContainer: () => ContainerState | null;
  selectMany: (blocks: string[]) => void;
  /** Arrange the selection (or `blocks`) as one change; "reset": Reset layout. */
  arrange: (how: Arrange, blocks?: string[]) => Promise<boolean>;
  /** A Toolbox item put on the page (a click in the Toolbox, the agent's canvas_add). */
  addTool: (tool: string, kind: "element" | "container", where?: Where) => Promise<unknown>;
  /** What the design surface shows: snaplines, the ruler, sample rows. */
  view: (next?: { snaplines?: boolean; rulers?: boolean; sampleRows?: boolean }) => { snaplines: boolean; rulers: boolean; sampleRows: boolean; width: DesignWidth };
  designWidth: (width?: DesignWidth) => Promise<DesignWidth>;
  removeSelected: () => Promise<void>;
  /** Another page in front, a block of it selected. */
  showPage: (page: string, block?: string) => void;
  /** Move or size several blocks of the page in front, as one change. */
  changeBlocks: (blocks: string[], body: Record<string, unknown>) => Promise<boolean>;
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
  return JSON.stringify({ pages: savedPages(pages).map(({ name, blocks, containers }) => ({ name, blocks: blocks.map(({ id: _, ...rest }) => rest), ...(containers ? { containers } : {}) })), settings });
}

export function canvasView(initial: SavedPage[], host: CanvasHost, initialSettings: AppSettings = DEFAULT_SETTINGS): CanvasView {
  let state: CanvasState | null = null;
  let selectedId: string | null = null; // the first selected: the one Properties shows
  let selectedIds: string[] = [];
  let copied: string[] = []; // Ctrl+C: the blocks Ctrl+V duplicates
  let snaplines = true;
  let rulers = false;
  let sampleRows = false;
  let designWidth: DesignWidth = "wide";
  let zoomed = 100;
  let device: Device = "desktop";
  let previewTheme: "light" | "dark" | null = null;
  let freshSession = 0; // Reset state: the live page is opened again with a new session
  // Undo and Redo, one history for everything the designer does: a layout change keeps the pages as they
  // were; a change to a cell's code (the property pane's) keeps its plan, taken back in the document.
  type Step = { pages: SavedPage[] } | { code: CodePlan };
  const undos: Step[] = [];
  const redos: Step[] = [];
  const changes = {
    push: (step: Step): void => {
      undos.push(step);
      if (undos.length > 50) undos.shift();
      redos.length = 0;
    },
    canUndo: (): boolean => undos.length > 0,
    canRedo: (): boolean => redos.length > 0,
  };
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
    const front = next.pages.find((p) => p.id === pageId);
    selectedIds = selectedIds.filter((itemId) => !!front && (front.blocks.some((b) => b.id === itemId) || front.containers.some((c) => c.id === itemId)));
    selectedId = selectedIds[0] ?? null;
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
      if (before) changes.push({ pages: before });
      return done;
    } catch (e) {
      errorHere(e);
      return null;
    }
  }

  // ===== Play, Edit =====

  async function play(page?: string): Promise<CanvasState | null> {
    if (busy) return state;
    if (page && state?.pages.some((p) => p.id === page)) pageId = page;
    busy = true;
    draw();
    const name = current()?.name ?? "the page";
    try {
      // The canvas is gated while Play starts (loading.ts): no block moves under a page being started.
      const ran = await gate(mode === "live" ? live : board, `Starting ${name}…`, (async () => {
        await host.settle(); // the linked cells as they are typed, saved or not
        return call("/run", "POST");
      })(), { errorIn: false });
      if (ran.problem?.kind === "failed") errorHere(problemText(ran.problem));
      // Streamlit missing from the app's Python: the prompt in the user's face; installed, Play again.
      if (ran.problem?.kind === "missing") void promptInstall(ran.problem, installing(() => void play(page)));
      if (ran.running && !ran.problem) mode = "live";
      return ran;
    } catch (e) {
      errorHere(e);
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
    toast(`${done.folder}: ${done.run}`);
    problemsHere(done.problems, `The export has ${done.problems.length} problems.`, { where: done.folder });
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
    toast(done.path);
    problemsHere(done.problems, `Saving has ${done.problems.length} problems.`, { where: done.path });
    return done;
  }

  // ===== Test this page, and a thin cell's move (domain/controllers.py, domain/thin_cells.py) =====

  async function test(page?: string): Promise<TestResult | null> {
    const target = page ?? pageId;
    if (testing || !target) return null;
    testing = target;
    draw();
    const name = state?.pages.find((p) => p.id === target)?.name ?? "the page";
    try {
      const done = await gate(mode === "live" ? live : board, `Testing ${name}…`, (async () => {
        await host.settle(); // the linked cells as they are typed, saved or not
        await ensure();
        return api<TestResult>(`${base()}/pages/${encodeURIComponent(target)}/test`, "POST");
      })(), { errorIn: false });
      if ("problem" in done && done.problem && typeof done.problem === "object") {
        if (done.problem.kind === "missing") void promptInstall(done.problem, installing(() => void test(target)));
        else errorHere(problemText(done.problem));
      }
      else if ("tries" in done) {
        const blocks = Object.keys(done.failures).length + (done.outside.length ? 1 : 0);
        const said = done.problem ?? (blocks ? `${blocks} ${blocks === 1 ? "block" : "blocks"} failed` : "Every block ran");
        const untried = done.untried.length ? ` · ${done.untried.length} not tried` : "";
        const words = `Tested ${done.tries} ${done.tries === 1 ? "value" : "values"}: ${said}${untried}`;
        if (blocks || done.problem) errorHere(words, { where: name });
        else toast(words);
      }
      await call("", "GET").catch(() => undefined);
      return done;
    } catch (e) {
      errorHere(e);
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

  async function place(link: CellLink, where?: Where): Promise<boolean> {
    if (!link.document) {
      errorHere(`Save ${link.title} first: a block links to a cell in a saved file.`);
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
    if (copied.length && mode === "edit") {
      await duplicateMany(copied);
      return true;
    }
    const link = copiedCell();
    if (!link) return false;
    if (link.kind !== "code" && link.kind !== "markdown" && link.kind !== "html") {
      errorHere("A Python, Markdown or HTML cell goes on a Streamlit app's canvas.");
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
    const playButton = button(stale ? "Out of date · Play" : "Play", () => void play(), {
      icon: "play",
      class: stale ? "cv-play cv-stale" : "cv-play",
      title: stale ? "A linked cell, a table it reads or the layout changed: Play shows it" : mode === "live" ? "Play again: the page from the linked cells as they are now" : "Play: run the page from the linked cells as they are now",
      pressed: mode === "live" || busy,
    });
    playButton.disabled = busy || !page;
    if (busy) markBusy(playButton, "Starting…");
    const modes = h("span", { class: "cv-mode", role: "group", "aria-label": "Edit or play" }, editButton, playButton);
    const exportButton = button("Export…", () => void exportApp().catch((e: Error) => errorHere(e)), { icon: "export", class: "cv-export", title: "Export an app that runs alone: app.py, its pages, the data as Parquet" });
    const saveAsButton = button("Save as zip…", () => void saveAs().catch((e: Error) => errorHere(e)), { icon: "save", class: "cv-save-as", title: "Save as: the project as one zip (data.py, pages, the sources; no rows)" });
    exportButton.disabled = saveAsButton.disabled = !pages.length;
    const testButton = button("Test this page", () => void test(), { icon: "check", class: "cv-test", title: "Run the page with each filter's values (Streamlit's own test runner)" });
    testButton.disabled = !!testing || busy || !page?.blocks.length;
    if (testing) markBusy(testButton, "Testing…");
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
    alignButton.title = selectedIds.length > 1 ? "Align the selected blocks" : alignButton.title;
    menuButton(alignButton, "Align", () =>
      selectedIds.length > 1
        ? [
            { label: "Align lefts", run: () => void arrange("left") },
            { label: "Align centres", run: () => void arrange("centre") },
            { label: "Align rights", run: () => void arrange("right") },
            { label: "Align tops", run: () => void arrange("top") },
            { label: "Align bottoms", run: () => void arrange("bottom") },
            { label: "Make same width", run: () => void arrange("same_width") },
            { label: "Make same height", run: () => void arrange("same_height") },
            { label: "Distribute across the row", run: () => void arrange("distribute") },
          ]
        : [
            { label: "Left edge", run: () => void align("left") },
            { label: "Centre", run: () => void align("centre") },
            { label: "Right edge", run: () => void align("right") },
            { label: "Full width", run: () => void align("full") },
          ],
    );
    // The design surface: its width (Streamlit's own layouts, and a phone's), and what it shows.
    const widthButton = (label: string, ic: string, value: DesignWidth): HTMLButtonElement => button(label, () => void setDesignWidth(value), { icon: ic, iconOnly: true, pressed: designWidth === value, class: `ghost cv-width-${value}`, title: value === "phone" ? "Phone width: the page as a phone shows it" : `${label}: the app's layout` });
    const viewButton = h("button", { type: "button", class: "btn ghost cv-view", "aria-label": "View", title: "What the design surface shows" }, icon("eye"), icon("down")) as HTMLButtonElement;
    const hidden = page ? [...page.blocks, ...page.containers].filter((i) => i.hidden) : [];
    menuButton(viewButton, "View", () => [
      { label: `${snaplines ? "Hide" : "Show"} snaplines`, run: () => void view({ snaplines: !snaplines }) },
      { label: `${rulers ? "Hide" : "Show"} the ruler`, run: () => void view({ rulers: !rulers }) },
      { label: `${sampleRows ? "Hide" : "Show"} sample rows`, run: () => void view({ sampleRows: !sampleRows }) },
      { label: hidden.length ? `Show the ${hidden.length} hidden` : "Nothing is hidden", run: () => void showHidden() },
      { label: "Reset layout", run: () => void arrange("reset") },
    ]);
    const duplicateButton = button("Duplicate", () => void duplicate(), { icon: "duplicate", iconOnly: true, class: "ghost cv-duplicate", title: selectedId ? "Duplicate the selected block" : "Select a block to duplicate it" });
    duplicateButton.disabled = !selectedId || !page;
    const zoomOut = button("Zoom out", () => zoom(zoomed - 10), { icon: "minus", iconOnly: true, class: "ghost" });
    const zoomIn = button("Zoom in", () => zoom(zoomed + 10), { icon: "plus", iconOnly: true, class: "ghost" });
    const percent = h("button", { type: "button", class: "btn ghost cv-zoom-level", title: "Zoom: back to 100%", onclick: () => zoom(100) }, `${zoomed}%`);
    return [
      h("span", { class: "cv-group", role: "group", "aria-label": "Undo and redo" }, undoButton, redoButton),
      h("span", { class: "cv-group", role: "group", "aria-label": "Arrange" }, alignButton, duplicateButton),
      h("span", { class: "cv-group cv-widths", role: "group", "aria-label": "Page width" }, widthButton("Wide", "desktop", "wide"), widthButton("Centered", "tablet", "centered"), widthButton("Phone", "phone", "phone"), viewButton),
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

  function setSelection(ids: string[]): void {
    const page = current();
    selectedIds = ids.filter((itemId, at) => ids.indexOf(itemId) === at && (!page || page.blocks.some((b) => b.id === itemId) || page.containers.some((c) => c.id === itemId)));
    selectedId = selectedIds[0] ?? null;
    refocus = selectedId;
    drawTop();
    drawBoard();
    host.selected?.(selectedId);
  }

  function select(block: string | null): void {
    if (selectedIds.length <= 1 && selectedId === block) return;
    setSelection(block ? [block] : []);
  }

  /** Ctrl+click: in or out of the selection. */
  const toggleSelected = (block: string): void => setSelection(selectedIds.includes(block) ? selectedIds.filter((b) => b !== block) : [...selectedIds, block]);
  const selectMany = (blocks: string[]): void => setSelection(blocks);

  /** Delete: every selected item off the page (blocks as one change; a container leaves what it holds). */
  async function removeSelected(from: string): Promise<void> {
    const page = current();
    if (!page) return;
    const ids = selectedIds.includes(from) ? [...selectedIds] : [from];
    const blocks = ids.filter((itemId) => page.blocks.some((b) => b.id === itemId));
    if (blocks.length > 1) {
      const before = savedPages(state!.pages);
      const after = before.map((p) => (p.id === page.id ? { ...p, blocks: p.blocks.filter((b) => !blocks.includes(b.id ?? "")) } : p));
      if (await replacePages(after)) changes.push({ pages: before });
    } else if (blocks.length === 1) await change(`/pages/${page.id}/blocks/${blocks[0]}`, "DELETE");
    for (const box of ids.filter((itemId) => !blocks.includes(itemId))) await change(`/pages/${page.id}/blocks/${box}`, "DELETE");
    setSelection([]);
  }

  async function duplicateMany(blocks: string[]): Promise<boolean> {
    let ok = false;
    for (const block of blocks) if (current()?.blocks.some((b) => b.id === block)) ok = (await duplicate(block)) || ok;
    return ok;
  }

  /** Arrange the selection as one change (align, same size, distribute), or Reset layout. */
  async function arrange(how: Arrange, blocks?: string[]): Promise<boolean> {
    const page = current();
    if (!page) return false;
    const done = await change(`/pages/${page.id}/arrange`, "POST", how === "reset" ? { how } : { how, blocks: blocks ?? selectedIds });
    return !!done;
  }

  /** A Toolbox item put on the page: a container is the canvas's own; an element gets its cell first. */
  async function addTool(tool: string, kind: "element" | "container", where?: Where): Promise<unknown> {
    if (kind === "element") {
      if (!host.toolbox) throw new Error("This window cannot write the element's cell.");
      return host.toolbox(tool, where);
    }
    let page = current();
    if (!page) {
      const made = await change("/pages", "POST", {});
      if (made?.page) pageId = made.page;
      page = current();
    }
    if (!page) return null;
    const done = await change(`/pages/${page.id}/containers`, "POST", { kind: tool, ...(where ?? {}) });
    const made = (done as { container?: string } | null)?.container;
    if (made) select(made);
    return made ? { container: made } : null;
  }

  function feeds(block: string): BlockState[] {
    const page = current();
    const from = page?.blocks.find((b) => b.id === block);
    if (!page || !from || !from.makes.length) return [];
    return page.blocks.filter((b) => b.id !== block && !b.hidden && [...b.reads, ...b.tables].some((name) => from.makes.includes(name)));
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
      errorHere(e);
      return false;
    }
  }

  /** One step of the history taken from `from` and put on `to`: the pages put back, or a cell's code. */
  async function step(from: Step[], to: Step[], back: boolean): Promise<boolean> {
    const taken = from.pop();
    if (!taken || !state) return false;
    if ("pages" in taken) {
      to.push({ pages: savedPages(state.pages) });
      return replacePages(taken.pages);
    }
    const plan = taken.code;
    const made: CodePlan = back ? { ...plan, before: plan.code, code: plan.before } : plan;
    try {
      if (!host.applyCode || !(await host.applyCode(made))) throw new Error(`${plan.where} could not be changed back.`);
      to.push(taken);
      drawTop();
      return true;
    } catch (e) {
      errorHere(e);
      drawTop();
      return false;
    }
  }

  const undo = (): Promise<boolean> => step(undos, redos, true);
  const redo = (): Promise<boolean> => step(redos, undos, false);

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

  /** The design surface's width: Wide and Centered are the app's own layout (saved in its file); Phone
   *  only narrows the board. */
  async function setDesignWidth(width: DesignWidth): Promise<DesignWidth> {
    designWidth = width;
    if (width !== "phone" && (state?.settings.layout ?? "wide") !== width) await setSettings({ layout: width });
    drawTop();
    drawBoard();
    return designWidth;
  }

  function view(next: { snaplines?: boolean; rulers?: boolean; sampleRows?: boolean } = {}): { snaplines: boolean; rulers: boolean; sampleRows: boolean; width: DesignWidth } {
    if (next.snaplines !== undefined) snaplines = next.snaplines;
    if (next.rulers !== undefined) rulers = next.rulers;
    if (next.sampleRows !== undefined) sampleRows = next.sampleRows;
    if (Object.keys(next).length) {
      drawTop();
      drawBoard();
    }
    return { snaplines, rulers, sampleRows, width: designWidth };
  }

  async function showHidden(): Promise<void> {
    const page = current();
    if (!page) return;
    for (const item of [...page.blocks, ...page.containers]) if (item.hidden) await change(`/pages/${page.id}/blocks/${item.id}`, "PATCH", { hidden: false });
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
      errorHere(e);
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
      problem ? errorNote(problemText(problem), { dismiss: false, fixes: problem.kind === "missing" ? [{ label: `Install ${problem.packages.join(", ")}`, icon: "import", run: () => install() }] : [] }) : null,
      ...said.map((p) => errorNote(p, { dismiss: false })),
      // The page's last test: an error outside every block, or the test itself not finishing.
      ...(mode === "edit" ? [...(page?.tested?.outside ?? []).map((f) => `${f.case}: ${f.error}`), ...(page?.tested?.problem ? [page.tested.problem] : [])] : []).map((p) => h("div", { class: "cv-test-problem" }, errorNote(p, { dismiss: false }))),
      ...(mode === "live" ? (state?.notes ?? []) : []).map((n) => errorNote(n, { dismiss: false })),
    );
    notes.hidden = !notes.childElementCount;
  }

  // ===== the board: the page's own grid of 12 columns, and each container's slots, each a grid of its own =====

  interface Drop {
    row: number;
    column: number;
    insert: boolean;
    parent: string | null;
    slot: number;
  }

  /** What blocks and containers share on the board: an id and a place in a grid. */
  type Placed = { id: string; row: number; column: number; w: number; h: number | null; parent: string | null; slot: number; hidden: boolean; locked: boolean };

  const gridOf = (el: Element | null): HTMLElement | null => (el?.closest(".cv-grid") as HTMLElement | null) ?? null;
  const topGrid = (): HTMLElement | null => board.querySelector<HTMLElement>('.cv-grid[data-grid=""]');
  const whereOf = (grid: HTMLElement): { parent: string | null; slot: number } => {
    const [parent, slot] = (grid.dataset.grid ?? "").split(":");
    return parent ? { parent, slot: Number(slot ?? 0) } : { parent: null, slot: 0 };
  };
  const itemOf = (page: CanvasPage, itemId: string): Placed | null => page.blocks.find((b) => b.id === itemId) ?? page.containers.find((c) => c.id === itemId) ?? null;
  const itemEl = (itemId: string): HTMLElement | null => board.querySelector<HTMLElement>(`[data-item="${itemId}"]`);
  const rowsOf = (grid: HTMLElement): HTMLElement[] => [...grid.children].filter((el): el is HTMLElement => el.classList.contains("cv-row") && !el.classList.contains("cv-insert"));

  /** Where a drop at this point lands in a grid: the row under it (or a new one between two rows, above
   *  the first, below the last) and the column, so a block `w` wide sits centred under the pointer. */
  function dropAt(x: number, y: number, w: number, grid: HTMLElement | null = topGrid()): Drop {
    if (!grid) return { row: 1, column: 1, insert: false, parent: null, slot: 0 };
    const rows = rowsOf(grid);
    const box = grid.getBoundingClientRect();
    const columnWidth = (box.width + GAP * (zoomed / 100)) / COLUMNS;
    const column = Math.max(1, Math.min(COLUMNS - w + 1, Math.round((x - box.left) / columnWidth - w / 2) + 1));
    const into = whereOf(grid);
    for (const [i, row] of rows.entries()) {
      const at = row.getBoundingClientRect();
      if (y < at.top - 1) return { row: i + 1, column, insert: true, ...into }; // the gap above it
      if (y <= at.bottom + 1) return { row: i + 1, column, insert: false, ...into };
    }
    return { row: rows.length + 1, column, insert: false, ...into };
  }

  let ghost: HTMLElement | null = null;
  function markDrop(drop: Drop | null, w = DEFAULT_WIDTH, grid: HTMLElement | null = topGrid()): void {
    ghost?.remove();
    ghost = null;
    for (const line of board.querySelectorAll(".cv-insert")) line.remove();
    for (const lit of board.querySelectorAll(".cv-grid.dropping")) lit.classList.remove("dropping");
    board.classList.toggle("dropping", drop !== null);
    clearGuides();
    if (!drop || !grid) return;
    grid.classList.add("dropping");
    const rows = rowsOf(grid);
    ghost = h("div", { class: "cv-ghost", "aria-hidden": "true", style: { gridColumn: `${drop.column} / span ${w}`, gridRow: "1" } });
    const target = drop.insert ? undefined : rows[drop.row - 1];
    if (target) target.append(ghost);
    else {
      // A row of its own: drawn where it would be.
      const line = h("div", { class: "cv-row cv-insert" }, ghost);
      grid.insertBefore(line, rows[drop.row - 1] ?? grid.querySelector(":scope > .cv-grid-empty"));
    }
    drawGuides(ghost, dragged?.id ?? null);
  }

  // ----- snaplines (canvasSnap.ts): guides where the moving block lines up with another, equal gaps marked

  const rectOf = (el: HTMLElement, itemId: string): Rect => {
    const base = board.getBoundingClientRect();
    const box = el.getBoundingClientRect();
    const scale = zoomed / 100;
    return { id: itemId, left: (box.left - base.left) / scale + board.scrollLeft, top: (box.top - base.top) / scale + board.scrollTop, width: box.width / scale, height: box.height / scale };
  };
  const rects = (skip: string | null = null): Rect[] => [...board.querySelectorAll<HTMLElement>("[data-item]")].filter((el) => el.dataset.item !== skip).map((el) => rectOf(el, el.dataset.item!));

  function clearGuides(): void {
    for (const old of board.querySelectorAll(".cv-guide, .cv-gap")) old.remove();
  }

  /** The guides for a moving element (a drop's ghost, a block being sized), drawn over the board. */
  function drawGuides(moving: HTMLElement, itemId: string | null): void {
    clearGuides();
    if (!snaplines) return;
    const mine = rectOf(moving, itemId ?? "moving");
    const others = rects(itemId);
    for (const g of guides(mine, others, 1.5)) {
      const vertical = g.axis === "v";
      board.append(h("div", { class: `cv-guide cv-guide-${g.axis}`, "aria-hidden": "true", dataset: { edge: g.edge, with: g.with.join(" ") }, style: vertical ? { left: `${g.at}px`, top: `${g.from}px`, height: `${g.to - g.from}px` } : { top: `${g.at}px`, left: `${g.from}px`, width: `${g.to - g.from}px` } }));
    }
    // Equal spacing: the gaps of the moving block's row that match.
    const row = moving.closest(".cv-row");
    if (row) {
      const inRow = [...row.children].filter((el): el is HTMLElement => el instanceof HTMLElement && (el === moving || (!!el.dataset.item && el.dataset.item !== itemId)));
      for (const gap of equalGaps(inRow.map((el) => rectOf(el, el === moving ? "moving" : el.dataset.item!)), 1.5)) {
        board.append(h("div", { class: "cv-gap", "aria-hidden": "true", style: { left: `${gap.from}px`, top: `${gap.y}px`, width: `${gap.to - gap.from}px` } }));
      }
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

  /** What a block and a container do alike on the board: selected by a click (Ctrl or Shift adds), moved
   *  by a drag or the arrow keys (Shift: three columns at a time), sized by the corner, taken off by
   *  Delete. A locked one is selected and nothing else. */
  function behave(element: HTMLElement, page: CanvasPage, item: Placed, name: string, size: HTMLElement | null, grip: HTMLElement | null, minHeight: (rows: number | null) => string): void {
    const path = `/pages/${page.id}/blocks/${item.id}`;
    element.addEventListener("click", (e) => {
      if ((e.target as HTMLElement).closest("button, input, select, [role=tab]")) return;
      if ((e.target as HTMLElement).closest("[data-item]") !== element) return; // a block inside it took the click
      e.stopPropagation();
      if (e.ctrlKey || e.metaKey || e.shiftKey) toggleSelected(item.id);
      else select(item.id);
    });
    element.addEventListener("keydown", (e) => {
      if (e.target === element && (e.key === "Enter" || e.key === " ")) {
        e.preventDefault();
        select(item.id);
      }
    });
    element.addEventListener("dragstart", (e) => {
      if ((e.target as HTMLElement).closest("[data-item]") !== element) return;
      if (item.locked || (e.target as HTMLElement).closest(".cv-grip")) return e.preventDefault();
      e.stopPropagation();
      e.dataTransfer?.setData(BLOCK_DRAG, JSON.stringify({ block: item.id, w: item.w }));
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
      dragged = { w: item.w, id: item.id };
      element.classList.add("dragging");
    });
    element.addEventListener("dragend", () => {
      element.classList.remove("dragging");
      dragged = null;
      markDrop(null);
    });
    element.addEventListener("keydown", (e) => {
      if (e.target !== element || e.ctrlKey || e.metaKey || e.altKey) return;
      const grid = page.grids[item.parent ? `${item.parent}:${item.slot}` : ""] ?? [];
      const step = e.shiftKey ? 3 : 1;
      const moving = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key);
      if (moving && item.locked) return void errorHere(`${name} is locked: unlock it to move it.`);
      if (e.key === "ArrowLeft") void change(path, "PATCH", { row: item.row, column: Math.max(1, item.column - step) });
      else if (e.key === "ArrowRight") void change(path, "PATCH", { row: item.row, column: Math.min(COLUMNS - item.w + 1, item.column + step) });
      else if (e.key === "ArrowUp") void change(path, "PATCH", item.row > 1 ? { row: Math.max(1, item.row - step), column: item.column } : { row: 1, column: item.column, insert: true });
      else if (e.key === "ArrowDown") void change(path, "PATCH", { row: Math.min(grid.length + 1, item.row + step), column: item.column });
      else if (e.key === "Delete" || e.key === "Backspace") void removeSelected(item.id);
      else return;
      e.preventDefault();
      refocus = item.id;
    });
    if (!grip) return;
    // Resize: the corner, snapped to the grid's columns and to rows of 40 pixels.
    const show = (w: number, rows: number | null): void => {
      element.style.gridColumn = `${item.column} / span ${w}`;
      element.style.minHeight = minHeight(rows);
      element.dataset.w = String(w);
      element.dataset.h = rows === null ? "" : String(rows);
      if (size) size.textContent = sizeWords({ w, h: rows });
      drawGuides(element, item.id);
      const same = sameSize(rectOf(element, item.id), rects(item.id), 1.5);
      for (const el of board.querySelectorAll<HTMLElement>("[data-item]")) el.classList.toggle("same-width", same.width.includes(el.dataset.item!));
    };
    const sized = (): { w: number; h: number | null } => ({ w: Number(element.dataset.w), h: element.dataset.h ? Number(element.dataset.h) : null });
    let column = 0;
    let box = element.getBoundingClientRect();
    let from = sized();
    let startX = 0;
    resizeGrip(
      grip,
      (down) => {
        startX = down.clientX;
        const grid = gridOf(element.parentElement) ?? board;
        column = (grid.getBoundingClientRect().width / (zoomed / 100) - GAP * (COLUMNS - 1)) / COLUMNS;
        box = element.getBoundingClientRect();
        from = sized();
        element.classList.add("resizing");
      },
      (dx, dy) => {
        const scale = zoomed / 100;
        const w = Math.max(MIN_WIDTH, Math.min(COLUMNS - item.column + 1, Math.round(((startX + dx - box.left) / scale + GAP) / (column + GAP))));
        // The height changes only once the pointer has clearly moved down or up: a sideways drag keeps it.
        const rows = Math.abs(dy) < 12 ? from.h : Math.max(1, Math.min(MAX_ROWS, (from.h ?? 6) + Math.round(dy / 14)));
        show(w, rows);
      },
      () => {
        element.classList.remove("resizing");
        clearGuides();
        for (const el of board.querySelectorAll(".same-width")) el.classList.remove("same-width");
        const now = sized();
        if (now.w !== item.w || now.h !== item.h) void change(path, "PATCH", { w: now.w, h: now.h });
      },
    );
    grip.addEventListener("keydown", (e) => {
      const step: Record<string, [number, number]> = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] };
      const [dw, dh] = step[e.key] ?? [0, 0];
      if (!dw && !dh) return;
      e.preventDefault();
      e.stopPropagation();
      const w = Math.max(MIN_WIDTH, Math.min(COLUMNS - item.column + 1, item.w + dw));
      const rows = dh ? Math.max(1, Math.min(MAX_ROWS, (item.h ?? 6) + dh)) : item.h;
      refocus = `${item.id}:grip`;
      void change(path, "PATCH", { w, h: rows });
    });
    grip.addEventListener("dblclick", () => void change(path, "PATCH", { h: null }));
  }

  const marks = (item: Placed): HTMLElement | null => (item.locked ? h("span", { class: "cv-lock", title: "Locked: the designer does not move or size it", "aria-label": "Locked" }, icon("pin")) : null);

  /** A design-time sample (View, Sample rows): the first rows of the first table a block reads, labelled. */
  const samples = new Map<string, { columns: { name: string }[]; head: unknown[][] } | null>();
  function sample(block: BlockState): HTMLElement | null {
    const table = block.tables[0];
    if (!sampleRows || !table) return null;
    if (!samples.has(table)) {
      samples.set(table, null);
      void api<{ columns: { name: string }[]; head: unknown[][] }>(`/streamlit/tables/${encodeURIComponent(table)}`).then((read) => {
        samples.set(table, read);
        drawBoard();
      }, () => undefined);
    }
    const read = samples.get(table);
    if (!read) return null;
    const columns = read.columns.slice(0, 5);
    return h(
      "div",
      { class: "cv-sample", title: `The first rows of ${table}: a sample while designing. Play shows the real page.` },
      h("span", { class: "cv-sample-label hint" }, `Sample · ${table}`),
      h("table", {}, h("thead", {}, h("tr", {}, ...columns.map((c) => h("th", {}, c.name)))), h("tbody", {}, ...read.head.slice(0, 3).map((row) => h("tr", {}, ...row.slice(0, 5).map((v) => h("td", {}, v === null ? "" : String(v))))))),
    );
  }

  function card(page: CanvasPage, block: BlockState): HTMLElement {
    const name = block.name ?? block.where;
    const others = state!.pages.filter((p) => p.id !== page.id);
    const size = h("span", { class: "hint cv-size" }, sizeWords(block));
    const grip = block.locked ? null : h("button", { type: "button", class: "card-grip cv-grip", title: "Resize: drag, or the arrow keys (a double-click fits its height)", "aria-label": `Resize ${name}`, "aria-valuetext": sizeWords(block) });
    const path = `/pages/${page.id}/blocks/${block.id}`;
    const stale = block.state === "outOfDate" && !!state?.running;
    const minHeight = (rows: number | null): string => `${rows === null ? 76 : Math.max(76, rows * 14)}px`;
    const on = selectedIds.includes(block.id);
    const element = h(
      "article",
      {
        // A left edge in its source document's kind colour (notebook blue, script green); red when the page's test failed on it.
        class: `cv-block conn-block km-${kindOfPath(block.document) ?? "notebook"} ${block.missing ? "gone" : ""} ${stale ? "stale" : ""} ${block.failures?.length ? "failed" : ""} ${on ? "selected" : ""} ${block.locked ? "locked" : ""}`,
        "aria-selected": String(on),
        role: "listitem",
        tabindex: 0,
        draggable: String(!block.locked),
        "aria-label": `${name}, ${block.where}, row ${block.row}, column ${block.column}, ${sizeWords(block)}`,
        ...(block.connections?.length ? { "data-connections": block.connections.join("|") } : {}),
        dataset: { item: block.id, block: block.id, cell: String(block.cell), row: String(block.row), column: String(block.column), w: String(block.w), h: block.h === null ? "" : String(block.h) },
        style: { gridColumn: `${block.column} / span ${block.w}`, gridRow: "1", minHeight: minHeight(block.h) },
      },
      h(
        "div",
        { class: "cv-block-head" },
        // A Markdown or HTML cell's block: st.markdown or st.html on the page (text cells on the canvas).
        block.kind === "markdown" || block.kind === "html" ? h("span", { class: "wb-st-t", title: block.kind === "markdown" ? "A Markdown cell" : "An HTML cell", "aria-label": block.kind === "markdown" ? "A Markdown cell" : "An HTML cell" }, "T") : null,
        h("span", { class: "cv-block-name" }, name),
        marks(block),
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
      block.thin ? h("div", { class: "cv-block-thin" }, h("span", { class: "hint" }, block.thin.words), button("Move to data.ipynb", () => void moveToData(block.id).catch((e: Error) => errorHere(e)), { icon: "notebook", class: "ghost cv-move-data", title: "Move these lines into a named cell of data.ipynb; one line here reads them back" })) : null,
      sample(block),
      size,
      grip,
    );
    // Right-click: the block's lineage, back through every cell to the data; lock, hide.
    element.addEventListener("contextmenu", (e) => {
      if (!id) return;
      e.preventDefault();
      e.stopPropagation();
      const gone = block.missing ? "Its cell is gone" : undefined;
      showMenu(e.clientX, e.clientY, name, [
        ...(host.lineage ? [["lineage", "Lineage", () => host.lineage!(page.id, block.id), gone] as MenuItem] : []),
        ...designMenu(page, block),
      ]);
    });
    behave(element, page, block, name, size, grip, minHeight);
    return element;
  }

  const designMenu = (page: CanvasPage, item: Placed): MenuItem[] => [
    ["pin", item.locked ? "Unlock" : "Lock", () => void change(`/pages/${page.id}/blocks/${item.id}`, "PATCH", { locked: !item.locked })],
    ["eye", "Hide while designing", () => void change(`/pages/${page.id}/blocks/${item.id}`, "PATCH", { hidden: true })],
    ...(item.parent ? [["up", "Move out of its container", () => void change(`/pages/${page.id}/blocks/${item.id}`, "PATCH", { parent: null }), item.locked ? "It is locked" : undefined] as MenuItem] : []),
  ];

  const CONTAINER_ICONS: Record<string, string> = { columns: "columns", tabs: "panel", expander: "expand", container: "max", form: "check", sidebar: "right", popover: "popout" };
  const shownTab = new Map<string, number>(); // which tab of a Tabs container the board shows

  /** A grid: the rows of one place (the page itself, a container's slot), and where drops land in it. */
  function gridEl(page: CanvasPage, key: string, empty: string): HTMLElement {
    const rows = page.grids[key] ?? [];
    const blocks = new Map(page.blocks.map((b) => [b.id, b]));
    const boxes = new Map(page.containers.map((c) => [c.id, c]));
    const drawn = rows
      .map((row) => row.map((itemId) => (blocks.has(itemId) ? (blocks.get(itemId)!.hidden ? null : card(page, blocks.get(itemId)!)) : boxes.has(itemId) ? (boxes.get(itemId)!.hidden ? null : box(page, boxes.get(itemId)!)) : null)))
      .map((row) => row.filter((el): el is HTMLElement => el !== null));
    return h(
      "div",
      { class: `cv-grid${key ? " cv-inner" : ""}`, dataset: { grid: key }, role: key ? "group" : undefined },
      // A row whose items are all hidden still holds its place: the page draws it.
      ...drawn.map((row) => h("div", { class: `cv-row${row.length ? "" : " cv-row-hidden"}` }, ...row)),
      rows.length ? null : h("p", { class: "cv-grid-empty hint" }, empty),
    );
  }

  /** A layout container on the board, drawn as what it is: columns side by side by their ratios, tabs
   *  with their strip, an expander, a form with its button, a bordered container, a popover. */
  function box(page: CanvasPage, c: ContainerState): HTMLElement {
    const on = selectedIds.includes(c.id);
    const size = h("span", { class: "hint cv-size" }, sizeWords(c));
    const grip = c.locked || c.kind === "sidebar" ? null : h("button", { type: "button", class: "card-grip cv-grip", title: "Resize: drag, or the arrow keys", "aria-label": `Resize ${c.title}` });
    const slot = (n: number): HTMLElement => h("div", { class: "cv-slot", dataset: { slot: String(n) } }, gridEl(page, `${c.id}:${n}`, "Drop blocks here"));
    let inside: HTMLElement;
    if (c.kind === "columns") {
      const widths = (c.props.widths as number[] | undefined) ?? [1, 1];
      inside = h("div", { class: "cv-slots cv-slots-columns", style: { gridTemplateColumns: widths.map((w) => `minmax(0, ${w}fr)`).join(" ") } }, ...widths.map((_, n) => slot(n)));
    } else if (c.kind === "tabs") {
      const shown = Math.min(shownTab.get(c.id) ?? 0, c.slots - 1);
      inside = h(
        "div",
        { class: "cv-slots cv-slots-tabs" },
        h("div", { class: "cv-box-tabs", role: "tablist", "aria-label": c.title }, ...c.slot_names.map((label, n) => h("button", { type: "button", role: "tab", class: `cv-box-tab${n === shown ? " active" : ""}`, "aria-selected": String(n === shown), dataset: { slot: String(n) }, onclick: (e: Event) => { e.stopPropagation(); shownTab.set(c.id, n); drawBoard(); } }, label))),
        slot(shown),
      );
    } else {
      inside = h("div", { class: "cv-slots" }, slot(0), c.kind === "form" ? h("span", { class: "btn cv-form-submit", "aria-hidden": "true" }, String(c.props.submit ?? "Submit")) : null);
    }
    const element = h(
      "section",
      {
        class: `cv-box cv-box-${c.kind} ${on ? "selected" : ""} ${c.locked ? "locked" : ""}`,
        "aria-selected": String(on),
        role: "listitem",
        tabindex: 0,
        draggable: String(!c.locked && c.kind !== "sidebar"),
        "aria-label": `${c.title}, row ${c.row}, column ${c.column}, ${sizeWords(c)}`,
        dataset: { item: c.id, container: c.id, kind: c.kind, row: String(c.row), column: String(c.column), w: String(c.w), h: c.h === null ? "" : String(c.h) },
        style: c.kind === "sidebar" ? {} : { gridColumn: `${c.column} / span ${c.w}`, gridRow: "1" },
      },
      h(
        "div",
        { class: "cv-box-head" },
        icon(CONTAINER_ICONS[c.kind] ?? "panel"),
        h("span", { class: "cv-box-name" }, c.title),
        marks(c),
        h("span", { class: "spacer" }),
        button(`Take ${c.title} off the page`, () => void change(`/pages/${page.id}/blocks/${c.id}`, "DELETE"), { icon: "close", iconOnly: true, class: "ghost cv-remove", title: `Take ${c.title} off the page (what it holds stays)` }),
      ),
      inside,
      c.kind === "sidebar" ? null : size,
      grip,
    );
    element.addEventListener("contextmenu", (e) => {
      if ((e.target as HTMLElement).closest("[data-item]") !== element) return;
      e.preventDefault();
      showMenu(e.clientX, e.clientY, c.title, designMenu(page, c));
    });
    behave(element, page, c, c.title, size, grip, () => "");
    return element;
  }

  let dragged: { w: number; id?: string } | null = null; // what is being dragged in this window (a drag's data is not readable until the drop)

  /** The ruler over the page: its twelve columns numbered, and the page's width in pixels. */
  function ruler(): HTMLElement {
    return h("div", { class: "cv-ruler", "aria-hidden": "true" }, ...Array.from({ length: COLUMNS }, (_, n) => h("span", { class: "cv-ruler-column" }, String(n + 1))), h("span", { class: "cv-ruler-width" }));
  }

  function drawBoard(): void {
    const page = current();
    board.hidden = mode !== "edit";
    if (board.hidden) return;
    // The keyboard stays on the block it was on, however often the board is drawn again.
    const active = document.activeElement as HTMLElement | null;
    const held = active && board.contains(active) ? (active.closest("[data-item]") as HTMLElement | null) : null;
    if (!refocus && held?.dataset.item) refocus = `${held.dataset.item}${active!.classList.contains("cv-grip") ? ":grip" : ""}`;
    ghost = null;
    const holds = !!page && (page.blocks.length > 0 || page.containers.length > 0);
    board.classList.toggle("empty", !holds);
    board.dataset.width = designWidth;
    if (!page || !holds) clear(board, h("p", { class: "cv-empty" }, "Drag a cell here: Python, Markdown or HTML"));
    else {
      const bar = page.containers.find((c) => c.kind === "sidebar" && !c.hidden);
      clear(board, h("div", { class: "cv-surface" }, bar ? h("div", { class: "cv-sidebar" }, box(page, bar)) : null, h("div", { class: "cv-page" }, rulers ? ruler() : null, gridEl(page, "", ""))));
      const width = board.querySelector<HTMLElement>(".cv-ruler-width");
      const grid = topGrid();
      if (width && grid) width.textContent = `${Math.round(grid.getBoundingClientRect().width / (zoomed / 100))} px`;
    }
    board.style.setProperty("zoom", String(zoomed / 100));
    drawWires();
    if (refocus) {
      const [itemId, part] = refocus.split(":");
      const found = itemEl(itemId ?? "");
      (part ? found?.querySelector<HTMLElement>(":scope > .cv-grip") : found)?.focus();
      refocus = null;
    }
  }

  board.addEventListener("dragover", (e) => {
    const types = e.dataTransfer?.types ?? [];
    if (!types.includes(BLOCK_DRAG) && !types.includes(CELL_DRAG) && !types.includes(STARTER_DRAG) && !types.includes(TOOLBOX_DRAG)) return;
    e.preventDefault();
    const w = types.includes(BLOCK_DRAG) ? (dragged?.w ?? DEFAULT_WIDTH) : toolboxWidth(types);
    const grid = dropGrid(e);
    markDrop(dropAt(e.clientX, e.clientY, w, grid), w, grid);
  });
  board.addEventListener("dragleave", (e) => {
    if (!board.contains(e.relatedTarget as Node | null)) markDrop(null);
  });

  /** The grid a drag is over: the deepest one under the pointer (never one inside the item dragged). */
  function dropGrid(e: DragEvent): HTMLElement | null {
    let grid = gridOf(e.target as Element);
    const moving = dragged?.id ? itemEl(dragged.id) : null;
    while (grid && moving && moving.contains(grid)) grid = gridOf(grid.parentElement);
    return grid ?? topGrid();
  }

  // A Toolbox container is dropped full width; an element at the usual width.
  const toolboxWidth = (types: readonly string[]): number => (types.includes(TOOLBOX_CONTAINER) ? COLUMNS : DEFAULT_WIDTH);

  board.addEventListener("drop", (e) => {
    const link = draggedLink(e.dataTransfer);
    const raw = e.dataTransfer?.getData(BLOCK_DRAG);
    const starter = e.dataTransfer?.getData(STARTER_DRAG);
    const tool = e.dataTransfer?.getData(TOOLBOX_DRAG);
    const grid = dropGrid(e);
    const holds = !!current() && (current()!.blocks.length > 0 || current()!.containers.length > 0);
    const at = (w: number): Drop | undefined => (holds ? dropAt(e.clientX, e.clientY, w, grid) : undefined);
    markDrop(null);
    if (tool) {
      e.preventDefault();
      const what = JSON.parse(tool) as { id: string; kind: "element" | "container" };
      void addTool(what.id, what.kind, at(what.kind === "container" ? COLUMNS : DEFAULT_WIDTH)).catch((error: Error) => errorHere(error));
      return;
    }
    if (starter && host.starter) {
      e.preventDefault();
      host.starter(starter, at(DEFAULT_WIDTH));
      return;
    }
    if (link) {
      e.preventDefault();
      void place(link, at(DEFAULT_WIDTH));
      return;
    }
    const page = current();
    if (!raw || !page) return;
    e.preventDefault();
    const what = JSON.parse(raw) as { block: string; w: number };
    const from = itemOf(page, what.block);
    if (!from) return;
    const drop = dropAt(e.clientX, e.clientY, from.w, grid);
    if (drop.row === from.row && drop.column === from.column && !drop.insert && drop.parent === from.parent && drop.slot === from.slot) return;
    refocus = from.id;
    void change(`/pages/${page.id}/blocks/${from.id}`, "PATCH", drop);
  });

  // ----- the rubber band: a drag from an empty place selects what it touches; a click there clears

  board.addEventListener("pointerdown", (down) => {
    if (down.button !== 0 || (down.target as HTMLElement).closest("[data-item], button, input")) return;
    const base = board.getBoundingClientRect();
    const scale = zoomed / 100;
    const at = (e: PointerEvent): { x: number; y: number } => ({ x: (e.clientX - base.left) / scale + board.scrollLeft, y: (e.clientY - base.top) / scale + board.scrollTop });
    const start = at(down);
    let band: HTMLElement | null = null;
    const move = (e: PointerEvent): void => {
      const now = at(e);
      if (!band && Math.abs(now.x - start.x) + Math.abs(now.y - start.y) < 6) return;
      if (!band) {
        band = h("div", { class: "cv-band", "aria-hidden": "true" });
        board.append(band);
      }
      Object.assign(band.style, { left: `${Math.min(start.x, now.x)}px`, top: `${Math.min(start.y, now.y)}px`, width: `${Math.abs(now.x - start.x)}px`, height: `${Math.abs(now.y - start.y)}px` });
    };
    const up = (e: PointerEvent): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (!band) {
        if (selectedIds.length) select(null); // a click on the board itself: Properties shows the page
        return;
      }
      band.remove();
      const now = at(e);
      // The blocks it touches; a container only when nothing inside it was touched.
      const touched = inBand({ x1: start.x, y1: start.y, x2: now.x, y2: now.y }, rects());
      const inner = touched.filter((itemId) => !touched.some((other) => other !== itemId && itemEl(itemId)?.contains(itemEl(other))));
      selectMany(inner);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });

  element.addEventListener("keydown", (e) => {
    const typing = !!(e.target as HTMLElement).closest("input, textarea, select");
    if (e.key === "Escape" && selectedIds.length && !typing) select(null);
    if (typing || !(e.ctrlKey || e.metaKey) || e.altKey) return;
    const key = e.key.toLowerCase();
    if (key === "z") {
      e.preventDefault();
      void (e.shiftKey ? redo() : undo());
    } else if (key === "y") {
      e.preventDefault();
      void redo();
    } else if (key === "a" && mode === "edit" && current()) {
      e.preventDefault();
      selectMany(current()!.blocks.filter((b) => !b.hidden).map((b) => b.id));
    } else if (key === "c" && selectedIds.length && mode === "edit") {
      e.preventDefault();
      copied = [...selectedIds];
      toast(`Copied ${copied.length === 1 ? "1 block" : `${copied.length} blocks`}`);
    } else if (key === "d" && selectedIds.length && mode === "edit") {
      e.preventDefault();
      void duplicateMany([...selectedIds]);
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
  void ensure().catch((e: Error) => errorHere(e));

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
      selected: [...selectedIds],
      view: { snaplines, rulers, sampleRows, width: designWidth },
      pages: (state?.pages ?? []).map((p) => ({ id: p.id, name: p.name, grids: p.grids, containers: p.containers.map((c) => ({ id: c.id, kind: c.kind, title: c.title, parent: c.parent, slot: c.slot, row: c.row, column: c.column, w: c.w, props: c.props, hidden: c.hidden, locked: c.locked })), out_of_date: p.out_of_date, problems: p.problems, rows: p.rows, check: p.check, tested: p.tested, blocks: p.blocks.map((b) => ({ id: b.id, document: b.document, cell: b.cell, row: b.row, column: b.column, w: b.w, h: b.h, parent: b.parent, slot: b.slot, hidden: b.hidden, locked: b.locked, name: b.name, makes: b.makes, reads: [...b.tables, ...b.reads], state: b.state, missing: b.missing, role: b.controller?.role ?? null, defaults: b.defaults, contract: b.contract, thin: b.thin, failures: b.failures })) })),
    }),
    close: () => {
      gone = true;
      if (id) void api(`/streamlit/apps/${id}`, "DELETE").catch(() => undefined);
    },
    selected: () => current()?.blocks.find((b) => b.id === selectedId) ?? null,
    select: (block) => select(block),
    page: current,
    codeChanged: (plan) => {
      changes.push({ code: plan });
      drawTop();
    },
    selection: () => {
      const page = current();
      return selectedIds.map((itemId) => page?.blocks.find((b) => b.id === itemId)).filter((b): b is BlockState => !!b);
    },
    selectedIds: () => [...selectedIds],
    selectedContainer: () => current()?.containers.find((c) => c.id === selectedId) ?? null,
    selectMany,
    arrange,
    addTool,
    view,
    designWidth: (width) => (width ? setDesignWidth(width) : Promise.resolve(designWidth)),
    removeSelected: () => (selectedId ? removeSelected(selectedId) : Promise.resolve()),
    showPage: (page, block) => {
      if (!state?.pages.some((p) => p.id === page)) return;
      pageId = page;
      selectedId = null;
      draw();
      select(block ?? null);
    },
    changeBlocks: async (blocks, body) => {
      const page = current();
      if (!page) return false;
      let ok = true;
      for (const block of blocks) ok = !!(await change(`/pages/${page.id}/blocks/${block}`, "PATCH", body)) && ok;
      return ok;
    },
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
