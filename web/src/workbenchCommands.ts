/**
 * workbenchCommands.ts: every action of the Workbench window, by one name. [FUNCTION + WIRE]
 *
 * One list feeds three doors, so they never drift apart (the review's advice, 2026-11-14):
 *   the PALETTE      Ctrl+Shift+P: type to filter, Enter runs; each command shows its keys
 *   the KEYS         the shortcuts named in the list (the page's keydown handler calls them)
 *   the AGENT        the MCP's workbench_window tool sends a command's id and arguments; the window runs
 *                    it and answers (the golden rule: whatever the user can do here, the agent can)
 *
 * ROUTING: the `workbench_command` notice {id, command, args} -> run -> POST /workbench/window/{id}
 *          with {result} or {error}
 */
import { api } from "./api";
import { recordAction } from "./betaNotes";
import { h } from "./dom";
import { areaOfCommand, gated } from "./gates";

export interface Command {
  /** The name the agent uses: "run.file", "cell.insertBelow". */
  id: string;
  /** What the palette shows: "Run the file". */
  title: string;
  group: string;
  /** The keys, as shown ("Ctrl+Enter"). */
  keys?: string;
  /** What `args` it takes, for the agent ("index: a cell, from 0"). */
  args?: string;
  /** Whether it can run now (the palette greys it; the agent is told why not). */
  when?: () => boolean;
  /** What to say when it cannot run now. */
  whyNot?: string;
  /** The area it belongs to, for a project type's gates (gates.ts areaOfCommand finds the base's own). */
  area?: string;
  /** For the agent only (a read the user sees on screen anyway): left out of the palette. */
  agentOnly?: boolean;
  /** `from.agent`: the agent asked (workbench_window), so what writes the user's rows to disk is sent
   * as the agent's request, and the server asks the user first (an export). */
  run: (args: Record<string, unknown>, from: { agent: boolean }) => unknown;
}

const registry = new Map<string, Command>();
// Commands worked out when they are asked for (the grid page's: its buttons and tabs as they stand).
let source: () => Command[] = () => [];

/** A page whose commands follow what is on screen gives them here, read each time the list is. */
export function setCommandSource(found: () => Command[]): void {
  source = found;
}

export function registerCommands(list: Command[]): void {
  for (const c of list) registry.set(c.id, c);
}

export function allCommands(): Command[] {
  return [...registry.values(), ...source()];
}

/** Run a command by its id (the palette, a key, the agent). */
export async function runCommand(id: string, args: Record<string, unknown> = {}, agent = false): Promise<unknown> {
  const command = registry.get(id) ?? source().find((c) => c.id === id);
  if (!command) throw new Error(`No command "${id}". The command "commands" lists them.`);
  if (command.when && !command.when()) throw new Error(`"${command.title}" cannot run now: ${command.whyNot ?? "it does not apply to what is open"}.`);
  // A feature this project's type keeps closed: its one line instead (the agent's tools stay open).
  if (!agent && gated(command.area ?? areaOfCommand(id))) return undefined;
  recordAction(agent ? `agent:${id}` : id);
  return command.run(args, { agent });
}

/** Where the agent's command happened: the front document and its selected cell (the Session page's link). */
export interface Place {
  path?: string | null;
  title?: string | null;
  cell?: number | null;
}
let placeOf: () => Place = () => ({});
let ranForAgent: (command: string, wasBusy: boolean) => void = () => undefined;
let busyNow: () => boolean = () => false;

/** The Workbench page: where the front document is, and what follows an agent's command (Follow the
 *  agent: the changed cell scrolled to and pulsed, unless the user was typing). */
export function setAgentHooks(hooks: { place: () => Place; ran: (command: string, wasBusy: boolean) => void; busy: () => boolean }): void {
  placeOf = hooks.place;
  ranForAgent = hooks.ran;
  busyNow = hooks.busy;
}

