/**
 * sandboxShow.ts: after sending something to the Sandbox, a toast with a Show button. [WIRE]
 *
 * The owner's decision 8: the window a result was sent from stays open (so more can be sent), and
 * the toast that says what arrived has Show, which closes the windows and goes to the card.
 *
 *   [SHOW]  -> close every open dialog, showAgentView(), then the Sandbox scrolls to the card
 *              (aiPanel.ts registers how with onShowCard)
 *
 * In a window with no Sandbox tab (the Key Finder's own window) the toast has no button.
 */
import { closeDialogs, toast } from "./dom";
import { showAgentView } from "./panes";

let reveal: (card: string | null) => void = () => {};

/** aiPanel.ts: how the Sandbox brings a card into view once it is drawn. */
export function onShowCard(handler: (card: string | null) => void): void {
  reveal = handler;
}

/** Go to the Sandbox and bring `card` into view. */
export function showInSandbox(card: string | null): void {
  closeDialogs();
  reveal(card);
  showAgentView();
}

/** Say what arrived in the Sandbox, with Show. `made`: the server's answer for the first card sent ({card: its id}). */
export function sentToast(message: string, made?: unknown): void {
  const id = made && typeof made === "object" && typeof (made as { card?: unknown }).card === "string" ? (made as { card: string }).card : null;
  if (!document.querySelector(".tab-agent")) {
    toast(message);
    return;
  }
  toast(message, "info", { label: "Show", run: () => showInSandbox(id) });
}
