/**
 * errorNote.ts: the one error component of every page and window (design principles 9.5). [SHARED]
 *
 * The owner (2026-11-18): "Errors should be presented to users in one uniform way as much as possible."
 *
 *   errorNote(error, extra)     the note, drawn in place: an icon and a word (Error, Warning), what happened in
 *                               one plain sentence, where (the connection, table, file or cell, by name), the fix
 *                               as buttons (Try again, Install now, ...), the source's own message folded behind
 *                               Details with Copy, and Send to the agent. The error token's colour (the warning's
 *                               for a warning), the body text's size.
 *   errorMark(what)             its inline form for a one-line row: the icon, the words, the message in its tip.
 *   warningNote(parts)          the same note in the warning colour ("Only works on your machine", cancelled work).
 *   showError(host, error, x)   the note at the top of `host`, in place of the one it showed before; returns it.
 *   clearError(host)            the note gone (a retry that worked: it never lingers).
 *   errorToast(error, show)     work with no place on screen (background): the same note in a toast, Show.
 *   errorHere(error, extra)     in place where the user's last action was (the row of the control they pressed,
 *                               inside its card, panel, form or dialog); pressing it again takes the note away.
 *   errorParts(error)           an ApiError, Error, string or the server's JSON refusal read into the parts.
 *
 * The server's refusal (9.5's one shape, domain/refusals.py): {"error": what, "where": ..., "fixes": [{label,
 * action: install | set_variable | sign_in | open_settings | try_again, ...}], "details": ...}, read loosely
 * ("message" and "traceback" too); a missing package's refusal brings Install now (missingPackages.ts).
 * Code errors in the Workbench keep the error panel (workbenchErrors.ts), this note's fullest form.
 */

import { ApiError, saidOf } from "./api";
import { button, h, icon, toast, toastNode } from "./dom";
import { missingOf, promptInstall } from "./missingPackages";
import { addVariable } from "./variableLinks";
import { sendToAgent } from "./workbenchAgent";

export interface ErrorFix {
  label: string;
  run: () => unknown;
  icon?: string;
}

export interface ErrorParts {
  /** What happened, in one plain sentence. */
  what: string;
  /** Where: the connection, table, file or cell, by name. */
  where?: string;
  /** The fixes, as buttons (each run once per click; the note stays until the caller clears it). */
  fixes?: ErrorFix[];
  /** The source's own message or the code, folded behind Details (with Copy). */
  details?: string;
  /** "warning" draws it in the warning colour, with Warning for its word. */
  level?: "error" | "warning";
  /** Send to the agent (9.3): on by default for an error, off for a warning. */
  agent?: boolean;
  /** A Close button (default on). */
  dismiss?: boolean;
}

const asParts = (e: unknown): e is ErrorParts => typeof e === "object" && e !== null && !(e instanceof Error) && typeof (e as ErrorParts).what === "string";

const text = (value: unknown): string | undefined => (typeof value === "string" && value.trim() ? value.trim() : undefined);

/** The first sentence or line of a long message (the rest goes to Details). */
function firstSentence(message: string): string {
  const line = message.trim().split("\n")[0]!.trim();
  if (line.length <= 240) return line;
  const stop = line.slice(0, 240).lastIndexOf(". ");
  return stop > 40 ? line.slice(0, stop + 1) : `${line.slice(0, 237)}…`;
}

/** The connection's own page (its card's detail on the Connections page): Sign in and Open its settings. */
function openConnection(name: string): void {
  // By its address (nav.ts): the Connections page's layer opens on the card's detail, as a link to it does.
  void import("./nav").then((nav) => nav.visit(nav.withParams({ open: "connections", at: "detail", type: null, name })));
}

/** A fix the server named (9.5's shape: {label, action, ...}) as a button, or null for one this page cannot do
 *  by itself (Try again: the caller's, since only it knows what to send again). */
function serverFix(fix: unknown, said: Record<string, unknown>, e: unknown): ErrorFix | null {
  if (!fix || typeof fix !== "object") return null;
  const f = fix as Record<string, unknown>;
  const label = text(f.label);
  if (!label) return null;
  const action = text(f.action) ?? (f.command === "variables_set" ? "set_variable" : undefined);
  const missing = missingOf(e instanceof Error ? e : said);
  switch (action) {
    case "install":
      return missing ? { label, icon: "import", run: () => promptInstall(missing, { force: true }) } : null;
    case "set_variable":
      return text(f.name) ? { label, icon: "plus", run: () => addVariable(text(f.name)!) } : null;
    case "sign_in":
    case "open_settings":
      return text(f.connection) ? { label, icon: action === "sign_in" ? "key" : "settings", run: () => openConnection(text(f.connection)!) } : null;
    default:
      return null;
  }
}

