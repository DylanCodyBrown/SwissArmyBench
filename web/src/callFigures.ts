/**
 * A connection's or an endpoint's running figures (services/call_stats.py; Plans/stats.plan.md), small and
 * out of the way: the Connections page's card and detail, the APIs page's operations. Names, times and
 * sizes only, never a value; the same figures the agent reads with its stats tool.
 */
import { h } from "./dom";

/** The figures of one object (GET /stats/figures, a card's calls.figures). */
export interface Figures {
  count: number;
  errors: number;
  error_rate: number;
  p50: number;
  p95: number;
  wait_p95: number;
  rows: number;
  bytes: number;
  pages: number;
  last: string;
}

/** 140 ms, 1.2 s, 2 min. */
export function msWords(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`;
  return `${Math.round(ms / 60_000)} min`;
}

/** "usually 140 ms": the card's few words (the rest on hover). */
export function usualWords(f: Figures | null | undefined): string {
  return f && f.count ? `usually ${msWords(f.p50)}` : "";
}

/** Every figure in words, one a line: the hover's title. */
export function figuresTitle(f: Figures): string {
  const lines = [
    `${f.count.toLocaleString()} call${f.count === 1 ? "" : "s"} in this project`,
    `Usually ${msWords(f.p50)}; 1 in 20 over ${msWords(f.p95)}`,
    f.wait_p95 ? `Waited for a slot up to ${msWords(f.wait_p95)}` : "",
    f.rows ? `Typically ${f.rows.toLocaleString()} rows` : "",
    f.pages > 1 ? `Typically ${f.pages} pages` : "",
    f.errors ? `${f.errors} failed (${Math.round(f.error_rate * 100)}%)` : "",
  ];
  return lines.filter(Boolean).join("\n");
}

/** A small muted line for an operation's row: "12 calls · usually 140 ms". */
export function figuresLine(f: Figures | null | undefined): HTMLElement | null {
  if (!f || !f.count) return null;
  const words = `${f.count.toLocaleString()} call${f.count === 1 ? "" : "s"} · ${usualWords(f)}${f.errors ? ` · ${f.errors} failed` : ""}`;
  return h("span", { class: "call-figures", title: figuresTitle(f) }, words);
}

/** The figures as a definition list's terms (the Connections page's Calls section). */
export function figuresTerms(f: Figures | null | undefined): HTMLElement[] {
  if (!f || !f.count) return [];
  const pair = (name: string, value: string): HTMLElement[] => [h("dt", {}, name), h("dd", {}, value)];
  return [
    ...pair("Usual time", `${msWords(f.p50)} (1 in 20 over ${msWords(f.p95)})`),
    ...(f.rows ? pair("Typical rows", f.rows.toLocaleString()) : []),
    ...(f.wait_p95 ? pair("Waited for a slot", `up to ${msWords(f.wait_p95)}`) : []),
    ...(f.errors ? pair("Failed", `${f.errors} of ${f.count.toLocaleString()}`) : []),
  ];
}
