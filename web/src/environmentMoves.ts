/**
 * environmentMoves.ts: the Environment's reading and moving: the list read again (load), the Libraries tab's
 * one look at the index (check), a tab chosen, a row selected or unfolded, the viewer folded. Each changes
 * the state record (environmentState.ts) and draws again through `env.act.draw`. Pulled out of
 * environmentPage.ts's mountEnvironment (the craft review of 2026-11-22, refactor 8). [VIEW]
 *
 * ROUTING: GET /environment ?search=  ·  GET /environment/columns ?name=  ·  GET /environment/libraries ?check=1
 */
import { api } from "./api";
import { remember } from "./dom";
import type { Item, Kind, Listing } from "./environmentRules";
import { type Environment, find, items } from "./environmentState";

/** Read the list again (the search's), then draw; an answer overtaken by a later ask is dropped. */
export async function load(env: Environment): Promise<void> {
  const mine = ++env.asked;
  try {
    const got = await api<Listing>(`/environment${env.query ? `?search=${encodeURIComponent(env.query)}` : ""}`);
    if (mine !== env.asked || env.disposed) return;
    env.listing = got;
    env.failed = null;
    if (env.tab === "setting") void env.vaults.refresh(); // a vault saved, renamed or read again: its card follows
  } catch (e) {
    if (mine !== env.asked || env.disposed) return;
    env.failed = e;
  }
  env.act.draw();
}

/** The Libraries tab asks the index for newer versions when it opens (never in the background). */
export async function check(env: Environment): Promise<void> {
  if (env.checking || env.listing?.checked) return;
  env.checking = true;
  try {
    await api("/environment/libraries?check=1");
    await load(env);
  } catch {
    // The index cannot be reached: the libraries show without a newer version.
  } finally {
    env.checking = false;
  }
}

export function setFolded(env: Environment, to: boolean): void {
  env.folded = to;
  remember(env.foldKey, to ? "1" : "0");
  env.act.draw();
}

export function setTab(env: Environment, kind: Kind, name?: string): void {
  env.tab = kind;
  env.selected = name ? `${kind}:${name}` : (items(env, kind)[0]?.id ?? null);
  env.options.moved?.(env.tab, name ?? null);
  env.act.draw();
  if (kind === "library") void check(env);
  if (kind === "setting") void env.vaults.refresh();
}

/** Select a row by its id (`reveal`: the viewer unfolds). */
export function select(env: Environment, id: string, reveal = false): void {
  const item = find(env, id);
  if (item && item.kind !== env.tab) env.tab = item.kind;
  env.selected = id;
  if (reveal && env.folded) env.folded = false;
  env.options.moved?.(env.tab, item?.name ?? null);
  env.act.draw();
  const made = env.list.querySelector<HTMLElement>(`.env-row[data-id="${CSS.escape(id)}"]`);
  made?.scrollIntoView({ block: "nearest" });
}

/** Unfold a row (or fold it); a table's columns with their ranges and blanks are asked once, when it first opens. */
export function toggle(env: Environment, item: Item, to?: boolean): void {
  const open = to ?? !env.opened.has(item.id);
  if (open) env.opened.add(item.id);
  else env.opened.delete(item.id);
  env.selected = item.id;
  env.act.draw();
  if (open && item.kind === "table" && item.open && !env.columnsOf.has(item.id)) {
    void api<{ columns: [string, string, string][] }>(`/environment/columns?name=${encodeURIComponent(item.name)}`).then(
      (got) => {
        env.columnsOf.set(item.id, got.columns);
        env.act.draw();
      },
      () => undefined,
    );
  }
}
