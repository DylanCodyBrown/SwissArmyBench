/**
 * updates.ts: "Update available" in the status bars, Settings' "Check for updates", Update to X. [SHARED]
 *
 * The owner (2026-11-16): "we should add a button that appears in the tray saying an update is available
 * and you can right click to update". The tray has it (server/tray.py); the grid page's and the
 * Workbench's status bars show the same, quietly, and only while there is one (principle 7.9: never "up to
 * date"). The check is the server's (services/updates.py): the one request that leaves the computer.
 *
 *   [UPDATE MARK]  "Update available" while a newer release exists: Update to X, What's new
 *   [FAILED MARK]  the last update's failure, said once, with its reason
 *   [UPDATE]       asks only when something would be lost (unsaved documents, running kernels), then the
 *                  app stops, installs the version and starts again; this page's link ends with it
 *   [SETTINGS]     Check for updates, kept across restarts
 *
 * ROUTING: GET/PUT /updates, POST /updates/install; the `update_changed` and `app_updating` notices
 */
import { api, onNotice } from "./api";
import { button, h, icon, openDialog, showMenu, toast } from "./dom";
import type { Command } from "./workbenchCommands";

export interface UpdateState {
  current: string;
  /** "lite": Swiss Army Bench Lite; else the full app. */
  edition?: string;
  latest: string | null;
  available: boolean;
  version: string | null;
  url: string | null;
  check: boolean;
  updating: string | null;
  failed?: { version: string; reason: string };
}

interface AtRisk {
  unsaved: string[];
  kernels: number;
}

let state: UpdateState | null = null;
let loading: Promise<UpdateState | null> | null = null;
let listening = false;
const listeners: (() => void)[] = [];

export const updateState = (): UpdateState | null => state;

function take(next: UpdateState): void {
  state = next;
  for (const listener of listeners) listener();
}

export function loadUpdates(): Promise<UpdateState | null> {
  if (!listening) {
    listening = true;
    onNotice((notice) => {
      if (notice.type === "update_changed") take(notice as unknown as UpdateState);
      if (notice.type === "app_updating" && state) take({ ...state, updating: String((notice as unknown as { version: string }).version) });
    });
  }
  loading ??= api<UpdateState>("/updates").then(
    (found) => {
      take(found);
      return found;
    },
    () => null, // an older server: no updates
  );
  return loading;
}

function onUpdates(listener: () => void): void {
  listeners.push(listener);
}

/** The app's name and version, at the bottom left of every status bar (the owner, 2026-11-16: "we should add a
 *  version stamp to the bottom of the app", then "Swiss Army Bench and Swiss Army Bench Lite as the app name in
 *  the bottom left"). Its tooltip says the newest version when another is offered. */
export function versionMark(): HTMLElement {
  const mark = h("span", { class: "version-mark" });
  const draw = (): void => {
    const s = state;
    const name = s?.edition === "lite" ? "Swiss Army Bench Lite" : "Swiss Army Bench";
    mark.textContent = s?.current ? `${name} ${s.current}` : name;
    mark.title = s?.available && s.version ? `${s.version} is out` : "";
  };
  onUpdates(draw);
  void loadUpdates().then(draw);
  draw();
  return mark;
}

/** The status bar's quiet mark: only while an update exists (or the last one failed). */
export function updateMark(): HTMLElement {
  const mark = h("button", { type: "button", class: "update-mark", hidden: true }) as HTMLButtonElement;
  const draw = (): void => {
    const s = state;
    mark.classList.toggle("failed", !!s?.failed && !s.available);
    if (s?.updating) {
      mark.hidden = false;
      mark.textContent = `Updating to ${s.updating}…`;
      mark.disabled = true;
      mark.title = "";
    } else if (s?.available && s.version) {
      mark.hidden = false;
      mark.disabled = false;
      mark.textContent = "Update available";
      mark.title = `Update to ${s.version}`;
    } else if (s?.failed) {
      mark.hidden = false;
      mark.disabled = false;
      mark.textContent = "Update failed";
      mark.title = s.failed.reason;
    } else {
      mark.hidden = true;
    }
  };
  mark.addEventListener("click", () => {
    const s = state;
    if (!s) return;
    if (!s.available && s.failed) {
      showFailure(s.failed);
      return;
    }
    const box = mark.getBoundingClientRect();
    showMenu(box.left, box.top - 8, `Update to ${s.version}`, [
      ["export", `Update to ${s.version}`, () => void startUpdate()],
      ["link", "What's new", () => whatsNew()],
    ]);
  });
  onUpdates(draw);
  void loadUpdates().then(draw);
  draw();
  return mark;
}

