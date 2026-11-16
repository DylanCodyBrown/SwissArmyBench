/**
 * main.ts: the grid page, put together. [EXPORT: bootstrap, composition only]
 *
 * One page holds every open grid: the tab bar and the grid panes (two side by side when split)
 * are panes.ts; everything else here (toolbar, ribbon, steps, the Analysis Sandbox in the Agent
 * tab, SQL box, status bar) is shared and shows the active grid. /g/<id> opens the page on that grid, /workspace on
 * the last one used.
 *
 * COMPOSES: panes (tabs, panes, split) · gridView + selection (one per grid) · ribbon (Table / Column tools) ·
 *           stepsPanel + stepForms (applied steps) · aiPanel (the Analysis Sandbox) ·
 *           agentAccess (approval popups) · stepsStrip · exportDialog ·
 *           erdView (the ERD tab) · queryTab (the "+" tab: a new table from a query) ·
 *           openMenu (the Open dialog: tables in running Python sessions) ·
 *           valueViewer · bottomBar · theme
 * ROUTING:  [TITLE]            -> read-only, the dataset name and version (centered, large)
 *           [SETTINGS]         the Application row (above the ribbon) -> settingsWindow.openSettings()
 *                              (theme, header profiles, what the agent may see)
 *           [RIBBON]           Table / Column tools -> ribbon.ts (Profile, Key Finder, Export in Table)
 *           [TRANSFORMATIONS]  -> read-only placement: the panel is always shown (it can still pop out)
 *           [ZOOM]   on the ribbon's Table row; Ctrl+= / Ctrl+- / Ctrl+0 here -> stepZoom() / setGridZoom(1)
 *           [PREVIEW BANNER] -> state.setPreview(null)
 *           [PASTE]  Ctrl+V of tab-separated text -> pasteAsDataset()
 *           [COLUMN PROFILE] the ribbon's Column row -> profileView.openColumnProfile(column)  (a popup)
 *           [LIVE NOTICES] dataset_updated / grid_updated / cards_updated -> onLiveNotice(); approvals -> handleAgentNotice()
 *
 * ?panel=steps opens only the steps panel (the pop-out window), and ?panel=keys only the Key
 * Finder; both follow the same server state through the WebSocket, so edits show in every window.
 */
import { mountContextMenus } from "./cellMenu";
import { api, connect, gridId, onNotice, openedWith, requireSession, token, type Notice } from "./api";
import { mountSnapshots } from "./snapshot";
import { handleAgentNotice, loadApprovals } from "./agentAccess";
import { handleNotice, mountAiPanel, refreshPanel } from "./aiPanel";
import { mountErd } from "./erdView";
import { mountBottomBar, setLive } from "./bottomBar";
import { $, button, clear, closeDialogs, h, toast } from "./dom";
import { appMark, HOME_URL, mountNav, setTitle, startNav } from "./nav";
import { mountNavRail } from "./rail";
import { renderKeyFinder } from "./keyFinder";
import { mountBeta } from "./betaNotes";
import { loadPanels } from "./panels";
import { restoreCompare, showCompare } from "./compare";
import { mountGridCommands } from "./gridCommands";
import { openCompareDialog } from "./compareDialog";
// Settings and Connections are layers the rail opens (open=settings, open=connections): their modules register
// them, so they load here even with no button of theirs on the page.
import "./settingsWindow";
import "./connectionsWindow";
import { activateGrid, activeContext, addGrid, contextOf, contextsOf, drawTitle, dropGrid, gridList, mountPanes, onSplitCreated, openGrids, renameContexts, resyncGrids, showAgentView, showErdView, showGridView, showPlace, showStartView, viewingStart } from "./panes";
import { mountStart } from "./startView";
import { mountRibbon, zoomControl } from "./ribbon";
import { openColumnProfile } from "./profileView";
import { mountFileDrop } from "./openFile";
import { mountOpenMenu } from "./openMenu";
import { mountQueryTab } from "./queryTab";
import { loadRelationships } from "./relationships";
import { PageState, activate, state } from "./state";
import { pastedToast } from "./renameTable";
import { mountStepsPanel } from "./stepsPanel";
import { mountStepsStrip } from "./stepsStrip";
import { setGridZoom, stepZoom } from "./theme";

