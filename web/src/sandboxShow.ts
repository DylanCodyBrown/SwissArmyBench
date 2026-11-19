/**
 * sandboxShow.ts: after sending something to Analyze, a toast with a Show button. [WIRE]
 *
 * The owner's decision 8: the window a result was sent from stays open (so more can be sent), and
 * the toast that says what arrived has Show, which closes the windows and goes to the card.
 *
 *   [SHOW]  -> close every open dialog, showAgentView(), then Analyze scrolls to the card
 *              (aiPanel.ts registers how with onShowCard)
 *
 * In a window with no Analyze tab (the Key Finder's own window) the toast has no button.
 */
import { closeDialogs, toast } from "./dom";
import type { Move } from "./nav";
import { showAgentView } from "./panes";

let reveal: (card: string | null) => void = () => {};

/** aiPanel.ts: how Analyze brings a card into view once it is drawn. */
export function onShowCard(handler: (card: string | null) => void): void {
  reveal = handler;
}

/** Go to Analyze and bring `card` into view (`how`: Follow the agent's move replaces). */
export function showInSandbox(card: string | null, how: Move = "auto"): void {
  closeDialogs();
  reveal(card);
  showAgentView(how);
}

/** Say what arrived in Analyze, with Show. `made`: the server's answer for the first card sent ({card: its id}). */
export function sentToast(message: string, made?: unknown): void {
  const id = made && typeof made === "object" && typeof (made as { card?: unknown }).card === "string" ? (made as { card: string }).card : null;
  if (!document.querySelector("#ai-panel")) { // the grid page only: Analyze is in this page
    toast(message);
    return;
  }
  toast(message, "info", { label: "Show", run: () => showInSandbox(id) });
}
