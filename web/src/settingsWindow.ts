/**
 * settingsWindow.ts: the Settings window (the cog at the far left of the tab bar). [WIRE + EXPORT]
 *
 * The theme, remembered per viewer and never sent anywhere; and what the agent has done (agentAccess.ts, from the server's audit log). How a
 * table compares text is a table setting, so it lives on the ribbon's Table row (textMatching.ts).
 * Everything here applies as you change it, so the window only has Close.
 *
 * ROUTING: [SETTINGS BUTTON]      -> openSettings()
 *          [THEME CHOICE]         -> setTheme(choice)  (every open tab and window follows)
 *          (Column profiles in the headers are switched in the grid's own top-left corner, beside
 *           what they change: gridView.ts CornerHeader. The zoom is the Application row's.)
 *          [PANELS]               a switch for each panel of the Workbench and the grid page -> panels.ts
 *                                 (the server's, for every window; all on again at each start)
 *          [KIND COLOURS]         app pages, notebooks, scripts: a colour each -> kindColours.ts (the
 *                                 server's, for every window; kept across restarts)
 *          [UPDATES]              Check for updates (kept across restarts) -> updates.ts
 *          [BETA]                 Beta mode (the beta log and Leave a note…, kept across restarts),
 *                                 Export beta log…, Clear the log -> betaNotes.ts
 *          [CONNECT AN AGENT]     Copy -> copyMcpPrompt()  (a prompt that installs the MCP in any agent)
 *          [CLOSE]                -> close()
 *          [AGENT ACCESS]         -> agentAccess.agentAccessSection()  (agent activity)
 */
import { agentAccessSection } from "./agentAccess";
import { betaSection } from "./betaNotes";
import { updatesSection } from "./updates";
import { button, h, icon, openDialog, toast } from "./dom";
import { type Kind, kindColours, kindIcon, loadKindColours, setKindColour } from "./kindColours";
import { dismissDialog, layerOpened, registerLayer, setOverTitle, watchLayerDialog } from "./nav";
import { loadPanels, panelList, setPanel } from "./panels";
import { THEME_LABELS, setTheme, themeChoice, type ThemeChoice } from "./theme";

/** One switch for each panel, by page. A panel turned off is gone from every window at once. */
function panelsSection(): HTMLElement {
  const grid = h("div", { class: "panel-switches" });
  const draw = (): void => {
    const pages = [...new Set(panelList().map((p) => p.page))];
    grid.replaceChildren(
      ...pages.map((page) =>
        h(
          "div",
          { class: "panel-page", role: "group", "aria-label": page },
          h("h4", {}, page),
          ...panelList()
            .filter((p) => p.page === page)
            .map((p) =>
              h(
                "label",
                { class: "check" },
                h("input", {
                  type: "checkbox",
                  checked: p.on,
                  dataset: { panel: p.id },
                  onchange: (e: Event) => void setPanel(p.id, (e.target as HTMLInputElement).checked).catch((error: Error) => toast(error.message, "error")),
                }),
                p.name,
              ),
            ),
        ),
      ),
    );
  };
  void loadPanels().then(draw);
  return h("fieldset", { class: "fieldset panels-fieldset" }, h("legend", {}, "Panels"), grid);
}

/** The colour of each kind of Workbench document: app pages, notebooks, scripts. The server's (every
 *  window follows, kept across restarts); Default puts the theme's own back. */
