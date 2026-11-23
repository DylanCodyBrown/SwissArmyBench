namespace SwissArmyBench.Web.Api.Panels;

/// <summary>A dry run to look over: each change, then Apply or Cancel.</summary>
public sealed record PanelReview
{
    public string Id { get; init; } = string.Empty;

    public string Heading { get; init; } = string.Empty;

    public IReadOnlyList<PanelReviewItem> Items { get; init; } = [];

    public PanelRowAction Apply { get; init; } = new();

    public PanelRowAction? Cancel { get; init; }

    public string? Empty { get; init; }
}
