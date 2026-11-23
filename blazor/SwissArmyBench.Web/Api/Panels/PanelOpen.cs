using System.Text.Json;

namespace SwissArmyBench.Web.Api.Panels;

/// <summary>A plug-in to open right there, with its context.</summary>
public sealed record PanelOpen
{
    public string Plugin { get; init; } = string.Empty;

    public JsonElement? Context { get; init; }
}
