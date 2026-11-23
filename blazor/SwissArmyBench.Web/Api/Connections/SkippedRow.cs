namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A found connection not imported, and why.</summary>
public sealed record SkippedRow(string Id, string Why);
