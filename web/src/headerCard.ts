/**
 * headerCard.ts: a column's numbers when the pointer rests on its header (feel-b, 2026-11-19). [VIEW]
 *
 * Hovering a header for a moment shows a small card under it: the type, the blanks, the distinct values,
 * the range (min and max, earliest and latest, shortest and longest), the mean, and a tiny histogram (a
 * number's bins, a date's months) or the most common values. It reads the column's profile (GET
 * /grids/{id}/profile?column=), which the server keeps by view, and keeps each answer for the same steps
 * here too, so a second hover draws at once. A click, a drag, a scroll or the pointer leaving hides it.
 *
 * ROUTING: StatsHeader (gridView.ts) mouseenter -> hoverHeader(); mouseleave / mousedown -> hideHeaderCard()
 */
import { api, query } from "./api";
import { formatCount, h, isLabelColumn, plainNumber } from "./dom";
import type { PageState } from "./state";

const HOVER_MS = 450;

interface Profile {
  column: string;
  type: string;
  family: string;
  rows: number;
  blanks: number;
  blank_percent: number;
  distinct: number;
  all_unique: boolean;
  top_values: { value: unknown; count: number }[];
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  histogram?: { low: number; high: number; count: number }[];
  shortest?: number | null;
  longest?: number | null;
  earliest?: string | null;
  latest?: string | null;
  by_month?: { month: string; count: number }[];
}

const kept = new Map<string, Promise<Profile>>();
let card: HTMLElement | null = null;
let timer = 0;
let hovered: HTMLElement | null = null;

const number = (v: unknown): string =>
  typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) < 1 && v !== 0 ? 4 : 2 }) : String(v ?? "");

function profileOf(grid: PageState, column: string): Promise<Profile> {
  const upto = grid.previewUpto ?? undefined;
  const key = `${grid.base}|${JSON.stringify(grid.info?.steps ?? [])}|${grid.info?.version ?? ""}|${upto ?? ""}|${column}`;
  let got = kept.get(key);
  if (!got) {
    got = api<Profile>(`${grid.base}/profile${query({ column, upto })}`);
    got.catch(() => kept.delete(key)); // a failure is asked again next time
    kept.set(key, got);
    if (kept.size > 200) kept.delete(kept.keys().next().value as string);
  }
  return got;
}

function bars(counts: number[]): HTMLElement | null {
  const top = Math.max(0, ...counts);
  if (!counts.length || !top) return null;
  return h("div", { class: "header-card-bars", "aria-hidden": "true" }, ...counts.map((n) => h("span", { style: { height: `${Math.max(n ? 6 : 0, (100 * n) / top)}%` } })));
}

function line(label: string, value: string): HTMLElement {
  return h("div", { class: "header-card-line" }, h("span", {}, label), h("strong", {}, value));
}

function draw(p: Profile): HTMLElement {
  const lines: HTMLElement[] = [
    line("Blank", p.blanks ? `${formatCount(p.blanks)} (${p.blank_percent}%)` : "none"),
    line("Distinct", `${formatCount(p.distinct)}${p.all_unique ? " · every row different" : ""}`),
  ];
  let picture: HTMLElement | null = null;
  if (p.family === "number") {
    const label = isLabelColumn(p.column, p.min, p.max); // a year or an identifier: 2018, not 2,018
    const value = (v: unknown): string => (label ? plainNumber(v) : number(v));
    lines.push(line("Range", `${value(p.min)} to ${value(p.max)}`));
    if (p.mean != null) lines.push(line("Mean", number(p.mean)));
    picture = bars((p.histogram ?? []).map((b) => b.count));
  } else if (p.family === "date" || p.family === "timestamp") {
    if (p.earliest != null) lines.push(line("Range", `${p.earliest} to ${p.latest}`));
    picture = bars((p.by_month ?? []).map((m) => m.count));
  } else if (p.family === "text" && p.shortest != null) {
    lines.push(line("Length", p.shortest === p.longest ? `${p.shortest}` : `${p.shortest} to ${p.longest}`));
  }
  const common = p.family === "number" || !p.top_values.length || p.all_unique
    ? null
    : h(
        "ol",
        { class: "header-card-top" },
        ...p.top_values.slice(0, 3).map((t) => h("li", {}, h("span", {}, t.value === null ? "(blank)" : String(t.value)), h("span", { class: "hint" }, formatCount(t.count)))),
      );
  return h(
    "div",
    { class: "header-card", role: "tooltip" },
    h("div", { class: "header-card-head" }, h("strong", {}, p.column), h("span", { class: "hint" }, p.type.toLowerCase())),
    ...lines,
    picture,
    common,
  );
}

function place(element: HTMLElement, under: HTMLElement): void {
  const box = under.getBoundingClientRect();
  element.style.left = `${Math.max(8, Math.min(box.left, window.innerWidth - element.offsetWidth - 8))}px`;
  element.style.top = `${box.bottom + 4}px`;
}

export function hideHeaderCard(): void {
  window.clearTimeout(timer);
  hovered = null;
  card?.remove();
  card = null;
}

/** The pointer rests on a header: after a moment, its card (unless a button is held: a drag selects columns). */
export function hoverHeader(header: HTMLElement, column: string, grid: PageState, buttons: number): void {
  hideHeaderCard();
  if (buttons) return;
  hovered = header;
  timer = window.setTimeout(() => {
    void profileOf(grid, column)
      .then((p) => {
        if (hovered !== header || !header.isConnected) return;
        card = draw(p);
        card.style.left = "-9999px";
        document.body.append(card);
        place(card, header.closest<HTMLElement>(".ag-header-cell") ?? header);
      })
      .catch(() => undefined); // no card: the header is still there to click
  }, HOVER_MS);
}

// A scroll or a key moves things on: the card goes with it.
for (const type of ["scroll", "wheel", "keydown"] as const) document.addEventListener(type, hideHeaderCard, { capture: true, passive: true });
