namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A catalog loading in the background: loading, waiting (first use), failed and why, or loaded.</summary>
public sealed record CatalogState(string State, string? Error = null);
