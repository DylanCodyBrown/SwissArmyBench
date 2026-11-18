/**
 * inlineCompletion.ts: ghost text in the editors, from whatever provider the backend declares. [SHARED]
 *
 * The mode (GET /app/mode, modes.ts) carries `inline_completion`: the providers an extension that is on
 * offers, as data ({id, name, languages, complete, cancel, event, status, toggle}: routes). Nothing here
 * names a provider: the status bar draws the name the backend gives.
 *
 *   [ASK]     askInline: the document and the cursor posted to the provider's `complete` route; Monaco's
 *             cancellation aborts the fetch and posts `cancel` with the same request id
 *   [TELL]    tellInline: an item shown, accepted, partly accepted (the length from its start), to `event`
 *   [STATUS]  inlineStatus(): the status bar's "Completions: <name> · on/off" item; a click turns it on or
 *             off (`toggle`); asked again on the `inline_completion_changed` notice and when the mode changes
 *
 * ROUTING: the provider's routes, as declared  ·  notices inline_completion_changed
 */
import { api, onNotice } from "./api";
import { h } from "./dom";
import { activeMode, type InlineProvider, onMode, whenMode } from "./modes";

export type { InlineProvider };

/** What an editor says of the document it edits: a script's text, or a notebook's code cells and the one
 *  being edited (the cell's text is its editor's). */
export type InlineDocument =
  | { key: string; name: string; kind: "script"; language: string; text: string }
  | { key: string; name: string; kind: "notebook"; cells: { id: string; text: string; language: string }[]; cell: string };

export interface InlineItem {
  id: string;
  text: string;
  range: { start: { line: number; character: number }; end: { line: number; character: number } } | null;
}

interface InlineStatus {
  name: string;
  on: boolean;
  ready: boolean;
  words: string;
}

/** The provider for a language in the open project's mode, if any. */
export function inlineProvider(language: string): InlineProvider | null {
  const listed = activeMode().mode.inline_completion ?? [];
  return listed.find((p) => p.languages.includes(language)) ?? null;
}

let asked = 0;

/** Ghost text at the cursor (0-based line, UTF-16 character), or none. An abort cancels it on the server. */
export async function askInline(
  provider: InlineProvider,
  document: InlineDocument,
  position: { line: number; character: number },
  format: { tabSize: number; insertSpaces: boolean },
  signal: AbortSignal,
): Promise<InlineItem[]> {
  const request = `i${++asked}`;
  const cancel = (): void => {
    if (provider.cancel) void api(provider.cancel, "POST", { request }).catch(() => undefined);
  };
  signal.addEventListener("abort", cancel, { once: true });
  try {
    const answer = await api<{ items?: InlineItem[] }>(provider.complete, "POST", { request, document, position, tab_size: format.tabSize, insert_spaces: format.insertSpaces }, signal);
    return signal.aborted ? [] : (answer.items ?? []);
  } catch {
    return [];
  } finally {
    signal.removeEventListener("abort", cancel);
  }
}

/** What an editor is handed (lazy/codeEditor.ts is a bundle of its own, so it is given these rather than
 *  importing them): ask for a language's ghost text (null: no provider for it), tell what became of an item. */
export interface InlineSource {
  ask(language: string, position: { line: number; character: number }, format: { tabSize: number; insertSpaces: boolean }, signal: AbortSignal): Promise<InlineItem[]> | null;
  tell(language: string, id: string, kind: "shown" | "accepted" | "partial", length?: number): void;
}

/** An editor's source of ghost text over the document it edits (null from `document`: none for now). */
export function inlineSource(document: () => InlineDocument | null): InlineSource {
  return {
    ask: (language, position, format, signal) => {
      const provider = inlineProvider(language);
      const doc = provider ? document() : null;
      return provider && doc ? askInline(provider, doc, position, format, signal) : null;
    },
    tell: (language, id, kind, length) => {
      const provider = inlineProvider(language);
      if (provider) tellInline(provider, id, kind, length);
    },
  };
}

/** What the editor did with an item, for the provider (its telemetry and its own bookkeeping). */
export function tellInline(provider: InlineProvider, id: string, kind: "shown" | "accepted" | "partial", length?: number): void {
  if (!provider.event) return;
  void api(provider.event, "POST", { id, kind, length }).catch(() => undefined);
}

// ===== the status bar's item =====

const statusItems: HTMLButtonElement[] = [];

async function drawStatus(): Promise<void> {
  await whenMode();
  const provider = (activeMode().mode.inline_completion ?? [])[0] ?? null;
  for (const item of statusItems) item.hidden = !provider;
  if (!provider?.status) return;
  let said: InlineStatus;
  try {
    said = await api<InlineStatus>(provider.status);
  } catch {
    return;
  }
  for (const item of statusItems) {
    item.textContent = `Completions: ${said.name} · ${said.words}`;
    item.dataset.on = String(said.on);
    item.dataset.ready = String(said.ready);
    item.setAttribute("aria-pressed", String(said.on));
    item.title = said.on ? `Turn ${said.name} off` : `Turn ${said.name} on`;
    item.onclick = () => {
      if (!provider.toggle) return;
      // What the item shows now, turned over (a later answer may have drawn it since this one).
      void api(provider.toggle, "POST", { on: item.dataset.on !== "true" }).then(() => drawStatus(), () => drawStatus());
    };
  }
}

onNotice((n) => {
  // Its own notice, and a project opened, closed or marked private (its word follows).
  if (n.type === "inline_completion_changed" || n.type === "project_changed") void drawStatus();
});
onMode(() => void drawStatus());

/** The status bar's item (hidden while no provider is declared). */
export function inlineStatus(): HTMLButtonElement {
  const item = h("button", { type: "button", class: "btn ghost inline-status", hidden: true }) as HTMLButtonElement;
  statusItems.push(item);
  void drawStatus();
  return item;
}
