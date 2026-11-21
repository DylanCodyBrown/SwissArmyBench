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
 *             line. The open document's outline follows its text as it is typed (POST /project/module-outline).
 *   [MARKS]   open (its name strong), unsaved (●), read-only (a key), edited by hand (a pencil).
 *   [FIND]    the search box matches files and symbols, in any case.
 *   [NEW]     New script (New notebook), and on the Scripts page New package.
 */
import { api } from "./api";
import { button, clear, h, icon } from "./dom";
import { errorHere } from "./errorNote";
import { kindIcon } from "./kindColours";
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
  /** Its read-only text (an item's). */
  text?: string;
  library?: boolean;
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
  /** A pane under the files, with a splitter between (the Scripts page's Blades: the owner, 2026-11-21:
   *  "navigation on top, blade on bottom"); each folds, the split remembered. */
  lower?: { id: string; title: string; element: HTMLElement; actions?: HTMLElement[] };
}

export interface CodeExplorer {
  element: HTMLElement;
  refresh: () => Promise<void>;
  /** The open documents' marks drawn again (opened, closed, typed, saved). */
  mark: () => void;
  /** The front document's text changed: its outline follows (a moment later). */
  typed: (full: string, text: string) => void;
  files: () => TreeFile[];
  /** New's words as the mode has them ("New TypeScript file" in a code app). */
  setNewLabel: (label: string) => void;
  /** Collapse it to a thin strip, or open it again (Ctrl+B); remembered per page. Whether it is open. */
  toggle: (show?: boolean) => boolean;
  /** The lower pane (Blades) unfolded and the focus in it. */
  showLower: () => void;
}

const SYMBOL_ICONS: Record<string, string> = { class: "blade", function: "formula", method: "formula", constant: "number" };

