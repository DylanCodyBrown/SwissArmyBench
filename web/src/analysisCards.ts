/**
 * analysisCards.ts: what the grid page sends to the Analyze board by hand, as cards that read as a report: a
 * column's profile, the whole table's, a value, a row (a note, and a Plotly chart beside it where there is one).
 * An analysis's own cards are made on the server (domain/analysis_cards.py), for the page, the agent and Python
 * alike. Charts name the theme's colors ("theme:accent"), which lazy/plotly.ts resolves when it draws.
 */

import { isLabelColumn, plainNumber } from "./dom";

export interface SandboxCard {
  kind: "note" | "plotly";
  title: string;
  body: string;
  size: { w: number; h: number };
}

const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const whole = new Intl.NumberFormat("en-US");
export const fmt = (v: unknown): string => (v === null || v === undefined ? "" : typeof v === "number" ? (Number.isInteger(v) ? whole.format(v) : number.format(v)) : String(v));
const pct = (v: number | null | undefined): string => (v === null || v === undefined ? "" : `${(100 * v).toFixed(v < 0.1 ? 1 : 0)}%`);
/** A cell's text: a bar inside a value would end the cell early. */
const cell = (v: unknown): string => fmt(v).replace(/\|/g, "\\|").replace(/\n/g, " ");

export function mdTable(head: string[], rows: unknown[][], right: boolean[] = []): string {
  const rule = head.map((_, i) => (right[i] ? "---:" : "---"));
  return [`| ${head.join(" | ")} |`, `| ${rule.join(" | ")} |`, ...rows.map((r) => `| ${r.map(cell).join(" | ")} |`)].join("\n");
}

/** A note and its chart, sized to sit side by side: the note five columns, the chart seven. */
function pair(title: string, markdown: string, figure: Record<string, unknown> | null): SandboxCard[] {
  const lines = markdown.split("\n").length;
  const h = Math.max(7, Math.min(18, Math.ceil((lines * 23 + 60) / 52)));
  const cards: SandboxCard[] = [{ kind: "note", title, body: markdown, size: { w: figure ? 5 : 12, h } }];
  if (figure) cards.push({ kind: "plotly", title: `${title} (chart)`, body: JSON.stringify(figure), size: { w: 7, h } });
  return cards;
}

// Each figure's own margin is room for its labels; the renderer (lazy/plotly.ts) styles the rest.
const BASE_LAYOUT = { font: { size: 12 }, hovermode: "closest" };

// ===== anything else pushed: a column's profile, the whole table's, a value, a row, the Key Finder =====

interface ProfileInput {
  column: string;
  type: string;
  family: string;
  rows: number;
  blanks: number;
  blank_percent: number;
  distinct: number;
  all_unique: boolean;
  top_values: { value: unknown; count: number }[];
  [key: string]: unknown;
}

const STAT_NAMES: [string, string][] = [
  ["min", "Lowest"],
  ["q1", "1st quartile"],
  ["median", "Median"],
  ["mean", "Mean"],
  ["q3", "3rd quartile"],
  ["max", "Highest"],
  ["stddev", "Standard deviation"],
  ["sum", "Sum"],
  ["zeros", "Zeros"],
  ["negatives", "Negatives"],
  ["shortest", "Shortest text"],
  ["longest", "Longest text"],
  ["empty_strings", "Empty text"],
  ["padded", "Padded with spaces"],
  ["earliest", "Earliest"],
  ["latest", "Latest"],
];

/** A column's profile: its numbers in a table, its most common values, and a histogram (numbers),
 * rows by month (dates) or the top values (anything else). */
