namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>A connection whose catalog is not searched yet: its state (loading, failed, not loaded) and its error.</summary>
public sealed record CatalogOffer(string Connection, string State = "", string? Error = null);
