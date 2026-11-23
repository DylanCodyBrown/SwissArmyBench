namespace SwissArmyBench.Web.Api.Blades;

/// <summary>GET /catalogs/{name}/schemas.</summary>
public sealed record CatalogSchemas(IReadOnlyList<CatalogSchema> Schemas);
