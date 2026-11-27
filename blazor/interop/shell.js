// shell.js: the small browser helpers the C# side calls through IJSRuntime ("sab.<name>").
// Nothing here holds data or a secret: the token is read from the address once, traded for the page's cookie and
// dropped (the same as the classic front end's api.ts openSession).

// The app's first window is the home window, named so another window (or the desktop app's channel) finds it
// by name (domain/desktop.py HOME_WINDOW); a window this one opened keeps the name it was given.
if (!window.name && !window.opener) window.name = "sab-home";

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
    const fragment = new URLSearchParams(location.hash.slice(1));
    const token = fragment.get("token");
    // A classic address's grid (/workspace#token=...&grid=3: a pushed table, the desktop app): kept for
    // takeStartGrid, which opens it on the Grids page.
    this.startGrid = fragment.get("grid") ?? "";
    if (token || this.startGrid) history.replaceState(null, "", location.pathname + location.search);
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

  /** The grid the address's fragment named at start (#grid=3), once; "" when none. */
  takeStartGrid() {
    const grid = this.startGrid ?? "";
    this.startGrid = "";
    return grid;
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

  /** The page's own title; the window's says it with the open project's name (the owner, 2026-11-24): "Tables ·
   *  Captive · Swiss Army Bench", Home's "Captive · Swiss Army Bench", no project as before. */
  setTitle(title) {
    this.pageTitle = title ?? "";
    this.showTitle();
  },

  /** The open project's name ("" with none), from ProjectState on every change: the title follows it at once. */
  setProject(name) {
    this.projectName = name ?? "";
    this.showTitle();
  },

  showTitle() {
    const parts = [this.pageTitle, this.projectName].filter((part, at, all) => part && all.indexOf(part) === at);
    document.title = [...parts, "Swiss Army Bench"].join(" · ");
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
      // The palette's own Enter and arrows: its list acts on them (C#); the browser's default goes, so the Enter that
      // runs a command never also presses the button of a dialog the command opens (Chrome clicks on keypress).
      if (e.target instanceof Element && e.target.id === "wb-palette-input" && ["Enter", "ArrowUp", "ArrowDown"].includes(e.key)) {
        e.preventDefault();
        return;
      }
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

  /** Zoom 100% from the palette: the Ctrl+0 the footer's zoom listens for, so its number follows. */
  zoomReset() {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "0", ctrlKey: true, bubbles: true }));
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
    // Which window this page is now (home, notebooks, scripts, tables...): said as the socket opens and as the
    // page moves, so the agent's commands reach the open Notebooks or Scripts page; and when the window comes to
    // the front (the one the user was last in is the one told).
    let kind = null;
    const say = (message) => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
    };
    const front = () => say({ type: "focus" });
    const open = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/ws${query ? `?${query}` : ""}`, ["swissarmybench"]);
      socket.onopen = () => {
        if (kind) say({ type: "window", kind });
        listener.invokeMethodAsync("Opened");
      };
      socket.onmessage = (event) => listener.invokeMethodAsync("Notice", String(event.data));
      socket.onclose = () => {
        listener.invokeMethodAsync("Closed");
        if (!stopped) setTimeout(open, 2000);
      };
    };
    open();
    window.addEventListener("focus", front);
    // A window that is going away (closed; the desktop app keeps its page a moment longer) lets go of its socket at
    // once, so the server never asks a window that can no longer answer (the project's Save waited a minute for
    // one). A page that comes back (the browser's Back cache) opens it again by itself.
    window.addEventListener("pagehide", () => socket?.close());
    return {
      place: (now) => {
        kind = now;
        say({ type: "window", kind });
      },
      /** A line this window sends the server (what it shows: Layout/ScreenReporter); false while the socket is shut. */
      send: (text) => {
        if (socket?.readyState !== WebSocket.OPEN) return false;
        socket.send(text);
        return true;
      },
      stop: () => {
        stopped = true;
        window.removeEventListener("focus", front);
        socket?.close();
      },
    };
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
    // A press on the dimmed page beside the dialog keeps the focus where it is (it used to go to the page, and
    // Escape, Enter and Tab no longer reached the dialog).
    dialog.parentElement?.addEventListener("mousedown", (event) => {
      if (!dialog.contains(event.target)) event.preventDefault();
    });
  },

  /** A page's full screen (the Notebooks and Scripts pages' F11, the Canvas's): `kind` on the body (the page's own
   *  CSS hides what goes) and body.page-full; in the desktop app the window itself (its channel's sabApp.fullScreen),
   *  in a browser its Fullscreen API, a refusal harmless (the page is full screen inside the window all the same).
   *  The browser's own Escape out of it tells the page (window.sabFullScreen, the page's toggle). */
  fullScreen(on, kind) {
    document.body.classList.toggle(kind, !!on);
    document.body.classList.toggle("page-full", !!on);
    if (window.sabApp?.app === true) {
      window.sabApp.fullScreen?.(!!on);
      return;
    }
    try {
      if (on && !document.fullscreenElement) document.documentElement.requestFullscreen?.()?.catch(() => {});
      else if (!on && document.fullscreenElement) document.exitFullscreen?.()?.catch(() => {});
    } catch {
      // no Fullscreen API here: the page alone
    }
  },

  /** A window over the page keeps the focus inside it (What's New): it goes to the window, and Tab and Shift+Tab
   *  go round its buttons, links and folds, never out to the page behind. */
  keepFocus(dialog) {
    if (!dialog) return;
    const inside = () => [...dialog.querySelectorAll("button, [href], summary, input, select, textarea, [tabindex]:not([tabindex='-1'])")].filter((e) => !e.disabled && e.offsetParent !== null);
    dialog.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      const all = inside();
      if (all.length === 0) return;
      const first = all[0];
      const last = all[all.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    (dialog.querySelector(".dialog-foot .btn.primary") ?? dialog).focus();
  },

  /** Whether the focus is in a box the user types in (an input, a text area, a list, an editable part). */
  typing() {
    const at = document.activeElement;
    return Boolean(at && at.matches("input, textarea, select, [contenteditable='true']"));
  },

  /** The first element under `root` that matches `selector` takes the focus (a palette's chosen colour). */
  focusFirst(root, selector) {
    root?.querySelector(selector)?.focus();
  },

  /** The focus moves `step` places among `root`'s elements that match `selector` (the arrow keys of a palette or
   *  a list), round from the end to the start. */
  moveFocus(root, selector, step) {
    const all = [...(root?.querySelectorAll(selector) ?? [])];
    if (all.length === 0) return;
    const at = all.indexOf(document.activeElement);
    all[((at < 0 ? 0 : at + step) + all.length) % all.length].focus();
  },

  /** Back (-1) or Forward (1) in this window's history: the agent's app_navigate back and forward. */
  historyGo(by) {
    history.go(by);
  },

  /** This window's name: sab-home is the app's first window (a .sql file's run brings the Tables page there). */
  windowName() {
    return window.name;
  },

  /** Pop out (the owner, 2026-11-27: any page or table in a window of its own; State/PopOuts.cs): a popped-out
   *  window is named sab-pop:<key>, so every window finds it by name, and this window keeps each one it opened to
   *  see it close (a reload never counts: the window is still there). */
  popOut: {
    PREFIX: "sab-pop:",
    opened: new Map(),
    timer: null,

    /** The key this window holds ("" for a window that is not popped out). */
    own() {
      return window.name.startsWith(this.PREFIX) ? window.name.slice(this.PREFIX.length) : "";
    },

    /** The address in a window of its own: the desktop app's own window, a browser's own tab. False when blocked. */
    open(key, address, listener) {
      const opened = window.open(new URL(address, document.baseURI).href, this.PREFIX + key);
      if (!opened) return false;
      this.opened.set(key, opened);
      opened.focus?.();
      this.timer ??= setInterval(() => {
        for (const [held, win] of this.opened) {
          if (!win.closed) continue;
          this.opened.delete(held);
          listener.invokeMethodAsync("WindowClosedAsync", held).catch(() => {});
        }
      }, 400);
      return true;
    },

    /** The popped-out window to the front: the one this window opened, else found by its name (a browser's; never
     *  a blank one made by the asking). */
    show(key) {
      let win = this.opened.get(key);
      if ((!win || win.closed) && window.sabApp?.app !== true) {
        win = window.open("", this.PREFIX + key);
        try {
          if (win && win.location.href === "about:blank") {
            win.close();
            win = null;
          }
        } catch {
          win = null;
        }
      }
      if (win && !win.closed) win.focus();
    },

    /** The window this one opened for `key`, closed (Reattach: it closes itself too). */
    close(key) {
      const win = this.opened.get(key);
      this.opened.delete(key);
      if (win && !win.closed) win.close();
    },

    /** An address in the main window (found by its name, else a new one), brought to the front. */
    toMain(address) {
      const main = window.open(new URL(address, document.baseURI).href, "sab-home");
      main?.focus?.();
      return !!main;
    },

    focusSelf() {
      window.focus();
    },

    /** The window that opened this one, to the front (it took a link this window handed over). */
    focusOpener() {
      try {
        window.opener?.focus?.();
      } catch {
        /* another origin's opener: nothing to raise */
      }
    },

    closeSelf() {
      window.close();
    },

    /** The page drawn alone (no rail): CSS reads the class. */
    mark(kind) {
      document.body.classList.add("popped-out");
      if (kind) document.body.dataset.popped = kind;
    },
  },

  /** A page of the app in a window of its own, reused by its name (the Queries window); false when blocked. */
  openWindow(url, name, features) {
    const opened = window.open(url, name, features);
    if (!opened) return false;
    opened.focus();
    return true;
  },

  /** An HTML output's frame as tall as its content (at most 640 px): its own page grows to the frame's, so it is
   *  measured once it has loaded. */
  fitFrame(frame) {
    const body = frame.contentDocument?.body;
    if (body) frame.style.height = `${Math.min(Math.ceil(body.getBoundingClientRect().height) + 6, 640)}px`;
  },
};

// Alt+Home goes Home (the Projects page) from anywhere (the classic nav.ts mountNav): the rail's Home link is
// clicked, so the move is the router's own (Back returns).
document.addEventListener("keydown", (e) => {
  if (!e.altKey || e.ctrlKey || e.metaKey || e.key !== "Home") return;
  const home = document.querySelector(".nav-rail-item[data-area=projects]");
  if (!home) return;
  e.preventDefault();
  e.stopPropagation();
  home.click();
}, { capture: true });

// The browser's own way out of full screen (its Escape, its bar): the page in full screen leaves its own too.
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && document.body.classList.contains("page-full")) window.sabFullScreen?.(false);
});
