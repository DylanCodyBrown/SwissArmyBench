/**
 * fileChanged.ts: a table whose file changed on disk (services/file_watch.py). [FUNCTION + WIRE]
 *
 * The owner (2026-11-18: "Agreed"): a grid read from a file on disk is watched; when the file changes its
 * tab and its pane say "Changed on disk" with Reload (read again, its steps kept) and Not now. Never
 * reloaded by itself. The server looks (in the browser too) and says so with the `file_changed` notice; a
 * reload is a `dataset_updated`, which takes the mark away.
 *
 *   [TAB MARK]   the tab's dot, "Changed on disk" in its name for a screen reader
 *   [DISK BAR]   in the table's pane: Changed on disk · Reload · Not now
 *
 * ROUTING: GET /datasets (changed_on_disk), POST /datasets/{name}/reload {"not_now"?}; the agent's tabs_reload
 */
import { api, onNotice } from "./api";
import { button, h } from "./dom";
import { errorHere } from "./errorNote";

const changed = new Set<string>();
const listeners: (() => void)[] = [];

function tell(): void {
  for (const listener of listeners) listener();
}

/** Has this table's file changed on disk since it was read? */
export function changedOnDisk(dataset: string): boolean {
  return changed.has(dataset);
}

/** Called whenever a table's mark comes or goes. */
export function onFileChanged(listener: () => void): void {
  listeners.push(listener);
}

/** Reload: the table read again from its file, its grids and their steps kept. */
export async function reloadTable(dataset: string): Promise<void> {
  try {
    await api(`/datasets/${encodeURIComponent(dataset)}/reload`, "POST", {});
  } catch (e) {
    errorHere(e);
  }
}

/** Not now: the table stays as it is (said again when the file changes again). */
async function notNow(dataset: string): Promise<void> {
  try {
    await api(`/datasets/${encodeURIComponent(dataset)}/reload`, "POST", { not_now: true });
  } catch (e) {
    errorHere(e);
  }
}

/** The pane's bar for `dataset`, or nothing while its file is as it was read. */
export function drawDiskBar(slot: HTMLElement, dataset: string): void {
  if (!changed.has(dataset)) {
    slot.replaceChildren();
    return;
  }
  slot.replaceChildren(
    h(
      "div",
      { class: "file-changed", role: "status" },
      h("strong", {}, "Changed on disk"),
      button("Reload", () => void reloadTable(dataset), { class: "small" }),
      button("Not now", () => void notNow(dataset), { class: "ghost small" }),
    ),
  );
}

/** The marks as the server has them now, then kept current by its notices. */
export function mountFileChanged(): void {
  void api<{ datasets: { name: string; changed_on_disk?: boolean }[] }>("/datasets")
    .then(({ datasets }) => {
      for (const d of datasets) if (d.changed_on_disk) changed.add(d.name);
      if (changed.size) tell();
    })
    .catch(() => undefined);
  onNotice((notice) => {
    const said = notice as unknown as { type: string; dataset?: string; changed?: boolean };
    if (!said.dataset) return;
    if (said.type === "file_changed") {
      if (said.changed) changed.add(said.dataset);
      else changed.delete(said.dataset);
      tell();
    } else if ((said.type === "dataset_updated" || said.type === "dataset_closed") && changed.delete(said.dataset)) {
      tell();
    }
  });
}
