/**
 * loading.ts: the one loading state of every page and window. [SHARED]
 *
 * The owner (2026-11-18): "Let's improve loading things with a uniform loading form. I noticed some things say
 * in tiny text loading and they don't gate the thing that is loading."
 *
 *   busy(host, words, work, options)   gates an element while its work runs: `inert` and aria-busy at once (a
 *                                       click lands nowhere, a second one starts nothing), and after 150 ms a
 *                                       translucent cover over exactly its box with a spinner and the words in
 *                                       the body's size ("Loading Finance Captive's tables…"); after 3 s the time
 *                                       taken; Cancel when the caller gives an AbortController; an error shown
 *                                       where the work was (not only a toast), then thrown on.
 *   loadingBlock(words, options)       an empty area's placeholder: the spinner and the words centred in the
 *                                       space the content will take (its height kept, so nothing jumps).
 *   busyButton(button, work, words)    a button while its work runs: disabled with a small spinner and its own
 *                                       words ("Testing…"), put back after; a second click does nothing.
 *
 * Work quicker than 150 ms shows nothing (no flicker); the gate holds all the same. The colours are grid.css's
 * tokens (--busy-*), each theme's own; with reduced motion the spinner stands still and the time still counts.
 */

import { h } from "./dom";
import { clearError, showError } from "./errorNote";

/** How long work runs before anything is drawn (shorter work never flickers). */
export const SHOW_AFTER_MS = 150;
/** How long before the time taken is shown beside the words. */
export const ELAPSED_AFTER_MS = 3000;

export type Work<T> = Promise<T> | ((signal: AbortSignal | undefined) => Promise<T>);

export interface BusyOptions {
  /** Cancel is shown, and aborts it (a fetch given its signal stops; onCancel can call the server's cancel). */
  abort?: AbortController;
  /** Called on Cancel, after the abort (a server route that stops the work). */
  onCancel?: () => void;
  /** Where a failure is shown (default: the host itself, at its top); `false` leaves it to the caller. */
  errorIn?: HTMLElement | false;
}

const active = new WeakMap<Element, Promise<unknown>>();

/** Whether `element` is being gated by busy() or busyButton() right now. */
export const isBusy = (element: Element): boolean => active.has(element);

const spinner = (): HTMLElement => h("span", { class: "busy-spinner", "aria-hidden": "true" });

function seconds(ms: number): string {
  const s = Math.floor(ms / 1000);
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}

/** A label that shows the time taken once the work is slow, counting while it is on the page. */
function elapsed(started: number, isLive: () => boolean): HTMLElement {
  const label = h("span", { class: "busy-elapsed", hidden: true });
  const tick = (): void => {
    if (!isLive()) return window.clearInterval(timer);
    const ms = performance.now() - started;
    if (ms < ELAPSED_AFTER_MS) return;
    label.hidden = false;
    label.textContent = seconds(ms);
  };
  const timer = window.setInterval(tick, 500);
  return label;
}

const isAbort = (e: unknown): boolean => e instanceof DOMException ? e.name === "AbortError" : (e as Error | null)?.name === "AbortError";

/** Gate `host` while `work` runs: see the module's comment. Resolves with the work's answer; a failure is
 * shown in place (options.errorIn) and thrown on; a Cancel throws an AbortError and shows nothing. */
export async function busy<T>(host: HTMLElement, words: string, work: Work<T>, options: BusyOptions = {}): Promise<T> {
  // Gated already (a path typed while a folder is read): this work's gate follows that one's, so the host
  // stays covered and each caller gets its own answer.
  const before = active.get(host);
  const promise = (before ? before.catch(() => undefined) : Promise.resolve()).then(() => gate(host, words, work, options));
  active.set(host, promise);
  try {
    return await promise;
  } finally {
    if (active.get(host) === promise) active.delete(host);
  }
}

async function gate<T>(host: HTMLElement, words: string, work: Work<T>, options: BusyOptions): Promise<T> {
  const hadFocus = host.contains(document.activeElement) ? (document.activeElement as HTMLElement) : null;
  const wasInert = host.inert;
  host.inert = true;
  host.setAttribute("aria-busy", "true");
  clearError(options.errorIn || host); // a retry: the last failure goes (9.5: it never lingers)

  const started = performance.now();
  let done = false;
  const cancel = options.abort
    ? h("button", {
        type: "button",
        class: "btn busy-cancel",
        onclick: () => {
          options.abort?.abort();
          options.onCancel?.();
        },
      }, "Cancel")
    : null;
  const panel = h(
    "div",
    { class: "busy-panel" },
    h("span", { class: "busy-progress", role: "progressbar", "aria-label": words }, spinner(), h("span", { class: "busy-words" }, words), elapsed(started, () => !done)),
    cancel,
  );
  const cover = h("div", { class: "busy-cover", "data-for": host.id || undefined }, panel);
  let frame = 0;
  // The cover is the host's sibling (an inert host's own child could not be clicked: Cancel), kept over
  // exactly its box each frame, wherever the host scrolls or grows to.
  const place = (): void => {
    if (done) return;
    if (!cover.isConnected) host.after(cover);
    const want = host.getBoundingClientRect();
    const have = cover.getBoundingClientRect();
    const left = parseFloat(cover.style.left || "0") + want.left - have.left;
    const top = parseFloat(cover.style.top || "0") + want.top - have.top;
    cover.style.left = `${left}px`;
    cover.style.top = `${top}px`;
    cover.style.width = `${want.width}px`;
    cover.style.height = `${want.height}px`;
    cover.classList.toggle("tall", want.height > 320); // the words near the top, where the eye is
    frame = requestAnimationFrame(place);
  };
  let show = 0;
  const draw = (): void => {
    if (done) return;
    if (!host.isConnected) {
      show = window.setTimeout(draw, 100); // gated before it was placed on the page: covered once it is
      return;
    }
    host.after(cover);
    cover.style.borderRadius = getComputedStyle(host).borderRadius; // a card's own corners
    place();
  };
  show = window.setTimeout(draw, SHOW_AFTER_MS);

  try {
    return await (typeof work === "function" ? work(options.abort?.signal) : work);
  } catch (e) {
    if (!isAbort(e) && options.errorIn !== false) {
      showError(options.errorIn ?? host, e); // the one error component (errorNote.ts, 9.5)
    }
    throw e;
  } finally {
    done = true;
    window.clearTimeout(show);
    cancelAnimationFrame(frame);
    cover.remove();
    host.inert = wasInert;
    host.removeAttribute("aria-busy");
    if (hadFocus?.isConnected && !host.inert) hadFocus.focus();
  }
}

