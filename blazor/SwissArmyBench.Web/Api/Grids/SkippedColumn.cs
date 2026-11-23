namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A column the Key Finder did not compare, and why.</summary>
public sealed record SkippedColumn(string Column, string Reason);
