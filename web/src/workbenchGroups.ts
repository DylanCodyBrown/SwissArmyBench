/**
 * workbenchGroups.ts: the Workbench's tab groups, after Visual Studio Code's editor groups (the
 * redesign of 2026-11-15: "Should be able to arrange and add as many tabs as you want"). [FUNCTION + WIRE]
 *
 *   [KINDS]    every tab has a kind (registerTabKind): an icon and a thin colour mark on its top edge,
 *              in its kind colour (kindColours.ts: app pages violet, notebooks blue, scripts green;
 *              data.ipynb is a notebook with the data's own icon; a blade or a table plain). The group
 *              wears its front document's colour as a band along its top. A kind with `start` is
 *              offered by a group's "+" and by the empty state
 *   [GROUPS]   any number of groups, side by side or stacked, each one row of tabs over the document in
 *              front. The focused group's row ends with that document's controls (the page draws them);
 *              the others show only their tabs
 *   [DRAG]     a tab dragged along a row moves there; over a group, the five-way guide: the middle moves
 *              it into that group, an edge splits that side. Escape puts it back. The same by command
 *              (split right, split down, move to a group, move left or right)
 *   [SIZES]    a splitter between groups: drag it, or focus it and use the arrow keys; a double-click
 *              shares the space evenly
 *   [CLOSE]    a group goes with its last tab (the window keeps one, empty, for the empty state)
 *   [SAVE]     the layout as plain data (the groups, their tabs, the sizes, the focused group), which the
 *              page keeps with its session restore
 */
import { button, dragPointer, dragResize, h, icon } from "./dom";

// ===== kinds =====

/** The kind colour a tab wears (kindColours.ts); "plain": none (a blade, a catalog table). */
export type Mark = "app" | "notebook" | "script" | "plain";

export interface TabKind {
  /** "notebook", "data", "script", "blade", "explorer"; the app pages add "page". */
  id: string;
  /** What the kind is called: "Notebook", "App page". */
  label: string;
  icon: string;
  mark: Mark;
  /** Made from a group's "+" and the empty state ("New notebook"); none: not made from there. */
  start?: { label: string; run: () => void };
}

const kinds = new Map<string, TabKind>();
const kindListeners: (() => void)[] = [];

/** Add a kind of tab (or replace one with the same id). */
export function registerTabKind(kind: TabKind): void {
  kinds.set(kind.id, kind);
  for (const listener of kindListeners) listener();
}

export function tabKind(id: string): TabKind | undefined {
  return kinds.get(id);
}

export function tabKinds(): TabKind[] {
  return [...kinds.values()];
}

/** Told when a kind is registered (the empty state's buttons follow). */
export function onTabKinds(listener: () => void): void {
  kindListeners.push(listener);
}

// ===== groups =====

export interface TabLike {
  id: number;
  title: string;
  path: string | null;
  dirty: boolean;
  element: HTMLElement;
}

export type Side = "left" | "right" | "up" | "down";
type Zone = Side | "center";

interface Group<T> {
  id: number;
  tabs: T[];
  active: T | null;
  el: HTMLElement;
  tabsEl: HTMLElement;
  controls: HTMLElement;
  body: HTMLElement;
}

interface Split<T> {
  dir: "row" | "column";
  children: Node<T>[];
  sizes: number[];
}

type Node<T> = { group: Group<T> } | Split<T>;

/** A layout as data: a group's tabs by their keys (the page's), or a split of nodes with their sizes. */
export type SavedNode = { tabs: number[]; active: number } | { dir: "row" | "column"; children: SavedNode[]; sizes: number[] };

export interface SavedLayout {
  root: SavedNode;
  /** The focused group, from 0 in reading order. */
  focused: number;
}

export interface GroupsHost<T> {
  kindOf(tab: T): string;
  /** The tab in front of the focused group changed (null: nothing is open). */
  focused(tab: T | null): void;
  /** A tab's close button (the page asks about unsaved changes, then calls remove). */
  close(tab: T): void;
  /** A group's "+": what can be made in it (the group is focused first). */
  plus(anchor: HTMLElement): void;
  /** The layout changed: remember it. */
  changed(): void;
  /** A tab's element was made: the page may listen on it (a cell dropped on an app page's tab). */
  tabMade?(tab: T, element: HTMLElement): void;
}

