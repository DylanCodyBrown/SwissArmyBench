/**
 * nav.ts: getting around, the same on every page and window (the owner, 2026-11-16: "there is no
 * navigation in the app to get back to the home page or go back anywhere. No back buttons."). [SHARED]
 *
 *   [MARK]    every page's top-left mark: a link to /workspace named "Home". On the home page it shows the
 *             grids, closing what is over them; in any other window it brings the home window forward
 *             (the window named sab-home), or opens it. Alt+Home does the same everywhere.
 *   [ADDRESS] a view the user moves to is in the address (go: history.pushState); a move the app makes by
 *             itself replaces the entry. Back and Forward are the browser's: popstate hands the address
 *             to the page (onPlace) and to the layers, the dialogs with views of their own (Connections,
 *             Settings), each by its `open=` key. The token is never in the address (the cookie keeps the
 *             session), so a reload keeps the view.
 *   [DIALOGS] every other dialog (dom.openDialog) pushes an entry of its own at the same address: Back
 *             closes it, and closing it takes the entry away again.
 *   [BACK]    backButton(): "← <where it goes>": back in the history when that is where it came from,
 *             else to that place (a reload, a bookmark).
 *   [CRUMBS]  crumbs(): the trail past one level, each crumb a link.
 *   [TITLE]   setTitle(page, where): "Blades · Warehouse › sales › orders", "Workbench · sales.ipynb".
 *   [AGENT]   the `navigate` notice (app_navigate): home, back, forward, a rail's area, or a view's address.
 *   [RAIL]    rail.ts, the areas down the left: onAddress (its current mark follows the address),
 *             homeWindow and namedWindow (another window brought forward), hasLayer, setAreaRunner.
 *
 * Every history move goes through one queue: history.back() lands later, so a push made right after it
 * (a dialog closed, another opened) waits for it instead of being the entry Back takes away.
 */
import { onNotice, type Notice } from "./api";
import { h, setDialogHook, toast } from "./dom";

/** What each entry of this tab's history carries (history.state.sab). */
interface Entry {
  /** How many of this app's entries are behind this one: Back stays in the app while n > 0. */
  n: number;
  /** The address and the name of the place this entry was entered from. */
  from?: string;
  fromLabel?: string;
  /** The plain dialogs open at this entry, oldest first. */
  dialogs: string[];
  /** A layer open at this entry: its key and the n of the entry under it (back: reached by pushes). */
  layer?: { key: string; n: number; back: boolean };
}

/** A dialog with views of its own, kept in the address as open=<key> (Connections, Settings). */
export interface Layer {
  isOpen(): boolean;
  /** Open it showing the view in `url` (Forward, a reload, the agent). */
  open(url: URL): void;
  /** It is open: show the view in `url` (Back and Forward inside it). */
  show(url: URL): void;
  /** Close it with no history move (Back took its entries away). */
  dismiss(): void;
}

export type Move = "push" | "replace" | "auto";
export type PageKind = "home" | "catalog" | "workbench" | "steps" | "keys";

/** A layer's words in the address (open=connections&at=form&type=postgres): a page's own view keeps them. */
export const LAYER_PARAMS = ["open", "at", "type", "name"];
export const HOME_WINDOW = "sab-home";
export const HOME_URL = "/workspace";

const load = Math.random().toString(36).slice(2, 8);
let serial = 0;
let queue: Promise<void> = Promise.resolve();
const openDialogs = new Map<string, HTMLDialogElement>();
const popped = new WeakSet<HTMLDialogElement>();
const layers = new Map<string, Layer>();
let placeListener: ((url: URL) => void) | null = null;
const addressListeners: ((url: URL) => void)[] = [];
let areaRunner: ((area: string, newWindow: boolean) => boolean) | null = null;
let homeHere: (() => void) | null = null;
let pageName = "";
let where = "";
let over = "";
// From mountNav until startNav: the page shows the address it was opened with, which is no move of the
// user's (a click just before a reload still counts as one in Chromium).
let starting = false;

// ===== the history =====

function entry(): Entry {
  const sab = (history.state as { sab?: Entry } | null)?.sab;
  return sab && typeof sab.n === "number" ? { ...sab, dialogs: sab.dialogs ?? [] } : { n: 0, dialogs: [] };
}

