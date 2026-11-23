namespace SwissArmyBench.Web.Api.Panels;

/// <summary>A switch: a change posts {switch, on}.</summary>
public sealed record PanelSwitch
{
    public string Id { get; init; } = string.Empty;

    public string Label { get; init; } = string.Empty;

    public bool On { get; init; }

    public bool Disabled { get; init; }
}