export interface GroupInfo<T> {
  tabs: T[];
  active: T | null;
  focused: boolean;
}

export interface Groups<T> {
  element: HTMLElement;
  /** Open a tab in the focused group (or group `at`, from 0), after the one in front, and show it. */
  add(tab: T, at?: number): void;
  /** Show a tab in its group and focus that group. */
  show(tab: T): void;
  remove(tab: T): void;
  /** Move a tab into group `at` (from 0), at `index` (default: the end). */
  move(tab: T, at: number, index?: number): void;
  /** A new group beside group `at` (default: the tab's own), holding the tab. False: it cannot (the
   *  tab is its group's only one, and the split would be beside that same group). */
  split(tab: T, side: Side, at?: number): boolean;
  /** Move a tab left or right in its row. */
  reorder(tab: T, by: -1 | 1): void;
  focusGroup(at: number): void;
  /** The focused group, from 0 in reading order. */
  focusedIndex(): number;
  indexOf(tab: T): number;
  list(): GroupInfo<T>[];
  /** Every tab, group by group. */
  tabs(): T[];
  /** The focused group's controls (the page fills them). */
  controls(): HTMLElement;
  /** Draw the tabs again (a title or an unsaved dot changed). */
  redraw(): void;
  save(keyOf: (tab: T) => number | null): SavedLayout;
  /** Put the open tabs back where a saved layout had them (the others go to the first group). */
  restore(saved: SavedLayout, tabOf: (key: number) => T | undefined): void;
}

const LABELS: Record<Zone, string> = { left: "Split left", right: "Split right", up: "Split up", down: "Split down", center: "Move here" };

