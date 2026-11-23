namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A rerun's web socket messages: how many and their size.</summary>
public sealed record PerfSocketRerun
{
    public string Trigger { get; init; } = string.Empty;

    public int Messages { get; init; }

    public double Size { get; init; }
}
