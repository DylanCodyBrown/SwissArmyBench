namespace SwissArmyBench.Web.Api.Structures;

/// <summary>A web call with Return as table on: where its records are, and DuckDB's query over the answer.</summary>
public sealed record WebCallTable(string Records, string Conversion);
