using System.Text.Json;

namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>A column in a table's detail: its name, type and whether it takes nulls (the source's own words: YES,
/// true, 1...).</summary>
public sealed record DetailColumn(string Name, string? Type = null, JsonElement? Nullable = null)
{
    private static readonly string[] _yes = ["YES", "Y", "TRUE", "1"];

    /// <summary>Yes, No, or nothing when the source does not say.</summary>
    public string NullsWords => Nullable is not { } value || value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined
        ? string.Empty
        : value.ValueKind switch
        {
            JsonValueKind.True => "Yes",
            JsonValueKind.False => "No",
            JsonValueKind.String when value.GetString() is not { Length: > 0 } => string.Empty,
            _ => _yes.Contains(value.ToString().ToUpperInvariant()) ? "Yes" : "No",
        };
}
