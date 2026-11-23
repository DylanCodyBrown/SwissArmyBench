/**
 * environmentRules.ts: the Environment's rules that need no page: what a row is (as the server lists it), the
 * tabs' words, which letters of a text a search marks, an empty tab's line, what Remove says it will do, the
 * session line about the project's Python, the row the arrow keys move to. Pulled out of environmentPage.ts's
 * mountEnvironment (the craft review of 2026-11-22, refactor 8), so the page is tested in parts
 * (tests/test_environment_page_rules.py runs these in Node). Pure: no DOM, no request. [FUNCTION]
 */
import type { ProjectPython } from "./projectSession";

export type Kind = "table" | "variable" | "structure" | "setting" | "library";
export const KINDS: readonly Kind[] = ["table", "variable", "structure", "setting", "library"];
export const TAB_WORDS: Record<Kind, string> = { table: "Tables", variable: "Variables", structure: "Structures", setting: "Settings and secrets", library: "Libraries" };
export const USED_WORDS: Record<string, string> = { grid: "Grid", cell: "Code", widget: "Canvas", endpoint: "API", analysis: "Analyze", table: "Table", erd: "ERD", connection: "Connection", settings: "Run settings" };

export interface Used {
  kind: string;
  words: string;
  link: { to?: string; grid?: string; path?: string; cell?: number; line?: number; name?: string; canvas?: string; page?: string };
}
export interface Item {
  id: string;
  kind: Kind;
  name: string;
  type: string;
  size: string;
  value: string;
  from: string;
  sub: string | null;
  tags: string[];
  grids: { id: string; name: string; steps: number }[];
  used: Used[];
  kids: [string, string, string][];
  more_kids: number;
  match?: { own: boolean; kids: number[] };
  // A table's
  open?: boolean | string | null;
  in_python?: boolean;
  // A structure's
  path?: string | null;
  saved?: boolean;
  // A setting's
  secret?: boolean;
  set?: boolean;
  editable?: boolean;
  renamable?: boolean;
  showable?: boolean;
  // A library's
  version?: string;
  installed?: boolean;
  pinned?: boolean;
  latest?: string | null;
}
export interface Listing {
  items: Item[];
  counts: Record<Kind, number>;
  python: ProjectPython & { version: string };
  project: { name: string; folder: string } | null;
  memory: string;
  checked: boolean;
}

/** The stretches of `text` a search marks: for each word, the shortest stretch from its first match whose
 *  letters and digits spell the word (so cust marks the start of customer_id and of CustomerKey), as the
 *  server matched it; in the text's order, none inside another. */
export function markSpans(text: string, query: string): [number, number][] {
  const words = query.toLowerCase().split(/\s+/).map((w) => w.replace(/[^a-z0-9]/g, "")).filter(Boolean);
  const low = text.toLowerCase();
  const spans: [number, number][] = [];
  for (const word of words) {
    for (let i = 0; i < text.length; i++) {
      if (!/[a-z0-9]/.test(low[i] ?? "")) continue;
      let j = i;
      let k = 0;
      while (j < text.length && k < word.length) {
        const c = low[j] ?? "";
        if (/[a-z0-9]/.test(c)) {
          if (c !== word[k]) break;
          k++;
        }
        j++;
      }
      if (k === word.length) {
        spans.push([i, j]);
        break;
      }
    }
  }
  spans.sort((a, b) => a[0] - b[0]);
  const kept: [number, number][] = [];
  let at = 0;
  for (const [start, end] of spans) {
    if (start < at) continue;
    kept.push([start, end]);
    at = end;
  }
  return kept;
}

/** An empty tab's one line. */
export function emptyWords(tab: Kind, query: string): string {
  if (query) return `Nothing in ${TAB_WORDS[tab]} matches “${query}”.`;
  if (tab === "table") return "No tables yet. Add one on the Connections page, or make one in code.";
  if (tab === "variable") return "No variables yet: they show here as your code makes them.";
  if (tab === "structure") return "No structures yet: open a JSON, YAML, XML or TOML file, or send one from code.";
  if (tab === "setting") return "No settings yet.";
  return "No libraries yet: Install a library… adds one to the project.";
}

/** What Remove will do to a row, in one sentence; `grids`: its grids counted in words ("2 grids"). */
export function removeWords(item: Pick<Item, "kind" | "open" | "grids" | "saved" | "from">, grids: string): string {
  if (item.kind === "table") return item.open ? `The table closes with ${item.grids.length ? grids : "no grid"}; its source is not touched.` : "It is a table in Python only.";
  if (item.kind === "variable") return "The variable is deleted in Python.";
  if (item.kind === "structure") return item.saved ? `Its file ${item.from} is deleted from the project.` : "The open structure closes; it was never saved.";
  if (item.kind === "setting") return "The setting goes from this computer; what uses it will ask for it.";
  return "The library is taken out of the project's environment and of requirements.txt.";
}

/** The session line's words about the Python the project's code runs in. */
export function pythonWords(python: { version: string; own?: boolean; status?: string }, project: unknown): string {
  return `Python ${python.version} · ${python.own ? "the project's own (.venv)" : python.status === "making" ? "this app's own (the project's is being made)" : project ? "this app's own (the project has no .venv yet)" : "this app's own"}`;
}

/** The row the arrow keys move the selection to (null: the tab is empty): Down stops at the last row (the
 *  first, when nothing was selected), Up at the first. */
export function stepped(ids: string[], selected: string | null, key: "ArrowDown" | "ArrowUp"): string | null {
  const at = selected === null ? -1 : ids.indexOf(selected);
  if (key === "ArrowDown") return ids[Math.min(ids.length - 1, at + 1)] ?? ids[0] ?? null;
  return ids[Math.max(0, at - 1)] ?? null;
}
