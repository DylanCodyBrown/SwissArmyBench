// shell.js: the small browser helpers the C# side calls through IJSRuntime ("sab.<name>").
// Nothing here holds data or a secret: the token is read from the address once, traded for the page's cookie and
// dropped (the same as the classic front end's api.ts openSession).

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

  focus(selector) {
    document.querySelector(selector)?.focus();
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
