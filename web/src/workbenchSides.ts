/**
 * workbenchSides.ts: the Workbench's panes on the right of the documents: Files (codeExplorer.ts: the project's
 * scripts by module, or its notebooks; what the app generates, read-only, with Fine-tune as a script) and, on the
 * Scripts page, Blades (the blades list, catalogRail.ts, drawn there; a blade opens as a tab). Moved out of
 * workbenchPage.ts along its own heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   Side by side (Files nearest the code), each shown or hidden by its status bar button and resized by its
 *   edge, as the Canvas's Properties and Widgets (sidePanes.ts); remembered per page in this browser (the owner,
 *   2026-11-22: "make the blades and files panes function just like properties and widgets on canvas").
 *   ?pane=blades and the sab-blades event show Blades; ?blade=<name> opens that blade's tab.
 *
 * ROUTING: POST /scripts/fine-tune
 */
import { api } from "./api";
import { button, h, openDialog } from "./dom";
import { errorHere } from "./errorNote";
import { mountCodeExplorer, type TreeFile } from "./codeExplorer";
import type { Kind } from "./kindColours";
import { go, withParams } from "./nav";
import { sidePanes } from "./sidePanes";
import { tabKinds } from "./workbenchGroups";
import { deleteFile, duplicateFile, newPackage, renameFile } from "./workbenchIde";
import type { Doc } from "./workbenchPage";
import type { CodePage } from "./workbenchPages";

/** What the panes ask of the page: its documents, a file opened (at a line), the page's New, the landing page,
 *  a blade's tab, the page's "…" and the status bar's place for the panes' toggles. */
export interface SidesHost {
  page: CodePage;
  docs: Doc[];
  open: (path?: string) => Promise<void>;
  openAt: (path: string, line: number) => Promise<void>;
  scriptLanguage: () => string | null;
  newModeFile: (language: string) => Promise<void>;
  landingKind: () => Kind | null;
  hideLanding: () => void;
  bladeDoc: (name: string | null) => void;
  menu: HTMLButtonElement;
  sideToggles: HTMLElement;
  readonly current: Doc | null;
}

