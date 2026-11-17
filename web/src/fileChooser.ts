/**
 * fileChooser.ts: pick a file or folder on this computer by its real path (a browser's own picker hides the
 * path). Every pick in the app comes here (Open file, Open project, the Workbench's Open and Save as, Locate,
 * Settings' folders, Add API's document, a connection's file fields, imports, exports). [WIRE]
 *
 * ROUTING: [SYSTEM] -> GET /dialogs, POST /dialogs/choose   (the system's own dialog, opened by the server)
 *          [LIST]   -> GET /folders?path=&suffixes=&kind=&hidden=, POST /folders/new, POST /dialogs/recent
 *
 *   [SYSTEM]  first: when this computer's dialogs open (GET /dialogs, asked once), the system's own dialog
 *             and nothing of the page's; a cancel is null; one that cannot open falls back to the page's
 *   [PLACES]  the page's own picker: Home, Desktop, Documents, Downloads, Projects, Library, this kind of
 *             pick's recent folders, the drives
 *   [PATH]    the breadcrumb (each part a click) and the path box (Enter goes); Up; Filter as you type;
 *             New folder (folder and save); Hidden files
 *   [LIST]    folders, then files of the wanted kinds: name, modified, size. A click selects, a double-click
 *             (or Enter) opens a folder or picks a file; arrows, Home, End, Backspace up, Escape closes
 *   [SAVE]    a file name box, for Save as: the folder shown plus that name
 */
import { api } from "./api";
import { button, clear, formatCount, h, icon, openDialog, toast } from "./dom";

interface Entry {
  name: string;
  path: string;
  size?: number;
  modified?: number;
}

interface Place {
  name: string;
  path: string;
  kind: string;
}

interface Listing {
  path: string;
  parent: string | null;
  folders: Entry[];
  files: Entry[];
  roots: string[];
  home: string;
  separator?: string;
  places?: Place[];
}

export interface ChooseOptions {
  title: string;
  /** "file" picks a file, "folder" the folder shown, "save" a new or existing file's path. */
  mode: "file" | "folder" | "save";
  /** File kinds to show, as [".csv", ".xlsx"]; none: every file. */
  suffixes?: string[];
  /** Where to start: a file's path starts in its folder. */
  start?: string;
  /** Save: the name to start with. */
  name?: string;
  /** The kind of pick, for its recent folders (default: the mode and the file kinds). */
  kind?: string;
}

interface SystemAnswer {
  path?: string;
  cancelled?: boolean;
  busy?: boolean;
  unavailable?: string;
}

const size = (bytes: number): string =>
  bytes < 1024 ? `${bytes} B` : bytes < 1024 ** 2 ? `${formatCount(Math.round(bytes / 1024))} KB` : `${(bytes / 1024 ** 2).toFixed(1)} MB`;

const PLACE_ICONS: Record<string, string> = {
  home: "user",
  desktop: "desktop",
  documents: "file",
  downloads: "import",
  projects: "project",
  library: "book",
  recent: "clock",
  drive: "data",
};

/** The kind of pick, as the server names it (domain/file_dialogs.py kind_of): "file:.csv,.xlsx". */
export function kindOf(options: ChooseOptions): string {
  if (options.kind) return options.kind;
  const kinds = options.mode === "folder" ? [] : [...new Set((options.suffixes ?? []).map((s) => s.toLowerCase()))].sort();
  return kinds.length ? `${options.mode}:${kinds.join(",")}` : options.mode;
}

/** A folder's path as its breadcrumb's parts, each with the path it opens. */
export function crumbs(path: string, separator = "/"): { name: string; path: string }[] {
  const windows = separator === "\\" || /^[A-Za-z]:[\\/]/.test(path) || path.startsWith("\\\\");
  const sep = windows ? "\\" : "/";
  const parts = path.split(/[\\/]+/).filter(Boolean);
  if (!parts.length) return [{ name: sep, path: sep }];
  const out: { name: string; path: string }[] = [];
  let at: string;
  if (windows && /^[A-Za-z]:$/.test(parts[0] ?? "")) {
    at = `${parts.shift()}\\`;
    out.push({ name: at, path: at });
  } else if (windows && path.startsWith("\\\\")) {
    at = `\\\\${parts.shift()}\\${parts.shift() ?? ""}`;
    out.push({ name: at, path: at });
  } else {
    at = "/";
    out.push({ name: "/", path: "/" });
  }
  for (const part of parts) {
    at = at.endsWith(sep) ? `${at}${part}` : `${at}${sep}${part}`;
    out.push({ name: part, path: at });
  }
  return out;
}

