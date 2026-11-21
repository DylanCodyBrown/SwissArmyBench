/**
 * perfPage.ts: the Performance Analyzer, a window of its own (the owner, 2026-11-19: "a separate window that can
 * be launched from the app canvas that can monitor apps as they run from our platform. We can see calls,
 * triggers, network activity and what is actually traveling through the web socket"; carried over to the widget
 * Canvas, 2026-11-21: each block is a widget instance, named "<widget> (<id>)").
 *
 *   [ATTACH]    opened with ?canvas=<canvas id>: it attaches to that canvas's launch and records while open
 *               (Pause and Record; closing the window detaches). ?build=&file=: a saved session, read-only
 *   [TIMELINE]  Chrome's Performance panel: each rerun a bar (its trigger: a widget, a page switch, the first
 *               load), its time, and under it each widget instance's time
 *   [CALLS]     each query (SQL, DAX), outside request and file read: its block, time, rows, its rerun
 *   [CACHE]     each st.cache_data / st.cache_resource function: calls, hits, misses, what the misses cost
 *   [SOCKET]    the web socket: messages per rerun, by element (a dataframe, a chart, markdown), the biggest
 *               first; kinds and sizes only, never the content
 *   [HINTS]     in plain words: what to change, and where
 *
 * ROUTING: POST/GET/DELETE /streamlit/canvases/{canvas}/perf, POST …/perf/save, GET …/builds/{n}/perf/{file}
 * (routes_launch.py).
 */
import { api, requireSession } from "./api";
import { button, clear, h } from "./dom";
import { errorHere } from "./errorNote";
import { loadingBlock } from "./loading";
import { watchTheme } from "./catalogRail";

interface BlockTime {
  block: string;
  title: string;
  ms: number;
}

interface SocketRerun {
  trigger: string;
  messages: number;
  size: number;
  elements: Record<string, { count: number; size: number }>;
  biggest: { direction: string; kind: string; size: number; element?: string; path?: string }[];
}

interface Rerun {
  index: number;
  trigger: string;
  page: string;
  ms: number;
  blocks: BlockTime[];
  calls: Record<string, unknown>[];
  socket: SocketRerun | null;
}

interface Session {
  canvas: string;
  build: number;
  recording: boolean;
  reruns: Rerun[];
  calls?: Record<string, unknown>[];
  caches?: { name: string; kind: string; calls: number; hits: number; misses: number; miss_ms: number }[];
  socket?: { messages: number; size: number; elements: Record<string, { count: number; size: number }>; biggest: SocketRerun["biggest"]; reruns: SocketRerun[] };
  hints: { rule: string; words: string; block?: string }[];
}

const params = new URLSearchParams(location.search);
const app = params.get("canvas") ?? params.get("app") ?? "";
const savedBuild = params.get("build");
const savedFile = params.get("file");
const saved = !!(savedBuild && savedFile);
const root = document.getElementById("perf")!;
const path = `/streamlit/canvases/${encodeURIComponent(app)}/perf`;
let tab: "timeline" | "calls" | "cache" | "socket" | "hints" = "timeline";
let session: Session | null = null;
let picked: number | null = null;
let timer: number | null = null;

const size = (n: number): string => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : n >= 1e3 ? `${(n / 1e3).toFixed(1)} KB` : `${n} B`);
const ms = (n: number): string => (n >= 1000 ? `${(n / 1000).toFixed(2)} s` : `${Math.round(n)} ms`);

function table(head: string[], rows: (string | number)[][], label: string): HTMLElement {
  if (!rows.length) return h("p", { class: "hint app-empty" }, `No ${label} yet`);
  return h(
    "table",
    { class: "app-state pf-table", "aria-label": label },
    h("thead", {}, h("tr", {}, ...head.map((c) => h("th", {}, c)))),
    h("tbody", {}, ...rows.map((r) => h("tr", {}, ...r.map((c) => h("td", { class: typeof c === "number" ? "num" : "" }, String(c)))))),
  );
}

function timeline(s: Session): HTMLElement {
  if (!s.reruns.length) return h("p", { class: "hint app-empty" }, s.recording ? "Use the app: each rerun shows here" : "Paused");
  const longest = Math.max(...s.reruns.map((r) => r.ms), 1);
  const bars = s.reruns.map((r) => {
    const bar = h(
      "button",
      { type: "button", class: `pf-rerun${picked === r.index ? " selected" : ""}`, dataset: { rerun: String(r.index), trigger: r.trigger }, title: `${r.trigger}: ${ms(r.ms)}` },
      h("span", { class: "pf-trigger" }, r.trigger),
      h("span", { class: "pf-bar", style: { width: `${Math.max(2, (r.ms / longest) * 100)}%` } }),
      h("span", { class: "pf-ms" }, ms(r.ms)),
      r.socket ? h("span", { class: "hint pf-sent" }, size(r.socket.size)) : null,
    );
    bar.addEventListener("click", () => {
      picked = r.index;
      draw();
    });
    return bar;
  });
  const shown = s.reruns.find((r) => r.index === picked) ?? s.reruns[s.reruns.length - 1]!;
  const slowest = Math.max(...shown.blocks.map((b) => b.ms), 1);
  return h(
    "div",
    { class: "pf-timeline" },
    h("div", { class: "pf-reruns", role: "list", "aria-label": "Reruns" }, ...bars),
    h(
      "section",
      { class: "pf-blocks", "aria-label": `Rerun ${shown.index}` },
      h("h3", { class: "app-heading" }, `Rerun ${shown.index} · ${shown.trigger} · ${ms(shown.ms)}`),
      ...shown.blocks.map((b) =>
        h("div", { class: "pf-block", dataset: { block: b.block } }, h("span", { class: "pf-name" }, b.title), h("span", { class: "pf-bar pf-block-bar", style: { width: `${Math.max(1, (b.ms / slowest) * 100)}%` } }), h("span", { class: "pf-ms" }, ms(b.ms))),
      ),
      shown.socket ? h("div", { class: "pf-socket-line hint" }, `${shown.socket.messages} socket messages · ${size(shown.socket.size)}`) : null,
    ),
  );
}