/** The address now: the path and the query (never the fragment). */
export function here(): string {
  return location.pathname + location.search;
}

function normal(url: string): string {
  const u = new URL(url, location.href);
  return u.pathname + u.search;
}

function enqueue(op: () => void | Promise<void>): Promise<void> {
  queue = queue.then(op).catch((e: unknown) => console.warn(e));
  return queue;
}

/** Until the browser has moved (its popstate), or a moment if it does not move (nothing behind). */
function moved(): Promise<void> {
  return new Promise((done) => {
    const finish = (): void => {
      window.removeEventListener("popstate", finish);
      window.clearTimeout(timer);
      done();
    };
    const timer = window.setTimeout(finish, 700);
    window.addEventListener("popstate", finish);
  });
}

/** A click or a key just now: a move the user made (pushed), not one the app made by itself (replaced). */
function byUser(): boolean {
  return (navigator as Navigator & { userActivation?: { isActive: boolean } }).userActivation?.isActive ?? true;
}

/** The name of the place in front, for the next entry's Back. */
function label(): string {
  const now = over || where || pageName;
  return now.split(" › ").pop() ?? now;
}

/** Go to `url` (a path and query of this page): pushed when the user moved (`auto`), replaced when the
 *  app did. The same address does nothing. */
export function go(url: string, how: Move = "auto"): Promise<void> {
  const fromLabel = label();
  const push = how === "push" || (how === "auto" && !starting && byUser());
  return enqueue(() => write(normal(url), push, fromLabel));
}

/** The entry for `target`: a new one (push) or this one changed. A layer's entries carry where it
 *  started, so closing it goes back past all of them. */
function write(target: string, push: boolean, fromLabel: string): void {
  if (target === here()) return;
  const now = entry();
  const was = new URLSearchParams(location.search).get("open");
  const key = new URL(target, location.href).searchParams.get("open");
  // (Kept on a replace too: a reload's page writes its own view first, then the layer's words again.)
  const layer = !key ? undefined : now.layer?.key === key && (key === was || !push) ? now.layer : { key, n: now.n, back: push && key !== was };
  // A dialog closed a moment ago (its close event not yet heard: "Show" closes it and goes to the
  // Sandbox at once) is not carried into the new entry, so its close takes nothing away from it.
  const dialogs = now.dialogs.filter((id) => openDialogs.get(id)?.open);
  const next: Entry = push ? { n: now.n + 1, from: here(), fromLabel, dialogs, layer } : { ...now, dialogs, layer };
  if (push) history.pushState({ sab: next }, "", target);
  else history.replaceState({ sab: next }, "", target);
  told();
}

/** The address changed (a move, Back, Forward, a layer closed): the rail's mark follows it. */
export function onAddress(listener: (url: URL) => void): void {
  addressListeners.push(listener);
}

function told(): void {
  const url = new URL(location.href);
  for (const listener of addressListeners) listener(url);
}

/** Go to `url` and show it, as Back and Forward show an address (the agent's named views). */
export function visit(url: string, how: Move = "push"): void {
  void go(url, how).then(() => apply());
}

export function canGoBack(): boolean {
  return entry().n > 0;
}

/** The browser's Back, kept inside the app: at the first entry it does nothing. */
export function back(): void {
  void enqueue(() => {
    if (!canGoBack()) return;
    history.back();
    return moved();
  });
}

export function forward(): void {
  void enqueue(() => {
    history.forward();
    return moved();
  });
}

/** Back to `url` when that is the entry this one came from, else go there (a reload, a bookmark). */
export function backTo(url: string): void {
  void enqueue(() => {
    const now = entry();
    if (now.n > 0 && now.from === normal(url)) {
      history.back();
      return moved();
    }
    write(normal(url), true, label());
    apply();
  });
}

/** The address now with `params` set (null: taken out). */
export function withParams(params: Record<string, string | null>, path = location.pathname): string {
  const search = new URLSearchParams(path === location.pathname ? location.search : "");
  for (const [key, value] of Object.entries(params)) {
    if (value === null) search.delete(key);
    else search.set(key, value);
  }
  const text = search.toString();
  return `${path}${text ? `?${text}` : ""}`;
}

// ===== layers: dialogs with views of their own (open=<key>) =====

export function registerLayer(key: string, layer: Layer): void {
  layers.set(key, layer);
}

