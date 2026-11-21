/**
 * connectionSlots.ts: each connection's slots on its card and detail (services/connection_slots.py).
 *
 * The owner (2026-11-21): "we should probably throttle how many queries an agent can run in parallel per
 * connection". One limit per connection covers every query (8 at once by default), the agent's share is
 * smaller (4); past it a query waits in line.
 *
 *   slotLine(name)       "Running 3 of 8 · 1 waiting", live (the `connection_slots` notice); on a card only
 *                        while something runs or waits; a click opens the Queries window
 *   slotsSection(name)   the detail's Queries section: the line, the three limits (at once, the agent's, the
 *                        wait in seconds), Save, Queries in progress…
 *   openQueriesWindow()  the Queries window (queriesWindow.ts: ?panel=queries&connection=<name>), a window of
 *                        its own per connection, or All connections
 */

import { api, onNotice, token } from "./api";
import { button, h, icon, toast } from "./dom";
import { errorHere } from "./errorNote";

export interface Limits {
  total: number;
  agent: number;
  wait: number;
}

export interface SlotStatus {
  connection: string;
  running: number;
  waiting: number;
  agent_running: number;
  agent_waiting: number;
  limits: Limits;
  words: string;
  full_words: string;
}

const statuses = new Map<string, SlotStatus>();
let asked: Promise<void> | null = null;

const key = (name: string): string => name.toLocaleLowerCase();

/** Every connection's counts, asked once; the notices keep them. */
function load(): Promise<void> {
  return (asked ??= api<{ connections: SlotStatus[] }>("/connections/slots").then(
    (r) => {
      for (const s of r.connections) statuses.set(key(s.connection), s);
      paint();
    },
    () => {
      asked = null;
    },
  ));
}

/** A connection's counts now (none known yet: its limits' defaults, nothing running). */
export function statusOf(name: string): SlotStatus | undefined {
  return statuses.get(key(name));
}

/** The words a line shows: "Running 3 of 8 · 1 waiting". */
function wordsOf(s: SlotStatus | undefined): string {
  return s ? s.words : "";
}

function paint(): void {
  for (const line of document.querySelectorAll<HTMLElement>("[data-slots]")) {
    const s = statusOf(line.dataset.slots ?? "");
    const busy = Boolean(s && (s.running || s.waiting));
    line.hidden = line.dataset.always !== "1" && !busy;
    const words = line.querySelector(".connection-slots-words");
    if (words) words.textContent = wordsOf(s) || "Running 0 of 8";
    line.classList.toggle("busy", busy);
    line.classList.toggle("full", Boolean(s && s.running >= s.limits.total));
  }
}

onNotice((notice) => {
  if (notice.type !== "connection_slots") return;
  const listed = new Set<string>();
  for (const s of (notice as unknown as { connections?: SlotStatus[] }).connections ?? []) {
    statuses.set(key(s.connection), s);
    listed.add(key(s.connection));
  }
  // A connection that is no longer named runs and waits nothing now.
  for (const [k, s] of statuses) {
    if (!listed.has(k) && (s.running || s.waiting)) {
      const total = s.limits.total;
      statuses.set(k, { ...s, running: 0, waiting: 0, agent_running: 0, agent_waiting: 0, words: `Running 0 of ${total}`, full_words: `Running 0 of ${total} · agent 0 of ${s.limits.agent}` });
    }
  }
  paint();
});

/** A connection's live line; `always`: shown with nothing running too (the detail). */
export function slotLine(name: string, always = false): HTMLElement {
  void load();
  const line = h(
    "button",
    {
      type: "button",
      class: "connection-slots",
      "data-slots": name,
      "data-always": always ? "1" : "0",
      title: "Queries in progress…",
      onclick: (e: MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        openQueriesWindow(name);
      },
    },
    icon("rows"),
    h("span", { class: "connection-slots-words" }, wordsOf(statusOf(name))),
  );
  queueMicrotask(paint);
  return line;
}

/** The Queries window: a window of its own for `connection` (or every connection's), reused when open. */
export function openQueriesWindow(connection: string | null = null): void {
  const at = new URL("/workspace", location.origin);
  at.searchParams.set("panel", "queries");
  if (connection) at.searchParams.set("connection", connection);
  const name = `sab-queries-${(connection ?? "all").replace(/[^A-Za-z0-9_-]/g, "_")}`;
  const opened = window.open(`${at.pathname}${at.search}${token ? `#token=${encodeURIComponent(token)}` : ""}`, name, "popup,width=1120,height=720");
  if (opened) opened.focus();
  else errorHere("The browser blocked the Queries window.");
}

/** The three limits as number boxes and Save (the detail, and the Queries window's header). */
export function limitsForm(name: string, compact = false): HTMLElement {
  const box = (label: string, min: number, max: number, field: keyof Limits): HTMLInputElement =>
    h("input", { type: "number", min: String(min), max: String(max), step: "1", class: "connection-limit", "aria-label": label, name: field, required: true }) as HTMLInputElement;
  const total = box("Queries at once", 1, 64, "total");
  const agent = box("The agent's share", 0, 64, "agent");
  const wait = box("Wait limit in seconds", 1, 3600, "wait");
  const fill = (l: Limits): void => {
    total.value = String(l.total);
    agent.value = String(l.agent);
    wait.value = String(l.wait);
    agent.max = String(l.total);
  };
  total.addEventListener("input", () => (agent.max = total.value || "64"));
  void api<Limits>(`/connections/${encodeURIComponent(name)}/limits`).then(fill, () => undefined);
  const save = button(
    "Save",
    () => {
      const body = { total: Number(total.value), agent: Number(agent.value), wait: Number(wait.value) };
      void api<Limits>(`/connections/${encodeURIComponent(name)}/limits`, "PUT", body).then(
        (l) => {
          fill(l);
          toast(`${name}: ${l.total} at once, ${l.agent} of them the agent's`);
        },
        (e: unknown) => errorHere(e, { where: name }),
      );
    },
    { icon: "save" },
  );
  const field = (label: string, input: HTMLInputElement): HTMLElement => h("label", { class: "connection-limit-field" }, h("span", {}, label), input);
  return h(
    "div",
    { class: `connection-limits${compact ? " compact" : ""}`, role: "group", "aria-label": "Limits" },
    field("At once", total),
    field("The agent's", agent),
    field("Wait (s)", wait),
    save,
  );
}

/** The detail's Queries section. */
export function slotsSection(name: string): HTMLElement {
  return h(
    "section",
    { class: "connection-section connection-queries", "aria-label": "Queries" },
    h("h2", {}, icon("rows"), "Queries"),
    slotLine(name, true),
    limitsForm(name),
    button("Queries in progress…", () => openQueriesWindow(name), { icon: "popout" }),
  );
}
