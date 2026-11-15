/**
 * designerPage.ts: the page designer (docs/ideas.md, 2026-11-15), in a window of its own: a
 * document's Streamlit pieces assembled on pages, like Lego. [COMPOSITION]
 *
 *   [PAGES]   the app's pages as tabs: add, rename (double-click or F2), remove; each shown live
 *   [PIECES]  the document's Streamlit cells at the left: drag one onto the board, or Add
 *   [BOARD]   the page's layout on 12 columns (the Sandbox board's pattern): pieces flow left to
 *             right in order, a row holding as many as fit. Drag a piece to move it (or the arrow
 *             keys), drag its corner to resize it (arrow keys too; a double-click fits its height),
 *             Delete takes it off the page. Each piece says the names it makes and reads: pieces
 *             that share a name are linked, wherever they sit
 *   [LIVE]    the page itself under the board, live, in a frame of this server's (sandboxed without
 *             the app's origin). It follows every change
 *   [APP]     Open app shows the whole app in its own window (this page with view=app: one frame)
 *
 * Nothing here is the designer's alone: every action is a streamlit_* command for the agent, and a
 * change made anywhere (the Workbench, the agent) shows here at once.
 *
 * ROUTING: /streamlit/apps/{app}... (routes_streamlit.py); the `streamlit_changed` notice
 */
import { api, connect, onNotice, openedWith } from "./api";
import { watchTheme } from "./catalogRail";
import { button, clear, h, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { FRAME_SANDBOX } from "./workbenchHtml";
import { type AppState, type ExportResult, frameAddress, openApp, type PageState, type PieceState, type Placed, problemText } from "./workbenchStreamlit";

watchTheme();

const COLUMNS = 12;
const GAP = 8;
const ROW = 40; // pixels a unit of a piece's height stands for (domain/streamlit_cells.py ROW_HEIGHT)
const MIN_WIDTH = 2;
const MAX_ROWS = 30;
const DRAG = "application/x-swissarmygrid-piece";

const appId = openedWith.get("app") ?? "";
const appOnly = openedWith.get("view") === "app";
let wanted = openedWith.get("page"); // the page asked for in the address
let state: AppState | null = null;
let pageId: string | null = null;
let busy = false;

const top = document.getElementById("dz-top") as HTMLElement;
const rail = document.getElementById("dz-pieces") as HTMLElement;
const board = document.getElementById("dz-board") as HTMLElement;
const live = document.getElementById("dz-live") as HTMLElement;
let frame: HTMLIFrameElement | null = null;
let shown: string | null = null; // the address the frame shows

const base = (): string => `/streamlit/apps/${encodeURIComponent(appId)}`;
const current = (): PageState | null => state?.pages.find((p) => p.id === pageId) ?? null;
const pieceOf = (cell: number): PieceState | undefined => state?.pieces.find((p) => p.cell === cell);

/** A change of the layout: sent, and the state that comes back drawn. */
async function change(path: string, method: string, body?: unknown): Promise<AppState | null> {
  try {
    const next = await api<AppState & { page?: string }>(`${base()}${path}`, method, body);
    take(next);
    return next;
  } catch (e) {
    toast((e as Error).message, "error");
    return null;
  }
}

function take(next: AppState): void {
  state = next;
  if (wanted && next.pages.some((p) => p.id === wanted)) pageId = wanted;
  wanted = null;
  if (!next.pages.some((p) => p.id === pageId)) pageId = next.pages[0]?.id ?? null;
  draw();
}

async function load(): Promise<void> {
  try {
    take(await api<AppState>(base()));
  } catch (e) {
    state = null;
    document.title = "Page designer";
    clear(top);
    clear(rail);
    clear(board);
    clear(live, h("p", { class: "dz-empty" }, (e as Error).message));
  }
}

async function run(): Promise<void> {
  if (busy) return;
  busy = true;
  draw();
  try {
    take(await api<AppState>(`${base()}/run`, "POST"));
  } catch (e) {
    toast((e as Error).message, "error");
  } finally {
    busy = false;
    draw();
  }
}

async function install(): Promise<void> {
  if (busy) return;
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
  await run();
}

async function exportApp(): Promise<void> {
  const folder = await chooseFile({ title: "Export as Streamlit app: choose its folder", mode: "folder" });
  if (!folder) return;
  try {
    const done = await api<ExportResult>(`${base()}/export`, "POST", { folder });
    toast(`${done.folder}: ${done.run}`, done.problems.length ? "error" : "info");
    for (const problem of done.problems) toast(problem, "error");
  } catch (e) {
    toast((e as Error).message, "error");
  }
}

// ===== the top: the pages as tabs, and the app's tools =====

function renamePage(page: PageState, label: HTMLElement): void {
  const input = h("input", { type: "text", class: "dz-rename", value: page.name, "aria-label": "Page name", maxlength: 80 }) as HTMLInputElement;
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
  if (!state) return;
  const page = current();
  const tabs = state.pages.map((p) => {
    const label = h("span", { class: "tab-label" }, p.name);
    const tab = h(
      "div",
      {
        class: `tab-item dz-tab ${p.id === pageId ? "active" : ""}`,
        role: "tab",
        "aria-selected": String(p.id === pageId),
        tabindex: p.id === pageId ? "0" : "-1",
        title: `${p.name}: double-click to rename`,
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
        if (p.pieces.length && !confirm(`Remove the page ${p.name}? Its pieces stay in the notebook.`)) return;
        void change(`/pages/${p.id}`, "DELETE");
      }, { icon: "close", iconOnly: true, class: "tab-close" }),
    );
    return tab;
  });
  const stale = !!page?.out_of_date;
  const runButton = !state.running
    ? button(busy ? "Starting…" : "Run", () => void run(), { icon: "play", class: "primary dz-run", title: "Run the app: its pages show live" })
    : button(stale ? "Out of date · Run" : "Refresh", () => void run(), { icon: "play", class: stale ? "dz-run dz-stale" : "ghost dz-run", title: stale ? "A piece's code or a table it names changed: run to see it" : "Read the tables from the grid again and run the pages" });
  runButton.disabled = busy;
  clear(
    top,
    h("div", { class: "dz-tabs", role: "tablist", "aria-label": "Pages" }, ...tabs, button("New page", () => void change("/pages", "POST", {}).then((next) => {
      const made = (next as (AppState & { page?: string }) | null)?.page;
      if (made) {
        pageId = made;
        draw();
      }
    }), { icon: "plus", class: "ghost dz-new-page" })),
    h(
      "div",
      { class: "ribbon-tools dz-tools" },
      runButton,
      button("Open app", () => openApp(appId, pageId ?? undefined), { icon: "popout", class: "dz-open-app", title: "The whole app in its own window" }),
      button("Export…", () => void exportApp(), { icon: "export", class: "dz-export", title: "Export as Streamlit app: a folder that runs without this app" }),
    ),
  );
  (top.querySelector(".dz-export") as HTMLButtonElement).disabled = !state.pages.length;
}

