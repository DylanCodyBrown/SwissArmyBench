/**
 * Share… a running app with your organization (the owner, 2026-11-21: "a place for a user to host a POC so
 * others can connect to it like an app"; the backend's services/sharing.py, Microsoft Dev Tunnels). Generic:
 * any page that runs an app opens it with openShareDialog(app) and shows shareMark(app) beside its
 * Launch / Stop. Organization only, until you stop it; devtunnel installed on the first share.
 *
 *   [DIALOG]  "Share <app>"
 *             one sentence (who can open it, where it runs)
 *             not installed:  Sharing needs devtunnel           [Install now]
 *             not signed in:  [Sign in with your work account]  [Use a code instead]
 *                             the device code, Copy, the page to open; Waiting for you to sign in…
 *             ready:          [Share]
 *             shared:         the link [Copy] [Open]
 *                             Your organization: <tenant>
 *                             the amber note
 *                             [Stop sharing]
 *   [MARK]    "Shared" with the link (its title), a click opens the dialog; hidden while not shared
 *
 * Live: the `sharing_changed` notice redraws both. globalThis.sabShare exposes them for pages built apart.
 */

import { api, onNotice, onNoticeWhile } from "./api";
import { button, h, icon, openDialog, toast } from "./dom";
import { busy, loadingBlock } from "./loading";
import { errorNote, showError } from "./errorNote";

export interface ShareableApp {
  /** The kind of app (the backend's share target): "streamlit" unless said. */
  kind?: string;
  /** The app's id (a canvas's). */
  id: string;
  /** Its name, as the user knows it. */
  title: string;
}

export interface ShareState {
  kind: string;
  app: string;
  title: string;
  state: "installing" | "signing_in" | "starting" | "sharing" | "stopped" | "failed";
  words: string;
  url: string | null;
  who: string | null;
  note: string | null;
  error: string | null;
}

export interface SharingStatus {
  installed: boolean;
  installing: boolean;
  checks: string;
  needs: string;
  sentence: string;
  signed_in: boolean;
  work_account: boolean;
  account: string | null;
  signing_in: boolean;
  device: { url: string; code: string } | null;
  sign_in_error: string | null;
  shares: ShareState[];
}

const kindOf = (app: ShareableApp): string => app.kind || "streamlit";
const query = (app: ShareableApp): string => `?kind=${encodeURIComponent(kindOf(app))}&app=${encodeURIComponent(app.id)}`;

export const sharingStatus = (app: ShareableApp, fresh = false): Promise<SharingStatus> =>
  api<SharingStatus>(`/sharing${query(app)}${fresh ? "&fresh=1" : ""}`);

const shareOf = (status: SharingStatus, app: ShareableApp): ShareState | undefined =>
  status.shares.find((s) => s.kind === kindOf(app) && s.app === app.id);

async function copy(text: string, said: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    toast(said);
  } catch {
    toast("Copy is blocked here: select the text and copy it.");
  }
}

function linkRow(url: string): HTMLElement {
  const field = h("input", { class: "share-link", type: "text", readonly: true, value: url, "aria-label": "Link", onfocus: (e: Event) => (e.target as HTMLInputElement).select() });
  return h(
    "div",
    { class: "share-link-row" },
    field,
    button("Copy", () => void copy(url, "Copied the link."), { icon: "copy", class: "line share-copy" }),
    button("Open", () => window.open(url, "_blank", "noopener"), { icon: "link", class: "line share-open" }),
  );
}

// ===== the dialog =====

const opened = new Map<string, () => void>();