/** Whether this page has the layer `key` (Settings, Connections): the rail opens it here, else at home. */
export function hasLayer(key: string): boolean {
  return layers.has(key);
}

/** Open the layer `key` at its first view, its address pushed (the rail's Settings and Connections);
 *  the page under it stays as it is. */
export function openLayer(key: string): void {
  const layer = layers.get(key);
  if (!layer || layer.isOpen()) return;
  const url = withParams({ open: key, at: null, type: null, name: null });
  void go(url, "push").then(() => layer.open(new URL(url, location.href)));
}

/** The layer open now (its dialog on screen), or null: a page's own move keeps its words only then. */
export function layerShown(): string | null {
  for (const [key, layer] of layers) if (layer.isOpen()) return key;
  // Starting: the layer the address names opens once the page is ready (startNav); its words stay.
  const named = new URLSearchParams(location.search).get("open");
  return starting && named && layers.has(named) ? named : null;
}

/** The layer `key` was opened by the user: its address (`params`, open=key among them) pushed. */
export function layerOpened(key: string, params: Record<string, string | null> = {}): void {
  void go(withParams({ ...params, open: key }), "push");
}

/** The layer `key` closed by its own Close, Escape or ×: back past its entries, or (opened from the
 *  address) its words taken out of it. `keys`: its own parameters besides open. */
export function layerClosed(key: string, keys: string[]): void {
  over = "";
  drawTitle();
  void enqueue(() => {
    if (new URLSearchParams(location.search).get("open") !== key) return;
    const now = entry();
    if (now.layer?.key === key && now.layer.back && now.n > now.layer.n) {
      history.go(now.layer.n - now.n);
      return moved();
    }
    const url = new URL(location.href);
    for (const k of ["open", ...keys]) url.searchParams.delete(k);
    history.replaceState({ sab: { ...now, layer: undefined } }, "", url.pathname + url.search);
    told();
  });
}

/** A layer's dialog: closed by its own Close, Escape or ×, its entries go (layerClosed); `closed` runs
 *  however it closes. */
export function watchLayerDialog(dialog: HTMLDialogElement, key: string, keys: string[], closed: () => void): void {
  dialog.addEventListener(
    "close",
    () => {
      closed();
      if (!popped.has(dialog)) layerClosed(key, keys);
    },
    { once: true },
  );
}

/** Close a dialog because the address no longer has it (Back): no history move of its own. */
export function dismissDialog(dialog: HTMLDialogElement): void {
  popped.add(dialog);
  dialog.close();
  dialog.remove();
}

// ===== plain dialogs: Back closes the one on top =====

function track(dialog: HTMLDialogElement): void {
  const id = `${load}.${++serial}`;
  openDialogs.set(id, dialog);
  const fromLabel = label();
  void enqueue(() => {
    if (!openDialogs.has(id)) return; // closed before its entry was made
    const now = entry();
    history.pushState({ sab: { ...now, n: now.n + 1, from: here(), fromLabel, dialogs: [...now.dialogs, id] } }, "", here());
  });
  dialog.addEventListener(
    "close",
    () => {
      openDialogs.delete(id);
      if (popped.has(dialog)) return; // Back closed it: its entry is gone already
      void enqueue(() => {
        const now = entry();
        if (now.dialogs[now.dialogs.length - 1] === id && now.n > 0) {
          history.back();
          return moved();
        }
        if (now.dialogs.includes(id)) history.replaceState({ sab: { ...now, dialogs: now.dialogs.filter((d) => d !== id) } }, "", here());
      });
    },
    { once: true },
  );
}

/** The browser moved (Back, Forward, a mouse's back button): every part follows the address. */
function apply(): void {
  const now = entry();
  for (const [id, dialog] of [...openDialogs].reverse()) {
    if (now.dialogs.includes(id)) continue;
    popped.add(dialog);
    openDialogs.delete(id);
    dialog.close();
  }
  // Forward onto a dialog that is gone (its work went with it): the entry is the page under it.
  if (now.dialogs.some((id) => !openDialogs.has(id))) {
    history.replaceState({ sab: { ...now, dialogs: now.dialogs.filter((id) => openDialogs.has(id)) } }, "", here());
  }
  const url = new URL(location.href);
  const key = url.searchParams.get("open");
  for (const [k, layer] of layers) {
    if (k === key) {
      if (layer.isOpen()) layer.show(url);
      else layer.open(url);
    } else if (layer.isOpen()) {
      over = "";
      layer.dismiss();
    }
  }
  if (!key) {
    over = "";
    drawTitle();
  }
  placeListener?.(url);
  told();
}

