/**
 * canvasBuilds.ts: the Canvas's Builds and the Performance Analyzer's window (the owner, 2026-11-19: "a build
 * version history every time we launch, think Visual Studio"; carried over to the widget Canvas, 2026-11-21).
 *
 *   [BUILDS]    Visual Studio's history: newest first, what changed in words, the result; tick two and Compare
 *               (Monaco's diff editor, file by file), or Compare with now (a build against the canvas as it is);
 *               Open one read-only; Relaunch; Restore its canvas (one change: Undo takes it back; the
 *               library's widgets stay as they are); a saved analyzer session opens read-only
 *   [ANALYZER]  the Performance Analyzer's window (/streamlit/perf?canvas=): it records while it is open
 *
 * ROUTING: /streamlit/canvases/{canvas}/builds, …/builds/compare, …/builds/{n}, …/builds/{n}/launch,
 * …/builds/{n}/restore (routes_launch.py; the agent's canvas_builds: list, files, compare, relaunch, restore).
 */
import { api } from "./api";
import { button, clear, h, openDialog } from "./dom";
import { errorHere } from "./errorNote";
import { busyButton, loadingBlock } from "./loading";
import { effectiveTheme } from "./theme";

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

export interface BuildsHost {
  /** A launch's answer (Relaunch): the page opens its window. */
  launched: (said: { url?: string; title?: string; build?: number }) => void;
  /** A build's canvas restored: the page draws the canvas as the answer has it. */
  restored: (state: unknown) => void;
}

const enc = encodeURIComponent;
const base = (canvas: string): string => `/streamlit/canvases/${enc(canvas)}`;

let editors: Promise<typeof import("./lazy/codeEditor")> | null = null;
function loadEditors(): Promise<typeof import("./lazy/codeEditor")> {
  if (!document.querySelector('link[href="/static/build/lazy/codeEditor.css"]')) document.head.append(h("link", { rel: "stylesheet", href: "/static/build/lazy/codeEditor.css" }));
  return (editors ??= import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>);
}

/** The Performance Analyzer's address for a canvas's launch (a saved session: its build and file). */
export function analyzerAddress(canvas: string, saved?: { build: number; file: string }): string {
  const extra = saved ? `&build=${saved.build}&file=${enc(saved.file)}` : "";
  return `/streamlit/perf?canvas=${enc(canvas)}${extra}`;
}

/** The analyzer's window (opened on the user's click: a window opened later, after a wait, is blocked). */
export function openAnalyzer(canvas: string, saved?: { build: number; file: string }, address = analyzerAddress(canvas, saved)): Window | null {
  return window.open(address, `sab-perf-${canvas}${saved ? `-${saved.file}` : ""}`, "popup,width=1200,height=820");
}

const when = (iso: string): string => {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : at.toLocaleString();
};

