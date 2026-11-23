/**
 * settingsWindow.ts: the Settings page (the rail's cog, pinned at its bottom). [WIRE + EXPORT]
 *
 * A page, not a dialog (the owner, 2026-11-16: "clicking the rail should land on a page not open a
 * form"): areaPage.ts, over the page you are on, at the same address as the dialog it was (open=settings),
 * so old addresses still land here. The theme, remembered per viewer and never sent anywhere. How a
 * table compares text is a table setting, so it lives on the ribbon's Table row (textMatching.ts).
 * Everything here applies as you change it, so the page has no Save and no Close: the rail or Back leaves.
 *
 * ROUTING: [SETTINGS BUTTON]      -> openSettings()
 *          [THEME CHOICE]         -> setTheme(choice)  (every open tab and window follows)
 *          (Column profiles in the headers are switched in the grid's own top-left corner, beside
 *           what they change: gridView.ts CornerHeader. The zoom is the Application row's.)
 *          [SESSION]              Follow the agent (kept across restarts; the user's switch) -> sessionPage.ts
 *          [TEAM]                 the Team box (first after Theme): Join a team…, Start a team…, the Joined row
 *                                 (Pull, Push, …), Advanced (the two folders), the local projects folder
 *                                 -> library.ts (the sign-in step: scmPage.ts teamSignIn)
 *          [UPDATES]              Click here to update (only while one is available) -> updates.ts
 *          [EXTENSIONS]           each on extension's own panel (its switches, sign-in) -> extensionPanel.ts
 *          [BETA]                 Beta mode (the beta log and Leave a note…, kept across restarts),
 *                                 Export beta log…, Clear the log -> betaNotes.ts
 *          [CONNECT AN AGENT]     Copy -> copyMcpPrompt()  (a prompt that installs the MCP in any agent)
 *          [FRONT END]            Classic / Blazor (preview): the front end the app opens (GET/PUT /app/frontend;
 *                                 frontend.json; the agent's app_frontend), and Open it now
 * */
import { api } from "./api";
import { betaSection } from "./betaNotes";
import { extensionSettings } from "./extensionPanel";
import { updatesSection } from "./updates";
import { teamSection } from "./library";
import { claudeSection } from "./claudeLaunch";
import { openAreaPage, type PageElement } from "./areaPage";
import { button, h, icon, toast } from "./dom";
import { dismissDialog, layerOpened, registerLayer, setOverTitle, watchLayerDialog } from "./nav";
import { followSwitch } from "./sessionPage";
import { THEME_LABELS, setTheme, themeChoice, type ThemeChoice } from "./theme";
import { errorHere } from "./errorNote";
import { gatesSetting } from "./gates";

/** What an agent needs to connect: paste it into Claude Code (or any agent that has a shell). The
 * command is the one the installers put on PATH (uv tool install of the wheel). */
export const MCP_PROMPT = [
  "Connect the Swiss Army Bench MCP server so you can work on my local data:",
  "1. Run: claude mcp add --scope user swissarmybench -- swissarmybench-mcp",
  "   (another agent: add an MCP server over stdio whose command is swissarmybench-mcp)",
  "2. Reconnect your MCP servers (/mcp in Claude Code).",
  "3. Call its guide tool first; it explains the app and its tools.",
].join("\n");

async function copyMcpPrompt(): Promise<void> {
  try {
    await navigator.clipboard.writeText(MCP_PROMPT);
    toast("Copied.");
  } catch {
    errorHere("The browser blocked the clipboard.");
  }
}

// Settings is in the address (open=settings, nav.ts): Back closes it, a reload and Forward bring it back.
let shown: PageElement | null = null;
registerLayer("settings", {
  isOpen: () => Boolean(shown?.open),
  open: () => drawSettings(),
  show: () => undefined, // one view: nothing to move between
  dismiss: () => {
    if (shown) dismissDialog(shown);
  },
});

/** Front end (the owner, 2026-11-23: the Blazor front end, side by side): the one the app opens, this computer's
 *  choice; the Blazor one at /blazor/, a preview. */
function frontendSection(): HTMLElement {
  const choices: [string, string][] = [
    ["classic", "Classic"],
    ["blazor", "Blazor (preview)"],
  ];
  const open = h("a", { href: "/blazor/", class: "frontend-open" }, "Open it now");
  const radios = choices.map(([value, label]) =>
    h(
      "label",
      { class: "check" },
      h("input", {
        type: "radio",
        name: "frontend",
        value,
        onchange: () =>
          void api<{ frontend: string }>("/app/frontend", "PUT", { frontend: value })
            .then((said) => (open.hidden = said.frontend !== "blazor"))
            .catch((error: unknown) => errorHere(error)),
      }),
      label,
    ),
  );
  void api<{ frontend: string }>("/app/frontend")
    .then((said) => {
      for (const radio of radios) {
        const input = radio.querySelector("input")!;
        input.checked = input.value === said.frontend;
      }
      open.hidden = said.frontend !== "blazor";
    })
    .catch(() => undefined);
  return h(
    "fieldset",
    { class: "fieldset" },
    h("legend", {}, icon("desktop"), "Front end"),
    h("div", { class: "form-grid", role: "radiogroup", "aria-label": "Front end" }, ...radios),
    h("p", { class: "muted" }, "The one the app opens. The Blazor front end is a preview: a page it does not have yet links back here. ", open),
  );
}

/** The Settings page, opened by the user (the rail's cog, the Workbench's "…"). */
export function openSettings(): void {
  if (shown?.open) return;
  layerOpened("settings");
  drawSettings();
}

function drawSettings(): void {
  const { element, body } = openAreaPage("settings", "Settings");
  shown = element;
  body.classList.add("settings-page");
  setOverTitle("Settings");
  watchLayerDialog(element, "settings", [], () => {
    if (shown === element) shown = null;
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
      h("legend", {}, icon("sun"), "Theme"),
      h("div", { class: "form-grid", role: "radiogroup", "aria-label": "Theme" }, ...themes),
    ),
    teamSection(),
    frontendSection(),
    gatesSetting(), // a project type's gates: Open every feature in this project
    // Follow the agent (the Session page has the same switch): its actions' areas come to the front.
    h("fieldset", { class: "fieldset follow-fieldset" }, h("legend", {}, icon("session"), "Session"), followSwitch()),
    updatesSection(),
    extensionSettings(),
    claudeSection(),
    betaSection(),
    h(
      "fieldset",
      { class: "fieldset" },
      h("legend", {}, icon("agent"), "Connect an agent"),
      h("pre", { class: "mono mcp-prompt" }, MCP_PROMPT),
      button("Copy the setup prompt", () => void copyMcpPrompt(), { icon: "copy" }),
    ),
  );
  (body.querySelector("input:checked") as HTMLInputElement | null)?.focus();
}