function draw(): void {
  if (!session) return;
  const s = session;
  const tabs = (["timeline", "calls", "cache", "socket", "hints"] as const).map((t) =>
    button(t === "socket" ? "Web socket" : t === "hints" ? `Hints${s.hints.length ? ` (${s.hints.length})` : ""}` : t[0]!.toUpperCase() + t.slice(1), () => {
      tab = t;
      draw();
    }, { class: `pf-tab${tab === t ? " selected" : ""}`, pressed: tab === t }),
  );
  const record = button(s.recording ? "Pause" : "Record", () => void attach(!s.recording), { icon: s.recording ? "stop" : "play", class: "pf-record" });
  const clearButton = button("Clear", () => void attach(true, true), { icon: "trash", class: "ghost pf-clear" });
  const save = button("Save into the build", () => void saveSession(save), { icon: "save", class: "pf-save" });
  for (const b of [record, clearButton, save]) b.hidden = saved;
  let content: HTMLElement;
  if (tab === "timeline") content = timeline(s);
  else if (tab === "calls")
    content = table(
      ["Rerun", "Kind", "Block", "Where", "Rows", "Time"],
      (s.calls ?? []).map((c) => [String(c.rerun ?? ""), String(c.kind ?? ""), String(c.block ?? ""), String(c.connection ?? c.host ?? c.file ?? ""), c.rows === null || c.rows === undefined ? "" : String(c.rows), ms(Number(c.ms ?? 0))]),
      "calls",
    );
  else if (tab === "cache") content = table(["Function", "Kind", "Calls", "Hits", "Misses", "Misses cost"], (s.caches ?? []).map((c) => [c.name, c.kind, c.calls, c.hits, c.misses, ms(c.miss_ms)]), "cached functions");
  else if (tab === "socket")
    content = h(
      "div",
      { class: "pf-socket-view" },
      h("p", { class: "pf-total" }, `${s.socket?.messages ?? 0} messages · ${size(s.socket?.size ?? 0)} to the page`),
      table(["Element", "Messages", "Size"], Object.entries(s.socket?.elements ?? {}).map(([k, v]) => [k, v.count, size(v.size)]), "elements"),
      h("h3", { class: "app-heading" }, "The biggest"),
      table(["Direction", "Kind", "Element", "Path", "Size"], (s.socket?.biggest ?? []).map((m) => [m.direction, m.kind, m.element ?? "", m.path ?? "", size(m.size)]), "messages"),
    );
  else content = s.hints.length ? h("ul", { class: "pf-hints" }, ...s.hints.map((x) => h("li", { class: "pf-hint", dataset: { rule: x.rule } }, x.words))) : h("p", { class: "hint app-empty" }, "No hints");
  clear(
    root,
    h("header", { class: "pf-top" }, h("h1", {}, saved ? `Saved session · build ${s.build}` : `Performance Analyzer · build ${s.build}`), h("span", { class: `pf-state${s.recording ? " on" : ""}`, role: "status" }, saved ? savedFile : s.recording ? "Recording" : "Paused"), h("span", { class: "spacer" }), record, clearButton, save),
    h("nav", { class: "pf-tabs", role: "tablist" }, ...tabs),
    h("div", { class: `pf-body pf-${tab}` }, content),
  );
}

async function read(): Promise<void> {
  try {
    session = await api<Session>(saved ? `/streamlit/canvases/${encodeURIComponent(app)}/builds/${savedBuild}/perf/${encodeURIComponent(savedFile!)}` : path);
    if (saved) session.recording = false;
    draw();
  } catch (e) {
    errorHere(e, {}, root);
  }
}

async function attach(on: boolean, fresh = false): Promise<void> {
  try {
    await api(path, "POST", { on, ...(fresh ? { clear: true } : {}) });
    if (fresh) picked = null;
    await read();
  } catch (e) {
    errorHere(e, {}, root);
  }
}

async function saveSession(from: HTMLElement): Promise<void> {
  try {
    const done = await api<{ file: string }>(`${path}/save`, "POST");
    from.textContent = `Saved: ${done.file}`;
  } catch (e) {
    errorHere(e, {}, from);
  }
}

async function start(): Promise<void> {
  watchTheme();
  if (!(await requireSession())) return;
  document.title = saved ? "Saved session · Performance Analyzer" : "Performance Analyzer";
  root.append(loadingBlock("Attaching to the app…"));
  if (saved) return void read();
  try {
    await api(path, "POST", {});
  } catch (e) {
    clear(root);
    errorHere(e, {}, root);
    return;
  }
  await read();
  timer = window.setInterval(() => void read(), 1000);
  // Closing the window detaches: nothing more is recorded (the owner: only when it is open).
  window.addEventListener("pagehide", () => {
    if (timer !== null) window.clearInterval(timer);
    void fetch(path, { method: "DELETE", credentials: "same-origin", keepalive: true });
  });
}

void start();