/** Share… for an app: one dialog per app (a second call brings it back). */
export function openShareDialog(app: ShareableApp): void {
  const key = `${kindOf(app)}\u0000${app.id}`;
  const again = opened.get(key);
  if (again) {
    again();
    return;
  }
  const { dialog, body, foot } = openDialog(`Share ${app.title}`, false, { history: false });
  dialog.classList.add("share-dialog");
  dialog.dataset.app = app.id;
  opened.set(key, () => dialog.focus());
  dialog.addEventListener("close", () => opened.delete(key));
  const main = h("div", { class: "share-main" });
  body.append(main);
  let drawing = false;

  const act = async (words: string, work: () => Promise<unknown>): Promise<void> => {
    try {
      await busy(main, words, work());
    } catch (error) {
      showError(main, error);
      return;
    }
    await draw();
  };

  const draw = async (status?: SharingStatus): Promise<void> => {
    if (drawing && !status) return;
    drawing = true;
    try {
      status ??= await sharingStatus(app);
    } catch (error) {
      main.replaceChildren(errorNote(error, { dismiss: false }));
      drawing = false;
      return;
    }
    drawing = false;
    const share = shareOf(status, app);
    const sentence = h("p", { class: "share-sentence" }, status.sentence);
    const parts: HTMLElement[] = [sentence];
    foot.replaceChildren();
    if (share?.state === "sharing" && share.url) {
      dialog.dataset.state = "sharing";
      parts.push(
        linkRow(share.url),
        h("p", { class: "share-who" }, icon("user"), share.who ?? "Your organization"),
        h("p", { class: "share-note", role: "note" }, icon("warning"), share.note ?? ""),
      );
      foot.append(button("Stop sharing", () => void act("Stopping…", () => api("/sharing/stop", "POST", { kind: kindOf(app), app: app.id })), { icon: "stop", class: "danger share-stop" }));
    } else if (!status.installed) {
      dialog.dataset.state = "install";
      parts.push(h("p", { class: "share-needs" }, status.needs, h("span", { class: "share-checks", title: status.checks }, icon("info"))));
      foot.append(button("Install now", () => void act("Installing devtunnel…", () => api("/sharing/install", "POST")), { icon: "import", class: "primary share-install" }));
    } else if (status.signing_in) {
      dialog.dataset.state = "signing_in";
      if (status.device) {
        const code = status.device.code;
        parts.push(
          h(
            "div",
            { class: "share-device" },
            h("code", { class: "share-code" }, code),
            button("Copy", () => void copy(code, "Copied the code."), { icon: "copy", class: "line" }),
            button("Open the page", () => window.open(status!.device!.url, "_blank", "noopener"), { icon: "link", class: "line" }),
          ),
        );
      }
      parts.push(loadingBlock("Waiting for you to sign in…", { inline: true }));
    } else if (!status.signed_in || !status.work_account) {
      dialog.dataset.state = "sign_in";
      if (status.sign_in_error) parts.push(errorNote({ what: status.sign_in_error, dismiss: false }));
      const signIn = (device: boolean): void => void act("Signing in…", () => api("/sharing/sign-in", "POST", { device }));
      foot.append(
        button("Use a code instead", () => signIn(true), { class: "ghost share-device-code" }),
        button("Sign in with your work account", () => signIn(false), { icon: "user", class: "primary share-sign-in" }),
      );
    } else {
      dialog.dataset.state = "ready";
      if (share?.state === "failed" && share.error) parts.push(errorNote({ what: share.error, dismiss: false }));
      if (status.account) parts.push(h("p", { class: "share-account muted" }, icon("user"), status.account));
      const go = button(share?.state === "failed" ? "Try again" : "Share", () => void act("Starting the tunnel…", () => api("/sharing/start", "POST", { kind: kindOf(app), app: app.id })), {
        icon: "globe",
        class: "primary share-start",
      });
      foot.append(go);
    }
    main.replaceChildren(...parts);
  };

  void draw();
  onNoticeWhile(dialog, (n) => {
    if (n.type === "sharing_changed") void draw();
  });
  // While signing in, the CLI's answer comes from its own process: look again until it ends.
  const timer = window.setInterval(() => {
    if (!dialog.isConnected) window.clearInterval(timer);
    else if (dialog.dataset.state === "signing_in") void sharingStatus(app, true).then((s) => draw(s));
  }, 1500);
  dialog.addEventListener("close", () => window.clearInterval(timer));
}

// ===== the mark =====

/** The small "Shared" mark for wherever the app's Launch / Stop shows: hidden while not shared; its
 *  title the link; a click opens Share…; Copy beside it. */
export function shareMark(app: ShareableApp): HTMLElement {
  const label = h("button", { type: "button", class: "share-mark-label", onclick: () => openShareDialog(app) }, icon("globe"), "Shared");
  const copyLink = button("Copy the link", () => void copy(mark.dataset.url ?? "", "Copied the link."), { icon: "copy", iconOnly: true, class: "ghost share-mark-copy" });
  const mark = h("span", { class: "share-mark", hidden: true, dataset: { app: app.id } }, label, copyLink);
  const show = (status: SharingStatus): void => {
    const share = shareOf(status, app);
    const url = share?.state === "sharing" ? share.url : null;
    mark.hidden = !url;
    mark.dataset.url = url ?? "";
    label.title = url ? `Shared with your organization: ${url}` : "";
  };
  const look = (): void => void sharingStatus(app).then(show, () => (mark.hidden = true));
  look();
  const stop = onNotice((n) => {
    if (n.type !== "sharing_changed") return;
    if (!mark.isConnected && mark.dataset.seen) stop();
    else look();
  });
  requestAnimationFrame(() => {
    if (mark.isConnected) mark.dataset.seen = "1";
  });
  return mark;
}

declare global {
  // eslint-disable-next-line no-var
  var sabShare: { openShareDialog: typeof openShareDialog; shareMark: typeof shareMark } | undefined;
}
globalThis.sabShare = { openShareDialog, shareMark };
