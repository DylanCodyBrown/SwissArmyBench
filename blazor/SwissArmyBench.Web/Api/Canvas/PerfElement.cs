namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One element's messages on the web socket: how many and their size.</summary>
public sealed record PerfElement
{
    public int Count { get; init; }

    public double Size { get; init; }
}
