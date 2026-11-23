namespace SwissArmyBench.Web.Api.Settings;

/// <summary>One kind of Claude: what was found, the one chosen, help when none is, Desktop's settings file.</summary>
public sealed record ClaudeKind(
    IReadOnlyList<ClaudeInstall> Found,
    string? Chosen,
    ClaudeHelp? Help = null,
    ClaudeConfig? Config = null);