// ===== the rail: the document's pieces =====

const partsOf = (piece: PieceState): string => [piece.makes.length ? `makes ${piece.makes.join(", ")}` : "", piece.tables.length || piece.reads.length ? `reads ${[...piece.tables, ...piece.reads].join(", ")}` : ""].filter(Boolean).join(" · ");

function drawRail(): void {
  if (!state) return;
  const page = current();
  const add = (cell: number): void => {
    if (page) void change(`/pages/${page.id}/pieces`, "POST", { cell });
    else void change("/pages", "POST", { cell });
  };
  clear(
    rail,
    h("h2", { id: "dz-pieces-title" }, "Pieces"),
    state.pieces.length
      ? h(
          "ul",
          { class: "dz-piece-list", "aria-labelledby": "dz-pieces-title" },
          ...state.pieces.map((piece) => {
            const here = page?.pieces.some((s) => s.cell === piece.cell) ?? false;
            const item = h(
              "li",
              { class: `dz-piece ${here ? "here" : ""}`, draggable: "true", dataset: { cell: String(piece.cell) }, title: "Drag onto the page, or Add" },
              h("div", { class: "dz-piece-name" }, piece.name, h("span", { class: "hint" }, ` cell ${piece.cell}`)),
              partsOf(piece) ? h("div", { class: "hint dz-piece-parts" }, partsOf(piece)) : null,
              piece.problem ? h("div", { class: "dz-piece-problem" }, `Not whole Python yet: ${piece.problem}`) : null,
              button("Add", () => add(piece.cell), { icon: "plus", iconOnly: true, class: "ghost dz-add", title: page ? `Add to ${page.name}${here ? " again" : ""}` : "Add to a new page" }),
            );
            item.addEventListener("dragstart", (e) => {
              e.dataTransfer?.setData(DRAG, JSON.stringify({ cell: piece.cell }));
              if (e.dataTransfer) e.dataTransfer.effectAllowed = "copyMove";
            });
            return item;
          }),
        )
      : h("p", { class: "hint" }, "This document has no Streamlit cells yet. Add one in the Workbench."),
  );
}

