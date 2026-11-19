/**
 * emptyState.ts: an empty page that leads somewhere (the owner, 2026-11-19; design principle 8.11, no dead
 * ends). [SHARED]
 *
 *   [STATE]   One sentence of what the page holds, the one primary button that fills it, and "Try it with
 *             sample data": the made-up sample store (POST /samples/store, domain/sample_data.py; the
 *             agent's datasets_sample) opened as tables, then the grids. Used by Connections, Variables, a
 *             kind's landing page in the Workbench and Session.
 */
import { api, token } from "./api";
import { button, h, icon } from "./dom";
import { busyClick } from "./loading";
import { errorHere } from "./errorNote";
import { HOME_URL, visit, withParams } from "./nav";

export interface EmptyState {
  /** The page's icon (dom.ts ICONS). */
  icon: string;
  /** One sentence: what the page holds, how it fills. */
  line: string;
  /** The one primary action. */
  action?: { label: string; icon?: string; run: () => void | Promise<unknown> };
  /** Offer the made-up sample store (default true). */
  sample?: boolean;
  /** What follows the sample's tables (default: the grids). */
  afterSample?: () => void;
}

/** Open the made-up sample store, then show the grids (the home page here, else this tab goes there). */
export async function openSample(then?: () => void): Promise<{ name: string; grid: string }[]> {
  const opened = (await api<{ tables: { name: string; grid: string }[] }>("/samples/store", "POST")).tables;
  if (then) {
    then();
    return opened;
  }
  const last = opened[opened.length - 1];
  const onHome = location.pathname === HOME_URL || location.pathname === "/";
  if (onHome) visit(withParams({ open: null, at: null, type: null, name: null, view: null }, HOME_URL));
  else location.assign(`${HOME_URL}${last ? `?grid=${encodeURIComponent(last.grid)}` : ""}${token ? `#token=${encodeURIComponent(token)}` : ""}`);
  return opened;
}

export function emptyState(o: EmptyState): HTMLElement {
  const sample = o.sample === false
    ? null
    : button(
        "Try it with sample data",
        busyClick("Opening the sample…", (b) =>
          openSample(o.afterSample).catch((e: unknown) => {
            errorHere(e, {}, b);
          }),
        ),
        { class: "ghost empty-state-sample", title: "Opens three made-up tables: customers, products and orders" },
      );
  const action = o.action ? button(o.action.label, () => void o.action!.run(), { icon: o.action.icon, class: "primary" }) : null;
  return h(
    "div",
    { class: "empty-state empty-note" },
    h("span", { class: "empty-state-icon", "aria-hidden": "true" }, icon(o.icon)),
    h("p", { class: "empty-state-line" }, o.line),
    action || sample ? h("div", { class: "empty-state-actions" }, action, sample) : null,
  );
}
