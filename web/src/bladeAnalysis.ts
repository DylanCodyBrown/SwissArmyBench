/**
 * bladeAnalysis.ts: your own analyses (analysis blades) in the Analyze menu. The server runs the blade
 * on the grid's rows as it shows them, in a child process (POST /grids/{id}/blade-analysis), and sends
 * back Visualizations cards: notes, tables, pictures, figures. Here they show in a window, with Send to Visualizations.
 */
import { api, errorText, grid, token } from "./api";
import { missingOf, promptInstall, reminder } from "./missingPackages";
import { button, clear, h, openDialog, toast } from "./dom";
import { sentToast } from "./sandboxShow";
import { selection } from "./gridView";
import { renderMarkdown } from "./markdown";
import { effectiveTheme } from "./theme";

interface Card {
  kind: string;
  title?: string;
  body?: string;
  columns?: string[];
  rows?: unknown[][];
  capped?: boolean;
}

export interface AnalysisBlade {
  name: string;
  description: string;
}

const plotly = (): Promise<typeof import("./lazy/plotly")> => import(/* external */ "/static/build/lazy/plotly.js" as string) as Promise<typeof import("./lazy/plotly")>;

/** The analysis blades, for the menu (none when the list can't be read). */
export async function analysisBlades(): Promise<AnalysisBlade[]> {
  try {
    return (await api<{ analyses: AnalysisBlade[] }>("/blades/analyses")).analyses;
  } catch {
    return [];
  }
}

export function openBladesPage(): void {
  window.open(`/catalog#token=${encodeURIComponent(token)}`, "swissarmybench-catalog")?.focus();
}

function drawCard(card: Card): HTMLElement {
  if (card.kind === "note") return h("div", { class: "blade-result-note" }, renderMarkdown(card.body ?? ""));
  if (card.kind === "image") return h("img", { class: "card-image", src: card.body ?? "", alt: card.title || "A picture from the analysis" });
  if (card.kind === "table") {
    const columns = card.columns ?? [];
    return h(
      "div",
      { class: "analysis-table-wrap" },
      h(
        "table",
        { class: "small" },
        h("thead", {}, h("tr", {}, ...columns.map((c) => h("th", { scope: "col" }, c)))),
        h("tbody", {}, ...(card.rows ?? []).map((r) => h("tr", {}, ...r.map((v) => h("td", { class: typeof v === "number" ? "num" : "" }, v === null ? "(blank)" : String(v)))))),
      ),
      card.capped ? h("p", { class: "hint" }, "The first 100 rows.") : null,
    );
  }
  if (card.kind === "plotly") {
    const host = h("div", { class: "analysis-chart" });
    requestAnimationFrame(() => void plotly().then((m) => m.drawPlotly(host, card.body ?? "{}", effectiveTheme() !== "light")).catch((e: Error) => (host.textContent = e.message)));
    return host;
  }
  return h("pre", { class: "code-box" }, card.body ?? "");
}

/** Run an analysis blade on this grid (with the selected columns) and show what it returned. */
export async function runBladeAnalysis(blade: AnalysisBlade): Promise<void> {
  const { body, foot, close } = openDialog(blade.name, true);
  const results = h("div", { class: "analysis-results" });
  const actions = h("span", { class: "analysis-actions" });
  const columns = selection.targetColumns();
  body.append(blade.description ? h("p", { class: "hint" }, blade.description) : "", results);
  foot.append(actions, button("Close", close));
  const run = async (): Promise<void> => {
    clear(results, h("p", { class: "hint" }, `Running ${blade.name}…`));
    clear(actions);
    try {
      const answer = await api<{ title: string; cards: Card[] }>(`${grid}/blade-analysis`, "POST", { name: blade.name, columns });
      clear(results, ...answer.cards.map(drawCard));
      clear(
        actions,
        button("Send to Visualizations", () => {
          void (async () => {
            let first: unknown;
            for (const [i, card] of answer.cards.entries()) {
              const made = await api(`${grid}/cards`, "POST", { ...card, title: card.title ?? (i === 0 ? answer.title : "") });
              first ??= made; // each card sent (??= alone skipped every card after the first)
            }
            return first;
          })().then((first) => sentToast(`In Visualizations: ${answer.cards.length} card${answer.cards.length === 1 ? "" : "s"} from ${blade.name}.`, first), (e: Error) => toast(e.message, "error"));
        }, { icon: "image" }),
        button("Run again", () => void run(), { icon: "play" }),
        button("Edit on the blades page", openBladesPage, { icon: "edit", class: "ghost" }),
      );
    } catch (e) {
      clear(results, h("p", { class: "status-error" }, errorText(e)));
      clear(actions, button("Edit on the blades page", openBladesPage, { icon: "edit" }));
      // Stopped on a missing package: the prompt in the user's face; installed, it runs again.
      const missing = missingOf(e);
      if (missing) {
        actions.prepend(reminder(missing, { then: run }));
        void promptInstall(missing, { then: run });
      }
    }
  };
  await run();
}