// ===== the page's part =====

/** Each page's start: its kind (for the agent's moves), how it shows an address, and what Home is when
 *  this is the home page. The address it was opened with is shown once the page is ready (start). */
export function mountNav(kind: PageKind, options: { show?: (url: URL) => void; home?: () => void } = {}): void {
  starting = true;
  placeListener = options.show ?? null;
  homeHere = options.home ?? null;
  if (kind === "home") window.name = HOME_WINDOW; // another window's mark finds this one by its name
  // This tab's first entry of the app (a reload keeps the one it had).
  if (!(history.state as { sab?: Entry } | null)?.sab) history.replaceState({ sab: { n: 0, dialogs: [] } }, "", here());
  else if (entry().dialogs.length) history.replaceState({ sab: { ...entry(), dialogs: [] } }, "", here());
  setDialogHook(track);
  window.addEventListener("popstate", () => apply());
  // Before an editor sees it (Monaco takes Home): Alt+Home is Home everywhere.
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.altKey && e.key === "Home" && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        goHome();
      }
    },
    true,
  );
  onNotice((notice) => agentMove(kind, notice));
}

/** The page is ready: the layer its address names opens (a reload, a bookmark, Forward). */
export function startNav(url: URL = new URL(location.href)): void {
  // After the moves already asked for while starting (they replace), the user's moves push again.
  void enqueue(() => {
    starting = false;
  });
  const key = url.searchParams.get("open");
  const layer = key ? layers.get(key) : undefined;
  if (!layer || layer.isOpen()) return;
  // Its words back in the address the page wrote meanwhile (its own view's), in this entry's place.
  void enqueue(() => {
    const now = new URL(location.href);
    for (const k of LAYER_PARAMS) {
      const value = url.searchParams.get(k);
      if (value === null) now.searchParams.delete(k);
      else now.searchParams.set(k, value);
    }
    write(now.pathname + now.search, false, label());
  });
  layer.open(url);
}

/** Home: the grids, on the home page; any other window brings the home window forward, or opens it. */
export function goHome(): void {
  if (homeHere) {
    homeHere();
    return;
  }
  const found = homeWindow();
  if (!found) return;
  if (found.fresh || found.win === window) found.win.location.href = HOME_URL;
  // The grids in front there (the rail's Grids: what is over them closes), as its own mark does.
  else found.win.postMessage({ sab: "area", area: "grids" }, location.origin);
  found.win.focus();
}

/** Another window of the app, by its name: the one found (`fresh`: just opened, still blank), or null
 *  when the browser blocked it (said in a toast). This window itself when it has that name. */
export interface Found {
  win: Window;
  fresh: boolean;
}

/** The home window: the window that opened this one (or the one that opened it), so no new window is
 *  asked for and it works for the agent's nav.home too, with no click to allow a pop-up; else by name. */
export function homeWindow(): Found | null {
  let up: Window | null = window.opener as Window | null;
  for (let hops = 0; up && hops < 5; hops += 1) {
    try {
      if (!up.closed && up.name === HOME_WINDOW && up.location.origin === location.origin) return { win: up, fresh: false };
      up = up.opener as Window | null;
    } catch {
      break; // another site's window: not ours
    }
  }
  // Never this window instead (unless it is the home window's tab): a Workbench would lose its kernels.
  return namedWindow(HOME_WINDOW, "The browser blocked the home window: allow pop-ups for this address.");
}

/** The window named `name`, open or opened (blank: `fresh`); null when the browser blocked it. */
export function namedWindow(name: string, blocked = "The browser blocked the new window: allow pop-ups for this address."): Found | null {
  if (window.name === name) return { win: window, fresh: false };
  const win = window.open("", name);
  if (!win) {
    toast(blocked, "error");
    return null;
  }
  try {
    return { win, fresh: win.location.href === "about:blank" };
  } catch {
    return { win, fresh: true }; // not readable: not one of ours yet
  }
}