export function profileCards(p: ProfileInput, dataset: string): SandboxCard[] {
  const label = isLabelColumn(p.column, p.min, p.max);
  const AMOUNTS = new Set(["min", "q1", "median", "q3", "max"]);
  const shown = (v: unknown): string => (label && typeof v === "number" ? plainNumber(v) : fmt(v));
  const stats = STAT_NAMES.filter(([key]) => p[key] !== undefined && p[key] !== null).map(([key, name]) => [name, AMOUNTS.has(key) ? shown(p[key]) : fmt(p[key])]);
  const lines = [
    `# Profile of ${p.column}`,
    `**${fmt(p.rows)} rows, ${fmt(p.distinct)} different values${p.all_unique ? " (every row different)" : ""}, ${fmt(p.blanks)} blank (${p.blank_percent}%).** A ${p.type.toLowerCase()} column of \`${dataset}\`.`,
  ];
  if (stats.length) lines.push("", mdTable(["Measure", "Value"], stats, [false, true]));
  if (p.top_values.length) {
    lines.push("", "#### Most common values", mdTable(["Value", "Rows", "Share"], p.top_values.slice(0, 10).map((t) => [t.value === null || t.value === undefined ? "(blank)" : shown(t.value), t.count, pct(t.count / Math.max(1, p.rows))]), [false, true, true]));
  }
  const histogram = p.histogram as { low: number; high: number; count: number }[] | undefined;
  const months = p.by_month as { month: string; count: number }[] | undefined;
  let figure: Record<string, unknown> | null = null;
  if (histogram?.length) {
    figure = {
      data: [{ type: "bar", x: histogram.map((b) => (b.low + b.high) / 2), y: histogram.map((b) => b.count), width: histogram.map((b) => (b.high - b.low) * 0.95), marker: { color: "theme:accent" }, hovertemplate: "%{x}: %{y} rows<extra></extra>" }],
      layout: { ...BASE_LAYOUT, xaxis: { title: { text: p.column } }, yaxis: { title: { text: "Rows" } }, bargap: 0 },
    };
  } else if (months?.length) {
    figure = {
      data: [{ type: "scatter", mode: "lines+markers", x: months.map((m) => m.month), y: months.map((m) => m.count), line: { color: "theme:accent", width: 2 }, hovertemplate: "%{x}: %{y} rows<extra></extra>" }],
      layout: { ...BASE_LAYOUT, xaxis: { title: { text: `${p.column} (by month)` } }, yaxis: { title: { text: "Rows" } } },
    };
  } else if (p.top_values.length > 1) {
    const top = [...p.top_values.slice(0, 15)].reverse();
    figure = {
      data: [{ type: "bar", orientation: "h", x: top.map((t) => t.count), y: top.map((t) => (t.value === null || t.value === undefined ? "(blank)" : shown(t.value))), marker: { color: "theme:accent" }, hovertemplate: "%{y}: %{x} rows<extra></extra>" }],
      layout: { ...BASE_LAYOUT, xaxis: { title: { text: "Rows" } }, yaxis: { automargin: true, type: "category" } },
    };
  }
  return pair(`Profile of ${p.column}`, lines.join("\n"), figure);
}

/** The whole view's profile: one row per column. */
export function tableProfileCards(r: { rows: number; duplicate_rows: number; columns: Record<string, unknown>[] }, dataset: string): SandboxCard[] {
  const markdown = [
    `# Profile of ${dataset}`,
    `**${fmt(r.rows)} rows, ${fmt(r.columns.length)} columns, ${fmt(r.duplicate_rows)} duplicate rows.**`,
    "",
    mdTable(
      ["Column", "Type", "Blank", "Blank %", "Different values", "Lowest", "Highest"],
      r.columns.map((c) => [
        c.column,
        String(c.type).toLowerCase(),
        c.blanks,
        `${String(c.blank_percent)}%`,
        c.distinct,
        ...(isLabelColumn(String(c.column), c.min, c.max) ? [plainNumber(c.min), plainNumber(c.max)] : [c.min, c.max])
      ]),
      [false, false, true, true, true, false, false]
    ),
  ].join("\n");
  return pair(`Profile of ${dataset}`, markdown, null).map((card) => ({ ...card, size: { w: 12, h: card.size.h } }));
}

/** One value (a cell, or a layer of one in the value viewer), titled with where it came from; a long
 * or structured value goes in a code block. */
export function valueCards(value: unknown, title: string, dataset: string): SandboxCard[] {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? "";
  const long = text.length > 120 || /[\n{[]/.test(text);
  const shown = text === "" ? "(empty text)" : value === null || value === undefined ? "(blank)" : text;
  const markdown = [`# ${title}`, `*A value from \`${dataset}\`.*`, "", long ? `\`\`\`\n${text}\n\`\`\`` : `**${shown}**`].join("\n");
  return [{ kind: "note", title, body: markdown, size: { w: long ? 6 : 4, h: long ? 8 : 4 } }];
}

/** One row: each column and its value, as a two-column table. */
export function rowCards(values: Record<string, unknown>, row: number, dataset: string): SandboxCard[] {
  const markdown = [
    `# Row ${fmt(row + 1)} of ${dataset}`,
    "",
    mdTable(
      ["Column", "Value"],
      Object.entries(values).map(([k, v]) => [
        k,
        v === null || v === undefined ? "(blank)" : typeof v === "object" ? JSON.stringify(v) : typeof v === "number" && isLabelColumn(k) ? plainNumber(v) : v
      ])
    )
  ].join("\n");
  return [{ kind: "note", title: `Row ${fmt(row + 1)} of ${dataset}`, body: markdown, size: { w: 5, h: Math.max(5, Math.min(18, Math.ceil(Object.keys(values).length * 0.6) + 3)) } }];
}
