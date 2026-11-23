/**
 * canvasRun.ts: the Canvas's Play, Launch and Export. Moved out of canvasPage.ts along its own heading (the
 * craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [PLAY]    Play (F5) shows the page live in place (Esc or Edit stops it); a broken wire is said first
 *   [LAUNCH]  Launch (Ctrl+F5): a build run in a window of its own; with the Performance Analyzer (Ctrl+Shift+F5)
 *             its window beside, recording from the first load; Play is Stop while the app runs
 *   [EXPORT]  the app into a folder the user picks (its warnings said)
 *   One run at a time, its words over the canvas meanwhile.
 *
 * ROUTING: POST /streamlit/canvases/{canvas}/play, …/launch, …/stop, …/export
 */
import { api } from "./api";
import { analyzerAddress, openAnalyzer } from "./canvasBuilds";
import type { CanvasState as State } from "./canvasPage";
import { brokenWords } from "./canvasWiring";
import { button, clear, h, icon, toast } from "./dom";
import { clearError, showError } from "./errorNote";
import { chooseFile } from "./fileChooser";
import { busy } from "./loading";
import { shareMark, type ShareableApp } from "./shareApp";

type Layout = "desktop" | "phone";

/** What a run asks of the page: where the live page goes and the board it covers, the notice, Play's button
 *  and Share's place, a word said, a canvas taken, and the canvas, its page and layout. */
export interface RunHost {
  live: HTMLElement;
  viewport: HTMLElement;
  stage: HTMLElement;
  notice: HTMLElement;
  playButton: HTMLElement;
  shareHolder: HTMLElement;
  previewWidth: Record<Layout, number>;
  say: (words: string) => void;
  take: (next: State) => void;
  shareable: () => ShareableApp | null;
  readonly state: State | null;
  readonly page: string;
  readonly layout: Layout;
}

