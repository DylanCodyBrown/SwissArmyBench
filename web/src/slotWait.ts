/**
 * slotWait.ts: this page's queries waiting in a connection's line (services/connection_slots.py), for the one
 * loading state (loading.ts): each `connection_slots` notice names the waiting queries with the page that
 * asked (X-Sab-Client, api.ts); the newest gate on the page shows the first one's words, and its Cancel gives
 * every one of this page's up (POST /connections/queries/cancel-mine).
 */

import { api, clientId, onNotice } from "./api";

interface Waiting {
  client?: string;
  state: string;
  words?: string;
}

type Listener = (words: string | null) => void;
const listeners = new Map<number, Listener>();
let current: string | null = null;

onNotice((notice) => {
  if (notice.type !== "connection_slots") return;
  const queries = (notice as unknown as { queries?: Waiting[] }).queries ?? [];
  const mine = queries.find((q) => q.client === clientId && q.state === "waiting");
  current = mine ? (mine.words ?? "Waiting for a slot") : null;
  const newest = Math.max(-1, ...listeners.keys());
  listeners.get(newest)?.(current);
});

/** Hear this page's waiting query while `gate` is the newest; the answer stops it. */
export function whileWaiting(gate: number, listener: Listener): () => void {
  listeners.set(gate, listener);
  if (current) listener(current);
  return () => {
    listeners.delete(gate);
  };
}

/** Give up every query this page has waiting (or running) on a connection. */
export async function cancelWaiting(): Promise<void> {
  try {
    await api("/connections/queries/cancel-mine", "POST", {});
  } catch {
    /* the work's own answer says it */
  }
}
