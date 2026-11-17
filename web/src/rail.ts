/**
 * rail.ts: the areas down the left of every page and window (the owner, 2026-11-16: "As much as I hate
 * to say it, this app needs a navigation pane somehow."; a slim icon rail, as VS Code's Activity Bar).
 * [SHARED]
 *
 *   [AREAS]   Grids (the home page's tabbed grids; the mark goes Home, the Start view), Visualizations, ERD, Notebooks,
 *             Scripts, Apps (the Streamlit canvas), Blades, Connections, Session (what the agent made this
 *             session, a count of what is new on its icon: sessionPage.ts), and Settings pinned at the
 *             bottom. An icon each, its name in a tip on hover and on keyboard focus; Notebooks,
 *             Scripts and Apps wear their kind colours. The mark stays in each page's top row.
 *   [PAGES]   Every area lands on a page, never a dialog or a menu (the owner, 2026-11-16: "clicking the
 *             rail should land on a page not open a form"): the grids, Visualizations, the ERD, a kind's
 *             landing page in the Workbench (workbenchLanding.ts), the blades page, the Connections page
 *             and the Settings page (areaPage.ts, over the page you are on: open=connections,
 *             open=settings).
 *   [GO]      A click is a navigation like any other (nav.ts): an area this page shows is pushed, so
 *             Back, Forward and a reload work. Connections and Settings show their pages where the page
 *             has them. An area another page shows takes this tab there (the owner, 2026-11-16: "the
 *             rail icons is opening a new tab every time instead of navigating the current page"): the
 *             home page for the grids, Visualizations and the ERD; the Workbench for notebooks, scripts and apps
 *             (code still never sits in the grid page); the blades page.
 *   [KINDS]   Notebooks, Scripts and Apps land on that kind's page in the Workbench (?kind=notebook&
 *             view=list): its documents as cards, open ones first; New is on that page's panel, never in
 *             a menu beside the icon (the owner: "get rid of that its duplicated behavior we should only
 *             create things from the panel"). On every area, right-click, Ctrl+click or a middle click:
 *             Open in a new window (for a code area, a Workbench window of its own).
 *   [CURRENT] the area the address names is marked (a bar on the left edge, the icon brighter) with
 *             aria-current="page"; it follows every move (onAddress), Back and Forward too.
 *   [KEYS]    one stop in the Tab order (a toolbar): the arrows move between the areas, Enter goes;
 *             Alt+Home is Home (the Start view) everywhere (nav.ts).
 *   [ALWAYS]  No switch (the owner, 2026-11-16): the rail is the one way to the areas, so the top tabs and
 *             the Application row no longer repeat them.
 *   [AGENT]   app_navigate's areas run here (setAreaRunner), as a click would (new_window too).
 *
 * Another window's area reaches the window that shows it as a message from this origin ({sab: "area"});
 * a window opened for it is given the area in its address (?view=visualizations, ?open=settings, ?kind=script).
 * The Sandbox is Visualizations and the Diagram the ERD (the owner, 2026-11-16): the old ?view=sandbox
 * and ?view=diagram still land there (panes.ts), and the address is replaced with the new word.
 */
import { token } from "./api";
import { h, icon, toast } from "./dom";
import { type Kind, loadKindColours } from "./kindColours";
import { goHome, hasLayer, HOME_URL, layerShown, onAddress, openLayer, type PageKind, setAreaRunner, visit, withParams } from "./nav";
import { loadPanels, onPanels } from "./panels";
import { onUnseen } from "./sessionPage";
import { APIS } from "./apisPage"; // the APIs page's layer, on every page with the rail
import { STRUCTURES } from "./structuresPage"; // the Structures page's layer, the same
import { CODE_APP, codeAppOn } from "./codeAppPage"; // the Power Apps extension's page (a plug-in: shown while it is on)
import "./variablesPage"; // the Variables page's layer, on every page with the rail
import { openMenu } from "./workbenchMenu";

export type Area = "grids" | "visualizations" | "erd" | "notebooks" | "scripts" | "apps" | "blades" | "connections" | "session" | "variables" | "apis" | "structures" | "codeapp" | "settings";

/** The rail's order (domain/navigation.py AREAS holds the same); the last one is pinned at the bottom.
 *  The code areas' icons are their documents' (kindColours.ts kindIcon). */
