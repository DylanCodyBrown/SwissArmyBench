namespace SwissArmyBench.Web.Api.Panels;

/// <summary>A row to work through, with its one fix.</summary>
public sealed record PanelRow
{
    public string Id { get; init; } = string.Empty;

    public string Text { get; init; } = string.Empty;

    public string? Tone { get; init; }

    public PanelRowAction? Action { get; init; }
}
