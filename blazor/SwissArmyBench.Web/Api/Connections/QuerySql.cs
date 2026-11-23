namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /connections/queries/{id}/sql: a query's SQL as written and formatted for reading.</summary>
public sealed record QuerySql(string Id, string Connection, string Sql, string Formatted, string Language = "sql");
