/**
 * explorerPage.ts: the Data Explorer popped out of the Workbench into a window of its own (the owner,
 * 2026-11-17: "that Data Explorer should have the option to pop it out into another tab just like the
 * structure explorer"). [COMPOSITION]
 *
 *   /workbench?panel=explorer   titled "Data Explorer", with the rail (as every window); the same search
 *                               (dataExplorer.ts), its search, filters and scroll carried in by the
 *                               handoff that opened it (#take=<id>), else this window's own last ones
 *   Insert                      into the Workbench window's focused cell (the button's title names the
 *                               document: its workbench_window command explorer.target); a result dragged
 *                               from here drops into a cell there (the browser carries the drag)
 *   Move back                   the search handed to the main Workbench window (a handoff to "main"),
 *                               its pane opens with it, and this window closes; the main window can ask
 *                               for it too (the agent's explorer.moveBack: a message on EXPLORER_BROADCAST)
 *
 * ROUTING: POST /workbench/handoffs/{id}/take  POST /workbench/handoffs {to: "main"}
 *          POST /workbench/window {command: "explorer.insert" | "explorer.target"}
 */
import { api, ApiError, connect, errorText, openedWith, requireSession } from "./api";
import { watchTheme } from "./catalogRail";
import { watchConnectionColours } from "./connectionColours";
import { EMPTY_STATE, EXPLORER_BROADCAST, type ExplorerState, mountExplorer } from "./dataExplorer";
import { button, h, toast } from "./dom";
import { mountNav, setTitle } from "./nav";
import { mountNavRail } from "./rail";
import { openVariables } from "./variablesPage";

const KEPT = "explorer-window-state";

watchTheme();
watchConnectionColours();
mountNav("explorer");
mountNavRail("explorer");
setTitle("Data Explorer");

let target = "the Workbench's selected cell";

/** The Workbench window's focused cell, in words, for Insert's title. */
async function readTarget(): Promise<void> {
  try {
    const got = await api<{ result: { document: string | null; cell: number | null } }>("/workbench/window", "POST", { command: "explorer.target", args: {} });
    const { document: doc, cell } = got.result ?? { document: null, cell: null };
    target = doc ? (cell ? `cell ${cell} of ${doc}` : doc) : "the Workbench (no notebook or script is in front)";
  } catch {
    target = "the Workbench (it is not open)";
  }
}

const explorer = mountExplorer({
  insert: async (r) => {
    const got = await api<{ result: { document: string; cell: number | null } }>("/workbench/window", "POST", { command: "explorer.insert", args: { insert: r.insert, name: r.name } });
    return got.result.cell ? `cell ${got.result.cell} of ${got.result.document}` : got.result.document;
  },
  target: () => target,
  showGrid: (grid) => {
    void api("/workbench/window", "POST", { command: "explorer.showGrid", args: { grid } }).catch(() => window.open(`/g/${encodeURIComponent(grid)}`, "_blank"));
  },
  openVariable: () => openVariables(),
  changed: (state) => {
    try {
      sessionStorage.setItem(KEPT, JSON.stringify(state));
    } catch {
      /* storage blocked: a reload starts empty */
    }
  },
});

const back = button("Move back", () => void moveBack(), { icon: "back", class: "line", title: "Move back to the Workbench's pane" });
document.getElementById("ex-window")!.append(
  h("header", { class: "ex-window-head" }, h("h1", {}, "Data Explorer"), h("span", { class: "spacer" }), back),
  explorer.element,
);

/** The search back to the main Workbench window's pane; this window closes once it has taken it. */
async function moveBack(): Promise<void> {
  try {
    const { id } = await api<{ id: string }>("/workbench/handoffs", "POST", { document: { kind: "explorer", ...explorer.state() }, to: "main" });
    const until = Date.now() + 8000;
    while (Date.now() < until) {
      await new Promise((done) => setTimeout(done, 200));
      const state = await api<{ taken: boolean }>(`/workbench/handoffs/${id}`).catch(() => ({ taken: false }));
      if (state.taken) {
        window.close();
        return;
      }
    }
    const cancelled = await api<{ cancelled: boolean }>(`/workbench/handoffs/${id}`, "DELETE").catch(() => ({ cancelled: true }));
    if (cancelled.cancelled) toast("The main Workbench window is not open: the Data Explorer stays here.", "error");
    else window.close();
  } catch (e) {
    toast(errorText(e), "error");
  }
}

// The main window's asks: move back (the agent's explorer.moveBack), and whether this window is here.
const channel = "BroadcastChannel" in window ? new BroadcastChannel(EXPLORER_BROADCAST) : null;
channel?.addEventListener("message", (e: MessageEvent) => {
  const said = e.data as { type?: string } | null;
  if (said?.type === "back") void moveBack();
  if (said?.type === "here?") channel.postMessage({ type: "here", state: explorer.state() });
  if (said?.type === "search" && (said as { state?: ExplorerState }).state) explorer.setState((said as { state: ExplorerState }).state);
});
window.addEventListener("beforeunload", () => channel?.postMessage({ type: "gone" }));
window.addEventListener("focus", () => void readTarget());

async function start(): Promise<void> {
  if (!(await requireSession())) return;
  const take = openedWith.get("take");
  let state: ExplorerState | null = null;
  if (take) {
    try {
      const got = await api<{ document: ExplorerState & { kind: string } }>(`/workbench/handoffs/${encodeURIComponent(take)}/take`, "POST", { window: "explorer" });
      state = { ...EMPTY_STATE, ...got.document };
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) toast(errorText(e), "error");
    }
  }
  if (!state) {
    try {
      state = { ...EMPTY_STATE, ...(JSON.parse(sessionStorage.getItem(KEPT) ?? "null") as ExplorerState | null) };
    } catch {
      state = null;
    }
  }
  if (state) explorer.setState(state);
  channel?.postMessage({ type: "here", state: explorer.state() });
  connect(() => undefined, { explorer: "1" });
  explorer.focus();
  void readTarget();
}
void start();
