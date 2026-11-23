namespace SwissArmyBench.Web.Api.Settings;

/// <summary>Claude Desktop's settings file: where it is, whether it was found there.</summary>
public sealed record ClaudeConfig(string Path, bool Known = false);