const AREAS: { area: Area; name: string; icon: string; kind?: Kind; plugin?: () => Promise<boolean> }[] = [
  // In the order of the work (the owner, 2026-11-17: "rearrange the rail to make since. In order of
  // workflow"): where the data comes from, getting and shaping it, web data, tools, building, presenting,
  // then the log.
  { area: "connections", name: "Connections", icon: "plug" },
  { area: "variables", name: "Variables", icon: "variables" }, // this computer's variables (variablesPage.ts)
  { area: "grids", name: "Grids", icon: "grids" },
  { area: "erd", name: "ERD", icon: "diagram" },
  { area: "apis", name: APIS, icon: "apis" }, // the library's APIs, their explorer (apisPage.ts)
  { area: "structures", name: STRUCTURES, icon: "structures" }, // nested data as documents (structuresPage.ts)
  { area: "blades", name: "Blades", icon: "blade" },
  // An extension's area: its plug-in says whether it is on here (hidden until it says so).
  { area: "codeapp", name: CODE_APP, icon: "codeapp", plugin: codeAppOn },
  { area: "notebooks", name: "Notebooks", icon: "notebook", kind: "notebook" },
  { area: "scripts", name: "Scripts", icon: "code", kind: "script" },
  { area: "apps", name: "Apps", icon: "page", kind: "app" },
  { area: "visualizations", name: "Visualizations", icon: "sandbox" },
  { area: "session", name: "Session", icon: "session" }, // what the agent made this session (sessionPage.ts)
  { area: "settings", name: "Settings", icon: "cog" },
];
/** The areas that are a page of the rail's over any page (areaPage.ts), each its own layer (open=<area>). */
const LAYERS: readonly Area[] = ["settings", "connections", "session", "variables", "apis", "structures", "codeapp"];
const isLayer = (name: string | null): name is Area => LAYERS.includes(name as Area);
const isArea = (name: unknown): name is Area => AREAS.some((a) => a.area === name);
const kindOfArea = (area: Area): Kind | undefined => AREAS.find((a) => a.area === area)?.kind;
const areaOfKind = (kind: string | null): Area | null => AREAS.find((a) => a.kind === kind)?.area ?? null;

const LAYER_OFF = { open: null, at: null, type: null, name: null };

let kind: PageKind = "home";
let items: HTMLButtonElement[] = [];

/** The area the address names on this page (null: none, a Workbench with no document of a kind). */
function currentArea(url: URL): Area | null {
  const open = url.searchParams.get("open");
  if (isLayer(open)) return open;
  if (kind === "catalog") return "blades";
  if (kind === "workbench") return areaOfKind(url.searchParams.get("kind"));
  const view = kind === "home" ? url.searchParams.get("view") : null;
  if (view === "visualizations" || view === "sandbox") return "visualizations";
  if (view === "erd" || view === "diagram") return "erd"; // the old words, one release
  if (view === "start") return null; // Home (startView.ts): no area of the rail's
  return "grids"; // the grids (and the steps and Key Finder windows, which are a grid's)
}

/** A home window opened for `area`: the area in its address. */
function arrivalUrl(area: Area): string {
  if (area === "visualizations" || area === "erd") return `${HOME_URL}?view=${area}`;
  if (isLayer(area)) return `${HOME_URL}?open=${area}`;
  return HOME_URL;
}

const withToken = (path: string, more: Record<string, string> = {}): string => {
  const hash = new URLSearchParams({ ...(token ? { token } : {}), ...more }).toString();
  return hash ? `${path}#${hash}` : path;
};

/** A Workbench window of its own for `kind` (the owner's "external tab"), as a popped-out tab's. */
function newKindWindow(k: Kind): void {
  const opened = window.open(withToken(`/workbench?kind=${k}`, { fresh: "1", popped: "1" }), `swissarmybench-workbench-${Date.now()}`, "popup,width=1200,height=800");
  if (opened) opened.focus();
  else toast("The browser blocked the new window: allow pop-ups for this address.", "error");
}


/** The page that shows `area`, at the area's address. */
function pageUrl(area: Area): string {
  const k = kindOfArea(area);
  if (k) return `/workbench?kind=${k}&view=list`; // that kind's landing page
  if (area === "blades") return "/catalog";
  return arrivalUrl(area);
}

/** Go to `area`, as its click does: in this tab (the owner, 2026-11-16: "the rail icons is opening a new
 *  tab every time instead of navigating the current page, the open in new tab is optional"). The page
 *  that shows the area moves here, or this tab goes to it; `newWindow` (right-click, Ctrl+click, a middle
 *  click) opens it in a window of its own instead. */
export function goArea(area: Area, newWindow = false): void {
  const k = kindOfArea(area);
  if (newWindow) {
    if (k) newKindWindow(k);
    else if (!window.open(withToken(pageUrl(area)), "_blank")) toast("The browser blocked the new window: allow pop-ups for this address.", "error");
    return;
  }
  if (k && kind === "workbench") {
    // That kind's landing page, here (the page over it, if one is, makes way).
    visit(withParams({ ...LAYER_OFF, kind: k, view: "list" }));
    return;
  }
  if (kind === "home" && (area === "grids" || area === "visualizations" || area === "erd")) {
    visit(withParams({ ...LAYER_OFF, view: area === "grids" ? null : area }, HOME_URL));
    return;
  }
  if (isLayer(area) && hasLayer(area)) {
    openLayer(area);
    return;
  }
  if (area === "blades" && kind === "catalog") {
    if (layerShown() || new URLSearchParams(location.search).get("open")) visit(withParams(LAYER_OFF)); // the page makes way
    return;
  }
  // Another page shows it: this tab goes there (the Workbench asks first when an edit is unsaved).
  location.assign(withToken(pageUrl(area)));
}

