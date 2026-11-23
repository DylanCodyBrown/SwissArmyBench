namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>A connection's tables in one database and schema (a Power BI workspace's dataset).</summary>
public sealed record BrowseGroup(string Database, string Schema, int Count, IReadOnlyList<SearchResult> Tables);
