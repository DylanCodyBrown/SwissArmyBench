/**
 * extensionsPage.ts: the Extensions page, on the rail above Settings (the owner, 2026-11-17: "add an extension
 * button to the rail to show what extensions are available to install and one click installs them"). [SHARED]
 *
 *   [CARDS]   a card per extension, as the server lists it (GET /extensions): its name, one line, what it
 *             adds, its status and version. Preinstalled (Streamlit: it comes with every install), Available
 *             (Install, one click), Installed (Remove, asked first), Coming (shown, never clickable).
 *   [CHANGE]  Install and Remove hand over to the update's helper: the app stops, uv installs this version
 *             with the extensions kept, and the app starts again (it opens its page). The card says each
 *             stage: handing over, the app stopped, the app back. A development checkout's answer (what to
 *             run instead) is said on the card; nothing happens.
 *   [PAGE]    a page of the rail's over any page (areaPage.ts), in the address as open=extensions.
 *
 * ROUTING: GET /extensions, POST /extensions/install, POST /extensions/remove  ·  notice extensions_changing
 */
import { api, headers, onNotice } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { button, h, icon, openDialog } from "./dom";
import { extensionPanel } from "./extensionPanel";
import { dismissDialog, registerLayer, setOverTitle } from "./nav";
import { busyClick } from "./loading";
import { errorNote } from "./errorNote";

/** The page's name, in one place: the rail, the title. */
export const EXTENSIONS = "Extensions";

type Status = "preinstalled" | "available" | "installed" | "coming";

interface Extension {
  id: string;
  name: string;
  description: string;
  adds: string[];
  status: Status;
  preinstalled?: boolean; // comes with every install (installed while its package is here)
  package: string;
  version: string | null;
  /** Its own panel's route, while it is on here (extensionPanel.ts draws what it answers). */
  panel?: string;
}

interface Listing {
  extensions: Extension[];
  installable: boolean;
  changing: { id: string; action: "install" | "remove" } | null;
}

const STATUS_WORDS: Record<Status, string> = { preinstalled: "Preinstalled", available: "Available", installed: "Installed", coming: "Coming" };

let shownPage: PageElement | null = null;
let reload: (() => void) | null = null;
let changing: { id: string; action: "install" | "remove" } | null = null;
let stage = "";

registerLayer("extensions", {
  isOpen: () => Boolean(shownPage?.open),
  open: () => drawPage(),
  show: () => undefined,
  dismiss: () => {
    if (shownPage) dismissDialog(shownPage);
  },
});

onNotice((n) => {
  if (n.type !== "extensions_changing") return;
  const said = n as unknown as { id: string; action: "install" | "remove" };
  started(said.id, said.action);
});

/** A change handed over (the user's click, or the agent's after Allow): the card follows the restart. */
function started(id: string, action: "install" | "remove"): void {
  if (changing) return;
  changing = { id, action };
  stage = "handing";
  reload?.();
  void follow();
}

/** The app stops, then a new one answers (with a token of its own: this page's link ends there). */
async function follow(): Promise<void> {
  let stopped = false;
  for (;;) {
    await new Promise((done) => window.setTimeout(done, 1500));
    let status = 0;
    try {
      status = (await fetch("/health", { headers: headers(false) })).status;
    } catch {
      status = 0;
    }
    if (status === 0 || status >= 500) {
      if (!stopped) {
        stopped = true;
        stage = "stopped";
        reload?.();
      }
      continue;
    }
    if (stopped && (status === 401 || status === 403)) {
      stage = "back";
      reload?.();
      return;
    }
    if (stopped && status === 200) {
      // The same server answering again: the hand-over did not happen (its note says why).
      changing = null;
      stage = "";
      reload?.();
      return;
    }
  }
}

function stageWords(name: string, action: "install" | "remove"): string {
  const doing = action === "install" ? `Installing ${name}` : `Removing ${name}`;
  if (stage === "stopped") return `${doing}: the app stopped; uv is at work.`;
  if (stage === "back") return `${action === "install" ? `${name} is installed` : `${name} is removed`}: the app opened again in a window of its own.`;
  return `${doing}: the app stops and starts again.`;
}

