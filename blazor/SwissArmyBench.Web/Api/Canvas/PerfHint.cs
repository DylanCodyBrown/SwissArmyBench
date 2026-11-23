namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A hint in plain words: what to change and where.</summary>
public sealed record PerfHint
{
    public string Rule { get; init; } = string.Empty;

    public string Words { get; init; } = string.Empty;

    public string? Block { get; init; }
}
