/**
 * canvasLaunch.ts: Launch, build history and the Performance Analyzer on a Streamlit app's canvas (the owner,
 * 2026-11-19: "build a way to launch the app canvas in a new tab ... along with a build version history every
 * time we launch, think Visual Studio"; "a separate window that can be launched from the app canvas").
 *
 *   [LAUNCH]    Launch (Ctrl+F5: without the analyzer) builds the app (builds/<app>/<n>/ in its project) and runs
 *               it in a window of its own, titled "<app> · build <n>" (the desktop app's window; a browser tab);
 *               F5 launches with the analyzer attached. Launch again replaces the running one; Stop ends it
 *   [ANALYZER]  the Performance Analyzer's window (/streamlit/perf?app=): it records only while it is open
 *   [BUILDS]    Visual Studio's history: newest first, what changed in words, the result; tick two and Compare
 *               (Monaco's diff editor, file by file); Open one read-only; Relaunch; Restore its code into the
 *               app (each cell's change made in its document like typing: Undo takes it back)
 *
 * ROUTING: …/launch, …/builds, …/builds/compare, …/builds/{n}, …/builds/{n}/launch, …/builds/{n}/restore
 * (routes_launch.py; the agent's app_launch, builds_list, builds_compare, build_relaunch, build_restore).
 */
import { api } from "./api";
import { button, clear, h, openDialog } from "./dom";
import { errorHere } from "./errorNote";
import { busyButton, loadingBlock } from "./loading";
import { effectiveTheme } from "./theme";

export interface LaunchState {
  app: string;
  running: boolean;
  build?: number;
  title?: string;
  address?: string;
  analyzer?: boolean;
  changed?: string[];
}

interface Build {
  number: number;
  time: string;
  changed: string[];
  result: string;
  first_load_ms: number | null;
  sessions: string[];
  error?: string;
}

interface Compared {
  file: string;
  status: "changed" | "added" | "removed" | "same";
  before: string | null;
  after: string | null;
  added: number;
  removed: number;
}

export interface LaunchHost {
  app: () => string | null;
  /** The app is saved (its builds go in its project's folder). */
  saved: () => boolean;
}

const enc = encodeURIComponent;
const base = (app: string): string => `/streamlit/apps/${enc(app)}`;

let editors: Promise<typeof import("./lazy/codeEditor")> | null = null;
function loadEditors(): Promise<typeof import("./lazy/codeEditor")> {
  if (!document.querySelector('link[href="/static/build/lazy/codeEditor.css"]')) document.head.append(h("link", { rel: "stylesheet", href: "/static/build/lazy/codeEditor.css" }));
  return (editors ??= import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>);
}

/** The launched app's window (the desktop app opens it as a window of its own; a browser, a tab). */
function showLaunched(state: LaunchState): void {
  if (state.address) window.open(state.address, `sab-launch-${state.app}`);
}

/** The Performance Analyzer's window for an app. */
export function openAnalyzer(app: string): void {
  window.open(`/streamlit/perf?app=${enc(app)}`, `sab-perf-${app}`);
}