/** The Builds dialog. */
export async function openBuilds(canvas: string, host: BuildsHost): Promise<void> {
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
            return h(
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
                button("Compare with now", () => void showNow(b.number), { icon: "columns", class: "small bd-now", title: "This build against the canvas as it is now" }),
                button("Relaunch", (e) => void relaunch(b.number, e.currentTarget as HTMLButtonElement), { icon: "play", class: "small bd-relaunch" }),
                button("Restore", (e) => void restore(b.number, e.currentTarget as HTMLButtonElement), { icon: "undo", class: "small bd-restore", title: "Its canvas back (Undo takes it back)" }),
                ...b.sessions.map((s) => button(s.replace(/^perf-|\.json$/g, ""), () => openAnalyzer(canvas, { build: b.number, file: s }), { icon: "bolt", class: "small ghost bd-session", title: "A saved analyzer session" })),
              ),
            );
          })
        : [h("p", { class: "hint app-empty" }, "No build yet: Launch makes the first")]),
    );
  };

  const relaunch = async (number: number, from: HTMLButtonElement): Promise<void> => {
    const opened = window.open("about:blank", `sab-launch-${canvas}`, "popup,width=1300,height=860");
    try {
      const said = await busyButton(from, api<{ ok: boolean; url?: string; title?: string; build?: number; problem?: { message?: string } }>(`${base(canvas)}/builds/${number}/launch`, "POST", {}), "Starting…");
      if (!said.ok || !said.url) throw new Error(said.problem?.message ?? "The build did not start.");
      if (opened) opened.location.href = said.url;
      host.launched(said);
    } catch (e) {
      opened?.close();
      errorHere(e, {}, from);
    }
  };

  const restore = async (number: number, from: HTMLButtonElement): Promise<void> => {
    try {
      host.restored(await busyButton(from, api(`${base(canvas)}/builds/${number}/restore`, "POST", {}), "Restoring…"));
      from.textContent = "Restored";
    } catch (e) {
      errorHere(e, {}, from);
    }
  };

  /** A list of files: the files beside, Monaco's diff editor for the one picked. */
  const drawFiles = async (title: string, files: Compared[]): Promise<void> => {
    const view = h("div", { class: "bd-diff" });
    const names = h("ul", { class: "bd-files", role: "listbox", "aria-label": "Files" });
    clear(detail, h("div", { class: "bd-detail-head" }, h("strong", {}, title)), h("div", { class: "bd-split" }, names, view));
    detail.append(loadingBlock("Opening the diff…"));
    const lib = await loadEditors();
    detail.lastElementChild?.remove();
    const viewer = lib.createDiffViewer(view, effectiveTheme());
    const pick = (f: Compared, item: HTMLElement): void => {
      for (const other of names.querySelectorAll(".selected")) other.classList.remove("selected");
      item.classList.add("selected");
      viewer.show(f.before ?? "", f.after ?? "", f.file);
    };
    const shown = files.filter((f) => f.status !== "same");
    for (const f of shown.length ? shown : files) {
      const item = h("li", { class: `bd-file bd-${f.status}`, role: "option", tabindex: 0, dataset: { file: f.file } }, h("span", { class: "mono" }, f.file), h("span", { class: "hint" }, f.status === "changed" ? `+${f.added} −${f.removed}` : f.status));
      item.addEventListener("click", () => pick(f, item));
      item.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") pick(f, item);
      });
      names.append(item);
    }
    const first = names.querySelector<HTMLElement>(".bd-file");
    const firstFile = (shown.length ? shown : files)[0];
    if (first && firstFile) pick(firstFile, first);
  };

  const showCompare = async (): Promise<void> => {
    const [a, b] = [...ticked].sort((x, y) => x - y);
    try {
      const got = await api<{ files: Compared[] }>(`${base(canvas)}/builds/compare?a=${a}&b=${b}`);
      await drawFiles(`Build ${a} → build ${b}`, got.files);
    } catch (e) {
      errorHere(e, {}, compare);
    }
  };

  const showNow = async (number: number): Promise<void> => {
    try {
      const got = await api<{ files: Compared[] }>(`${base(canvas)}/builds/compare?a=${number}`);
      await drawFiles(`Build ${number} → now`, got.files);
    } catch (e) {
      errorHere(e, {}, list);
    }
  };

  const showBuild = async (number: number): Promise<void> => {
    try {
      const got = await api<{ files: Record<string, string> }>(`${base(canvas)}/builds/${number}`);
      const files: Compared[] = Object.entries(got.files).map(([file, text]) => ({ file, status: "same", before: text, after: text, added: 0, removed: 0 }));
      await drawFiles(`Build ${number} (read-only)`, files);
    } catch (e) {
      errorHere(e, {}, list);
    }
  };

  list.append(loadingBlock("Reading the builds…"));
  try {
    builds = (await api<{ builds: Build[] }>(`${base(canvas)}/builds`)).builds;
    drawList();
  } catch (e) {
    clear(list);
    errorHere(e, {}, list);
  }
}
