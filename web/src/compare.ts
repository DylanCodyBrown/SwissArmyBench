/**
 * compare.ts: the two grids in a split, aligned row for row on key columns. [STATE + FUNCTION]
 *
 * The rule: the grids always align. Both panes read the same server mapping (routes_compare.py),
 * so row N on the left and row N on the right are the same key, or a shaded blank row on the side
 * that lacks it, and the two grids scroll together. Like a diff tool's two panes, for tables.
 *
 * Modes: outer join (every key from both sides), anti join (only unmatched rows: both sides, left
 * only or right only), cross compare (each grid shows its own rows; a row picked on one side
 * filters the other to that key). Keys come from the key picker (compareDialog.ts) when a split
 * is made, or from the ribbon's Compare row later.
 *
 * ROUTING: [START]          compareDialog Compare button -> startCompare(keys)
 *          [MODE / SIDE]    ribbon Compare row -> changeCompare({mode, anti_side})
 *          [STOP]           ribbon, or the split ending -> stopCompare()
 *          [ROW PICK]       aligned: a click lights up every row sharing its key, both sides -> showKeyGroup(row)
 *                           cross: a click filters the other grid to that key -> pick(side, row)
 *          [FOCUS BANNER]   per pane -> clearFocus()
 *          [CENTER SCROLLBAR] while aligned, one scrollbar between the grids drives both -> showSharedScroll()
 *          [DIFF COLUMNS]   diff mode: each side shows its keys and the columns that differ (the ribbon's
 *                           Only differing columns, on to start) -> showDiffColumns(); both halves scroll
 *                           sideways together and start at the first column that differs -> lockSideways()
 *          [SHOWN]          a compare started in the Key Finder's window or by the agent (the server's
 *                           compare_shown notice) -> showCompare(id)
 *          [RELOAD]         the page remembers its compare; a reload puts the split and the compare back
 *                           -> restoreCompare()
 */
import { api } from "./api";
import { button, clear, formatCount, h, recall, remember, toast } from "./dom";
import { contextOf, onSplitChange, splitPair, splitWith, type Context } from "./panes";
import { errorHere } from "./errorNote";

export interface DiffOptions {
  tolerance: number;
  percent: boolean;
  trim: boolean;
  ignore_case: boolean;
  skip: string[];
  column: string | null;
  /** Show only each side's keys and the columns that differ (on unless switched off). */
  only_differing: boolean;
}

export interface CompareInfo {
  compare: string;
  left: string;
  right: string;
  keys: [string, string][];
  mode: "outer" | "anti" | "cross" | "diff";
  anti_side: "both" | "left" | "right";
  diff: DiffOptions;
  row_count: number;
  counts: { matched: number; left_only: number; right_only: number };
  /** Diff mode: matched rows that differ, and each column's changes (most first). */
  differ: {
    matched: number;
    differ: number;
    left_only: number;
    right_only: number;
    columns: Record<string, number>;
    compared: string[];
    /** Each side's keys, then its columns that differ, under that side's own names. */
    shown: { left: string[]; right: string[] };
    /** The first column that differs, on each side (null: nothing differs). */
    first: { left: string; right: string } | null;
  } | null;
  focus: { side: "left" | "right"; rows: number; key: unknown[] } | null;
}

let current: CompareInfo | null = null;
const listeners: (() => void)[] = [];
const linked = new WeakSet<object>();

export function currentCompare(): CompareInfo | null {
  return current;
}

/** The ribbon redraws its Compare row on every change. */
export function onCompareChange(listener: () => void): void {
  listeners.push(listener);
}

function changed(): void {
  // The page remembers which compare is its own, so a reload takes it up again (restoreCompare).
  remember("workspace.compare", current ? JSON.stringify({ compare: current.compare, left: current.left, right: current.right }) : "");
  for (const listener of listeners) listener();
}

/** A compare started away from this page for it to show (the Key Finder's Compare on these, the
 * agent's compare_create with show): the two grids go side by side, lined up. No key picker. */
