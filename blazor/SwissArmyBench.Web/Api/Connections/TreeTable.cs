namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One table in a connection's tree, and how DuckDB SQL names it ([Shop].orders).</summary>
public sealed record TreeTable(string Table, string? Database = null, string? Schema = null, string Sql = "");
