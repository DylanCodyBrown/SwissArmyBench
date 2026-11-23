namespace SwissArmyBench.Web.Api.Blades;

/// <summary>GET /catalogs/{name}/tables: a schema's tables, and how many there are.</summary>
public sealed record CatalogTables(int Total, IReadOnlyList<CatalogTable> Tables);
