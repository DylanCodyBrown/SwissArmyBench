/**
 * scmPage.ts: the Source Control page, a front-end plug-in shown only while the backend names its rail area
 * (GET /app/areas: "scm"); it never names the extension that serves it (the owner, 2026-11-18: "literally steal
 * VS Code's panel for git with the graph and commit and show it with a diff navigator on a new rail icon" /
 * "literally clone to exactly no deviation"). [PLUG-IN]
 *
 * VS Code's Source Control view and its Source Control Graph, drawn from VS Code's own layout, sizes, words,
 * codicons, menus, keys and its Dark Modern and Light Modern colours (scm.css's values in grid.css, the graph in
 * scmGraph.ts, ported under its MIT licence), over GitHub sync. No local Git: what needs one (stash, a local
 * commit before pushing, rebase, amend, staging a hunk, tags, worktrees, remotes) is shown disabled, as VS Code
 * shows a disabled command (docs/ideas.md lists each).
 *
 *   [CHANGES]  each connected folder a repository (the team library; the shared projects, scoped to the open
 *              project): the message box ("Message (Ctrl+Enter to commit on "main")"), the Commit button and its
 *              menu, Merge Changes, Staged Changes and Changes with their counts, each file's icon, name, folder
 *              (greyed) and letter in VS Code's git decoration colour, the inline actions on hover (Open File,
 *              Discard Changes, Stage Changes / Unstage Changes), the right-click menus, list or tree
 *   [GRAPH]    the branch's history from GitHub: VS Code's swimlanes, each row's subject, author and the refs'
 *              labels, Incoming Changes when GitHub is ahead, a row's files when it is opened (each opens its diff)
 *   [DIFF]     Monaco's diff editor (side by side, Inline View, F7 and Shift+F7), the files beside it, the
 *              previous and next file; read-only (a file is edited in its own editor)
 *   [GITHUB]   signed out: VS Code's welcome words and Sign in; Clone Repository and Connect (a quick pick of
 *              the signed-in user's repositories, then the folder); Settings' Team box's sign-in step (teamSignIn)
 *   [CARDS]    a shared project's card: Pull and Push, and its sync words (projectExplorer.ts asks here)
 *
 * ROUTING: GET /app/areas · GET /git, /git/changes, /git/history, /git/commit-files, /git/diff, /git/branches,
 *          /git/repositories · POST /git/stage, /git/discard, /git/commit, /git/pull, /git/push, /git/sync,
 *          /git/checkout, /git/clone, /git/connect, /git/disconnect, /git/sign-in/token, /git/sign-in/device[/poll],
 *          /git/sign-out · notices sync_changed, projects_changed, project_changed
 */