const panelParam = new URLSearchParams(location.search).get("panel");
const popout = panelParam === "steps";
const keysWindow = panelParam === "keys";

/** The dataset name is the page's title: centered and large, in its own row. */
function title(): void {
  const info = state.info!;
  // The version shows once there has been a second push: "v1" says nothing to act on.
  clear($("#grid-title"), info.dataset, info.version > 1 ? h("span", { class: "version", title: `Version ${info.version} of ${info.dataset}` }, `v${info.version}`) : null);
}

const pasting = new Set<string>();

async function pasteAsDataset(text: string): Promise<void> {
  // Named for the local time, and never an open dataset's name: a paste stores under its name,
  // so two pastes within one second replaced the first (and the time read in UTC).
  const now = new Date();
  const stamp = [now.getHours(), now.getMinutes(), now.getSeconds()].map((n) => String(n).padStart(2, "0")).join("");
  let name = `pasted_${stamp}`;
  try {
    const taken = new Set((await api<{ datasets: { name: string }[] }>("/datasets")).datasets.map((d) => d.name));
    for (let n = 2; taken.has(name) || pasting.has(name); n += 1) name = `pasted_${stamp}_${n}`;
    pasting.add(name); // a second paste before this one lands picks another name
    const response = await fetch(`/datasets/${name}/paste`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: text });
    if (!response.ok) throw new Error(await response.text());
    pastedToast(name);
  } catch (e) {
    toast((e as Error).message, "error");
  }
}

/** Route a live notice to the grid(s) it is about, active or not. */
function onLiveNotice(notice: Notice): void {
  if (notice.type === "grid_shown" && notice.grid && !popout && !keysWindow) {
    // A push or an agent opened a grid: it arrives as a tab and comes to the front (over the Start view).
    addGrid(notice.grid, notice.dataset ?? notice.grid);
    if (viewingStart()) showGridView("replace");
    void activateGrid(notice.grid);
  }
  if (notice.type === "grid_closed" && notice.grid) dropGrid(notice.grid);
  if (notice.type === "dataset_renamed" && notice.dataset && notice.to) renameContexts(notice.dataset, notice.to);
  if (notice.type === "dataset_closed" && notice.dataset) {
    for (const ctx of contextsOf(notice.dataset)) dropGrid(ctx.id);
    if (popout || keysWindow) {
      toast(`Dataset ${notice.dataset} was closed.`, "error");
      setLive(false);
    }
  }
  if (notice.type === "dataset_updated" && notice.dataset) {
    for (const ctx of contextsOf(notice.dataset)) {
      if (!ctx.state.info) continue;
      void ctx.state.load().then(() => {
        ctx.view?.refresh();
        if (ctx.state === state) {
          toast(`${notice.dataset} updated to version ${notice.version}.`);
          refreshPanel();
        }
      }).catch(() => undefined); // closed meanwhile: its grid_closed notice drops the tab
    }
  }
  if (notice.type === "grid_updated" && notice.grid) {
    // Steps changed in another window, by a chart click, or by the agent.
    const ctx = contextOf(notice.grid);
    if (ctx?.state.info) {
      // The new generation first: load() redraws the panels at once, and the step counts they
      // ask for with the old one were refused (409), so the row counts went missing.
      ctx.state.gen = Math.max(ctx.state.gen, (notice as { gen?: number }).gen ?? 0);
      void ctx.state.load().then(() => {
        ctx.view?.refresh();
        if (notice.by === "agent" && ctx.state === state) toast("The agent changed this grid's view.");
      }).catch(() => undefined);
    }
  }
  if (notice.type === "relationships_updated") void loadRelationships();
  // A compare started for this page to show (the Key Finder's window, the agent).
  if (notice.type === "compare_shown" && notice.compare && !popout && !keysWindow) void showCompare(notice.compare);
  handleNotice(notice);
  handleAgentNotice(notice);
}

