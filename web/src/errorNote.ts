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
 *   warningNote(parts)          the same note in the warning colour ("Only works on your machine", cancelled work).
 *   showError(host, error, x)   the note at the top of `host`, in place of the one it showed before; returns it.
 *   clearError(host)            the note gone (a retry that worked: it never lingers).
 *   errorToast(error, show)     work with no place on screen (background): a toast with the same words, Show.
 *   errorParts(error)           an ApiError, Error, string or the server's JSON refusal read into the parts.
 *
 * The server's refusal, read loosely (9.5's one shape): {"error" | "message": what, "where": ..., "details" |
 * "traceback": ..., "missing": {...}}; a missing package's refusal brings Install now (missingPackages.ts).
 * Code errors in the Workbench keep the error panel (workbenchErrors.ts), this note's fullest form.
 */

import { ApiError } from "./api";
import { button, h, icon, toast } from "./dom";
import { missingOf, promptInstall } from "./missingPackages";
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

function parsed(message: string): Record<string, unknown> | null {
  if (!message.trim().startsWith("{")) return null;
  try {
    const value = JSON.parse(message) as unknown;
    return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

const text = (value: unknown): string | undefined => (typeof value === "string" && value.trim() ? value.trim() : undefined);

/** The first sentence or line of a long message (the rest goes to Details). */
function firstSentence(message: string): string {
  const line = message.trim().split("\n")[0]!.trim();
  if (line.length <= 240) return line;
  const stop = line.slice(0, 240).lastIndexOf(". ");
  return stop > 40 ? line.slice(0, stop + 1) : `${line.slice(0, 237)}…`;
}

/** An error of any kind read into the note's parts. */
export function errorParts(e: unknown): ErrorParts {
  if (asParts(e)) return e;
  const message = e instanceof Error ? e.message : typeof e === "string" ? e : String(e);
  const said = parsed(message);
  const fixes: ErrorFix[] = [];
  const missing = missingOf(e instanceof Error ? e : said ?? e);
  if (missing) fixes.push({ label: "Install now", icon: "import", run: () => promptInstall(missing, { force: true }) });
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

/** Work with no place on screen: a toast with the same words, and Show to go to the place when there is one. */
export function errorToast(e: unknown, show?: () => void): void {
  const parts = errorParts(e);
  toast(parts.where ? `${parts.what} (${parts.where})` : parts.what, "error", show ? { label: "Show", run: show } : undefined);
}
