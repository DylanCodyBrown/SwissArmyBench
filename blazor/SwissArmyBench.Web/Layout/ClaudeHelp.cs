namespace SwissArmyBench.Web.Layout;

/// <summary>Launch Claude's install help for one app (code or desktop): its commands and its page.</summary>
public sealed record ClaudeHelp(string Kind, IReadOnlyList<string> Commands, string Url = "");
