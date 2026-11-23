namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>What a table or a pivot reads: an open table or a DuckDB query.</summary>
public sealed record BlockSource
{
    public string? Table { get; init; }

    public string? Query { get; init; }
}
