/**
 * catalogPage.ts: the blades page, in its own tab (plan decisions 14-18). [COMPOSITION]
 *
 * The blades list (catalogRail.ts) on the left; the main area shows a blade's screen (its code read-only:
 * a blade's code is edited in its file), New blade's templates, or a welcome. Dragging gives plain text: a
 * blade its `sab.blade(...)` line. The catalog panel went (the owner, 2026-11-17: "we dont even need
 * catalog if its just tables"): a connection's tables are on the Connections page and in the Data Explorer.
 *
 * Getting around (nav.ts): the mark at the top-left brings the home window forward. Each view is in the
 * address, so the browser's Back and Forward move between them and a reload keeps the one shown:
 *   /catalog                                  the welcome            "Blades"
 *   ?blade=refresh_sales  ·  ?blade=          a blade's screen, New blade's templates
 */
import { handleAgentNotice, loadApprovals } from "./agentAccess";
import { api, connect, onNotice, requireSession } from "./api";
import { watchConnectionColours } from "./connectionColours";
import { type BladeKind, editBlade } from "./bladeEditor";
import { mountRail, watchTheme } from "./catalogRail";
import { mountBeta } from "./betaNotes";
import { installZoomInput } from "./zoom";
import { mountAppFooter } from "./appFooter";
import { button, clear, h } from "./dom";
import { appMark, backButton, backTo, go, type Move, mountNav, setTitle, startNav } from "./nav";
import { mountNavRail } from "./rail";
import "./settingsWindow"; // the rail's Settings opens here too (open=settings)

watchTheme();

const detail = document.getElementById("detail") as HTMLElement;
const liveNote = document.querySelector<HTMLElement>(".cat-live");
// No token and no good cookie (a bookmark after a restart): the page says how to open the app.
void requireSession();
watchConnectionColours(); // a connection's colour on its blade (connectionColours.ts)

const PAGE = "Blades";
const WELCOME = "/catalog";

/** A view's address on this page: only the words it needs. */
function address(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== undefined) search.set(key, value);
  const text = search.toString();
  return `${WELCOME}${text ? `?${text}` : ""}`;
}

function showWelcome(how: Move = "auto"): void {
  setTitle(PAGE);
  void go(WELCOME, how);
  clear(detail, h("h2", {}, "Blades"), h("div", { class: "row-actions" }, button("New blade", () => openEditor(null), { icon: "plus", class: "primary" })));
}

/** Nothing at the address (a blade removed): said, with the way back. */
function showMissing(words: string): void {
  setTitle(PAGE);
  clear(detail, h("div", { class: "row-actions" }, backButton(PAGE, WELCOME)), h("p", { class: "status-error", role: "alert" }, words));
}

/** The blade the screen shows ("" New blade), while it is open. */
let editorOf: string | null = null;

function openEditor(name: string | null, how: Move = "auto"): void {
  editorOf = name ?? "";
  void go(address({ blade: editorOf }), how);
  setTitle(PAGE, name ?? "New blade");
  const lead = h("div", { class: "row-actions" });
  const host = h("div", {});
  clear(detail, lead, host);
  const closed = (): void => {
    rail.editorClosed();
    backTo(WELCOME);
  };
  lead.append(backButton(PAGE, WELCOME, () => rail.editorClosed()));
  const saved = (savedName: string): void => {
    rail.bladeSaved(savedName);
    editorOf = savedName;
    setTitle(PAGE, savedName);
    void go(address({ blade: savedName }), "replace"); // a new or renamed blade has its name now
  };
  void editBlade(host, name, null, "other" as BladeKind, saved, closed);
}

const rail = mountRail({
  bladesHost: document.getElementById("blades") as HTMLElement,
  editBlade: (name) => openEditor(name),
  isEditing: () => false, // the screen holds nothing that would be lost: its code is the file's
  showTable: () => undefined,
});

/** A starter (listed apart from the user's blades) or a blade made since the list was read. */
async function isBlade(name: string): Promise<boolean> {
  return api(`/blades/${encodeURIComponent(name)}`).then(() => true, () => false);
}

/** Show what an address names (a reload, Back, Forward, the agent). */
async function showAddress(url: URL): Promise<void> {
  const blade = url.searchParams.get("blade");
  if (blade !== null) {
    if (blade === editorOf) return; // shown already (its own move into the address)
    if (blade && !rail.blades().some((b) => b.name === blade) && !(await isBlade(blade))) {
      showMissing(`There is no blade called ${blade}.`);
      return;
    }
    openEditor(blade || null, "replace");
    return;
  }
  editorOf = null;
  showWelcome("replace");
}

const opened = new URL(location.href);
mountNav("catalog", { show: (url) => void showAddress(url) });
mountNavRail("catalog"); // the grids, Visualizations and the ERD are the home window's
document.querySelector(".cat-top")?.prepend(appMark());
setTitle(PAGE);
void rail
  .loadBlades()
  .then(() => (editorOf === null ? showAddress(opened) : undefined)) // a click while it loaded wins
  .then(() => startNav(opened));
connect((live) => {
  if (liveNote) liveNote.textContent = live ? "" : "Not connected to the server";
  if (live) void loadApprovals(); // an agent's request (an export, say) asks here too
}, { catalog: "1" });
onNotice((notice) => {
  handleAgentNotice(notice);
  if (notice.type === "blades_changed") void rail.loadBlades();
});

// Beta mode on the blades page: the right-click notes and the Beta mark, from the start (not after an editor closes).
mountBeta("catalog");
// The app's one footer (appFooter.ts), as on every page.
const footer = document.querySelector<HTMLElement>("footer.statusbar");
if (footer) mountAppFooter(footer);
installZoomInput();