/** An error of any kind read into the note's parts: the server's one shape ({error, where, fixes, details};
 *  an ApiError's `said`), an Error, a string. */
export function errorParts(e: unknown): ErrorParts {
  if (asParts(e)) return e;
  const message = e instanceof Error ? e.message : typeof e === "string" ? e : String(e);
  const said = saidOf(e instanceof Error || typeof e === "string" ? e : null) ?? (e && typeof e === "object" ? (e as Record<string, unknown>) : null);
  const fixes: ErrorFix[] = [];
  const named = said && Array.isArray(said.fixes) ? said.fixes : [];
  for (const fix of named) {
    const made = serverFix(fix, said!, e);
    if (made && !fixes.some((f) => f.label === made.label)) fixes.push(made);
  }
  // Answers from before the shape named its fixes: Install now from `missing`, Set it from `missing_variables`.
  const missing = missingOf(e instanceof Error ? e : said ?? e);
  if (missing && !fixes.some((f) => f.label === "Install now")) fixes.push({ label: "Install now", icon: "import", run: () => promptInstall(missing, { force: true }) });
  const unset = said && Array.isArray(said.missing_variables) ? said.missing_variables.filter((n): n is string => typeof n === "string") : [];
  if (!named.length) for (const name of unset) fixes.push({ label: unset.length > 1 ? `Set ${name}` : "Set it", icon: "plus", run: () => addVariable(name) });
  if (said) {
    const what = text(said.error) ?? text(said.message) ?? (missing ? `${missing.packages.join(", ")} is not installed.` : "Something went wrong.");
    const details = text(said.details) ?? text(said.traceback) ?? (what.includes("\n") || what.length > 240 ? what : undefined);
    return { what: firstSentence(what), where: text(said.where), details, fixes };
  }
  const plain = message.trim() || (e instanceof ApiError ? `The server answered ${e.status}.` : "Something went wrong.");
  const what = firstSentence(plain);
  return { what, details: what === plain ? undefined : plain, fixes };
}

async function copy(words: string, pressed: HTMLButtonElement): Promise<void> {
  try {
    await navigator.clipboard.writeText(words);
    toast("Copied");
  } catch {
    pressed.title = "The browser did not allow the copy";
  }
}

/** The note: see the module's comment. `extra` adds to what the error says (a where, a Try again). */
export function errorNote(e: unknown, extra: Partial<ErrorParts> = {}): HTMLElement {
  const read = errorParts(e);
  const parts: ErrorParts = { ...read, ...extra, fixes: [...(extra.fixes ?? []), ...(read.fixes ?? [])] };
  const warning = parts.level === "warning";
  const word = warning ? "Warning" : "Error";
  const note = h("div", { class: `error-note${warning ? " warning" : ""}`, role: warning ? "status" : "alert", "data-level": warning ? "warning" : "error" });
  const head = h(
    "div",
    { class: "error-note-head" },
    h("span", { class: "error-note-icon", "aria-hidden": "true" }, icon(warning ? "warning" : "problem")),
    h("strong", { class: "error-note-word" }, word),
    h("span", { class: "error-note-what" }, parts.what),
  );
  if (parts.dismiss !== false) {
    head.append(button("Close", () => note.remove(), { icon: "close", iconOnly: true, class: "ghost small error-note-close" }));
  }
  note.append(head);
  if (parts.where) note.append(h("div", { class: "error-note-where" }, parts.where));
  const actions = h("div", { class: "error-note-actions" });
  for (const fix of parts.fixes ?? []) {
    actions.append(button(fix.label, () => void fix.run(), { icon: fix.icon, class: "small error-note-fix" }));
  }
  const all = [parts.what, parts.where ? `Where: ${parts.where}` : "", parts.details ?? ""].filter(Boolean).join("\n\n");
  if (parts.agent ?? !warning) {
    actions.append(button("Send to the agent", () => sendToAgent({ kind: "error", title: parts.where ?? document.title, text: all }), { icon: "agent", class: "small ghost error-note-agent" }));
  }
  if (parts.details) {
    const copyButton = button("Copy", (event) => void copy(all, event.currentTarget as HTMLButtonElement), { icon: "copy", class: "small ghost error-note-copy" });
    note.append(
      h(
        "details",
        { class: "error-note-details" },
        h("summary", {}, "Details"),
        h("pre", { class: "error-note-text mono" }, parts.details),
        copyButton,
      ),
    );
  }
  if (actions.childElementCount) note.append(actions);
  return note;
}

