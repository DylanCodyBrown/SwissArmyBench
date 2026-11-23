namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>An Out (or an Event's last payload) an In can read: its type, its instance and widget, its port and page.</summary>
public sealed record OutRef
{
    public string Type { get; init; } = string.Empty;

    public string Instance { get; init; } = string.Empty;

    public string Widget { get; init; } = string.Empty;

    public string Port { get; init; } = string.Empty;

    public string Direction { get; init; } = string.Empty;

    public string? Page { get; init; }
}