/** The agent's request (a `workbench_command` notice): run it here, answer the server. */
export async function answerAgent(notice: { id?: string; command?: string; args?: Record<string, unknown> }): Promise<void> {
  if (!notice.id || !notice.command) return;
  let body: { result?: unknown; error?: string; place?: Place };
  const wasBusy = busyNow();
  try {
    const result = await runCommand(notice.command, notice.args ?? {}, true);
    body = { result: result === undefined ? null : result, place: placeOf() };
    ranForAgent(notice.command, wasBusy);
  } catch (e) {
    body = { error: (e as Error).message };
  }
  await api(`/workbench/window/${encodeURIComponent(notice.id)}`, "POST", body).catch(() => undefined);
}

// ===== recently used: the palette lists them first (this browser's convenience only) =====

const RECENT_KEY = "sab.palette.recent";
const RECENT_MAX = 8;

function recentIds(): string[] {
  try {
    const kept = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]") as unknown;
    return Array.isArray(kept) ? kept.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function noteRecent(id: string): void {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...recentIds().filter((x) => x !== id)].slice(0, RECENT_MAX)));
  } catch {
    // No storage (a private window): the list keeps its own order.
  }
}

/** The commands in the palette's order: the recently used first (most recent first), then the rest as
 *  the page gives them; one entry per group and title (a button found twice is listed once). */
