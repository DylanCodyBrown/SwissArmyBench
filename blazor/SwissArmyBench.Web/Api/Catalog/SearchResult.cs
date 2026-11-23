namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>One thing the Data Explorer's search found (a connection, a table, a column, a structure, an API, a
/// variable, a blade): its key, kind, name, where it is, its detail, how SQL and Python name it, and the parts each
/// kind carries (an open table's grid, a connection's table's place, a column's type, whether a connection's catalog
/// is loaded, a shared table's set-up, a structure's node).</summary>
public sealed record SearchResult(
    string Key,
    string Kind,
    string Name,
    IReadOnlyList<string> Path,
    string? Connection = null,
    string Detail = "",
    string Icon = "",
    InsertText? Insert = null,
    string? Grid = null,
    TablePlace? Place = null)
{
    public string? Source { get; init; }

    public string? Sql { get; init; }

    public string? Variable { get; init; }

    public string? Dataset { get; init; }

    public string? Type { get; init; }

    public bool? Loaded { get; init; }

    public bool Setup { get; init; }

    public string? Pointer { get; init; }

    public string? Structure { get; init; }

    public string? File { get; init; }
}
