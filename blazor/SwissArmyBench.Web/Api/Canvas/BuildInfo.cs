namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One build: its number, time, what changed in words, its result, its first load and its saved analyzer sessions.</summary>
public sealed record BuildInfo
{
    public int Number { get; init; }

    public string Time { get; init; } = string.Empty;

    public IReadOnlyList<string> Changed { get; init; } = [];

    public string Result { get; init; } = string.Empty;

    public double? FirstLoadMs { get; init; }

    public IReadOnlyList<string> Sessions { get; init; } = [];

    public string? Error { get; init; }
}
