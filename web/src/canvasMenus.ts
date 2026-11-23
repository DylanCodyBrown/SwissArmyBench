/**
 * canvasMenus.ts: the Canvas's menus. Moved out of canvasPage.ts along its own heading (the craft review of
 * 2026-11-22), unchanged. [WIRE]
 *
 *   [MENU]     the app's one menu (dom.ts showEntries) in the Canvas's look, with its keys, ticks and submenus,
 *              closed with the page's other floating panels (a press outside, a pick)
 *   [NODE]     right-click a container: Insert widget ▸, Insert container, Scrollable, Resizable, Delete; a
 *              widget: Edit, Replace ▸, Delete; read-only: the run group only
 *   [RUN]      the run group at the bottom of every right-click menu and Play's ▾: Play, Launch, Launch with
 *              the Performance Analyzer, Share… while launched, Builds…, Export…
 *   [WIDGETS]  every widget of the framework, grouped, with search
 */
import { openAnalyzer, openBuilds } from "./canvasBuilds";
import type { CanvasNode as Node, CanvasState as State } from "./canvasPage";
import { clear, h, type MenuEntry, showEntries } from "./dom";
import { openWidgets } from "./rail";
import { openShareDialog, type ShareableApp } from "./shareApp";
import { headingElement, headingOf } from "./widgetPacks";
import type { WidgetEntry } from "./widgetPage";

/** What the menus ask of the page: the canvas, a command sent, a widget inserted, and Play, Launch and Export. */
export interface MenusHost {
  editable: () => boolean;
  send: (kind: string, body: Record<string, unknown>) => Promise<State | null>;
  insert: (name: string, parent: string | null) => Promise<void>;
  grouped: () => WidgetEntry[];
  playing: () => boolean;
  play: () => Promise<void>;
  stopPlay: () => void;
  launch: (analyzer?: boolean) => Promise<void>;
  stopLaunch: () => Promise<void>;
  exportApp: () => Promise<void>;
  buildsHost: Parameters<typeof openBuilds>[1];
  readonly state: State | null;
  readonly page: string;
  readonly launched: boolean;
}

