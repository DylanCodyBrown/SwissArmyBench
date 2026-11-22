/**
 * workbenchDebug.ts: the Scripts page's debugger, one script's (services/debugger.py over the kernel's own
 * debugpy). [VIEW]
 *
 *   [GUTTER]   a click in the gutter toggles a breakpoint (F9 at the cursor); right-click there: Add
 *              conditional breakpoint…, Add log point…, Edit…, Remove. They follow the lines as the code is
 *              edited, and go to the kernel while it is being debugged.
 *   [START]    Start debugging (the row's bug, Ctrl+Shift+D): the script's text runs in its kernel under the
 *              debugger; it pauses at a breakpoint (a log point prints its words instead).
 *   [PAUSED]   the line highlighted; the panel under the code (closed until a debug starts, about 30% then):
 *              the toolbar (Continue F5, Step over F10, Step into F11, Step out Shift+F11, Stop Shift+F5), Call
 *              stack (a click shows that frame's variables), Variables (unfold a value), Watch (expressions
 *              evaluated at each stop), and the Debug console (an expression evaluated in the frame; the
 *              script's output and the log points' words above it).
 *   [NOTICE]   debug_state from the server (the agent's moves too: workbench_debug) is what draws it.
 */
import { api } from "./api";
import { askText, button, clear, h, icon, type MenuItem, showMenu } from "./dom";
import { errorHere } from "./errorNote";
import type { BreakpointMark, CodeEditor } from "./lazy/codeEditor";

export interface DebugHost {
  kernel: () => Promise<string>;
  path: () => string | null;
  text: () => string;
  editor: () => CodeEditor | null;
  /** Another frame's file (a module of the project) at a line; a library's: read-only. */
  openAt?: (path: string, line: number) => void;
  /** The panel opened or closed: the editor lays itself out again. */
  layout: () => void;
}

interface Mark {
  line: number;
  condition?: string;
  log?: string;
}

interface Frame {
  id: number;
  name: string;
  line: number;
  yours: boolean;
  path: string | null;
}

interface Variable {
  name: string;
  value: string;
  type: string;
  reference: number;
}

export interface DebugState {
  kernel: string;
  document: string | null;
  state: "idle" | "running" | "paused" | "ended";
  reason: string;
  line: number | null;
  frames: Frame[];
  output?: string;
  ok: boolean | null;
  error: string;
}

export interface DebugSession {
  element: HTMLElement;
  gutter: { toggle: (line: number) => void; menu: (line: number, x: number, y: number) => void };
  /** The editor is there: its marks drawn. */
  attach: (editor: CodeEditor) => void;
  toggleAtCursor: () => void;
  start: () => Promise<void>;
  step: (action: "over" | "into" | "out" | "continue") => Promise<void>;
  stop: () => Promise<void>;
  /** Paused at a breakpoint (the keys F5, F10, F11, Shift+F11 and Shift+F5 are the debugger's then). */
  paused: () => boolean;
  /** Being debugged (running or paused). */
  active: () => boolean;
  /** A debug_state notice: drawn when it is this script's kernel's. */
  heard: (state: DebugState) => void;
  marks: () => Mark[];
}

const KIND_WORDS: Record<string, string> = { plain: "Breakpoint", condition: "Conditional breakpoint", log: "Log point" };

