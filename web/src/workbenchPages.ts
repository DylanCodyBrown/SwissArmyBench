/**
 * workbenchPages.ts: Notebooks and Scripts, two pages (the owner, 2026-11-21: "notebooks and scripts should
 * not reuse the same page they are seperate things" / "right now they all open tabbed beside each other").
 * [SHARED]
 *
 *   [PAGES]   /notebooks (the window named sab-notebooks) and /scripts (sab-scripts): the Workbench's one page
 *             code, each window its own page, said by its path. The old /workbench?kind=... goes to its page
 *             (the server's redirect: domain/workbench_pages.py holds the same rule).
 *   [KINDS]   a notebook (.ipynb) opens only on the Notebooks page, a .py only on the Scripts page, from
 *             anywhere; a Streamlit app's canvas and a workbook design stay beside the notebooks.
 *   [OPEN]    openOnPage: the page's own window opens the file (asked through the server, as the agent's
 *             workbench_window is: nothing reloads), else that page's window, opened on it.
 */
import { api, token } from "./api";
import { errorHere } from "./errorNote";

export type CodePage = "notebooks" | "scripts";
export const CODE_PAGES: readonly CodePage[] = ["notebooks", "scripts"];
export const PAGE_WINDOW: Record<CodePage, string> = { notebooks: "sab-notebooks", scripts: "sab-scripts" };
export const PAGE_WORDS: Record<CodePage, string> = { notebooks: "Notebooks", scripts: "Scripts" };

/** The page a file opens on (null: neither). */
export function pageOfPath(path: string | null | undefined): CodePage | null {
  const name = (path ?? "").replace(/\\/g, "/").split("/").pop()?.toLowerCase() ?? "";
  if (name.endsWith(".py")) return "scripts";
  if (name.endsWith(".ipynb") || name.endsWith(".stapp.json") || name.endsWith(".design.json")) return "notebooks";
  return null;
}

/** A document kind's page: a notebook and an app the Notebooks page, a script the Scripts page. */
export function pageOfKind(kind: string | null | undefined): CodePage | null {
  return kind === "script" ? "scripts" : kind === "notebook" || kind === "app" ? "notebooks" : null;
}

const KIND_WORDS: Record<string, string> = { notebook: "A notebook", app: "A Streamlit app", script: "A script" };

/** The one line a document of `kind` dropped on `page` is refused with (null: it belongs there). */
export function wrongPage(kind: string | null | undefined, page: CodePage): string | null {
  const home = pageOfKind(kind);
  if (!home || home === page) return null;
  return `${KIND_WORDS[kind!]} opens on the ${PAGE_WORDS[home]} page, not here.`;
}

/** The page this window is (by its path; an old /workbench address by its ?kind=). */
export function thisPage(): CodePage {
  const path = location.pathname.replace(/\/+$/, "");
  if (path === "/scripts") return "scripts";
  if (path === "/notebooks") return "notebooks";
  return pageOfKind(new URLSearchParams(location.search).get("kind")) ?? "notebooks";
}

export const pageUrl = (page: CodePage): string => `/${page}`;

const hashOf = (words: Record<string, string>): string => new URLSearchParams({ ...(token ? { token } : {}), ...words }).toString();

/** That page's window brought forward (opened at `address` when there is none yet); false when blocked. */
export function bringPage(page: CodePage, address = pageUrl(page), words: Record<string, string> = {}): boolean {
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
  if (fresh) win.location.href = `${address}#${hashOf(words)}`;
  win.focus();
  return true;
}

/** Open `path` on its page (`cell`: a notebook's cell; `line`: a script's line), in that page's window. */
export async function openOnPage(path: string, at: { cell?: number | null; line?: number | null } = {}): Promise<void> {
  const page = pageOfPath(path) ?? "notebooks";
  const command = at.cell ? "file.openCell" : at.line ? "file.openAt" : "file.open";
  const args = { path, ...(at.cell ? { cell: at.cell } : {}), ...(at.line ? { line: at.line } : {}) };
  try {
    await api("/workbench/window", "POST", { command, args, page });
    bringPage(page);
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