/** Room kept for content that is coming, under a busy() cover (the words are the cover's): nothing jumps. */
export const room = (height = "120px"): HTMLElement => h("div", { class: "busy-room", style: { minHeight: height } });

/** The placeholder for an area that is empty until its content arrives: the spinner and the words centred in
 * `height` (the content's usual height, so the layout does not jump). Nothing shows for the first 150 ms. */
export function loadingBlock(words: string, options: { height?: string; inline?: boolean } = {}): HTMLElement {
  const started = performance.now();
  const block = h(
    options.inline ? "span" : "div",
    {
      class: options.inline ? "loading-block inline" : "loading-block",
      role: "progressbar",
      "aria-label": words,
      "aria-live": "polite",
      "aria-busy": "true",
      style: options.height ? { minHeight: options.height } : undefined,
    },
    spinner(),
    h("span", { class: "busy-words" }, words),
  );
  block.append(elapsed(started, () => block.isConnected || performance.now() - started < 1000));
  window.setTimeout(() => block.setAttribute("data-shown", ""), SHOW_AFTER_MS);
  return block;
}

/** `button` while `work` runs: disabled, with a small spinner and `words` ("Testing…") in place of its label;
 * put back as it was after. A second click while busy does nothing. Resolves or throws as the work does. */
export async function busyButton<T>(button: HTMLButtonElement, work: Work<T>, words?: string): Promise<T> {
  const running = active.get(button);
  if (running) return running as Promise<T>;
  const promise = holdButton(button, work, words);
  active.set(button, promise);
  try {
    return await promise;
  } finally {
    active.delete(button);
  }
}

/** A button drawn while its work runs (a view that draws its buttons again from its own state, like a
 * canvas's Play, a query's Run): the busy look of busyButton, at once, with `words`. Returns what puts the
 * button back as it was. */
export function markBusy(button: HTMLButtonElement, words: string): () => void {
  const kept = [...button.childNodes];
  const wasDisabled = button.disabled;
  button.disabled = true;
  button.classList.add("busy");
  button.setAttribute("aria-busy", "true");
  if (button.classList.contains("icon")) button.replaceChildren(spinner());
  else button.replaceChildren(spinner(), h("span", { class: "btn-label" }, words));
  return () => {
    if (!button.classList.contains("busy")) return;
    button.classList.remove("busy");
    button.removeAttribute("aria-busy");
    button.replaceChildren(...kept);
    button.disabled = wasDisabled;
  };
}

/** A click handler that runs `work` with its button busy (busyButton): `button("Test", busyClick("Testing…",
 * test))`. The work says its own failure (it is the caller's: a form's line, the error panel); it is handed
 * the button, to gate what is around it too (`(b) => busy(b.closest(".api-card")!, …)`). */
export function busyClick(words: string, work: (button: HTMLElement) => Promise<unknown>): (event: MouseEvent) => void {
  return (event) => {
    const target = event.currentTarget as HTMLElement;
    const running = target instanceof HTMLButtonElement ? busyButton(target, () => work(target), words) : work(target);
    void running.catch(() => undefined);
  };
}

async function holdButton<T>(button: HTMLButtonElement, work: Work<T>, words?: string): Promise<T> {
  const kept = [...button.childNodes];
  const wasDisabled = button.disabled;
  const swallow = (event: Event): void => {
    event.preventDefault();
    event.stopImmediatePropagation();
  };
  // At once: clicks (mouse or keys) are swallowed and the button reads as busy; the look changes only
  // when the work is slow enough to see (no flicker).
  button.addEventListener("click", swallow, true);
  button.setAttribute("aria-busy", "true");
  let done = false;
  const show = window.setTimeout(() => {
    if (done) return;
    button.disabled = true;
    button.classList.add("busy");
    // An icon-only button keeps its size: the spinner in place of the icon, its name for screen readers.
    if (button.classList.contains("icon")) return button.replaceChildren(spinner());
    const label = words ?? button.querySelector(".btn-label")?.textContent ?? button.textContent ?? "";
    button.replaceChildren(spinner(), h("span", { class: "btn-label" }, label));
  }, SHOW_AFTER_MS);
  try {
    return await (typeof work === "function" ? work(undefined) : work);
  } finally {
    done = true;
    window.clearTimeout(show);
    button.removeEventListener("click", swallow, true);
    button.removeAttribute("aria-busy");
    if (button.classList.contains("busy")) {
      button.classList.remove("busy");
      button.replaceChildren(...kept);
      button.disabled = wasDisabled;
    }
  }
}
