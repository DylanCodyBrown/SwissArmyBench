/**
 * powerbiExport.ts: Export to Power BI… on the ERD page (the owner, 2026-11-19: "Make a powerbi desktop file with
 * our model exported an option on the erd page"). [DIALOG]
 *
 *   the tables the ERD shows, each with a tick (all ticked); a table Power Query cannot read says why in one
 *   line with its fix, Include its rows; each table's notes (steps not carried, a type as text) and the amber
 *   Only works on your machine; the relationships that go (inactive ones said) and the ones left out; the name
 *   -> Export: written into the open project's powerbi/ (Open in Power BI Desktop, else Show its folder), or a
 *   zip download with no project open; Use an existing report's pages (a dropped or chosen .pbix, .pbit or .pbip:
 *   its fields mapped to ours, matched ones ticked, a picker or Leave it for the rest). The one loading state (loading.ts) and the one error (errorNote.ts).
 *
 * A plug-in of the Power BI extension: the ERD draws its button from the mode's page_actions (pageActions.ts) only
 * while the extension is on.
 *
 * ROUTING: POST /powerbi/plan, POST /powerbi/export, POST /powerbi/open (services/powerbi_export.py)
 */
import { api, downloadPost, postBytes } from "./api";
import { chooseFile } from "./fileChooser";
import { button, clear, h, openDialog } from "./dom";
import { busy, loadingBlock } from "./loading";
import { errorHere } from "./errorNote";
import { registerPageAction } from "./pageActions";
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
  report?: ReportUse;
}

interface MappedField {
  table: string;
  field: string;
  kind: string;
  to: { table: string; field: string } | null;
  matched: boolean;
}

interface ReportUse {
  file: string;
  kind: string;
  pages: string;
  ours: Record<string, string[]>;
  fields: MappedField[];
  measures: string[];
  said: string[];
}

const REPORT_KINDS = [".pbix", ".pbit", ".pbip"];

const words = (r: PlannedRelationship): string => `${r.from}.${r.from_columns.join(", ")} → ${r.to}.${r.to_columns.join(", ")}`;

registerPageAction("powerbi_export", (tables) => openPowerBIExport(Array.isArray(tables) ? (tables as string[]) : []));
// The Power BI page's Use another report's pages: the same dialog, its report part in view and first.
registerPageAction("powerbi_report_pages", (tables) => openPowerBIExport(Array.isArray(tables) ? (tables as string[]) : [], true));

/** Open the dialog for these tables (the ERD's own); `reportFirst`: its report part in view and focused. */
export function openPowerBIExport(tables: string[], reportFirst = false): void {
  const parts = openDialog("Export to Power BI", true);
  parts.dialog.classList.add("pbi-export");
  const ticked = new Set(tables);
  const rows = new Set<string>();
  const name = h("input", { type: "text", class: "pbi-name", "aria-label": "Name", maxlength: 64, "data-no-variables": "" });
  const listing = h("div", { class: "pbi-listing" }, loadingBlock("Reading the tables…", { height: "200px" }));
  const done = h("div", { class: "pbi-done" });
  // ===== Use an existing report's pages: a dropped or chosen .pbix, .pbit or .pbip =====
  let report: { path?: string; upload?: string; file: string } | null = null;
  const mapping: Record<string, string | null> = {};
  const reportBox = h("div", { class: "pbi-report" });
  const drawReportPicker = (): void => {
    const zone = h(
      "div",
      { class: "pbi-drop", tabindex: 0 },
      h("span", {}, "Use an existing report's pages: drop a .pbix, .pbit or .pbip here"),
      button("Choose file…", () => void choose(), { icon: "folder" }),
    );
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("over"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("over");
      const file = e.dataTransfer?.files[0];
      if (file) void dropped(file);
    });
    reportBox.replaceChildren(zone);
  };
  const choose = async (): Promise<void> => {
    const path = await chooseFile({ title: "A Power BI report", mode: "file", suffixes: REPORT_KINDS, kind: "powerbi-report" });
    if (!path) return;
    report = { path, file: path.split(/[\\/]/).pop() ?? path };
    void refresh();
  };
  const dropped = async (file: File): Promise<void> => {
    try {
      const kept = await busy(reportBox, `Reading ${file.name}…`, postBytes<{ upload: string; file: string }>("/powerbi/report", file, file.name));
      report = { upload: kept.upload, file: kept.file };
      void refresh();
    } catch {
      // shown in place by busy()
    }
  };
  const drawReport = (used: ReportUse): void => {
    const options = Object.entries(used.ours).flatMap(([t, cols]) => cols.map((c) => `${t}.${c}`));
    const measures = used.measures.map((m) => m);
    const rows = used.fields.map((f) => {
      const key = `${f.table}.${f.field}`;
      const pick = h("select", {
        "aria-label": `${key} maps to`,
        onchange: () => {
          mapping[key] = pick.value === "" ? null : pick.value;
          void refresh();
        },
      });
      const current = f.to ? `${f.to.table}.${f.to.field}` : "";
      const choices = [...new Set([...(current ? [current] : []), ...options, ...measures.map((m) => `${f.to?.table ?? f.table}.${m}`)])];
      pick.append(h("option", { value: "" }, "Leave it"), ...choices.map((c) => h("option", { value: c, selected: c === current }, c)));
      return h(
        "li",
        { class: `pbi-field ${f.to ? "" : "pbi-unmapped"}`.trim(), "data-field": key },
        h("span", {}, f.matched ? "✓ " : "", key, h("span", { class: "hint" }, f.kind === "measure" ? " · measure" : "")),
        pick,
      );
    });
    clear(
      reportBox,
      h(
        "div",
        { class: "pbi-report-head" },
        h("strong", {}, used.file),
        h("span", { class: "hint" }, ` · ${used.pages}`),
        button("Remove", () => {
          report = null;
          for (const k of Object.keys(mapping)) delete mapping[k];
          void refresh();
        }, { class: "ghost" }),
      ),
      h("ul", { class: "pbi-fields" }, ...rows),
      used.measures.length ? h("p", { class: "hint" }, `Measures that come along: ${used.measures.join(", ")}.`) : null,
      ...used.said.map((line) => h("div", { class: "pbi-note" }, line)),
    );
  };
  drawReportPicker();
  parts.body.append(h("label", { class: "pbi-name-row" }, h("span", {}, "Name"), name), listing, reportBox, done);
  if (reportFirst) {
    reportBox.classList.add("pbi-report-first");
    parts.body.prepend(reportBox);
    window.setTimeout(() => reportBox.querySelector<HTMLElement>("button, [tabindex]")?.focus());
  }
  let plan: Plan | null = null;

  const body = (): Record<string, unknown> => ({
    tables: tables.filter((t) => ticked.has(t)),
    name: name.value.trim() || undefined,
    include_rows: [...rows].filter((t) => ticked.has(t)),
    ...(report ? { report: report.path ? { path: report.path } : { upload: report.upload }, mapping } : {}),
  });

  const draw = (p: Plan): void => {
    plan = p;
    if (p.report) drawReport(p.report);
    else if (!report) drawReportPicker();
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
