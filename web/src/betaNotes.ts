/**
 * betaNotes.ts: beta mode on every page: right-click anything, "Leave a note…"; page errors to the beta
 * log; the "Beta" mark. [SHARED]
 *
 * The owner (2026-11-15): "give me a temporary ability to right click anything in the app and leave a
 * note on that visual that saves to the log so you can trace what was the issue". Beta mode is one
 * switch on the server (services/beta_log.py), kept across restarts; while it is off this module has no
 * listener on the page and the item is nowhere.
 *
 *   [RIGHT-CLICK]  an app menu (dom.showMenu, the Workbench's openMenu, its small context menus) gets
 *                  "Leave a note…" at its end (menuExtras); text boxes, a text selection and the
 *                  editors keep their own menu (Monaco adds the item to its own: lazy/codeEditor.ts);
 *                  anywhere else a small menu with only the item
 *   [NOTE FORM]    what is wrong; the element outlined; "Attach a picture of this window", off: the one
 *                  way data reaches the log, on the user's tick
 *   [SAVED]        the page and window, the element (role, name, a button's words, never a cell's; its
 *                  CSS path; its box), the panels and tab kinds, the last 20 actions by name, the last
 *                  page errors' ids; the server adds the last server errors' ids, the time, the version
 *   [PAGE ERRORS]  window.onerror and unhandled rejections, at most 20 a minute
 *   [BETA MARK]    in the status bar while on: its menu has Leave a note…, Export beta log…, Turn off
 *
 * ROUTING: GET/PUT /beta, POST /beta/notes, POST /beta/page-errors, POST /beta/export, DELETE /beta/log;
 *          the `beta_changed` notice
 */