export function debugSession(host: DebugHost): DebugSession {
  let marks: Mark[] = [];
  let kernelId: string | null = null;
  let state: DebugState["state"] = "idle";
  let frames: Frame[] = [];
  let frame: number | null = null;
  const watches: string[] = [];

  // ----- the panel (closed until a debug starts: 8.14) -----
  const status = h("span", { class: "wb-debug-status", role: "status", "aria-live": "polite" });
  const tool = (label: string, iconName: string, run: () => void, title: string): HTMLButtonElement => button(label, run, { icon: iconName, iconOnly: true, class: "ghost wb-debug-btn", title });
  const continueBtn = tool("Continue", "play", () => void session.step("continue"), "Continue (F5)");
  const overBtn = tool("Step over", "step-over", () => void session.step("over"), "Step over (F10)");
  const intoBtn = tool("Step into", "step-into", () => void session.step("into"), "Step into (F11)");
  const outBtn = tool("Step out", "step-out", () => void session.step("out"), "Step out (Shift+F11)");
  const stopBtn = tool("Stop debugging", "stop", () => void session.stop(), "Stop (Shift+F5)");
  const closeBtn = tool("Close the debugger", "close", () => setOpen(false), "Close");
  const stackHost = h("ol", { class: "wb-debug-stack", "aria-label": "Call stack" });
  const varsHost = h("div", { class: "wb-debug-vars", "aria-label": "Variables" });
  const watchInput = h("input", { type: "text", class: "mono", placeholder: "Add an expression to watch", "aria-label": "Watch expression", "data-no-variables": "", spellcheck: "false" }) as HTMLInputElement;
  const watchHost = h("ul", { class: "wb-debug-watch", "aria-label": "Watch" });
  const programOut = h("pre", { class: "wb-debug-out wb-debug-program", role: "log", "aria-label": "Output" });
  const consoleOut = h("pre", { class: "wb-debug-out", role: "log", "aria-label": "Debug console output" });
  const consoleInput = h("input", { type: "text", class: "mono", placeholder: "Evaluate in the frame", "aria-label": "Debug console", "data-no-variables": "", spellcheck: "false" }) as HTMLInputElement;
  const section = (title: string, ...body: (HTMLElement | null)[]): HTMLElement => h("section", { class: "wb-debug-part" }, h("h4", {}, title), ...body);
  const element = h(
    "section",
    { class: "wb-debug", "aria-label": "Debugger", hidden: true },
    h("div", { class: "wb-debug-bar", role: "toolbar", "aria-label": "Debug toolbar" }, icon("bug"), status, h("span", { class: "ide-bar-gap" }), continueBtn, overBtn, intoBtn, outBtn, stopBtn, closeBtn),
    h(
      "div",
      { class: "wb-debug-body" },
      section("Call stack", stackHost),
      section("Variables", varsHost),
      section("Watch", watchInput, watchHost),
      section("Output", programOut),
      section("Debug console", consoleOut, consoleInput),
    ),
  );

  function setOpen(open: boolean): void {
    element.hidden = !open;
    host.layout();
  }

  function drawButtons(): void {
    const pausedNow = state === "paused";
    for (const b of [continueBtn, overBtn, intoBtn, outBtn]) b.disabled = !pausedNow;
    stopBtn.disabled = state !== "paused" && state !== "running";
    status.textContent = state === "paused" ? `Paused${frames[0] ? ` in ${frames[0].name}, line ${frames[0].line}` : ""}` : state === "running" ? "Running…" : state === "ended" ? "Ended" : "Not debugging";
  }

  // ----- breakpoints -----
  const kindOf = (m: Mark): BreakpointMark["kind"] => (m.log ? "log" : m.condition ? "condition" : "plain");
  function draw(): void {
    host.editor()?.setBreakpoints(marks.map((m) => ({ line: m.line, kind: kindOf(m), title: m.log ? `Log point: ${m.log}` : m.condition ? `Breaks when ${m.condition}` : "Breakpoint" })));
  }
  /** The marks' lines as edits moved them (the editor's decorations, in line order). */
  function follow(): void {
    const lines = host.editor()?.breakpointLines() ?? [];
    if (lines.length !== marks.length) return;
    const sorted = [...lines].sort((a, b) => a - b);
    marks = marks.map((m, i) => ({ ...m, line: sorted[i] ?? m.line }));
  }
  async function send(): Promise<void> {
    if (!kernelId || (state !== "running" && state !== "paused")) return;
    await api("/workbench/debug/breakpoints", "POST", { kernel: kernelId, breakpoints: marks }).catch((e: Error) => errorHere(e));
  }
  function setMark(line: number, mark: Mark | null): void {
    follow();
    marks = marks.filter((m) => m.line !== line);
    if (mark) marks.push(mark);
    marks.sort((a, b) => a.line - b.line);
    draw();
    void send();
  }
  async function ask(words: string, now: string): Promise<string | null> {
    const said = await askText(words, now);
    return said === null ? null : said.trim();
  }

  // ----- the paused state -----
  async function showVariables(): Promise<void> {
    if (!kernelId || frame === null) return void clear(varsHost);
    const said = await api<{ scopes: { scope: string; variables: Variable[] }[] }>("/workbench/debug/variables", "POST", { kernel: kernelId, frame });
    clear(varsHost, ...said.scopes.map((s) => h("details", { class: "wb-debug-scope", open: s.scope === "Locals" || said.scopes.length === 1 }, h("summary", {}, s.scope), variableList(s.variables))));
  }
  function variableList(list: Variable[]): HTMLElement {
    return h(
      "ul",
      { class: "wb-debug-varlist" },
      ...list.map((v) => {
        const row = h("li", { class: "wb-debug-var", "data-name": v.name }, h("span", { class: "wb-debug-name" }, v.name), h("span", { class: "wb-debug-value mono", title: v.type }, v.value));
        if (v.reference > 0) {
          const more = h("details", {}, h("summary", {}, h("span", { class: "wb-debug-name" }, v.name), h("span", { class: "wb-debug-value mono", title: v.type }, v.value)));
          more.addEventListener(
            "toggle",
            () => {
              if (!more.open || more.dataset.loaded || !kernelId) return;
              more.dataset.loaded = "1";
              void api<{ variables: Variable[] }>("/workbench/debug/variables", "POST", { kernel: kernelId, reference: v.reference }).then((r) => more.append(variableList(r.variables)), (e: Error) => errorHere(e));
            },
          );
          return h("li", { class: "wb-debug-var" }, more);
        }
        return row;
      }),
    );
  }
  async function evaluate(expression: string): Promise<{ value?: string; error?: string }> {
    if (!kernelId) return { error: "Not debugging." };
    return api<{ value?: string; error?: string }>("/workbench/debug/evaluate", "POST", { kernel: kernelId, expression, frame });
  }
  async function showWatches(): Promise<void> {
    const rows = await Promise.all(watches.map(async (w) => [w, state === "paused" ? await evaluate(w).catch((e: Error) => ({ error: e.message }) as { value?: string; error?: string }) : ({} as { value?: string; error?: string })] as const));
    clear(
      watchHost,
      ...rows.map(([w, got], i) =>
        h(
          "li",
          { class: "wb-debug-var" },
          h("span", { class: "wb-debug-name mono" }, w),
          h("span", { class: `wb-debug-value mono${got.error ? " error-text" : ""}` }, got.error ?? got.value ?? ""),
          button("Remove the watch", () => (watches.splice(i, 1), void showWatches()), { icon: "close", iconOnly: true, class: "ghost" }),
        ),
      ),
    );
  }
  function drawStack(): void {
    clear(
      stackHost,
      ...frames.map((f) => {
        const go = h("button", { type: "button", class: `wb-debug-frame${f.id === frame ? " current" : ""}${f.yours ? "" : " library"}`, "aria-current": f.id === frame ? "true" : undefined }, h("strong", {}, f.name), h("span", { class: "hint" }, ` ${f.yours ? "" : `${(f.path ?? "").split(/[\\/]/).pop()} `}line ${f.line}`));
        go.addEventListener("click", () => {
          frame = f.id;
          drawStack();
          if (f.yours) host.editor()?.reveal(f.line);
          else if (f.path && host.openAt) host.openAt(f.path, f.line);
          void showVariables().catch((e: Error) => errorHere(e));
          void showWatches();
        });
        return h("li", {}, go);
      }),
    );
  }

  const session: DebugSession = {
    element,
    gutter: {
      toggle: (line) => setMark(line, marks.some((m) => m.line === line) ? null : { line }),
      menu: (line, x, y) => {
        follow();
        const here = marks.find((m) => m.line === line);
        const items: MenuItem[] = [
          ...(here ? ([["close", `Remove ${KIND_WORDS[kindOf(here)]!.toLowerCase()}`, () => setMark(line, null)]] as MenuItem[]) : ([["bug", "Add breakpoint", () => setMark(line, { line })]] as MenuItem[])),
          ["bug", here?.condition ? "Edit condition…" : "Add conditional breakpoint…", async () => {
            const condition = await ask(`Break at line ${line} when (Python)`, here?.condition ?? "");
            if (condition) setMark(line, { line, condition });
          }],
          ["note", here?.log ? "Edit log point…" : "Add log point…", async () => {
            const log = await ask(`At line ${line}, print (values in {braces})`, here?.log ?? "");
            if (log) setMark(line, { line, log });
          }],
        ];
        showMenu(x, y, `Breakpoints at line ${line}`, items);
      },
    },
    attach: () => draw(),
    toggleAtCursor: () => {
      const line = host.editor()?.cursorLine();
      if (line) session.gutter.toggle(line);
    },
    start: async () => {
      follow();
      kernelId = await host.kernel();
      programOut.textContent = "";
      setOpen(true);
      const said = await api<DebugState>("/workbench/debug/start", "POST", { kernel: kernelId, document: host.path(), code: host.text(), breakpoints: marks });
      session.heard(said);
    },
    step: async (action) => {
      if (!kernelId || state !== "paused") return;
      host.editor()?.setExecutionLine(null);
      state = "running";
      drawButtons();
      await api("/workbench/debug/step", "POST", { kernel: kernelId, action }).catch((e: Error) => errorHere(e));
    },
    stop: async () => {
      if (!kernelId) return;
      const said = await api<DebugState>("/workbench/debug/stop", "POST", { kernel: kernelId });
      session.heard(said);
    },
    paused: () => state === "paused",
    active: () => state === "paused" || state === "running",
    heard: (said) => {
      if (!kernelId || said.kernel !== kernelId) return;
      state = said.state;
      const shown = (text: string): void => {
        programOut.textContent = text;
        programOut.scrollTop = programOut.scrollHeight;
      };
      // The script's output and the log points' words: in the answer, else read once a stop or the end says so.
      if (said.output !== undefined) shown(said.output);
      else void api<DebugState>(`/workbench/debug?kernel=${encodeURIComponent(kernelId)}`).then((full) => shown(full.output ?? "")).catch(() => undefined);
      frames = said.frames;
      if (state === "paused") {
        setOpen(true);
        frame = frames[0]?.id ?? null;
        const mine = frames.find((f) => f.yours);
        host.editor()?.setExecutionLine(mine?.line ?? null);
        drawStack();
        void showVariables().catch((e: Error) => errorHere(e));
        void showWatches();
      } else {
        host.editor()?.setExecutionLine(null);
        frame = null;
        drawStack();
        clear(varsHost);
        if (state === "ended") void showWatches();
      }
      drawButtons();
    },
    marks: () => (follow(), marks),
  };

  watchInput.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !watchInput.value.trim()) return;
    watches.push(watchInput.value.trim());
    watchInput.value = "";
    void showWatches();
  });
  consoleInput.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !consoleInput.value.trim()) return;
    const expression = consoleInput.value.trim();
    consoleInput.value = "";
    void evaluate(expression).then(
      (got) => {
        consoleOut.append(h("span", { class: "wb-debug-in" }, `> ${expression}\n`), h("span", { class: got.error ? "error-text" : "" }, `${got.error ?? got.value ?? ""}\n`));
        consoleOut.scrollTop = consoleOut.scrollHeight;
      },
      (err: Error) => errorHere(err),
    );
  });
  drawButtons();
  return session;
}
