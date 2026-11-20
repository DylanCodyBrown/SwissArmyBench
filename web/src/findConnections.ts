/**
 * findConnections.ts: the Connections page's Find connections on this computer… (the owner, 2026-11-20: "Is it
 * possible to scan the computer's common apps for connections and import them. DBeaver, SSMS, ODBC, etc." /
 * "You could scan the app directory for hints of what to search for"). [WIRE]
 *
 *   [SCAN]   on the button's click only: the dialog gated by the one loading state while the known tools are
 *            read and the settings folders searched (Cancel stops the search; what it found is listed)
 *   [LIST]   each found connection: its kind's icon, name, kind, server, database, user (never a password),
 *            where it came from (each tool; "found by searching" for the hint scan), Already added, a kind with
 *            no connection yet (not tickable), the amber Only works on your machine. A search box, Select all
 *   [IMPORT] the ticked rows made library connections; the Connections page draws the new cards
 *
 * ROUTING: [SCAN] POST /connections/found   [CANCEL] POST /connections/found/cancel
 *          [IMPORT] POST /connections/found/import {ids}
 */
import { api } from "./api";
import { button, clear, h, hasIcon, icon, openDialog, toast } from "./dom";
import { errorMark, errorNote } from "./errorNote";
import { busy, busyClick, room } from "./loading";

interface FoundSource {
  tool: string;
  where: string;
  searched: boolean;
}

interface FoundRow {
  id: string;
  name: string;
  kind: string;
  kind_label: string;
  server: string;
  port: number | null;
  database: string;
  user: string;
  data_source: string;
  path: string;
  sign_in: "password" | "windows" | "dsn" | "file";
  from: FoundSource[];
  searched: boolean;
  already: string | null;
  supported: boolean;
  why: string | null;
  local: { key: string; words: string }[];
}

interface FoundList {
  connections: FoundRow[];
  notes: string[];
  files: number;
  stopped: string | null;
}

interface Imported {
  imported: { id: string; name: string; kind: string; variable: string | null }[];
  variables: string[];
  skipped: { id: string; why: string }[];
}

const isAbort = (e: unknown): boolean => (e as Error | null)?.name === "AbortError";

/** Where a row reads from: server and database, a data source, or a file. */
function placeOf(r: FoundRow): string {
  if (r.path) return r.path;
  if (r.sign_in === "dsn") return r.data_source;
  const server = r.port ? `${r.server}:${r.port}` : r.server;
  return [server, r.database].filter(Boolean).join(" / ");
}

