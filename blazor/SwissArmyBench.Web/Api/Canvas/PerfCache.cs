namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One cached function: its calls, hits, misses and what the misses cost.</summary>
public sealed record PerfCache
{
    public string Name { get; init; } = string.Empty;

    public string Kind { get; init; } = string.Empty;

    public int Calls { get; init; }

    public int Hits { get; init; }

    public int Misses { get; init; }

    public double MissMs { get; init; }
}
