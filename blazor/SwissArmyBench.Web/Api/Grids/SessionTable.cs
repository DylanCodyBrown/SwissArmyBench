namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A table a Python session holds: its variable's name, its kind (dataframe, polars, arrow...), its size,
/// and whether it is open as a grid.</summary>
public sealed record SessionTable(string Name, string Kind, long? Rows, long? Columns, bool Open);
