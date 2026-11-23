namespace SwissArmyBench.Web.Api.Settings;

/// <summary>One kind of Claude: what was found, the one chosen, and help when none is.</summary>
public sealed record ClaudeKind(IReadOnlyList<ClaudeInstall> Found, string? Chosen, ClaudeHelp? Help = null);
