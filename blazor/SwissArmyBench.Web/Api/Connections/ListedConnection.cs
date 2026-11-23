namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One saved connection as GET /connections lists it: what the detail's tools ask (its kind, dialect, a catalog, a starter's).</summary>
public sealed record ListedConnection(
    string Name,
    string Connection,
    string Dialect = "",
    string? Template = null,
    string Type = "",
    bool HasCatalog = false,
    string Source = "saved",
    string? TablesKind = null);
