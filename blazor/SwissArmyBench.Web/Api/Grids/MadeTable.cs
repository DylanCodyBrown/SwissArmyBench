namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A new table's grid (the "+" tab's query, a sandbox variant): its grid id and name.</summary>
public sealed record MadeTable(string? Grid, string? Dataset, string? Added, string? Title);