function draw(url: URL): void {
  const now = currentArea(url);
  const stop = now ?? AREAS[0]!.area;
  for (const item of items) {
    const here = item.dataset.area === now;
    item.classList.toggle("current", here);
    if (here) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
    // One stop in the Tab order: the current area's (the arrows reach the others).
    item.tabIndex = item.dataset.area === stop ? 0 : -1;
  }
}

function onKey(e: KeyboardEvent): void {
  const shown = items.filter((i) => !i.hidden);
  const at = shown.indexOf(e.target as HTMLButtonElement);
  if (at < 0 || e.altKey || e.ctrlKey || e.metaKey) return;
  const to = { ArrowDown: at + 1, ArrowRight: at + 1, ArrowUp: at - 1, ArrowLeft: at - 1, Home: 0, End: shown.length - 1 }[e.key];
  if (to === undefined) return;
  e.preventDefault();
  const next = shown[(to + shown.length) % shown.length]!;
  for (const item of items) item.tabIndex = item === next ? 0 : -1;
  next.focus();
}

function item(area: (typeof AREAS)[number]): HTMLButtonElement {
  const grids = area.area === "grids";
  const element = h(
    "button",
    {
      type: "button",
      class: ["nav-rail-item", area.area === "settings" ? "nav-rail-bottom" : "", area.kind ? `nav-rail-kind km-${area.kind}` : ""].filter(Boolean).join(" "),
      "data-area": area.area,
      "aria-label": area.name,
      "aria-keyshortcuts": undefined,
      // Ctrl+click (Cmd+click): a new window, as a link's new tab.
      onclick: (e: MouseEvent) => goArea(area.area, e.ctrlKey || e.metaKey),
    },
    icon(area.icon),
    // The Session icon: what the agent made that the user has not seen yet (sessionPage.ts).
    area.area === "session" ? h("span", { class: "nav-rail-count", "aria-hidden": "true", hidden: true }) : null,
    // The name, on hover and on focus (a `title` would show the same words a second time).
    h("span", { class: "nav-rail-tip", "aria-hidden": "true" }, area.name),
  );
  if (area.plugin) {
    element.hidden = true;
    void area.plugin().then((on) => (element.hidden = !on));
  }
  {
    // A middle click: a new window too (its mousedown would start the browser's autoscroll).
    element.addEventListener("mousedown", (e) => {
      if (e.button === 1) e.preventDefault();
    });
    element.addEventListener("auxclick", (e) => {
      if (e.button !== 1) return;
      e.preventDefault();
      goArea(area.area, true);
    });
    element.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      openMenu(element, area.name, [{ label: "Open in a new window", icon: "popout", run: () => goArea(area.area, true) }], { beside: true });
    });
  }
  return element;
}

/** Each page's composition mounts the rail once (mountNavRail), right after mountNav. */
export function mountNavRail(page: PageKind): void {
  kind = page;
  items = AREAS.map(item);
  const toolbar = h("div", { class: "nav-rail-items", role: "toolbar", "aria-label": "Areas", "aria-orientation": "vertical", onkeydown: onKey }, ...items);
  document.body.prepend(h("nav", { class: "nav-rail", "aria-label": "Areas" }, toolbar));
  document.body.classList.add("has-rail");
  draw(new URL(location.href));
  onAddress(draw);
  // The Session icon's count, and its name with the count for a screen reader.
  const session = items.find((i) => i.dataset.area === "session");
  onUnseen((n) => {
    const count = session?.querySelector<HTMLElement>(".nav-rail-count");
    if (!session || !count) return;
    count.hidden = n === 0;
    count.textContent = n > 99 ? "99+" : String(n);
    session.setAttribute("aria-label", n ? `Session, ${n} new` : "Session");
  });
  setAreaRunner((area, newWindow) => {
    if (!isArea(area)) return false;
    goArea(area, newWindow);
    return true;
  });
  // The rail on or off: the page's width changes, so the grid, Monaco and the canvas measure again.
  onPanels(() => window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize"))));
  void loadPanels();
  void loadKindColours(); // the code areas wear the kind colours chosen in Settings
  // Another window's rail: the area it asked this window for (a message from this origin only).
  window.addEventListener("message", (e: MessageEvent) => {
    const said = e.data as { sab?: unknown; area?: unknown } | null;
    if (e.origin !== location.origin || said?.sab !== "area") return;
    if (said.area === "home") goHome(); // another window's mark: Home (the Start view)
    else if (isArea(said.area)) goArea(said.area);
  });
}
