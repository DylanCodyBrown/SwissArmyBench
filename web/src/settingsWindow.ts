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
 *          [CONNECT AN AGENT]     Copy -> copyMcpPrompt()  (a prompt that installs the MCP in any agent)
 *          [CLOSE]                -> close()
 *          [AGENT ACCESS]         -> agentAccess.agentAccessSection()  (agent activity)
 */
import { agentAccessSection } from "./agentAccess";
import { button, h, openDialog, toast } from "./dom";
import { THEME_LABELS, setTheme, themeChoice, type ThemeChoice } from "./theme";

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
  "1. Run: claude mcp add --scope user swissarmygrid -- swissarmygrid-mcp",
  "   (another agent: add an MCP server over stdio whose command is swissarmygrid-mcp)",
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

export function openSettings(): void {
  const { body, foot, close } = openDialog("Settings", true);
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