// ===== the board: the page's layout =====

let dropAt: number | null = null;

/** Where a drop at this point lands among the page's pieces (from 0). */
function indexAt(x: number, y: number): number {
  const cards = [...board.querySelectorAll<HTMLElement>(".dz-card")];
  for (const [i, card] of cards.entries()) {
    const box = card.getBoundingClientRect();
    if (y < box.top - GAP / 2) return i; // above this row: before its first card
    if (y <= box.bottom + GAP / 2 && x < box.left + box.width / 2) return i;
  }
  return cards.length;
}

function markDrop(index: number | null): void {
  dropAt = index;
  const cards = [...board.querySelectorAll<HTMLElement>(".dz-card")];
  for (const [i, card] of cards.entries()) {
    card.classList.toggle("drop-before", index === i);
    card.classList.toggle("drop-after", index === cards.length && i === cards.length - 1);
  }
  board.classList.toggle("dropping", index !== null);
}

function place(page: PageState, placed: Placed, body: Record<string, unknown>): void {
  void change(`/pages/${page.id}/pieces/${placed.id}`, "PATCH", body);
}

function sizeWords(placed: Placed): string {
  return `${placed.w} of ${COLUMNS} wide${placed.h === null ? "" : ` · ${placed.h * ROW}px tall`}`;
}

function card(page: PageState, placed: Placed, index: number): HTMLElement {
  const piece = pieceOf(placed.cell);
  const name = piece?.name ?? `Cell ${placed.cell} (deleted)`;
  const others = state!.pages.filter((p) => p.id !== page.id);
  const size = h("span", { class: "hint dz-size" }, sizeWords(placed));
  const grip = h("button", { type: "button", class: "card-grip dz-grip", title: "Resize: drag, or the arrow keys (a double-click fits its height)", "aria-label": `Resize ${name}`, "aria-valuetext": sizeWords(placed) });
  const element = h(
    "article",
    {
      class: `dz-card ${piece ? "" : "gone"} ${piece?.state === "outOfDate" && state!.running ? "stale" : ""}`,
      tabindex: 0,
      draggable: "true",
      "aria-label": `${name}, piece ${index + 1} of ${page.pieces.length}, ${sizeWords(placed)}`,
      dataset: { piece: placed.id, cell: String(placed.cell), w: String(placed.w), h: placed.h === null ? "" : String(placed.h) },
      style: { gridColumn: `span ${placed.w}`, minHeight: `${placed.h === null ? 76 : Math.max(76, placed.h * 14)}px` },
    },
    h(
      "div",
      { class: "dz-card-head" },
      h("span", { class: "dz-card-name" }, name),
      h("span", { class: "hint" }, `cell ${placed.cell}`),
      h("span", { class: "spacer" }),
      others.length
        ? button("Move to another page", (e) => moveMenu(page, placed, e.currentTarget as HTMLElement), { icon: "forward", iconOnly: true, class: "ghost" })
        : null,
      button(`Take ${name} off the page`, () => void change(`/pages/${page.id}/pieces/${placed.id}`, "DELETE"), { icon: "close", iconOnly: true, class: "ghost dz-remove" }),
    ),
    piece && partsOf(piece) ? h("div", { class: "dz-card-parts" }, partsOf(piece)) : null,
    size,
    grip,
  );
  // Move: drag the card, or the arrow keys on it.
  element.addEventListener("dragstart", (e) => {
    if ((e.target as HTMLElement).closest(".dz-grip")) return e.preventDefault();
    e.dataTransfer?.setData(DRAG, JSON.stringify({ piece: placed.id }));
    if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
    element.classList.add("dragging");
  });
  element.addEventListener("dragend", () => {
    element.classList.remove("dragging");
    markDrop(null);
  });
  element.addEventListener("keydown", (e) => {
    if (e.target !== element) return;
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") place(page, placed, { index: Math.max(0, index - 1) });
    else if (e.key === "ArrowRight" || e.key === "ArrowDown") place(page, placed, { index: Math.min(page.pieces.length - 1, index + 1) });
    else if (e.key === "Delete" || e.key === "Backspace") void change(`/pages/${page.id}/pieces/${placed.id}`, "DELETE");
    else return;
    e.preventDefault();
    refocus = placed.id;
  });
  // Resize: the corner, snapped to the board's columns and to rows of 40 pixels.
  const show = (w: number, rows: number | null): void => {
    element.style.gridColumn = `span ${w}`;
    element.style.minHeight = `${rows === null ? 76 : Math.max(76, rows * 14)}px`;
    element.dataset.w = String(w);
    element.dataset.h = rows === null ? "" : String(rows);
    size.textContent = sizeWords({ ...placed, w, h: rows });
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
      const w = Math.max(MIN_WIDTH, Math.min(COLUMNS, Math.round((event.clientX - box.left + GAP) / (column + GAP))));
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
      if (now.w !== placed.w || now.h !== placed.h) place(page, placed, { w: now.w, h: now.h });
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
    const w = Math.max(MIN_WIDTH, Math.min(COLUMNS, placed.w + dw));
    const rows = dh ? Math.max(1, Math.min(MAX_ROWS, (placed.h ?? 6) + dh)) : placed.h;
    refocus = `${placed.id}:grip`;
    place(page, placed, { w, h: rows });
  });
  grip.addEventListener("dblclick", () => place(page, placed, { h: null }));
  return element;
}