import { api, onNotice } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { button, h, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import type { DiffViewer } from "./lazy/codeEditor";
import { dismissDialog, layerOpened, registerLayer, setOverTitle } from "./nav";
import { graph, INCOMING_ID, REF_COLOR, REMOTE_REF_COLOR, type HistoryItem, type Ref, type ViewModel, viewModels } from "./scmGraph";
import { effectiveTheme, onThemeChange } from "./theme";

export const SCM = "Source Control";
const KEY = "scm";

// ===== the backend's answers =====

interface Resource { path: string; status: string; letter: string; tooltip: string; colour: string; previous?: string | null }
interface Repository {
  which: "library" | "shared";
  name: string;
  repository: string;
  folder: string;
  scope: string | null;
  branch: string;
  commit: string | null;
  groups: { merge: Resource[]; index: Resource[]; workingTree: Resource[] };
  count: number;
  behind: number;
  pulled: boolean;
}
interface Changes { signed_in: boolean; account: string | null; repositories: Repository[] }
interface Row { id: string; parents: string[]; subject: string; message: string; author: string; email: string; date: string }
interface History { which: string; branch: string; page: number; more: boolean; rows: Row[]; refs: { id: string; name: string; commit: string; kind: "local" | "remote" }[]; uncommitted: number }
interface Folder { which: "library" | "shared"; folder: string | null; set: boolean; connected: boolean; repository?: string; branch?: string; words: string; state: string; projects?: Record<string, { to_push: number; conflicts: number }>; behind?: number | null; pulled?: boolean }
interface Status { signed_in: boolean; account: string | null; device: boolean; token_steps: string[]; folders: Folder[] }
interface Diff { path: string; original: string; modified: string; original_label: string; modified_label: string; binary: boolean; added: boolean; deleted: boolean }

// ===== whether it is on here =====

let onAsked: Promise<boolean> | null = null;
/** The rail's Source Control area: on when the backend names it. Asked once a page. */
export function scmOn(): Promise<boolean> {
  onAsked ??= api<{ areas: { area: string }[] }>("/app/areas").then((got) => got.areas.some((a) => a.area === KEY), () => false);
  return onAsked;
}

// ===== codicons (Monaco's codicon font, loaded with the editor's stylesheet) =====

const CODICONS: Record<string, number> = {
  check: 0xeab2, refresh: 0xeb37, ellipsis: 0xea7c, "list-tree": 0xeb86, "list-flat": 0xeb84, "go-to-file": 0xea94,
  discard: 0xeae2, add: 0xea60, remove: 0xeb3b, "compare-changes": 0xeafd, "diff-multiple": 0xec23, "chevron-down": 0xeab4,
  "chevron-right": 0xeab6, "source-control": 0xea68, repo: 0xea62, "repo-pull": 0xeb40, "repo-push": 0xeb41, sync: 0xea77,
  "git-commit": 0xeafc, "git-branch": 0xea68, target: 0xebf8, cloud: 0xebaa, "cloud-upload": 0xeac3, "git-fetch": 0xecb2,
  "arrow-up": 0xeaa1, "arrow-down": 0xea9a, close: 0xea76, file: 0xea7b, warning: 0xea6c, whitespace: 0xeb7d, copy: 0xebcc,
  "collapse-all": 0xeac5, github: 0xea84, folder: 0xea83, "folder-opened": 0xeaf7, account: 0xeb99, "sign-in": 0xea6f,
  "sign-out": 0xea6e, "link-external": 0xeb14, info: 0xea74, error: 0xea87, loading: 0xeb19, "repo-clone": 0xeb3e,
  "arrow-left": 0xea9b, "arrow-right": 0xea9c,
};

export function codicon(name: string, extra = ""): HTMLElement {
  const code = CODICONS[name] ?? CODICONS.file!;
  return h("span", { class: `codicon codicon-${name}${extra ? ` ${extra}` : ""}`, "aria-hidden": "true", "data-codicon": name }, String.fromCodePoint(code));
}

function loadEditorStyles(): void {
  if (!document.querySelector('link[href="/static/build/lazy/codeEditor.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/build/lazy/codeEditor.css" }));
  }
}

let editors: Promise<typeof import("./lazy/codeEditor")> | null = null;
function loadEditors(): Promise<typeof import("./lazy/codeEditor")> {
  loadEditorStyles();
  return (editors ??= import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>);
}

// ===== VS Code's action items and menus =====

interface MenuItem { label: string; run?: () => void; disabled?: boolean; submenu?: MenuEntry[]; keys?: string; checked?: boolean }
type MenuEntry = MenuItem | null;

function action(icon: string, title: string, run: () => void, disabled = false): HTMLElement {
  const a = h(
    "a",
    {
      class: `action-label codicon codicon-${icon}${disabled ? " disabled" : ""}`,
      role: "button",
      tabindex: disabled ? -1 : 0,
      "aria-label": title,
      title,
      "aria-disabled": disabled ? "true" : undefined,
      "data-codicon": icon,
      onclick: (e: MouseEvent) => {
        e.stopPropagation();
        e.preventDefault();
        if (!disabled) run();
      },
      onkeydown: (e: KeyboardEvent) => {
        if ((e.key === "Enter" || e.key === " ") && !disabled) {
          e.preventDefault();
          run();
        }
      },
    },
    String.fromCodePoint(CODICONS[icon] ?? CODICONS.file!),
  );
  return h("li", { class: "action-item", role: "presentation" }, a);
}

function actionBar(...items: HTMLElement[]): HTMLElement {
  return h("div", { class: "monaco-action-bar" }, h("ul", { class: "actions-container", role: "toolbar" }, ...items));
}

let openMenu: HTMLElement | null = null;
function closeMenus(): void {
  for (const m of document.querySelectorAll(".scm-context-view")) m.remove();
  openMenu = null;
}
document.addEventListener("mousedown", (e) => {
  if (openMenu && !(e.target as Element).closest?.(".scm-context-view")) closeMenus();
});

/** VS Code's context menu: its rows, separators, keybindings, disabled entries and submenus. */
function menu(x: number, y: number, entries: MenuEntry[], label: string, parent?: HTMLElement): HTMLElement {
  if (!parent) closeMenus();
  const list = h("ul", { class: "actions-container", role: "menu", "aria-label": label });
  const view = h("div", { class: "scm-context-view monaco-menu-container", tabindex: -1 }, h("div", { class: "monaco-menu" }, h("div", { class: "monaco-action-bar vertical" }, list)));
  const rows: HTMLElement[] = [];
  for (const entry of entries) {
    if (entry === null) {
      list.append(h("li", { class: "action-item disabled", role: "presentation" }, h("a", { class: "action-label codicon separator disabled", role: "presentation" })));
      continue;
    }
    const row = h(
      "a",
      { class: `action-menu-item${entry.disabled ? " disabled" : ""}`, role: "menuitem", tabindex: -1, "aria-disabled": entry.disabled ? "true" : undefined, "aria-haspopup": entry.submenu ? "true" : undefined, "aria-checked": entry.checked === undefined ? undefined : String(entry.checked) },
      h("span", { class: `menu-item-check codicon codicon-menu-selection${entry.checked ? " checked" : ""}` }, entry.checked ? String.fromCodePoint(CODICONS.check!) : ""),
      h("span", { class: "action-label" }, entry.label),
      entry.keys ? h("span", { class: "keybinding" }, entry.keys) : null,
      entry.submenu ? h("span", { class: "submenu-indicator codicon codicon-menu-submenu" }, String.fromCodePoint(CODICONS["chevron-right"]!)) : null,
    );
    rows.push(row);
    const item = h("li", { class: `action-item${entry.disabled ? " disabled" : ""}`, role: "presentation" }, row);
    row.addEventListener("mouseenter", () => {
      for (const sub of view.querySelectorAll(".scm-context-view")) sub.remove();
      row.focus();
      if (entry.submenu && !entry.disabled) {
        const box = row.getBoundingClientRect();
        menu(box.right, box.top - 4, entry.submenu, entry.label, view);
      }
    });
    row.addEventListener("click", (e) => {
      e.stopPropagation();
      if (entry.disabled || entry.submenu) return;
      closeMenus();
      entry.run?.();
    });
    list.append(item);
  }
  view.addEventListener("keydown", (e) => {
    const at = rows.indexOf(document.activeElement as HTMLElement);
    const live = rows.filter((r) => !r.classList.contains("disabled"));
    if (e.key === "Escape") closeMenus();
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const i = live.indexOf(rows[at]!);
      const next = live[(i + (e.key === "ArrowDown" ? 1 : -1) + live.length) % live.length];
      next?.focus();
    } else if (e.key === "Enter" && at >= 0) rows[at]!.click();
  });
  (parent ?? document.body).append(view);
  view.style.left = `${Math.min(x, window.innerWidth - 260)}px`;
  view.style.top = `${Math.min(y, window.innerHeight - Math.min(rows.length * 26 + 16, window.innerHeight))}px`;
  if (!parent) openMenu = view;
  view.focus();
  return view;
}

/** A quick pick (VS Code's): a box to type in and the items under it; resolves with the one picked. */
function quickPick<T>(placeholder: string, items: { label: string; description?: string; value: T }[], free?: (typed: string) => T | null): Promise<T | null> {
  return new Promise((resolve) => {
    const input = h("input", { class: "input", type: "text", placeholder, "aria-label": placeholder, spellcheck: "false" });
    const list = h("div", { class: "quick-input-list", role: "listbox" });
    const widget = h("div", { class: "scm-quick-input quick-input-widget", role: "dialog", "aria-label": placeholder }, h("div", { class: "quick-input-box" }, input), list);
    let shown = items;
    let at = 0;
    const done = (value: T | null): void => {
      widget.remove();
      resolve(value);
    };
    const draw = (): void => {
      const words = input.value.trim().toLowerCase();
      shown = items.filter((i) => !words || i.label.toLowerCase().includes(words) || (i.description ?? "").toLowerCase().includes(words));
      at = Math.min(at, Math.max(shown.length - 1, 0));
      list.replaceChildren(
        ...shown.map((i, n) =>
          h("div", { class: `quick-input-list-entry${n === at ? " focused" : ""}`, role: "option", "aria-selected": String(n === at), onmousedown: (e: Event) => { e.preventDefault(); done(i.value); } }, h("span", { class: "label-name" }, i.label), i.description ? h("span", { class: "label-description" }, i.description) : null),
        ),
      );
    };
    input.addEventListener("input", () => { at = 0; draw(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") done(null);
      else if (e.key === "ArrowDown") { at = Math.min(at + 1, shown.length - 1); draw(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { at = Math.max(at - 1, 0); draw(); e.preventDefault(); }
      else if (e.key === "Enter") {
        e.preventDefault();
        if (shown[at]) done(shown[at]!.value);
        else if (free) done(free(input.value.trim()));
      }
    });
    input.addEventListener("blur", () => window.setTimeout(() => widget.isConnected && done(null), 150));
    document.body.append(widget);
    draw();
    input.focus();
  });
}

/** VS Code's modal dialog: its message, detail and buttons (the first the primary). */
function dialog(message: string, detail: string, buttons: string[]): Promise<string | null> {
  return new Promise((resolve) => {
    const shade = h("div", { class: "scm-dialog-shade" });
    const close = (picked: string | null): void => {
      shade.remove();
      resolve(picked);
    };
    const box = h(
      "div",
      { class: "scm-dialog monaco-dialog-box", role: "dialog", "aria-modal": "true", "aria-label": message },
      h("div", { class: "dialog-message-row" }, codicon("warning", "dialog-icon"), h("div", { class: "dialog-message-container" }, h("div", { class: "dialog-message" }, message), h("div", { class: "dialog-message-detail" }, detail))),
      h(
        "div",
        { class: "dialog-buttons-row" },
        h("div", { class: "dialog-buttons" }, ...buttons.map((b, i) => h("button", { type: "button", class: `monaco-button monaco-text-button${i ? " secondary" : ""}`, onclick: () => close(b) }, b)), h("button", { type: "button", class: "monaco-button monaco-text-button secondary", onclick: () => close(null) }, "Cancel")),
      ),
    );
    box.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close(null);
    });
    shade.append(box);
    document.body.append(shade);
    box.querySelector<HTMLButtonElement>("button")?.focus();
  });
}

// ===== the page =====

let shownPage: PageElement | null = null;
let redraw: (() => void) | null = null;

registerLayer(KEY, {
  isOpen: () => Boolean(shownPage?.open),
  open: () => drawPage(),
  show: () => undefined,
  dismiss: () => {
    if (shownPage) dismissDialog(shownPage);
  },
});

export function openScm(): void {
  if (shownPage?.open) return;
  layerOpened(KEY);
  drawPage();
}

onNotice((n) => {
  if (n.type === "sync_changed" || n.type === "project_changed" || n.type === "projects_changed") redraw?.();
});

const VIEW_MODE = "sab.scm.viewMode";
const SMART = "sab.scm.smartCommit";
function stored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function store(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // a private window: the choice lasts this page
  }
}

const baseName = (path: string): string => path.split("/").pop() ?? path;
const dirName = (path: string): string => (path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "");

function ago(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const s = Math.max(1, Math.round((Date.now() - then) / 1000));
  const unit = (n: number, one: string): string => `${n} ${one}${n === 1 ? "" : "s"} ago`;
  if (s < 60) return unit(s, "sec");
  if (s < 3600) return unit(Math.round(s / 60), "min");
  if (s < 86400) return unit(Math.round(s / 3600), "hr");
  if (s < 86400 * 7) return unit(Math.round(s / 86400), "day");
  if (s < 86400 * 30) return unit(Math.round(s / 86400 / 7), "wk");
  if (s < 86400 * 365) return unit(Math.round(s / 86400 / 30), "mo");
  return unit(Math.round(s / 86400 / 365), "yr");
}

interface Shown { which: string; path: string; commit?: string; conflict?: boolean; list: Resource[]; title: string }

function drawPage(): void {
  const { element, body, setHeading } = openAreaPage(KEY, SCM);
  shownPage = element;
  setOverTitle(SCM);
  setHeading(SCM);
  loadEditorStyles();
  body.classList.add("scm-page-body");
  const themeClass = (): string => (effectiveTheme().includes("dark") ? "vs-dark" : "vs");
  const root = h("div", { class: `scm-page monaco-workbench ${themeClass()}` });
  const offTheme = onThemeChange(() => {
    root.className = `scm-page monaco-workbench ${themeClass()}`;
    viewer?.setTheme(effectiveTheme());
  });
  const sidebar = h("div", { class: "part sidebar scm-sidebar", role: "complementary" });
  const changesBody = h("div", { class: "pane-body scm-view" });
  const graphBody = h("div", { class: "pane-body scm-view scm-history-view" });
  const editorPart = h("div", { class: "part editor scm-editor-part" });
  root.append(sidebar, h("div", { class: "scm-sash", role: "separator", "aria-orientation": "vertical" }), editorPart);
  body.replaceChildren(root);
  let changes: Changes | null = null;
  let status: Status | null = null;
  let current: Repository | null = null; // the repository the graph and the title actions are for
  const histories = new Map<string, History>();
  const opened = new Map<string, Resource[]>(); // a graph row's files, when opened
  const messages = new Map<string, string>(); // each repository's message box
  let mode = stored(VIEW_MODE) === "tree" ? "tree" : "list";
  let viewer: DiffViewer | null = null;
  let shown: Shown | null = null;
  const collapsedGroups = new Set<string>();
  const collapsedPanes = new Set<string>();

  // The sash between the side bar and the editor: dragged, as VS Code's.
  const sash = root.querySelector<HTMLElement>(".scm-sash")!;
  sash.addEventListener("pointerdown", (e) => {
    const start = e.clientX;
    const width = sidebar.getBoundingClientRect().width;
    const move = (m: PointerEvent): void => {
      sidebar.style.width = `${Math.max(170, Math.min(800, width + m.clientX - start))}px`;
    };
    const up = (): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });

  const call = async <T>(path: string, method = "GET", data?: unknown): Promise<T | null> => {
    try {
      return await api<T>(path, method, data);
    } catch (e) {
      toast((e as Error).message, "error");
      return null;
    }
  };

  const load = async (): Promise<void> => {
    const [got, said] = await Promise.all([call<Changes>("/git/changes"), call<Status>("/git?remote=1")]);
    if (!element.open) return;
    changes = got;
    status = said;
    const repos = changes?.repositories ?? [];
    current = repos.find((r) => r.which === current?.which) ?? repos[0] ?? null;
    drawSidebar();
    if (current && changes?.signed_in) void loadHistory(current);
  };
  redraw = () => void load();
  element.addEventListener("close", () => {
    redraw = null;
    offTheme();
    viewer?.dispose();
    closeMenus();
  });

  const loadHistory = async (repo: Repository, more = false): Promise<void> => {
    const had = histories.get(repo.which);
    const page = more && had ? had.page + 1 : 1;
    const got = await call<History>(`/git/history?which=${repo.which}&page=${page}`);
    if (!got || !element.open) return;
    if (more && had) got.rows = [...had.rows, ...got.rows];
    histories.set(repo.which, got);
    drawGraph();
  };

  // ===== the side bar: SOURCE CONTROL and GRAPH, VS Code's two views =====

  const paneHeader = (id: string, title: string, actions: HTMLElement | null, count?: number): HTMLElement => {
    const expanded = !collapsedPanes.has(id);
    const header = h(
      "div",
      { class: `pane-header${expanded ? " expanded" : ""}`, role: "button", tabindex: 0, "aria-expanded": String(expanded), "aria-label": `${title} Section`, "data-pane": id },
      codicon(expanded ? "chevron-down" : "chevron-right", "twisty-container"),
      h("h3", { class: "title", title }, title),
      count ? h("div", { class: "count-badge-wrapper" }, h("div", { class: "monaco-count-badge long" }, String(count))) : null,
      h("div", { class: "actions" }, actions),
    );
    const toggle = (): void => {
      if (collapsedPanes.has(id)) collapsedPanes.delete(id);
      else collapsedPanes.add(id);
      drawSidebar();
    };
    header.addEventListener("click", (e) => {
      if (!(e.target as Element).closest(".actions")) toggle();
    });
    header.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target === header) {
        e.preventDefault();
        toggle();
      }
    });
    return header;
  };

  const moreMenu = (repo: Repository): MenuEntry[] => {
    const which = repo.which;
    const off = (label: string): MenuItem => ({ label, disabled: true });
    const sub = (label: string, items: MenuEntry[]): MenuItem => ({ label, submenu: items });
    return [
      { label: "Pull", run: () => void pull(which) },
      { label: "Push", run: () => void push(which) },
      { label: "Clone", run: () => void cloneRepository() },
      { label: "Checkout to...", run: () => void checkoutTo(repo) },
      { label: "Fetch", run: () => void fetchNow() },
      null,
      sub("Commit", [
        { label: "Commit", run: () => void commit(repo) },
        { label: "Commit Staged", run: () => void commit(repo, "staged") },
        { label: "Commit All", run: () => void commit(repo, "all") },
        off("Undo Last Commit"),
        off("Abort Rebase"),
        null,
        off("Commit (Amend)"),
        off("Commit Staged (Amend)"),
        off("Commit All (Amend)"),
        null,
        off("Commit (Signed Off)"),
        off("Commit Staged (Signed Off)"),
        off("Commit All (Signed Off)"),
      ]),
      sub("Changes", [
        { label: "Stage All Changes", run: () => void stage(repo, repo.groups.workingTree.map((r) => r.path)) },
        { label: "Unstage All Changes", run: () => void stage(repo, repo.groups.index.map((r) => r.path), true) },
        { label: "Discard All Changes", run: () => void discard(repo, repo.groups.workingTree) },
      ]),
      sub("Pull, Push", [
        { label: "Sync", run: () => void sync(which) },
        off("Sync (Rebase)"),
        null,
        { label: "Pull", run: () => void pull(which) },
        off("Pull (Rebase)"),
        off("Pull from..."),
        null,
        { label: "Push", run: () => void push(which) },
        off("Push to..."),
        null,
        { label: "Fetch", run: () => void fetchNow() },
        off("Fetch (Prune)"),
        off("Fetch From All Remotes"),
      ]),
      sub("Branch", [
        off("Merge..."),
        off("Rebase Branch..."),
        null,
        { label: "Create Branch...", run: () => void createBranch(repo) },
        off("Create Branch From..."),
        null,
        off("Rename Branch..."),
        off("Delete Branch..."),
        off("Delete Remote Branch..."),
        null,
        off("Publish Branch..."),
      ]),
      sub("Remote", [off("Add Remote..."), off("Remove Remote")]),
      sub("Stash", [off("Stash"), off("Stash (Include Untracked)"), off("Stash Staged"), off("Apply Latest Stash"), off("Apply Stash..."), off("Pop Latest Stash"), off("Pop Stash..."), off("Drop Stash..."), off("Drop All Stashes...")]),
      sub("Tags", [off("Create Tag"), off("Delete Tag..."), off("Delete Remote Tag...")]),
      sub("Worktrees", [off("Create Worktree..."), off("Delete Worktree...")]),
      null,
      { label: "Disconnect from GitHub", run: () => void disconnect(which) },
      off("Show Git Output"),
    ];
  };

  const drawSidebar = (): void => {
    const repos = changes?.repositories ?? [];
    const scmActions = current
      ? actionBar(
          action(mode === "list" ? "list-tree" : "list-flat", mode === "list" ? "View as Tree" : "View as List", () => {
            mode = mode === "list" ? "tree" : "list";
            store(VIEW_MODE, mode);
            drawSidebar();
          }),
          action("check", "Commit", () => current && void commit(current)),
          action("refresh", "Refresh", () => void load()),
          action("ellipsis", "More Actions...", () => {
            const box = sidebar.querySelector<HTMLElement>('[data-pane="scm"] [data-codicon="ellipsis"]')!.getBoundingClientRect();
            if (current) menu(box.left, box.bottom, moreMenu(current), "More Actions...");
          }),
        )
      : null;
    const total = repos.reduce((n, r) => n + r.count, 0);
    const parts: HTMLElement[] = [paneHeader("scm", "SOURCE CONTROL", scmActions, total || undefined)];
    if (!collapsedPanes.has("scm")) {
      changesBody.replaceChildren(...drawChanges(repos));
      parts.push(changesBody);
    }
    const graphActions = current && changes?.signed_in
      ? actionBar(
          action("git-fetch", "Fetch From All Remotes", () => void fetchNow()),
          action("repo-pull", "Pull", () => current && void pull(current.which)),
          action("repo-push", "Push", () => current && void push(current.which)),
          action("refresh", "Refresh", () => current && void loadHistory(current)),
        )
      : null;
    parts.push(paneHeader("graph", "GRAPH", graphActions));
    if (!collapsedPanes.has("graph")) parts.push(graphBody);
    sidebar.replaceChildren(...parts.map((p) => (p.classList.contains("pane-body") ? p : h("div", { class: "pane" }, p))));
    sidebar.classList.toggle("graph-collapsed", collapsedPanes.has("graph"));
    if (!collapsedPanes.has("graph")) drawGraph();
  };

  // ===== SOURCE CONTROL: the welcome views, the repositories, the message box, the groups =====

  const welcome = (...children: (HTMLElement | string)[]): HTMLElement => h("div", { class: "welcome-view-content" }, ...children);
  const welcomeButton = (label: string, run: () => void): HTMLElement =>
    h("div", { class: "button-container" }, h("button", { type: "button", class: "monaco-button monaco-text-button", onclick: run }, label));

  const drawChanges = (repos: Repository[]): HTMLElement[] => {
    if (!changes?.signed_in) {
      return [
        welcome(
          h("p", {}, "In order to use Git features, you can sign in to GitHub and clone a repository or connect your team library or shared projects folder."),
          ...githubSignIn(status, () => void load()),
        ),
      ];
    }
    if (!repos.length) {
      return [
        welcome(
          h("p", {}, "The team library folder and the shared projects folder are not connected to a GitHub repository. You can clone a repository from GitHub, or connect a folder to one."),
          welcomeButton("Clone Repository", () => void cloneRepository()),
          welcomeButton("Connect Folder to Repository", () => void connectFolder()),
          h("p", {}, "Signed in to GitHub as ", h("strong", {}, changes.account ?? ""), "."),
        ),
      ];
    }
    const list = h("div", { class: "monaco-list", role: "tree", "aria-label": "Source Control Management", tabindex: 0 });
    const rows = h("div", { class: "monaco-list-rows" });
    list.append(rows);
    for (const repo of repos) {
      if (repos.length > 1) rows.append(providerRow(repo));
      rows.append(inputRow(repo), buttonRow(repo));
      const groups: [keyof Repository["groups"], string][] = [
        ["merge", "Merge Changes"],
        ["index", "Staged Changes"],
        ["workingTree", "Changes"],
      ];
      for (const [id, label] of groups) {
        const items = repo.groups[id];
        if (!items.length && id !== "workingTree") continue; // Merge and Staged: hidden when empty, as VS Code's
        rows.append(groupRow(repo, id, label, items));
        if (collapsedGroups.has(`${repo.which}:${id}`)) continue;
        for (const row of resourceRows(repo, id, items)) rows.append(row);
      }
    }
    return [list];
  };

  const providerRow = (repo: Repository): HTMLElement =>
    h(
      "div",
      { class: `monaco-list-row scm-provider-row${repo.which === current?.which ? " selected" : ""}`, role: "treeitem", "aria-level": 1, "data-provider": repo.which, onclick: () => { current = repo; drawSidebar(); void loadHistory(repo); } },
      h(
        "div",
        { class: "scm-provider" },
        codicon("repo"),
        h("div", { class: "monaco-icon-label" }, h("span", { class: "monaco-highlighted-label" }, repo.name)),
        h("div", { class: "actions" }, actionBar(
          h("li", { class: "action-item scm-status-bar-action" }, h("a", { class: "action-label", role: "button", title: `${repo.branch}, Checkout Branch/Tag...`, onclick: (e: Event) => { e.stopPropagation(); void checkoutTo(repo); } }, codicon("git-branch"), h("span", {}, repo.branch))),
          h("li", { class: "action-item scm-status-bar-action" }, h("a", { class: "action-label", role: "button", title: "Synchronize Changes", onclick: (e: Event) => { e.stopPropagation(); void sync(repo.which); } }, codicon("sync"), repo.behind ? h("span", {}, `${repo.behind}↓`) : null)),
          action("check", "Commit", () => void commit(repo)),
          action("ellipsis", "More Actions...", () => {
            const box = sidebar.querySelector<HTMLElement>(`[data-provider="${repo.which}"]`)?.getBoundingClientRect();
            menu(box?.left ?? 100, box?.bottom ?? 100, moreMenu(repo), "More Actions...");
          }),
        )),
        // scm.providerCountBadge's default (hidden): no count on the repository's row.
      ),
    );

  const inputRow = (repo: Repository): HTMLElement => {
    const placeholder = `Message (Ctrl+Enter to commit on "${repo.branch}")`;
    const box = h("textarea", { class: "scm-input-box", rows: 1, placeholder, "aria-label": "Source Control Input", spellcheck: "true", "data-which": repo.which }) as HTMLTextAreaElement;
    box.value = messages.get(repo.which) ?? "";
    const fit = (): void => {
      box.style.height = "auto";
      box.style.height = `${Math.min(Math.max(box.scrollHeight, 20), 134)}px`;
    };
    box.addEventListener("input", () => {
      messages.set(repo.which, box.value);
      fit();
    });
    box.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        void commit(repo);
      }
    });
    window.requestAnimationFrame(fit);
    const editor = h("div", { class: "scm-editor" }, h("div", { class: "scm-editor-container" }, box));
    box.addEventListener("focus", () => editor.classList.add("synthetic-focus"));
    box.addEventListener("blur", () => editor.classList.remove("synthetic-focus"));
    return h("div", { class: "monaco-list-row scm-input-row", role: "treeitem" }, h("div", { class: "scm-input" }, editor));
  };

  const buttonRow = (repo: Repository): HTMLElement => {
    const anything = repo.count > 0;
    const commitTip = `Commit Changes on "${repo.branch}"`;
    let primary: HTMLElement;
    if (!anything && (repo.behind > 0 || !repo.pulled)) {
      primary = h(
        "div",
        { class: "monaco-button-dropdown" },
        h("a", { class: "monaco-button monaco-text-button", role: "button", tabindex: 0, title: "Pull from GitHub", onclick: () => void sync(repo.which) }, codicon("sync"), h("span", {}, "Sync Changes"), repo.behind ? h("span", {}, ` ${repo.behind}`) : null, repo.behind ? codicon("arrow-down") : null),
      );
    } else {
      const dropdown = h("a", { class: `monaco-button monaco-dropdown-button${anything ? "" : " disabled"}`, role: "button", tabindex: 0, title: "More Actions...", "aria-label": "More Actions..." }, codicon("chevron-down"));
      dropdown.addEventListener("click", () => {
        const box = dropdown.getBoundingClientRect();
        menu(box.left, box.bottom, [
          { label: "Commit", run: () => void commit(repo) },
          { label: "Commit (Amend)", disabled: true },
          null,
          { label: "Commit & Push", run: () => void commit(repo) },
          { label: "Commit & Sync", run: () => void commit(repo, undefined, true) },
        ], "More Actions...");
      });
      primary = h(
        "div",
        { class: `monaco-button-dropdown${anything ? "" : " disabled"}` },
        h("a", { class: `monaco-button monaco-text-button${anything ? "" : " disabled"}`, role: "button", tabindex: 0, title: commitTip, "aria-disabled": anything ? undefined : "true", onclick: () => anything && void commit(repo) }, codicon("check"), h("span", {}, "Commit")),
        h("div", { class: "monaco-button-dropdown-separator" }, h("div", {})),
        dropdown,
      );
    }
    return h("div", { class: "monaco-list-row scm-button-row", role: "treeitem" }, h("div", { class: "button-container" }, primary));
  };

  const groupRow = (repo: Repository, id: string, label: string, items: Resource[]): HTMLElement => {
    const key = `${repo.which}:${id}`;
    const collapsed = collapsedGroups.has(key);
    const actions: HTMLElement[] = [];
    if (id === "merge") actions.push(action("add", "Stage All Merge Changes", () => void stage(repo, items.map((r) => r.path))));
    if (id === "index") actions.push(action("diff-multiple", "Open Staged Changes", () => openList(repo, items, "Staged Changes")), action("remove", "Unstage All Changes", () => void stage(repo, items.map((r) => r.path), true)));
    if (id === "workingTree") actions.push(action("diff-multiple", "Open Changes", () => openList(repo, items, "Changes")), action("discard", "Discard All Changes", () => void discard(repo, items)), action("add", "Stage All Changes", () => void stage(repo, items.map((r) => r.path))));
    const row = h(
      "div",
      { class: "monaco-list-row", role: "treeitem", "aria-level": 1, "aria-expanded": String(!collapsed), "data-group": id, tabindex: -1 },
      h(
        "div",
        { class: "monaco-tl-row" },
        h("div", { class: "monaco-tl-indent", style: { width: "0px" } }),
        h("div", { class: `monaco-tl-twistie collapsible${collapsed ? " collapsed" : ""}` }, codicon(collapsed ? "chevron-right" : "chevron-down")),
        h(
          "div",
          { class: "monaco-tl-contents" },
          h("div", { class: "resource-group" }, h("div", { class: "name" }, label), h("div", { class: "actions" }, actionBar(...actions)), h("div", { class: "count" }, h("div", { class: "monaco-count-badge long" }, String(items.length)))),
        ),
      ),
    );
    row.addEventListener("click", (e) => {
      if ((e.target as Element).closest(".actions")) return;
      if (collapsedGroups.has(key)) collapsedGroups.delete(key);
      else collapsedGroups.add(key);
      drawSidebar();
    });
    row.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const entries: MenuEntry[] = id === "index"
        ? [{ label: "Unstage All Changes", run: () => void stage(repo, items.map((r) => r.path), true) }]
        : id === "merge"
          ? [{ label: "Stage All Merge Changes", run: () => void stage(repo, items.map((r) => r.path)) }]
          : [{ label: "Discard All Changes", run: () => void discard(repo, items) }, { label: "Stage All Changes", run: () => void stage(repo, items.map((r) => r.path)) }];
      menu(e.clientX, e.clientY, entries, label);
    });
    return row;
  };

  const resourceMenu = (repo: Repository, group: string, r: Resource): MenuEntry[] => {
    const open = { label: "Open Changes", run: () => openDiff(repo, r, group) };
    const file = { label: "Open File", run: () => openFile(repo, r) };
    const head = { label: "Open File (HEAD)", run: () => openDiff(repo, r, group), disabled: r.status === "untracked" || r.status === "index_added" };
    if (group === "index") return [open, file, head, null, { label: "Unstage Changes", run: () => void stage(repo, [r.path], true) }, null, { label: "Reveal in File Explorer View", disabled: true }];
    if (group === "merge") return [file, null, { label: "Stage Changes", run: () => void stage(repo, [r.path]) }, { label: "Accept Theirs (Open Changes)", run: () => openDiff(repo, r, group) }];
    return [
      open,
      head,
      file,
      null,
      { label: "Stage Changes", run: () => void stage(repo, [r.path]) },
      { label: "Discard Changes", run: () => void discard(repo, [r]) },
      { label: "Add to .gitignore", disabled: true },
      null,
      { label: "Reveal in File Explorer View", disabled: true },
    ];
  };

  const resourceRow = (repo: Repository, group: string, r: Resource, depth: number, showFolder: boolean): HTMLElement => {
    const inline: HTMLElement[] = [action("go-to-file", "Open File", () => openFile(repo, r))];
    if (group === "index") inline.push(action("remove", "Unstage Changes", () => void stage(repo, [r.path], true)));
    else if (group === "merge") inline.push(action("add", "Stage Changes", () => void stage(repo, [r.path])));
    else inline.push(action("discard", "Discard Changes", () => void discard(repo, [r])), action("add", "Stage Changes", () => void stage(repo, [r.path])));
    const selected = shown && shown.which === repo.which && shown.path === r.path && !shown.commit;
    const strike = r.letter === "D" ? " strikethrough" : "";
    const row = h(
      "div",
      { class: `monaco-list-row${selected ? " selected focused" : ""}`, role: "treeitem", "aria-level": 2 + depth, "aria-label": `${r.path}, ${r.tooltip}`, "data-path": r.path, "data-group": group, "data-letter": r.letter, tabindex: -1, title: `${repo.scope ? r.path.slice(repo.scope.length + 1) : r.path} • ${r.tooltip}` },
      h(
        "div",
        { class: "monaco-tl-row" },
        h("div", { class: "monaco-tl-indent", style: { width: `${8 + depth * 8}px` } }),
        h("div", { class: "monaco-tl-twistie" }),
        h(
          "div",
          { class: "monaco-tl-contents" },
          h(
            "div",
            { class: "resource" },
            h(
              "div",
              { class: "name" },
              h(
                "div",
                { class: `monaco-icon-label file-icon${strike}` },
                codicon("file", "file-icon-glyph"),
                h("div", { class: "monaco-icon-label-container" }, h("span", { class: "monaco-icon-name-container" }, h("a", { class: "label-name", style: { color: `var(--vscode-${r.colour.replace(/\./g, "-")})` } }, baseName(r.path))), showFolder && dirName(r.path) ? h("span", { class: "monaco-icon-description-container" }, h("span", { class: "label-description" }, dirName(repo.scope ? r.path.slice(repo.scope.length + 1) : r.path))) : null),
                h("div", { class: "actions" }, actionBar(...inline)),
              ),
            ),
            h("div", { class: "decoration-letter", style: { color: `var(--vscode-${r.colour.replace(/\./g, "-")})` }, title: r.tooltip }, r.letter),
          ),
        ),
      ),
    );
    row.addEventListener("click", (e) => {
      if ((e.target as Element).closest(".actions")) return;
      openDiff(repo, r, group);
    });
    row.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      menu(e.clientX, e.clientY, resourceMenu(repo, group, r), r.path);
    });
    return row;
  };

  const resourceRows = (repo: Repository, group: string, items: Resource[]): HTMLElement[] => {
    if (mode === "list") return items.map((r) => resourceRow(repo, group, r, 0, true));
    // Tree: folders as rows, files under them (VS Code's View as Tree).
    const out: HTMLElement[] = [];
    const strip = (p: string): string => (repo.scope ? p.slice(repo.scope.length + 1) : p);
    const folders = new Map<string, Resource[]>();
    for (const r of items) {
      const d = dirName(strip(r.path));
      folders.set(d, [...(folders.get(d) ?? []), r]);
    }
    for (const [folder, rs] of [...folders.entries()].sort()) {
      let depth = 0;
      if (folder) {
        out.push(
          h(
            "div",
            { class: "monaco-list-row", role: "treeitem", "aria-level": 2, "aria-expanded": "true", "data-folder": folder },
            h("div", { class: "monaco-tl-row" }, h("div", { class: "monaco-tl-indent", style: { width: "8px" } }), h("div", { class: "monaco-tl-twistie collapsible" }, codicon("chevron-down")), h("div", { class: "monaco-tl-contents" }, h("div", { class: "resource" }, h("div", { class: "name" }, h("div", { class: "monaco-icon-label folder-icon" }, codicon("folder"), h("span", { class: "label-name" }, folder)))))),
          ),
        );
        depth = 1;
      }
      for (const r of rs) out.push(resourceRow(repo, group, r, depth, false));
    }
    return out;
  };

  // ===== GRAPH =====

  const drawGraph = (): void => {
    if (!current || !changes?.signed_in) {
      graphBody.replaceChildren();
      return;
    }
    const history = histories.get(current.which);
    if (!history) {
      graphBody.replaceChildren(h("div", { class: "scm-graph-loading" }, codicon("loading", "codicon-modifier-spin")));
      return;
    }
    const local = history.refs.find((r) => r.kind === "local");
    const remote = history.refs.find((r) => r.kind === "remote");
    const items: HistoryItem[] = history.rows.map((row) => ({
      id: row.id,
      parentIds: row.parents,
      subject: row.subject,
      author: row.author,
      date: row.date,
      message: row.message,
      references: history.refs.filter((ref) => ref.commit === row.id).map((ref): Ref => ({ id: ref.id, name: ref.name, kind: ref.kind })),
    }));
    // Incoming Changes: GitHub's head is ahead of the last commit synced here (VS Code's dashed node).
    if (local && remote && local.commit !== remote.commit) {
      const at = items.findIndex((i) => i.id === local.commit);
      if (at > 0) items.splice(at, 0, { id: INCOMING_ID, parentIds: [local.commit], subject: "Incoming Changes", author: "", date: "", message: "", references: [] });
    }
    const colors = new Map<string, string | undefined>();
    if (local) colors.set(local.id, REF_COLOR);
    if (remote) colors.set(remote.id, REMOTE_REF_COLOR);
    const models = viewModels(items, colors, local?.commit);
    const list = h("div", { class: "monaco-list", role: "tree", "aria-label": "Source Control Graph", tabindex: 0 });
    for (const model of models) {
      list.append(historyRow(current, model));
      const files = opened.get(model.item.id);
      if (files) for (const f of files) list.append(changeRow(current, model, f));
    }
    if (history.more) {
      list.append(h("div", { class: "monaco-list-row history-load-more", role: "treeitem", onclick: () => current && void loadHistory(current, true) }, h("div", { class: "history-item-load-more" }, h("span", {}, "Load More..."))));
    }
    graphBody.replaceChildren(list);
  };

  const hover = h("div", { class: "scm-hover monaco-hover", role: "tooltip", hidden: true });
  document.body.append(hover);
  element.addEventListener("close", () => hover.remove());

  const historyRow = (repo: Repository, model: ViewModel): HTMLElement => {
    const item = model.item;
    const isOpen = opened.has(item.id);
    const incoming = item.id === INCOMING_ID;
    const labels = (item.references ?? []).map((ref) =>
      h(
        "div",
        { class: "label", style: { color: "var(--vscode-scmGraph-historyItemHoverLabelForeground)", backgroundColor: ref.color ? `var(--vscode-${ref.color})` : "var(--vscode-scmGraph-historyItemHoverDefaultLabelBackground)" }, title: ref.name },
        codicon(ref.kind === "remote" ? "cloud" : "target"),
        h("div", { class: "description" }, ref.name),
      ),
    );
    const row = h(
      "div",
      { class: "monaco-list-row", role: "treeitem", "aria-level": 1, "aria-expanded": incoming ? undefined : String(isOpen), "data-commit": item.id, "aria-label": item.subject, tabindex: -1 },
      h(
        "div",
        { class: "monaco-tl-row" },
        h("div", { class: `monaco-tl-twistie${isOpen ? "" : " collapsed"}` }),
        h(
          "div",
          { class: "monaco-tl-contents" },
          h(
            "div",
            { class: "history-item" },
            h("div", { class: `graph-container${model.kind === "HEAD" ? " current" : ""}${incoming ? " incoming-changes" : ""}` }, graph(model)),
            h("div", { class: `monaco-icon-label${model.kind === "HEAD" ? " history-item-current" : ""}` }, h("div", { class: "monaco-icon-label-container" }, h("span", { class: "monaco-icon-name-container" }, h("a", { class: "label-name" }, item.subject)), item.author ? h("span", { class: "monaco-icon-description-container" }, h("span", { class: "label-description" }, item.author)) : null)),
            h("div", { class: "label-container" }, ...labels),
          ),
        ),
      ),
    );
    if (incoming) return row;
    row.addEventListener("click", () => void toggleCommit(repo, item.id));
    row.addEventListener("mouseenter", () => {
      const box = row.getBoundingClientRect();
      hover.replaceChildren(
        h("div", { class: "hover-contents" }, h("p", {}, codicon("account"), " ", h("strong", {}, item.author), item.date ? `, ${ago(item.date)} (${new Date(item.date).toLocaleString()})` : ""), h("p", { class: "hover-message" }, item.message)),
        h("div", { class: "hover-row status-bar" }, ...(item.references ?? []).map((ref) => h("span", { class: "hover-ref", style: { backgroundColor: ref.color ? `var(--vscode-${ref.color})` : "" } }, codicon(ref.kind === "remote" ? "cloud" : "target"), ref.name)), h("span", { class: "hover-sha" }, codicon("git-commit"), " ", item.id.slice(0, 8))),
      );
      hover.hidden = false;
      hover.style.left = `${box.right + 6}px`;
      hover.style.top = `${box.top}px`;
    });
    row.addEventListener("mouseleave", () => (hover.hidden = true));
    row.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      menu(e.clientX, e.clientY, [
        { label: "Checkout (Detached)", disabled: true },
        { label: "Create Branch...", disabled: item.id !== repo.commit, run: () => void createBranch(repo) },
        { label: "Create Tag...", disabled: true },
        null,
        { label: "Cherry Pick", disabled: true },
        null,
        { label: "Compare with Remote", disabled: true },
        { label: "Compare with Merge Base", disabled: true },
        { label: "Compare with...", disabled: true },
        null,
        { label: "Copy Commit Hash", run: () => void navigator.clipboard.writeText(item.id) },
        { label: "Copy Commit Message", run: () => void navigator.clipboard.writeText(item.message) },
      ], item.subject);
    });
    return row;
  };

  const changeRow = (repo: Repository, model: ViewModel, f: Resource): HTMLElement => {
    const row = h(
      "div",
      { class: `monaco-list-row${shown?.commit === model.item.id && shown.path === f.path ? " selected focused" : ""}`, role: "treeitem", "aria-level": 2, "data-commit-file": f.path, tabindex: -1, title: `${f.path} • ${f.tooltip}` },
      h(
        "div",
        { class: "monaco-tl-row" },
        h("div", { class: "monaco-tl-indent", style: { width: "8px" } }),
        h("div", { class: "monaco-tl-twistie" }),
        h(
          "div",
          { class: "monaco-tl-contents" },
          h(
            "div",
            { class: "history-item-change" },
            h("div", { class: "graph-container" }, placeholderGraph(model)),
            h("div", { class: "label-container" }, h("div", { class: "monaco-icon-label file-icon" }, codicon("file", "file-icon-glyph"), h("div", { class: "monaco-icon-label-container" }, h("span", { class: "monaco-icon-name-container" }, h("a", { class: "label-name", style: { color: `var(--vscode-${f.colour.replace(/\./g, "-")})` } }, baseName(f.path))), dirName(f.path) ? h("span", { class: "monaco-icon-description-container" }, h("span", { class: "label-description" }, dirName(f.path))) : null))),
            h("div", { class: "decoration-letter", style: { color: `var(--vscode-${f.colour.replace(/\./g, "-")})` } }, f.letter),
          ),
        ),
      ),
    );
    row.addEventListener("click", () => void showDiff({ which: repo.which, path: f.path, commit: model.item.id, list: opened.get(model.item.id) ?? [f], title: `${model.item.subject}` }));
    return row;
  };

  const placeholderGraph = (model: ViewModel): SVGSVGElement => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const lanes = model.output;
    svg.style.height = "22px";
    svg.style.width = `${11 * (lanes.length + 1)}px`;
    lanes.forEach((lane, i) => {
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", `M ${11 * (i + 1)} 0 V 22`);
      p.setAttribute("fill", "none");
      p.setAttribute("stroke-width", "1px");
      p.style.stroke = `var(--vscode-${lane.color})`;
      svg.append(p);
    });
    return svg;
  };

  const toggleCommit = async (repo: Repository, id: string): Promise<void> => {
    if (opened.has(id)) {
      opened.delete(id);
      drawGraph();
      return;
    }
    const got = await call<{ files: Resource[] }>(`/git/commit-files?which=${repo.which}&commit=${id}`);
    if (!got) return;
    opened.set(id, got.files);
    drawGraph();
  };

  // ===== the editor: Monaco's diff editor, the files beside it =====

  const openDiff = (repo: Repository, r: Resource, group: string): void => {
    const list = group === "index" ? repo.groups.index : group === "merge" ? repo.groups.merge : repo.groups.workingTree;
    void showDiff({ which: repo.which, path: r.path, conflict: group === "merge", list, title: group === "index" ? "Staged Changes" : group === "merge" ? "Merge Changes" : "Changes" });
  };
  const openList = (repo: Repository, items: Resource[], title: string): void => {
    if (items[0]) void showDiff({ which: repo.which, path: items[0].path, list: items, title });
  };
  const openFile = (repo: Repository, r: Resource): void => {
    toast(`${r.path} is in ${repo.folder}: open it in its own editor.`);
  };

  const showDiff = async (what: Shown): Promise<void> => {
    shown = what;
    const params = new URLSearchParams({ which: what.which, path: what.path });
    if (what.commit) params.set("commit", what.commit);
    if (what.conflict) params.set("conflict", "1");
    const got = await call<Diff>(`/git/diff?${params.toString()}`);
    if (!got || !element.open) return;
    const lib = await loadEditors();
    const host = h("div", { class: "scm-diff-host" });
    const at = what.list.findIndex((f) => f.path === what.path);
    const step = (by: number): void => {
      const next = what.list[at + by];
      if (next) void showDiff({ ...what, path: next.path });
    };
    const resource = what.list[at];
    const title = `${baseName(got.path)} (${what.commit ? `${what.commit.slice(0, 8)}` : what.conflict ? "Yours ↔ Theirs" : resource?.letter === "A" || got.added ? "Index" : "Working Tree"})`;
    const toolbar = actionBar(
      action("go-to-file", "Open File", () => toast(`${got.path}: open it in its own editor.`)),
      action("arrow-up", "Previous Change (Shift+F7)", () => viewer?.previous()),
      action("arrow-down", "Next Change (F7)", () => viewer?.next()),
      action("ellipsis", "More Actions...", () => {
        const box = editorPart.querySelector<HTMLElement>('.title-actions [data-codicon="ellipsis"]')!.getBoundingClientRect();
        menu(box.left - 160, box.bottom, [
          { label: "Inline View", checked: viewer?.inline() ?? false, run: () => viewer?.setInline(!(viewer?.inline() ?? false)) },
          null,
          { label: "Previous File", disabled: at <= 0, run: () => step(-1) },
          { label: "Next File", disabled: at >= what.list.length - 1, run: () => step(1) },
        ], "More Actions...");
      }),
      action("close", "Close (Ctrl+F4)", () => {
        shown = null;
        viewer?.dispose();
        viewer = null;
        editorPart.replaceChildren(emptyEditor());
        drawSidebar();
      }),
    );
    const files = h(
      "div",
      { class: "scm-diff-files monaco-list", role: "listbox", "aria-label": what.title },
      h("div", { class: "scm-diff-files-title" }, h("span", {}, what.title), actionBar(action("arrow-left", "Previous File", () => step(-1), at <= 0), action("arrow-right", "Next File", () => step(1), at >= what.list.length - 1))),
      ...what.list.map((f) =>
        h(
          "div",
          { class: `monaco-list-row${f.path === what.path ? " selected focused" : ""}`, role: "option", "aria-selected": String(f.path === what.path), "data-diff-file": f.path, onclick: () => void showDiff({ ...what, path: f.path }) },
          h("div", { class: "resource" }, codicon("file", "file-icon-glyph"), h("span", { class: "label-name", style: { color: `var(--vscode-${f.colour.replace(/\./g, "-")})` } }, baseName(f.path)), dirName(f.path) ? h("span", { class: "label-description" }, dirName(f.path)) : null, h("span", { class: "decoration-letter", style: { color: `var(--vscode-${f.colour.replace(/\./g, "-")})` } }, f.letter)),
        ),
      ),
    );
    editorPart.replaceChildren(
      h(
        "div",
        { class: "title tabs show-file-icons" },
        h("div", { class: "tabs-container", role: "tablist" }, h("div", { class: "tab active", role: "tab", "aria-selected": "true", title: `${got.original_label} ↔ ${got.modified_label}` }, codicon("file", "file-icon-glyph"), h("span", { class: "label-name scm-diff-title" }, title))),
        h("div", { class: "title-actions" }, toolbar),
      ),
      h("div", { class: "scm-diff-body" }, got.binary ? h("div", { class: "scm-binary" }, "The file is not displayed in the text compare editor because it is either binary or uses an unsupported text encoding.") : host, files),
    );
    if (!got.binary) {
      const inline = viewer?.inline() ?? false;
      viewer?.dispose();
      viewer = lib.createDiffViewer(host, effectiveTheme());
      viewer.setInline(inline);
      viewer.show(got.original, got.modified, got.path);
    }
    drawSidebar();
  };

  const emptyEditor = (): HTMLElement => h("div", { class: "scm-editor-empty" }, codicon("source-control", "letterpress"));
  editorPart.append(emptyEditor());

  // ===== the actions =====

  const after = async <T>(done: Promise<T | null>, words?: (t: T) => string): Promise<T | null> => {
    const got = await done;
    if (got && words) toast(words(got));
    await load();
    return got;
  };

  const stage = (repo: Repository, paths: string[], unstage = false): Promise<unknown> =>
    after(call("/git/stage", "POST", { which: repo.which, paths, unstage }));

  const discard = async (repo: Repository, items: Resource[]): Promise<void> => {
    if (!items.length) return;
    const one = items.length === 1 ? items[0]! : null;
    const untracked = one && (one.letter === "U" || one.letter === "A");
    const message = one
      ? untracked
        ? `Are you sure you want to DELETE ${baseName(one.path)}?\nThis is IRREVERSIBLE!\nThis file will be FOREVER LOST if you proceed.`
        : `Are you sure you want to discard changes in '${baseName(one.path)}'?`
      : `Are you sure you want to discard ALL changes in ${items.length} files?`;
    const picked = await dialog(message, one && !untracked ? "" : "This is IRREVERSIBLE!\nYour current working set will be FOREVER LOST if you proceed.", [untracked ? "Delete File" : one ? "Discard File" : `Discard All ${items.length} Files`]);
    if (!picked) return;
    await after(call("/git/discard", "POST", { which: repo.which, paths: items.map((r) => r.path) }));
  };

  const commit = async (repo: Repository, which?: "staged" | "all", syncFirst = false): Promise<void> => {
    const box = sidebar.querySelector<HTMLTextAreaElement>(`textarea[data-which="${repo.which}"]`);
    const message = (box?.value ?? messages.get(repo.which) ?? "").trim();
    let paths: string[] | undefined;
    const staged = repo.groups.index.map((r) => r.path);
    if (which === "all" || (!staged.length && which !== "staged")) {
      if (!repo.groups.workingTree.length && !staged.length) {
        await dialog("There are no changes to commit.", "", ["OK"]);
        return;
      }
      if (!staged.length && which !== "all" && stored(SMART) !== "always") {
        const picked = await dialog("There are no staged changes to commit.", "Would you like to stage all your changes and commit them directly?", ["Yes", "Always", "Never"]);
        if (!picked || picked === "Never") return;
        if (picked === "Always") store(SMART, "always");
      }
      paths = [...staged, ...repo.groups.workingTree.map((r) => r.path)];
    } else paths = staged;
    if (!message) {
      box?.focus();
      toast("Please provide a commit message", "error");
      return;
    }
    const done = await after(call<{ pushed: number; words: string }>("/git/commit", "POST", { which: repo.which, message, paths, sync: syncFirst }), (d) => d.words);
    if (done) {
      messages.delete(repo.which);
      histories.delete(repo.which);
      await load();
    }
  };

  const pull = (which: string): Promise<unknown> => after(call<{ words: string }>("/git/pull", "POST", { which }), (d) => d.words).then(() => histories.delete(which));
  const push = (which: string): Promise<unknown> => after(call<{ words: string }>("/git/push", "POST", { which }), (d) => d.words);
  const sync = (which: string): Promise<unknown> => after(call<{ words: string }>("/git/sync", "POST", { which }), (d) => d.words);
  const fetchNow = async (): Promise<void> => {
    await call("/git?remote=1");
    histories.clear();
    await load();
  };
  const disconnect = (which: string): Promise<unknown> => after(call("/git/disconnect", "POST", { which }));

  const checkoutTo = async (repo: Repository): Promise<void> => {
    const got = await call<{ current: string; branches: { name: string; commit: string }[] }>(`/git/branches?which=${repo.which}`);
    if (!got) return;
    const picked = await quickPick<string>(
      "Select a ref to checkout",
      [{ label: "+ Create new branch...", value: "\0create" }, ...got.branches.map((b) => ({ label: b.name, description: b.commit.slice(0, 8), value: b.name }))],
    );
    if (picked === "\0create") return createBranch(repo);
    if (picked && picked !== got.current) await after(call<{ words: string }>("/git/checkout", "POST", { which: repo.which, branch: picked }), (d) => d.words);
  };

  const createBranch = async (repo: Repository): Promise<void> => {
    const name = await quickPick<string>("Please provide a new branch name", [], (typed) => typed || null);
    if (name) await after(call<{ words: string }>("/git/checkout", "POST", { which: repo.which, branch: name, create: true }), (d) => d.words);
  };

  void load();
}

