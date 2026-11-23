namespace SwissArmyBench.Web.Api.Blades;

/// <summary>GET /catalogs: the loaded catalogs.</summary>
public sealed record CatalogList(IReadOnlyList<CatalogInfo> Catalogs);
