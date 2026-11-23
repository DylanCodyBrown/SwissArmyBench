/**
 * canvasGallery.ts: the Canvas's Widgets pane and the widgets' rendered previews. Moved out of canvasPage.ts
 * along its own heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [PREVIEWS] a widget's rendered preview, one per widget file and theme (server/previews.py), made one at a
 *              time: the board's first, the gallery's cards as they scroll into view, the hover's at once; until
 *              then a card with its name and "Preview is being made…", a failure's one line with Try again, a
 *              missing Streamlit the one missing-package prompt, once
 *   [GALLERY]  a card per widget (its preview, name, description), search, groups (yours first, then the
 *              starter packs); drag a card in, double-click or Insert puts it in the selected container;
 *              hovering a card shows its preview large
 *
 * ROUTING: GET /streamlit/widgets/{name}/preview, POST /environment/libraries/install (a preview's package)
 */
import { api } from "./api";
import { button, clear, h, icon } from "./dom";
import { intoApp, type Missing, promptInstall } from "./missingPackages";
import { openWidgets } from "./rail";
import { effectiveTheme } from "./theme";
import { headingElement, headingOf } from "./widgetPacks";
import type { WidgetEntry } from "./widgetPage";

/** A widget card's drag (the board takes it). */
export const DRAG = "application/x-sab-widget";

/** A widget's rendered preview, and what the box shows until it is there (the owner, 2026-11-22: "The
 *  pre-built widgets are not rendering on my machine": a box is never empty). One per widget file and theme
 *  (server/previews.py), made one at a time: the board's widgets first (`board`), the gallery's cards as
 *  they scroll into view (`card`), the hover's at once (`hover`). Until it is made, a card with the widget's
 *  name and "Preview is being made…"; a failure's one line with Try again (its full words in the title),
 *  and a missing Streamlit the one missing-package prompt, once. Asked again while it is coming (its
 *  `widget_preview` notice, a slow look meanwhile; never given up while a box shows it), and a failure
 *  again when the server's back-off is over or its cause changed (`widget_previews`). */
type PreviewHow = "board" | "card" | "hover";
interface PreviewState {
  state: string;
  url?: string;
  said?: string;
  kind?: string;
  retry_in?: number;
  missing?: Missing;
  install?: string;
}
const previews = new Map<string, PreviewState>(); // by theme and name
const previewTheme = (): string => (effectiveTheme().includes("dark") ? "dark" : "light");
const previewKey = (name: string): string => `${previewTheme()}\u0000${name}`;
const holdersOf = (name: string): HTMLElement[] => [...document.querySelectorAll<HTMLElement>(`[data-preview="${CSS.escape(name)}"]`)];
const onBoard = (name: string): boolean => holdersOf(name).some((x) => x.dataset.how === "board");

export function preview(name: string, className: string, how: PreviewHow = "board"): HTMLElement {
  const holder = h("div", { class: `${className} cvs-preview`, "data-preview": name, "data-how": how });
  paintPreview(holder, name);
  if (how === "card") seenLater(holder);
  else void askPreview(name, how === "board");
  return holder;
}

/** One line of a failure's words, short enough for a box. */
function firstLine(said: string): string {
  const line = said.split("\n").map((l) => l.trim()).find(Boolean) ?? "The preview could not be made.";
  return line.length > 110 ? `${line.slice(0, 108)}…` : line;
}

function paintPreview(holder: HTMLElement, name: string): void {
  const p = previews.get(previewKey(name));
  const how = (holder.dataset.how ?? "board") as PreviewHow;
  holder.dataset.state = p?.state ?? "coming";
  if (p?.state === "ready" && p.url) {
    const image = h("img", { src: p.url, alt: `${name}, rendered`, draggable: "false" });
    image.addEventListener("error", () => {
      // The picture is gone (its cache cleared): asked for again.
      previews.delete(previewKey(name));
      paintPreview(holder, name);
      void askPreview(name, how === "board");
    });
    clear(holder, image);
    return;
  }
  const failed = p?.state === "failed";
  const missing = failed ? p.missing : undefined;
  const words = failed ? (missing ? `Needs ${missing.packages.join(", ")} to draw.` : firstLine(p.said ?? "")) : "Preview is being made…";
  const again = !failed
    ? null
    : missing
      ? button(`Install ${missing.packages.join(", ")}`, () => void installForPreviews(p, true), { icon: "import", class: "ghost small cvs-ph-again" })
      : button("Try again", () => void askPreview(name, how === "board", true), { icon: "reset", class: "ghost small cvs-ph-again" });
  clear(
    holder,
    h(
      "div",
      { class: `cvs-ph${failed ? " failed" : ""}`, title: failed ? (p.said ?? "") : `${name}: its preview is being made` },
      h("span", { class: "cvs-ph-icon" }, icon(failed ? "warning" : "sliders")),
      how === "card" ? null : h("span", { class: "cvs-ph-name" }, name),
      h("span", { class: "cvs-ph-line", role: "status" }, words),
      how === "card" ? null : again,
    ),
  );
}