/** The note's inline form, for a row that must stay on one line (a card's status, a step's problem, a tree's
 *  row): the same icon and colour, its word for screen readers, the words, the whole message in its tip. */
export function errorMark(what: string, options: { title?: string; level?: "error" | "warning"; iconOnly?: boolean } = {}): HTMLElement {
  const warning = options.level === "warning";
  const word = warning ? "Warning" : "Error";
  return h(
    "span",
    { class: `error-mark${warning ? " warning" : ""}`, title: options.title || what, "data-level": warning ? "warning" : "error", role: options.iconOnly ? "img" : null, "aria-label": options.iconOnly ? `${word}: ${what}` : null },
    h("span", { class: "error-note-icon", "aria-hidden": "true" }, icon(warning ? "warning" : "problem")),
    options.iconOnly ? null : h("span", { class: "visually-hidden" }, `${word}: `),
    options.iconOnly ? null : h("span", { class: "error-mark-what" }, what),
  );
}

/** The note in the warning colour. */
export const warningNote = (parts: ErrorParts): HTMLElement => errorNote({ ...parts, level: "warning" });

/** The note at the top of `host`, replacing the one it showed before. */
export function showError(host: HTMLElement, e: unknown, extra: Partial<ErrorParts> = {}): HTMLElement {
  clearError(host);
  const note = errorNote(e, extra);
  host.prepend(note);
  return note;
}

/** The note `host` shows, gone. */
export function clearError(host: HTMLElement): void {
  host.querySelectorAll(":scope > .error-note").forEach((old) => old.remove());
}

/** Work with no place on screen (something in the background): the same note in a toast, with Show to go to the
 *  place when there is one. */
export function errorToast(e: unknown, show?: () => void, extra: Partial<ErrorParts> = {}): void {
  const parts = errorParts(e);
  let item: HTMLElement | null = null;
  const fixes: ErrorFix[] = show ? [{ label: "Show", icon: "forward", run: () => { item?.remove(); show(); } }] : [];
  const note = errorNote(parts, { ...extra, fixes: [...fixes, ...(extra.fixes ?? [])] });
  // The note's own Close takes the toast with it.
  note.querySelector(".error-note-close")?.addEventListener("click", () => item?.remove());
  item = toastNode(note, `${parts.what}\n${parts.where ?? ""}`);
}

// ===== in place, where the action happened =====
//
// errorHere(e) puts the note where the user's last action was: under the row of the button, box or menu's
// opener they pressed, inside the part of the page that holds it (its card, panel, pane, section, form, cell
// or dialog). A second press of that control takes its note away first, so a retry that works leaves none
// (9.5: "it goes when it is fixed"). With no such place on screen (the control is gone, or the work was the
// page's own), it is errorToast.

let lastAction: { element: Element; at: number } | null = null;

const ACTING = "button, a, input, select, textarea, summary, [role=menuitem], [role=option], [role=tab], [role=button], [tabindex], [contenteditable=true]";

/** A part of the page an error belongs to: a dialog's body, a form, a card, panel, pane, section, cell or
 *  page by its class, a landmark, or a place marked data-error-host. */
const PART = /(^|[-_])(card|panel|pane|section|cell|page|body|form|detail|details|group|tab|block)$/;

function isPart(element: Element): boolean {
  if (element instanceof HTMLDialogElement || element.matches("form, section, article, aside, main, [role=tabpanel], [role=region], [role=dialog], [data-error-host]")) return true;
  return [...element.classList].some((c) => PART.test(c));
}

function heard(event: Event): void {
  const target = event.target instanceof Element ? event.target : null;
  const element = target?.closest(ACTING) ?? target;
  if (!element || element.closest(".error-note, .toasts")) return;
  // A menu's item: the work is the menu's opener's (the button or the right-clicked row), which stays on screen.
  if (element.closest("[role=menu], .menu") && lastAction?.element.isConnected) {
    lastAction = { element: lastAction.element, at: Date.now() };
    return;
  }
  // Pressing the same control again: its last note goes first (a retry that works leaves none).
  document.querySelectorAll<HTMLElement>(".error-note[data-from]").forEach((note) => {
    if (fromOf.get(note) === element) note.remove();
  });
  lastAction = { element, at: Date.now() };
}

