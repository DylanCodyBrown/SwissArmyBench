namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A table that could not open, and why.</summary>
public sealed record FailedTable(string Table, string Error);