/** The pop-out windows (?panel=steps, ?panel=keys) show one grid: the one in their address. */
async function startSingle(): Promise<void> {
  const single = new PageState(gridId);
  activate(single);
  const info = await single.load();
  const stepsHost = $("#steps-panel");
  if (popout) mountStepsPanel(stepsHost);
  connect((live, again) => {
    setLive(live);
    if (again) void single.load().catch(() => undefined); // changes made while the socket was down
  });
  onNotice(onLiveNotice);
  mountSnapshots();
  mountContextMenus();
  if (keysWindow) {
    // The Key Finder window: the finder alone, full width, titled for this grid; the mark goes home.
    setTitle("Key Finder", info.dataset);
    clear($("#grid-title"), `Possible Join Keys for ${info.dataset}`);
    $(".titlebar").prepend(appMark());
    for (const selector of [".tabbar", ".ribbon", ".workspace", ".statusbar"]) $(selector).remove();
    const host = h("main", { class: "keys-window" });
    document.body.append(host);
    await renderKeyFinder(host);
    return;
  }
  setTitle("Table Transformations", info.dataset);
  $(".tabbar").remove();
  $(".titlebar").remove();
  // The steps window's top row: the mark (home), then whose steps these are.
  document.body.prepend(h("header", { class: "window-top" }, appMark(), h("strong", {}, info.dataset)));
  // The steps window shows only the steps: no ribbon of its own (the grid's page has it).
  $(".app-row").remove();
  $(".ribbon").remove();
  $(".statusbar").remove();
  document.body.append(stepsHost);
  $(".workspace").remove();
  single.emit("info");
}