export function mountCodeExplorer(host: CodeExplorerHost): CodeExplorer {
  const words = host.page === "scripts" ? { title: "Scripts", one: "script" } : { title: "Notebooks", one: "notebook" };
  const search = h("input", { type: "search", class: "wb-codex-search", placeholder: host.page === "scripts" ? "Find a file or symbol" : "Find a notebook", "aria-label": "Find", "data-no-variables": "" }) as HTMLInputElement;
  const newDoc = button(`New ${words.one}`, () => host.newDocument(), { icon: "plus", iconOnly: true, class: "ghost wb-codex-new", title: `New ${words.one}` });
  const newPackage = host.newPackage ? button("New package", () => host.newPackage!(), { icon: "folder", iconOnly: true, class: "ghost wb-codex-package", title: "New package" }) : null;
  const refreshButton = button("Refresh", () => void refresh(), { icon: "reset", iconOnly: true, class: "ghost", title: "Refresh" });
  const body = h("div", { class: "wb-codex-body", role: "tree", "aria-label": words.title });
  // Its width and whether it is folded, per page (this browser's: a convenience).
  const KEY = `wb-codex:${host.page}`;
  const kept = (() => {
    try {
      return JSON.parse(localStorage.getItem(KEY) ?? "{}") as { width?: number; closed?: boolean; split?: number; filesFolded?: boolean; lowerFolded?: boolean };
    } catch {
      return {};
    }
  })();
  let width = Math.min(520, Math.max(160, kept.width ?? 240));
  let closed = !!kept.closed;
  let split = Math.min(0.85, Math.max(0.15, kept.split ?? 0.55)); // the files' share of the height
  let filesFolded = !!kept.filesFolded;
  let lowerFolded = !!kept.lowerFolded;
  const keep = (): void => {
    try {
      localStorage.setItem(KEY, JSON.stringify({ width, closed, split, filesFolded, lowerFolded }));
    } catch {
      /* storage blocked */
    }
  };
  const fold = button("Collapse the explorer", () => toggle(), { icon: "collapse", iconOnly: true, class: "ghost wb-codex-fold-all", title: "Collapse (Ctrl+B)" });
  const strip = h("button", { type: "button", class: "wb-codex-strip", title: `${words.title} (Ctrl+B)`, "aria-label": `Show the ${words.title.toLowerCase()} explorer`, onclick: () => toggle(true) }, icon(host.page === "scripts" ? "code" : "notebook"));
  const sash = h("div", { class: "wb-codex-sash", role: "separator", "aria-orientation": "vertical", "aria-label": "Explorer width", tabindex: 0 });
  const filesHead = h(
    "div",
    { class: "wb-codex-head" },
    h("button", { type: "button", class: "wb-codex-pane-fold", "aria-label": `Fold ${words.title}`, onclick: () => foldPane("files") }, icon("down")),
    h("strong", { class: "wb-codex-title" }, host.lower ? "Files" : words.title),
    h("span", { class: "wb-grow" }),
    newDoc,
    newPackage,
    refreshButton,
    host.menu ?? null,
    fold,
  );
  const filesPane = h("section", { class: "wb-codex-pane wb-codex-filespane", "aria-label": host.lower ? "Files" : words.title }, filesHead, search, body);
  const lowerSash = host.lower ? h("div", { class: "wb-codex-hsash", role: "separator", "aria-orientation": "horizontal", "aria-label": `${host.lower.title} height`, tabindex: 0 }) : null;
  const lowerPane = host.lower
    ? h(
        "section",
        { class: `wb-codex-pane wb-codex-lower lower-${host.lower.id}`, "aria-label": host.lower.title, "data-pane": host.lower.id },
        h(
          "div",
          { class: "wb-codex-head" },
          h("button", { type: "button", class: "wb-codex-pane-fold", "aria-label": `Fold ${host.lower.title}`, onclick: () => foldPane("lower") }, icon("down")),
          h("strong", { class: "wb-codex-title" }, host.lower.title),
          h("span", { class: "wb-grow" }),
          ...(host.lower.actions ?? []),
        ),
        h("div", { class: "wb-codex-lower-body" }, host.lower.element),
      )
    : null;
  const element = h(
    "aside",
    { class: `wb-codex page-${host.page}${host.lower ? " stacked" : ""}`, "aria-label": `${words.title} explorer` },
    filesPane,
    lowerSash,
    lowerPane,
    strip,
    sash,
  );
  let groups: TreeGroup[] = [];
  let project: string | null = null;
  let loaded = false;
  const folded = new Set<string>();
  const unfolded = new Set<string>(); // the modules whose outline shows
  const live = new Map<string, Symbol[]>(); // an open document's outline as typed
  let typedTimer: number | null = null;
  const drawSplit = (): void => {
    filesPane.classList.toggle("folded", filesFolded);
    lowerPane?.classList.toggle("folded", lowerFolded);
    if (lowerSash) lowerSash.hidden = filesFolded || lowerFolded;
    filesPane.style.flex = filesFolded ? "0 0 auto" : lowerPane && !lowerFolded ? `${split} 1 0` : "1 1 0";
    if (lowerPane) lowerPane.style.flex = lowerFolded ? "0 0 auto" : filesFolded ? "1 1 0" : `${1 - split} 1 0`;
    for (const [pane, folded] of [[filesPane, filesFolded], [lowerPane, lowerFolded]] as const) {
      const b = pane?.querySelector<HTMLElement>(".wb-codex-pane-fold");
      if (b) {
        b.setAttribute("aria-expanded", String(!folded));
        b.replaceChildren(icon(folded ? "forward" : "down"));
      }
    }
  };
  function foldPane(which: "files" | "lower", folded?: boolean): void {
    if (which === "files") filesFolded = folded ?? !filesFolded;
    else lowerFolded = folded ?? !lowerFolded;
    keep();
    drawSplit();
  }
  lowerSash?.addEventListener("pointerdown", (e) => {
    const box = element.getBoundingClientRect();
    lowerSash.setPointerCapture(e.pointerId);
    const move = (m: PointerEvent): void => {
      split = Math.min(0.85, Math.max(0.15, (m.clientY - box.top) / Math.max(1, box.height)));
      drawSplit();
    };
    lowerSash.addEventListener("pointermove", move);
    lowerSash.addEventListener("pointerup", () => (lowerSash.removeEventListener("pointermove", move), keep()), { once: true });
  });
  lowerSash?.addEventListener("keydown", (e) => {
    const by = e.key === "ArrowUp" ? -0.05 : e.key === "ArrowDown" ? 0.05 : 0;
    if (!by) return;
    e.preventDefault();
    split = Math.min(0.85, Math.max(0.15, split + by));
    keep();
    drawSplit();
  });
  drawSplit();
  const apply = (): void => {
    element.classList.toggle("closed", closed);
    element.style.width = closed ? "" : `${width}px`;
    window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  };
  function toggle(show?: boolean): boolean {
    closed = show === undefined ? !closed : !show;
    keep();
    apply();
    return !closed;
  }
  sash.addEventListener("pointerdown", (e) => {
    const start = e.clientX;
    const from = width;
    sash.setPointerCapture(e.pointerId);
    const move = (m: PointerEvent): void => {
      width = Math.min(520, Math.max(160, from + m.clientX - start));
      element.style.width = `${width}px`;
    };
    const up = (): void => {
      sash.removeEventListener("pointermove", move);
      keep();
      window.dispatchEvent(new Event("resize"));
    };
    sash.addEventListener("pointermove", move);
    sash.addEventListener("pointerup", up, { once: true });
  });
  sash.addEventListener("keydown", (e) => {
    const by = e.key === "ArrowLeft" ? -16 : e.key === "ArrowRight" ? 16 : 0;
    if (!by) return;
    e.preventDefault();
    width = Math.min(520, Math.max(160, width + by));
    keep();
    apply();
  });

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
        icon(file.item ? "table" : host.page === "scripts" ? "code" : kindIcon("notebook", file.full)),
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
      // Scripts: the project's code, the library's and what the app generates (GET /scripts/tree).
      const said = await api<{ project: string | null; groups: TreeGroup[] }>(host.page === "scripts" ? "/scripts/tree" : `/project/tree?page=${host.page}`);
      project = said.project;
      groups = said.groups;
    } catch (e) {
      errorHere(e);
    }
    loaded = true;
    draw();
  }

  search.addEventListener("input", draw);
  apply();
  draw();
  void refresh();
  return {
    element,
    refresh,
    mark: draw,
    files: () => groups.flatMap((g) => g.files),
    toggle,
    showLower: () => {
      toggle(true);
      foldPane("lower", false);
      lowerPane?.querySelector<HTMLElement>("input, button")?.focus();
    },
    setNewLabel: (label) => {
      newDoc.title = label;
      newDoc.setAttribute("aria-label", label);
    },
    typed: (full, text) => {
      if (host.page !== "scripts") return;
      if (typedTimer !== null) window.clearTimeout(typedTimer);
      typedTimer = window.setTimeout(() => {
        void api<{ symbols: Symbol[]; error: unknown }>("/project/module-outline", "POST", { text })
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