export async function showCompare(id: string): Promise<void> {
  let found: CompareInfo;
  try {
    found = await api<CompareInfo>(`/compares/${encodeURIComponent(id)}`);
  } catch {
    return; // stopped again already
  }
  if (!contextOf(found.left) || !contextOf(found.right)) return;
  if (current && current.compare !== found.compare) await stopCompare();
  restored = true;
  await splitWith(found.right, found.left, "right", true);
  const pair = splitPair();
  if (!pair || pair[0].id !== found.left || pair[1].id !== found.right) return;
  current = found;
  apply(pair, true);
}

// Until the page has looked for its remembered compare, a change of split is not a reason to
// forget it (the tabs are still opening).
let restored = false;

/** After a reload: the compare this page was showing, if the server still runs it and both its
 * grids are still open, comes back as it was (the split, the mode, the keys). No key picker. */
export async function restoreCompare(): Promise<void> {
  let was: { compare?: string; left?: string; right?: string } = {};
  try {
    was = JSON.parse(recall("workspace.compare") || "{}") as typeof was;
  } catch {
    was = {};
  }
  restored = true;
  if (!was.compare || !was.left || !was.right || !contextOf(was.left) || !contextOf(was.right)) return;
  let found: CompareInfo;
  try {
    found = await api<CompareInfo>(`/compares/${encodeURIComponent(was.compare)}`);
  } catch {
    remember("workspace.compare", ""); // stopped meanwhile, or the server restarted: nothing to put back
    return;
  }
  await splitWith(found.right, found.left, "right", true);
  const pair = splitPair();
  if (!pair || pair[0].id !== found.left || pair[1].id !== found.right) return;
  current = found;
  apply(pair, true);
}

// The compare belongs to the two grids it was made for: a different split (or none) ends it.
onSplitChange(() => {
  const pair = splitPair();
  if (!restored) return;
  if (current && (!pair || pair[0].id !== current.left || pair[1].id !== current.right)) void stopCompare();
  else changed();
});

export async function startCompare(keys: [string, string][], mode: CompareInfo["mode"] = "outer"): Promise<void> {
  const pair = splitPair();
  if (!pair) return;
  if (current) await stopCompare();
  try {
    current = await api<CompareInfo>("/compares", "POST", { left: pair[0].id, right: pair[1].id, keys, mode });
  } catch (e) {
    errorHere(e);
    return;
  }
  apply(pair, true);
  toast(`Aligned on ${keys.map(([l, r]) => (l === r ? l : `${l} = ${r}`)).join(" + ")}: ${formatCount(current.counts.matched)} matched, ${formatCount(current.counts.left_only)} left only, ${formatCount(current.counts.right_only)} right only.`);
}

export async function changeCompare(patch: Partial<Pick<CompareInfo, "keys" | "mode" | "anti_side">> & { diff?: Partial<DiffOptions> }): Promise<void> {
  if (patch.diff && current) patch = { ...patch, diff: { ...current.diff, ...patch.diff } };
  const pair = splitPair();
  if (!current || !pair) return;
  const was = current;
  try {
    current = await api<CompareInfo>(`/compares/${encodeURIComponent(current.compare)}`, "PATCH", patch);
  } catch (e) {
    errorHere(e);
    return;
  }
  // Only what is shown changed (Only differing columns): the rows on screen are still right.
  const sameRows = JSON.stringify({ ...was, diff: { ...was.diff, only_differing: true } }) === JSON.stringify({ ...current, diff: { ...current.diff, only_differing: true } });
  if (sameRows) {
    showDiffColumns(pair, true);
    changed();
  } else apply(pair, true);
}

let recounting = 0;