function paintAll(name: string): void {
  for (const holder of holdersOf(name)) paintPreview(holder, name);
}

/** A gallery card's preview is asked for once the card is in view (113 prebuilt widgets: never all at once,
 *  never ahead of the board's). */
let cardWatch: IntersectionObserver | null = null;
function seenLater(holder: HTMLElement): void {
  if (typeof IntersectionObserver === "undefined") return void askPreview(holder.dataset.preview ?? "", false);
  cardWatch ??= new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      cardWatch?.unobserve(entry.target);
      void askPreview((entry.target as HTMLElement).dataset.preview ?? "", false);
    }
  });
  cardWatch.observe(holder);
}

const asking = new Map<string, Promise<void>>();
const againLater = new Map<string, number>();
const prompted = new Set<string>();

function askPreview(name: string, first: boolean, retry = false): Promise<void> {
  if (!name) return Promise.resolve();
  const key = previewKey(name);
  const known = previews.get(key);
  if (!retry && known && known.state !== "coming") return Promise.resolve();
  const running = asking.get(key);
  if (running && !retry) return running;
  if (retry) {
    previews.set(key, { state: "coming" });
    paintAll(name);
  }
  const theme = previewTheme();
  const made = (async () => {
    let wait = 2000;
    let again = retry;
    for (;;) {
      let said: PreviewState;
      try {
        said = await api<PreviewState>(`/streamlit/widgets/${encodeURIComponent(name)}/preview?theme=${theme}${first ? "&first=1" : ""}${again ? "&retry=1" : ""}`);
      } catch {
        said = { state: "failed", said: "The preview could not be asked for.", kind: "setup", retry_in: 15 };
      }
      again = false;
      if (previewTheme() !== theme) return; // the theme changed meanwhile: the new theme's is asked for
      previews.set(key, said);
      paintAll(name);
      if (said.state === "failed") return void failedPreview(name, said);
      if (said.state !== "coming" || holdersOf(name).length === 0) return;
      await new Promise((r) => window.setTimeout(r, wait));
      wait = Math.min(6000, wait + 1000); // its notice usually comes first; this is the slow look meanwhile
      if (previews.get(key)?.state !== "coming") return; // its notice answered meanwhile
    }
  })().finally(() => {
    if (asking.get(key) === made) asking.delete(key);
  });
  asking.set(key, made);
  return made;
}

/** A failure: asked again once the server's back-off is over (while a box still shows it); a missing
 *  Streamlit the one prompt, once a page. */
function failedPreview(name: string, said: PreviewState): void {
  const key = previewKey(name);
  if (said.missing) {
    const once = `${said.missing.python}\u0000${said.missing.packages.join(" ")}`;
    if (!prompted.has(once)) {
      prompted.add(once);
      void installForPreviews(said, false);
    }
  }
  if (againLater.has(key)) return;
  const at = window.setTimeout(
    () => {
      againLater.delete(key);
      if (holdersOf(name).length === 0 || previews.get(key)?.state !== "failed") return;
      previews.delete(key);
      void askPreview(name, onBoard(name));
    },
    Math.max(1, said.retry_in ?? 30) * 1000,
  );
  againLater.set(key, at);
}

/** Install what the previews need (the project's Python: the Environment's Install, into its `.venv` and
 *  requirements.txt; else the app's own), then every failed preview tried again. */
async function installForPreviews(said: PreviewState, force: boolean): Promise<void> {
  if (!said.missing) return;
  const names = said.missing.packages;
  await promptInstall(said.missing, {
    force,
    install: said.install === "project" ? async () => void (await api("/environment/libraries/install", "POST", { names })) : intoApp,
    then: () => retryFailedPreviews(true),
  });
}

/** Every failed preview a box shows, asked for again (`now`: past its back-off: an install just ended). */
function retryFailedPreviews(now: boolean): void {
  const theme = previewTheme();
  for (const [key, p] of [...previews]) {
    const [keyTheme, name = ""] = key.split("\u0000");
    if (!name || keyTheme !== theme || p.state !== "failed" || holdersOf(name).length === 0) continue;
    window.clearTimeout(againLater.get(key));
    againLater.delete(key);
    previews.delete(key);
    void askPreview(name, onBoard(name), now);
  }
}

/** The server's word: one made or failed (asked again: its address or its words), or the failures may be
 *  tried again (the project's Python ready). */
export function previewNotice(said: { type: string; name?: string; theme?: string }): void {
  if (said.type === "widget_preview" && said.name && said.theme === previewTheme()) {
    const key = previewKey(said.name);
    if (holdersOf(said.name).length === 0) return void previews.delete(key);
    previews.set(key, { state: "coming" });
    void askPreview(said.name, onBoard(said.name));
  }
  if (said.type === "widget_previews") retryFailedPreviews(false);
}

