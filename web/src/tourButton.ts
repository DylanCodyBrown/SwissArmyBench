/**
 * tourButton.ts: the Projects page's Tour button and its "New here?" bubble (projectsPage.ts). The tour
 * itself (tour.ts) loads when the button is first pressed. [WIRE]
 */
import { button, h, recall, remember } from "./dom";

const SEEN = "tour.seen";

const openTour = (): void => void import("./tour").then((tour) => tour.openTour());

/** The Projects page's Tour button, with the "New here?" bubble until the tour is opened once. */
export function tourButton(): HTMLElement {
  const btn = button("Tour", () => openTour(), {
    icon: "help",
    class: "ribbon-btn tour-btn",
    title: "What everything means: a guided tour",
  });
  btn.setAttribute("aria-haspopup", "dialog");
  if (recall(SEEN)) return btn;
  const bubble = h(
    "span",
    { class: "tour-bubble" },
    h("button", { type: "button", class: "tour-bubble-go", onclick: () => openTour() }, "New here? Take the tour"),
    button("Not now", () => markSeen(), { icon: "close", iconOnly: true, class: "ghost" }),
  );
  btn.classList.add("tour-new");
  return h("span", { class: "tour-slot" }, btn, bubble);
}

/** The tour was opened (or Not now): the bubble goes, for good in this browser. */
export function markSeen(): void {
  remember(SEEN, "1");
  document.querySelectorAll(".tour-bubble").forEach((b) => b.remove());
  document.querySelectorAll(".tour-new").forEach((b) => b.classList.remove("tour-new"));
}

/** Whether the tour is on show: it moves the user itself, so a table that arrives meanwhile (its own staged
 *  tables among them) never takes the user anywhere (main.ts's grid_shown; the
 *  tour's made-up form in connectionsWindow.ts never prompts for a missing driver). */
export function touring(): boolean {
  return document.querySelector(".tour") !== null;
}
