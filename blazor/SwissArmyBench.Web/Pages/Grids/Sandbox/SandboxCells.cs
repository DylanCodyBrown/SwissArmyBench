using System.Text.Json;

namespace SwissArmyBench.Web.Pages.Grids.Sandbox;

/// <summary>A sandbox cell's rules (the classic sandboxGrid.ts): a LIST, STRUCT or MAP column takes JSON; its value
/// shown as its JSON box shows it; why typed text is not JSON.</summary>
public static class SandboxCells
{
    public static bool IsNested(string type)
    {
        var upper = type.ToUpperInvariant().Trim();
        return upper.EndsWith(']') || upper.StartsWith("STRUCT(", StringComparison.Ordinal) || upper.StartsWith("MAP(", StringComparison.Ordinal);
    }

    /// <summary>A cell's value in its box: JSON for a nested column, else its text.</summary>
    public static string Shown(JsonElement value, bool nested) => value.ValueKind switch
    {
        JsonValueKind.Null or JsonValueKind.Undefined => string.Empty,
        JsonValueKind.String when nested && IsJson(value.GetString()!) => value.GetString()!,
        JsonValueKind.String when nested => JsonSerializer.Serialize(value.GetString()),
        JsonValueKind.String => value.GetString()!,
        _ => value.GetRawText(),
    };

    /// <summary>Why a nested cell's text cannot be sent (not JSON), else null.</summary>
    public static string? JsonProblem(string text)
    {
        if (text.Trim().Length == 0)
        {
            return null;
        }
        try
        {
            using var _ = JsonDocument.Parse(text);
            return null;
        }
        catch (JsonException error)
        {
            return $"Not JSON: {error.Message}";
        }
    }

    private static bool IsJson(string text) => JsonProblem(text) is null && text.Trim().Length > 0;
}
