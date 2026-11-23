// workbench.js: the Notebooks and Scripts pages' own keys and the tab groups' sashes (the classic
// workbenchCommands.ts keys and workbenchGroups.ts sash), for the WorkbenchPage component.

// The page's keys: told to C# by name. The ones an editor keeps for itself (Save, Save as, F5) are told only when no
// editor has the focus (the editor tells its own); the others win over Monaco's (taken before it sees them).
const KEYS = [
  { name: "palette", ctrl: true, shift: true, key: "p", always: true },
  { name: "palette", key: "F1", always: true },
  { name: "splitRight", ctrl: true, key: "\\", always: true },
  { name: "nextDoc", ctrl: true, key: "PageDown", always: true },
  { name: "previousDoc", ctrl: true, key: "PageUp", always: true },
  { name: "fullScreen", key: "F11", always: true },
  { name: "open", ctrl: true, key: "o", always: true },
  { name: "files", ctrl: true, key: "b", always: true },
  { name: "searchScripts", ctrl: true, shift: true, key: "f", always: true },
  { name: "debug", ctrl: true, shift: true, key: "d", always: true },
  { name: "save", ctrl: true, key: "s" },
  { name: "saveAs", ctrl: true, shift: true, key: "s" },
  { name: "run", key: "F5" },
  { name: "escape", key: "Escape" },
  { name: "nextPane", key: "F6", always: true },
  { name: "previousPane", shift: true, key: "F6", always: true },
  { name: "source", ctrl: true, key: "1", always: true },
  { name: "explorer", ctrl: true, shift: true, key: "e", always: true },
];

function named(event) {
  const ctrl = event.ctrlKey || event.metaKey;
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  return KEYS.find((k) => !!k.ctrl === ctrl && !!k.shift === event.shiftKey && !event.altKey && k.key.toLowerCase() === key.toLowerCase());
}

/** The page's keys for as long as it is open: stop() lets them go. */
export function keys(dotnet) {
  const listener = (event) => {
    const found = named(event);
    if (!found) return;
    const inEditor = !!event.target.closest?.(".monaco-editor");
    const inField = ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) && !inEditor;
    if (!found.always && (inEditor || (inField && found.name !== "save" && found.name !== "saveAs"))) return;
    if (found.name === "escape" && inField) return;
    // Escape in a dialog, an overlay or a pane is theirs (Close, a lineage, the help card, the explorer's flyout).
    if (found.name === "escape" && event.target.closest?.("[role=dialog], [role=menu], .wb-explorer, .structure-doc, .wb-lineage-shade")) return;
    event.preventDefault();
    event.stopPropagation();
    // F1 in an editor is help on the name at the cursor; elsewhere every command (the classic keys).
    const name = found.name === "palette" && found.key === "F1" && inEditor ? "help" : found.name;
    dotnet.invokeMethodAsync("PageKey", name).catch(() => {});
  };
  window.addEventListener("keydown", listener, true);
  return { stop: () => window.removeEventListener("keydown", listener, true) };
}

/** A sash between two groups: dragged, the share of the pair's room before it goes to C# as it moves. */
export function sash(element, dotnet, row) {
  element.addEventListener("pointerdown", (down) => {
    const before = element.previousElementSibling;
    const after = element.nextElementSibling;
    if (!before || !after) return;
    down.preventDefault();
    element.setPointerCapture(down.pointerId);
    const a = before.getBoundingClientRect();
    const b = after.getBoundingClientRect();
    const start = row ? a.left : a.top;
    const room = row ? b.right - a.left : b.bottom - a.top;
    const move = (event) => {
      const fraction = ((row ? event.clientX : event.clientY) - start) / room;
      before.style.flex = `${fraction} 1 0px`;
      after.style.flex = `${1 - fraction} 1 0px`;
      element.dataset.fraction = String(fraction);
    };
    const up = () => {
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", up);
      if (element.dataset.fraction) dotnet.invokeMethodAsync("Resized", Number(element.dataset.fraction)).catch(() => {});
    };
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", up);
  });
}

/** The page full screen (F11): the rail, the top bar and the side panes go (body.wb-full). */
export function fullScreen(on) {
  document.body.classList.toggle("wb-full", !!on);
}