/** The mark: the window's icon, drawn small, a link home. */
export function appMark(): HTMLAnchorElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = '<path d="M42 23h16v19h19v16H58v19H42V58H23V42h19z"/>';
  return h(
    "a",
    {
      class: "app-mark",
      href: HOME_URL,
      title: "Home (Alt+Home)",
      "aria-label": "Home",
      onclick: (e: MouseEvent) => {
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return; // a new tab, as links do
        e.preventDefault();
        goHome();
      },
    },
    svg,
  );
}

/** "← Connections": back to `url` (see backTo), named for where it goes. */
export function backButton(to: string, url: string, then?: () => void): HTMLButtonElement {
  return h(
    "button",
    {
      type: "button",
      class: "btn back-btn",
      title: `Back to ${to} (Alt+Left)`,
      "aria-label": `Back to ${to}`,
      onclick: () => {
        backTo(url);
        then?.();
      },
    },
    h("span", { class: "back-arrow", "aria-hidden": "true" }, "←"),
    h("span", { class: "btn-label" }, to),
  );
}

/** The trail, past one level: each crumb a link to its place (the last one is the place itself). */
export function crumbs(trail: { label: string; url?: string }[]): HTMLElement {
  const list = h("ol", {});
  trail.forEach((crumb, i) => {
    const last = i === trail.length - 1;
    list.append(
      h(
        "li",
        {},
        last || !crumb.url
          ? h("span", { "aria-current": last ? "page" : undefined }, crumb.label)
          : h(
              "a",
              {
                href: crumb.url,
                onclick: (e: MouseEvent) => {
                  if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
                  e.preventDefault();
                  visit(crumb.url!);
                },
              },
              crumb.label,
            ),
      ),
    );
  });
  return h("nav", { class: "crumbs", "aria-label": "Breadcrumb" }, list);
}

// ===== titles: the page, then the place =====

function drawTitle(): void {
  document.title = [pageName, over || where].filter(Boolean).join(" · ") || "Home";
}

/** The window's title: `page` first ("Blades", "Workbench"; none on the home page), then the place. */
export function setTitle(page: string, place = ""): void {
  pageName = page;
  where = place;
  drawTitle();
}

/** A layer's place over the page ("Connections › Add connection"); "" when it closes. */
export function setOverTitle(place: string): void {
  over = place;
  drawTitle();
}

// ===== the agent (app_navigate) =====

type NavNotice = Notice & { window?: string; to?: string; grid?: string; catalog?: string; schema?: string; table?: string; new_window?: boolean };

/** Where the agent's named view is, as an address of this page ("" when this page has no such view). */
function agentUrl(n: NavNotice): string {
  const layer: Record<string, Record<string, string | null>> = {
    settings: { open: "settings", at: null, type: null, name: null },
    connections: { open: "connections", at: null, type: null, name: null },
    add_connection: { open: "connections", at: "types", type: null, name: null },
    add_api: { open: "connections", at: "api", type: null, name: null },
  };
  if (n.to && layer[n.to]) return withParams(layer[n.to]!);
  const home = { open: null, at: null, type: null, name: null };
  if (n.to === "sandbox" || n.to === "diagram" || n.to === "query") return withParams({ ...home, view: n.to }, HOME_URL);
  if (n.to === "grid" && n.grid) return `/g/${encodeURIComponent(n.grid)}`;
  if (n.to === "catalog") return withParams({ catalog: n.catalog ?? null, database: null, schema: n.schema ?? null, table: n.table ?? null, blade: null }, "/catalog");
  if (n.to === "blade") return withParams({ blade: n.name ?? "" }, "/catalog");
  if (n.to === "new_blade") return withParams({ blade: "" }, "/catalog");
  return "";
}

/** The rail's areas, run as its click runs them (rail.ts): true when `area` is one. */
export function setAreaRunner(run: (area: string, newWindow: boolean) => boolean): void {
  areaRunner = run;
}

function agentMove(kind: PageKind, notice: Notice): void {
  const n = notice as NavNotice;
  if (n.type !== "navigate" || n.window !== kind) return;
  if (n.to === "home" || n.to === "grids") goHome(); // the rail's Grids is home (the mark)
  else if (n.to === "back") back();
  else if (n.to === "forward") forward();
  else if (n.to && areaRunner?.(n.to, n.new_window === true)) return; // a rail's area, here or brought forward
  else {
    const url = agentUrl(n);
    if (url) visit(url);
  }
}
