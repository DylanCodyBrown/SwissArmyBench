namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A catalog's schema (a Power BI workspace's dataset): its database and counts.</summary>
public sealed record CatalogSchema(string Schema, string Database = "", int Tables = 0, int Views = 0);