/** Where a control is on screen, for a menu opened under it. */
export function under(element) {
  const box = element.getBoundingClientRect();
  return [box.left, box.bottom + 2, box.right];
}

// An HTML cell's design (the classic workbenchHtml.ts designPane): drawn in a frame of its own, sandboxed (its
// scripts run, but not as the app's origin: it cannot reach the app, its cookie, its storage or the user's data), whose
// page (/static/design.html) loads nothing over the network. The page's HTML goes in once the frame says it is ready;
// the design tells its own height back.
const REPORTER =
  `<script>(function(){var last=0;function say(){var h=Math.ceil(Math.max(document.documentElement.scrollHeight,` +
  `document.body?document.body.scrollHeight:0));if(h!==last){last=h;parent.postMessage({sabDesignHeight:h},"*")}}` +
  `addEventListener("load",say);if(window.ResizeObserver)new ResizeObserver(say).observe(document.documentElement);` +
  `setTimeout(say,0)})()</script>`;

function designPage(html, dark) {
  const ink = dark ? "#e8ecef" : "#1c2228";
  const line = dark ? "#343c45" : "#d5dbe1";
  const base = `<style>html{color-scheme:${dark ? "dark" : "light"}}body{margin:12px;font:14px/1.45 "Segoe UI",system-ui,sans-serif;color:${ink};background:transparent}
.sab-table{border-collapse:collapse;font-size:13px}.sab-table th,.sab-table td{padding:3px 10px;border-bottom:1px solid ${line};text-align:left}.sab-table thead th{border-bottom-width:2px}
.sab-table caption{caption-side:bottom;text-align:left;font-size:12px;opacity:.75;padding-top:6px}</style>`;
  return `<!doctype html><meta charset="utf-8">${base}${html}${REPORTER}`;
}

export function design(stage, dotnet) {
  let frame = null;
  let html = "";
  let dark = false;
  const listener = (event) => {
    if (!frame || event.source !== frame.contentWindow) return;
    if (event.data === "sab-design-ready") frame.contentWindow.postMessage(designPage(html, dark), "*");
    else if (event.data && typeof event.data.sabDesignHeight === "number") dotnet.invokeMethodAsync("Fits", event.data.sabDesignHeight).catch(() => {});
  };
  window.addEventListener("message", listener);
  return {
    // A new frame each time: the old design's scripts stop, and the new one starts clean.
    show: (next, darkTheme) => {
      html = next;
      dark = !!darkTheme;
      const fresh = document.createElement("iframe");
      fresh.className = "wb-design-frame";
      fresh.setAttribute("sandbox", "allow-scripts");
      fresh.title = "Design";
      fresh.referrerPolicy = "no-referrer";
      fresh.src = "/static/design.html";
      frame = fresh;
      stage.replaceChildren(fresh);
    },
    stop: () => {
      window.removeEventListener("message", listener);
      frame = null;
      stage.replaceChildren();
    },
  };
}

/** A grip dragged up or down: the height it reaches goes to C# when the drag ends (Resized). */
export function grip(element, dotnet) {
  element.addEventListener("pointerdown", (down) => {
    down.preventDefault();
    element.setPointerCapture(down.pointerId);
    const stage = element.parentElement?.querySelector(".wb-design-stage");
    const from = stage ? stage.getBoundingClientRect().height : 160;
    const y = down.clientY;
    let height = from;
    const move = (event) => {
      height = from + event.clientY - y;
      if (stage) stage.style.height = `${Math.max(60, height)}px`;
    };
    const up = () => {
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", up);
      dotnet.invokeMethodAsync("Resized", height).catch(() => {});
    };
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", up);
  });
}

/** F6 and Shift+F6: the focus to the next or previous pane of the page (the code, the side panes, the status bar). */
export function cyclePane(by) {
  const panes = [...document.querySelectorAll(".wb-group.focused .wb-gbody, .wb-explorer, .side-pane, .wb-status")]
    .filter((p) => p.getClientRects().length);
  if (!panes.length) return;
  const now = panes.findIndex((p) => p.contains(document.activeElement));
  const next = panes[(now + by + panes.length) % panes.length];
  const target = next.querySelector(".monaco-editor textarea, button, input, [tabindex]") ?? next;
  target.focus?.();
}
