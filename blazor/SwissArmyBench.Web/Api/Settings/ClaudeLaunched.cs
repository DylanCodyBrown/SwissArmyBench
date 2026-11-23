namespace SwissArmyBench.Web.Api.Settings;

/// <summary>POST /claude/launch: which started, or what to ask first (which one, what to install, Desktop's settings file).</summary>
public sealed record ClaudeLaunched(
    string? Launched = null,
    IReadOnlyList<string>? Choose = null,
    IReadOnlyList<ClaudeHelp>? Missing = null,
    ClaudeConfig? Confirm = null,
    ClaudeConfig? ConfigUnknown = null,
    string? Error = null,
    string? Terminal = null,
    bool Bypass = false,
    bool Changed = false);
