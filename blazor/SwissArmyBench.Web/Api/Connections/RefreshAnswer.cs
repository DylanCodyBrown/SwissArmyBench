namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /blades/{name}/refresh: the catalog listed again.</summary>
public sealed record RefreshAnswer(CatalogCount Catalog);