function showFailure(failed: { version: string; reason: string }): void {
  const { body, foot, close } = openDialog(`Update to ${failed.version} failed`);
  body.append(h("pre", { class: "mono update-reason" }, failed.reason));
  foot.append(button("Close", close, { class: "primary" }));
}

function whatsNew(): void {
  if (state?.url) window.open(state.url, "_blank", "noopener");
}

/** Update to the version offered: asks first only when something would be lost. */
export async function startUpdate(confirmed = false): Promise<void> {
  const version = state?.version;
  if (!version) {
    toast("No update is available.");
    return;
  }
  try {
    const answer = await api<{ confirm?: AtRisk; updating?: string }>("/updates/install", "POST", { version, confirmed });
    if (answer.confirm) {
      askFirst(version, answer.confirm);
      return;
    }
    if (answer.updating && state) take({ ...state, updating: answer.updating });
  } catch (e) {
    toast((e as Error).message, "error");
  }
}

function askFirst(version: string, risk: AtRisk): void {
  const { body, foot, close } = openDialog(`Update to ${version}`);
  if (risk.unsaved.length) body.append(h("p", {}, "Unsaved changes are lost:"), h("ul", { class: "update-unsaved" }, ...risk.unsaved.map((name) => h("li", {}, name))));
  if (risk.kernels) body.append(h("p", {}, `${risk.kernels} running kernel${risk.kernels === 1 ? " stops" : "s stop"}.`));
  foot.append(
    button("Cancel", close),
    button(`Update to ${version}`, () => {
      close();
      void startUpdate(true);
    }, { class: "danger" }),
  );
}

/** Settings' switch: Check for updates (the server's, kept across restarts). */
export function updatesSection(): HTMLElement {
  const box = h("input", { type: "checkbox", class: "update-switch", checked: true }) as HTMLInputElement;
  const draw = (): void => {
    box.checked = state?.check !== false;
  };
  box.addEventListener("change", () => void setCheck(box.checked));
  onUpdates(draw);
  void loadUpdates().then(draw);
  return h("fieldset", { class: "fieldset updates-fieldset" }, h("legend", {}, icon("import"), "Updates"), h("label", { class: "check" }, box, "Check for updates"));
}

export async function setCheck(on: boolean): Promise<void> {
  try {
    take(await api<UpdateState>("/updates", "PUT", { check: on }));
  } catch (e) {
    toast((e as Error).message, "error");
  }
}

/** The palette's commands (the Workbench's registry, the grid page's list). */
export function updateCommands(): Command[] {
  const available = (): boolean => !!state?.available && !state.updating;
  return [
    { id: "app.update", group: "Application", title: `Update to ${state?.version ?? "the new version"}`, when: available, whyNot: "no update is available", run: () => startUpdate() },
    { id: "app.whatsNew", group: "Application", title: "What's new", when: available, whyNot: "no update is available", run: () => whatsNew() },
    { id: "app.checkForUpdatesOn", group: "Application", title: "Check for updates", when: () => state?.check === false, whyNot: "it is on", run: () => setCheck(true) },
    { id: "app.checkForUpdatesOff", group: "Application", title: "Stop checking for updates", when: () => state?.check !== false, whyNot: "it is off", run: () => setCheck(false) },
  ];
}
