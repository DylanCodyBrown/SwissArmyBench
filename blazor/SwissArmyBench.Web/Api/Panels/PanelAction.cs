namespace SwissArmyBench.Web.Api.Panels;

/// <summary>A button: a click posts {action}; a note under it.</summary>
public sealed record PanelAction
{
    public string Id { get; init; } = string.Empty;

    public string Label { get; init; } = string.Empty;

    public bool Primary { get; init; }

    public bool Disabled { get; init; }

    public string? Note { get; init; }
}
