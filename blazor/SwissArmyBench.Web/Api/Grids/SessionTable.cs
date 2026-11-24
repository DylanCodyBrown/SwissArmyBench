namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A table a Python session holds: its variable's name, its kind (dataframe, polars, arrow...), its size,
/// and whether it is open on the Tables page.</summary>
public sealed record SessionTable(string Name, string Kind, long? Rows, long? Columns, bool Open);
