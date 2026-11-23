namespace SwissArmyBench.Web.Api.Panels;

/// <summary>One change of a dry run, its tone and why.</summary>
public sealed record PanelReviewItem
{
    public string Text { get; init; } = string.Empty;

    public string? Tone { get; init; }

    public string? Why { get; init; }
}
