namespace SwissArmyBench.Web.Api.Settings;

/// <summary>How to install a Claude that is not found: its words, the commands to copy, where to read more.</summary>
public sealed record ClaudeHelp(
    string Kind,
    string Message,
    IReadOnlyList<string>? Commands = null,
    string? Url = null);