export function paletteOrder(list: Command[]): Command[] {
  const seen = new Set<string>();
  const unique = list.filter((c) => {
    const key = `${c.group}\u0000${c.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const recent = recentIds();
  const rank = (c: Command): number => {
    const at = recent.indexOf(c.id);
    return at < 0 ? RECENT_MAX : at;
  };
  return unique.map((c, i) => ({ c, i })).sort((a, b) => rank(a.c) - rank(b.c) || a.i - b.i).map(({ c }) => c);
}

// ===== Keyboard shortcuts (? and Ctrl+/): the same list, every command that has keys, by group =====

/** Whether a key press belongs to what has the focus (a text box, an editor), not to the page. */
function typing(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest("input, textarea, select, [contenteditable]:not([contenteditable=false]), .monaco-editor") !== null;
}

let shortcutsOpen: HTMLElement | null = null;

export function openShortcuts(): void {
  if (shortcutsOpen) return;
  const back = document.activeElement as HTMLElement | null;
  const groups = new Map<string, Command[]>();
  for (const c of paletteOrder(allCommands())) {
    if (c.agentOnly || !c.keys) continue;
    const list = groups.get(c.group) ?? [];
    if (!list.some((x) => x.keys === c.keys && x.title === c.title)) list.push(c);
    groups.set(c.group, list);
  }
  const filter = h("input", { type: "search", class: "wb-palette-input", placeholder: "Find a shortcut", "aria-label": "Find a shortcut", "data-no-variables": "" }) as HTMLInputElement;
  const body = h("div", { class: "shortcuts-groups" });
  const draw = (): void => {
    const words = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
    body.replaceChildren(
      ...[...groups.entries()].map(([group, list]) => {
        const rows = list.filter((c) => words.every((w) => `${group} ${c.title} ${c.keys}`.toLowerCase().includes(w)));
        if (!rows.length) return null;
        return h(
          "section",
          { class: "shortcuts-group" },
          h("h3", {}, group),
          h("dl", {}, ...rows.flatMap((c) => [h("dt", {}, ...String(c.keys).split(" ").map((k) => h("kbd", {}, k))), h("dd", {}, c.title)])),
        );
      }).filter((x): x is HTMLElement => x !== null),
    );
    if (!body.childElementCount) body.append(h("p", { class: "hint" }, "No shortcut matches."));
  };
  const close = (): void => {
    shade.remove();
    shortcutsOpen = null;
    back?.focus?.();
  };
  const box = h(
    "div",
    { class: "wb-palette shortcuts", role: "dialog", "aria-modal": "true", "aria-label": "Keyboard shortcuts" },
    h("div", { class: "shortcuts-head" }, h("h2", {}, "Keyboard shortcuts"), h("button", { type: "button", class: "ghost icon-only", "aria-label": "Close", title: "Close (Escape)", onclick: () => close() }, "×")),
    filter,
    body,
  );
  const shade = h("div", { class: "wb-palette-shade" }, box);
  filter.addEventListener("input", draw);
  box.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    e.preventDefault();
    e.stopPropagation();
    close();
  });
  shade.addEventListener("mousedown", (e) => {
    if (e.target === shade) close();
  });
  document.body.append(shade);
  shortcutsOpen = shade;
  draw();
  filter.focus();
}

/** ? (outside a text box) and Ctrl+/ (outside an editor, where it comments a line) show the shortcuts. */
export function mountShortcutKeys(): void {
  document.addEventListener("keydown", (e) => {
    if (e.defaultPrevented || e.altKey || typing(e.target)) return;
    const question = e.key === "?" && !e.ctrlKey && !e.metaKey;
    const slash = (e.ctrlKey || e.metaKey) && (e.key === "/" || e.code === "Slash");
    if (!question && !slash) return;
    if (document.querySelector("dialog[open]")) return; // a dialog's own keys
    e.preventDefault();
    document.querySelector(".menu")?.remove();
    openShortcuts();
  });
}

// ===== the palette =====

let open: HTMLElement | null = null;

export function openPalette(): void {
  if (open) {
    (open.querySelector("input") as HTMLInputElement).focus();
    return;
  }
  const back = document.activeElement as HTMLElement | null;
  const input = h("input", { type: "search", class: "wb-palette-input", placeholder: "Command", "aria-label": "Command", "aria-controls": "wb-palette-list", "aria-autocomplete": "list", role: "combobox", "aria-expanded": "true" }) as HTMLInputElement;
  const list = h("ul", { class: "wb-palette-list", id: "wb-palette-list", role: "listbox", "aria-label": "Commands" });
  const box = h("div", { class: "wb-palette", role: "dialog", "aria-modal": "true", "aria-label": "Command palette" }, input, list);
  const shade = h("div", { class: "wb-palette-shade" }, box);
  let shown: Command[] = [];
  let at = 0;

  const close = (): void => {
    shade.remove();
    open = null;
    back?.focus?.();
  };
  const choose = (c: Command | undefined): void => {
    if (!c || (c.when && !c.when())) return;
    close();
    void Promise.resolve()
      .then(() => {
        if (c.when && !c.when()) return undefined;
        if (gated(c.area ?? areaOfCommand(c.id))) return undefined; // closed in this project: its line
        recordAction(c.id);
        noteRecent(c.id);
        return c.run({}, { agent: false });
      })
      .catch((e: Error) => import("./errorNote").then((m) => m.errorHere(e)));
  };
  const draw = (): void => {
    const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    shown = paletteOrder(allCommands()).filter((c) => !c.agentOnly && words.every((w) => `${c.group} ${c.title} ${c.keys ?? ""}`.toLowerCase().includes(w)));
    at = Math.min(at, Math.max(0, shown.length - 1));
    list.replaceChildren(
      ...shown.map((c, i) => {
        const off = c.when ? !c.when() : false;
        const row = h(
          "li",
          { role: "option", id: `wb-cmd-${i}`, class: `wb-palette-item${i === at ? " active" : ""}${off ? " off" : ""}`, "aria-selected": String(i === at), "aria-disabled": off ? "true" : undefined, title: off ? c.whyNot : undefined },
          h("span", { class: "wb-palette-group" }, c.group),
          h("span", { class: "wb-palette-title" }, c.title),
          // Why it cannot run now, said in the row (not only in a tooltip).
          off && c.whyNot ? h("span", { class: "wb-palette-why" }, c.whyNot) : null,
          c.keys ? h("kbd", {}, c.keys) : null,
        );
        row.addEventListener("mousedown", (e) => {
          e.preventDefault();
          choose(c);
        });
        return row;
      }),
    );
    if (!shown.length) list.append(h("li", { class: "hint" }, "No matches"));
    input.setAttribute("aria-activedescendant", shown.length ? `wb-cmd-${at}` : "");
    list.querySelector(".active")?.scrollIntoView({ block: "nearest" });
  };
  input.addEventListener("input", () => {
    at = 0;
    draw();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") at = Math.min(shown.length - 1, at + 1);
    else if (e.key === "ArrowUp") at = Math.max(0, at - 1);
    else if (e.key === "Enter") return choose(shown[at]);
    else if (e.key === "Escape") return close();
    else return;
    e.preventDefault();
    draw();
  });
  shade.addEventListener("mousedown", (e) => {
    if (e.target === shade) close();
  });
  document.body.append(shade);
  open = shade;
  draw();
  input.focus();
}
