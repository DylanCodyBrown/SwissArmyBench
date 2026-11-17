/**
 * canvasKit.ts: the machinery a canvas shares (the Streamlit canvas, workbenchCanvas.ts; the Excel canvas,
 * excelCanvas.ts; the Report canvas after them): one place for each, never a fork. [SHARED]
 *
 *   [HISTORY]  Undo and Redo: the state before each change kept (50 at most); a new change clears Redo
 *   [TABS]     the canvas's pages or sheets as tabs: a click selects, a double-click or F2 renames, the
 *              close button removes (asked first when it holds blocks), the "New" button adds; each tab
 *              can take drops (decorate)
 *   [GRIP]     a resize grip: the pointer captured, each move given its distance from where it started,
 *              the end given once
 */
import { button, h } from "./dom";

export interface History<T> {
  /** Keep the state before a change (Redo is cleared). */
  push: (before: T) => void;
  /** The state to go back to (the current one goes to Redo); undefined: nothing to undo. */
  undo: (now: T) => T | undefined;
  redo: (now: T) => T | undefined;
  canUndo: () => boolean;
  canRedo: () => boolean;
}

export function history<T>(limit = 50): History<T> {
  const undos: T[] = [];
  const redos: T[] = [];
  return {
    push: (before) => {
      undos.push(before);
      if (undos.length > limit) undos.shift();
      redos.length = 0;
    },
    undo: (now) => {
      const back = undos.pop();
      if (back !== undefined) redos.push(now);
      return back;
    },
    redo: (now) => {
      const again = redos.pop();
      if (again !== undefined) undos.push(now);
      return again;
    },
    canUndo: () => undos.length > 0,
    canRedo: () => redos.length > 0,
  };
}

export interface TabPage {
  id: string;
  name: string;
}

export interface TabsOptions<P extends TabPage> {
  pages: P[];
  current: string | null;
  /** What the strip is ("Pages", "Sheets"), and the words for one ("page", "sheet"). */
  label: string;
  noun: string;
  select: (page: P) => void;
  rename: (page: P, name: string) => void;
  /** Remove it; `ask`: its blocks would go with it (the strip asks first). */
  remove: (page: P) => void;
  holds: (page: P) => boolean;
  add: () => void;
  /** More on each tab (drops onto it). */
  decorate?: (tab: HTMLElement, page: P) => void;
  /** The strip's own class beside "cv-tabs" (the Streamlit canvas's tabs stay "cv-tab"). */
  tabClass?: string;
  maxLength?: number;
}

/** A tab's name edited in place: Enter or a click away keeps it, Escape puts it back. */
export function renameInPlace(label: HTMLElement, name: string, done: (name: string | null) => void, maxLength = 80): void {
  const input = h("input", { type: "text", class: "cv-rename", value: name, "aria-label": "Name", maxlength: maxLength }) as HTMLInputElement;
  let finished = false;
  const finish = (keep: boolean): void => {
    if (finished) return;
    finished = true;
    const said = input.value.trim();
    done(keep && said && said !== name ? said : null);
  };
  input.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") finish(true);
    else if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
  label.replaceWith(input);
  input.focus();
  input.select();
}

/** The pages (or sheets) as a tab strip, with its New button. */
export function pageTabs<P extends TabPage>(o: TabsOptions<P>): HTMLElement {
  const tabs = o.pages.map((p) => {
    const label = h("span", { class: "tab-label" }, p.name);
    const rename = (): void => renameInPlace(label, p.name, (name) => (name ? o.rename(p, name) : o.select(p)), o.maxLength);
    const tab = h(
      "div",
      {
        class: `tab-item ${o.tabClass ?? "cv-tab"} ${p.id === o.current ? "active" : ""}`,
        role: "tab",
        "aria-selected": String(p.id === o.current),
        tabindex: p.id === o.current ? "0" : "-1",
        title: p.name,
        dataset: { page: p.id },
        onclick: () => {
          if (o.current !== p.id) o.select(p);
        },
        ondblclick: rename,
        onkeydown: (e: KeyboardEvent) => {
          if (e.target !== tab) return;
          if (e.key === "F2") rename();
          else if (e.key === "Enter" || e.key === " ") tab.click();
        },
      },
      label,
      button(`Remove ${p.name}`, (e) => {
        e.stopPropagation();
        if (o.holds(p) && !confirm(`Remove the ${o.noun} ${p.name} and its blocks?`)) return;
        o.remove(p);
      }, { icon: "close", iconOnly: true, class: "tab-close" }),
    );
    o.decorate?.(tab, p);
    return tab;
  });
  return h("div", { class: "cv-tabs", role: "tablist", "aria-label": o.label }, ...tabs, button(`New ${o.noun}`, () => o.add(), { icon: "plus", class: "ghost cv-new-page" }));
}

/** A resize grip: `move` hears the pointer's distance from where it went down, `end` once it lets go. */
export function resizeGrip(grip: HTMLElement, start: (down: PointerEvent) => void, move: (dx: number, dy: number) => void, end: () => void): void {
  grip.addEventListener("pointerdown", (down) => {
    down.preventDefault();
    down.stopPropagation();
    grip.setPointerCapture(down.pointerId);
    start(down);
    const moved = (event: PointerEvent): void => move(event.clientX - down.clientX, event.clientY - down.clientY);
    const up = (): void => {
      grip.removeEventListener("pointermove", moved);
      grip.removeEventListener("pointerup", up);
      grip.removeEventListener("pointercancel", up);
      end();
    };
    grip.addEventListener("pointermove", moved);
    grip.addEventListener("pointerup", up);
    grip.addEventListener("pointercancel", up);
  });
}
