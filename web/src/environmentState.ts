/**
 * environmentState.ts: the Environment's list as one record (`Environment`): its tab, search, the listing
 * last read, the selected and opened rows, a shown secret, its elements; and what every part of it asks (the
 * tab's rows, a row by its id, a row's inner lines, a match marked). Pulled out of environmentPage.ts's
 * mountEnvironment (the craft review of 2026-11-22, refactor 8): what was the closure's shared variables is
 * this record, handed to each part as its first argument. A part imports the ones below it (rules, state,
 * moves, actions, columns, draw) and reaches the page only through `env.act.draw`. [VIEW]
 */
import { h, recall } from "./dom";
import { type Item, type Kind, type Listing, markSpans, TAB_WORDS } from "./environmentRules";
import type { mountKeyVaults } from "./keyVaults";

export interface EnvironmentOptions {
  /** The Workbench's pane: fewer columns, the viewer under the list. */
  compact?: boolean;
  /** Insert into code: the host's editor takes it (the Workbench); none: it is copied. */
  insert?: (code: { python?: string; sql?: string; text?: string }) => boolean;
  /** The tab and the row to start on. */
  tab?: Kind;
  name?: string;
  /** Told when the tab or the selected row changes (the page keeps them in its address). */
  moved?: (tab: Kind, name: string | null) => void;
  /** The page's heading actions (Clear… goes there); none: in the find row. */
  actions?: HTMLElement;
}

export interface Column {
  head: string;
  width: string;
  /** Kept in the Workbench's pane. */
  compact?: boolean;
  cell: (item: Item) => Node;
}

/** The Environment's list: what every part of it reads and writes. */
export interface Environment {
  options: EnvironmentOptions;
  compact: boolean;
  tab: Kind;
  query: string;
  listing: Listing | null;
  failed: unknown;
  selected: string | null;
  opened: Set<string>;
  /** A table's columns with their ranges, once asked. */
  columnsOf: Map<string, [string, string, string][]>;
  /** A secret shown on the user's click, until hidden or the page goes. */
  revealed: Map<string, string>;
  checking: boolean;
  disposed: boolean;
  asked: number;
  /** The viewer folded away (kept per host: the page, the Workbench's pane). */
  foldKey: string;
  folded: boolean;
  /** The viewer's "Also delete it in Python" tick, for Remove. */
  pythonTick: HTMLInputElement | null;
  // ----- its elements
  search: HTMLInputElement;
  hint: HTMLElement;
  tools: HTMLElement;
  tabs: HTMLElement;
  session: HTMLElement;
  projectHost: HTMLElement;
  vaults: ReturnType<typeof mountKeyVaults>;
  list: HTMLElement;
  viewer: HTMLElement;
  element: HTMLElement;
  /** What a part asks of the page: draw it again (environmentDraw.ts's, set by the page). */
  act: { draw: () => void };
}

// ===== marking a match =====

/** `text` with the search's words marked: the shortest stretch whose letters and digits spell a word (so cust
 *  marks the start of customer_id and of CustomerKey), as the server matched it. */
export function marked(text: string, query: string): DocumentFragment {
  const out = document.createDocumentFragment();
  let at = 0;
  for (const [start, end] of markSpans(text, query)) {
    out.append(text.slice(at, start), h("mark", {}, text.slice(start, end)));
    at = end;
  }
  out.append(text.slice(at));
  return out;
}

// ===== what the list holds =====

export const items = (env: Environment, kind: Kind = env.tab): Item[] => (env.listing?.items ?? []).filter((i) => i.kind === kind);
export const find = (env: Environment, id: string | null): Item | undefined => (id ? env.listing?.items.find((i) => i.id === id) : undefined);
export const kindMark = (item: Item): HTMLElement => h("span", { class: `env-kind env-k-${item.sub === "secret" || item.sub === "sandbox" ? item.sub : item.kind}`, title: TAB_WORDS[item.kind], "aria-hidden": "true" });
export const kidsOf = (env: Environment, item: Item): [string, string, string][] => env.columnsOf.get(item.id) ?? item.kids;
export const isOpen = (env: Environment, item: Item): boolean => env.opened.has(item.id) || Boolean(env.query && item.match && !item.match.own && item.match.kids.length);

/** The columns a tab hides, kept per tab. */
export const hiddenKey = (kind: Kind): string => `env.hidden.${kind}`;
export const hidden = (kind: Kind): Set<string> => new Set((recall(hiddenKey(kind)) ?? "").split("|").filter(Boolean));
