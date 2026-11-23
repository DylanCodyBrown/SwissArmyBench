namespace SwissArmyBench.Web.Api.Blades;

/// <summary>GET /catalogs/{name}/columns: a table's columns and the SELECT that reads it in its dialect.</summary>
public sealed record CatalogColumns(
    string Dialect,
    string Table,
    IReadOnlyList<CatalogColumn> Columns,
    string Select = "",
    string Schema = "");