export function canvasMenus(host: MenusHost) {
  let floatingOpen: HTMLElement[] = [];
  function closeFloating(): void {
    for (const f of floatingOpen) f.remove();
    floatingOpen = [];
  }
  function floating(element: HTMLElement, x: number, y: number, above = false, keep = false): void {
    if (!keep) closeFloating();
    document.body.append(element);
    floatingOpen.push(element);
    const r = element.getBoundingClientRect();
    element.style.left = `${Math.min(x, window.innerWidth - r.width - 8)}px`;
    element.style.top = `${above ? Math.max(8, y - r.height) : Math.min(y, window.innerHeight - r.height - 8)}px`;
  }
  document.addEventListener("pointerdown", (e) => {
    if (!(e.target as HTMLElement).closest(".cvs-menu")) closeFloating();
  });

  /** A menu of the Canvas: the app's one menu (dom.ts showEntries: kept inside the window, arrow keys,
   *  Escape) in the Canvas's look, with its keys, ticks and submenus; it closes with the page's other floating
   *  panels (a press outside, a pick). */
  function menu(x: number, y: number, entries: MenuEntry[]): void {
    closeFloating();
    floatingOpen.push(showEntries(x, y, "Canvas", entries, { menu: "cvs-menu", item: "cvs-menu-item", rule: "cvs-menu-sep", heading: false, away: false, closing: closeFloating }));
  }

  /** Play's ▾ (and the run group's middle): Launch, Launch with the Performance Analyzer, the analyzer's window
   *  and Share… while launched, Builds…; Stop instead of Launch while the app is launched. */
  function launchEntries(group: boolean): MenuEntry[] {
    const canvas = host.state?.canvas;
    return [
      host.launched ? { label: "Stop the launched app", group, run: () => void host.stopLaunch() } : { label: "Launch", key: "Ctrl+F5", group, run: () => void host.launch(false) },
      host.launched
        ? { label: "Performance Analyzer", disabled: !canvas, run: () => canvas && openAnalyzer(canvas) }
        : { label: "Launch with the Performance Analyzer", key: "Ctrl+Shift+F5", run: () => void host.launch(true) },
      // Share… (the share-app branch): the launched app's address for others, while it is launched.
      ...(host.launched ? [shareEntry()] : []),
      { label: "Builds…", disabled: !canvas, run: () => canvas && void openBuilds(canvas, host.buildsHost) },
    ];
  }

  /** The run group at the bottom of every right-click menu (the owner, 2026-11-21): Play, Launch, Launch with
   *  the Performance Analyzer, Builds…, Export…, each with its key; Stop instead while the page plays or the app is
   *  launched. */
  function runGroup(after: boolean): MenuEntry[] {
    const playing = host.playing();
    return [
      playing ? { label: "Stop playing", key: "Esc", group: after, run: () => host.stopPlay() } : { label: "Play", key: "F5", group: after, run: () => void host.play() },
      ...launchEntries(false),
      { label: "Export…", key: "Ctrl+Shift+E", run: () => void host.exportApp() },
    ];
  }

  /** The launched app as Share… knows it (the Streamlit extension's share target: the canvas's id). */
  function shareable(): ShareableApp | null {
    return host.state ? { kind: "streamlit", id: host.state.canvas, title: host.state.name } : null;
  }

  /** Share… with the organization (shareApp.ts): offered while the app is launched. */
  function shareEntry(): MenuEntry {
    return { label: "Share…", run: () => { const app = shareable(); if (app) openShareDialog(app); } };
  }

  function nodeMenu(node: Node, e: MouseEvent): void {
    if (!host.editable()) return void menu(e.clientX, e.clientY, runGroup(false));
    if (node.kind === "container") {
      const p = node.props!;
      menu(e.clientX, e.clientY, [
        { label: "Insert widget", sub: (x, y) => widgetMenu(x, y, (name) => void host.insert(name, node.id), true) },
        { label: "Insert container", run: () => void host.send("add_container", { page: host.page, parent: node.id, w: Math.min(200, node.w), h: Math.min(120, node.h) }) },
        { label: "Scrollable", checked: p.scrollable, run: () => void host.send("set_container", { id: node.id, props: { scrollable: !p.scrollable } }) },
        { label: "Resizable by viewers", checked: p.resizable, run: () => void host.send("set_container", { id: node.id, props: { resizable: !p.resizable } }) },
        { label: "Delete", run: () => void host.send("delete", { id: node.id }) },
        ...runGroup(true),
      ]);
      return;
    }
    menu(e.clientX, e.clientY, [
      { label: "Edit widget", run: () => openWidgets(node.widget) },
      { label: "Replace widget", sub: (x, y) => widgetMenu(x, y, (name) => void host.send("replace_widget", { id: node.id, widget: name }), true) },
      { label: "Delete", run: () => void host.send("delete", { id: node.id }) },
      ...runGroup(true),
    ]);
  }

  /** Every widget of the framework, grouped, with search: `pick` takes one. */
  function widgetMenu(x: number, y: number, pick: (name: string) => void, keep = false): void {
    const search = h("input", { type: "search", class: "cvs-menu-search", placeholder: "Search widgets", "aria-label": "Search widgets", "data-no-variables": "" });
    const list = h("div", { class: "cvs-menu-list", role: "menu" });
    const draw = (): void => {
      const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
      clear(list);
      let group = "";
      for (const w of host.grouped().filter((x2) => words.every((word) => `${x2.name} ${x2.description} ${x2.group} ${x2.pack}`.toLowerCase().includes(word)))) {
        const heading = headingOf(w);
        if (heading !== group) {
          group = heading;
          list.append(headingElement("cvs-menu-group", w, false));
        }
        list.append(
          h(
            "button",
            {
              type: "button",
              role: "menuitem",
              class: "cvs-menu-item",
              "data-widget": w.name,
              title: w.description,
              onclick: () => {
                closeFloating();
                pick(w.name);
              },
            },
            h("span", { class: "cvs-check" }),
            h("span", {}, w.name),
          ),
        );
      }
    };
    search.addEventListener("input", draw);
    draw();
    const element = h("div", { class: "cvs-menu cvs-widget-menu", role: "dialog", "aria-label": "Insert widget" }, search, list);
    if (keep) {
      for (const f of floatingOpen.filter((f2) => f2.classList.contains("cvs-widget-menu"))) f.remove();
      floatingOpen = floatingOpen.filter((f2) => !f2.classList.contains("cvs-widget-menu"));
    }
    floating(element, x, y, false, keep);
    search.focus();
  }

  return { closeFloating, floating, menu, launchEntries, runGroup, shareable, nodeMenu, widgetMenu };
}
