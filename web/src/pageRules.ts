/**
 * pageRules.ts: the rules the pages apply and keep no copy of (the owner's front end / back end rule): which
 * page a file or a document kind opens on, the one line a wrong-kind take is refused with, a file's kind, and
 * which files are a structure's tab. The tables are the server's (domain/workbench_pages.py rules(), GET
 * /app/rules); this module only applies them. Pure: no DOM, no request (tests/test_page_rules.py runs it in
 * Node on the server's own tables). [SHARED]
 *
 *   [TABLES]  usePageRules(given): the server's answer, taken once at a page's start (workbenchPages.ts
 *             loadPageRules); until then every question answers "none" (null, false)
 *   [ASK]     pageOfPath, pageOfKind, kindOfPath, wrongPage, pageWords, pageWindow, isStructurePath,
 *             structureSuffixes
 */

/** The server's tables (domain/workbench_pages.py rules()). Endings are matched in order against a file's
 *  lower-cased name; `wrong_page` holds {kind} and {page}. */
export interface PageRules {
  pages: string[];
  windows: Record<string, string>;
  words: Record<string, string>;
  path_pages: [string, string][];
  path_kinds: [string, string][];
  kind_pages: Record<string, string>;
  kind_words: Record<string, string>;
  wrong_page: string;
  structures: { suffixes: string[]; not: string[]; state_folder: string; home: string };
}

const NONE: PageRules = { pages: [], windows: {}, words: {}, path_pages: [], path_kinds: [], kind_pages: {}, kind_words: {}, wrong_page: "", structures: { suffixes: [], not: [], state_folder: "", home: "" } };
let rules: PageRules = NONE;

/** The server's tables, from now on. */
export function usePageRules(given: PageRules): void {
  rules = given;
}

/** Whether the server's tables are here yet. */
export const pageRulesReady = (): boolean => rules !== NONE;

const parts = (path: string | null | undefined): string[] => (path ?? "").replace(/\\/g, "/").split("/");
const nameOf = (path: string | null | undefined): string => (parts(path).pop() ?? "").toLowerCase();
const byEnding = (table: [string, string][], path: string | null | undefined): string | null => {
  const name = nameOf(path);
  if (!name.trim()) return null;
  return table.find(([ending]) => name.endsWith(ending))?.[1] ?? null;
};

/** The page a file opens on (null: neither). */
export const pageOfPath = (path: string | null | undefined): string | null => byEnding(rules.path_pages, path);

/** A document's kind by its file's ending (null: not a document of the code pages). */
export const kindOfPath = (path: string | null | undefined): string | null => byEnding(rules.path_kinds, path);

/** A document kind's page (null: it has none). */
export const pageOfKind = (kind: string | null | undefined): string | null => (typeof kind === "string" ? (rules.kind_pages[kind] ?? null) : null);

/** A page's name in words (Notebooks, Scripts). */
export const pageWords = (page: string): string => rules.words[page] ?? page;

/** A page's own window's name (sab-notebooks, sab-scripts). */
export const pageWindow = (page: string): string => rules.windows[page] ?? `sab-${page}`;

/** The one line a document of `kind` dropped on `page` is refused with (null: it belongs there). */
export function wrongPage(kind: string | null | undefined, page: string): string | null {
  const home = pageOfKind(kind);
  if (!home || home === page) return null;
  return rules.wrong_page.replace("{kind}", rules.kind_words[kind!] ?? String(kind)).replace("{page}", pageWords(home));
}

/** Whether a file opens as a structure's tab beside the code. */
export function isStructurePath(path: string | null | undefined): boolean {
  const folders = parts(path);
  const name = (folders.pop() ?? "").toLowerCase();
  const s = rules.structures;
  if (!name.trim() || name.startsWith(".") || (s.state_folder !== "" && folders.includes(s.state_folder))) return false;
  return s.suffixes.some((e) => name.endsWith(e)) && !s.not.some((e) => name.endsWith(e));
}

/** The endings a structure's file may have (a file picker's filter). */
export const structureSuffixes = (): string[] => [...rules.structures.suffixes];

/** The page a file opens on when nothing says which: its kind's page, a structure's the server's home. */
export const homeOfPath = (path: string | null | undefined): string | null => pageOfPath(path) ?? (isStructurePath(path) && rules.structures.home ? rules.structures.home : null);
