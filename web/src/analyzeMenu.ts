/**
 * analyzeMenu.ts: sending something from the grid page to the Analyze board by hand (a column's profile, a
 * value, a row, the Key Finder's pairs). [WIRE]
 *
 * The analyses themselves left the grid page (the owner, 2026-11-19): they are the Analyze page's
 * (analyzePage.ts), where every result lands on the board by itself. This file kept its name; the Table
 * row's Analyze menu it held is gone.
 *
 *   sendCards(cards) -> POST /grids/{id}/cards for each, then a toast with Show
 */
import { api, grid } from "./api";
import type { SandboxCard } from "./analysisCards";
import { errorHere } from "./errorNote";
import { sentToast } from "./sandboxShow";

/** Add cards to Analyze, filed with the grid in front; says what arrived, with Show (the
 * window it was sent from stays open). */
export async function sendCards(cards: SandboxCard[]): Promise<void> {
  try {
    let first: unknown;
    // Each card is sent; the first is the one Show goes to. (`first ??= await api(...)` sent only the
    // note: ??= does not run its right side once `first` is set, so the chart never arrived.)
    for (const card of cards) {
      const made = await api(`${grid}/cards`, "POST", card);
      first ??= made;
    }
    sentToast(`On the Analyze board: ${cards.length === 1 ? "a note" : "a note and its chart"}.`, first);
  } catch (e) {
    errorHere(e);
  }
}