// ===== GitHub: sign-in, Clone Repository, Connect (the page's welcome and Settings') =====

function githubSignIn(status: Status | null, done: () => void): HTMLElement[] {
  const token = h("input", { type: "password", class: "input scm-token", placeholder: "github_pat_…", "aria-label": "Personal access token", autocomplete: "off", spellcheck: "false" });
  const use = (): void => {
    if (!token.value.trim()) return;
    void api("/git/sign-in/token", "POST", { token: token.value.trim() }).then(
      () => {
        token.value = "";
        done();
      },
      (e: Error) => toast(e.message, "error"),
    );
  };
  token.addEventListener("keydown", (e) => {
    if (e.key === "Enter") use();
  });
  const code = h("p", { class: "scm-device-code", hidden: true });
  const device = (): void => {
    void api<{ user_code: string; verification_uri: string; interval: number }>("/git/sign-in/device", "POST").then(
      (got) => {
        code.hidden = false;
        code.replaceChildren("Type ", h("strong", { class: "mono" }, got.user_code), " at ", h("a", { href: got.verification_uri, target: "_blank", rel: "noopener" }, got.verification_uri));
        window.open(got.verification_uri, "_blank", "noopener");
        const poll = (): void => {
          void api<{ state: string; interval?: number; words?: string }>("/git/sign-in/device/poll", "POST").then(
            (said) => {
              if (said.state === "pending") window.setTimeout(poll, (said.interval ?? 5) * 1000);
              else if (said.state === "signed_in") done();
              else code.textContent = said.words ?? said.state;
            },
            (e: Error) => toast(e.message, "error"),
          );
        };
        window.setTimeout(poll, got.interval * 1000);
      },
      (e: Error) => toast(e.message, "error"),
    );
  };
  return [
    h("div", { class: "button-container" }, h("button", { type: "button", class: "monaco-button monaco-text-button scm-device", onclick: device, disabled: status?.device ? undefined : true, title: status?.device ? "Sign in with GitHub" : "Sign in with GitHub needs the app's registration with GitHub: use a token" }, codicon("github"), " Sign in with GitHub")),
    code,
    h("p", {}, "Or use a fine-grained personal access token:"),
    h("ol", { class: "scm-token-steps" }, ...(status?.token_steps ?? []).map((s) => h("li", {}, s))),
    h("div", { class: "scm-token-row" }, token, h("button", { type: "button", class: "monaco-button monaco-text-button", onclick: use }, "Use Token")),
  ];
}