export function workbenchSides(host: SidesHost) {
  const { page, docs, open, openAt, scriptLanguage, newModeFile, hideLanding, bladeDoc, sideToggles } = host;
  const topMenu = host.menu;

  /** What the app generates, read-only (a table's transformations as one DuckDB query), with Fine-tune. */
  function showGenerated(file: TreeFile): void {
    const { body, foot, close } = openDialog(`${file.name}: its transformations (read-only)`, true);
    body.append(h("pre", { class: "mono wb-generated" }, file.text ?? ""));
    foot.append(button("Fine-tune as a script", () => (close(), void fineTune(file.name)), { class: "primary" }), button("Close", () => close(), { class: "ghost" }));
  }

  /** Fine-tune as a script: the table's transformations as a new script in scripts/, opened here. */
  async function fineTune(table: string): Promise<void> {
    try {
      const made = await api<{ path: string }>("/scripts/fine-tune", "POST", { table });
      await codex.refresh();
      await open(made.path);
    } catch (e) {
      errorHere(e);
    }
  }

  /** The Scripts explorer's tree actions (2026-11-21): Rename (imports follow, previewed), Duplicate, Delete (to
   *  the trash), a package's own. */
  function treeAction(file: TreeFile, action: string, path: string): void {
    const refreshed = (): void => void codex.refresh();
    if (action === "rename" || action === "rename-package") renameFile(path, refreshed);
    else if (action === "duplicate") void duplicateFile(path).then((made) => (refreshed(), void open(made))).catch((e: Error) => errorHere(e));
    else if (action === "delete" || action === "delete-package") deleteFile(path, refreshed);
    else if (action === "new-package") newPackage(path, refreshed);
    void file;
  }

  /** The page's New: a script here, a notebook on the Notebooks page (the creator's and the explorer's). */
  function newHere(): void {
    const k: Kind = page === "scripts" ? "script" : "notebook";
    const own = k === "script" ? scriptLanguage() : null;
    if (own) return void newModeFile(own);
    const start = tabKinds().find((t) => t.mark === k && t.start)?.start;
    if (!start) return;
    if (host.landingKind()) {
      hideLanding();
      void go(withParams({ view: null, kind: k }), "push");
    }
    start.run();
  }

  // The Scripts page's Blades, a pane on the right beside Files (the owner, 2026-11-22: "make the blades and files
  // panes function just like properties and widgets on canvas"): the blades list (catalogRail.ts) drawn here; a
  // blade opens as a tab (bladeDoc). Elsewhere the Data Explorer's.
  const bladesPane = page === "scripts" ? h("section", { class: "rail-section wb-blades-pane", id: "blades", "aria-labelledby": "blades-title" }) : null;

  // The page's Files pane (codeExplorer.ts): the project's scripts by module, or its notebooks; a click opens the
  // file as a tab here.
  const codex = mountCodeExplorer({
    page: page,
    open: (file) => (file.item ? showGenerated(file) : void open(file.full)),
    action: (file, id) => {
      if (id === "fine-tune") void fineTune(file.name);
    },
    openAt: (file, line) => void openAt(file.full, line),
    newDocument: newHere,
    newPackage: page === "scripts" ? () => newPackage(null, () => void codex.refresh()) : undefined,
    fileAction: page === "scripts" ? treeAction : undefined,
    menu: topMenu, // the page's "…" (no top bar: the owner, 2026-11-21)
    openNow: () => ({ paths: docs.map((d) => d.path ?? "").filter(Boolean), dirty: docs.filter((d) => d.dirty && d.path).map((d) => d.path!), front: host.current?.path ?? null }),
  });
    // Files and Blades: columns on the right of the documents, side by side (Files nearest the code), each shown or
  // hidden by its status bar button and resized by its edge, as the Canvas's Properties and Widgets (sidePanes.ts);
  // remembered per page in this browser.
  const bladesSide = bladesPane ? h("aside", { class: "wb-side wb-blades-side", "aria-label": "Blades" }, bladesPane) : null;
  codex.element.classList.add("wb-side");
  const sides = sidePanes(() => `wb-sides:${page}`, [
    { id: "files", label: "Files", icon: page === "scripts" ? "code" : "notebook", pane: codex.element, title: "Files (Ctrl+B)" },
    ...(bladesSide ? [{ id: "blades", label: "Blades", icon: "blade", pane: bladesSide, shown: false, title: "Blades" }] : []),
  ]);
  {
    const body = document.getElementById("wb-body") as HTMLElement;
    const row = h("div", { class: "wb-siderow" });
    body.before(row);
    row.append(body, codex.element, ...(bladesSide ? [bladesSide] : []));
    sides.mount();
    sideToggles.append(...sides.toggles);
  }
  /** The Blades pane shown, the focus in it (the old rail icon's place: ?pane=blades, ?blade=, app_navigate). */
  function showBlades(): void {
    if (!bladesSide) return;
    sides.show("blades", true);
    bladesSide.querySelector<HTMLElement>("input, button")?.focus();
  }
  window.addEventListener("sab-blades", () => showBlades());
  if (new URLSearchParams(location.search).get("pane") === "blades") window.setTimeout(() => showBlades(), 0);
  /** ?blade=<name> (the old /catalog?blade=, a Session link, the agent's blade:<name>): that blade's tab here; an
   *  empty name: New blade. The word leaves the address once it is shown (a reload does not open it again). */
  function bladeAsked(url: URL): void {
    if (page !== "scripts" || !url.searchParams.has("blade")) return;
    const name = url.searchParams.get("blade") ?? "";
    void go(withParams({ blade: null }), "replace");
    showBlades();
    bladeDoc(name || null);
  }

  return { codex, sides, bladesPane, bladeAsked };
}