/** The theme changed: every box shows the new theme's picture (asked for when it is not known). */
export function watchPreviewTheme(): void {
  new MutationObserver(() => {
    for (const holder of document.querySelectorAll<HTMLElement>("[data-preview]")) {
      const name = holder.dataset.preview ?? "";
      paintPreview(holder, name);
      void askPreview(name, holder.dataset.how === "board");
    }
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}

/** Every preview forgotten (the widgets changed: each is asked for again as its box shows). */
export function clearPreviews(): void {
  previews.clear();
}

/** What the Widgets pane asks of the page: its pane, the widgets, and an insert into the selected container. */
export interface GalleryHost {
  pane: HTMLElement;
  editable: () => boolean;
  insert: (name: string, parent: string | null) => Promise<void>;
  selectedContainer: () => string | null;
  readonly widgets: WidgetEntry[];
}

export function canvasGallery(host: GalleryHost) {
  let galleryFocus: string | null = null;
  let galleryQuery = "";

  /** Yours first, then the prebuilt ones in the server's order: the starter packs, then by group (Buttons, Inputs...). */
  const grouped = (): WidgetEntry[] => [...host.widgets].sort((a, b) => Number(a.prebuilt) - Number(b.prebuilt));

  let hoverTimer: number | null = null;
  let bigPreview: HTMLElement | null = null;
  function hidePreview(): void {
    if (hoverTimer !== null) window.clearTimeout(hoverTimer);
    hoverTimer = null;
    bigPreview?.remove();
    bigPreview = null;
  }

  function drawGallery(): void {
    const search = h("input", { type: "search", class: "cvs-gallery-search", placeholder: "Search widgets", value: galleryQuery, "aria-label": "Search widgets", "data-no-variables": "" });
    const cards = h("div", { class: "cvs-cards" });
    const draw = (): void => {
      const words = galleryQuery.toLowerCase().split(/\s+/).filter(Boolean);
      clear(cards);
      let group = "";
      for (const w of grouped().filter((x) => words.every((word) => `${x.name} ${x.description} ${x.group} ${x.pack} ${x.tags.join(" ")}`.toLowerCase().includes(word)))) {
        const heading = headingOf(w);
        if (heading !== group) {
          group = heading;
          cards.append(headingElement("cvs-gallery-group", w));
        }
        const card = h(
          "div",
          { class: `cvs-card${galleryFocus === w.name ? " focused" : ""}`, draggable: "true", tabindex: "0", role: "button", "data-widget": w.name, "aria-label": `${w.name}: ${w.description}` },
          preview(w.name, "cvs-card-preview", "card"),
          h("div", { class: "cvs-card-name" }, w.name),
          h("div", { class: "cvs-card-desc" }, w.description),
        );
        card.addEventListener("dragstart", (e) => {
          hidePreview();
          e.dataTransfer?.setData(DRAG, w.name);
          e.dataTransfer?.setData("text/plain", w.name);
        });
        card.addEventListener("focus", () => {
          galleryFocus = w.name;
          for (const c of cards.querySelectorAll(".cvs-card")) c.classList.toggle("focused", c === card);
        });
        card.addEventListener("click", () => card.focus());
        card.addEventListener("dblclick", () => {
          if (host.editable()) void host.insert(w.name, host.selectedContainer());
        });
        card.addEventListener("keydown", (e) => {
          if ((e.key === "Insert" || e.key === "Enter") && host.editable()) {
            e.preventDefault();
            e.stopPropagation();
            void host.insert(w.name, host.selectedContainer());
          }
        });
        card.addEventListener("mouseenter", () => {
          hidePreview();
          hoverTimer = window.setTimeout(() => {
            const r = card.getBoundingClientRect();
            bigPreview = h("div", { class: "cvs-big-preview", role: "tooltip" }, preview(w.name, "cvs-big-image", "hover"), h("div", { class: "cvs-card-name" }, w.name), h("div", { class: "cvs-card-desc" }, w.description));
            document.body.append(bigPreview);
            const width = 496;
            bigPreview.style.left = `${Math.max(8, r.left - width - 12)}px`;
            bigPreview.style.top = `${Math.max(8, Math.min(r.top, window.innerHeight - bigPreview.getBoundingClientRect().height - 8))}px`;
          }, 400);
        });
        card.addEventListener("mouseleave", hidePreview);
        cards.append(card);
      }
    };
    search.addEventListener("input", () => {
      galleryQuery = search.value;
      draw();
    });
    draw();
    clear(host.pane, h("div", { class: "cvs-pane-head" }, h("h2", {}, "Widgets"), button("Open the Widgets window", () => openWidgets(), { icon: "popout", iconOnly: true, class: "ghost" })), search, cards);
  }

  return { drawGallery, grouped, hidePreview, focused: (): string | null => galleryFocus };
}