import { api, onNotice } from "./api";
import { button, h, icon, openDialog, setMenuExtras, showMenu, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import type { Command } from "./workbenchCommands";
import { errorHere } from "./errorNote";

export interface BetaState {
  on: boolean;
  set_by: "default" | "settings" | "environment";
  variable: string;
  files: number;
  bytes: number;
  pictures: number;
}

interface PageContext {
  /** The window's kind: "main", "steps", "keys", "popout". */
  window: string;
  /** The kinds of the tabs open (never their names): "table", "sandbox", "notebook", "app". */
  tabs: () => string[];
}

let page = "";
let context: PageContext = { window: "main", tabs: () => [] };
let state: BetaState | null = null;
const listeners: ((on: boolean) => void)[] = [];
const actions: string[] = [];
const pageErrors: string[] = [];
let lastContext: { target: Element; x: number; y: number; at: number } | null = null;
let listening = false;
let errorTimes: number[] = [];

export const betaOn = (): boolean => state?.on === true;
/** Called when beta mode goes on or off (here or in another window). */
export function onBeta(listener: (on: boolean) => void): void {
  listeners.push(listener);
}

// ===== the last actions, by name =====

/** An action by its command's name ("steps.add", "canvas.play"); only while beta mode is on. */
export function recordAction(name: string): void {
  if (!betaOn() || !name) return;
  actions.push(name.slice(0, 80));
  if (actions.length > 20) actions.shift();
}

const clicked = (event: MouseEvent): void => {
  const target = event.target instanceof Element ? event.target.closest("button, [role=menuitem], [role=tab], a[href]") : null;
  if (!target || target.closest(".beta-note-form")) return;
  const words = (target.getAttribute("aria-label") || target.getAttribute("title") || target.textContent || "").trim().replace(/\s+/g, " ");
  if (words) recordAction(`click:${words.slice(0, 60)}`);
};

// ===== the element, described without its data =====

const DATA_PLACES = ".ag-cell, .wb-output, .monaco-editor, pre, td, textarea, input, select, [contenteditable], .value-viewer, .sab-card-body, .wb-err";
const WORDY = "button, [role=button], [role=tab], [role=menuitem], [role=columnheader], .ag-header-cell, label, legend, summary, h1, h2, h3, h4, th";
const IMPLICIT: Record<string, string> = { BUTTON: "button", A: "link", INPUT: "textbox", TEXTAREA: "textbox", SELECT: "combobox", SUMMARY: "button", H1: "heading", H2: "heading", H3: "heading", H4: "heading", TABLE: "table", DIALOG: "dialog" };

function step(el: Element): string {
  let part = el.tagName.toLowerCase();
  if (el.id && /^[A-Za-z][\w-]{0,40}$/.test(el.id) && !/\d{3,}/.test(el.id)) part += `#${el.id}`;
  const classes = [...el.classList].filter((c) => /^[A-Za-z][\w-]{0,40}$/.test(c) && !/\d{3,}/.test(c)).slice(0, 3);
  if (classes.length) part += `.${classes.join(".")}`;
  const column = el.getAttribute("col-id");
  if (column) part += `[col-id="${column.slice(0, 60)}"]`;
  return part;
}

/** The CSS path to `el` through the app's own ids and classes: the last six steps. */
export function cssPath(el: Element): string {
  const parts: string[] = [];
  for (let at: Element | null = el; at && at !== document.body && parts.length < 6; at = at.parentElement) parts.unshift(step(at));
  return parts.join(" > ");
}

export interface ElementInfo {
  tag: string;
  role: string;
  name: string;
  text: string;
  path: string;
  box: { x: number; y: number; w: number; h: number };
}

/** What was right-clicked, as a note keeps it: no cell's or editor's text, ever. */
export function describe(el: Element): ElementInfo {
  const target = el.closest(`${WORDY}, [role=gridcell], .ag-cell, [aria-label], [title], [role]`) ?? el;
  const data = target.closest(DATA_PLACES) !== null;
  const wordy = target.matches(WORDY);
  const name = data ? "" : target.getAttribute("aria-label") || target.getAttribute("title") || "";
  const text = data || !wordy ? "" : (target.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 80);
  const box = target.getBoundingClientRect();
  return {
    tag: target.tagName.toLowerCase(),
    role: target.getAttribute("role") ?? IMPLICIT[target.tagName] ?? (target.classList.contains("ag-cell") ? "gridcell" : ""),
    name: name.slice(0, 80),
    text,
    path: cssPath(target),
    box: { x: Math.round(box.left), y: Math.round(box.top), w: Math.round(box.width), h: Math.round(box.height) },
  };
}

const shortName = (info: ElementInfo): string => {
  const what = info.role ? info.role.charAt(0).toUpperCase() + info.role.slice(1) : info.tag;
  const words = info.name || info.text;
  return words ? `${what}: ${words}` : what;
};

// ===== right-click =====

const recent = (): typeof lastContext => (lastContext && performance.now() - lastContext.at < 800 ? lastContext : null);

/** "Leave a note…" for a menu being drawn now from a right-click (nothing for a drop-down's button). */
function extras(): { icon: string; label: string; run: () => void }[] {
  const found = recent();
  if (!betaOn() || !found) return [];
  lastContext = null;
  const target = found.target;
  return [{ icon: "edit", label: "Leave a note…", run: () => openNote(target) }];
}

const editable = (el: Element): boolean => el.closest("input, textarea, select, [contenteditable=''], [contenteditable=true], .monaco-editor") !== null;

// A left click after a right-click: that right-click is over (a drop-down opened now is not its menu).
const pressed = (event: MouseEvent): void => {
  if (event.button === 0) lastContext = null;
};

const noticed = (event: MouseEvent): void => {
  if (event.target instanceof Element) lastContext = { target: event.target, x: event.clientX, y: event.clientY, at: performance.now() };
};

/** Where no app menu answered: a small menu with only the item. Text boxes, editors and selected text
 * keep the browser's own menu (copy and paste). */
const fallback = (event: MouseEvent): void => {
  if (event.defaultPrevented || !(event.target instanceof Element)) return;
  const target = event.target;
  if (editable(target) || target.closest(".beta-note-form") || (window.getSelection()?.toString() ?? "") !== "") return;
  event.preventDefault();
  showMenu(event.clientX, event.clientY, shortName(describe(target)), []);
};

// ===== page errors =====

// The browser's own notice that a resize took two frames: not an error of the app's.
const BENIGN = /^ResizeObserver loop/;

function reportError(kind: "error" | "rejection", message: string, stack: string): void {
  if (BENIGN.test(message)) return;
  const now = Date.now();
  errorTimes = errorTimes.filter((t) => now - t < 60_000);
  if (errorTimes.length >= 20) return;
  errorTimes.push(now);
  void api<{ id: string | null }>("/beta/page-errors", "POST", { message: message.slice(0, 2000), stack: stack.slice(0, 8000), page, window: context.window, kind })
    .then((answer) => {
      if (!answer.id) return;
      pageErrors.push(answer.id);
      if (pageErrors.length > 5) pageErrors.shift();
    })
    .catch(() => undefined);
}

const onError = (event: ErrorEvent): void => {
  const error = event.error as Error | undefined;
  reportError("error", error?.message ?? event.message ?? "Error", error?.stack ?? `    at ? (${event.filename}:${event.lineno}:${event.colno})`);
};

const onRejection = (event: PromiseRejectionEvent): void => {
  const reason = event.reason as Error | string | undefined;
  reportError("rejection", typeof reason === "string" ? reason : reason?.message ?? "Unhandled rejection", typeof reason === "object" ? reason?.stack ?? "" : "");
};

// ===== on and off =====

interface NoteHook {
  on: () => boolean;
  open: (target: Element) => void;
}

function listen(on: boolean): void {
  if (on === listening) return;
  listening = on;
  const way = on ? "addEventListener" : "removeEventListener";
  window[way]("contextmenu", noticed as EventListener, true);
  window[way]("contextmenu", fallback as EventListener);
  window[way]("click", clicked as EventListener, true);
  window[way]("mousedown", pressed as EventListener, true);
  window[way]("error", onError as EventListener);
  window[way]("unhandledrejection", onRejection as EventListener);
  setMenuExtras(on ? extras : null);
  // The editors (another bundle) read this hook to show their own "Leave a note…" (lazy/codeEditor.ts).
  (globalThis as { sabLeaveNote?: NoteHook }).sabLeaveNote = on ? { on: betaOn, open: (target) => openNote(target) } : undefined;
  if (!on) {
    actions.length = 0;
    lastContext = null;
  }
}

function take(next: BetaState): void {
  const was = betaOn();
  state = next;
  listen(next.on);
  document.body.classList.toggle("beta-on", next.on);
  if (was !== next.on) for (const listener of listeners) listener(next.on);
}

/** Start beta mode's part of this page. `page`: "grid", "workbench", "catalog". */
export function mountBeta(pageName: string, pageContext: Partial<PageContext> = {}): void {
  page = pageName;
  context = { ...context, ...pageContext };
  void loadBeta();
  onNotice((notice) => {
    if (notice.type === "beta_changed") void loadBeta();
  });
}

export async function loadBeta(): Promise<BetaState | null> {
  try {
    take(await api<BetaState>("/beta"));
  } catch {
    /* an older server: no beta mode */
  }
  return state;
}

export async function setBeta(on: boolean): Promise<void> {
  try {
    take(await api<BetaState>("/beta", "PUT", { on }));
    toast(on ? "Beta mode on" : "Beta mode off");
  } catch (e) {
    errorHere(e);
  }
}

// ===== export and clear =====

export async function exportBetaLog(): Promise<void> {
  const path = await chooseFile({ title: "Export beta log", mode: "save", name: "beta-log.zip" });
  if (!path) return;
  try {
    const made = await api<{ path: string }>("/beta/export", "POST", { path: path.toLowerCase().endsWith(".zip") ? path : `${path}.zip` });
    toast(`Saved to ${made.path}`); // the whole path: the chooser starts in the app's own folder, easy to lose
  } catch (e) {
    errorHere(e);
  }
}

export function clearBetaLog(): void {
  const { body, foot, close } = openDialog("Clear the beta log");
  body.append(h("p", {}, "Every log file, note and picture goes."));
  foot.append(
    button("Cancel", close, { class: "ghost" }),
    button("Clear", () => {
      close();
      void api("/beta/log", "DELETE").then(() => {
        toast("Cleared");
        void loadBeta();
      }, (e: Error) => errorHere(e));
    }, { icon: "trash", class: "danger" }),
  );
}

// ===== the note form =====

async function picture(skip: Element[]): Promise<string> {
  const { toPng } = await import("html-to-image");
  return toPng(document.body, {
    width: window.innerWidth,
    height: window.innerHeight,
    pixelRatio: 1,
    cacheBust: false,
    backgroundColor: getComputedStyle(document.body).backgroundColor,
    filter: (node) => !(node instanceof Element) || !skip.some((s) => s === node),
  });
}

/** The note form for `target`, outlined while the form is open. */
export function openNote(target: Element): void {
  if (!betaOn()) return;
  const info = describe(target);
  const { dialog, body, foot, close } = openDialog("Leave a note");
  dialog.classList.add("beta-note-form");
  const outline = h("div", { class: "beta-outline", "aria-hidden": "true", style: { left: `${info.box.x - 3}px`, top: `${info.box.y - 3}px`, width: `${info.box.w + 6}px`, height: `${info.box.h + 6}px` } });
  dialog.append(outline);
  const text = h("textarea", { rows: 5, class: "beta-note-text", placeholder: "What is wrong", "aria-label": "What is wrong" }) as HTMLTextAreaElement;
  const attach = h("input", { type: "checkbox", class: "beta-note-picture" }) as HTMLInputElement;
  body.append(
    h("p", { class: "hint beta-note-where" }, shortName(info)),
    text,
    h("label", { class: "check" }, attach, "Attach a picture of this window", h("span", { class: "hint" }, " (the picture shows your data)")),
  );
  const save = async (): Promise<void> => {
    if (!text.value.trim()) {
      text.focus();
      return;
    }
    const sent: Record<string, unknown> = {
      text: text.value,
      page,
      window: context.window,
      element: info,
      tabs: context.tabs(),
      actions: [...actions],
      page_errors: [...pageErrors],
      viewport: { w: window.innerWidth, h: window.innerHeight },
    };
    try {
      if (attach.checked) {
        dialog.style.visibility = "hidden";
        sent.attach_picture = true;
        sent.picture = await picture([dialog]).finally(() => (dialog.style.visibility = ""));
      }
      await api("/beta/notes", "POST", sent);
      close();
      toast("Saved");
    } catch (e) {
      errorHere(e);
    }
  };
  text.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void save();
    }
  });
  foot.append(button("Cancel", close, { class: "ghost" }), button("Save", () => void save(), { icon: "save", class: "primary" }));
  setTimeout(() => text.focus(), 0);
}

