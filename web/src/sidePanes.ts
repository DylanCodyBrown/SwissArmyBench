/**
 * sidePanes.ts: panes down the right of a page, each its own column (the owner, 2026-11-22: "Let's make the
 * blades and files panes function just like properties and widgets on canvas. On the right side with buttons
 * to show and hide them"). The Canvas's Properties and Widgets and the code pages' Files and Blades share it.
 *
 *   [COLUMNS] each pane a column of its own, side by side, its grip on its left edge (drag, or the arrow keys
 *             on the focused grip: 200 to 560 px).
 *   [TOGGLES] a button a pane (aria-pressed), for the host's bottom bar; a hidden pane's grip goes with it.
 *   [KEPT]    shown and width per pane, under the host's key (this browser's: a convenience), as
 *             `{<id>: true, <id>Width: "280px"}`: the Canvas's own format before this file.
 */
import { button, h } from "./dom";

export interface SidePaneSpec {
  id: string;
  label: string;
  icon: string;
  pane: HTMLElement;
  /** Shown when nothing is kept (default true). */
  shown?: boolean;
  title?: string;
}

export interface SidePanes {
  /** The toggle buttons, in the panes' order. */
  toggles: HTMLButtonElement[];
  /** One pane's toggle button. */
  toggle: (id: string) => HTMLButtonElement;
  /** The grips put before the panes (once each; again after the host redraws its layout). */
  mount: () => void;
  /** Show or hide a pane (default: the other way); whether it is shown now. */
  show: (id: string, on?: boolean) => boolean;
  shown: (id: string) => boolean;
  /** Read again what is kept (the key may have changed: another canvas). */
  apply: () => void;
}

const MIN = 200;
const MAX = 560;

export function sidePanes(key: () => string, specs: SidePaneSpec[], options: { toggleClass?: string; gripClass?: string; changed?: () => void } = {}): SidePanes {
  const kept = (): Record<string, unknown> => {
    try {
      return JSON.parse(localStorage.getItem(key()) ?? "{}") as Record<string, unknown>;
    } catch {
      return {};
    }
  };
  const isShown = (spec: SidePaneSpec, from = kept()): boolean => (typeof from[spec.id] === "boolean" ? (from[spec.id] as boolean) : spec.shown !== false);
  const remember = (change: Record<string, boolean> = {}): void => {
    const now: Record<string, unknown> = { ...kept(), ...change };
    for (const spec of specs) now[`${spec.id}Width`] = spec.pane.style.width || undefined;
    try {
      localStorage.setItem(key(), JSON.stringify(now));
    } catch {
      /* no storage: this window only */
    }
    apply();
  };
  const grips = new Map<string, HTMLElement>();
  const toggles = new Map<string, HTMLButtonElement>();
  for (const spec of specs) {
    spec.pane.classList.add("side-pane");
    spec.pane.dataset.sidePane = spec.id;
    toggles.set(spec.id, button(spec.label, () => void show(spec.id), { icon: spec.icon, class: `ghost side-toggle ${options.toggleClass ?? ""}`.trim(), pressed: spec.shown !== false, title: spec.title ?? spec.label }));
    const grip = h("div", { class: `side-grip ${options.gripClass ?? ""}`.trim(), role: "separator", "aria-orientation": "vertical", "aria-label": `${spec.label} width`, title: "Drag to resize", tabindex: 0 });
    grip.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const start = e.clientX;
      const width = spec.pane.getBoundingClientRect().width;
      const move = (m: PointerEvent): void => {
        spec.pane.style.width = `${Math.max(MIN, Math.min(MAX, width - (m.clientX - start)))}px`;
      };
      const up = (): void => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        remember();
        window.dispatchEvent(new Event("resize"));
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });
    grip.addEventListener("keydown", (e) => {
      const by = e.key === "ArrowLeft" ? 16 : e.key === "ArrowRight" ? -16 : 0;
      if (!by) return;
      e.preventDefault();
      spec.pane.style.width = `${Math.max(MIN, Math.min(MAX, spec.pane.getBoundingClientRect().width + by))}px`;
      remember();
    });
    grips.set(spec.id, grip);
  }
  function apply(): void {
    const now = kept();
    for (const spec of specs) {
      const on = isShown(spec, now);
      spec.pane.hidden = !on;
      grips.get(spec.id)?.toggleAttribute("hidden", !on);
      const width = now[`${spec.id}Width`];
      if (typeof width === "string" && width) spec.pane.style.width = width;
      toggles.get(spec.id)?.setAttribute("aria-pressed", String(on));
    }
    options.changed?.();
    window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  }
  function show(id: string, on?: boolean): boolean {
    const spec = specs.find((s) => s.id === id);
    if (!spec) return false;
    const next = on ?? !isShown(spec);
    remember({ [id]: next });
    return next;
  }
  return {
    toggles: [...toggles.values()],
    toggle: (id) => {
      const found = toggles.get(id);
      if (!found) throw new Error(`No side pane ${id}`);
      return found;
    },
    mount: () => {
      for (const spec of specs) {
        const grip = grips.get(spec.id)!;
        if (spec.pane.previousElementSibling !== grip) spec.pane.before(grip);
      }
      apply();
    },
    show,
    shown: (id) => {
      const spec = specs.find((s) => s.id === id);
      return !!spec && isShown(spec);
    },
    apply,
  };
}
