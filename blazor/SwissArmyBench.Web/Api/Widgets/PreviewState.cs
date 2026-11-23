namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>A widget's rendered preview: coming, ready (its picture) or failed (its words, what it needs, when to ask again).</summary>
public sealed record PreviewState
{
    public string State { get; init; } = string.Empty;

    public string? Url { get; init; }

    public string? Said { get; init; }

    public string? Kind { get; init; }

    public double? RetryIn { get; init; }

    public MissingPackages? Missing { get; init; }

    public string? Install { get; init; }
}