function kindColoursSection(): HTMLElement {
  const grid = h("div", { class: "kind-colours" });
  const draw = (): void => {
    grid.replaceChildren(
      ...kindColours().map((k) => {
        const shown = k.chosen ?? getComputedStyle(document.documentElement).getPropertyValue(`--kind-${k.kind}`).trim();
        const picker = h("input", {
          type: "color",
          value: /^#[0-9a-f]{6}$/i.test(shown) ? shown : "#000000",
          "aria-label": `${k.name} colour`,
          dataset: { kind: k.kind },
          onchange: (e: Event) => void setKindColour(k.kind, (e.target as HTMLInputElement).value).then(draw, (error: Error) => toast(error.message, "error")),
        });
        return h(
          "div",
          { class: `kind-colour km-${k.kind}`, role: "group", "aria-label": k.name },
          h("span", { class: "kind-colour-icon" }, icon(kindIcon(k.kind as Kind))),
          h("span", { class: "kind-colour-name" }, k.name),
          picker,
          k.chosen ? button("Default", () => void setKindColour(k.kind, null).then(draw, (error: Error) => toast(error.message, "error")), { class: "ghost", title: `${k.name}: the theme's own colour` }) : null,
        );
      }),
    );
  };
  void loadKindColours().then(draw);
  return h("fieldset", { class: "fieldset kind-colours-fieldset" }, h("legend", {}, "Kind colours"), grid);
}

export function settingsButton(): HTMLButtonElement {
  // First in the Application row: always there, whichever tab is open.
  const btn = button("Settings", () => openSettings(), { icon: "cog", class: "ribbon-btn" });
  btn.setAttribute("aria-haspopup", "dialog");
  return btn;
}

/** What an agent needs to connect: paste it into Claude Code (or any agent that has a shell). The
 * command is the one the installers put on PATH (uv tool install of the wheel). */
export const MCP_PROMPT = [
  "Connect the grid MCP server so you can work on my local data grids:",
  "1. Run: claude mcp add --scope user swissarmybench -- swissarmybench-mcp",
  "   (another agent: add an MCP server over stdio whose command is swissarmybench-mcp)",
  "2. Reconnect your MCP servers (/mcp in Claude Code).",
  "3. Call its guide tool first; it explains the grids and the tools.",
].join("\n");

async function copyMcpPrompt(): Promise<void> {
  try {
    await navigator.clipboard.writeText(MCP_PROMPT);
    toast("Copied.");
  } catch {
    toast("The browser blocked the clipboard.", "error");
  }
}

// Settings is in the address (open=settings, nav.ts): Back closes it, a reload and Forward bring it back.
let shown: HTMLDialogElement | null = null;
registerLayer("settings", {
  isOpen: () => Boolean(shown?.open),
  open: () => drawSettings(),
  show: () => undefined, // one view: nothing to move between
  dismiss: () => {
    if (shown) dismissDialog(shown);
  },
});

/** The Application row's Settings (the Workbench's "…" too), opened by the user. */
export function openSettings(): void {
  if (shown?.open) return;
  layerOpened("settings");
  drawSettings();
}

function drawSettings(): void {
  const { dialog, body, foot, close } = openDialog("Settings", true, { history: false });
  shown = dialog;
  setOverTitle("Settings");
  watchLayerDialog(dialog, "settings", [], () => {
    if (shown === dialog) shown = null;
  });
  const themes = Object.entries(THEME_LABELS).map(([value, label]) =>
    h(
      "label",
      { class: "check" },
      h("input", { type: "radio", name: "theme", value, checked: value === themeChoice(), onchange: () => setTheme(value as ThemeChoice) }),
      label,
    ),
  );
  body.append(
    h(
      "fieldset",
      { class: "fieldset" },
      h("legend", {}, "Theme"),
      h("div", { class: "form-grid", role: "radiogroup", "aria-label": "Theme" }, ...themes),
    ),
    panelsSection(),
    kindColoursSection(),
    updatesSection(),
    betaSection(),
    h(
      "fieldset",
      { class: "fieldset" },
      h("legend", {}, "Connect an agent"),
      h("pre", { class: "mono mcp-prompt" }, MCP_PROMPT),
      button("Copy the setup prompt", () => void copyMcpPrompt(), { icon: "copy" }),
    ),
    agentAccessSection(),
  );
  foot.append(button("Close", close, { class: "primary" }));
  (body.querySelector("input:checked") as HTMLInputElement | null)?.focus();
}
