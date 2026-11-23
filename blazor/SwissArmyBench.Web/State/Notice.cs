using System.Text.Json;

namespace SwissArmyBench.Web.State;

/// <summary>One notice from the live-updates socket: its type ("rail_changed", "grid_changed"...) and the whole
/// message, read by the page that cares.</summary>
public sealed record Notice(string Type, JsonElement Body)
{
    /// <summary>A text field of the notice, or null.</summary>
    public string? Text(string name) =>
        Body.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    /// <summary>A true/false field of the notice, or null.</summary>
    public bool? Flag(string name) =>
        Body.TryGetProperty(name, out var value) && value.ValueKind is JsonValueKind.True or JsonValueKind.False ? value.GetBoolean() : null;
}
