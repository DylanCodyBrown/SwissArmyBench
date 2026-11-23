namespace SwissArmyBench.Web.Api.Blades;

/// <summary>GET /catalogs/{name}/search: the tables and columns whose names hold the words.</summary>
public sealed record CatalogSearch(IReadOnlyList<CatalogTable> Tables, IReadOnlyList<CatalogTable> Columns);
