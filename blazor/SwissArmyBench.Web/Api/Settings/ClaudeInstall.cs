namespace SwissArmyBench.Web.Api.Settings;

/// <summary>A Claude found on this computer (Claude Code or Claude Desktop).</summary>
public sealed record ClaudeInstall(string Kind, string Path, string Name, string Source, bool Official);
