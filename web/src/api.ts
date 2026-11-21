/**
 * api.ts: the page's one door to the server. [SOURCE]
 *
 * The token arrives in the URL fragment (#token=...), which the browser never sends to the
 * server. Every request here attaches it: a Bearer header on fetch, a subprotocol on the
 * WebSocket (browsers cannot set WebSocket headers). Think of this as the typed HttpClient
 * wrapper a C# front end would inject everywhere.
 */

// ===== TYPES: the shapes the server sends (server/routes_*.py) =====

export type Row = unknown[];

export interface ColumnInfo {
  name: string;
  type: string; // DuckDB type name: BIGINT, DOUBLE, VARCHAR, DATE, ...
}

export interface StepJson {
  id?: string;
  kind: string;
  params: Record<string, unknown>;
  enabled?: boolean;
  description?: string;
}

export interface Settings {
  case_sensitive: boolean;
  wildcards: boolean;
  trim_spaces: boolean;
  empty_is_blank: boolean;
}

export interface Budget {
  used_bytes: number;
  total_bytes: number;
  used: string;
  total: string;
  datasets: number;
  max_datasets: number;
  grids: number;
  max_grids: number;
  warn: boolean;
}

export interface GridInfo {
  grid: string;
  dataset: string;
  title: string;
  version: number;
  row_count: number;
  source_kind: string;
  /** The SELECT that built this dataset (a "+" tab's table), or null for data pushed or loaded. */
  query: string | null;
  /** Opened from a connection with fewer rows than it holds: the grid says so and offers the rest. */
  opened: { connection: string; database: string; schema: string; table: string; shown: number; total: number } | null;
  source_columns: ColumnInfo[];
  columns: ColumnInfo[];
  stage_columns: ColumnInfo[][];
  steps: StepJson[];
  /** Is there a step change to undo, or an undone one to redo? */
  can_undo?: boolean;
  can_redo?: boolean;
  step_error: { index: number; message: string } | null;
  settings: Settings;
  gen: number;
  budget: Budget;
}

export interface RowsResponse {
  rows: Row[];
  row_count: number;
  columns: string[];
  truncated: [number, number][];
  highlighted: [number, string][];
  version: number;
  gen: number | null;
}

export interface Notice {
  type: string;
  dataset?: string;
  grid?: string;
  version?: number;
  by?: string;
  id?: string;
  action?: string;
  detail?: string;
  sql?: string;
  rows?: number;
  label?: string;
  name?: string;
  message?: string;
  area?: string;
  scale?: number;
  process?: string;
  to?: string; // dataset_renamed: the new name
  /** compare_shown: the compare to put on screen. */
  compare?: string;
}

// ===== the token and the grid id, from the address =====

/** The active grid's id and API path. Live bindings: useGrid() switches them when another grid
 * (a tab, or the other side of a split) becomes active, and every module reads the new value. */
export let gridId: string = location.pathname.startsWith("/g/") ? decodeURIComponent(location.pathname.slice(3)) : "";
export let grid = gridPath(gridId);

export function gridPath(id: string): string {
  return `/grids/${encodeURIComponent(id)}`;
}

export function useGrid(id: string): void {
  gridId = id;
  grid = gridPath(id);
}
/** The fragment as the page was opened with (#token=...&grid=...), kept because reading the
 * token clears it from the address bar. The workspace reads `grid` from here. */
export const openedWith: URLSearchParams = new URLSearchParams(location.hash.slice(1));
/** Read from the URL fragment once, then removed from the address bar (so it is not on screen
 * or in a screenshot) and kept in this tab's session storage so a reload still works. */
export const token: string = (() => {
  const key = `swissarmybench.token.${location.pathname}`;
  const fromUrl = new URLSearchParams(location.hash.slice(1)).get("token");
  let found = fromUrl ?? "";
  try {
    if (fromUrl) sessionStorage.setItem(key, fromUrl);
    else found = sessionStorage.getItem(key) ?? "";
  } catch {
    // Storage blocked: the token lives only in this page; a reload needs the full link again.
  }
  if (fromUrl) history.replaceState(null, "", location.pathname + location.search);
  return found;
})();
/** The page's session (security.py): with the token, the server answers with its cookie (HttpOnly,
 * SameSite=Strict, a secret of this start's own, never the token), so a bookmark or a new tab works
 * with no token in the address. False when neither the token nor a cookie is good (a restart since):
 * the page then says how to open the app. */