/** The canvas's Launch, Stop, Analyzer and Builds buttons, drawn into the canvas's bar. */
export function launchControls(host: LaunchHost): { element: HTMLElement; refresh: () => void; launch: (analyzer: boolean) => Promise<void> } {
  const element = h("span", { class: "cv-launch", role: "group", "aria-label": "Launch" });
  let state: LaunchState | null = null;

  async function launch(analyzer: boolean, from?: HTMLElement): Promise<void> {
    const app = host.app();
    if (!app) return;
    try {
      const work = api<LaunchState>(`${base(app)}/launch`, "POST", analyzer ? { analyzer: true } : {});
      state = from instanceof HTMLButtonElement ? await busyButton(from, work, "Building…") : await work;
      showLaunched(state);
      if (analyzer) openAnalyzer(app);
      draw();
    } catch (e) {
      errorHere(e, {}, from ?? element);
    }
  }

  function draw(): void {
    const app = host.app();
    const go = button("Launch", (e) => void launch(false, e.currentTarget as HTMLElement), { icon: "play", class: "cv-launch-go", title: "Launch: build the app and run it in its own window (Ctrl+F5; F5: with the Performance Analyzer)" });
    go.disabled = !app || !host.saved();
    if (!host.saved()) go.title = "Save the app first: its builds go in its project's folder";
    const stop = button("Stop", (e) => {
      if (!app) return;
      void busyButton(e.currentTarget as HTMLButtonElement, api<LaunchState>(`${base(app)}/launch`, "DELETE"), "Stopping…")
        .then(() => {
          state = null;
          draw();
        })
        .catch((error: unknown) => errorHere(error, {}, element));
    }, { icon: "stop", iconOnly: true, class: "ghost cv-launch-stop", title: state?.running ? `Stop build ${state.build}` : "Stop" });
    stop.hidden = !state?.running;
    const analyzer = button("Performance Analyzer", () => app && openAnalyzer(app), { icon: "bolt", iconOnly: true, class: "ghost cv-analyzer", title: "Performance Analyzer: its own window, attached to the launched app" });
    analyzer.disabled = !state?.running;
    const history = button("Builds", () => app && void openBuilds(app), { icon: "history", iconOnly: true, class: "ghost cv-builds", title: "Builds: every launch, what changed, Compare, Relaunch, Restore" });
    history.disabled = !app || !host.saved();
    clear(element, go, stop, analyzer, history);
  }

  let asked = 0;
  async function refresh(): Promise<void> {
    // The canvas draws its bar often: the launch is asked at most every two seconds.
    if (Date.now() - asked < 2000) return draw();
    asked = Date.now();
    const app = host.app();
    if (app) {
      try {
        state = await api<LaunchState>(`${base(app)}/launch`);
      } catch {
        state = null;
      }
    }
    draw();
  }

  draw();
  void refresh();
  return { element, refresh: () => void refresh(), launch: (analyzer) => launch(analyzer) };
}

// ===== Builds: Visual Studio's history =====

const when = (iso: string): string => {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : at.toLocaleString();
};