/** The compare's counts again, after a side's view changed (debounced: both sides often change at once). */
async function recount(grid: string): Promise<void> {
  if (!current || (current.left !== grid && current.right !== grid)) return;
  window.clearTimeout(recounting);
  recounting = window.setTimeout(() => {
    const was = current;
    if (!was) return;
    void api<CompareInfo>(`/compares/${encodeURIComponent(was.compare)}`)
      .then((now) => {
        if (current?.compare !== was.compare) return;
        current = { ...now, focus: current.focus };
        // A step on either side can change which columns differ.
        const pair = splitPair();
        if (pair) showDiffColumns(pair);
        changed();
      })
      .catch(() => undefined);
  }, 150);
}

export async function stopCompare(): Promise<void> {
  const was = current;
  current = null;
  // The compared grids by id: when the split itself ended (a side closed, "Close this side"),
  // splitPair() is already empty, and the grid left on screen kept showing the compare's rows.
  const compared = was ? [contextOf(was.left), contextOf(was.right)] : (splitPair() ?? []);
  for (const ctx of compared) {
    if (!ctx) continue;
    ctx.view?.setCompare(null);
    ctx.view?.showOnly(null);
    banner(ctx, null);
  }
  hideSharedScroll();
  unlockSideways();
  if (was) await api(`/compares/${encodeURIComponent(was.compare)}`, "DELETE").catch(() => undefined);
  changed();
}

/** Point both panes at the compare, keep their scrolling level, and draw any focus banner. `jump`:
 * the compare was just started or changed, so diff mode goes to the first column that differs. */
function apply([left, right]: [Context, Context], jump = false): void {
  const cmp = current!;
  left.view?.setCompare({ id: cmp.compare, side: "left" });
  right.view?.setCompare({ id: cmp.compare, side: "right" });
  // Each view is linked once; the handlers look up the current split when they fire.
  for (const mine of [left, right]) {
    if (!linked.has(mine.state)) {
      linked.add(mine.state);
      // A step on either side changes what lines up: the ribbon's counts are read again. A step made
      // here raises "view"; one from the server (the agent, a tie-out click) reloads, raising "info".
      mine.state.on("view", () => void recount(mine.id));
      mine.state.on("info", () => void recount(mine.id));
    }
    const view = mine.view;
    if (!view || linked.has(view)) continue;
    linked.add(view);
    view.onRowPick((row) => {
      const pairNow = splitPair();
      const at = pairNow?.findIndex((c) => c.view === view) ?? -1;
      if (!current || at < 0) return;
      if (current.mode === "cross") void pick(at === 0 ? "left" : "right", row);
      else void showKeyGroup(row);
    });
  }
  banner(left, cmp.focus?.side === "left" ? cmp.focus : null);
  banner(right, cmp.focus?.side === "right" ? cmp.focus : null);
  // Aligned grids share one scrollbar in the center; in cross compare each scrolls on its own.
  if (cmp.mode === "cross") hideSharedScroll();
  else showSharedScroll(left, right);
  showDiffColumns([left, right], jump);
  changed();
}

// ===== diff mode: only the columns that differ, both halves scrolling sideways together =====

/** In diff mode each side shows its keys and the columns that differ (unless Only differing columns
 * is off), the two halves scroll sideways as one, and with `jump` both go to the first column that
 * differs (or the one whose changes are being looked at). Any other mode shows every column. */
function showDiffColumns([left, right]: [Context, Context], jump = false): void {
  const cmp = current;
  const differ = cmp?.mode === "diff" ? cmp.differ : null;
  if (!cmp || !differ) {
    left.view?.showOnly(null);
    right.view?.showOnly(null);
    unlockSideways();
    return;
  }
  const only = cmp.diff.only_differing;
  left.view?.showOnly(only ? differ.shown.left : null);
  right.view?.showOnly(only ? differ.shown.right : null);
  lockSideways(left, right);
  if (!jump) return;
  const focused = cmp.diff.column;
  const to = focused ? { left: focused, right: counterpart(focused, "left") ?? focused } : differ.first;
  if (!to) return;
  // After the columns have been shown or hidden: both halves, each to its own name for the column.
  setTimeout(() => {
    left.view?.revealColumn(to.left);
    right.view?.revealColumn(to.right);
  }, 0);
}