export async function openSession(): Promise<boolean> {
  try {
    if (token) {
      const minted = await fetch("/session", { method: "POST", headers: { Authorization: `Bearer ${token}` } });
      if (minted.ok) return true;
    }
    return (await fetch("/session")).ok;
  } catch {
    return false;
  }
}

/** The page for a browser with no token and no good cookie: how to open the app, nothing else. */
export function showSignedOut(): void {
  const page = document.createElement("main");
  page.className = "signed-out";
  page.append("Open Swiss Army Bench from its launcher, or run ");
  const code = document.createElement("code");
  code.textContent = "swissarmybench open";
  page.append(code, ".");
  document.body.replaceChildren(page);
}

/** Every page's start: the session, or the page that says how to open the app (false). */
export async function requireSession(): Promise<boolean> {
  if (await openSession()) return true;
  showSignedOut();
  return false;
}

/** This page's id: request generations are counted per page, so two tabs on one grid never
 * make each other's requests look stale. */
export const clientId: string = Math.random().toString(36).slice(2, 12);

function parsedObject(text: string): Record<string, unknown> | null {
  if (!text.trim().startsWith("{")) return null;
  try {
    const value = JSON.parse(text) as unknown;
    return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** A refusal from the server. Every route answers the one shape (design principle 9.5; domain/refusals.py):
 *  {"error": what happened, "where", "fixes": [{label, action, ...}], "details"} and the fields a page reads
 *  beside them (missing, missing_variables, needs). `message` is the words; `said` the whole answer; `body`
 *  its text as it came. */
export class ApiError extends Error {
  readonly said: Record<string, unknown> | null;
  readonly body: string;
  constructor(
    public status: number,
    text: string,
  ) {
    const said = parsedObject(text);
    const words = said && typeof said.error === "string" ? said.error : said && typeof said.message === "string" ? said.message : text;
    super(words);
    this.said = said;
    this.body = text;
  }
}

/** The server's whole answer behind an error (an ApiError's, or JSON an Error's words carry), else null. */
export function saidOf(e: unknown): Record<string, unknown> | null {
  if (e instanceof ApiError) return e.said;
  if (e instanceof Error) return parsedObject(e.message);
  if (typeof e === "string") return parsedObject(e);
  return e && typeof e === "object" && !Array.isArray(e) ? (e as Record<string, unknown>) : null;
}

/** A failed response read into an ApiError (its words, and the whole answer behind them). */
export async function failure(response: Response): Promise<ApiError> {
  return new ApiError(response.status, (await response.text()) || response.statusText);
}

/** An error's words: the server's sentence, never the JSON around it. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  const message = e instanceof Error ? e.message : String(e);
  const said = parsedObject(message);
  if (!said) return message;
  return typeof said.error === "string" ? said.error : typeof said.message === "string" ? said.message : message;
}

export function headers(json: boolean): Record<string, string> {
  // No token in this tab (a bookmark): the page's cookie is the credential, sent by the browser itself.
  const out: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  if (json) out["Content-Type"] = "application/json";
  // This page's id: a query of its waiting in a connection's line is found by it (its place, its Cancel).
  out["X-Sab-Client"] = clientId;
  return out;
}

/** GET/POST/PATCH/DELETE returning JSON; a non-2xx status throws ApiError with the server's
 * plain-language message. */
/** fetch, with the browser's bare "Failed to fetch" (the server stopped, or never answered)
 * turned into a message a person can act on. A deliberate abort stays an AbortError. */
async function send(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(path, init);
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "The grid's server is not answering. Start it again.");
  }
}

