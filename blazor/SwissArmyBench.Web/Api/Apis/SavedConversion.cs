namespace SwissArmyBench.Web.Api.Apis;

/// <summary>A saved web call's table: where its rows are and DuckDB's query over them.</summary>
public sealed record SavedConversion(string? Records = null, string? Conversion = null);
