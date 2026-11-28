namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One query's composed DuckDB SQL (POST /scripts/pq/sql): the query, the table it makes, the SQL and the
/// sources the SQL names.</summary>
public sealed record PowerQuerySql(
    string Query,
    string Table,
    string Sql,
    int Line,
    IReadOnlyList<PowerQuerySource> Sources);
