namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /catalogs/{connection}/tables: a schema's tables.</summary>
public sealed record CatalogTablesAnswer(IReadOnlyList<SwapPlace> Tables);
