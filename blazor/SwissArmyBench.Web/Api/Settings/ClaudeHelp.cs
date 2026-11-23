namespace SwissArmyBench.Web.Api.Settings;

/// <summary>How to install a Claude that is not found.</summary>
public sealed record ClaudeHelp(string Message, string? Url = null);
