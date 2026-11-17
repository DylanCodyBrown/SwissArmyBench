/**
 * codeAppPage.ts: the Code App page, the Power Apps extension's front-end plug-in (the owner, 2026-11-17:
 * "pac actually simplifies a ton of this ... we let pac cli do the work"). Shown only while the extension is
 * on: the rail's Code App area appears when the app's modes list the code app type (codeAppOn). [PLUG-IN]
 *
 *   [STRIP]     the tools (Node.js, npm, the Power Apps CLI, the Power Platform CLI; Deno for phase 2), each
 *               found with its version or with its Install (the one missing-package prompt); who is signed
 *               in (Sign in opens the browser); the environment.
 *   [PROJECT]   no code app open: New code app (a name, an environment, a folder) and Open code app…; open:
 *               its name, environment, data sources (Dataverse tables, connectors; Remove), Add a Dataverse
 *               table, the generated models and services and the app's files (each opens in the Workbench's
 *               editor, TypeScript with Monaco's own language service).
 *   [CONNECTORS] the environment's connectors, searched; one's operations, inputs and outputs drawn as the
 *               APIs explorer draws an API's (read-only: no Author a call); Add to app with its connection.
 *   [LIVE]      Run live: the app's dev server in a pane through this server (its own secret in the
 *               address, as Streamlit's live pages), reloading on save; Local Play opens in the browser,
 *               where its connectors answer; Stop.
 *   [PUSH]      what Push runs (npm run build, pa app push), Push, the app's link, the environment's code
 *               apps and this session's pushes.
 *   [CUSTOM]    a custom connector from an API on the APIs page: its two files shown first (the dry run),
 *               then Make it (pac connector create).
 *   [RUNS]      every pa, pac and npm run of this session, its lines as they come (powerapps_output).
 *
 * ROUTING: GET /powerapps, /powerapps/connectors[/{name}], /powerapps/project[/files|/file] · POST
 *          /powerapps/project/new|open|close, /powerapps/sources[/remove], /powerapps/live, /powerapps/push,
 *          /powerapps/custom-connector · DELETE /powerapps/live · notices powerapps_*
 */
