namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A table's .sql file (POST /scripts/sql/for-table, Edit in Scripts): its path, whether it was made now
/// from the table's query, and the connection the query runs on.</summary>
public sealed record SqlTableFile(string Path, bool Made, string Table, string? Connection = null);
