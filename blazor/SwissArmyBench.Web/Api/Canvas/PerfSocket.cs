namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>The web socket to the page: messages, size, by element and the biggest (kinds and sizes only).</summary>
public sealed record PerfSocket
{
    public int Messages { get; init; }

    public double Size { get; init; }

    public IReadOnlyDictionary<string, PerfElement> Elements { get; init; } = new Dictionary<string, PerfElement>();

    public IReadOnlyList<PerfMessage> Biggest { get; init; } = [];
}
