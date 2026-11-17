/**
 * excelPreview.ts: a workbook's sheet drawn in the page (the Excel canvas's Play, and a template on the
 * canvas): the server read the built (or imported) .xlsx back (the Accounting extension's files.py
 * preview), and this draws it as a sheet looks in Excel. [EXCEL]
 *
 *   [CELLS]   column letters and row numbers, each cell's text as formatted, bold and italic, font
 *             colour and fill, a total's borders, numbers to the right; merged cells spanned; column
 *             widths in Excel's characters
 *   [CHARTS]  each of the sheet's native charts drawn where it is anchored (a picture of it: columns,
 *             bars, lines, a pie, a combo's line over its columns), its title and legend
 *   [PICK]    a click on a cell names it (B3, or its named range): the template's binding form
 *
 * Every value is text in the page (never markup): a workbook's cells are data.
 */
import { h } from "./dom";

export interface PreviewCell {
  t?: string;
  n?: 1;
  b?: 1;
  i?: 1;
  size?: number;
  c?: string;
  fill?: string;
  top?: 1;
  bottom?: 1;
  formula?: string;
}

export interface PreviewChart {
  kind: string;
  cell: string;
  width: number;
  height: number;
  title: string | null;
  categories: string[];
  series: { name: string; kind: string; values: (number | null)[] }[];
}

export interface PreviewSheet {
  name: string;
  rows: (PreviewCell | null)[][];
  row_count: number;
  column_count: number;
  cut: boolean;
  merged: string[];
  widths: Record<string, number>;
  freeze: string | null;
  charts: PreviewChart[];
}

export interface Preview {
  sheets: PreviewSheet[];
  names: Record<string, string>;
}

export const letters = (n: number): string => {
  let out = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    out = String.fromCharCode(65 + r) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
};

export const columnOf = (text: string): number => [...text.toUpperCase()].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0);

/** "B3" -> [row 3, column 2]. */
export function cellAt(cell: string): [number, number] {
  const m = /^\$?([A-Za-z]{1,3})\$?(\d+)$/.exec(cell.trim());
  return m ? [Number(m[2] ?? 1), columnOf(m[1] ?? "A")] : [1, 1];
}

const PALETTE = ["#1f3864", "#c55a11", "#548235", "#7030a0", "#2e75b6", "#bf9000"];
const colour = (i: number): string => PALETTE[i % PALETTE.length] ?? "#1f3864";
const CM = 37.8; // pixels in a centimetre (a chart's size in the workbook)

function spans(merged: string[]): { at: Map<string, [number, number]>; covered: Set<string> } {
  const at = new Map<string, [number, number]>();
  const covered = new Set<string>();
  for (const range of merged) {
    const [from, to] = range.split(":");
    if (!from || !to) continue;
    const [r1, c1] = cellAt(from);
    const [r2, c2] = cellAt(to);
    at.set(`${r1}:${c1}`, [r2 - r1 + 1, c2 - c1 + 1]);
    for (let r = r1; r <= r2; r++) for (let c = c1; c <= c2; c++) if (r !== r1 || c !== c1) covered.add(`${r}:${c}`);
  }
  return { at, covered };
}