async function start(): Promise<void> {
  if (!(await requireSession())) return; // no token and no good cookie: how to open the app
  // Beta mode (the beta log and Leave a note…): on every window of this page; nothing while it is off.
  mountBeta("grid", {
    window: popout ? "steps" : keysWindow ? "keys" : "main",
    tabs: () => [`front:${document.querySelector<HTMLElement>(".workspace")?.dataset.view ?? "grid"}`, ...Array.from(document.querySelectorAll(".tabs-row [role=tab]"), () => "tab")],
  });
  if (popout || keysWindow) {
    mountNav(popout ? "steps" : "keys");
    mountNavRail(popout ? "steps" : "keys"); // the areas: Grids brings the home window forward
    await startSingle();
    return;
  }
  // The address it was opened with (a reload, a bookmark): shown once the tables are back.
  const opened = new URL(location.href);
  // The home page: its tabs and dialogs in the address; Home (the mark, Alt+Home) is the Start view.
  mountNav("home", {
    show: (url) => void showPlace(url),
    home: () => {
      closeDialogs();
      showStartView("push");
    },
  });
  mountNavRail("home"); // the areas down the left
  $(".tabbar").prepend(appMark());
  const workspace = $(".workspace");
  // The grid has the whole page (plan decision 13): no Table Transformations panel and no SQL box here.
  // The ribbon adds steps; the strip under the title shows them, and opens the panel in a tab of its
  // own; the steps as code are the table's read-only cell in the Workbench.
  $("#steps-panel").remove();
  const strip = h("div", { class: "steps-strip" });
  $(".titlebar").append(strip);
  mountStepsStrip(strip);
  mountBottomBar($(".statusbar"));
  void loadPanels(); // a panel turned off in Settings is gone (grid.css, by <body>'s class)
  mountAiPanel(workspace, $("#ai-panel"), $(".splitter"));
  mountErd($("#erd-view"));
  // Before the panes: a built table's pane gets its query tray as the pane is made.
  mountQueryTab($("#query-view"));
  // Panels: each redraws when the active grid changes or the active grid's info does.
  state.on("info", () => {
    if (!state.info) return;
    title();
    // The browser tab names the place in front (the table, Sandbox, Diagram); the tab bar names them all.
    drawTitle();
  });
  // The Application row: app-wide commands, with their words, above the ribbon's Table row.
  clear(
    $(".app-row"),
    h(
      "div",
      { class: "ribbon-group", role: "toolbar", "aria-label": "Application tools" },
      h("div", { class: "ribbon-caption" }, h("strong", {}, "Application")),
      h("div", { class: "ribbon-tools" }, zoomControl()), // Settings, Connections, Blades: the rail's; the tour: Start's
    ),
  );
  // A project as one .sab file (startView.ts): the Start view, the project's group first in the Application
  // row, and the strip of tables that need a fix under the tabs.
  const projectGroup = h("div", { class: "ribbon-group project-group", role: "toolbar", "aria-label": "Project", hidden: true });
  $(".app-row").prepend(projectGroup);
  const fixes = h("div", { class: "project-fixes", "aria-label": "Tables to fix", hidden: true });
  $(".tabbar").after(fixes);
  mountStart($("#start-view"), projectGroup, fixes, {
    layout: () => ({
      order: gridList().map((g) => contextOf(g.id)?.dataset ?? g.label),
      front: activeContext()?.dataset ?? null,
      view: document.querySelector<HTMLElement>(".workspace")?.dataset.view ?? "grid",
    }),
    restore: (saved) => {
      if (saved.view === "agent") showAgentView("replace");
      else if (saved.view === "erd") showErdView("replace");
      else {
        const front = gridList().find((g) => contextOf(g.id)?.dataset === saved.front);
        if (front) {
          showGridView("replace");
          void activateGrid(front.id, "replace");
        }
      }
    },
    // The Grids landing's Paste: the clipboard's table, as Ctrl+V (the browser may ask first).
    paste: () =>
      void navigator.clipboard.readText().then(
        (text) => (text.includes("\t") && text.includes("\n") ? pasteAsDataset(text) : toast("Copy a table first, then press Ctrl+V.", "error")),
        () => toast("Press Ctrl+V to paste a table.", "error"),
      ),
  });
  mountRibbon($(".ribbon"), openColumnProfile);
  mountPanes($(".tabs-row"), $(".panes"), () => refreshPanel());
  // A new split opens the key picker with the Key Finder already run; Close keeps it key-less.
  onSplitCreated((left, right) => openCompareDialog(left, right));
  onNotice(onLiveNotice);
  mountSnapshots();
  mountContextMenus();
  mountOpenMenu();
  mountFileDrop(); // a file dropped anywhere opens as a grid
  mountGridCommands(); // Ctrl+Shift+P: every action of this page, by name
  // This page shows every grid as a tab, so a push while it is open adds a tab, not a window.
  // Each (re)connect fetches the agent's requests already waiting: one made before the socket was
  // open never reached this page as a notice.
  connect((live, again) => {
    setLive(live);
    if (live) void loadApprovals();
    if (again) void resyncGrids().catch(() => undefined);
  }, { workspace: "1" });
  await openGrids(gridId || openedWith.get("grid"));
  // A compare this page was showing before a reload comes back with its split.
  await restoreCompare().catch(() => undefined);
  if (!activeContext()) toolbarEmpty();
  // The view the address named (the Sandbox, the Diagram, a table), then the dialog over it.
  await showPlace(opened);
  startNav(opened);

  document.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    if (e.key === "=" || e.key === "+") { e.preventDefault(); stepZoom(1); }
    else if (e.key === "-") { e.preventDefault(); stepZoom(-1); }
    else if (e.key === "0") { e.preventDefault(); setGridZoom(1); }
  });
  document.addEventListener("paste", (e) => {
    // With nothing focused the target is the document itself, which has no closest().
    const target = e.target instanceof Element ? e.target : null;
    if (target?.closest("input, textarea, .monaco-editor")) return;
    const text = e.clipboardData?.getData("text/plain") ?? "";
    if (text.includes("\t") && text.includes("\n")) {
      e.preventDefault();
      void pasteAsDataset(text);
    }
  });
  void loadRelationships();
}

/** No grid open yet: a quiet title until the first push arrives as a tab. */
function toolbarEmpty(): void {
  clear($("#grid-title"), "No table yet");
  drawTitle();
}

// A failed action nothing else caught (a button whose request the server refused, a tab closed
// mid-request): say so in a toast instead of failing silently with only a console error.
window.addEventListener("unhandledrejection", (event: PromiseRejectionEvent) => {
  const reason = event.reason as { name?: string; message?: string } | null | undefined;
  event.preventDefault();
  if (reason?.name === "AbortError") return; // cancelled on purpose
  console.warn(reason);
  toast(reason?.message || String(reason), "error");
});

start().catch((e: unknown) => {
  // Never a dead end: the words, and the way home.
  document.body.append(
    h("p", { class: "status-error", style: { padding: "16px" } }, `Could not open this grid: ${(e as Error).message} `, h("a", { href: HOME_URL }, "Home")),
  );
});


