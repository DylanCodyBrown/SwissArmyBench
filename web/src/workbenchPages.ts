/**
 * workbenchPages.ts: Notebooks and Scripts, two pages (the owner, 2026-11-21: "notebooks and scripts should
 * not reuse the same page they are seperate things" / "right now they all open tabbed beside each other").
 * [SHARED]
 *
 *   [PAGES]   /notebooks (the window named sab-notebooks) and /scripts (sab-scripts): the Workbench's one page
 *             code, each window its own page, said by its path. The old /workbench?kind=... goes to its page
 *             (the server's redirect).
 *   [KINDS]   which page a file or a kind opens on, and the one line a wrong-kind take is refused with, are
 *             the server's rules (domain/workbench_pages.py), read as data: loadPageRules takes GET
 *             /app/rules once at a page's start and pageRules.ts applies it. This file holds no copy.
 *   [OPEN]    openOnPage: the page's own window opens the file (asked through the server, as the agent's
 *             workbench_window is: nothing reloads), else that page's window, opened on it.
 */
import { api, token } from "./api";
import { errorHere } from "./errorNote";
import * as rules from "./pageRules";

export type CodePage = "notebooks" | "scripts";
export const CODE_PAGES: readonly CodePage[] = ["notebooks", "scripts"];
export const PAGE_WINDOW: Record<CodePage, string> = { notebooks: "sab-notebooks", scripts: "sab-scripts" };
export const PAGE_WORDS: Record<CodePage, string> = { notebooks: "Notebooks", scripts: "Scripts" };

/** An app's canvas (<app>.canvas.json): the Canvas page's own, never a document of these pages. */
export const isCanvasFile = (path: string | null | undefined): boolean => (path ?? "").toLowerCase().endsWith(".canvas.json");

/** The Canvas page on `path` (its own window's name, so a second ask brings it forward). */
export function openCanvasFile(path: string): void {
  window.open(`/streamlit/canvas?path=${encodeURIComponent(path)}`, "sab-canvas")?.focus();
}

let asked: Promise<void> | null = null;

/** The server's page rules, taken once (a page awaits this before its first question; a failure leaves every
 *  question answering "none", and the server refuses a wrong take by itself). */
export function loadPageRules(): Promise<void> {
  asked ??= api<{ pages: rules.PageRules }>("/app/rules").then(
    (found) => rules.usePageRules(found.pages),
    () => {
      asked = null; // asked again by the next page move
    },
  );
  return asked;
}

const asPage = (page: string | null): CodePage | null => (page === "notebooks" || page === "scripts" ? page : null);

/** The page a file opens on (null: neither): the server's table. */
export const pageOfPath = (path: string | null | undefined): CodePage | null => asPage(rules.pageOfPath(path));

/** A document kind's page (null: it has none): the server's table. */
export const pageOfKind = (kind: string | null | undefined): CodePage | null => asPage(rules.pageOfKind(kind));

/** The one line a document of `kind` dropped on `page` is refused with (null: it belongs there). */
export const wrongPage = (kind: string | null | undefined, page: CodePage): string | null => rules.wrongPage(kind, page);

/** The page this window is (by its path; an old /workbench address by its ?kind=). */
export function thisPage(): CodePage {
  const path = location.pathname.replace(/\/+$/, "");
  if (path === "/scripts") return "scripts";
  if (path === "/notebooks") return "notebooks";
  return pageOfKind(new URLSearchParams(location.search).get("kind")) ?? "notebooks";
}

export const pageUrl = (page: CodePage): string => `/${page}`;

const hashOf = (words: Record<string, string>): string => new URLSearchParams({ ...(token ? { token } : {}), ...words }).toString();

/** That page's window brought forward (opened at `address` when there is none yet); false when blocked.
 *  `known`: a window of that page answered already (it may be one this window cannot reach by its name): a
 *  blank one is not opened for it. */
export function bringPage(page: CodePage, address = pageUrl(page), words: Record<string, string> = {}, known = false): boolean {
  if (window.name === PAGE_WINDOW[page]) return true;
  const win = window.open("", PAGE_WINDOW[page]);
  if (!win) {
    errorHere("The browser blocked the new window: allow pop-ups for this address.");
    return false;
  }
  let fresh = true;
  try {
    fresh = win.location.href === "about:blank";
  } catch {
    fresh = true;
  }
  if (fresh && known) {
    win.close();
    return true;
  }
  if (fresh) win.location.href = `${address}#${hashOf(words)}`;
  win.focus();
  return true;
}

/** Open `path` on its page (`cell`: a notebook's cell; `line`: a script's line), in that page's window. */
export async function openOnPage(path: string, at: { cell?: number | null; line?: number | null } = {}): Promise<void> {
  await loadPageRules();
  const page = pageOfPath(path) ?? "notebooks";
  const command = at.cell ? "file.openCell" : at.line ? "file.openAt" : "file.open";
  const args = { path, ...(at.cell ? { cell: at.cell } : {}), ...(at.line ? { line: at.line } : {}) };
  try {
    await api("/workbench/window", "POST", { command, args, page });
    bringPage(page, pageUrl(page), {}, true);
  } catch {
    // No window of that page yet: one, opened on the file.
    bringPage(page, pageUrl(page), { open: path, ...(at.cell ? { cell: String(at.cell) } : {}), ...(at.line ? { line: String(at.line) } : {}) });
  }
}

/** A session kept before the two pages (both kinds under `oldKey`): each document moved to its page's own
 *  key (workbench-documents:<page>), once; the groups' layout starts again (its places were the mixed
 *  list's). */
export function splitSession(storage: Storage, oldKey: string): void {
  const raw = storage.getItem(oldKey);
  if (raw === null) return;
  storage.removeItem(oldKey);
  type Saved = { docs?: { kind?: string }[]; project?: unknown } | null;
  let saved: Saved;
  try {
    saved = JSON.parse(raw) as Saved;
  } catch {
    return;
  }
  for (const page of CODE_PAGES) {
    const mine = (saved?.docs ?? []).filter((d) => pageOfKind(d.kind) === page);
    if (!mine.length || storage.getItem(`${oldKey}:${page}`) !== null) continue;
    storage.setItem(`${oldKey}:${page}`, JSON.stringify({ docs: mine, current: mine.length - 1, project: saved?.project ?? null }));
  }
}

/** A blade's tab on the Scripts page, from anywhere (the old blades page went, 2026-11-21: blades are the
 *  Scripts page's Blades pane). The open Scripts window is told (as the agent's app_navigate tells it); else
 *  one opens on it (?pane=blades&blade=<name>; "" is New blade). */
export async function openBladeOnScripts(name: string | null): Promise<void> {
  const to = name ? `blade:${name}` : "new_blade";
  const told = await api("/navigate", "POST", { window: "scripts", to }).then(() => true, () => false);
  const query = new URLSearchParams({ pane: "blades", ...(name !== null ? { blade: name } : {}) });
  bringPage("scripts", `${pageUrl("scripts")}?${query.toString()}`, {}, told);
  if (told) window.open("", PAGE_WINDOW.scripts)?.focus();
}