/** A chart as a picture of itself (SVG): what Excel will draw from the same series. */
function chartPicture(chart: PreviewChart): SVGSVGElement {
  const W = Math.max(220, Math.round(chart.width * CM));
  const H = Math.max(140, Math.round(chart.height * CM));
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", String(W));
  svg.setAttribute("height", String(H));
  svg.setAttribute("class", "xc-chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${chart.kind} chart${chart.title ? `: ${chart.title}` : ""}`);
  const el = (tag: string, attrs: Record<string, string | number>, text?: string): SVGElement => {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
    if (text !== undefined) node.textContent = text;
    svg.append(node);
    return node;
  };
  el("rect", { x: 0, y: 0, width: W, height: H, class: "xc-chart-frame" });
  const top = chart.title ? 30 : 12;
  if (chart.title) el("text", { x: W / 2, y: 20, "text-anchor": "middle", class: "xc-chart-title" }, chart.title);
  const legendH = 20;
  const left = 46;
  const plotW = W - left - 14;
  const plotH = H - top - 34 - legendH;
  const series = chart.series.filter((s) => s.values.length);
  const cats = chart.categories.length ? chart.categories : (series[0]?.values ?? []).map((_, i) => String(i + 1));
  series.forEach((s, i) => {
    const x = 12 + i * Math.min(150, (W - 24) / Math.max(1, series.length));
    el("rect", { x, y: H - 15, width: 10, height: 10, fill: colour(i) });
    el("text", { x: x + 14, y: H - 6, class: "xc-chart-legend" }, s.name || `Series ${i + 1}`);
  });
  if (chart.kind === "pie") {
    const values = (series[0]?.values ?? []).map((v) => Math.max(0, v ?? 0));
    const sum = values.reduce((a, b) => a + b, 0) || 1;
    const cx = W / 2;
    const cy = top + plotH / 2 + 8;
    const r = Math.max(20, Math.min(plotW, plotH) / 2);
    let angle = -Math.PI / 2;
    values.forEach((v, i) => {
      const next = angle + (v / sum) * Math.PI * 2;
      const large = next - angle > Math.PI ? 1 : 0;
      const d = `M${cx},${cy} L${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)} A${r},${r} 0 ${large} 1 ${cx + r * Math.cos(next)},${cy + r * Math.sin(next)} Z`;
      el("path", { d, fill: colour(i), class: "xc-chart-slice" });
      angle = next;
    });
    return svg;
  }
  const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  const max = Math.max(0, ...all);
  const min = Math.min(0, ...all);
  const span = max - min || 1;
  const y = (v: number): number => top + plotH - ((v - min) / span) * plotH;
  el("line", { x1: left, x2: left + plotW, y1: y(0), y2: y(0), class: "xc-chart-axis" });
  for (const v of [max, (max + min) / 2, min]) el("text", { x: left - 6, y: y(v) + 4, "text-anchor": "end", class: "xc-chart-tick" }, Math.abs(v) >= 1000 ? `${Math.round(v / 1000)}k` : String(Math.round(v * 100) / 100));
  const horizontal = chart.kind === "bar";
  const bars = series.filter((s) => s.kind !== "line" && chart.kind !== "line");
  const lines = series.filter((s) => s.kind === "line" || chart.kind === "line");
  const slot = plotW / Math.max(1, cats.length);
  cats.forEach((c, j) => {
    el("text", { x: left + slot * (j + 0.5), y: top + plotH + 14, "text-anchor": "middle", class: "xc-chart-tick" }, c.length > 14 ? `${c.slice(0, 13)}…` : c);
  });
  if (horizontal) {
    const band = plotH / Math.max(1, cats.length);
    const x = (v: number): number => left + ((v - min) / span) * plotW;
    bars.forEach((s, i) => {
      s.values.forEach((v, j) => {
        if (v === null) return;
        const hgt = (band * 0.8) / bars.length;
        el("rect", { x: Math.min(x(0), x(v)), y: top + band * j + band * 0.1 + hgt * i, width: Math.abs(x(v) - x(0)), height: hgt, fill: colour(series.indexOf(s)) });
      });
    });
    return svg;
  }
  bars.forEach((s, i) => {
    s.values.forEach((v, j) => {
      if (v === null) return;
      const wdt = (slot * 0.8) / bars.length;
      el("rect", { x: left + slot * j + slot * 0.1 + wdt * i, y: Math.min(y(0), y(v)), width: wdt, height: Math.abs(y(v) - y(0)), fill: colour(series.indexOf(s)) });
    });
  });
  for (const s of lines) {
    const points = s.values.map((v, j) => (v === null ? null : `${left + slot * (j + 0.5)},${y(v)}`)).filter(Boolean).join(" ");
    el("polyline", { points, fill: "none", stroke: colour(series.indexOf(s)), "stroke-width": 2.5 });
  }
  return svg;
}

export interface SheetOptions {
  /** A cell clicked: its address (B3) and the named range there, if any. */
  pick?: (cell: string, named: string | null) => void;
  /** Cells to mark (a template's bound places), by address: their words. */
  marks?: Map<string, string>;
  names?: Record<string, string>;
}

/** One sheet of a preview, as a table, its charts over it. */
export function drawSheet(sheet: PreviewSheet, options: SheetOptions = {}): HTMLElement {
  const columns = Math.max(sheet.rows.reduce((n, r) => Math.max(n, r.length), 0), 8);
  const { at, covered } = spans(sheet.merged);
  const named = new Map<string, string>();
  for (const [name, place] of Object.entries(options.names ?? {})) {
    const [where, ref] = place.includes("!") ? place.split("!") : [sheet.name, place];
    if (where === sheet.name && ref) named.set((ref.split(":")[0] ?? ref).toUpperCase(), name);
  }
  const colgroup = h("colgroup", {}, h("col", { class: "xc-rowhead-col" }), ...Array.from({ length: columns }, (_, i) => h("col", { style: { width: `${Math.round((sheet.widths[letters(i + 1)] ?? 8.43) * 7 + 5)}px` } })));
  const head = h("tr", {}, h("th", { class: "xc-corner" }), ...Array.from({ length: columns }, (_, i) => h("th", { scope: "col" }, letters(i + 1))));
  const body = sheet.rows.map((row, r) =>
    h(
      "tr",
      {},
      h("th", { scope: "row" }, String(r + 1)),
      ...Array.from({ length: columns }, (_, c) => {
        const key = `${r + 1}:${c + 1}`;
        if (covered.has(key)) return null;
        const cell = row[c] ?? null;
        const address = `${letters(c + 1)}${r + 1}`;
        const span = at.get(key);
        const mark = options.marks?.get(address) ?? (named.get(address) ? options.marks?.get(named.get(address)!) : undefined);
        const td = h(
          "td",
          {
            class: [cell?.n ? "num" : "", cell?.b ? "b" : "", cell?.i ? "i" : "", cell?.top ? "top" : "", cell?.bottom ? "bottom" : "", mark ? "bound" : "", named.has(address) ? "named" : ""].filter(Boolean).join(" ") || undefined,
            rowspan: span && span[0] > 1 ? span[0] : undefined,
            colspan: span && span[1] > 1 ? span[1] : undefined,
            title: [cell?.formula, named.get(address), mark].filter(Boolean).join(" · ") || undefined,
            dataset: { cell: address },
            style: { ...(cell?.fill ? { background: cell.fill } : {}), ...(cell?.c ? { color: cell.c } : {}), ...(cell?.size ? { fontSize: `${Math.min(22, cell.size)}px` } : {}) },
            onclick: options.pick ? () => options.pick!(address, named.get(address) ?? null) : undefined,
          },
          cell?.t ?? "",
          mark ? h("span", { class: "xc-mark" }, mark) : null,
        );
        return td;
      }),
    ),
  );
  const table = h("table", { class: `xc-grid ${options.pick ? "pickable" : ""}`, "aria-label": sheet.name }, colgroup, h("thead", {}, head), h("tbody", {}, ...body));
  const wrap = h("div", { class: "xc-preview-sheet", dataset: { sheet: sheet.name } }, table);
  if (sheet.cut) wrap.append(h("p", { class: "hint" }, `${sheet.row_count.toLocaleString()} rows by ${sheet.column_count} columns: the first ones shown`));
  // Charts over their anchor cells, once the table is laid out.
  for (const chart of sheet.charts) {
    const holder = h("div", { class: "xc-chart-holder", dataset: { cell: chart.cell, kind: chart.kind } }, chartPicture(chart));
    wrap.append(holder);
    requestAnimationFrame(() => {
      const [r, c] = cellAt(chart.cell);
      const rowEl = table.tBodies[0]?.rows[r - 1];
      const headCells = table.tHead?.rows[0]?.cells;
      const left = headCells?.[c]?.offsetLeft ?? 40;
      const top = rowEl?.offsetTop ?? (table.tHead?.offsetHeight ?? 22) + (r - 1) * 22;
      holder.style.left = `${left}px`;
      holder.style.top = `${top}px`;
      // The sheet is as tall and wide as its charts reach (they hang over the cells, as in Excel).
      wrap.style.minHeight = `${Math.max(wrap.offsetHeight, top + holder.offsetHeight + 8)}px`;
      wrap.style.minWidth = `${Math.max(wrap.offsetWidth, left + holder.offsetWidth + 8)}px`;
    });
  }
  return wrap;
}
