/**
 * bottomBar.ts: the status bar (plan sections 6a and 8). [WIRE]
 *
 * ROUTING: [ROWS SHOWN]     -> read-only, from the grid's displayed range and row count
 *          [SELECTION]      -> read-only, from state.selection (Excel's Count, Average, Sum)
 *          [MEMORY METER]   -> shown only past 80% of the budget; a click opens the Tables list (the ≡ button
 *                             beside "+": openMenu.ts), which has the numbers and where tables are removed
 *          [LIVE]           -> setLive(): words only while the page is not live
 *          [LAUNCH CLAUDE]  -> claudeLaunch.ts: Claude Code in a terminal or Claude Desktop, with the context
 */
import { api, type Budget } from "./api";
import { mountAppFooter } from "./appFooter";
import { clear, formatCount, h } from "./dom";
import { showTables } from "./openMenu";
import { displayedRange, shownTotal } from "./gridView";
import { onAgentView } from "./panes";
import { state } from "./state";

let rows: HTMLElement;
let selection: HTMLElement;
let meter: HTMLElement;
let live: HTMLElement;

export function mountBottomBar(host: HTMLElement): void {
  rows = h("span", { id: "status", role: "status" });
  selection = h("span", { "aria-live": "polite" });
  meter = h("button", { type: "button", class: "meter", onclick: () => showTables() });
  live = h("span", { id: "live" });
  mountAppFooter(host, [rows, selection], [meter, live]);
  state.on("selection", render);
  state.on("info", render);
  onAgentView(render);
}

// What the status bar says when an app tab is in front: the grid's row count belongs to the grid.
const APP_TABS: Record<string, string> = {
  agent: "Analyze",
  erd: "ERD",
  query: "New table from a query",
};

function render(): void {
  const info = state.info;
  if (!info) return;
  const view = document.querySelector<HTMLElement>(".workspace")?.dataset.view ?? "grid";
  if (view === "erd") {
    // The ERD draws every open table: the grid behind it is not what it shows (feel-a).
    rows.textContent = APP_TABS.erd!;
    selection.textContent = "";
    renderMeter(info.budget);
    return;
  }
  if (view !== "grid" && !(view === "query" && state.sqlResult)) {
    // The tab's name, then the grid behind it: an Analyze chart's click filters that grid, and this says so.
    const total = shownTotal() || 0;
    const grid = total === info.row_count ? `${formatCount(total)} rows` : `${formatCount(total)} of ${formatCount(info.row_count)} rows`;
    rows.textContent = `${APP_TABS[view] ?? ""} · ${info.dataset}: ${grid}`;
    selection.textContent = "";
    renderMeter(info.budget);
    return;
  }
  if (state.sqlResult) {
    const r = state.sqlResult;
    rows.textContent = `Query result: ${formatCount(r.rows)} row${r.rows === 1 ? "" : "s"} \u00b7 ${r.milliseconds} ms${r.capped ? " \u00b7 row cap reached" : ""}`;
    selection.textContent = "";
    renderMeter(info.budget);
    return;
  }
  if (document.querySelector(".workspace")?.getAttribute("data-panel") === "max") {
    const total = shownTotal() || 0;
    rows.textContent = `${formatCount(total)} rows in the view (${formatCount(info.row_count)} in ${info.dataset})`;
    selection.textContent = "";
    renderMeter(info.budget);
    return;
  }
  const [first, last] = displayedRange();
  const total = shownTotal() || 0;
  rows.textContent = total
    ? `Rows ${formatCount(Math.min(first + 1, total))}–${formatCount(Math.min(last + 1, total))} of ${formatCount(total)}${total !== info.row_count ? ` (${formatCount(info.row_count)} in ${info.dataset})` : ""}`
    : `0 rows (${formatCount(info.row_count)} in ${info.dataset})`;
  if (state.previewUpto !== null) rows.textContent += ` · previewing after step ${state.previewUpto}`;
  // Excel's status bar: Count is non-blank cells; Average and Sum cover the number cells.
  const s = state.selection;
  // Sum and Average to the columns' scale (a whole-number column's Sum has no decimals; an Average two);
  // an id column (order_id) is counted only: its Sum would mean nothing (feel-b, 2026-11-19).
  selection.textContent = s
    ? [
        s.kind === "rows" ? `${formatCount(s.rows)} row${s.rows === 1 ? "" : "s"} selected` : s.kind === "all" ? "All selected" : `${formatCount(s.cells)} cell${s.cells === 1 ? "" : "s"} selected`,
        `Count ${formatCount(s.count)}`,
        ...(s.mean !== null && s.sum !== null ? [`Average ${scaled(s.mean, s.digits?.mean ?? 2)}`, `Sum ${scaled(s.sum, s.digits?.sum ?? 2)}`] : []),
      ].join(" · ")
    : "";
  renderMeter(info.budget);
}

/** A number with `digits` after the point (grouped); a small fraction keeps four significant digits, so
 *  0.0034 never reads 0.00. */
export function scaled(value: number, digits: number): string {
  if (value !== 0 && Math.abs(value) < 1 && digits > 0 && Math.abs(value) < 10 ** -digits * 10) {
    return value.toLocaleString(undefined, { maximumSignificantDigits: 4 });
  }
  return value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function renderMeter(budget: Budget): void {
  // Shown only when there is something to do about it (principle 7.9): the Tables list has the numbers.
  meter.hidden = !budget.warn;
  if (!budget.warn) {
    clear(meter);
    return;
  }
  const share = budget.total_bytes ? budget.used_bytes / budget.total_bytes : 0;
  meter.className = "meter warn";
  meter.title = "Over 80% of the data budget is in use. Open the Tables list to remove some.";
  clear(
    meter,
    h("span", { class: "meter-bar", role: "meter", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(share * 100)), "aria-label": "Data budget used" }, h("span", { style: { width: `${Math.min(100, share * 100)}%` } })),
    `${budget.used} of ${budget.total} of data`,
  );
}

export function setLive(on: boolean): void {
  if (!live) return; // the pop-out windows have no status bar
  live.textContent = on ? "" : "○ not live: push again";
  live.className = on ? "" : "off";
  live.hidden = on;
}
