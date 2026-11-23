namespace SwissArmyBench.Web.Api.Structures;

/// <summary>PUT /apis/{api}/calls/{operation} {as_table}: the table's name in DuckDB SQL and the web call.</summary>
public sealed record ReturnedAsTable(string? SqlName, WebCallTable WebCall);
