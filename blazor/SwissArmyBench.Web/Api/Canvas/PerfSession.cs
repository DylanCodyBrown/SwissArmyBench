namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>The Performance Analyzer's session for a launch (domain/perf.py): its reruns, calls, caches, web socket and hints.</summary>
public sealed record PerfSession
{
    public string Canvas { get; init; } = string.Empty;

    public int Build { get; init; }

    public bool Recording { get; init; }

    public IReadOnlyList<PerfRerun> Reruns { get; init; } = [];

    public IReadOnlyList<PerfCall> Calls { get; init; } = [];

    public IReadOnlyList<PerfCache> Caches { get; init; } = [];

    public PerfSocket? Socket { get; init; }

    public IReadOnlyList<PerfHint> Hints { get; init; } = [];
}
