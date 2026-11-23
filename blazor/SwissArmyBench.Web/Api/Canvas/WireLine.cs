namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One wire: from an Out to an In, automatic (by name), from another page.</summary>
public sealed record WireLine
{
    public string From { get; init; } = string.Empty;

    public string To { get; init; } = string.Empty;

    public bool Auto { get; init; }

    public bool Cross { get; init; }

    public string? Page { get; init; }
}
