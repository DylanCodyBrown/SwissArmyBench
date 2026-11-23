namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /structures/{id}/grid: a list of records opened as a table of its own, and its rows.</summary>
public sealed record StructureGrid(string? Grid, string Dataset, long Rows);
