namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>One change a panel's dry run lists.</summary>
public sealed record PanelReviewItem(string Text, string? Tone = null, string? Why = null);
