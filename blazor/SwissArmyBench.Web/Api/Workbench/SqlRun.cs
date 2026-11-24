namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A .sql file's run (POST /scripts/sql/run): the open table it built (named after the file), its grid, rows
/// and version, the connection it ran on (none: DuckDB over the open tables), and the file's lines it ran.</summary>
public sealed record SqlRun(
    string Grid,
    string Dataset,
    long Version,
    long Rows,
    string Table,
    int Line,
    int EndLine,
    string? Connection = null,
    IReadOnlyList<SwissArmyBench.Web.Api.Grids.ConnectionRead>? ConnectionReads = null);