/** The other side's name for a column: its key partner, else the column of the same name ignoring
 * case (how diff mode pairs columns). */
function counterpart(name: string, from: "left" | "right"): string | null {
  const pair = splitPair();
  if (!current || !pair) return null;
  const key = current.keys.find((k) => k[from === "left" ? 0 : 1] === name);
  if (key) return key[from === "left" ? 1 : 0];
  const other = (from === "left" ? pair[1] : pair[0]).view?.viewColumns() ?? [];
  return other.find((c) => c.name.toLowerCase() === name.toLowerCase())?.name ?? null;
}

const sideways: { off: () => void; pair: [Context, Context] | null } = { off: () => {}, pair: null };

/** Keep the two halves at the same column while either scrolls sideways. By column, not by pixel:
 * the two sides size their columns to their own values. Moving the other half raises its own scroll
 * event; that echo is known by where it lands, and is not followed back. */
function lockSideways(left: Context, right: Context): void {
  if (sideways.pair?.[0] === left && sideways.pair[1] === right) return;
  unlockSideways();
  const echo = new Map<HTMLElement, number>(); // a half we moved -> where we put it
  const last = new Map<HTMLElement, number>();
  const sides: [Context, "left" | "right", Context][] = [[left, "left", right], [right, "right", left]];
  const offs = sides.map(([mine, side, other]) => {
    const element = mine.view?.sideways();
    if (!element) return () => {};
    const follow = (): void => {
      if (last.get(element) === element.scrollLeft) return; // scrolled up or down only
      last.set(element, element.scrollLeft);
      const put = echo.get(element);
      echo.delete(element);
      if (put !== undefined && Math.abs(put - element.scrollLeft) <= 1) return;
      const at = mine.view?.horizontal();
      const name = at ? counterpart(at.column, side) : null;
      const target = other.view?.sideways();
      if (!at || !name || !target) return;
      other.view?.setHorizontal(name, at.inset);
      if (target.scrollLeft !== last.get(target)) echo.set(target, target.scrollLeft);
    };
    element.addEventListener("scroll", follow, { passive: true });
    return () => element.removeEventListener("scroll", follow);
  });
  sideways.pair = [left, right];
  sideways.off = () => offs.forEach((off) => off());
}

function unlockSideways(): void {
  sideways.off();
  sideways.off = () => {};
  sideways.pair = null;
}

// ===== the shared scrollbar between two aligned grids =====

let shared: { bar: HTMLElement; spacer: HTMLElement; sizes: ResizeObserver; left: Context; right: Context; unlock: () => void } | null = null;

const viewportOf = (ctx: Context): HTMLElement | null => ctx.view?.host.querySelector<HTMLElement>(".ag-grid-viewport") ?? null;

/** One vertical scrollbar between the panes, the height of the grids' rows, driving both grids.
 * The grids' own vertical scrollbars hide meanwhile (wheel scrolling still works in either). */
function showSharedScroll(left: Context, right: Context): void {
  const panes = left.pane?.parentElement;
  if (!panes || !right.pane) return;
  if (!shared) {
    const spacer = h("div", { class: "center-scroll-spacer" });
    const bar = h("div", { class: "center-scroll", role: "scrollbar", "aria-label": "Scroll both grids", "aria-orientation": "vertical" }, spacer);
    // Fitted again whenever the panes, the left grid's viewport or its rows' area change size: the row
    // count (and so the scroll height) changes as windows load and steps change. Nothing runs while
    // nothing changes, or while the compare is hidden.
    shared = { bar, spacer, sizes: new ResizeObserver(() => fitSharedScroll()), left, right, unlock: () => {} };
  }
  shared.left = left;
  shared.right = right;
  panes.insertBefore(shared.bar, right.pane);
  shared.sizes.disconnect();
  shared.sizes.observe(panes);
  const viewport = viewportOf(left);
  if (viewport) for (const box of [viewport, ...viewport.children]) shared.sizes.observe(box);
  panes.dataset.aligned = "on";
  fitSharedScroll();
  // Lock the two grids and the bar: whichever scrolls, the others take its exact position.
  shared.unlock();
  const elements = [viewportOf(left), shared.bar, viewportOf(right)].filter((e): e is HTMLElement => e !== null);
  shared.unlock = lockScroll(elements);
}

