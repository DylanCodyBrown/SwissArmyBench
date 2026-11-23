namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A table (or a view) of a catalog; with Column set, a search's column of it.</summary>
public sealed record CatalogTable(
    string Table,
    string Schema = "",
    string Database = "",
    string Kind = "table",
    int Columns = 0,
    string? Column = null,
    string? Type = null);
