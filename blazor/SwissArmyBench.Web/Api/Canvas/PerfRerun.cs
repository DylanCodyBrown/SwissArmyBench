namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One rerun: its trigger, page, time, each widget instance's time and its web socket's messages.</summary>
public sealed record PerfRerun
{
    public int Index { get; init; }

    public string Trigger { get; init; } = string.Empty;

    public string Page { get; init; } = string.Empty;

    public double Ms { get; init; }

    public IReadOnlyList<PerfBlock> Blocks { get; init; } = [];

    public PerfSocketRerun? Socket { get; init; }
}
