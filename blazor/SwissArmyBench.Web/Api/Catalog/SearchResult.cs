namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>One thing the Data Explorer's search found (a connection, a table, a column, a structure, an API, a variable, a blade).</summary>
public sealed record SearchResult(string Key, string Kind, string Name, IReadOnlyList<string> Path, string? Connection = null, string Detail = "", string Icon = "", InsertText? Insert = null, string? Grid = null, TablePlace? Place = null);
