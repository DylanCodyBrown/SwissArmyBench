/**
 * codeExplorer.ts: the explorer on the left of the Notebooks and Scripts pages (the owner, 2026-11-21: "What
 * it should have is a project file explorer to browse and open all project scripts" / "a by module navigation
 * tree on the left to navigate all of the scripts (except the notebooks)"). [WIRE]
 *
 *   [ALWAYS]  always there on its page, the creator in the middle included; no project open: one line with a
 *             link to Projects.
 *   [GROUPS]  the server's (GET /project/tree?page=, domain/code_tree.py): Scripts by module in groups (Your
 *             scripts, Project code, the library's code, what the app generates), Notebooks with the data
 *             notebook first. Never the other page's kind.
 *   [OUTLINE] a module unfolds to its classes (their methods), functions and constants; a click goes to the
 *             line. The open document's outline follows its text as it is typed (POST /project/outline).
 *   [MARKS]   open (its name strong), unsaved (●), read-only (a key), edited by hand (a pencil).
 *   [FIND]    the search box matches files and symbols, in any case.
 *   [NEW]     New script (New notebook), and on the Scripts page New package.
 */
import { api } from "./api";
import { button, clear, h, icon } from "./dom";
import { errorHere } from "./errorNote";
import { goHome } from "./nav";
import type { CodePage } from "./workbenchPages";

export interface Symbol {
  name: string;
  kind: "class" | "function" | "method" | "constant";
  line: number;
  end: number;
  children: Symbol[];
}

export interface TreeFile {
  path: string;
  full: string;
  name: string;
  folder: string;
  module?: string;
  made_from?: string | null;
  edited?: boolean;
  read_only?: boolean;
  outline?: Symbol[];
  /** An item that is no file of its own (a table's transformations): opened by the host by its id. */
  item?: string;
  actions?: { id: string; label: string }[];
}

interface TreeGroup {
  id: string;
  name: string;
  files: TreeFile[];
}

export interface CodeExplorerHost {
  page: CodePage;
  open: (file: TreeFile) => void;
  openAt: (file: TreeFile, line: number) => void;
  newDocument: () => void;
  newPackage?: () => void;
  /** A file's own action (Fine-tune as a script, Copy as your own). */
  action?: (file: TreeFile, id: string) => void;
  /** The documents open in this window: their full paths, the unsaved ones, the one in front. */
  openNow: () => { paths: string[]; dirty: string[]; front: string | null };
  /** The page's own menu ("…": New, Open…, split, Commands…, Settings…), at the head's end. */
  menu?: HTMLElement;
}

export interface CodeExplorer {
  element: HTMLElement;
  refresh: () => Promise<void>;
  /** The open documents' marks drawn again (opened, closed, typed, saved). */
  mark: () => void;
  /** The front document's text changed: its outline follows (a moment later). */
  typed: (full: string, text: string) => void;
  files: () => TreeFile[];
}

const SYMBOL_ICONS: Record<string, string> = { class: "blade", function: "formula", method: "formula", constant: "number" };

