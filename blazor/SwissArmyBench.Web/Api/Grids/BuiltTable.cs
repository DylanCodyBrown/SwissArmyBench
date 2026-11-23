namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A table built from a query (POST /datasets/{name}/query, /connection-query): its grid, rows and version,
/// the connection it ran on, and the connections' tables it read.</summary>
public sealed record BuiltTable(
    string Grid,
    string Dataset,
    long Version,
    long Rows,
    string? Connection = null,
    IReadOnlyList<ConnectionRead>? ConnectionReads = null);