const WHICH_WORDS: Record<string, string> = { library: "Team library folder", shared: "Shared projects folder" };

async function pickRepository(): Promise<string | null> {
  const got = await api<{ repositories: { repository: string; branch: string; private: boolean }[] }>("/git/repositories").catch((e: Error) => {
    toast(e.message, "error");
    return null;
  });
  if (!got) return null;
  return quickPick<string>(
    "Provide repository URL or pick a repository source.",
    got.repositories.map((r) => ({ label: r.repository, description: r.private ? "Private" : "Public", value: r.repository })),
    (typed) => typed || null,
  );
}

async function pickWhich(): Promise<"library" | "shared" | null> {
  return quickPick<"library" | "shared">("Pick the folder", [
    { label: "Team library folder", description: "connections, variables, the shared catalog", value: "library" },
    { label: "Shared projects folder", description: "your team's projects", value: "shared" },
  ]);
}

export async function cloneRepository(): Promise<void> {
  const repository = await pickRepository();
  if (!repository) return;
  const which = await pickWhich();
  if (!which) return;
  const folder = await chooseFile({ title: `Choose a folder to clone ${repository} into`, mode: "folder" });
  if (!folder) return;
  const done = await api<{ files: number }>("/git/clone", "POST", { which, repository, folder }).catch((e: Error) => {
    toast(e.message, "error");
    return null;
  });
  if (done) toast(`Cloned ${repository}: ${done.files} files. It is the ${WHICH_WORDS[which]?.toLowerCase()} now.`);
}

