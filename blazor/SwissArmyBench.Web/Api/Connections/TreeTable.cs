namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One table in a connection's tree, how DuckDB SQL names it ([Shop].orders) and what its source says of it.</summary>
public sealed record TreeTable(
    string Table,
    string? Database = null,
    string? Schema = null,
    string Sql = "",
    string? Title = null);