export async function openBuilds(app: string): Promise<void> {
  const { body, foot } = openDialog("Builds", true);
  body.classList.add("bd");
  const list = h("div", { class: "bd-list", role: "list" });
  const detail = h("div", { class: "bd-detail" });
  body.append(list, detail);
  const ticked = new Set<number>();
  const compare = button("Compare", () => void showCompare(), { icon: "columns", class: "primary bd-compare", title: "Compare the two ticked builds, file by file" });
  foot.append(compare);
  let builds: Build[] = [];

  const drawList = (): void => {
    compare.disabled = ticked.size !== 2;
    clear(
      list,
      ...(builds.length
        ? builds.map((b) => {
            const tick = h("input", { type: "checkbox", "aria-label": `Build ${b.number}`, checked: ticked.has(b.number) }) as HTMLInputElement;
            tick.addEventListener("change", () => {
              if (tick.checked) ticked.add(b.number);
              else ticked.delete(b.number);
              while (ticked.size > 2) ticked.delete([...ticked][0]!);
              drawList();
            });
            const row = h(
              "div",
              { class: `bd-row bd-${b.result}`, role: "listitem", dataset: { build: String(b.number) } },
              tick,
              h("div", { class: "bd-head" }, h("strong", {}, `Build ${b.number}`), h("span", { class: "hint" }, when(b.time)), h("span", { class: `bd-result bd-result-${b.result}` }, b.result === "started" ? (b.first_load_ms !== null ? `started · ${b.first_load_ms} ms` : "started") : b.result)),
              h("ul", { class: "bd-changed" }, ...b.changed.map((c) => h("li", {}, c))),
              b.error ? h("div", { class: "bd-error", role: "alert" }, b.error) : null,
              h(
                "div",
                { class: "bd-actions" },
                button("Open", () => void showBuild(b.number), { icon: "eye", class: "small bd-open" }),
                button("Relaunch", (e) => void relaunch(b.number, e.currentTarget as HTMLButtonElement), { icon: "play", class: "small bd-relaunch" }),
                button("Restore", (e) => void restore(b.number, e.currentTarget as HTMLButtonElement), { icon: "undo", class: "small bd-restore", title: "Its cells' code and layout back into the app (Undo takes it back)" }),
                ...b.sessions.map((s) => button(s.replace(/^perf-|\.json$/g, ""), () => window.open(`/streamlit/perf?app=${enc(app)}&build=${b.number}&file=${enc(s)}`, `sab-perf-${app}-${s}`), { icon: "bolt", class: "small ghost bd-session", title: "A saved analyzer session" })),
              ),
            );
            return row;
          })
        : [h("p", { class: "hint app-empty" }, "No build yet: Launch makes the first")]),
    );
  };

  const relaunch = async (number: number, from: HTMLButtonElement): Promise<void> => {
    try {
      const state = await busyButton(from, api<LaunchState>(`${base(app)}/builds/${number}/launch`, "POST"), "Starting…");
      showLaunched(state);
    } catch (e) {
      errorHere(e, {}, from);
    }
  };

  const restore = async (number: number, from: HTMLButtonElement): Promise<void> => {
    try {
      await busyButton(from, api(`${base(app)}/builds/${number}/restore`, "POST"), "Restoring…");
    } catch (e) {
      errorHere(e, {}, from);
    }
  };

  /** The diff of a list of files: the files beside, Monaco's diff editor for the one picked. */
  const drawFiles = async (title: string, files: Compared[]): Promise<void> => {
    const host = h("div", { class: "bd-diff" });
    const names = h("ul", { class: "bd-files", role: "listbox", "aria-label": "Files" });
    clear(detail, h("div", { class: "bd-detail-head" }, h("strong", {}, title)), h("div", { class: "bd-split" }, names, host));
    const lib = await loadEditors();
    const viewer = lib.createDiffViewer(host, effectiveTheme());
    const pick = (f: Compared, item: HTMLElement): void => {
      for (const other of names.querySelectorAll(".selected")) other.classList.remove("selected");
      item.classList.add("selected");
      viewer.show(f.before ?? "", f.after ?? "", f.file);
    };
    const shown = files.filter((f) => f.status !== "same");
    for (const f of shown.length ? shown : files) {
      const item = h("li", { class: `bd-file bd-${f.status}`, role: "option", tabindex: 0, dataset: { file: f.file } }, h("span", { class: "mono" }, f.file), h("span", { class: "hint" }, f.status === "changed" ? `+${f.added} −${f.removed}` : f.status));
      item.addEventListener("click", () => pick(f, item));
      names.append(item);
    }
    const first = names.querySelector<HTMLElement>(".bd-file");
    const firstFile = (shown.length ? shown : files)[0];
    if (first && firstFile) pick(firstFile, first);
  };

  const showCompare = async (): Promise<void> => {
    const [a, b] = [...ticked].sort((x, y) => x - y);
    try {
      const got = await api<{ files: Compared[] }>(`${base(app)}/builds/compare?a=${a}&b=${b}`);
      await drawFiles(`Build ${a} → build ${b}`, got.files);
    } catch (e) {
      errorHere(e, {}, compare);
    }
  };

  const showBuild = async (number: number): Promise<void> => {
    try {
      const got = await api<{ files: Record<string, string> }>(`${base(app)}/builds/${number}`);
      const files: Compared[] = Object.entries(got.files).map(([file, text]) => ({ file, status: "same", before: text, after: text, added: 0, removed: 0 }));
      await drawFiles(`Build ${number} (read-only)`, files);
    } catch (e) {
      errorHere(e, {}, list);
    }
  };

  list.append(loadingBlock("Reading the builds…"));
  try {
    builds = (await api<{ builds: Build[] }>(`${base(app)}/builds`)).builds;
    drawList();
  } catch (e) {
    clear(list);
    errorHere(e, {}, list);
  }
}
