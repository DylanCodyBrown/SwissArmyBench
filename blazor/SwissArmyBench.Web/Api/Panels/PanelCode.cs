namespace SwissArmyBench.Web.Api.Panels;

/// <summary>A code to copy and a page to open (https only): the page opens on the user's click, then {action: then} is posted.</summary>
public sealed record PanelCode
{
    public string Label { get; init; } = string.Empty;

    public string Text { get; init; } = string.Empty;

    public string Link { get; init; } = string.Empty;

    public string LinkLabel { get; init; } = string.Empty;

    public string Then { get; init; } = string.Empty;

    public bool Waiting { get; init; }
}
