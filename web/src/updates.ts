/**
 * updates.ts: "Update available" in the status bars, Settings' "Click here to update", Update to X. [SHARED]
 *
 * The owner (2026-11-16): "we should add a button that appears in the tray saying an update is available
 * and you can right click to update". The tray is gone (2026-11-18); the grid page's and the
 * Workbench's status bars show it, quietly, and only while there is one (principle 7.9: never "up to
 * date"). The check is the server's (services/updates.py): the one request that leaves the computer.
 *
 *   [UPDATE CORNER] "Update available" in the window's top-right corner while a newer release exists
 *   [FAILED MARK]  the last update's failure, said once, with its reason
 *   [UPDATE]       always warns of the restart first (and what would be lost: unsaved documents, kernels), then the
 *                  app stops, installs the version and starts again; this page's link ends with it
 *   [SETTINGS]     Click here to update, only while an update is available
 *
 * ROUTING: GET/PUT /updates, POST /updates/install; the `update_changed` and `app_updating` notices
 */
import { api, onNotice } from "./api";
import { button, h, icon, openDialog, toast } from "./dom";
import type { Command } from "./workbenchCommands";
import { errorHere } from "./errorNote";

export interface UpdateState {
  current: string;
  /** The app's name, as the backend says it (Swiss Army Bench). */
  name?: string;
  /** The extensions this install has (their names: "Streamlit"), for the version mark's tooltip. */
  extensions?: string[];
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
 *  version stamp to the bottom of the app"; 2026-11-17: "call this the streamlit edition"; then "It's not an edition now it's the
 *  streamlit extension. Preinstalled"): the name is the backend's to say. Its tooltip lists the installed
 *  extensions and says the newest version when another is offered. */
export function versionMark(): HTMLElement {
  const mark = h("span", { class: "version-mark" });
  const draw = (): void => {
    const s = state;
    const name = s?.name ?? "Swiss Army Bench";
    // The name folds away first when the bar runs out of room (design principle 3.6); the version stays.
    mark.replaceChildren(h("span", { class: "version-name" }, name), s?.current ? ` ${s.current}` : "");
    const title = [name + (s?.current ? ` ${s.current}` : ""), s?.available && s.version ? `${s.version} is out` : ""].filter(Boolean).join(": ");
    mark.title = s?.extensions?.length ? `${title}\nExtensions: ${s.extensions.join(", ")}` : title;
  };
  onUpdates(draw);
  void loadUpdates().then(draw);
  draw();
  return mark;
}

/** The update button in the window's top-right corner (the owner, 2026-11-18: "pop up an update button in the
 *  top right when an update is available then warn that it will restart once updated"): only while an update
 *  exists (or the last one failed); one per window, put there by the footer. A click warns of the restart first. */
export function mountUpdateCorner(): void {
  if (document.querySelector(".update-corner")) return;
  const mark = h("button", { type: "button", class: "update-corner", hidden: true }) as HTMLButtonElement;
  const draw = (): void => {
    const s = state;
    mark.classList.toggle("failed", !!s?.failed && !s.available);
    if (s?.updating) {
      mark.hidden = false;
      mark.disabled = true;
      mark.replaceChildren(`Updating to ${s.updating}…`);
      mark.title = "Swiss Army Bench opens again by itself";
    } else if (s?.available && s.version) {
      mark.hidden = false;
      mark.disabled = false;
      mark.replaceChildren(icon("export"), " Update available");
      mark.title = `Update to ${s.version}`;
    } else if (s?.failed) {
      mark.hidden = false;
      mark.disabled = false;
      mark.replaceChildren("Update failed");
      mark.title = s.failed.reason;
    } else {
      mark.hidden = true;
    }
  };
  mark.addEventListener("click", () => {
    const s = state;
    if (!s) return;
    if (!s.available && s.failed) showFailure(s.failed);
    else void startUpdate();
  });
  document.body.append(mark);
  onUpdates(draw);
  void loadUpdates().then(draw);
  draw();
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
    errorHere(e);
  }
}

function askFirst(version: string, risk: AtRisk): void {
  const name = state?.name ?? "Swiss Army Bench";
  const { body, foot, close } = openDialog(`Update to ${version}`);
  body.append(h("p", { class: "update-restart" }, `${name} closes, installs ${version} and opens again by itself. It takes about a minute.`));
  if (risk.unsaved.length) body.append(h("p", {}, "Unsaved changes are lost:"), h("ul", { class: "update-unsaved" }, ...risk.unsaved.map((n) => h("li", {}, n))));
  if (risk.kernels) body.append(h("p", {}, `${risk.kernels} running kernel${risk.kernels === 1 ? " stops" : "s stop"}.`));
  const lost = risk.unsaved.length > 0 || risk.kernels > 0;
  foot.append(
    ...(state?.url ? [button("What's new", () => whatsNew(), { class: "link" }), h("span", { class: "grow" })] : []),
    button("Cancel", close),
    button("Update and restart", () => {
      close();
      void startUpdate(true);
    }, { class: lost ? "danger" : "primary" }),
  );
}

/** Check for updates now, and update when there is one (the owner, 2026-11-16: "check for updates should be a
 *  button that launches the update"). Update to X still asks first when work would be lost. */
export async function checkNow(): Promise<void> {
  try {
    take(await api<UpdateState>("/updates/check", "POST", { asked: true }));
  } catch (e) {
    errorHere(e);
    return;
  }
  const s = state;
  if (s?.available && s.version) await startUpdate();
  else if ((s as { error?: string } | null)?.error) errorHere(String((s as { error?: string }).error));
  else toast(`${s?.current ?? "This"} is the newest version.`);
}

/** Settings' Updates (the owner, 2026-11-19: "Check for updates should be changed to Click here to update and
 *  should only show when an update is available, and 6 hours is a hidden setting not needed in settings"): one
 *  button, only while a newer version exists; the check every six hours runs by itself (the server's switch stays,
 *  off the screen). The button warns of the restart first, as the top-right corner does. */
export function updatesSection(): HTMLElement {
  const go = button("Click here to update", () => void startUpdate(), { icon: "import", class: "update-now" });
  const section = h(
    "fieldset",
    { class: "fieldset updates-fieldset", hidden: true },
    h("legend", {}, icon("import"), "Updates"),
    h("div", { class: "updates-row" }, go),
  );
  const draw = (): void => {
    const s = state;
    const show = !!s?.available && !!s.version && !s.updating;
    section.hidden = !show;
    if (show) go.title = `Update to ${s?.version}: Swiss Army Bench restarts once it is updated`;
  };
  onUpdates(draw);
  void loadUpdates().then(draw);
  draw();
  return section;
}

export async function setCheck(on: boolean): Promise<void> {
  try {
    take(await api<UpdateState>("/updates", "PUT", { check: on }));
  } catch (e) {
    errorHere(e);
  }
}

/** The palette's commands (the Workbench's registry, the grid page's list). */
export function updateCommands(): Command[] {
  const available = (): boolean => !!state?.available && !state.updating;
  return [
    { id: "app.update", group: "Application", title: `Update to ${state?.version ?? "the new version"}`, when: available, whyNot: "no update is available", run: () => startUpdate() },
    { id: "app.whatsNew", group: "Application", title: "What's new", when: available, whyNot: "no update is available", run: () => whatsNew() },
  ];
}
