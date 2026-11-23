using System.Text.Json;
using System.Text.Json.Serialization;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>One action of an Event (services/canvas.py): call an endpoint (its body: the whole payload, a part of it,
/// or a field each; its path's values), set a page value, or rerun the page.</summary>
public sealed record EventAction
{
    [JsonPropertyName("do")]
    public string Do { get; init; } = "rerun";

    public string? Endpoint { get; init; }

    /// <summary>Text (empty: the whole payload; else a part of it), or an object of field to value.</summary>
    public JsonElement? Body { get; init; }

    public IReadOnlyDictionary<string, string>? Params { get; init; }

    public string? Key { get; init; }

    public string? Value { get; init; }

    /// <summary>The body's field-by-field map, when it is one.</summary>
    public IReadOnlyDictionary<string, string>? Mapped => Body is { ValueKind: JsonValueKind.Object } body
        ? body.EnumerateObject().ToDictionary(p => p.Name, p => p.Value.GetString() ?? string.Empty)
        : null;

    /// <summary>The body as text (empty: the whole payload).</summary>
    public string BodyText => Body is { ValueKind: JsonValueKind.String } body ? body.GetString() ?? string.Empty : string.Empty;
}
