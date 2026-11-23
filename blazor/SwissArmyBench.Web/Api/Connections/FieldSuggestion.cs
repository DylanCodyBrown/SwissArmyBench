namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A value a setting may take, and where it was seen (another blade's, an environment variable).</summary>
public sealed record FieldSuggestion(string Value, string From);