let refocus: string | null = null; // the card (or its grip) the keyboard was on before a change

function moveMenu(page: PageState, placed: Placed, anchor: HTMLElement): void {
  document.querySelector(".menu")?.remove();
  const menu = h(
    "div",
    { class: "menu", role: "menu", "aria-label": "Move to another page" },
    ...state!.pages.filter((p) => p.id !== page.id).map((p) => h("button", { type: "button", role: "menuitem", onclick: () => { menu.remove(); place(page, placed, { page: p.id }); } }, `Move to ${p.name}`)),
  );
  document.body.append(menu);
  const box = anchor.getBoundingClientRect();
  menu.style.top = `${box.bottom + 4}px`;
  menu.style.left = `${Math.max(8, Math.min(box.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 8))}px`;
  (menu.querySelector("button") as HTMLButtonElement | null)?.focus();
  setTimeout(() => document.addEventListener("mousedown", function away(e) { if (!menu.contains(e.target as Node)) { menu.remove(); document.removeEventListener("mousedown", away); } }));
  menu.addEventListener("keydown", (e) => { if (e.key === "Escape") { menu.remove(); anchor.focus(); } });
}

function drawBoard(): void {
  if (!state) return;
  const page = current();
  board.classList.toggle("empty", !page || !page.pieces.length);
  if (!page) {
    clear(board, h("p", { class: "dz-empty" }, "No pages yet. Add a piece from the left, or make a page with New page."));
    return;
  }
  // The keyboard stays on the piece it was on, however often the board is drawn again.
  const active = document.activeElement as HTMLElement | null;
  const held = active && board.contains(active) ? (active.closest(".dz-card") as HTMLElement | null) : null;
  if (!refocus && held?.dataset.piece) refocus = `${held.dataset.piece}${active!.classList.contains("dz-grip") ? ":grip" : ""}`;
  const problems = page.problems.map((p) => h("p", { class: "dz-problem", role: "alert" }, p));
  clear(
    board,
    ...problems,
    ...(page.pieces.length ? page.pieces.map((placed, index) => card(page, placed, index)) : [h("p", { class: "dz-empty" }, "Drag a piece here from the left, or use its Add.")]),
  );
  if (refocus) {
    const [id, part] = refocus.split(":");
    const found = board.querySelector<HTMLElement>(`.dz-card[data-piece="${id}"]`);
    (part ? found?.querySelector<HTMLElement>(".dz-grip") : found)?.focus();
    refocus = null;
  }
}

