namespace SwissArmyBench.Web.Api.Panels;

/// <summary>A row's fix: its action id and words.</summary>
public sealed record PanelRowAction
{
    public string Id { get; init; } = string.Empty;

    public string Label { get; init; } = string.Empty;

    public bool Disabled { get; init; }
}
