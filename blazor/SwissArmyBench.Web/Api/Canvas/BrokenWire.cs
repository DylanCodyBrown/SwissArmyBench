namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A wire that does not hold any more, and why.</summary>
public sealed record BrokenWire
{
    public string Instance { get; init; } = string.Empty;

    public string Port { get; init; } = string.Empty;

    public string Reason { get; init; } = string.Empty;

    public string? Source { get; init; }
}
