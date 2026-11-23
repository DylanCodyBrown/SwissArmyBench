namespace SwissArmyBench.Web.Api.Sharing;

/// <summary>One app's share: its state, its words, its link, who can open it, the amber note, its error.</summary>
public sealed record ShareState
{
    public string Kind { get; init; } = string.Empty;

    public string App { get; init; } = string.Empty;

    public string Title { get; init; } = string.Empty;

    public string State { get; init; } = string.Empty;

    public string Words { get; init; } = string.Empty;

    public string? Url { get; init; }

    public string? Who { get; init; }

    public string? Note { get; init; }

    public string? Error { get; init; }
}
