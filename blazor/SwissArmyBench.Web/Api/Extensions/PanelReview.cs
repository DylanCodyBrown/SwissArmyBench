namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>A panel's dry run to look over: each change, then Apply or Cancel.</summary>
public sealed record PanelReview(
    string Id,
    string Heading,
    IReadOnlyList<PanelReviewItem> Items,
    PanelAction Apply,
    PanelAction? Cancel = null,
    string? Empty = null);
