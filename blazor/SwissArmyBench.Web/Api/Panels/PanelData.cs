namespace SwissArmyBench.Web.Api.Panels;

/// <summary>An extension's own panel, as its backend answers it (the classic extensionPanel.ts): lines, switches, actions, choices, rows, a code and a page, busy words, a dry run to review, a plug-in to open.</summary>
public sealed record PanelData
{
    public string? Title { get; init; }

    public IReadOnlyList<PanelLine> Lines { get; init; } = [];

    public IReadOnlyList<PanelSwitch> Switches { get; init; } = [];

    public IReadOnlyList<PanelAction> Actions { get; init; } = [];

    public IReadOnlyList<PanelChoice> Choices { get; init; } = [];

    public IReadOnlyList<PanelRow> Rows { get; init; } = [];

    public string? Heading { get; init; }

    public PanelCode? Code { get; init; }

    public string? Busy { get; init; }

    public PanelReview? Review { get; init; }

    public PanelOpen? Open { get; init; }
}
