// shell.js: the small browser helpers the C# side calls through IJSRuntime ("sab.<name>").
// Nothing here holds data or a secret: the token is read from the address once, traded for the page's cookie and
// dropped (the same as the classic front end's api.ts openSession).

/** A refusal's one sentence (domain/refusals.py's shape), else the answer's text. */
async function refusalWords(answer) {
  const text = await answer.text();
  try {
    return JSON.parse(text).error ?? text;
  } catch {
    return text;
  }
}

window.sab = {
  /** The page's session: the #token in the address (never sent to the server by the browser) bought once for the
   *  page's cookie, then the address cleaned; or the cookie this browser already holds. True when it worked. */
  async openSession() {
    const token = new URLSearchParams(location.hash.slice(1)).get("token");
    if (token) history.replaceState(null, "", location.pathname + location.search);
    try {
      if (token) {
        const minted = await fetch("/session", { method: "POST", headers: { Authorization: `Bearer ${token}` } });
        if (minted.ok) return true;
      }
      return (await fetch("/session")).ok;
    } catch {
      return false;
    }
  },

  /** The theme the system prefers right now ("light" or "dark"), and every change after (to the C# listener). */
  systemTheme(listener) {
    const query = matchMedia("(prefers-color-scheme: dark)");
    if (listener) query.addEventListener("change", () => listener.invokeMethodAsync("SystemThemeChangedAsync", query.matches ? "dark" : "light"));
    return query.matches ? "dark" : "light";
  },

  setTheme(theme) {
    document.documentElement.dataset.theme = theme;
  },

  setRailNames(on) {
    document.documentElement.classList.toggle("rail-names", on);
    // The page's width changed: the grid, Monaco and the charts measure again.
    requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  },

  /** This browser's own small memory (a remembered tab or theme); empty when storage is blocked. */
  recall(key) {
    try {
      return localStorage.getItem(`sab.blazor.${key}`);
    } catch {
      return null;
    }
  },

  remember(key, value) {
    try {
      localStorage.setItem(`sab.blazor.${key}`, value);
    } catch {
      /* storage blocked: the choice lasts this page only */
    }
  },

  async copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  },

  setTitle(title) {
    document.title = title ? `${title} · Swiss Army Bench` : "Swiss Army Bench";
  },

  click(selector) {
    document.querySelector(selector)?.click();
  },

  focus(selector) {
    document.querySelector(selector)?.focus();
  },

  /** A box that opens a pasted table at once: a paste of more than one line goes to the C# listener. */
  onTablePaste(box, listener) {
    box.addEventListener("paste", (event) => {
      const text = event.clipboardData?.getData("text/plain") ?? "";
      if (!text.includes("\n")) return;
      event.preventDefault();
      box.value = text;
      listener.invokeMethodAsync("Pasted", text);
    });
  },

  /** Ctrl+V of a table (tab-separated lines) anywhere but a text box or an editor: told to the C# listener, which
   *  opens it as a new table. Returns what stops listening. */
  pagePaste(listener) {
    const heard = (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest("input, textarea, .monaco-editor")) return;
      const text = event.clipboardData?.getData("text/plain") ?? "";
      if (!(text.includes("\t") && text.includes("\n"))) return;
      event.preventDefault();
      listener.invokeMethodAsync("PastedTable", text);
    };
    document.addEventListener("paste", heard);
    return { stop: () => document.removeEventListener("paste", heard) };
  },

  /** Text sent as a request's body (a pasted table); a refusal is thrown with its words. */
  async postText(url, text) {
    const answer = await fetch(url, { method: "POST", body: text });
    if (!answer.ok) throw new Error(await refusalWords(answer));
  },

  /** Files dropped anywhere on the page: each kept here by a number and told to the C# listener, which asks for
   *  a workbook's sheets (droppedSheets) and sends each table (dropAs). A tab dragged between tabs is not a file. */
  fileDrop(listener) {
    const dropped = new Map();
    let next = 0;
    const hasFiles = (event) => Array.from(event.dataTransfer?.types ?? []).includes("Files");
    document.addEventListener("dragover", (event) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      document.body.classList.add("dropping-file");
    });
    document.addEventListener("dragleave", (event) => {
      if (!event.relatedTarget) document.body.classList.remove("dropping-file");
    });
    document.addEventListener("drop", (event) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      document.body.classList.remove("dropping-file");
      for (const file of Array.from(event.dataTransfer?.files ?? [])) {
        next += 1;
        dropped.set(next, file);
        listener.invokeMethodAsync("Dropped", next, file.name);
      }
    });
    const send = async (url, file) => {
      const answer = await fetch(url, { method: "POST", body: await file.arrayBuffer() });
      if (!answer.ok) throw new Error(await refusalWords(answer));
      return answer;
    };
    window.sab.droppedSheets = async (id) => {
      const file = dropped.get(id);
      return (await (await send(`/files/dropped-sheets?filename=${encodeURIComponent(file.name)}`, file)).json()).sheets;
    };
    window.sab.dropAs = async (id, name, sheet) => {
      const file = dropped.get(id);
      const part = sheet ? `&sheet=${encodeURIComponent(sheet)}` : "";
      await send(`/datasets/${encodeURIComponent(name)}/drop?filename=${encodeURIComponent(file.name)}${part}`, file);
    };
    window.sab.forgetDropped = (id) => dropped.delete(id);
  },

  /** Whether the keys are going to a text box or an editor (the page's own shortcuts leave them alone). */
  typing() {
    return Boolean(document.activeElement?.closest("input, textarea, select, [contenteditable], .monaco-editor"));
  },

  /** The focus moved `by` places among the elements `selector` finds (wrapping round); none focused: the first. */
  moveFocus(selector, by) {
    const all = [...document.querySelectorAll(selector)].filter((e) => e.offsetParent !== null);
    if (!all.length) return;
    const at = all.indexOf(document.activeElement);
    all[at < 0 ? 0 : (at + by + all.length) % all.length].focus();
  },

  /** The app's keys (the classic mountGridCommands and mountShortcutKeys): Ctrl+Shift+P the palette; ? (outside a
   *  text box) and Ctrl+/ (outside an editor) the shortcuts; Ctrl+K Find data where a page offers it. */
  commandKeys(listener) {
    const typing = (t) => t instanceof Element && t.closest("input, textarea, select, [contenteditable]:not([contenteditable=false]), .monaco-editor") !== null;
    const heard = (e) => {
      if (e.defaultPrevented || e.altKey) return;
      const ctrl = e.ctrlKey || e.metaKey;
      let which = null;
      if (ctrl && e.shiftKey && e.key.toLowerCase() === "p") which = "palette";
      else if (ctrl && !e.shiftKey && e.key.toLowerCase() === "k") which = "find";
      else if (!typing(e.target) && !document.querySelector(".dialog") && ((e.key === "?" && !ctrl) || (ctrl && (e.key === "/" || e.code === "Slash")))) which = "shortcuts";
      if (!which) return;
      e.preventDefault();
      listener.invokeMethodAsync("Wanted", which);
    };
    document.addEventListener("keydown", heard);
    return { stop: () => document.removeEventListener("keydown", heard) };
  },

  /** The app's one zoom: the page's text, icons and the grid's rows scaled (the browser's own zoom is taken over). */
  setZoom(zoom) {
    document.documentElement.style.zoom = String(zoom);
    requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  },

  /** Ctrl+= / Ctrl++ / Ctrl+- / Ctrl+0 and Ctrl + wheel told to the C# listener (Zoom: +1, -1, 0 to reset). */
  zoomKeys(listener) {
    const keys = (e) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey || e.target?.closest?.("[data-own-zoom]")) return;
      const by = e.key === "=" || e.key === "+" ? 1 : e.key === "-" || e.key === "_" ? -1 : e.key === "0" ? 0 : null;
      if (by === null) return;
      e.preventDefault();
      e.stopPropagation();
      listener.invokeMethodAsync("Zoom", by);
    };
    let pending = 0;
    const wheel = (e) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      pending += e.deltaY;
      if (Math.abs(pending) < 40) return;
      listener.invokeMethodAsync("Zoom", pending < 0 ? 1 : -1);
      pending = 0;
    };
    document.addEventListener("keydown", keys, { capture: true });
    document.addEventListener("wheel", wheel, { capture: true, passive: false });
    return { stop: () => { document.removeEventListener("keydown", keys, { capture: true }); document.removeEventListener("wheel", wheel, { capture: true }); } };
  },

  /** A box takes the focus with its words selected (a name renamed in place). */
  focusSelect(selector) {
    const box = document.querySelector(selector);
    box?.focus();
    box?.select?.();
  },

  /** Text saved by the browser as a file (Export outline's Download). */
  saveText(name, text) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
  },

  /** A file the server answers with, fetched first (so a refusal is said in place, not saved as a file), then saved
   *  by the browser under the server's name; the answer's X-Export-Message words, if any. */
  async fetchDownload(url) {
    const answer = await fetch(url);
    if (!answer.ok) throw new Error(await refusalWords(answer));
    const name = /filename="([^"]+)"/.exec(answer.headers.get("Content-Disposition") ?? "")?.[1] ?? "export";
    const blob = await answer.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
    return answer.headers.get("X-Export-Message") ?? "";
  },

  /** A file the server answered with (an export), saved by the browser's own download. */
  download(url) {
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.append(a);
    a.click();
    a.remove();
  },

  /** The live-updates socket (/ws): each notice handed to the C# listener as JSON text; it opens again by itself. */
  live(listener, query) {
    let socket = null;
    let stopped = false;
    const open = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/ws${query ? `?${query}` : ""}`, ["swissarmybench"]);
      socket.onopen = () => listener.invokeMethodAsync("Opened");
      socket.onmessage = (event) => listener.invokeMethodAsync("Notice", String(event.data));
      socket.onclose = () => {
        listener.invokeMethodAsync("Closed");
        if (!stopped) setTimeout(open, 2000);
      };
    };
    open();
    return { stop: () => { stopped = true; socket?.close(); } };
  },

  /** A menu's keys (the classic dom.ts showMenu): its first line takes focus, the arrows, Home and End move
   *  between its lines (greyed-out ones skipped); Enter runs one and Escape closes it (the component's own). */
  menuKeys(menu) {
    const lines = () => [...menu.querySelectorAll("[role=menuitem]:not([disabled])")];
    lines()[0]?.focus();
    menu.addEventListener("keydown", (event) => {
      const all = lines();
      const at = all.indexOf(document.activeElement);
      const to = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: all.length - 1 }[event.key];
      if (to === undefined || all.length === 0) return;
      event.preventDefault();
      all[(to + all.length) % all.length].focus();
    });
  },

  /** A dialog just opened: the focus goes into it (its first empty field, else its first field, else its first
   *  button past Close), so Enter and Escape reach it and Tab starts there. */
  dialogOpened(dialog) {
    const fields = [...dialog.querySelectorAll("input:not([type=checkbox]):not([type=radio]), select, textarea")].filter((f) => !f.disabled && f.offsetParent !== null);
    const first = fields.find((f) => f instanceof HTMLInputElement && !f.value) ?? fields[0];
    const target = first ?? dialog.querySelector(".dialog-foot button, .dialog button:not([aria-label=Close])") ?? dialog;
    target.focus();
  },

  /** An HTML output's frame as tall as its content (at most 640 px): its own page grows to the frame's, so it is
   *  measured once it has loaded. */
  fitFrame(frame) {
    const body = frame.contentDocument?.body;
    if (body) frame.style.height = `${Math.min(Math.ceil(body.getBoundingClientRect().height) + 6, 640)}px`;
  },
};