// ===== the mark, the commands =====

/** "Beta" in the status bar while beta mode is on; its menu: Leave a note…, Export beta log…, Turn off. */
export function betaMark(): HTMLElement {
  const mark = h("button", { type: "button", class: "beta-mark", title: "Beta mode: recording errors and notes", hidden: !betaOn() }, "Beta");
  mark.addEventListener("click", () => {
    const box = mark.getBoundingClientRect();
    showMenu(box.left, box.top - 8, "Beta mode", [
      ["edit", "Leave a note…", () => openNote(document.body)],
      ["export", "Export beta log…", () => void exportBetaLog()],
      ["exclude", "Turn off beta mode", () => void setBeta(false)],
    ]);
  });
  onBeta((on) => (mark.hidden = !on));
  return mark;
}

/** The palette's and the agent's commands (the Workbench's registry, the grid page's list). */
export function betaCommands(): Command[] {
  const locked = (): boolean => state?.set_by === "environment";
  const why = (): string => `${state?.variable ?? "SWISSARMYBENCH_BETA"} decides it for this server`;
  return [
    { id: "app.betaOn", group: "Application", title: "Turn beta mode on", when: () => !betaOn() && !locked(), whyNot: "it is on, or the environment decides it", run: () => setBeta(true) },
    { id: "app.betaOff", group: "Application", title: "Turn beta mode off", when: () => betaOn() && !locked(), whyNot: locked() ? why() : "it is off", run: () => setBeta(false) },
    { id: "app.leaveNote", group: "Application", title: "Leave a note…", when: betaOn, whyNot: "beta mode is off", run: () => openNote(document.body) },
    { id: "app.exportBetaLog", group: "Application", title: "Export beta log…", run: () => exportBetaLog() },
    { id: "app.clearBetaLog", group: "Application", title: "Clear the beta log…", run: () => clearBetaLog() },
  ];
}

/** Settings' Beta section: the switch, Export beta log…, Clear the log (both there when it is off). */
export function betaSection(): HTMLElement {
  const box = h("input", { type: "checkbox", class: "beta-switch", checked: betaOn() }) as HTMLInputElement;
  const draw = (): void => {
    box.checked = betaOn();
    box.disabled = state?.set_by === "environment";
    box.title = box.disabled ? `${state?.variable} decides it for this server` : "";
  };
  box.addEventListener("change", () => void setBeta(box.checked).then(draw));
  void loadBeta().then(draw);
  onBeta(draw);
  return h(
    "fieldset",
    { class: "fieldset beta-fieldset" },
    h("legend", {}, icon("edit"), "Beta"),
    h("label", { class: "check" }, box, "Beta mode"),
    h("div", { class: "beta-actions" }, button("Export beta log…", () => void exportBetaLog(), { icon: "export" }), button("Clear the log", () => clearBetaLog(), { icon: "trash", class: "danger" })),
  );
}