/** The dialog; resolves to the names imported (none when closed). */
export function openFindConnections(): Promise<string[]> {
  return new Promise((resolve) => {
    const { dialog, body, foot, close } = openDialog("Find connections on this computer", true);
    dialog.classList.add("find-connections");
    let done = false;
    let shown: FoundList | null = null;
    const ticks = new Map<string, HTMLInputElement>();
    const end = (names: string[]): void => {
      if (done) return;
      done = true;
      close();
      resolve(names);
    };
    dialog.addEventListener("close", () => end([]));

    const go = button("Import", busyClick("Importing…", () => finish()), { icon: "import", class: "primary" });
    go.disabled = true;
    const count = h("span", { class: "find-count", "aria-live": "polite" });
    const search = h("input", { type: "search", placeholder: "Search", "aria-label": "Search the found connections" }) as HTMLInputElement;
    const all = h("input", { type: "checkbox", "aria-label": "Select all" }) as HTMLInputElement;
    const list = h("ul", { class: "find-list", "aria-label": "Found connections" });
    const notes = h("div", { class: "find-notes" });

    const ticked = (): string[] => [...ticks].filter(([, box]) => box.checked && !box.disabled).map(([id]) => id);
    const visible = (): HTMLInputElement[] => [...ticks.values()].filter((box) => !box.disabled && !box.closest("li")?.hidden);
    const update = (): void => {
      const n = ticked().length;
      go.disabled = n === 0;
      const label = n ? `Import ${n}` : "Import";
      go.querySelector(".btn-label")!.textContent = label;
      go.setAttribute("aria-label", label);
      const can = visible();
      all.checked = can.length > 0 && can.every((b) => b.checked);
      all.indeterminate = !all.checked && can.some((b) => b.checked);
      all.disabled = can.length === 0;
    };
    all.addEventListener("change", () => {
      for (const box of visible()) box.checked = all.checked;
      update();
    });
    search.addEventListener("input", () => {
      const words = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
      for (const li of list.children as HTMLCollectionOf<HTMLElement>) {
        const text = li.dataset.search ?? "";
        li.hidden = !words.every((w) => text.includes(w));
      }
      update();
    });

    const rowOf = (r: FoundRow): HTMLElement => {
      const box = h("input", { type: "checkbox", "data-id": r.id, "aria-label": `Import ${r.name}` }) as HTMLInputElement;
      box.disabled = !r.supported || Boolean(r.already);
      box.addEventListener("change", update);
      ticks.set(r.id, box);
      const from = r.from.map((s) => s.tool).filter((t, i, every) => every.indexOf(t) === i).join(", ");
      const where = r.from.map((s) => s.where).filter(Boolean).join("\n");
      return h(
        "li",
        {
          class: `find-row${box.disabled ? " find-off" : ""}`,
          "data-id": r.id,
          "data-search": [r.name, r.kind_label, r.server, r.database, r.user, r.data_source, r.path, from].join(" ").toLowerCase(),
        },
        h(
          "label",
          { class: "find-main" },
          box,
          h("span", { class: "find-icon", "aria-hidden": "true" }, icon(hasIcon(r.kind) ? r.kind : "plug")),
          h(
            "span",
            { class: "find-text" },
            h("strong", { class: "find-name" }, r.name),
            h("span", { class: "find-kind" }, r.kind_label),
            h("span", { class: "find-place" }, placeOf(r)),
            r.user ? h("span", { class: "find-user" }, icon("user"), r.user) : null,
          ),
        ),
        h(
          "span",
          { class: "find-marks" },
          h("span", { class: "find-from", title: where }, from, r.searched ? h("span", { class: "badge" }, "found by searching") : null),
          r.already ? h("span", { class: "badge ok", title: r.already }, "Already added") : null,
          r.why ? h("span", { class: "find-why" }, r.why) : null,
          r.supported && !r.already && r.local.length ? errorMark(r.local[0]!.words, { level: "warning", iconOnly: true, title: r.local.map((n) => n.words).join("\n") }) : null,
        ),
      );
    };

    const draw = (found: FoundList): void => {
      shown = found;
      ticks.clear();
      clear(list, ...found.connections.map(rowOf));
      clear(notes, ...found.notes.map((n) => h("p", { class: "muted" }, n)));
      const can = found.connections.filter((r) => r.supported && !r.already).length;
      count.textContent = found.connections.length ? `${found.connections.length} found` + (can !== found.connections.length ? ` · ${can} to import` : "") : "";
      clear(
        body,
        found.connections.length
          ? h("div", { class: "find-bar" }, h("label", { class: "find-all" }, all, h("span", {}, "Select all")), search, count)
          : h("p", { class: "find-empty" }, "No connections found."),
        found.connections.length ? list : null,
        notes,
      );
      update();
      if (found.connections.length) search.focus();
    };

    const scan = async (): Promise<void> => {
      clear(body, room("260px"));
      const abort = new AbortController();
      const request = api<FoundList>("/connections/found", "POST", {});
      try {
        draw(await busy(body, "Looking for connections…", request, { abort, onCancel: () => void api("/connections/found/cancel", "POST", {}).catch(() => undefined), errorIn: false }));
      } catch (e) {
        if (!isAbort(e)) return void clear(body, errorNote(e, { fixes: [{ label: "Try again", run: () => void scan() }] }));
        // Cancelled: the search stops and answers with what it found until then.
        try {
          draw(await request);
        } catch (failed) {
          clear(body, errorNote(failed));
        }
      }
    };

    const finish = async (): Promise<void> => {
      const ids = ticked();
      if (!shown || !ids.length) return;
      const result = await api<Imported>("/connections/found/import", "POST", { ids });
      for (const s of result.skipped) {
        const name = shown.connections.find((r) => r.id === s.id)?.name ?? s.id;
        toast(`${name}: ${s.why}`);
      }
      if (result.imported.length) end(result.imported.map((m) => m.name));
      else body.prepend(errorNote(result.skipped[0]?.why ?? "Nothing was imported."));
    };

    foot.append(button("Cancel", () => end([]), { class: "ghost" }), go);
    void scan();
  });
}