const fromOf = new WeakMap<HTMLElement, Element>();
let listening = false;

function listen(): void {
  if (listening || typeof document === "undefined") return;
  listening = true;
  document.addEventListener("pointerdown", heard, true);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " " || event.ctrlKey || event.metaKey) heard(event);
  }, true);
}
listen();

/** A page's bars (the ribbon, the title and tab rows, a status bar, the rail, a toolbar): no room for a note
 *  inside, so one for a control there floats just under the bar, beside the control. */
const BARS = ".ribbon, .app-row, .titlebar, .tabbar, .tabs-row, .statusbar, .wb-top, .cat-top, .nav-rail, [role=toolbar], [role=menubar], [role=tablist]";

/** The outermost bar `from` sits in, or null. */
function barOf(from: Element): HTMLElement | null {
  let bar: HTMLElement | null = null;
  for (let at = from.closest<HTMLElement>(BARS); at; at = at.parentElement?.closest<HTMLElement>(BARS) ?? null) bar = at;
  return bar;
}

/** The note floating under `bar`, lined up with `control` (one at a time). */
function floatUnder(bar: HTMLElement, control: Element, note: HTMLElement): void {
  document.querySelectorAll(".error-note.floating").forEach((old) => old.remove());
  note.classList.add("floating");
  ([...document.querySelectorAll<HTMLDialogElement>("dialog[open]")].pop() ?? document.body).append(note);
  const under = bar.getBoundingClientRect();
  const at = control.getBoundingClientRect();
  const width = note.offsetWidth;
  const atBottom = under.top > window.innerHeight / 2; // a status bar: above it
  note.style.left = `${Math.max(8, Math.min(at.left, window.innerWidth - width - 8))}px`;
  if (atBottom) note.style.bottom = `${Math.max(8, window.innerHeight - under.top + 6)}px`;
  else note.style.top = `${Math.max(8, under.bottom + 6)}px`;
}

/** Where a note for an action on `from` goes: the part that holds it, and the child of that part to put the
 *  note after (the row of the control), or null to put it first. */
function placeFor(from: Element): { part: HTMLElement; after: Element | null } | null {
  let child: Element = from;
  for (let at = from.parentElement; at && at !== document.body && at !== document.documentElement; at = at.parentElement) {
    if (isPart(at)) {
      if (at instanceof HTMLDialogElement) {
        // A dialog: its body, the note at the body's foot (just above the buttons) unless the control is in it.
        const body = at.querySelector<HTMLElement>(":scope > .dialog-body");
        if (body && !body.contains(from)) return { part: body, after: body.lastElementChild };
      }
      return { part: at as HTMLElement, after: child };
    }
    child = at;
  }
  return null;
}

/** Several problems from one action as one note, in place: the one itself, or `many` with each in Details. */
export function problemsHere(items: string[], many: string, extra: Partial<ErrorParts> = {}): void {
  if (!items.length) return;
  errorHere({ what: items.length === 1 ? items[0]! : many, details: items.length > 1 ? items.join("\n") : undefined }, extra);
}

/** How long after the user's press a failure still belongs to it (a slow Test, a sign-in): later than this the
 *  work is taken as the page's own, and the note is a toast. */
const ACTION_MS = 3 * 60_000;

/** The note in place where the user's last action was (see above), else errorToast. `from` names the control
 *  when the caller has it. */
export function errorHere(e: unknown, extra: Partial<ErrorParts> = {}, from?: Element | null): void {
  const recent = lastAction && Date.now() - lastAction.at < ACTION_MS ? lastAction.element : null;
  const control = from ?? recent;
  if (!control || !control.isConnected) {
    errorToast(e, undefined, extra);
    return;
  }
  const bar = barOf(control);
  if (bar) {
    const floating = errorNote(e, extra);
    floating.dataset.from = "";
    fromOf.set(floating, control);
    floatUnder(bar, control, floating);
    return;
  }
  const place = placeFor(control);
  if (!place) {
    errorToast(e, undefined, extra);
    return;
  }
  const note = errorNote(e, extra);
  note.dataset.from = "";
  fromOf.set(note, control);
  // One note per place and control: the one it showed before goes.
  place.part.querySelectorAll<HTMLElement>(":scope > .error-note[data-from]").forEach((old) => {
    if (fromOf.get(old) === control) old.remove();
  });
  if (place.after && place.after.parentElement === place.part) place.after.after(note);
  else place.part.prepend(note);
  note.scrollIntoView?.({ block: "nearest" });
}