export async function connectFolder(): Promise<void> {
  const which = await pickWhich();
  if (!which) return;
  const repository = await pickRepository();
  if (!repository) return;
  const done = await api<{ words: string }>("/git/connect", "POST", { which, repository }).catch((e: Error) => {
    toast(e.message, "error");
    return null;
  });
  if (done) toast(done.words);
}

/** The Team box's sign-in step (Settings' Join a team… and Start a team…, library.ts): Sign in with GitHub (the
 *  device flow: the code shown, GitHub opened, asked again until typed) or a token pasted once. The user's own:
 *  the agent never signs in. `done` runs once signed in. Drawn with the app's own buttons (Settings, not the
 *  Source Control page). */
export function teamSignIn(said: { device: boolean; token_steps: string[] }, done: () => void): HTMLElement {
  const box = h("div", { class: "team-sign-in" });
  const code = h("p", { class: "team-device-code", hidden: true });
  const token = h("input", { type: "password", class: "input team-token", placeholder: "github_pat_…", "aria-label": "Personal access token", autocomplete: "off", spellcheck: "false" });
  const use = (): Promise<unknown> =>
    api("/git/sign-in/token", "POST", { token: token.value.trim() }).then(
      () => {
        token.value = "";
        done();
      },
      (e: Error) => toast(e.message, "error"),
    );
  token.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && token.value.trim()) void use();
  });
  const device = async (): Promise<void> => {
    const got = await api<{ user_code: string; verification_uri: string; interval: number }>("/git/sign-in/device", "POST").catch((e: Error) => {
      toast(e.message, "error");
      return null;
    });
    if (!got) return;
    code.hidden = false;
    code.replaceChildren("Type ", h("strong", { class: "mono" }, got.user_code), " at ", h("a", { href: got.verification_uri, target: "_blank", rel: "noopener" }, got.verification_uri));
    window.open(got.verification_uri, "_blank", "noopener");
    const poll = (): void => {
      if (!box.isConnected) return;
      void api<{ state: string; interval?: number; words?: string }>("/git/sign-in/device/poll", "POST").then(
        (answer) => {
          if (answer.state === "pending") window.setTimeout(poll, (answer.interval ?? 5) * 1000);
          else if (answer.state === "signed_in") done();
          else code.textContent = answer.words ?? answer.state;
        },
        (e: Error) => toast(e.message, "error"),
      );
    };
    window.setTimeout(poll, got.interval * 1000);
  };
  const tokenPart = h(
    "details",
    { class: "team-token-part", open: said.device ? undefined : true },
    h("summary", {}, "Use a token"),
    h("ol", { class: "team-token-steps" }, ...said.token_steps.map((s) => h("li", {}, s))),
    h("div", { class: "row" }, token, button("Use the token", () => void (token.value.trim() ? use() : token.focus()), { class: "line" })),
  );
  box.append(
    ...(said.device ? [h("div", { class: "row" }, button("Sign in with GitHub", () => void device(), { icon: "user", class: "primary team-device" }))] : []),
    code,
    tokenPart,
  );
  return box;
}