function drawPage(): void {
  const { element, body } = openAreaPage("extensions", EXTENSIONS);
  shownPage = element;
  body.classList.add("extensions-page");
  setOverTitle(EXTENSIONS);
  let listing: Listing | null = null;
  const said = new Map<string, string>(); // a card's answer from the server (a development checkout's words)

  const card = (ext: Extension, installable: boolean): HTMLElement => {
    const label = ext.preinstalled && ext.status === "installed" ? STATUS_WORDS.preinstalled : STATUS_WORDS[ext.status];
    const status = h("span", { class: `extension-status status-${ext.status}` }, label);
    const version = ext.version ? h("span", { class: "extension-version muted" }, ext.version) : null;
    const foot = h("div", { class: "extension-foot" });
    const here = changing?.id === ext.id ? changing : null;
    if (here) {
      foot.append(
        h("progress", { class: "extension-progress", "aria-label": stageWords(ext.name, here.action) }),
        h("p", { class: "extension-stage", role: "status" }, stageWords(ext.name, here.action)),
      );
    } else if (ext.status === "available") {
      const go = button("Install", busyClick("Installing…", () => change(ext, "install", go)), { icon: "import", class: "primary extension-install" });
      go.disabled = changing !== null;
      foot.append(go);
    } else if (ext.status === "installed") {
      const go = button("Remove", busyClick("Removing…", () => change(ext, "remove", go)), { icon: "trash", class: "extension-remove" });
      go.disabled = changing !== null;
      foot.append(go);
    }
    const words = said.get(ext.id);
    if (words) foot.append(h("p", { class: "extension-said", role: "status" }, words));
    return h(
      "article",
      { class: `extension-card ${ext.status}`, "data-extension": ext.id, "aria-disabled": ext.status === "coming" ? "true" : undefined, "data-installable": String(installable) },
      h("header", { class: "extension-head" }, h("span", { class: "extension-name" }, icon("extensions"), ext.name), status, version),
      h("p", { class: "extension-description" }, ext.description),
      ext.adds.length ? h("ul", { class: "extension-adds" }, ...ext.adds.map((a) => h("li", {}, a))) : null,
      ext.panel && ext.status === "installed" ? extensionPanel(ext.panel) : null,
      foot,
    );
  };

  const draw = (): void => {
    if (!listing) return;
    body.replaceChildren(h("div", { class: "extension-cards" }, ...listing.extensions.map((e) => card(e, listing!.installable))));
  };

  const change = async (ext: Extension, action: "install" | "remove", from: HTMLButtonElement, confirmed = false): Promise<void> => {
    from.disabled = true;
    said.delete(ext.id);
    try {
      const answer = await api<{ confirm?: string; changing?: { id: string; action: "install" | "remove" } }>(`/extensions/${action}`, "POST", { id: ext.id, confirmed });
      if (answer.confirm) {
        askFirst(ext, answer.confirm, () => void change(ext, action, from, true));
        from.disabled = false;
        return;
      }
      if (answer.changing) started(answer.changing.id, answer.changing.action);
    } catch (e) {
      said.set(ext.id, (e as Error).message);
      from.disabled = false;
      draw();
    }
  };

  reload = () => {
    if (!element.open) return;
    if (changing) {
      draw(); // the server is going away: draw from what was listed
      return;
    }
    void api<Listing>("/extensions").then(
      (got) => {
        listing = got;
        if (got.changing && !changing) started(got.changing.id, got.changing.action);
        else draw();
      },
      (e: Error) => body.replaceChildren(errorNote(e)),
    );
  };
  element.addEventListener("close", () => {
    if (shownPage === element) shownPage = null;
  });
  reload();
}

function askFirst(ext: Extension, question: string, yes: () => void): void {
  const { body, foot, close } = openDialog(`Remove ${ext.name}`);
  body.append(h("p", {}, question));
  foot.append(
    button("Cancel", close),
    button(`Remove ${ext.name}`, () => {
      close();
      yes();
    }, { class: "danger" }),
  );
}
