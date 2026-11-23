namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One file of a comparison: its status, its two sides and the lines added and removed.</summary>
public sealed record ComparedFile
{
    public string File { get; init; } = string.Empty;

    public string Status { get; init; } = string.Empty;

    public string? Before { get; init; }

    public string? After { get; init; }

    public int Added { get; init; }

    public int Removed { get; init; }
}
