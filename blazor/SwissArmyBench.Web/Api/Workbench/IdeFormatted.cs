namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /scripts/format's answer: formatted or why not, the text, whether it changed.</summary>
public sealed record IdeFormatted(bool Formatted, string? Text = null, string? Why = null, bool Changed = false);
