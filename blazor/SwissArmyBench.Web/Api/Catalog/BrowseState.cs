namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>A connection's catalog: loaded, loading, waiting, failed (with its error) or none.</summary>
public sealed record BrowseState(string State, string? Error = null);
