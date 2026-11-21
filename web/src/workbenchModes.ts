/**
 * workbenchModes.ts: the Workbench's modes (2026-11-15): each document's own panels, beside it in its
 * group, so the panels follow the group they belong to (two groups side by side each keep theirs). [WIRE]
 *
 *   (App mode's Properties, State, Streamlit cells and Starters went with app notebooks, 2026-11-21: an app
 *   is widgets on the Canvas, its own page)
 *   Notebook  Outline on the right
 *   Script    Run settings on the right; Run history under it
 *   Data      (data.ipynb) the Cells | Lineage | Dictionary switch is the document's own (workbenchDoc
 *             Mode.ts); its Outline as a notebook's
 *
 * The status bar shows the focused document's panels as toggles; a panel turned off in Settings
 * (Panels) is gone, its toggle too. A panel draws itself when it opens and when its document asks.
 */
import { button, h, icon } from "./dom";

export interface ModePanel {
  id: string;
  title: string;
  icon: string;
  where: "left" | "side" | "bottom";
  /** Draw the panel's body (called when it opens, and on `redraw`). */
  draw: (body: HTMLElement) => void;
  /** Its head's own buttons (Reset state). */
  tools?: () => HTMLElement[];
  /** The status bar's word for its toggle (default: the title). */
  label?: string;
}

export interface ModeFrame {
  add: (panel: ModePanel) => void;
  /** Open or close a panel (no `show`: the other way). True when it is open now. */
  toggle: (id: string, show?: boolean) => boolean;
  isOpen: (id: string) => boolean;
  /** Draw the open panels again (or the one named). */
  redraw: (id?: string) => void;
  panels: () => ModePanel[];
  /** The panel's body, while it is open. */
  body: (id: string) => HTMLElement | null;
}

/** A document's panels, in its own element (`host`, the document's body in its group). */
export function modeFrame(host: HTMLElement, changed: () => void): ModeFrame {
  const left = h("aside", { class: "wb-mode-left", hidden: true });
  const side = h("aside", { class: "wb-mode-side", hidden: true });
  const bottom = h("section", { class: "wb-mode-bottom", hidden: true });
  host.append(left, side, bottom);
  const panels: ModePanel[] = [];
  const open = new Set<string>();
  const bodies = new Map<string, HTMLElement>();

  const layout = (): void => {
    left.hidden = !left.childElementCount;
    side.hidden = !side.childElementCount;
    bottom.hidden = !bottom.childElementCount;
    host.classList.toggle("mode-open", !left.hidden || !side.hidden || !bottom.hidden);
    host.classList.toggle("mode-left", !left.hidden);
    host.classList.toggle("mode-side", !side.hidden);
    host.classList.toggle("mode-bottom", !bottom.hidden);
  };

  const shown = (panel: ModePanel): HTMLElement => {
    const body = h("div", { class: "wb-mode-body" });
    bodies.set(panel.id, body);
    const close = button(`Close ${panel.title}`, () => toggle(panel.id, false), { icon: "close", iconOnly: true, class: "ghost" });
    return h(
      "section",
      { class: `wb-mode-panel wb-mode-${panel.id}`, role: "region", "aria-label": panel.title, dataset: { panel: panel.id } },
      h("header", { class: "wb-mode-head" }, h("span", { class: "wb-mode-title" }, icon(panel.icon), h("span", {}, panel.title)), h("span", { class: "spacer" }), ...(panel.tools?.() ?? []), close),
      body,
    );
  };

  function toggle(id: string, show?: boolean): boolean {
    const panel = panels.find((p) => p.id === id);
    if (!panel) return false;
    const want = show ?? !open.has(id);
    const where = panel.where === "left" ? left : panel.where === "side" ? side : bottom;
    if (want && !open.has(id)) {
      // One panel a side: another one there gives way.
      for (const other of panels) if (other !== panel && other.where === panel.where && open.has(other.id)) toggle(other.id, false);
      open.add(id);
      where.append(shown(panel));
      panel.draw(bodies.get(id)!);
    } else if (!want && open.has(id)) {
      open.delete(id);
      bodies.delete(id);
      where.querySelector(`[data-panel="${id}"]`)?.remove();
    }
    layout();
    changed();
    return open.has(id);
  }

  return {
    add: (panel) => {
      panels.push(panel);
    },
    toggle,
    isOpen: (id) => open.has(id),
    redraw: (id) => {
      for (const panel of panels) {
        if ((id && panel.id !== id) || !open.has(panel.id)) continue;
        const body = bodies.get(panel.id);
        if (body) panel.draw(body);
      }
    },
    panels: () => panels,
    body: (id) => bodies.get(id) ?? null,
  };
}

/** A small "Plain value"-style select's options. */
export function options(select: HTMLSelectElement, list: [string, string][], value: string): HTMLSelectElement {
  select.replaceChildren(...list.map(([v, label]) => h("option", { value: v, selected: v === value }, label)));
  return select;
}