board.addEventListener("dragover", (e) => {
  if (!e.dataTransfer?.types.includes(DRAG)) return;
  e.preventDefault();
  markDrop(indexAt(e.clientX, e.clientY));
});
board.addEventListener("dragleave", (e) => {
  if (!board.contains(e.relatedTarget as Node | null)) markDrop(null);
});
board.addEventListener("drop", (e) => {
  const raw = e.dataTransfer?.getData(DRAG);
  const page = current();
  const index = dropAt ?? indexAt(e.clientX, e.clientY);
  markDrop(null);
  if (!raw) return;
  e.preventDefault();
  const what = JSON.parse(raw) as { cell?: number; piece?: string };
  if (what.cell !== undefined) {
    // A piece from the left: onto this page at that place (a new page when there is none).
    if (page) void change(`/pages/${page.id}/pieces`, "POST", { cell: what.cell, index });
    else void change("/pages", "POST", { cell: what.cell });
    return;
  }
  if (!page || !what.piece) return;
  const from = page.pieces.findIndex((s) => s.id === what.piece);
  if (from < 0) return;
  // The place among the others, once it has left its own.
  const to = index > from ? index - 1 : index;
  if (to !== from) void change(`/pages/${page.id}/pieces/${what.piece}`, "PATCH", { index: to });
});

// ===== the live page =====

function drawLive(): void {
  if (!state) return;
  const page = current();
  const address = state.running && page?.address ? frameAddress(page.address) : null;
  live.classList.toggle("running", address !== null);
  if (address !== null) {
    if (shown === address && frame) return; // the same page: Streamlit itself follows the change
    shown = address;
    frame = h("iframe", { class: "dz-frame", sandbox: FRAME_SANDBOX, title: page!.name, src: address, referrerpolicy: "no-referrer" }) as HTMLIFrameElement;
    clear(live, frame);
    return;
  }
  shown = null;
  frame = null;
  const problem = state.problem;
  clear(
    live,
    h(
      "div",
      { class: "dz-empty dz-stopped" },
      problem ? h("p", { class: "dz-problem", role: "alert" }, problemText(problem)) : h("p", {}, page ? "Run the app to see this page live." : "A page shows here, live, once it has a piece."),
      problem?.kind === "missing" ? button(busy ? "Installing…" : "Install", () => void install(), { class: "primary dz-install", title: problem.command }) : null,
      !problem && page ? button(busy ? "Starting…" : "Run", () => void run(), { icon: "play", class: "primary" }) : null,
    ),
  );
}

function draw(): void {
  if (!state) return;
  if (appOnly) return drawApp();
  const page = current();
  document.title = `${page ? `${page.name} · ` : ""}${state.title} · Page designer`;
  drawTop();
  drawRail();
  drawBoard();
  drawLive();
}

// ===== the app on its own (view=app): one frame, the whole window =====

function drawApp(): void {
  if (!state) return;
  document.title = state.title.replace(/\.(ipynb|py)$/, "");
  const start = wanted ?? pageId;
  const page = state.pages.find((p) => p.id === start);
  const address = state.running && state.path ? (page?.address ?? state.path) : null;
  if (address !== null) {
    if (shown !== null && frame) return; // the app moves between its own pages
    shown = address;
    frame = h("iframe", { class: "dz-frame", sandbox: FRAME_SANDBOX, title: state.title, src: address, referrerpolicy: "no-referrer" }) as HTMLIFrameElement;
    clear(live, frame);
    return;
  }
  shown = null;
  frame = null;
  clear(
    live,
    h(
      "div",
      { class: "dz-empty dz-stopped" },
      state.problem ? h("p", { class: "dz-problem", role: "alert" }, problemText(state.problem)) : h("p", {}, "The app is not running."),
      state.problem?.kind === "missing" ? button(busy ? "Installing…" : "Install", () => void install(), { class: "primary dz-install" }) : button(busy ? "Starting…" : "Run", () => void run(), { icon: "play", class: "primary" }),
    ),
  );
}

// ===== start =====

document.body.classList.toggle("dz-app-only", appOnly);
if (!appId) clear(live, h("p", { class: "dz-empty" }, "Open the page designer from a notebook's Streamlit app menu in the Workbench."));
else {
  connect((online) => {
    if (online) void load();
  }, { designer: "1" });
  onNotice((notice) => {
    if (notice.type === "streamlit_changed" && (notice as unknown as { app: string }).app === appId) void load();
    // A table changed in the grid: a piece that names it is out of date now.
    if (state?.running && ["grid_updated", "dataset_updated", "dataset_closed", "dataset_renamed"].includes(notice.type)) void load();
  });
}
// Asked for again from the Workbench (a page's name on a piece): the same window, that page.
window.addEventListener("hashchange", () => {
  const asked = new URLSearchParams(location.hash.slice(1));
  if (!asked.has("token")) return;
  history.replaceState(null, "", location.pathname + location.search);
  const page = asked.get("page");
  if (page && state?.pages.some((p) => p.id === page)) {
    pageId = page;
    draw();
  }
});
