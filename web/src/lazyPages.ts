/**
 * lazyPages.ts: the rail's pages that load when first opened (the overnight optimisation pass, the owner
 * 2026-11-19): APIs, Structures, Code App, Source Control and Extensions. [STATE + WIRE]
 *
 * Every page with the rail has their layers (open=apis and the rest work from the address, Back and the
 * agent's app_navigate as before), their names and whether a plug-in page is on; the page's own module
 * (apisPage.ts, structuresPage.ts, codeAppPage.ts, scmPage.ts, extensionsPage.ts) arrives the first time
 * it is opened, as a chunk of the page's build, and registers its real layer in the stand-in's place.
 * What has to be heard before a page is ever opened is heard here: a Power Apps run's lines, the card
 * status's end, an extension's change handed over (the Extensions page follows it through the restart).
 *
 * ROUTING: GET /app/areas (scmOn), GET /app/modes (codeAppOn), GET /git?remote=1 (sharedSync);
 *          the `powerapps_output`, `sync_changed` and `extensions_changing` notices
 */
import { api, onNotice, type Notice } from "./api";
import { toast } from "./dom";
import { registerLazyLayer } from "./nav";
import { errorToast } from "./errorNote";
import type { Part } from "./structureTree";

export const APIS = "APIs";
export const STRUCTURES = "Structures";
export const CODE_APP = "Code App";
/** The Code App page's layer and the project type that turns it on. */
export const CODE_APP_TYPE = "codeapp";
export const SCM = "Source Control";
/** The Source Control page's layer and the area the backend names when it is on. */
export const SCM_KEY = "scm";
export const EXTENSIONS = "Extensions";

registerLazyLayer("structures", () => import("./structuresPage"));
registerLazyLayer("apis", () => import("./apisPage"));
registerLazyLayer(CODE_APP_TYPE, () => import("./codeAppPage"));
registerLazyLayer(SCM_KEY, () => import("./scmPage"));
registerLazyLayer("extensions", () => import("./extensionsPage"));

/** The Structures page, `id` in front (the Data Explorer's Open, an API's answer). */
export function openStructures(id: string | null = null, at: Part[] | null = null): void {
  void import("./structuresPage").then((page) => page.openStructures(id, at));
}

// ===== Code App (the Power Apps extension's page) =====

/** Whether the extension is on here: the app's modes name the code app type. Asked once a page. */
let codeAppAsked: Promise<boolean> | null = null;
export function codeAppOn(): Promise<boolean> {
  codeAppAsked ??= api<{ modes: { type: string }[] }>("/app/modes").then((got) => got.modes.some((m) => m.type === CODE_APP_TYPE), () => false);
  return codeAppAsked;
}

/** Each run's lines as they come, kept from the page's start (the Runs tab shows them live). */
export const runLines = new Map<string, string[]>();
export const runListeners = new Set<(run: string, line: string) => void>();
onNotice((notice: Notice) => {
  const said = notice as Notice & { run?: unknown; line?: unknown };
  if (notice.type === "powerapps_output" && typeof said.run === "string" && typeof said.line === "string") {
    const lines = runLines.get(said.run) ?? [];
    lines.push(said.line);
    runLines.set(said.run, lines.slice(-2000));
    for (const listen of runListeners) listen(said.run, said.line);
  }
});

// ===== Source Control (the Git extension's page) and the Project Explorer's shared cards =====

export interface SyncFolder {
  which: "library" | "shared";
  folder: string | null;
  set: boolean;
  connected: boolean;
  repository?: string;
  branch?: string;
  words: string;
  state: string;
  projects?: Record<string, { to_push: number; conflicts: number }>;
  behind?: number | null;
  pulled?: boolean;
}
export interface SyncStatus { signed_in: boolean; account: string | null; device: boolean; token_steps: string[]; folders: SyncFolder[] }

let scmAsked: Promise<boolean> | null = null;
/** The rail's Source Control area: on when the backend names it. Asked once a page. */
export function scmOn(): Promise<boolean> {
  scmAsked ??= api<{ areas: { area: string }[] }>("/app/areas").then((got) => got.areas.some((a) => a.area === SCM_KEY), () => false);
  return scmAsked;
}

let cardStatus: Promise<SyncStatus | null> | null = null;
let cardAsked = 0;
/** The shared projects folder's sync, for the cards: asked when the Explorer draws, at most once a minute
 *  from GitHub (the backend keeps to that). */
export function sharedSync(): Promise<SyncStatus | null> {
  if (!cardStatus || Date.now() - cardAsked > 5000) {
    cardAsked = Date.now();
    cardStatus = scmOn().then((on) => (on ? api<SyncStatus>("/git?remote=1").catch(() => null) : null));
  }
  return cardStatus;
}
onNotice((n) => {
  if (n.type === "sync_changed") cardStatus = null;
});

/** A shared card's words ("↑2 to push", "↓1 behind", "Conflicts: 1"), or null when up to date or not connected. */
export function cardWords(status: SyncStatus | null, name: string): string | null {
  const shared = status?.folders.find((f) => f.which === "shared");
  if (!shared?.connected) return null;
  const own = shared.projects?.[name] ?? { to_push: 0, conflicts: 0 };
  if (own.conflicts) return `Conflicts: ${own.conflicts}`;
  if (!shared.pulled) return "↓ Pull";
  if (shared.behind) return `↓${shared.behind} behind`;
  if (own.to_push) return `↑${own.to_push} to push`;
  return null;
}

/** A shared card's Pull and Push (the shared projects folder's, Push scoped to the card's project). */
export function cardActions(status: SyncStatus | null, path: string): { label: string; run: () => Promise<unknown> }[] {
  const shared = status?.folders.find((f) => f.which === "shared");
  if (!shared?.connected) return [];
  const act = (route: string, data: unknown) => (): Promise<unknown> =>
    api<{ words: string }>(route, "POST", data).then(
      (d) => toast(d.words),
      (e: Error) => errorToast(e),
    );
  return [
    { label: "Pull", run: act("/git/pull", { which: "shared" }) },
    { label: "Push", run: act("/git/push", { which: "shared", path }) },
  ];
}

// ===== Extensions =====

// An install or a removal handed over (the user's click elsewhere, or the agent's after Allow): the
// Extensions page follows it through the restart, opened or not.
onNotice((n) => {
  if (n.type !== "extensions_changing") return;
  const said = n as unknown as { id: string; action: "install" | "remove" };
  void import("./extensionsPage").then((page) => page.started(said.id, said.action));
});
