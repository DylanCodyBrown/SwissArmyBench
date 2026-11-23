namespace SwissArmyBench.Web.Api.Panels;

/// <summary>What the panel says, and its tone (ok, warn, error or none).</summary>
public sealed record PanelLine
{
    public string Text { get; init; } = string.Empty;

    public string? Tone { get; init; }
}