/** Keep `elements` at one vertical position. A native scroll listener on each sets the others to
 * its scrollTop in the same frame (no timers, no AG Grid events in between), so the two grids
 * can't drift apart. The echo from setting the others reads the same value and stops there. */
function lockScroll(elements: HTMLElement[]): () => void {
  const offs = elements.map((element) => {
    const follow = (): void => {
      for (const other of elements) if (other !== element && other.scrollTop !== element.scrollTop) other.scrollTop = element.scrollTop;
    };
    element.addEventListener("scroll", follow, { passive: true });
    return () => element.removeEventListener("scroll", follow);
  });
  return () => offs.forEach((off) => off());
}

/** Line the bar up with the grids' row area, and give it the same scroll height. */
function fitSharedScroll(): void {
  if (!shared) return;
  const viewport = viewportOf(shared.left);
  const panes = shared.bar.parentElement;
  if (!viewport || !panes) return;
  const box = viewport.getBoundingClientRect();
  const outer = panes.getBoundingClientRect();
  shared.bar.style.marginTop = `${Math.max(0, box.top - outer.top)}px`;
  shared.bar.style.height = `${viewport.clientHeight}px`;
  shared.spacer.style.height = `${viewport.scrollHeight}px`;
}

function hideSharedScroll(): void {
  if (!shared) return;
  const panes = shared.bar.parentElement;
  if (panes) delete panes.dataset.aligned;
  shared.sizes.disconnect();
  shared.unlock();
  shared.bar.remove();
  shared = null;
}

/** Aligned compare: light up every compare row that shares row's key, on both grids. Duplicate
 * keys pair up next to each other, so that is one block. */
async function showKeyGroup(row: number): Promise<void> {
  const pair = splitPair();
  if (!current || !pair) return;
  try {
    const group = await api<{ first: number; last: number }>(`/compares/${encodeURIComponent(current.compare)}/key-group?row=${row}`);
    for (const ctx of pair) ctx.view?.setKeyRows(group);
  } catch (e) {
    errorHere(e);
  }
}

/** Cross compare: a row picked on `side` filters the other grid to that row's key. */
async function pick(side: "left" | "right", row: number): Promise<void> {
  const pair = splitPair();
  if (!current || !pair) return;
  try {
    current = await api<CompareInfo>(`/compares/${encodeURIComponent(current.compare)}/focus`, "POST", { side, position: row });
  } catch (e) {
    errorHere(e);
    return;
  }
  const filtered = current.focus?.side === "left" ? pair[0] : pair[1];
  filtered.view?.setCompare({ id: current.compare, side: current.focus!.side });
  apply(pair);
}

export async function clearFocus(): Promise<void> {
  const pair = splitPair();
  if (!current || !pair) return;
  current = await api<CompareInfo>(`/compares/${encodeURIComponent(current.compare)}/focus`, "DELETE");
  apply(pair);
}

function banner(ctx: Context, focus: CompareInfo["focus"]): void {
  const slot = ctx.pane?.querySelector<HTMLElement>(".compare-slot");
  if (!slot) return;
  if (!focus) {
    clear(slot);
    return;
  }
  const key = focus.key.map((v) => (v === null ? "(blank)" : String(v))).join(", ");
  clear(
    slot,
    h(
      "div",
      { class: "preview-banner compare-banner", role: "status" },
      h("strong", {}, "Cross compare"),
      h("span", {}, `${formatCount(focus.rows)} row${focus.rows === 1 ? "" : "s"} with key ${key}`),
      h("span", { class: "spacer" }),
      button("Clear", () => void clearFocus(), { class: "primary" }),
    ),
  );
}