export function mountCodeExplorer(host: CodeExplorerHost): CodeExplorer {
  const words = host.page === "scripts" ? { title: "Scripts", one: "script" } : { title: "Notebooks", one: "notebook" };
  const search = h("input", { type: "search", class: "wb-codex-search", placeholder: host.page === "scripts" ? "Find a file or symbol" : "Find a notebook", "aria-label": "Find", "data-no-variables": "" }) as HTMLInputElement;
  const newDoc = button(`New ${words.one}`, () => host.newDocument(), { icon: "plus", iconOnly: true, class: "ghost wb-codex-new", title: `New ${words.one}` });
  const newPackage = host.newPackage ? button("New package", () => host.newPackage!(), { icon: "folder", iconOnly: true, class: "ghost wb-codex-package", title: "New package" }) : null;
  const refreshButton = button("Refresh", () => void refresh(), { icon: "reset", iconOnly: true, class: "ghost", title: "Refresh" });
  const body = h("div", { class: "wb-codex-body", role: "tree", "aria-label": words.title });
  const element = h(
    "aside",
    { class: `wb-codex page-${host.page}`, "aria-label": `${words.title} explorer` },
    h("div", { class: "wb-codex-head" }, h("strong", { class: "wb-codex-title" }, words.title), h("span", { class: "wb-grow" }), newDoc, newPackage, refreshButton, host.menu ?? null),
    search,
    body,
  );
  let groups: TreeGroup[] = [];
  let project: string | null = null;
  let loaded = false;
  const folded = new Set<string>();
  const unfolded = new Set<string>(); // the modules whose outline shows
  const live = new Map<string, Symbol[]>(); // an open document's outline as typed
  let typedTimer: number | null = null;

  const matches = (text: string): boolean => text.toLowerCase().includes(search.value.trim().toLowerCase());
  const symbolMatches = (symbols: Symbol[]): boolean => symbols.some((s) => matches(s.name) || symbolMatches(s.children));

  const symbolRow = (file: TreeFile, s: Symbol, depth: number): HTMLElement[] => [
    h(
      "button",
      { type: "button", class: `wb-codex-symbol sym-${s.kind}`, role: "treeitem", style: { paddingLeft: `${20 + depth * 14}px` }, "data-symbol": s.name, "data-line": String(s.line), title: `${s.kind} ${s.name}, line ${s.line}`, onclick: () => host.openAt(file, s.line) },
      icon(SYMBOL_ICONS[s.kind] ?? "code"),
      h("span", {}, s.name),
    ),
    ...s.children.flatMap((c) => symbolRow(file, c, depth + 1)),
  ];

  const fileRow = (file: TreeFile): HTMLElement => {
    const now = host.openNow();
    const outline = live.get(file.full) ?? file.outline ?? [];
    const shows = unfolded.has(file.full) || (!!search.value.trim() && symbolMatches(outline));
    const toggle = outline.length
      ? h("button", { type: "button", class: "wb-codex-fold", "aria-label": shows ? "Hide its outline" : "Show its outline", "aria-expanded": String(shows), onclick: () => (unfolded.has(file.full) ? unfolded.delete(file.full) : unfolded.add(file.full), draw()) }, icon(shows ? "down" : "forward"))
      : h("span", { class: "wb-codex-fold" });
    const row = h(
      "div",
      { class: "wb-codex-file-row" },
      toggle,
      h(
        "button",
        {
          type: "button",
          class: `wb-codex-file${now.paths.includes(file.full) ? " open" : ""}${now.front === file.full ? " front" : ""}`,
          role: "treeitem",
          "data-path": file.path,
          title: file.made_from ? `${file.path}: made from ${file.made_from}` : file.path,
          onclick: () => host.open(file),
        },
        icon(file.item ? "table" : host.page === "scripts" ? "code" : file.name.toLowerCase() === "data.ipynb" ? "dataNotebook" : "notebook"),
        h("span", { class: "wb-codex-name" }, host.page === "scripts" && file.module && !file.item ? file.module : file.name),
        now.dirty.includes(file.full) ? h("span", { class: "wb-codex-dirty", title: "Not saved", "aria-label": "Not saved" }, "●") : null,
        file.edited ? h("span", { class: "wb-codex-mark edited", title: "Edited by hand", "aria-label": "Edited by hand" }, icon("edit")) : file.read_only ? h("span", { class: "wb-codex-mark locked", title: file.made_from ? `Made from ${file.made_from}: read-only` : "Read-only", "aria-label": "Read-only" }, icon("key")) : null,
      ),
      ...(file.actions ?? []).map((a) => button(a.label, () => host.action?.(file, a.id), { class: "ghost wb-codex-action", title: a.label })),
    );
    return h("div", { class: "wb-codex-item" }, row, ...(shows ? outline.flatMap((s) => symbolRow(file, s, 0)) : []));
  };

  function draw(): void {
    if (!loaded) return void clear(body, h("p", { class: "hint" }, "Loading…"));
    if (!project) {
      clear(body, h("p", { class: "wb-codex-none" }, "No project is open. ", h("a", { href: "#", class: "link", onclick: (e: Event) => (e.preventDefault(), goHome()) }, "Home")));
      return;
    }
    const q = search.value.trim();
    const shown = groups.map((g) => ({ g, files: q ? g.files.filter((f) => matches(f.path) || matches(f.module ?? "") || symbolMatches(f.outline ?? [])) : g.files })).filter(({ g, files }) => files.length || (!q && g.id !== "generated"));
    if (!shown.length) return void clear(body, h("p", { class: "hint" }, q ? "Nothing matches." : `No ${words.one}s yet.`));
    clear(
      body,
      ...shown.map(({ g, files }) => {
        const closed = folded.has(g.id) && !q;
        return h(
          "section",
          { class: "wb-codex-group", "data-group": g.id },
          h("button", { type: "button", class: "wb-codex-group-head", "aria-expanded": String(!closed), onclick: () => (folded.has(g.id) ? folded.delete(g.id) : folded.add(g.id), draw()) }, icon(closed ? "forward" : "down"), h("span", {}, g.name), h("span", { class: "wb-codex-count" }, String(files.length))),
          closed ? null : files.length ? h("div", { class: "wb-codex-files" }, ...files.map(fileRow)) : h("p", { class: "hint wb-codex-empty" }, "None"),
        );
      }),
    );
  }

  async function refresh(): Promise<void> {
    try {
      const said = await api<{ project: string | null; groups: TreeGroup[] }>(`/project/tree?page=${host.page}`);
      project = said.project;
      groups = said.groups;
    } catch (e) {
      errorHere(e);
    }
    loaded = true;
    draw();
  }

  search.addEventListener("input", draw);
  draw();
  void refresh();
  return {
    element,
    refresh,
    mark: draw,
    files: () => groups.flatMap((g) => g.files),
    typed: (full, text) => {
      if (host.page !== "scripts") return;
      if (typedTimer !== null) window.clearTimeout(typedTimer);
      typedTimer = window.setTimeout(() => {
        void api<{ symbols: Symbol[]; error: unknown }>("/project/outline", "POST", { text })
          .then((said) => {
            if (said.error) return; // a syntax error: the last outline stays
            live.set(full, said.symbols);
            draw();
          })
          .catch(() => undefined);
      }, 400);
    },
  };
}