export function mountGroups<T extends TabLike>(host: GroupsHost<T>): Groups<T> {
  const element = h("div", { class: "wb-groups" });
  let counter = 0;
  const tabEls = new Map<T, HTMLElement>();
  let root: Node<T> = { group: makeGroup() };
  let focused = (root as { group: Group<T> }).group;
  let reported: T | null | undefined;
  let reportedGroup: Group<T> | null = null;

  // ----- the tree

  function leaves(node: Node<T> = root): Group<T>[] {
    return "group" in node ? [node.group] : node.children.flatMap((c) => leaves(c));
  }

  function parentOf(target: Group<T>, node: Node<T> = root): { split: Split<T>; index: number } | null {
    if ("group" in node) return null;
    for (const [index, child] of node.children.entries()) {
      if ("group" in child && child.group === target) return { split: node, index };
      const found = parentOf(target, child);
      if (found) return found;
    }
    return null;
  }

  /** One child left: the split is that child; a split inside one of the same direction joins it. */
  function normalize(node: Node<T>): Node<T> {
    if ("group" in node) return node;
    const children: Node<T>[] = [];
    const sizes: number[] = [];
    node.children.forEach((child, i) => {
      const done = normalize(child);
      const size = node.sizes[i] ?? 1;
      if (!("group" in done) && done.dir === node.dir) {
        const total = done.sizes.reduce((a, b) => a + b, 0) || 1;
        done.children.forEach((c, j) => {
          children.push(c);
          sizes.push((size * (done.sizes[j] ?? 1)) / total);
        });
      } else {
        children.push(done);
        sizes.push(size);
      }
    });
    if (children.length === 1) return children[0]!;
    return { dir: node.dir, children, sizes };
  }

  function groupOf(tab: T): Group<T> | undefined {
    return leaves().find((g) => g.tabs.includes(tab));
  }

  // ----- drawing

  function makeGroup(): Group<T> {
    const tabsEl = h("div", { class: "wb-tabs", role: "tablist", "aria-label": "Open documents" });
    const controls = h("div", { class: "wb-gcontrols" });
    const body = h("div", { class: "wb-gbody" });
    const plus = button("New tab", (e) => host.plus(e.currentTarget as HTMLElement), { icon: "plus", iconOnly: true, class: "ghost wb-tab-new", title: "New tab" });
    plus.setAttribute("aria-haspopup", "menu");
    const el = h("section", { class: "wb-group" }, h("div", { class: "wb-gstrip" }, tabsEl, plus, h("span", { class: "wb-grow" }), controls), body);
    const group: Group<T> = { id: ++counter, tabs: [], active: null, el, tabsEl, controls, body };
    // Captured, so the group is focused before a tab or a button in it acts.
    el.addEventListener("pointerdown", () => focus(group), true);
    el.addEventListener("focusin", () => focus(group));
    tabsEl.addEventListener("keydown", (e) => {
      if (!group.active || (e.key !== "ArrowLeft" && e.key !== "ArrowRight" && e.key !== "Home" && e.key !== "End")) return;
      const at = group.tabs.indexOf(group.active);
      const next = e.key === "Home" ? 0 : e.key === "End" ? group.tabs.length - 1 : (at + (e.key === "ArrowLeft" ? -1 : 1) + group.tabs.length) % group.tabs.length;
      e.preventDefault();
      show(group.tabs[next]!);
      tabEls.get(group.tabs[next]!)?.focus();
    });
    return group;
  }

  function tabEl(tab: T): HTMLElement {
    let el = tabEls.get(tab);
    if (!el) {
      const close = button("Close", (e) => {
        e.stopPropagation();
        host.close(tab);
      }, { icon: "close", iconOnly: true, class: "tab-close" });
      close.addEventListener("pointerdown", (e) => e.stopPropagation());
      el = h("div", { class: "tab-item wb-tab", role: "tab" }, h("span", { class: "wb-tab-icon" }), h("span", { class: "wb-tab-dirty", title: "Unsaved changes" }), h("span", { class: "tab-label" }), close);
      pressable(tab, el);
      host.tabMade?.(tab, el);
      el.addEventListener("auxclick", (e) => {
        if (e.button === 1) host.close(tab);
      });
      tabEls.set(tab, el);
    }
    return el;
  }

  function paint(tab: T, group: Group<T>): HTMLElement {
    const el = tabEl(tab);
    const kind = tabKind(host.kindOf(tab));
    const on = group.active === tab;
    el.className = `tab-item wb-tab mark-${kind?.mark ?? "plain"}${on ? " active" : ""}`;
    if (on) group.el.dataset.mark = kind?.mark ?? "plain";
    el.dataset.kind = kind?.id ?? host.kindOf(tab);
    el.setAttribute("aria-selected", String(on));
    el.tabIndex = on ? 0 : -1;
    const iconHost = el.querySelector(".wb-tab-icon")!;
    if (iconHost.getAttribute("data-icon") !== (kind?.icon ?? "")) {
      iconHost.setAttribute("data-icon", kind?.icon ?? "");
      iconHost.replaceChildren(icon(kind?.icon ?? "code"));
    }
    // The kind's word on its icon (Notebook, Script): the tab's tooltip says it too.
    iconHost.setAttribute("title", kind?.label ?? "");
    el.title = kind?.label ? `${kind.label}: ${tab.path ?? tab.title}` : (tab.path ?? tab.title);
    // The unsaved dot: a character, so the tab's text says it too ("● analysis.ipynb").
    el.querySelector(".wb-tab-dirty")!.textContent = tab.dirty ? "●" : "";
    el.classList.toggle("dirty", tab.dirty);
    el.querySelector(".tab-label")!.textContent = tab.title;
    const close = el.querySelector(".tab-close") as HTMLButtonElement;
    close.setAttribute("aria-label", `Close ${tab.title}`);
    close.title = `Close ${tab.title}`;
    return el;
  }

  function drawTabs(group: Group<T>): void {
    if (!group.active) delete group.el.dataset.mark;
    const els = group.tabs.map((t) => paint(t, group));
    const now = [...group.tabsEl.children];
    if (now.length !== els.length || now.some((el, i) => el !== els[i])) group.tabsEl.replaceChildren(...els);
    const want = group.active?.element;
    if (group.body.firstElementChild !== (want ?? null) || group.body.childElementCount > 1) group.body.replaceChildren(...(want ? [want] : []));
  }

  function render(): void {
    root = normalize(root);
    const build = (node: Node<T>): HTMLElement => {
      if ("group" in node) return node.group.el;
      const el = h("div", { class: `wb-gsplit ${node.dir}` });
      node.children.forEach((child, i) => {
        if (i) el.append(sash(node, i, el));
        const built = build(child);
        built.style.flex = `${node.sizes[i] ?? 1} 1 0px`;
        el.append(built);
      });
      return el;
    };
    const top = build(root);
    top.style.flex = "1 1 0px";
    if (element.firstElementChild !== top || element.childElementCount !== 1) element.replaceChildren(top);
    const all = leaves();
    all.forEach((g, i) => {
      g.el.dataset.group = String(i);
      g.el.setAttribute("aria-label", `Group ${i + 1}`);
      g.el.classList.toggle("focused", g === focused);
      g.el.classList.toggle("only", all.length === 1);
      drawTabs(g);
    });
  }

  function sash(node: Split<T>, i: number, splitEl: HTMLElement): HTMLElement {
    const across = node.dir === "row";
    const el = h("div", { class: `wb-gsash ${node.dir}`, role: "separator", tabindex: 0, "aria-orientation": across ? "vertical" : "horizontal", "aria-label": "Resize groups" });
    const set = (fraction: number): void => {
      const f = Math.max(0.1, Math.min(0.9, fraction));
      const pair = (node.sizes[i - 1] ?? 1) + (node.sizes[i] ?? 1);
      node.sizes[i - 1] = pair * f;
      node.sizes[i] = pair * (1 - f);
      const kids = [...splitEl.children].filter((c) => !c.classList.contains("wb-gsash")) as HTMLElement[];
      kids[i - 1]!.style.flex = `${node.sizes[i - 1]} 1 0px`;
      kids[i]!.style.flex = `${node.sizes[i]} 1 0px`;
      el.setAttribute("aria-valuenow", String(Math.round(f * 100)));
    };
    const fraction = (): number => (node.sizes[i - 1] ?? 1) / ((node.sizes[i - 1] ?? 1) + (node.sizes[i] ?? 1));
    let start = 0;
    let total = 1;
    dragResize(el, {
      dragging: "dragging",
      start: () => {
        const a = el.previousElementSibling!.getBoundingClientRect();
        const b = el.nextElementSibling!.getBoundingClientRect();
        start = across ? a.left : a.top;
        total = across ? b.right - a.left : b.bottom - a.top;
      },
      move: (_dx, _dy, m) => set(((across ? m.clientX : m.clientY) - start) / total),
      end: () => host.changed(),
    });
    el.addEventListener("keydown", (e) => {
      const back = across ? "ArrowLeft" : "ArrowUp";
      const forth = across ? "ArrowRight" : "ArrowDown";
      const by = e.shiftKey ? 0.1 : 0.03;
      if (e.key === back) set(fraction() - by);
      else if (e.key === forth) set(fraction() + by);
      else return;
      e.preventDefault();
      host.changed();
    });
    el.addEventListener("dblclick", () => {
      set(0.5);
      host.changed();
    });
    return el;
  }

  // ----- focus

  /** Tell the page when the focused group or its tab changed (the controls follow both). */
  function report(): void {
    const tab = focused.active;
    if (tab === reported && focused === reportedGroup) return;
    reported = tab;
    reportedGroup = focused;
    host.focused(tab);
  }

  function focus(group: Group<T>): void {
    if (focused !== group) {
      focused.controls.replaceChildren();
      focused = group;
      for (const g of leaves()) g.el.classList.toggle("focused", g === focused);
    }
    report();
  }

  // ----- changes

  /** Take a tab out of its group; an emptied group goes (unless it is the last). */
  function lift(tab: T): Group<T> | undefined {
    const group = groupOf(tab);
    if (!group) return undefined;
    const at = group.tabs.indexOf(tab);
    group.tabs.splice(at, 1);
    if (group.active === tab) group.active = group.tabs[at] ?? group.tabs[at - 1] ?? null;
    if (!group.tabs.length && leaves().length > 1) {
      const was = leaves().indexOf(group);
      const parent = parentOf(group)!;
      parent.split.children.splice(parent.index, 1);
      parent.split.sizes.splice(parent.index, 1);
      root = normalize(root);
      // The group before it takes the focus (the first when it was the first).
      if (focused === group) focused = leaves()[Math.max(0, was - 1)] ?? leaves()[0]!;
    }
    return group;
  }

  function add(tab: T, at?: number): void {
    const group = (at !== undefined ? leaves()[at] : undefined) ?? focused;
    if (group.tabs.includes(tab)) return show(tab);
    lift(tab);
    const after = group.active ? group.tabs.indexOf(group.active) + 1 : group.tabs.length;
    group.tabs.splice(after, 0, tab);
    group.active = tab;
    focused.controls.replaceChildren();
    focused = group;
    render();
    report();
    host.changed();
  }

  function show(tab: T): void {
    const group = groupOf(tab);
    if (!group) return add(tab);
    group.active = tab;
    drawTabs(group);
    focus(group);
    host.changed();
  }

  function remove(tab: T): void {
    if (!groupOf(tab)) return;
    lift(tab);
    tabEls.get(tab)?.remove();
    tabEls.delete(tab);
    render();
    report();
    host.changed();
  }

  function move(tab: T, at: number, index?: number): void {
    const target = leaves()[at];
    if (!target) throw new Error(`There is no group ${at}.`);
    const from = groupOf(tab);
    let place = index ?? target.tabs.length;
    if (from === target) {
      const was = target.tabs.indexOf(tab);
      if (was < place) place -= 1;
    }
    lift(tab);
    place = Math.max(0, Math.min(place, target.tabs.length));
    target.tabs.splice(place, 0, tab);
    target.active = tab;
    focused.controls.replaceChildren();
    focused = target;
    render();
    report();
    host.changed();
  }

  function split(tab: T, side: Side, at?: number): boolean {
    const from = groupOf(tab);
    const target = (at !== undefined ? leaves()[at] : undefined) ?? from;
    if (!target) return false;
    if (from === target && target.tabs.length < 2) return false;
    const made = makeGroup();
    lift(tab);
    made.tabs = [tab];
    made.active = tab;
    const dir = side === "left" || side === "right" ? "row" : "column";
    const before = side === "left" || side === "up";
    const parent = parentOf(target);
    if (parent && parent.split.dir === dir) {
      const size = parent.split.sizes[parent.index] ?? 1;
      parent.split.sizes[parent.index] = size / 2;
      parent.split.children.splice(parent.index + (before ? 0 : 1), 0, { group: made });
      parent.split.sizes.splice(parent.index + (before ? 0 : 1), 0, size / 2);
    } else {
      const pair: Split<T> = { dir, children: before ? [{ group: made }, { group: target }] : [{ group: target }, { group: made }], sizes: [1, 1] };
      if (parent) parent.split.children[parent.index] = pair;
      else root = pair;
    }
    focused.controls.replaceChildren();
    focused = made;
    render();
    report();
    host.changed();
    return true;
  }

  function reorder(tab: T, by: -1 | 1): void {
    const group = groupOf(tab);
    if (!group) return;
    const at = group.tabs.indexOf(tab);
    const to = at + by;
    if (to < 0 || to >= group.tabs.length) return;
    group.tabs.splice(at, 1);
    group.tabs.splice(to, 0, tab);
    drawTabs(group);
    host.changed();
  }

  // ----- dragging a tab

  /** A press on a tab shows it; carried six pixels, it is dragged (Escape puts it back). */
  function pressable(tab: T, el: HTMLElement): void {
    let drag: Drag | null = null;
    let key: ((k: KeyboardEvent) => void) | null = null;
    dragPointer(el, {
      onStart: (_down, pointer) => {
        if (!groupOf(tab)) return false;
        drag = null;
        key = (k) => {
          if (k.key !== "Escape") return;
          k.preventDefault();
          pointer.cancel();
        };
        document.addEventListener("keydown", key, true);
        return undefined;
      },
      onMove: (dx, dy, m) => {
        if (!drag && Math.hypot(dx, dy) < 6) return;
        drag ??= startDrag(tab);
        drag.over(m.clientX, m.clientY);
      },
      onEnd: (up) => {
        if (key) document.removeEventListener("keydown", key, true);
        if (!up) drag?.cancel();
        else if (drag) drag.drop(up.clientX, up.clientY);
        else show(tab);
      },
    });
  }

  interface Drag {
    over: (x: number, y: number) => void;
    drop: (x: number, y: number) => void;
    cancel: () => void;
  }

  function startDrag(tab: T): Drag {
    const from = groupOf(tab)!;
    const kind = tabKind(host.kindOf(tab));
    const lifted = tabEl(tab);
    lifted.classList.add("lifted");
    const ghost = h("div", { class: `wb-tab-ghost mark-${kind?.mark ?? "plain"}`, "aria-hidden": "true" }, icon(kind?.icon ?? "code"), h("span", {}, tab.title));
    document.body.append(ghost);
    document.body.classList.add("wb-dragging-tab");
    const marker = h("div", { class: "wb-tab-insert", "aria-hidden": "true" });
    const compass = h("div", { class: "wb-compass", "aria-hidden": "true" }, ...(["up", "left", "center", "right", "down"] as Zone[]).map((z) => h("i", { "data-zone": z })));
    const zoneEl = h("div", { class: "wb-drop-zone" });
    const overlay = h("div", { class: "wb-drop", "aria-hidden": "true" }, zoneEl, compass);
    let target: { group: Group<T>; index: number } | { group: Group<T>; zone: Zone | null } | null = null;

    const clear = (): void => {
      marker.remove();
      overlay.remove();
      target = null;
    };
    const groupAt = (x: number, y: number): Group<T> | undefined => {
      const at = document.elementFromPoint(x, y);
      const el = at?.closest(".wb-group");
      return leaves().find((g) => g.el === el);
    };
    const insertAt = (group: Group<T>, x: number): number => {
      const els = group.tabs.map((t) => tabEls.get(t)!);
      const at = els.findIndex((el) => {
        const box = el.getBoundingClientRect();
        return x < box.left + box.width / 2;
      });
      return at < 0 ? group.tabs.length : at;
    };
    const zoneAt = (group: Group<T>, x: number, y: number): Zone => {
      for (const square of compass.querySelectorAll<HTMLElement>("i")) {
        const box = square.getBoundingClientRect();
        if (box.width && x >= box.left - 3 && x <= box.right + 3 && y >= box.top - 3 && y <= box.bottom + 3) return square.dataset.zone as Zone;
      }
      const box = group.body.getBoundingClientRect();
      const fx = (x - box.left) / box.width;
      const fy = (y - box.top) / box.height;
      const near: [Zone, number][] = [["left", fx], ["right", 1 - fx], ["up", fy], ["down", 1 - fy]];
      near.sort((a, b) => a[1] - b[1]);
      return near[0]![1] < 0.3 ? near[0]![0] : "center";
    };
    const allowed = (group: Group<T>, zone: Zone): boolean => (group === from ? zone !== "center" && from.tabs.length > 1 : true);

    const over = (x: number, y: number): void => {
      ghost.style.left = `${x + 10}px`;
      ghost.style.top = `${y + 6}px`;
      const group = groupAt(x, y);
      if (!group) return clear();
      const inStrip = !!document.elementFromPoint(x, y)?.closest(".wb-gstrip");
      if (inStrip) {
        overlay.remove();
        const index = insertAt(group, x);
        target = { group, index };
        const els = group.tabs.map((t) => tabEls.get(t)!);
        const strip = group.tabsEl.getBoundingClientRect();
        const edge = index < els.length ? els[index]!.getBoundingClientRect().left : els.length ? els[els.length - 1]!.getBoundingClientRect().right : strip.left;
        marker.style.left = `${edge - strip.left + group.tabsEl.scrollLeft - 1}px`;
        if (marker.parentElement !== group.tabsEl) group.tabsEl.append(marker);
        return;
      }
      marker.remove();
      if (overlay.parentElement !== group.el) group.el.append(overlay);
      const zone = zoneAt(group, x, y);
      const ok = allowed(group, zone);
      target = { group, zone: ok ? zone : null };
      overlay.dataset.zone = ok ? zone : "";
      zoneEl.textContent = ok ? LABELS[zone] : "";
      for (const square of compass.querySelectorAll<HTMLElement>("i")) square.classList.toggle("on", ok && square.dataset.zone === zone);
    };
    const end = (): void => {
      clear();
      ghost.remove();
      lifted.classList.remove("lifted");
      document.body.classList.remove("wb-dragging-tab");
    };
    return {
      over,
      cancel: end,
      drop: (x, y) => {
        over(x, y);
        const chosen = target;
        end();
        if (!chosen) return;
        const at = leaves().indexOf(chosen.group);
        if ("index" in chosen) move(tab, at, chosen.index);
        else if (chosen.zone === "center") move(tab, at);
        else if (chosen.zone) split(tab, chosen.zone, at);
      },
    };
  }

  // ----- saving

  function save(keyOf: (tab: T) => number | null): SavedLayout {
    const walk = (node: Node<T>): SavedNode => {
      if ("group" in node) {
        const kept = node.group.tabs.filter((t) => keyOf(t) !== null);
        return { tabs: kept.map((t) => keyOf(t)!), active: node.group.active ? kept.indexOf(node.group.active) : -1 };
      }
      return { dir: node.dir, children: node.children.map(walk), sizes: node.sizes.map((s) => Math.round(s * 1000) / 1000) };
    };
    return { root: walk(root), focused: leaves().indexOf(focused) };
  }

  function restore(saved: SavedLayout, tabOf: (key: number) => T | undefined): void {
    const every = leaves().flatMap((g) => g.tabs);
    const placed = new Set<T>();
    const made: Group<T>[] = [];
    const walk = (node: SavedNode): Node<T> | null => {
      if ("tabs" in node) {
        const group = makeGroup();
        for (const key of node.tabs) {
          const tab = tabOf(key);
          if (tab && every.includes(tab) && !placed.has(tab)) {
            placed.add(tab);
            group.tabs.push(tab);
          }
        }
        if (!group.tabs.length) return null;
        group.active = group.tabs[node.active] ?? group.tabs[0] ?? null;
        made.push(group);
        return { group };
      }
      const kids: Node<T>[] = [];
      const sizes: number[] = [];
      node.children.forEach((c, i) => {
        const built = walk(c);
        if (built) {
          kids.push(built);
          sizes.push(node.sizes[i] ?? 1);
        }
      });
      return kids.length ? { dir: node.dir, children: kids, sizes } : null;
    };
    const built = walk(saved.root);
    if (!built) return;
    root = built;
    const first = leaves()[0]!;
    for (const tab of every) if (!placed.has(tab)) first.tabs.push(tab);
    focused = leaves()[saved.focused] ?? first;
    render();
    report();
    host.changed();
  }

  render();

  return {
    element,
    add,
    show,
    remove,
    move,
    split,
    reorder,
    focusGroup: (at) => {
      const group = leaves()[at];
      if (!group) throw new Error(`There is no group ${at}.`);
      focus(group);
      (tabEls.get(group.active!) ?? group.el).focus?.();
    },
    focusedIndex: () => leaves().indexOf(focused),
    indexOf: (tab) => {
      const group = groupOf(tab);
      return group ? leaves().indexOf(group) : -1;
    },
    list: () => leaves().map((g) => ({ tabs: [...g.tabs], active: g.active, focused: g === focused })),
    tabs: () => leaves().flatMap((g) => g.tabs),
    controls: () => focused.controls,
    redraw: () => {
      for (const g of leaves()) drawTabs(g);
    },
    save,
    restore,
  };
}
