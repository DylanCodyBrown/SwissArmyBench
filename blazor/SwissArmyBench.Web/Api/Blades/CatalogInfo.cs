namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A loaded catalog (a connection's tables, named after it): its dialect and counts.</summary>
public sealed record CatalogInfo(
    string Name,
    string Dialect,
    int Databases = 1,
    int Schemas = 0,
    int Tables = 0,
    int Views = 0,
    int Columns = 0);