export function canvasRun(host: RunHost) {
  const { live, viewport, stage, notice, playButton, shareHolder } = host;

  let launched = false;
  let runningWork = false;

  function running(): boolean {
    return !live.hidden || launched;
  }
  function stopRunning(): void {
    if (!live.hidden) stopPlay();
    else if (launched) void stopLaunch();
  }
  /** Play is Stop while the app runs (the page playing, or launched). */
  function drawRun(): void {
    const on = running();
    playButton.replaceChildren(icon(on ? "stop" : "play"), h("span", { class: "btn-label" }, on ? "Stop" : "Play"));
    playButton.setAttribute("aria-label", on ? "Stop" : "Play");
    playButton.title = on ? (!live.hidden ? "Stop playing (Esc)" : "Stop the launched app") : "Play (F5)";
    playButton.classList.toggle("running", on);
    const app = host.shareable();
    if (app && shareHolder.dataset.app !== app.id) {
      shareHolder.dataset.app = app.id;
      shareHolder.replaceChildren(shareMark(app));
    }
  }

  /** One run at a time (Play, Launch, Export), its words over the canvas meanwhile. */
  async function gated(words: string, work: () => Promise<void>): Promise<void> {
    if (runningWork) return;
    runningWork = true;
    try {
      await busy(stage, words, work(), { errorIn: false });
    } finally {
      runningWork = false;
    }
  }

  async function play(): Promise<void> {
    if (!host.state) return;
    const broken = brokenWords(host.state.wiring);
    if (broken) host.say(broken); // listed before Play: the host.page runs, each broken In on its starting value
    await gated("Starting the page…", async () => {
      try {
        const said = await api<{ ok: boolean; url?: string; problem?: { message?: string; command?: string } }>(`/streamlit/canvases/${host.state!.canvas}/play`, "POST", { page: host.page });
        if (!said.ok || !said.url) return void showError(notice, new Error(said.problem?.message ?? `Streamlit is not in this Python${said.problem?.command ? `: ${said.problem.command}` : ""}.`));
        clearError(notice);
        clear(
          live,
          h("div", { class: "cvs-live-bar" }, h("span", {}, "Playing"), button("Edit", () => stopPlay(), { icon: "edit", class: "ghost cvs-edit" })),
          h(
            "iframe",
            {
              class: "cvs-live-frame",
              src: said.url,
              title: "The page, playing",
              "data-layout": host.layout,
              style: { width: `${host.previewWidth[host.layout]}px`, maxWidth: "100%", alignSelf: "center" }
            }
          )
        );
        live.hidden = false;
        viewport.hidden = true;
        drawRun();
      } catch (e) {
        showError(notice, e);
      }
    });
  }

  function stopPlay(): void {
    live.hidden = true;
    viewport.hidden = false;
    clear(live);
    drawRun();
    if (host.state) void api(`/streamlit/canvases/${host.state.canvas}/stop`, "POST", {}).catch(() => undefined);
  }

  async function stopLaunch(): Promise<void> {
    if (!host.state) return;
    launched = false;
    drawRun();
    await api(`/streamlit/canvases/${host.state.canvas}/stop`, "POST", { run: "launch" }).catch((e) => showError(notice, e));
  }

  /** Launch (Ctrl+F5): a new build run in a window of its own; `analyzer` (Ctrl+Shift+F5): the Performance
   *  Analyzer recording from the first load, its window opened beside. */
  async function launch(analyzer = false): Promise<void> {
    if (!host.state) return;
    const opened = window.open("about:blank", `sab-launch-${host.state.canvas}`, "popup,width=1300,height=860");
    // Both windows open now, on the key or click (a window opened after the wait would be blocked).
    const perfWindow = analyzer ? openAnalyzer(host.state.canvas, undefined, "about:blank") : null;
    await gated(analyzer ? "Launching with the Performance Analyzer…" : "Launching…", async () => {
      try {
        const said = await api<{ ok: boolean; url?: string; title?: string; problem?: { message?: string } }>(`/streamlit/canvases/${host.state!.canvas}/launch`, "POST", analyzer ? { analyzer: true } : {});
        if (!said.ok || !said.url) {
          opened?.close();
          perfWindow?.close();
          return void showError(notice, new Error(said.problem?.message ?? "The app did not start."));
        }
        launched = true;
        drawRun();
        if (opened) opened.location.href = said.url;
        else showError(notice, new Error("The browser blocked the new window: allow pop-ups for this address."));
        if (perfWindow) perfWindow.location.href = analyzerAddress(host.state!.canvas);
        toast(`${said.title ?? "The app"} launched.`);
      } catch (e) {
        opened?.close();
        perfWindow?.close();
        showError(notice, e);
      }
    });
  }

  /** What the Builds dialog asks of the page: a relaunch's window is open, a restore's canvas is drawn. */
  const buildsHost = {
    launched: (said: { title?: string }) => {
      launched = true;
      drawRun();
      toast(`${said.title ?? "The build"} launched.`);
    },
    restored: (next: unknown) => host.take(next as State),
  };

  async function exportApp(): Promise<void> {
    if (!host.state) return;
    const folder = await chooseFile({ title: "Export the app into", mode: "folder", start: host.state.path.replace(/[\\/][^\\/]*$/, "") });
    if (!folder) return;
    await gated("Exporting…", async () => {
      try {
        const done = await api<{ folder: string; files: string[]; warnings?: string[] }>(`/streamlit/canvases/${host.state!.canvas}/export`, "POST", { folder });
        toast(`Exported: ${done.files.length} files in ${done.folder}`);
        // It calls the local sandbox API: the variables to set where it runs (its README lists them too).
        if (done.warnings?.length) showError(notice, done.warnings.join(" "), { level: "warning", agent: false });
      } catch (e) {
        showError(notice, e);
      }
    });
  }

  return { running, stopRunning, drawRun, play, stopPlay, stopLaunch, launch, exportApp, buildsHost, isLaunched: (): boolean => launched };
}
