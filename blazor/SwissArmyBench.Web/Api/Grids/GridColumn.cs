namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A column of a grid's view: its name and DuckDB type (BIGINT, VARCHAR, DATE...).</summary>
public sealed record GridColumn(string Name, string Type);
