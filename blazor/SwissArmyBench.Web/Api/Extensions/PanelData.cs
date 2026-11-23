namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>An extension's own panel, as data: lines, switches, actions, choices, rows, a code, busy words, a review.</summary>
public sealed record PanelData(
    IReadOnlyList<PanelLine> Lines,
    IReadOnlyList<PanelSwitch> Switches,
    IReadOnlyList<PanelAction> Actions,
    IReadOnlyList<PanelChoice>? Choices = null,
    IReadOnlyList<PanelRow>? Rows = null,
    string? Heading = null,
    PanelCode? Code = null,
    string? Busy = null,
    PanelReview? Review = null);