// ===== the Project Explorer's shared cards =====

let cardStatus: Promise<Status | null> | null = null;
let cardAsked = 0;
/** The shared projects folder's sync, for the cards: asked when the Explorer draws, at most once a minute
 *  from GitHub (the backend keeps to that). */
export function sharedSync(): Promise<Status | null> {
  if (!cardStatus || Date.now() - cardAsked > 5000) {
    cardAsked = Date.now();
    cardStatus = scmOn().then((on) => (on ? api<Status>("/git?remote=1").catch(() => null) : null));
  }
  return cardStatus;
}
onNotice((n) => {
  if (n.type === "sync_changed") cardStatus = null;
});

/** A shared card's words ("↑2 to push", "↓1 behind", "Conflicts: 1"), or null when up to date or not connected. */
export function cardWords(status: Status | null, name: string): string | null {
  const shared = status?.folders.find((f) => f.which === "shared");
  if (!shared?.connected) return null;
  const own = shared.projects?.[name] ?? { to_push: 0, conflicts: 0 };
  if (own.conflicts) return `Conflicts: ${own.conflicts}`;
  if (!shared.pulled) return "↓ Pull";
  if (shared.behind) return `↓${shared.behind} behind`;
  if (own.to_push) return `↑${own.to_push} to push`;
  return null;
}

/** A shared card's Pull and Push (the shared projects folder's, Push scoped to the card's project). */
export function cardActions(status: Status | null, path: string): { label: string; run: () => Promise<unknown> }[] {
  const shared = status?.folders.find((f) => f.which === "shared");
  if (!shared?.connected) return [];
  const act = (route: string, data: unknown) => (): Promise<unknown> =>
    api<{ words: string }>(route, "POST", data).then(
      (d) => toast(d.words),
      (e: Error) => toast(e.message, "error"),
    );
  return [
    { label: "Pull", run: act("/git/pull", { which: "shared" }) },
    { label: "Push", run: act("/git/push", { which: "shared", path }) },
  ];
}

/** After Share: "Push it to GitHub now?" when the shared projects folder is connected. */
export async function offerPush(path: string, name: string): Promise<void> {
  const status = await sharedSync();
  const shared = status?.folders.find((f) => f.which === "shared");
  if (!shared?.connected) return;
  const picked = await dialog(`Push ${name} to GitHub now?`, `It goes to ${shared.repository} as one commit.`, ["Push"]);
  if (picked) await cardActions(status, path)[1]?.run();
}
