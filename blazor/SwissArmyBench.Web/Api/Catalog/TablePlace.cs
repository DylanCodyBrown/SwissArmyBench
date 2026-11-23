namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>Where a connection's table is: its database, schema and name.</summary>
public sealed record TablePlace(string Table, string? Database = null, string? Schema = null);
