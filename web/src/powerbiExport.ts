/**
 * powerbiExport.ts: Export to Power BI… on the ERD page (the owner, 2026-11-19: "Make a powerbi desktop file with
 * our model exported an option on the erd page"). [DIALOG]
 *
 *   the tables the ERD shows, each with a tick (all ticked); a table Power Query cannot read says why in one
 *   line with its fix, Include its rows; each table's notes (steps not carried, a type as text) and the amber
 *   Only works on your machine; the relationships that go (inactive ones said) and the ones left out; the name
 *   -> Export: written into the open project's powerbi/ (Open in Power BI Desktop, else Show its folder), or a
 *   zip download with no project open. The one loading state (loading.ts) and the one error (errorNote.ts).
 *
 * ROUTING: POST /powerbi/plan, POST /powerbi/export, POST /powerbi/open (services/powerbi_export.py)
 */
import { api, downloadPost } from "./api";
import { button, clear, h, openDialog } from "./dom";
import { busy, loadingBlock } from "./loading";
import { errorHere } from "./errorNote";
import { saveBlob } from "./profileView";

interface PlannedTable {
  name: string;
  goes: boolean;
  source: string;
  why?: string;
  fix?: string;
  needs_rows: boolean;
  rows: boolean;
  notes: string[];
  local: string[];
  columns: number;
  row_count?: number;
}

interface PlannedRelationship {
  from: string;
  from_columns: string[];
  to: string;
  to_columns: string[];
  goes: boolean;
  active: boolean;
  left_out?: string;
  note?: string;
}

interface Plan {
  name: string;
  where: string | null;
  download: boolean;
  tables: PlannedTable[];
  relationships: PlannedRelationship[];
  parameters: string[];
  written?: string[];
  removed?: string[];
  opens?: boolean;
}

const words = (r: PlannedRelationship): string => `${r.from}.${r.from_columns.join(", ")} → ${r.to}.${r.to_columns.join(", ")}`;

/** Open the dialog for these tables (the ERD's own). */
export function openPowerBIExport(tables: string[]): void {
  const parts = openDialog("Export to Power BI", true);
  parts.dialog.classList.add("pbi-export");
  const ticked = new Set(tables);
  const rows = new Set<string>();
  const name = h("input", { type: "text", class: "pbi-name", "aria-label": "Name", maxlength: 64, "data-no-variables": "" });
  const listing = h("div", { class: "pbi-listing" }, loadingBlock("Reading the tables…", { height: "200px" }));
  const done = h("div", { class: "pbi-done" });
  parts.body.append(h("label", { class: "pbi-name-row" }, h("span", {}, "Name"), name), listing, done);
  let plan: Plan | null = null;

  const body = (): Record<string, unknown> => ({
    tables: tables.filter((t) => ticked.has(t)),
    name: name.value.trim() || undefined,
    include_rows: [...rows].filter((t) => ticked.has(t)),
  });

  const draw = (p: Plan): void => {
    plan = p;
    if (!name.value) name.value = p.name;
    const byName = new Map(p.tables.map((t) => [t.name, t]));
    const tableRows = tables.map((t) => {
      const one = byName.get(t);
      const box = h("input", {
        type: "checkbox",
        checked: ticked.has(t),
        onchange: () => {
          if (box.checked) ticked.add(t);
          else ticked.delete(t);
          void refresh();
        },
      });
      const lines: (HTMLElement | null)[] = [];
      if (one && ticked.has(t)) {
        if (one.why) lines.push(h("div", { class: "pbi-why" }, `${one.why}.`));
        if (one.needs_rows) {
          const keep = h("input", {
            type: "checkbox",
            checked: rows.has(t),
            onchange: () => {
              if (keep.checked) rows.add(t);
              else rows.delete(t);
              void refresh();
            },
          });
          lines.push(h("label", { class: "pbi-rows" }, keep, `Include its rows (${(one.row_count ?? 0).toLocaleString()})`));
        }
        for (const note of one.notes) lines.push(h("div", { class: "pbi-note" }, note));
        for (const local of one.local) lines.push(h("div", { class: "pbi-local amber" }, local));
      }
      return h(
        "li",
        { class: `pbi-table ${one && !one.goes && ticked.has(t) ? "pbi-not" : ""}`, "data-table": t },
        h("label", {}, box, h("strong", {}, t), one?.source ? h("span", { class: "hint" }, ` · ${one.source}`) : null),
        ...lines,
      );
    });
    const going = p.relationships.filter((r) => r.goes);
    const out = p.relationships.filter((r) => !r.goes);
    clear(
      listing,
      h("h3", {}, "Tables"),
      h("ul", { class: "pbi-tables" }, ...tableRows),
      h("h3", {}, `Relationships (${going.length})`),
      going.length
        ? h("ul", { class: "pbi-rels" }, ...going.map((r) => h("li", {}, words(r), r.active ? null : h("span", { class: "hint" }, " · inactive"))))
        : h("p", { class: "hint" }, "None between these tables."),
      out.length ? h("ul", { class: "pbi-rels pbi-out" }, ...out.map((r) => h("li", {}, words(r), h("div", { class: "pbi-why" }, `Left out: ${r.left_out}.`)))) : null,
      p.parameters.length ? h("p", { class: "hint" }, `Power Query parameters: ${p.parameters.join(", ")}.`) : null,
    );
  };

  const refresh = async (): Promise<void> => {
    try {
      draw(await busy(listing, "Reading the tables…", api<Plan>("/powerbi/plan", "POST", body())));
    } catch {
      // shown in place by busy()
    }
  };

  const exportIt = async (): Promise<void> => {
    if (!plan) return;
    try {
      if (plan.download) {
        const file = await busy(parts.body, "Exporting…", downloadPost("/powerbi/export", body()));
        saveBlob(file.blob, file.name);
        parts.close();
        return;
      }
      const made = await busy(parts.body, "Exporting…", api<Plan>("/powerbi/export", "POST", body()));
      const where = made.where ?? "";
      done.replaceChildren(
        h("p", { class: "pbi-written" }, h("strong", {}, where), ` · ${made.written?.length ?? 0} files written`),
        button(made.opens ? "Open in Power BI Desktop" : "Show its folder", (e) => void openIt(where, e), {
          class: "primary",
          icon: made.opens ? "export" : "folder",
        }),
      );
    } catch {
      // shown in place by busy()
    }
  };

  const openIt = async (path: string, event: MouseEvent): Promise<void> => {
    try {
      await api("/powerbi/open", "POST", { path });
    } catch (e) {
      errorHere(e, {}, event.currentTarget as Element);
    }
  };

  parts.foot.append(button("Export", () => void exportIt(), { class: "primary", icon: "export" }), button("Cancel", parts.close));
  name.addEventListener("change", () => void refresh());
  void refresh();
}
