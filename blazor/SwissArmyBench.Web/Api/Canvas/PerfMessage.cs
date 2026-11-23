namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One big message: its direction, kind, element, path and size.</summary>
public sealed record PerfMessage
{
    public string Direction { get; init; } = string.Empty;

    public string Kind { get; init; } = string.Empty;

    public string? Element { get; init; }

    public string? Path { get; init; }

    public double Size { get; init; }
}