import { api, ApiError, onNotice, type Notice, token } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { button, h, icon, openDialog, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { type Missing, promptForError } from "./missingPackages";
import { dismissDialog, layerOpened, registerLayer, setOverTitle } from "./nav";
import { mountTree, type Value } from "./structureTree";

export const CODE_APP = "Code App";
const TYPE = "codeapp";

interface Tool { id: string; name: string; purpose: string; found: boolean; version: string | null; ok: boolean; phase: number; install: string; problem?: string }
interface Source { name: string; kind: string; connector: string; table?: string | null; dataset?: string | null; display_name?: string }
interface Generated { path: string; kind: string; name: string }
interface DataTs { written: string; target: string; cells: unknown[]; left: unknown[]; types: string[] }
interface Project {
  open: boolean;
  recent?: string | null;
  folder?: string;
  problem?: string;
  app?: { name: string; environment_id: string; app_id: string | null; local_url: string };
  environment?: string;
  sources?: Source[];
  generated?: Generated[];
  vite_plugin?: boolean;
}
interface Run { id: string; command: string; who: string; code: number | null; ok: boolean; done: boolean; output: string; seconds: number }
interface Live { running: boolean; ready?: boolean; pane?: string; play_url?: string | null; local_url?: string }
interface State { tools: { system: string; tools: Tool[] }; account: { signed_in: boolean; active: string | null } | null; environments: Environment[] | null; project: Project; live: Live; runs: Run[] }
interface Environment { name: string; id: string; url: string; active: boolean; project?: boolean }
interface Connector { name: string; display_name: string; description: string; tabular: boolean; in_app: boolean }
interface Parameter { name: string; in: string; type: string; required: boolean; default: Value; description: string }
interface Operation {
  id: string;
  operation_id: string;
  name: string;
  method: string;
  path: string;
  description: string;
  tags: string[];
  parameters: Parameter[];
  body: { required: boolean; schema: Value; example: Value } | null;
  responses: { status: string; description: string; schema: Value; example: Value }[];
}
interface Explored { name: string; display_name: string; title: string; from: string; operations: Operation[] }
interface TreeNode { name: string; path: string; children?: TreeNode[] }

/** Whether the extension is on here: the app's modes name the code app type. Asked once a page. */
let onAsked: Promise<boolean> | null = null;
export function codeAppOn(): Promise<boolean> {
  onAsked ??= api<{ modes: { type: string }[] }>("/app/modes").then((got) => got.modes.some((m) => m.type === TYPE), () => false);
  return onAsked;
}

let shownPage: PageElement | null = null;
let tab: "project" | "connectors" | "live" | "push" | "custom" | "runs" = "project";
let redraw: (() => void) | null = null;
const runLines = new Map<string, string[]>();
const runListeners = new Set<(run: string, line: string) => void>();

onNotice((notice: Notice) => {
  const said = notice as Notice & { run?: string | Run; line?: string };
  if (notice.type === "powerapps_output" && typeof said.run === "string" && typeof said.line === "string") {
    const lines = runLines.get(said.run) ?? [];
    lines.push(said.line);
    runLines.set(said.run, lines.slice(-2000));
    for (const listen of runListeners) listen(said.run, said.line);
  } else if (notice.type === "powerapps_project" || notice.type === "powerapps_live") {
    if (shownPage?.open && (tab === "project" || tab === "live")) redraw?.(); // the others keep what they show
  }
});

registerLayer(TYPE, {
  isOpen: () => Boolean(shownPage?.open),
  open: () => drawPage(),
  show: () => undefined,
  dismiss: () => {
    if (shownPage) dismissDialog(shownPage);
  },
});

export function openCodeApp(): void {
  if (shownPage?.open) return;
  layerOpened(TYPE);
  drawPage();
}

/** A call whose missing tool puts the install prompt in the user's face (Install runs this system's
 *  command on the server); any other failure is said in a toast. */
async function call<T>(path: string, method = "GET", body?: unknown, again?: () => void): Promise<T | null> {
  try {
    return await api<T>(path, method, body);
  } catch (e) {
    let said: unknown = e;
    if (e instanceof ApiError) {
      try {
        said = JSON.parse(e.message);
      } catch {
        said = e;
      }
    }
    const install = async (missing: Missing): Promise<void> => {
      await api("/powerapps/tools/install", "POST", { tool: (missing as Missing & { tool?: string }).tool });
    };
    if (!promptForError(said, { install, then: again })) toast((e as Error).message, "error");
    return null;
  }
}

const badge = (method: string): HTMLElement => h("span", { class: `api-method m-${method.toLowerCase()}` }, method);

/** The Workbench window, with this file of the open code app in its editor (`document`: a notebook or any
 *  document by its full path, opened as the Workbench opens it). */
function openInWorkbench(path: string, document = false): void {
  // The Workbench window this app opened before, as it is (asked by message: nothing reloads), else a new one.
  const name = "swissarmybench-codeapp-workbench";
  const found = window.open("", name);
  if (!found) {
    toast("The browser blocked the new window: allow pop-ups for this address.", "error");
    return;
  }
  let there = false;
  try {
    there = found.location.pathname === "/workbench";
  } catch {
    there = false;
  }
  if (there) found.postMessage({ sab: document ? "open" : "codefile", path }, location.origin);
  else found.location.href = `/workbench#${new URLSearchParams({ ...(token ? { token } : {}), [document ? "open" : "codefile"]: path }).toString()}`;
  found.focus();
}

function drawPage(): void {
  const { element, body, actions, foot, setHeading } = openAreaPage(TYPE, CODE_APP);
  shownPage = element;
  body.classList.add("ca-page");
  setOverTitle(CODE_APP);
  const strip = h("div", { class: "ca-strip", "aria-label": "Tools and sign-in" });
  const tabs = h("div", { class: "ca-tabs", role: "tablist", "aria-label": CODE_APP });
  const panel = h("div", { class: "ca-panel", role: "tabpanel" });
  body.replaceChildren(strip, tabs, panel);
  let state: State | null = null;
  let lastDataTs: DataTs | null = null;

  const load = async (): Promise<void> => {
    const got = await call<State>("/powerapps");
    if (!got || !element.open) return;
    state = got;
    draw();
  };
  redraw = () => void load();

  const draw = (): void => {
    if (!state) return;
    const project = state.project;
    setHeading(CODE_APP, project.open && project.app ? ` › ${project.app.name}` : "");
    setOverTitle(project.open && project.app ? `${CODE_APP} › ${project.app.name}` : CODE_APP);
    actions.replaceChildren(
      ...(project.open
        ? [button("Close", () => void close(), { icon: "close", class: "ghost ca-close" })]
        : [button("Open code app…", () => void openApp(), { icon: "folder", class: "ca-open" }), button("New code app", () => void newApp(), { icon: "plus", class: "primary ca-new" })]),
    );
    drawStrip();
    drawTabs();
    drawPanel();
  };

  // ----- the strip: tools, account, environment -----

  const drawStrip = (): void => {
    if (!state) return;
    // .NET is only how the Power Platform CLI is installed: shown while that is missing.
    const pacOk = state.tools.tools.some((t) => t.id === "pac" && t.ok);
    const chips = state.tools.tools.filter((t) => !(t.id === "dotnet" && pacOk)).map((t) =>
      h(
        "span",
        { class: `ca-tool ${t.ok ? "ok" : t.phase > 1 ? "later" : "missing"}`, "data-tool": t.id, title: `${t.name}: ${t.purpose}${t.problem ? ` (${t.problem})` : ""}` },
        icon(t.ok ? "check" : t.phase > 1 ? "clock" : "warning"),
        h("span", {}, t.name),
        t.version ? h("span", { class: "muted" }, t.version) : null,
        !t.ok && t.phase === 1 ? button("Install", () => void install(t), { class: "ghost ca-install" }) : null,
        !t.ok && t.phase > 1 ? h("span", { class: "muted" }, "phase 2") : null,
      ),
    );
    const who = state.account;
    const account = h(
      "span",
      { class: "ca-account" },
      icon("user"),
      who === null ? button("Who is signed in?", () => void account_(), { class: "link" }) : who.signed_in ? h("span", {}, who.active ?? "") : h("span", { class: "muted" }, "Not signed in"),
      who && !who.signed_in ? button("Sign in", () => void signIn(), { class: "primary ca-sign-in" }) : null,
    );
    const env = state.project.open ? h("span", { class: "ca-env", title: state.project.app?.environment_id ?? "" }, icon("globe"), state.project.environment || state.project.app?.environment_id || "") : null;
    strip.replaceChildren(h("div", { class: "ca-tools" }, ...chips), account, env ?? "");
  };

  const install = async (t: Tool): Promise<void> => {
    const done = await call<{ tools: Tool[] }>("/powerapps/tools/install", "POST", { tool: t.id });
    if (done) {
      toast(`${t.name} is installed.`);
      void load();
    }
  };
  const account_ = async (): Promise<void> => {
    const got = await call<State["account"]>("/powerapps/account");
    if (got && state) {
      state.account = got;
      drawStrip();
    }
  };
  const signIn = async (): Promise<void> => {
    toast("Sign in in the browser window that opens.");
    const got = await call<State["account"]>("/powerapps/account/sign-in", "POST", {});
    if (got && state) {
      state.account = got;
      drawStrip();
    }
  };

  // ----- the tabs -----

  const TABS: { id: typeof tab; label: string; needs: boolean }[] = [
    { id: "project", label: "Project", needs: false },
    { id: "connectors", label: "Connectors", needs: false },
    { id: "live", label: "Run live", needs: true },
    { id: "push", label: "Push", needs: true },
    { id: "custom", label: "Custom connector", needs: false },
    { id: "runs", label: "Runs", needs: false },
  ];
  const drawTabs = (): void => {
    const open = Boolean(state?.project.open);
    tabs.replaceChildren(
      ...TABS.map((t) => {
        const b = h("button", { type: "button", role: "tab", class: "ca-tab", "data-tab": t.id, "aria-selected": String(tab === t.id), disabled: t.needs && !open }, t.label);
        b.addEventListener("click", () => {
          tab = t.id;
          drawTabs();
          drawPanel();
        });
        return b;
      }),
    );
  };

  const drawPanel = (): void => {
    if (!state) return;
    foot.replaceChildren();
    if (tab === "project") drawProject();
    else if (tab === "connectors") void drawConnectors();
    else if (tab === "live") drawLive();
    else if (tab === "push") void drawPush();
    else if (tab === "custom") void drawCustom();
    else drawRuns();
  };

  // ----- Project -----

  const drawProject = (): void => {
    const project = state!.project;
    if (!project.open) {
      panel.replaceChildren(
        h("div", { class: "ca-empty" },
          h("p", { class: "empty-note" }, "No code app is open."),
          project.recent ? button(`Open ${project.recent.split(/[\\/]/).pop()} again`, () => void openApp(project.recent!), { icon: "folder", class: "ca-recent" }) : null,
        ),
      );
      return;
    }
    if (project.problem) {
      panel.replaceChildren(h("p", { class: "status-error" }, project.problem));
      return;
    }
    const app = project.app!;
    const sources = project.sources ?? [];
    const sourceRows = sources.map((s) =>
      h("tr", { "data-source": s.name },
        h("td", {}, icon(s.kind === "dataverse" ? "table" : "plug"), " ", s.name),
        h("td", {}, s.kind === "dataverse" ? "Dataverse table" : s.kind === "table" ? `${s.display_name ?? s.connector} table` : s.display_name ?? s.connector),
        h("td", { class: "mono" }, s.table ?? ""),
        h("td", { class: "ca-row-actions" },
          s.kind === "dataverse" ? button("Open as grid", () => void dataverseGrid(s), { icon: "table", class: "ghost ca-open-grid", title: `${s.name} as a grid, through the library's Dataverse connection` }) : null,
          button("Remove", () => void removeSource(s), { icon: "trash", class: "ghost ca-remove", title: `Remove ${s.name}` })),
      ),
    );
    const generated = project.generated ?? [];
    panel.replaceChildren(
      h("section", { class: "ca-app" },
        h("div", { class: "ca-facts" },
          h("span", {}, h("strong", {}, app.name)),
          h("span", { class: "mono muted" }, project.folder ?? ""),
          app.app_id ? h("span", { class: "muted" }, `Pushed as ${app.app_id}`) : h("span", { class: "muted" }, "Not pushed yet"),
        ),
      ),
      h("section", { class: "ca-sources" },
        h("div", { class: "ca-section-head" }, h("h2", {}, "Data sources"), button("Add a Dataverse table", () => addTable(), { icon: "plus", class: "ca-add-table" }), button("Add a connector", () => { tab = "connectors"; drawTabs(); drawPanel(); }, { icon: "plug" })),
        sources.length ? h("table", { class: "ca-table" }, h("thead", {}, h("tr", {}, ...["Name", "Kind", "Table", ""].map((t) => h("th", {}, t)))), h("tbody", {}, ...sourceRows)) : h("p", { class: "muted" }, "None yet."),
      ),
      h("section", { class: "ca-notebook" },
        h("div", { class: "ca-section-head" },
          h("h2", {}, "Data notebook"),
          button("Open data notebook", () => void openDataNotebook(), { icon: "notebook", class: "ca-data-notebook", title: "data.ipynb: SQL and TypeScript cells on one DuckDB" }),
          button("Use in app", () => void useInApp(), { icon: "export", class: "ca-use-in-app", title: "Write data.ts (the notebook's TypeScript, typed) into src/" }),
        ),
        dataTsLine(),
      ),
      h("section", { class: "ca-generated" },
        h("h2", {}, "Generated models and services"),
        generated.length
          ? h("ul", { class: "ca-files" }, ...generated.map((g) => h("li", {}, h("button", { type: "button", class: "link ca-file", "data-path": g.path, onclick: () => openInWorkbench(g.path) }, icon(g.kind === "service" ? "bolt" : "schema"), g.name), h("span", { class: "muted" }, ` ${g.kind}`))))
          : h("p", { class: "muted" }, "Added data sources make them."),
      ),
      h("section", { class: "ca-tree" }, h("h2", {}, "Files"), h("div", { class: "ca-tree-host" }, h("p", { class: "muted" }, "…"))),
    );
    void drawTree(panel.querySelector<HTMLElement>(".ca-tree-host")!);
  };

  const openDataNotebook = async (): Promise<void> => {
    const got = await call<{ path: string }>("/powerapps/notebook/open", "POST", {});
    if (got) openInWorkbench(got.path, true);
  };

  /** The last Use in app's data.ts (kept while the page redraws): the file, and what went into it. */
  const dataTsLine = (): HTMLElement => {
    const host = h("div", { class: "ca-data-ts" });
    const got = lastDataTs;
    if (!got) return host;
    const words = [`${got.cells.length} cell${got.cells.length === 1 ? "" : "s"} exported`, got.types.length ? `${got.types.length} typed result${got.types.length === 1 ? "" : "s"}` : "", got.left.length ? `${got.left.length} kept in the notebook` : ""].filter(Boolean).join(", ");
    host.append(h("button", { type: "button", class: "link ca-file", "data-path": got.target, onclick: () => openInWorkbench(got.target) }, icon("code"), got.target), h("span", { class: "muted" }, ` ${words}`));
    return host;
  };

  const useInApp = async (): Promise<void> => {
    const got = await call<DataTs>("/powerapps/notebook/use-in-app", "POST", {});
    if (!got) return;
    lastDataTs = got;
    panel.querySelector<HTMLElement>(".ca-data-ts")?.replaceWith(dataTsLine());
  };

  const dataverseGrid = async (s: Source): Promise<void> => {
    const got = await call<{ opened: boolean; dataset?: string; message?: string }>("/powerapps/dataverse/grid", "POST", { source: s.name });
    if (!got) return;
    toast(got.opened ? `${got.dataset ?? s.name} is open as a grid.` : (got.message ?? ""), got.opened ? "info" : "error");
  };

  const drawTree = async (host: HTMLElement): Promise<void> => {
    const got = await call<{ tree: TreeNode }>("/powerapps/project/files");
    if (!got) return;
    const node = (n: TreeNode): HTMLElement =>
      n.children
        ? h("details", { class: "ca-folder", open: n.path === "src" }, h("summary", {}, icon("folder"), n.name), h("ul", {}, ...n.children.map((c) => h("li", {}, node(c)))))
        : h("button", { type: "button", class: "link ca-file", "data-path": n.path, onclick: () => openInWorkbench(n.path) }, icon("page"), n.name);
    host.replaceChildren(h("ul", { class: "ca-files" }, ...(got.tree.children ?? []).map((c) => h("li", {}, node(c)))));
  };

  const addTable = (): void => {
    const { body: box, foot: buttons, close } = openDialog("Add a Dataverse table");
    const table = h("input", { "aria-label": "The table's logical name", placeholder: "account", spellcheck: false }) as HTMLInputElement;
    box.append(h("label", { class: "ca-field" }, h("span", {}, "Table (its logical name)"), table));
    buttons.append(button("Cancel", () => close()), button("Add", async () => {
      const done = await call<Project>("/powerapps/sources", "POST", { kind: "dataverse", table: table.value });
      if (!done) return;
      close();
      toast(`Added ${table.value}.`);
      void load();
    }, { class: "primary" }));
    table.focus();
  };

  const removeSource = async (s: Source): Promise<void> => {
    if (!confirm(`Remove ${s.name} from the app? Its generated model and service go too.`)) return;
    const done = await call<Project>("/powerapps/sources/remove", "POST", { name: s.name, connector: s.connector });
    if (done) void load();
  };

  // ----- New, Open, Close -----

  const newApp = async (): Promise<void> => {
    const { body: box, foot: buttons, close } = openDialog("New code app");
    const name = h("input", { "aria-label": "The app's name", placeholder: "Expense Tracker" }) as HTMLInputElement;
    const environment = h("select", { "aria-label": "The environment" }) as HTMLSelectElement;
    const typed = h("input", { "aria-label": "The environment's id", placeholder: "00000000-0000-0000-0000-000000000000", hidden: true, spellcheck: false }) as HTMLInputElement;
    const folder = h("input", { "aria-label": "The folder it goes in", readonly: true }) as HTMLInputElement;
    const pick = button("Choose…", async () => {
      const chosen = await chooseFile({ title: "The folder the code app goes in", mode: "folder" });
      if (chosen) folder.value = chosen;
    });
    box.append(
      h("label", { class: "ca-field" }, h("span", {}, "Name"), name),
      h("label", { class: "ca-field" }, h("span", {}, "Environment"), environment, typed),
      h("label", { class: "ca-field" }, h("span", {}, "Folder"), h("span", { class: "ca-row" }, folder, pick)),
    );
    const fill = (envs: Environment[]): void => {
      environment.replaceChildren(...envs.map((e) => h("option", { value: e.id, selected: e.active }, e.name)), h("option", { value: "" }, "Another (its id)…"));
      typed.hidden = envs.length > 0;
    };
    environment.addEventListener("change", () => (typed.hidden = environment.value !== ""));
    if (state?.environments) fill(state.environments);
    else void call<{ environments: Environment[] }>("/powerapps/environments").then((got) => fill(got?.environments ?? []));
    buttons.append(button("Cancel", () => close()), button("Make it", async () => {
      const made = button("Making…", () => undefined, { class: "primary" });
      made.disabled = true;
      const done = await call<Project>("/powerapps/project/new", "POST", { name: name.value, environment_id: environment.value || typed.value, parent: folder.value });
      if (!done) return;
      close();
      tab = "project";
      toast(`Made ${name.value}.`);
      void load();
    }, { class: "primary ca-make" }));
    name.focus();
  };

  const openApp = async (folder?: string): Promise<void> => {
    const chosen = folder ?? (await chooseFile({ title: "A code app's folder (it has power.config.json)", mode: "folder" }));
    if (!chosen) return;
    const done = await call<Project>("/powerapps/project/open", "POST", { folder: chosen });
    if (done) void load();
  };

  const close = async (): Promise<void> => {
    const done = await call<Project>("/powerapps/project/close", "POST", {});
    if (done) void load();
  };

  // ----- Connectors: the list, and one as the APIs explorer draws it -----

  const drawConnectors = async (query = ""): Promise<void> => {
    const search = h("input", { type: "search", class: "apis-search ca-search", placeholder: "Search the environment's connectors", "aria-label": "Search the environment's connectors", value: query }) as HTMLInputElement;
    const list = h("div", { class: "apis-cards ca-connectors", role: "list" }, h("p", { class: "muted" }, "…"));
    panel.replaceChildren(h("div", { class: "ca-section-head" }, search, button("Refresh", () => void fill(true), { icon: "reset", class: "ghost" })), list);
    let timer = 0;
    search.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void fill(), 250);
    });
    const fill = async (refresh = false): Promise<void> => {
      const got = await call<{ connectors: Connector[]; total: number }>(`/powerapps/connectors?q=${encodeURIComponent(search.value.trim())}${refresh ? "&refresh=1" : ""}`);
      if (!got) return;
      list.replaceChildren(
        ...(got.connectors.length
          ? got.connectors.map((c) =>
              h("article", { class: "api-card ca-connector", role: "listitem", "data-connector": c.name },
                h("button", { type: "button", class: "api-card-open", onclick: () => void explore(c) }, h("span", { class: "api-card-name" }, icon("plug"), c.display_name), h("span", { class: "muted mono" }, c.name)),
                h("p", { class: "muted" }, c.description),
                h("div", { class: "api-card-facts" }, c.tabular ? h("span", {}, "tables") : h("span", {}, "actions"), c.in_app ? h("span", { class: "ca-in-app" }, icon("check"), "in the app") : null),
                h("div", { class: "api-card-actions" }, button("Add to app", () => void addToApp(c), { icon: "plus", class: "ca-add-connector" })),
              ),
            )
          : [h("p", { class: "empty-note" }, "No match.")]),
      );
    };
    await fill();
  };

  const explore = async (c: Connector): Promise<void> => {
    const got = await call<Explored>(`/powerapps/connectors/${encodeURIComponent(c.name)}`);
    if (!got) return;
    foot.replaceChildren(button("← Connectors", () => void drawConnectors(), { class: "ghost" }));
    const left = h("nav", { class: "api-ops", "aria-label": `${got.display_name}'s operations` });
    const right = h("div", { class: "api-detail" });
    const groups = new Map<string, Operation[]>();
    for (const op of got.operations) groups.set(op.tags[0] || "Operations", [...(groups.get(op.tags[0] || "Operations") ?? []), op]);
    for (const [tag, ops] of groups) {
      const group = h("details", { class: "api-tag", open: true }, h("summary", {}, tag, h("span", { class: "count" }, String(ops.length))));
      for (const op of ops) {
        const item = h("button", { type: "button", class: "api-op", "data-operation": op.operation_id || op.id, title: op.name }, badge(op.method), h("code", {}, op.operation_id || op.path));
        item.addEventListener("click", () => {
          left.querySelectorAll(".current").forEach((x) => x.classList.remove("current"));
          item.classList.add("current");
          showOperation(got, c, op, right);
        });
        group.append(item);
      }
      left.append(group);
    }
    panel.replaceChildren(
      h("div", { class: "ca-section-head" }, h("h2", {}, icon("plug"), " ", got.display_name), h("span", { class: "muted" }, `read from ${got.from}`), button("Add to app", () => void addToApp(c), { icon: "plus", class: "primary ca-add-connector" })),
      h("div", { class: "api-explorer" }, left, right),
    );
    left.querySelector<HTMLElement>(".api-op")?.click();
  };

  const tree = (title: string, value: Value, schema: boolean): HTMLElement =>
    h("div", { class: "api-tree-block" }, h("h4", {}, title), mountTree(value, { depth: 3, schema, label: title }).element);

  const showOperation = (got: Explored, c: Connector, op: Operation, right: HTMLElement): void => {
    const service = `${c.name.replace(/^shared_/, "").replace(/^./, (x) => x.toUpperCase())}Service`;
    const inputs = op.parameters.length
      ? h("table", { class: "api-params" }, h("thead", {}, h("tr", {}, ...["Name", "Where", "Type", "Required", "Description"].map((t) => h("th", {}, t)))), h("tbody", {}, ...op.parameters.map((p) => h("tr", {}, h("td", { class: "mono" }, p.name), h("td", {}, p.in), h("td", {}, p.type), h("td", {}, p.required ? "yes" : ""), h("td", {}, p.description)))))
      : h("p", { class: "muted" }, "No inputs.");
    right.replaceChildren(
      h("h2", { class: "api-op-title" }, badge(op.method), h("code", {}, op.path)),
      h("p", { class: "api-op-name" }, op.name),
      op.description ? h("p", {}, op.description) : "",
      op.operation_id ? h("p", { class: "ca-method" }, "In the app: ", h("code", {}, `${service}.${op.operation_id}(…)`)) : "",
      h("section", { class: "api-inputs" }, h("h3", {}, "Inputs"), inputs, op.body ? h("div", { class: "api-two" }, tree(`Body${op.body.required ? " (required)" : ""}`, op.body.schema, true), tree("Example", op.body.example, false)) : ""),
      h("section", { class: "api-outputs" }, h("h3", {}, "Outputs"), ...op.responses.map((r) => h("div", { class: "api-answer" }, h("h4", {}, h("span", { class: `api-status s${r.status[0]}` }, r.status), " ", r.description), r.schema ? h("div", { class: "api-two" }, tree("Schema", r.schema, true), tree("Example", r.example, false)) : h("p", { class: "muted" }, "No body.")))),
    );
  };

  const addToApp = async (c: Connector): Promise<void> => {
    if (!state?.project.open) {
      toast("Open a code app first (Project).", "error");
      return;
    }
    const got = await call<{ connections: { id: string; display_name: string; status: string }[] }>(`/powerapps/connections?connector=${encodeURIComponent(c.name)}`);
    if (!got) return;
    const { body: box, foot: buttons, close } = openDialog(`Add ${c.display_name} to the app`);
    const choice = h("select", { "aria-label": "Its connection" }, ...got.connections.map((x) => h("option", { value: x.id }, `${x.display_name} (${x.status || "connection"})`))) as HTMLSelectElement;
    const asKind = h("select", { "aria-label": "Add it as" }, h("option", { value: "" }, c.tabular ? "A table" : "Its actions"), h("option", { value: "action" }, "Its actions"), h("option", { value: "table" }, "A table")) as HTMLSelectElement;
    const dataset = h("input", { "aria-label": "Dataset", placeholder: "A site, or server,database" }) as HTMLInputElement;
    const table = h("input", { "aria-label": "Table", placeholder: "A list or a table" }) as HTMLInputElement;
    box.append(
      got.connections.length ? h("label", { class: "ca-field" }, h("span", {}, "Connection"), choice) : h("p", { class: "status-error" }, `No connection to ${c.display_name} yet: make one in Power Apps (Connections), then come back.`),
      ...(c.tabular ? [h("label", { class: "ca-field" }, h("span", {}, "Add it as"), asKind), h("label", { class: "ca-field" }, h("span", {}, "Dataset"), dataset), h("label", { class: "ca-field" }, h("span", {}, "Table"), table)] : []),
    );
    buttons.append(button("Cancel", () => close()), button("Add", async () => {
      const wanted = c.tabular ? asKind.value || "table" : "";
      const done = await call<Project>("/powerapps/sources", "POST", { kind: "connector", connector: c.name, connection_id: choice.value, as: wanted === "action" ? "action" : null, dataset: wanted === "table" ? dataset.value : null, table: wanted === "table" ? table.value : null });
      if (!done) return;
      close();
      toast(`Added ${c.display_name}.`);
      if (state) state.project = done;
    }, { class: "primary ca-add" }));
  };

  // ----- Run live -----

  const drawLive = (): void => {
    const live = state!.live;
    const output = h("pre", { class: "ca-output", "aria-live": "polite" });
    const frame = live.running && live.pane ? (h("iframe", { class: "ca-live-frame", src: live.pane, title: "The code app, live", sandbox: "allow-scripts allow-forms allow-popups" }) as HTMLIFrameElement) : null;
    panel.replaceChildren(
      h("div", { class: "ca-section-head" },
        live.running
          ? button("Stop", () => void stopLive(), { icon: "stop", class: "ca-stop" })
          : button("Run live", () => void startLive(), { icon: "play", class: "primary ca-run-live" }),
        live.running && live.play_url ? playButton(live.play_url) : null,
        live.running ? h("span", { class: "muted" }, live.ready ? "Running: it reloads as you save." : "Starting…") : h("span", { class: "muted" }, "The app's dev server, here; Local Play opens it in Power Apps, where its data answers."),
      ),
      frame ?? h("div", { class: "ca-live-empty" }, icon("play"), h("p", { class: "muted" }, "Not running.")),
      output,
    );
  };
  const playButton = (url: string): HTMLElement => {
    const b = button("Local Play", () => void window.open(url, "_blank", "noopener,noreferrer"), { icon: "popout", class: "ca-play", title: "In your browser, signed in: its connectors answer there" });
    b.dataset.href = url;
    return b;
  };
  const startLive = async (): Promise<void> => {
    const done = await call<Live>("/powerapps/live", "POST", {});
    if (done && state) {
      state.live = done;
      drawLive();
    }
  };
  const stopLive = async (): Promise<void> => {
    const done = await call<Live>("/powerapps/live", "DELETE");
    if (done && state) {
      state.live = done;
      drawLive();
    }
  };

  // ----- Push -----

  const drawPush = async (): Promise<void> => {
    const plan = await call<{ commands: string[]; app: string; environment: string }>("/powerapps/push", "POST", { dry_run: true });
    if (!plan) return;
    const result = h("div", { class: "ca-push-result" });
    panel.replaceChildren(
      h("section", { class: "ca-push" },
        h("p", {}, "Push makes a new version of ", h("strong", {}, plan.app), " in ", h("strong", {}, plan.environment), ":"),
        h("ol", { class: "ca-commands" }, ...plan.commands.map((c) => h("li", {}, h("code", {}, c)))),
        h("div", { class: "ca-section-head" }, button("Push", () => void push(result), { icon: "upload", class: "primary ca-push-button" }), button("Versions", () => void versions(result), { icon: "clock", class: "ghost ca-versions" })),
        result,
      ),
    );
  };
  const push = async (result: HTMLElement): Promise<void> => {
    result.replaceChildren(h("p", { class: "muted" }, "Pushing… (its lines are under Runs)"));
    const done = await call<{ link: string | null }>("/powerapps/push", "POST", {});
    if (!done) {
      result.replaceChildren();
      return;
    }
    result.replaceChildren(h("p", { class: "ca-pushed" }, icon("check"), " Pushed. ", done.link ? h("a", { href: done.link, target: "_blank", rel: "noopener noreferrer" }, "Open the app") : ""));
  };
  const versions = async (result: HTMLElement): Promise<void> => {
    const got = await call<{ apps: { id: string; name: string; this: boolean }[]; pushes: { at: number; link: string | null; who: string }[] }>("/powerapps/versions");
    if (!got) return;
    result.replaceChildren(
      h("h3", {}, "This session's pushes"),
      got.pushes.length ? h("ul", {}, ...got.pushes.map((p) => h("li", {}, new Date(p.at * 1000).toLocaleString(), p.who === "agent" ? " (the agent)" : "", " ", p.link ? h("a", { href: p.link, target: "_blank", rel: "noopener noreferrer" }, "Open") : ""))) : h("p", { class: "muted" }, "None this session."),
      h("h3", {}, "The environment's code apps"),
      h("ul", {}, ...got.apps.map((a) => h("li", { class: a.this ? "ca-this" : "" }, a.name, a.this ? h("span", { class: "muted" }, " (this one)") : "", h("span", { class: "muted mono" }, ` ${a.id}`)))),
    );
  };

  // ----- Custom connector -----

  const drawCustom = async (): Promise<void> => {
    const listed = await call<{ apis: { name: string; title: string; auth: string; operations: number }[] }>("/apis");
    if (!listed) return;
    const choice = h("select", { "aria-label": "The API", class: "ca-api" }, ...listed.apis.map((a) => h("option", { value: a.name }, `${a.name} (${a.operations} operations, sign-in: ${a.auth})`))) as HTMLSelectElement;
    const shown = h("div", { class: "ca-custom-files" });
    panel.replaceChildren(
      h("section", { class: "ca-custom" },
        listed.apis.length ? h("label", { class: "ca-field" }, h("span", {}, "From the API"), choice) : h("p", { class: "empty-note" }, "No APIs yet: add one on the APIs page."),
        listed.apis.length ? h("div", { class: "ca-section-head" }, button("Show its files", () => void dry(), { icon: "eye", class: "primary ca-dry-run" })) : null,
        shown,
      ),
    );
    const dry = async (): Promise<void> => {
      const got = await call<{ files: Record<string, string>; operations: number; title: string; host: string; sign_in: string }>("/powerapps/custom-connector", "POST", { api: choice.value, dry_run: true });
      if (!got) return;
      shown.replaceChildren(
        h("p", {}, h("strong", {}, got.title), ` · ${got.host} · ${got.operations} operations · ${got.sign_in}`),
        ...Object.entries(got.files).map(([name, text]) => h("details", { class: "ca-file-text", open: name.startsWith("apiProperties") }, h("summary", {}, icon("page"), " ", name), h("pre", { class: "mono" }, text))),
        h("div", { class: "ca-section-head" }, button("Make the connector", () => void make(), { icon: "plug", class: "primary ca-make-connector" }), h("span", { class: "muted" }, "pac connector create, in the code app's connectors folder")),
      );
    };
    const make = async (): Promise<void> => {
      const done = await call<{ made: boolean; files: string[] }>("/powerapps/custom-connector", "POST", { api: choice.value, dry_run: false });
      if (done) toast(`The custom connector is made (${done.files.length} files written).`);
    };
  };

  // ----- Runs -----

  const drawRuns = (): void => {
    const runs = state!.runs;
    const list = h("ol", { class: "ca-runs" });
    const fill = (all: Run[]): void => {
      list.replaceChildren(
        ...all.map((r) => {
          const lines = runLines.get(r.id) ?? r.output.split("\n");
          return h("li", { class: `ca-run ${r.done ? (r.ok ? "ok" : "failed") : "running"}`, "data-run": r.id },
            h("details", {}, h("summary", {}, icon(r.done ? (r.ok ? "check" : "warning") : "clock"), h("code", {}, r.command), h("span", { class: "muted" }, ` ${r.who === "agent" ? "the agent" : "you"}${r.done ? `, ${r.seconds.toFixed(1)} s` : ""}`)), h("pre", { class: "ca-output" }, lines.join("\n"))),
          );
        }),
      );
    };
    fill(runs);
    panel.replaceChildren(list.childElementCount ? list : h("p", { class: "empty-note" }, "No runs this session."));
    void call<{ runs: Run[] }>("/powerapps/runs").then((got) => {
      if (got && tab === "runs") {
        fill(got.runs);
        panel.replaceChildren(got.runs.length ? list : h("p", { class: "empty-note" }, "No runs this session."));
      }
    });
  };

  // The lines of a run as they come, under Runs and Run live.
  const listen = (run: string, line: string): void => {
    if (!element.open) {
      runListeners.delete(listen);
      return;
    }
    const pre = panel.querySelector<HTMLElement>(`[data-run="${CSS.escape(run)}"] .ca-output`) ?? (tab === "live" ? panel.querySelector<HTMLElement>(".ca-output") : null);
    if (pre) pre.textContent = `${pre.textContent ? `${pre.textContent}\n` : ""}${line}`;
  };
  runListeners.add(listen);
  element.addEventListener("close", () => {
    runListeners.delete(listen);
    redraw = null;
    shownPage = null;
  });
  void load();
}
