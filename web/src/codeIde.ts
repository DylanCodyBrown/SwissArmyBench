/**
 * codeIde.ts: a page that is an IDE for one piece of code. [SHARED]
 *
 * The owner (2026-11-21), on the blade screen: "this entire panel should be an ide, with small save, saves,
 * cancel buttons at the top and a play button to execute with a realtime linter and output at the bottom to
 * see the results. This is an IDE not a save form". The blade screen (bladeEditor.ts) is the first page built
 * on it; any page with one piece of code to edit and run can use it (a host gives the code, what Save, Save
 * as, Cancel and Run do, and its Properties).
 *
 *   TOP BAR     small buttons: Back, the name, the dirty dot, Save (Ctrl+S), Save as…, Cancel, ▶ Run (F5,
 *               Ctrl+Enter; ■ Stop while it runs), Properties (the pane's switch), "…" (the host's menu)
 *   NOTE        a bar under it for what needs the user (the file changed on disk: Reload / Keep mine)
 *   EDITOR      Monaco, filling the middle; the intelligence is the host's (the Workbench's: workbenchIntel.ts,
 *               ghost text from inlineCompletion.ts): this file draws, it never asks the server
 *   PROPERTIES  a narrow pane at the right, closed until its switch opens it (remembered per host)
 *   PANEL       at the bottom, resizable (its splitter), folded to its tabs until something runs or a tab
 *               is clicked: Output | Result | Problems. Output is
 *               written as it comes (stdout, stderr in the error colour); Result holds what the host puts
 *               there (a table, a value, the error panel); Problems is the lint as you type, each a link to
 *               its line, its count on the tab
 *
 * Design principle 8.14 (the owner, 2026-11-21: "Never crowd the place where code is written"): one slim row
 * of small buttons, no heading over the editor, Properties closed and the panel folded until wanted.
 *
 * Run is gated with the one loading state (loading.ts busy over the Result, Cancel aborting the host's work).
 */
import { button, h, icon, showMenu } from "./dom";
import type { CodeEditor, CodeEditorOptions, EditorLanguage, IntelProblem, Problem } from "./lazy/codeEditor";
import { busy } from "./loading";

