namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One widget instance's time in a rerun.</summary>
public sealed record PerfBlock
{
    public string Block { get; init; } = string.Empty;

    public string Title { get; init; } = string.Empty;

    public double Ms { get; init; }
}
