namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>
/// What a run sends (POST /workbench/kernels/{id}/execute): the code and its kind (code, sql, dax, table, file), a
/// SQL or DAX cell's connection, a table cell's table, a saved script's path for Run file, and the document it runs
/// for (a table it sends lands in that document's Tables group).
/// </summary>
public sealed record RunRequest(
    string Code,
    string Kind = "code",
    string? Connection = null,
    string? Table = null,
    string? Path = null,
    string? Document = null);