/** Monaco, loaded when an IDE (or a read-only viewer) first opens; its styles with it. */
let editors: Promise<typeof import("./lazy/codeEditor")> | null = null;
export function loadEditors(): Promise<typeof import("./lazy/codeEditor")> {
  if (!document.querySelector('link[href="/static/build/lazy/codeEditor.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/build/lazy/codeEditor.css" }));
  }
  return (editors ??= import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>);
}

export type IdeTab = "output" | "result" | "problems";

export interface IdeOutput {
  clear(): void;
  write(stream: "stdout" | "stderr" | "note", text: string): void;
}

export interface IdeMenuItem {
  label: string;
  icon: string;
  run: () => void;
}

export interface IdeOptions {
  /** What the bar names (the blade's name). */
  name: string;
  /** Drawn after the name (a kind chip, "read-only"). */
  badge?: HTMLElement | null;
  language: EditorLanguage;
  value: string;
  theme: () => string;
  back?: { label: string; run: () => void };
  /** Save (Ctrl+S): true when it was saved (the IDE is clean again at the text it saved). */
  save?: (code: string) => Promise<boolean>;
  saveAs?: (code: string) => void;
  /** Cancel: the file's text again (null: leave it). The IDE asks first when there are unsaved changes. */
  revert?: () => Promise<string | null>;
  /** Run (F5, Ctrl+Enter): the host's work; the IDE gates the Result with the loading state meanwhile. */
  run?: (code: string, abort: AbortController, output: IdeOutput) => Promise<void>;
  /** Words while it runs ("Running Loaves…"). */
  runWords?: string;
  menu?: () => IdeMenuItem[];
  properties?: HTMLElement | null;
  /** The editor's intelligence and keys (complete, intel, inline, sendToAgent...), as the Workbench gives. */
  editor?: Partial<CodeEditorOptions>;
  /** Where the panel's height and the Properties pane's fold are remembered (localStorage), per host. */
  remember?: string;
  /** The host's own controls in the bar, before Run (the Widgets window's Code | Preview switch). */
  actions?: HTMLElement[];
  /** Shown in the editor's place while the host says (setStage(true)): the Widgets window's Preview. */
  stage?: HTMLElement;
  /** Properties open until the user closes it (default: closed until asked for). */
  propertiesOpen?: boolean;
}

export interface CodeIde {
  element: HTMLElement;
  /** Monaco, once loaded. */
  ready: Promise<CodeEditor>;
  value(): string;
  /** The editor's text replaced; `clean`: it is the file's now (no dirty dot). */
  setValue(text: string, clean?: boolean): void;
  dirty(): boolean;
  /** The text that is saved now (the dirty dot goes while the editor holds it). */
  markClean(text: string): void;
  /** Something else unsaved (the host's Properties): the dirty dot shows for it too. */
  setExtraDirty(dirty: boolean): void;
  setName(name: string): void;
  /** Properties opened or closed (its switch's work; no argument: the other way). */
  toggleProperties(shown?: boolean): void;
  /** The host's stage in the editor's place (true), or the editor again (false). */
  setStage(shown: boolean): void;
  output: IdeOutput;
  /** The Result tab's content (null: empty). */
  showResult(content: HTMLElement | null): void;
  /** A failed run's places in the editor (squiggles, end-of-line words); [] clears them. */
  setRunProblems(list: Problem[]): void;
  showTab(tab: IdeTab): void;
  /** The bar under the top bar (null: gone). */
  note(content: HTMLElement | null): void;
  /** The lint's problems now. */
  problems(): IntelProblem[];
  /** Run now, as the ▶ button does. */
  run(): Promise<void>;
  save(): Promise<void>;
  dispose(): void;
}

function remembered(key: string | undefined, part: string): string | null {
  if (!key) return null;
  try {
    return localStorage.getItem(`sab-ide-${key}-${part}`);
  } catch {
    return null;
  }
}

function keep(key: string | undefined, part: string, value: string): void {
  if (!key) return;
  try {
    localStorage.setItem(`sab-ide-${key}-${part}`, value);
  } catch {
    /* no storage: not remembered */
  }
}

const SEVERITY_WORD: Record<string, string> = { error: "Error", warning: "Warning", hint: "Hint", info: "Info" };

// ===== the panel: Output | Result | Problems, on its own (another page's tab can mount it) =====

export interface RunPanel {
  /** The panel itself (a section); put `splitter()` above it to make it resizable. */
  element: HTMLElement;
  output: IdeOutput;
  showResult(content: HTMLElement | null): void;
  showTab(tab: IdeTab): void;
  /** The lint's problems now (the Problems tab and its count). */
  setLint(problems: IntelProblem[]): void;
  lint(): IntelProblem[];
  setFolded(folded: boolean): void;
  /** A run's work, gated with the one loading state (the Result's cover, Cancel aborting `abort`); the
   *  Output is cleared first and the Result tab spins meanwhile. A failure or a Cancel is not thrown. */
  running(words: string, work: Promise<void>, abort: AbortController): Promise<void>;
  /** A splitter to put above the panel: dragged, the panel's height follows (at most `within`'s less 80px). */
  splitter(within: () => HTMLElement): HTMLElement;
}

export interface RunPanelOptions {
  /** Where its height and fold are remembered (localStorage). */
  remember?: string;
  /** Told when its size changes (the editor beside it lays itself out again). */
  layout?: () => void;
  /** A problem's link: the editor to that line and column. */
  reveal?: (line: number, column: number) => void;
}

export function runPanel(options: RunPanelOptions = {}): RunPanel {
  let lint: IntelProblem[] = [];
  const outputPane = h("pre", { class: "ide-output", role: "log", "aria-live": "polite", "aria-label": "Output" });
  const resultPane = h("div", { class: "ide-result", "aria-label": "Result" });
  const problemsPane = h("div", { class: "ide-problems", "aria-label": "Problems" });
  const panes: Record<IdeTab, HTMLElement> = { output: outputPane, result: resultPane, problems: problemsPane };
  const tabCount = h("span", { class: "ide-count", hidden: true });
  const tabs: Record<IdeTab, HTMLButtonElement> = {
    output: h("button", { type: "button", role: "tab", class: "ide-tab" }, "Output") as HTMLButtonElement,
    result: h("button", { type: "button", role: "tab", class: "ide-tab" }, "Result") as HTMLButtonElement,
    problems: h("button", { type: "button", role: "tab", class: "ide-tab" }, "Problems", tabCount) as HTMLButtonElement,
  };
  // Folded to its tabs until something runs (design principle 8.14); a tab or a run opens it.
  let folded = true;
  function showTab(tab: IdeTab, open = true): void {
    for (const [key, el] of Object.entries(tabs) as [IdeTab, HTMLButtonElement][]) {
      el.setAttribute("aria-selected", String(key === tab));
      panes[key].hidden = key !== tab;
    }
    if (folded && open) setFolded(false);
  }
  for (const [key, el] of Object.entries(tabs) as [IdeTab, HTMLButtonElement][]) el.addEventListener("click", () => showTab(key));
  const foldBtn = button("Fold the panel", () => setFolded(!folded), { icon: "collapse", iconOnly: true, class: "ghost ide-btn" });
  const element = h(
    "section",
    { class: "ide-panel", "aria-label": "Output, result and problems" },
    h("div", { class: "ide-tabs", role: "tablist" }, tabs.output, tabs.result, tabs.problems, h("span", { class: "ide-bar-gap" }), foldBtn),
    h("div", { class: "ide-panel-body" }, outputPane, resultPane, problemsPane),
  );
  const height = Number(remembered(options.remember, "panel")) || 0;
  if (height > 60) element.style.height = `${height}px`;
  function setFolded(fold: boolean): void {
    folded = fold;
    element.classList.toggle("folded", fold);
    foldBtn.setAttribute("aria-pressed", String(fold));
    foldBtn.title = fold ? "Open the panel" : "Fold the panel";
    foldBtn.setAttribute("aria-label", foldBtn.title);
    options.layout?.();
  }
  function drawProblems(): void {
    tabCount.hidden = lint.length === 0;
    tabCount.textContent = String(lint.length);
    problemsPane.replaceChildren(
      lint.length
        ? h(
            "ul",
            { class: "ide-problem-list" },
            ...lint.map((p) => {
              const go = h(
                "button",
                { type: "button", class: `link ide-problem ${p.severity}` },
                icon(p.severity === "error" ? "problem" : p.severity === "warning" ? "warning" : "info"),
                h("span", { class: "ide-problem-text" }, p.message),
                h("span", { class: "hint" }, ` ${p.source}${p.code ? ` ${p.code}` : ""}, line ${p.line}, column ${p.col}`),
              );
              go.setAttribute("aria-label", `${SEVERITY_WORD[p.severity] ?? p.severity}: ${p.message}, line ${p.line}`);
              go.addEventListener("click", () => options.reveal?.(p.line, p.col));
              return h("li", {}, go);
            }),
          )
        : h("p", { class: "hint ide-empty" }, "No problems."),
    );
  }
  const output: IdeOutput = {
    clear: () => outputPane.replaceChildren(),
    write: (stream, text) => {
      const last = outputPane.lastElementChild as HTMLElement | null;
      if (last && last.dataset.stream === stream) last.textContent += text;
      else outputPane.append(h("span", { class: `ide-out ${stream}`, "data-stream": stream }, text));
      outputPane.scrollTop = outputPane.scrollHeight;
    },
  };
  function splitter(within: () => HTMLElement): HTMLElement {
    const split = h("div", { class: "ide-split", role: "separator", "aria-orientation": "horizontal", "aria-label": "Resize the panel", tabindex: "0" });
    split.addEventListener("pointerdown", (down) => {
      down.preventDefault();
      const start = down.clientY;
      const from = element.getBoundingClientRect().height;
      if (folded) setFolded(false);
      split.setPointerCapture(down.pointerId);
      const move = (e: PointerEvent): void => {
        const max = Math.max(120, within().getBoundingClientRect().height - 80);
        element.style.height = `${Math.round(Math.min(max, Math.max(60, from + start - e.clientY)))}px`;
        options.layout?.();
      };
      split.addEventListener("pointermove", move);
      split.addEventListener(
        "pointerup",
        () => {
          split.removeEventListener("pointermove", move);
          keep(options.remember, "panel", String(Math.round(element.getBoundingClientRect().height)));
        },
        { once: true },
      );
    });
    split.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      e.preventDefault();
      element.style.height = `${Math.max(60, element.getBoundingClientRect().height + (e.key === "ArrowUp" ? 24 : -24))}px`;
      options.layout?.();
    });
    return split;
  }
  drawProblems();
  setFolded(folded);
  showTab("output", false);
  return {
    element,
    output,
    showResult: (content) => resultPane.replaceChildren(...(content ? [content] : [])),
    showTab: (tab) => showTab(tab),
    setLint: (found) => {
      lint = found;
      drawProblems();
    },
    lint: () => lint,
    setFolded,
    running: async (words, work, abort) => {
      output.clear();
      resultPane.replaceChildren();
      showTab("output");
      const spinning = h("span", { class: "busy-spinner ide-tab-spin", "aria-hidden": "true" });
      tabs.result.append(spinning);
      try {
        await busy(resultPane, words, work, { abort, errorIn: false });
      } catch {
        /* the host shows its own failure; a Cancel shows nothing */
      } finally {
        spinning.remove();
      }
    },
    splitter,
  };
}

