// documents.js: a text document's tab on the Scripts page (Pages/Workbench/Docs): the Markdown reader's clicks and
// keys (a block becomes its source text; a task box ticks; a link opens), its code blocks coloured, the walled-off
// frame an HTML page or an SVG picture is drawn in, the preview scrolling with its source, a diagram's picture.
import { toPng } from "html-to-image";

// The page's own codeEditor.js beside this file (one Monaco for the page), never bundled in here.
let editors = null;
const codeEditor = () => (editors ??= import(new URL("./codeEditor.js", import.meta.url).href));

// ===== the Markdown reader =====

/**
 * The reader's own clicks and keys, told to C# by block: Edit(block) for a click on a block's words (never while
 * text is being selected), Tick(block, task) for a task box, Follow(href) for a link to another file of the
 * project; a web link opens as any link does. Enter or F2 on a focused block edits it.
 */
export function reader(host, dotnet) {
  const blockOf = (node) => node.closest?.("[data-block]");
  const click = (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const block = target ? blockOf(target) : null;
    if (!target || !block || !host.contains(block) || target.closest("textarea")) return;
    const index = Number(block.dataset.block);
    const box = target.closest("input[data-task]");
    if (box) {
      event.preventDefault(); // the file says whether it is ticked: drawn again from it
      dotnet.invokeMethodAsync("Tick", index, Number(box.dataset.task)).catch(() => {});
      return;
    }
    const link = target.closest("a[href]");
    if (link) {
      const href = link.getAttribute("href") ?? "";
      if (link.dataset.file !== undefined) {
        event.preventDefault();
        dotnet.invokeMethodAsync("Follow", href).catch(() => {});
      }
      return; // a web link opens by itself
    }
    if (host.dataset.editable !== "true" || (window.getSelection()?.toString() ?? "").length > 0) return;
    dotnet.invokeMethodAsync("Edit", index).catch(() => {});
  };
  const key = (event) => {
    const block = event.target instanceof Element && event.target.matches("[data-block]") ? event.target : null;
    if (!block || host.dataset.editable !== "true" || (event.key !== "Enter" && event.key !== "F2")) return;
    event.preventDefault();
    dotnet.invokeMethodAsync("Edit", Number(block.dataset.block)).catch(() => {});
  };
  host.addEventListener("click", click);
  host.addEventListener("keydown", key);
  return {
    stop: () => {
      host.removeEventListener("click", click);
      host.removeEventListener("keydown", key);
    },
  };
}

/** The block being edited: its box as tall as its text, the cursor in it. */
export function editing(box) {
  if (!box) return;
  const fit = () => {
    box.style.height = "auto";
    box.style.height = `${box.scrollHeight + 2}px`;
  };
  box.addEventListener("input", fit);
  fit();
  box.focus();
  box.setSelectionRange(box.value.length, box.value.length);
}

/** Every fenced code block under `root` coloured once (Monaco's colouriser, loaded only when a block shows). */
export async function highlight(root) {
  const blocks = [...(root?.querySelectorAll("pre code[data-lang]:not([data-coloured])") ?? [])];
  if (blocks.length === 0) return;
  const editor = await codeEditor();
  for (const block of blocks) {
    block.dataset.coloured = "1";
    try {
      block.innerHTML = await editor.colorize(block.textContent ?? "", block.dataset.lang, document.documentElement.dataset.theme);
    } catch {
      /* left plain: its text is already shown */
    }
  }
}

// ===== the walled-off frame (an HTML page, an SVG picture) =====

/**
 * A page drawn in a frame of its own: the HTML cells' frame (/blazor/design.html: sandboxed without the app's
 * origin, its policy letting nothing load over the network), so a script in the file cannot reach the app, its
 * cookie, its storage or the user's data. A new frame each time: the old page's scripts stop.
 */
export function frame(stage) {
  let shown = null;
  let html = "";
  const listener = (event) => {
    if (shown && event.source === shown.contentWindow && event.data === "sab-design-ready") shown.contentWindow.postMessage(html, "*");
  };
  window.addEventListener("message", listener);
  return {
    show: (next) => {
      html = next;
      const fresh = document.createElement("iframe");
      fresh.className = "wb-preview-frame";
      fresh.setAttribute("sandbox", "allow-scripts");
      fresh.title = "Preview";
      fresh.referrerPolicy = "no-referrer";
      fresh.src = "/blazor/design.html";
      shown = fresh;
      stage.replaceChildren(fresh);
    },
    stop: () => {
      window.removeEventListener("message", listener);
      shown = null;
      stage.replaceChildren();
    },
  };
}

// ===== source beside preview =====

/** Split view: the preview scrolls with its source and the source with its preview (by how far down each is). */
export async function link(source, preview) {
  const editor = await codeEditor();
  let from = "";
  let quiet = 0;
  const lead = (who) => {
    if (from && from !== who && performance.now() < quiet) return false;
    from = who;
    quiet = performance.now() + 120;
    return true;
  };
  const scroll = editor.scrollLink(source, (part) => {
    if (lead("source")) preview.scrollTop = part * Math.max(0, preview.scrollHeight - preview.clientHeight);
  });
  const follow = () => {
    const most = preview.scrollHeight - preview.clientHeight;
    if (most > 0 && lead("preview")) scroll?.to(preview.scrollTop / most);
  };
  preview.addEventListener("scroll", follow, { passive: true });
  return {
    stop: () => {
      preview.removeEventListener("scroll", follow);
      scroll?.stop();
    },
  };
}

/** A preview's problem marked on its source's line (none: the mark taken away). */
export async function problem(source, line, message) {
  if (!source) return;
  (await codeEditor()).previewProblem(source, line ?? 0, message ?? "");
}

// ===== a diagram's picture =====

/** The drawn diagram as SVG text ("" when nothing is drawn). */
export function svgOf(host) {
  const svg = host?.querySelector("svg");
  if (!svg) return "";
  const copy = svg.cloneNode(true);
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  return new XMLSerializer().serializeToString(copy);
}

/** The drawn diagram as a PNG (base64, no prefix; "" when nothing is drawn), on the page's own background. */
export async function pngOf(host) {
  const svg = host?.querySelector("svg");
  if (!svg) return "";
  const url = await toPng(host, { pixelRatio: 2, cacheBust: false, backgroundColor: getComputedStyle(document.body).backgroundColor });
  return url.slice(url.indexOf(",") + 1);
}