export async function api<T>(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await send(path, {
    method,
    headers: headers(body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new ApiError(response.status, (await response.text()) || response.statusText);
  return (await response.json()) as T;
}

/** api(), for a request the window makes on the agent's behalf (a workbench_window command): marked as
 * the agent's (`X-Actor: agent`), as the MCP's own requests are, so the server asks the user first
 * where it asks for the agent (an export with table rows) and the audit log names the agent. */
export async function agentApi<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await send(path, {
    method,
    headers: { ...headers(body !== undefined), "X-Actor": "agent" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new ApiError(response.status, (await response.text()) || response.statusText);
  return (await response.json()) as T;
}

/** A download (export): returns the bytes, the file name and the server's summary message. */
export async function download(path: string): Promise<{ blob: Blob; name: string; message: string }> {
  const response = await send(path, { headers: headers(false) });
  if (!response.ok) throw new ApiError(response.status, await response.text());
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "export";
  return { blob: await response.blob(), name, message: response.headers.get("X-Export-Message") ?? "" };
}

/** A file's bytes POSTed as they are (a dropped file the server reads), its name in X-File-Name; JSON back. */
export async function postBytes<T>(path: string, data: Blob, name: string): Promise<T> {
  const response = await send(path, {
    method: "POST",
    headers: { ...headers(false), "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(name) },
    body: data,
  });
  if (!response.ok) throw new ApiError(response.status, (await response.text()) || response.statusText);
  return (await response.json()) as T;
}

/** A download made by a POST with a JSON body (Export to Power BI's zip): the bytes and the file name. */
export async function downloadPost(path: string, body: unknown): Promise<{ blob: Blob; name: string }> {
  const response = await send(path, { method: "POST", headers: headers(true), body: JSON.stringify(body) });
  if (!response.ok) throw new ApiError(response.status, await response.text());
  const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1] ?? "export.zip";
  return { blob: await response.blob(), name };
}

export function query(params: Record<string, string | number | undefined | null>): string {
  const pairs = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return pairs.length ? "?" + new URLSearchParams(pairs.map(([k, v]) => [k, String(v)])).toString() : "";
}

// ===== live updates =====

type Listener = (notice: Notice) => void;
const listeners: Listener[] = [];

/** Hear every notice; the answer stops it. */
export function onNotice(listener: Listener): () => void {
  listeners.push(listener);
  return () => {
    const at = listeners.indexOf(listener);
    if (at >= 0) listeners.splice(at, 1);
  };
}

/** Hear the notices while `element` is on the page: none reach it while it is off, and once it has been
 *  on the page and is gone (its dialog or page closed), it stops hearing them for good. */
export function onNoticeWhile(element: Element, listener: Listener): () => void {
  let seen = element.isConnected;
  if (!seen) requestAnimationFrame(() => (seen ||= element.isConnected));
  const stop = onNotice((notice) => {
    if (!element.isConnected) {
      if (seen) stop();
      return;
    }
    seen = true;
    listener(notice);
  });
  return stop;
}

/** The live connection. `onState(live, again)` hears each open and close; `again` is true on an
 * open after the first, when notices may have been missed while the socket was down.
 *
 * A dropped socket is opened again while this server still knows the token (it answers /health
 * with it): a stall or a network blip no longer leaves the page "not live" for good, which also
 * made every later push open a new window instead of a tab here. A restarted server has a new
 * token, so this page's link is dead and it stops trying. */
let liveSocket: WebSocket | null = null;

/** Tell the server this window came to the front (the Workbench: the agent's commands go to the window
 *  the user was last in). Nothing is sent while the socket is down. */
export function tellFocus(): void {
  if (liveSocket?.readyState === WebSocket.OPEN) liveSocket.send('{"type":"focus"}');
}

export function connect(onState: (live: boolean, again: boolean) => void, who: Record<string, string> = { grid: gridId }): void {
  let delay = 1000;
  let opened = false;
  const retryLater = (): void => {
    window.setTimeout(() => void retry(), delay);
    delay = Math.min(delay * 2, 15000);
  };
  const retry = async (): Promise<void> => {
    try {
      const health = await fetch("/health", { headers: headers(false) });
      if (health.status === 401 || health.status === 403) return; // another server now: the link is dead
      if (!health.ok) throw new Error(health.statusText);
    } catch {
      retryLater(); // not answering yet
      return;
    }
    open();
  };
  const open = (): void => {
    // ?grid= tells the server which grid this page shows (?workspace=1: a tab bar that shows every
    // grid), so a push knows its grid is on screen and opens no new window.
    const socket = new WebSocket(`ws://${location.host}/ws?${new URLSearchParams(who).toString()}`, token ? ["swissarmybench", token] : ["swissarmybench"]);
    let live = false;
    socket.addEventListener("open", () => {
      live = true;
      liveSocket = socket;
      delay = 1000;
      onState(true, opened);
      opened = true;
    });
    socket.addEventListener("close", () => {
      if (live) onState(false, false);
      retryLater();
    });
    socket.addEventListener("message", (event: MessageEvent<string>) => {
      let notice: Notice;
      try {
        notice = JSON.parse(event.data) as Notice;
      } catch {
        return;
      }
      // One listener's failure must not keep the notice from the others.
      // A copy: a listener may stop hearing (onNoticeWhile) while the notice goes round.
      for (const listener of [...listeners]) {
        try {
          listener(notice);
        } catch (error) {
          console.error(error);
        }
      }
    });
  };
  open();
}