/** Build the IDE (see the module's comment). The host puts `element` where it fills the page. */
export function codeIde(options: IdeOptions): CodeIde {
  let editor: CodeEditor | null = null;
  let disposed = false;
  let pending = options.value; // the text before Monaco loads, then the editor's
  let saved = options.value;
  let running: AbortController | null = null;
  let extraDirty = false;

  // ----- the top bar -----
  const nameEl = h("span", { class: "ide-name" }, options.name);
  const dot = h("span", { class: "ide-dirty", title: "Unsaved changes", "aria-label": "Unsaved changes", hidden: true });
  const small = (label: string, run: () => void, iconName: string, extra: { class?: string; title?: string; iconOnly?: boolean } = {}): HTMLButtonElement =>
    button(label, run, { icon: iconName, class: `ide-btn ${extra.class ?? "ghost"}`, title: extra.title ?? label, iconOnly: extra.iconOnly });
  const saveBtn = options.save ? small("Save", () => void doSave(), "save", { title: "Save (Ctrl+S)" }) : null;
  const saveAsBtn = options.saveAs ? small("Save as…", () => options.saveAs?.(value()), "copy") : null;
  const cancelBtn = options.revert ? small("Cancel", () => void doRevert(), "undo", { title: "Cancel: back to the file" }) : null;
  const runBtn = options.run ? small("Run", () => void doRun(), "play", { class: "primary", title: "Run (F5, Ctrl+Enter)" }) : null;
  const propsBtn = options.properties ? small("Properties", () => setProps(!propsShown), "properties", { iconOnly: true }) : null;
  const moreBtn = options.menu
    ? small("More", () => {
        const rect = moreBtn!.getBoundingClientRect();
        showMenu(rect.left, rect.bottom + 2, "More", options.menu!().map((m) => [m.icon, m.label, m.run] as [string, string, () => void]));
      }, "more", { iconOnly: true, title: "More" })
    : null;
  // ----- the code's own zoom (the owner, 2026-11-21: "Can the blade ide be zoomable"): Ctrl + wheel and
  // Ctrl+= / Ctrl+- / Ctrl+0 over the code size the code alone (8 to 40 px), remembered per host; the bar shows
  // the size only while it is not 100% (design principle 8.14), a click puts it back. -----
  const BASE = 13;
  let fontPx = Math.min(40, Math.max(8, Number(remembered(options.remember, "font")) || BASE));
  const zoomBadge = h("button", { type: "button", class: "ide-btn ghost ide-zoom", title: "Code size: click for 100% (Ctrl+0)", hidden: true, onclick: () => setFont(BASE) });
  function setFont(px: number): void {
    fontPx = Math.min(40, Math.max(8, Math.round(px)));
    editor?.setFontSize(fontPx);
    zoomBadge.textContent = `${Math.round((fontPx / BASE) * 100)}%`;
    zoomBadge.hidden = fontPx === BASE;
    keep(options.remember, "font", String(fontPx));
  }
  const stepFont = (direction: number): void => setFont(fontPx + direction * (fontPx >= 20 ? 2 : 1));

  const bar = h(
    "div",
    { class: "ide-bar", role: "toolbar", "aria-label": `${options.name} toolbar` },
    options.back ? small(options.back.label, options.back.run, "back", { class: "ghost back-btn" }) : null,
    h("span", { class: "ide-title" }, nameEl, dot, options.badge ?? null),
    h("span", { class: "ide-bar-gap" }),
    zoomBadge,
    saveBtn,
    saveAsBtn,
    cancelBtn,
    ...(options.actions ?? []),
    runBtn,
    propsBtn,
    moreBtn,
  );
  const noteHost = h("div", { class: "ide-note", hidden: true });


  // ----- the middle: the editor and Properties -----
  const editorHost = h("div", { class: "ide-editor", "data-own-zoom": "", "aria-label": `${options.name} code` }, h("pre", { class: "code-box ide-plain" }, options.value));
  const props = options.properties ? h("aside", { class: "ide-props", "aria-label": "Properties" }, h("h3", { class: "ide-props-title" }, "Properties"), options.properties) : null;
  // Design principle 8.14 ("Never crowd the place where code is written"): closed until asked for.
  const keptProps = remembered(options.remember, "props");
  let propsShown = keptProps === null ? !!options.propertiesOpen : keptProps === "on";
  function setProps(shown: boolean): void {
    propsShown = shown;
    if (props) props.hidden = !shown;
    propsBtn?.setAttribute("aria-pressed", String(shown));
    keep(options.remember, "props", shown ? "on" : "off");
  }

  // ----- the panel: Output | Result | Problems (runPanel, mountable on its own) -----
  const panel = runPanel({ remember: options.remember, layout: () => editor?.layout(), reveal: (line, col) => editor?.reveal(line, col) });
  const { output, showTab } = panel;
  const split = panel.splitter(() => center);

  const stageHost = options.stage ? h("div", { class: "ide-stage", hidden: true }, options.stage) : null;
  const center = h("div", { class: "ide-center" }, editorHost, stageHost, split, panel.element);
  const element = h("div", { class: "code-ide" }, bar, noteHost, h("div", { class: "ide-body" }, center, props));
  setProps(propsShown);

  // Ctrl+S anywhere in the IDE (the page's own save never opens); F5 too, outside the editor.
  element.addEventListener(
    "keydown",
    (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        e.stopPropagation();
        void doSave();
      } else if ((e.ctrlKey || e.metaKey) && !e.altKey && ["=", "+", "-", "0"].includes(e.key) && editorHost.contains(e.target as Node)) {
        // Over the code, the code's own size (the page's zoom stays where it is).
        e.preventDefault();
        e.stopPropagation();
        if (e.key === "0") setFont(BASE);
        else stepFont(e.key === "-" ? -1 : 1);
      } else if (e.key === "F5" && options.run) {
        e.preventDefault();
        void doRun();
      }
    },
    true,
  );

  editorHost.addEventListener(
    "wheel",
    (e) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      e.stopPropagation();
      stepFont(e.deltaY < 0 ? 1 : -1);
    },
    { capture: true, passive: false },
  );

  // ----- state -----
  function value(): string {
    return editor ? editor.value() : pending;
  }
  function drawDirty(): void {
    const isDirty = value() !== saved || extraDirty;
    dot.hidden = !isDirty;
    element.classList.toggle("is-dirty", isDirty);
  }
  // ----- the actions -----
  async function doSave(): Promise<void> {
    if (!options.save || !saveBtn || saveBtn.disabled) return;
    const text = value();
    saveBtn.disabled = true;
    try {
      if (await options.save(text)) {
        saved = text;
        drawDirty();
      }
    } finally {
      saveBtn.disabled = false;
    }
  }

  async function doRevert(): Promise<void> {
    if (!options.revert) return;
    if ((value() !== saved || extraDirty) && !(await askDiscard())) return;
    const text = await options.revert();
    if (text === null) return;
    api.setValue(text, true);
  }

  /** Unsaved changes: the user's word before they go. */
  function askDiscard(): Promise<boolean> {
    return new Promise((resolve) => {
      const words = h("span", {}, "Throw away your unsaved changes?");
      const done = (answer: boolean): void => {
        api.note(null);
        resolve(answer);
      };
      api.note(
        h(
          "div",
          { class: "ide-note-row", role: "alertdialog", "aria-label": "Unsaved changes" },
          icon("warning"),
          words,
          button("Throw them away", () => done(true), { class: "danger ide-btn" }),
          button("Keep editing", () => done(false), { class: "ghost ide-btn" }),
        ),
      );
    });
  }

  async function doRun(): Promise<void> {
    if (!options.run || !runBtn) return;
    if (running) {
      running.abort();
      return;
    }
    const abort = new AbortController();
    running = abort;
    runBtn.classList.add("running");
    runBtn.replaceChildren(icon("stop"), h("span", { class: "btn-label" }, "Stop"));
    runBtn.setAttribute("aria-label", "Stop");
    runBtn.title = "Stop the run";
    editor?.setProblems([]);
    try {
      await panel.running(options.runWords ?? "Running…", options.run(value(), abort, output), abort);
    } finally {
      running = null;
      runBtn.classList.remove("running");
      runBtn.replaceChildren(icon("play"), h("span", { class: "btn-label" }, "Run"));
      runBtn.setAttribute("aria-label", "Run");
      runBtn.title = "Run (F5, Ctrl+Enter)";
    }
  }

  // ----- Monaco -----
  const ready = loadEditors().then((m) => {
    if (disposed) throw new Error("closed");
    const given = options.editor ?? {};
    editorHost.replaceChildren();
    editor = m.createCodeEditor(editorHost, {
      ...given,
      language: options.language,
      value: pending,
      theme: options.theme(),
      keys: options.run ? { ...(given.keys ?? {}), f5: () => void doRun(), ctrlEnter: () => void doRun() } : given.keys,
      intel: given.intel
        ? {
            ...given.intel,
            onLint: (found) => {
              panel.setLint(found);
              given.intel?.onLint?.(found);
            },
          }
        : undefined,
    });
    setFont(fontPx);
    editor.onChange(() => {
      pending = editor!.value();
      drawDirty();
    });
    return editor;
  });
  ready.catch(() => undefined);

  const api: CodeIde = {
    element,
    ready,
    value,
    setValue: (text, clean = false) => {
      if (clean) saved = text;
      pending = text;
      if (editor && editor.value() !== text) editor.replaceText(text);
      drawDirty();
    },
    dirty: () => value() !== saved || extraDirty,
    setExtraDirty: (dirtyNow) => {
      extraDirty = dirtyNow;
      drawDirty();
    },
    markClean: (text) => {
      saved = text;
      drawDirty();
    },
    setName: (name) => {
      nameEl.textContent = name;
    },
    toggleProperties: (shown) => setProps(shown ?? !propsShown),
    setStage: (shown) => {
      if (!stageHost) return;
      stageHost.hidden = !shown;
      editorHost.hidden = shown;
      if (!shown) {
        editor?.layout();
        editor?.focus();
      }
    },
    output,
    showResult: panel.showResult,
    setRunProblems: (list) => editor?.setProblems(list),
    showTab,
    note: (content) => {
      noteHost.replaceChildren(...(content ? [content] : []));
      noteHost.hidden = !content;
      editor?.layout();
    },
    problems: panel.lint,
    run: doRun,
    save: doSave,
    dispose: () => {
      disposed = true;
      editor?.dispose();
    },
  };
  return api;
}