// ===== [SYSTEM] the system's own dialog =====

let systemReady: Promise<boolean> | null = null;

/** Whether this computer's own dialogs open (asked once per page). */
export function systemDialogs(): Promise<boolean> {
  systemReady ??= api<{ system: boolean }>("/dialogs").then(
    (r) => Boolean(r.system),
    () => false,
  );
  return systemReady;
}

/** The chosen path, or null when the dialog is closed without one. */
export async function chooseFile(options: ChooseOptions): Promise<string | null> {
  if (await systemDialogs()) {
    try {
      const answer = await api<SystemAnswer>("/dialogs/choose", "POST", {
        mode: options.mode,
        title: options.title,
        start: options.start || undefined,
        suffixes: options.suffixes?.length ? options.suffixes : undefined,
        name: options.mode === "save" ? options.name || undefined : undefined,
        kind: kindOf(options),
      });
      if (answer.path) return answer.path;
      if (answer.cancelled) return null;
      if (answer.busy) {
        toast("A file dialog is already open");
        return null;
      }
    } catch {
      // the page's own picker, below
    }
    systemReady = Promise.resolve(false); // it could not open here: the page's own from now on
  }
  return choosePage(options);
}

// ===== the page's own picker =====

function choosePage(options: ChooseOptions): Promise<string | null> {
  return new Promise((resolve) => {
    const { dialog, body, foot, close } = openDialog(options.title, true);
    dialog.classList.add("file-chooser");
    const kind = kindOf(options);
    let done = false;
    const finish = (value: string | null): void => {
      if (done) return;
      done = true;
      close();
      if (value) void api("/dialogs/recent", "POST", { kind, path: value, mode: options.mode }).catch(() => undefined);
      resolve(value);
    };
    dialog.addEventListener("close", () => finish(null));

    let shown: Listing | null = null;
    let hidden = false;
    let selected = -1; // the selected row among those drawn
    let drawn: { entry: Entry; folder: boolean; row: HTMLElement }[] = [];

    const where = h("input", { type: "text", class: "mono", "aria-label": "Folder", spellcheck: false });
    const trail = h("nav", { class: "file-crumbs", "aria-label": "Path" });
    const filter = h("input", { type: "search", "aria-label": "Filter", placeholder: "Filter", spellcheck: false });
    const places = h("nav", { class: "file-places", "aria-label": "Places" });
    const list = h("ul", { class: "file-list", role: "listbox", tabindex: 0, "aria-label": "Folders and files" });
    const status = h("p", { class: "hint", role: "status" });
    const saveName = h("input", { type: "text", "aria-label": "File name", value: options.name ?? "", spellcheck: false });
    const up = button("Up", () => shown?.parent && void go(shown.parent), { icon: "up", iconOnly: true, class: "ghost" });
    const hiddenBox = h("input", { type: "checkbox", "aria-label": "Hidden files" });
    hiddenBox.addEventListener("change", () => {
      hidden = hiddenBox.checked;
      if (shown) void go(shown.path);
    });

    const choose = button(
      options.mode === "folder" ? "Choose this folder" : options.mode === "save" ? "Save here" : "Open",
      () => pick(),
      { class: "primary", icon: "check" },
    );
    if (options.mode === "file") choose.disabled = true;

    const join = (folder: string, name: string): string => {
      const sep = folder.includes("\\") && !folder.includes("/") ? "\\" : "/";
      return `${folder.replace(/[\\/]+$/, "")}${sep}${name}`;
    };

    // A click on the main button before the first folder is read waits for it (it was lost before).
    let early = false;
    const pick = (): void => {
      if (!shown) {
        early = true;
        status.textContent = "Loading…";
        return;
      }
      if (options.mode === "folder") finish(shown.path);
      else if (options.mode === "save") {
        const name = saveName.value.trim();
        if (!name || /[\\/]/.test(name)) {
          status.textContent = "Type a file name (no slashes)";
          saveName.focus();
          return;
        }
        finish(join(shown.path, name));
      } else {
        const chosen = drawn[selected];
        if (!chosen) return;
        if (chosen.folder) void go(chosen.entry.path);
        else finish(chosen.entry.path);
      }
    };

    /** A double-click or Enter on a row: a folder opens, a file is picked (Save: saved over, as named). */
    const activate = (index: number): void => {
      const chosen = drawn[index];
      if (!chosen) return;
      if (chosen.folder) void go(chosen.entry.path);
      else if (options.mode === "file") finish(chosen.entry.path);
      else if (options.mode === "save") {
        saveName.value = chosen.entry.name;
        pick();
      }
    };

    const select = (index: number, focus = true): void => {
      if (!drawn.length) return;
      selected = Math.max(0, Math.min(drawn.length - 1, index));
      drawn.forEach((d, i) => d.row.setAttribute("aria-selected", String(i === selected)));
      const row = drawn[selected];
      if (!row) return;
      list.setAttribute("aria-activedescendant", row.row.id);
      row.row.scrollIntoView({ block: "nearest" });
      if (focus) list.focus();
      if (options.mode === "save" && !row.folder) saveName.value = row.entry.name;
      if (options.mode === "file") choose.disabled = false;
    };

    const draw = (): void => {
      if (!shown) return;
      const at = shown;
      const words = filter.value.trim().toLowerCase();
      const keep = (e: Entry): boolean => !words || e.name.toLowerCase().includes(words);
      const folders = at.folders.filter(keep);
      const files = at.files.filter(keep);
      selected = -1;
      list.removeAttribute("aria-activedescendant");
      if (options.mode === "file") choose.disabled = true;
      drawn = [...folders.map((entry) => ({ entry, folder: true })), ...files.map((entry) => ({ entry, folder: false }))].map(
        ({ entry, folder }, i) => {
          const row = h(
            "li",
            {
              id: `file-row-${i}`,
              class: `file-row ${folder ? "folder" : "file"}${!folder && options.mode === "folder" ? " muted" : ""}`,
              role: "option",
              "aria-selected": "false",
              title: entry.path,
              onclick: () => select(i),
              ondblclick: () => activate(i),
            },
            h("span", { class: "file-name" }, icon(folder ? "folder" : "file"), h("span", {}, entry.name)),
            h("span", { class: "file-meta file-date" }, entry.modified ? new Date(entry.modified * 1000).toLocaleDateString() : ""),
            h("span", { class: "file-meta file-size" }, folder || entry.size === undefined ? "" : size(entry.size)),
          );
          return { entry, folder, row };
        },
      );
      clear(list, ...drawn.map((d) => d.row));
      if (!drawn.length) list.append(h("li", { class: "file-empty" }, words ? "Nothing matches" : "Empty folder"));
      const kinds = options.suffixes?.length ? ` (${options.suffixes.join(", ")})` : "";
      const counted = `${folders.length} folder${folders.length === 1 ? "" : "s"}, ${files.length} file${files.length === 1 ? "" : "s"}${kinds}`;
      status.textContent = words ? `${counted} matching` : counted;
    };

    let placesDrawn = false;
    const drawPlaces = (at: Listing): void => {
      const all = [...(at.places ?? [])];
      const sep = at.separator ?? "/";
      for (const root of at.roots) {
        if (root !== at.home) all.push({ name: root === "/" ? "Computer" : root, path: root, kind: "drive" });
      }
      const group = (label: string, items: Place[]): HTMLElement | null =>
        items.length
          ? h(
              "div",
              { class: "file-place-group" },
              h("h3", {}, label),
              ...items.map((p) =>
                h(
                  "button",
                  { type: "button", class: "file-place", title: p.path, "data-path": p.path, onclick: () => void go(p.path) },
                  icon(PLACE_ICONS[p.kind] ?? "folder"),
                  h("span", {}, p.kind === "recent" ? (crumbs(p.path, sep).pop()?.name ?? p.path) : p.name),
                ),
              ),
            )
          : null;
      clear(
        places,
        group("Places", all.filter((p) => p.kind !== "recent" && p.kind !== "drive")),
        group("Recent", all.filter((p) => p.kind === "recent")),
        group("Drives", all.filter((p) => p.kind === "drive")),
      );
      placesDrawn = true;
    };

    const markPlace = (path: string): void => {
      for (const b of places.querySelectorAll<HTMLElement>(".file-place")) {
        if (b.dataset.path === path) b.setAttribute("aria-current", "location");
        else b.removeAttribute("aria-current");
      }
    };

    // Only the newest listing is drawn: a path typed while the first folder is still being read would
    // otherwise be replaced by that first answer when it arrives late.
    let asked = 0;
    let missing: string | null = null; // the first folder asked for, when it did not exist
    const go = async (path: string | null): Promise<void> => {
      const query = new URLSearchParams();
      if (path) query.set("path", path);
      if (options.suffixes?.length) query.set("suffixes", options.suffixes.join(","));
      if (!placesDrawn) query.set("kind", kind);
      if (hidden) query.set("hidden", "1");
      status.textContent = "Loading…";
      const mine = ++asked;
      const typed = where.value; // what the path box said when this folder was asked for
      let found: Listing;
      try {
        found = await api<Listing>(`/folders?${query}`);
      } catch (e) {
        if (mine !== asked) return;
        // The first folder asked for may not exist yet (a projects folder before its first project, a moved
        // project's old place): the nearest folder above it that does is shown instead, else home.
        if (!shown && path) {
          const above = path.replace(/[\\/]+$/, "").replace(/[\\/][^\\/]*$/, "");
          missing ??= path;
          void go(above && above !== path && !/^[A-Za-z]:$/.test(above) ? above : null);
          return;
        }
        status.textContent = (e as Error).message;
        return;
      }
      if (mine !== asked) return;
      const changed = shown?.path !== found.path;
      shown = found;
      if (found.places) drawPlaces(found);
      markPlace(found.path);
      if (early) {
        early = false;
        window.setTimeout(pick); // after this folder is drawn
      }
      // A path typed while this folder was being read is kept (the Enter that followed opened this folder
      // instead of the one typed); an empty box with the cursor in it is about to be typed in.
      const typing = document.activeElement === where;
      if (!typing || (where.value === typed && typed !== "")) where.value = found.path;
      where.placeholder = found.path;
      clear(
        trail,
        ...crumbs(found.path, found.separator).map((c, i, all) =>
          i === all.length - 1
            ? h("span", { class: "file-crumb current", "aria-current": "location" }, c.name)
            : h("button", { type: "button", class: "file-crumb", title: c.path, onclick: () => void go(c.path) }, c.name),
        ),
      );
      up.disabled = !found.parent;
      if (changed) filter.value = "";
      draw();
      if (missing) {
        status.textContent = `${missing} does not exist yet: showing the nearest folder that does.`;
        missing = null;
      }
    };

    // ===== New folder =====
    const newFolder = (): void => {
      if (!shown || list.querySelector(".file-new")) return;
      const at = shown;
      const name = h("input", { type: "text", "aria-label": "New folder's name", value: "New folder", spellcheck: false });
      const row = h("li", { class: "file-row folder file-new" }, h("span", { class: "file-name" }, icon("folder"), name));
      const make = async (): Promise<void> => {
        try {
          const made = await api<{ path: string }>("/folders/new", "POST", { path: at.path, name: name.value });
          await go(made.path);
          (options.mode === "save" ? saveName : list).focus();
        } catch (e) {
          status.textContent = (e as Error).message;
          name.focus();
        }
      };
      name.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          void make();
        } else if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          row.remove();
          list.focus();
        }
      });
      list.prepend(row);
      name.focus();
      name.select();
    };

    // ===== the keys =====
    list.addEventListener("keydown", (e) => {
      if (e.target !== list) return;
      if (e.key === "ArrowDown") select(selected + 1);
      else if (e.key === "ArrowUp") select(selected < 0 ? 0 : selected - 1);
      else if (e.key === "Home") select(0);
      else if (e.key === "End") select(drawn.length - 1);
      else if (e.key === "Enter") {
        if (selected >= 0) activate(selected);
        else if (options.mode !== "file") pick();
      } else if (e.key === "Backspace") {
        if (shown?.parent) void go(shown.parent);
      } else return;
      e.preventDefault();
    });
    filter.addEventListener("input", draw);
    filter.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        e.preventDefault();
        select(0);
        if (e.key === "Enter" && drawn.length === 1) activate(0);
      } else if (e.key === "Escape" && filter.value) {
        e.preventDefault();
        filter.value = "";
        draw();
      }
    });
    where.addEventListener("keydown", (e) => {
      if (e.key === "Enter") void go(where.value.trim());
    });
    saveName.addEventListener("keydown", (e) => {
      if (e.key === "Enter") pick();
    });

    body.append(
      h(
        "div",
        { class: "file-chooser-body" },
        places,
        h(
          "div",
          { class: "file-main" },
          h("div", { class: "file-bar" }, up, trail),
          h("div", { class: "file-path" }, where, button("Go", () => void go(where.value.trim()), { icon: "play" })),
          h(
            "div",
            { class: "file-tools" },
            filter,
            options.mode === "file" ? null : button("New folder", newFolder, { icon: "plus" }),
            h("label", { class: "file-hidden" }, hiddenBox, h("span", {}, "Hidden files")),
          ),
          list,
          ...(options.mode === "save" ? [h("label", { class: "field file-save" }, h("span", {}, "File name"), saveName)] : []),
          status,
        ),
      ),
    );
    foot.append(choose, button("Cancel", () => finish(null)));
    void go(options.start ?? null);
    window.setTimeout(() => (options.mode === "save" ? saveName : filter).focus());
  });
}
