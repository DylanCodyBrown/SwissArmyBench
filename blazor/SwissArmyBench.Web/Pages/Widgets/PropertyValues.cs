using System.Globalization;
using System.Text.Json;

namespace SwissArmyBench.Web.Pages.Widgets;

/// <summary>A property's value as its box shows it, and a box's text made the value it sends (the classic
/// widgetFields.ts's text() and its parsing).</summary>
public static class PropertyValues
{
    /// <summary>The made-up sample's columns (sab_canvas.sample): a column property with no table picks among these.</summary>
    public static readonly IReadOnlyList<string> SampleColumns = ["month", "region", "product", "revenue", "units", "margin", "lat", "lon"];

    public static string Text(JsonElement? value) => value switch
    {
        null => string.Empty,
        { ValueKind: JsonValueKind.Null or JsonValueKind.Undefined } => string.Empty,
        { ValueKind: JsonValueKind.String } text => text.GetString() ?? string.Empty,
        { ValueKind: JsonValueKind.True } => "true",
        { ValueKind: JsonValueKind.False } => "false",
        { } other => other.GetRawText(),
    };

    public static bool Flag(JsonElement? value) => value switch
    {
        { ValueKind: JsonValueKind.True } => true,
        { ValueKind: JsonValueKind.String } text => !string.IsNullOrEmpty(text.GetString()),
        { ValueKind: JsonValueKind.Number } number => number.GetDouble() != 0,
        _ => false,
    };

    /// <summary>The value as JSON text (a json property's box).</summary>
    public static string Json(JsonElement? value) => value is { ValueKind: not JsonValueKind.Undefined } given ? given.GetRawText() : "null";

    /// <summary>A number box's text as the number it sends (a whole one for an int property), or null when it is not one.</summary>
    public static object? Number(string text, string type)
    {
        if (!double.TryParse(text.Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out var number) || text.Trim().Length == 0)
        {
            return null;
        }
        return type == "int" && Math.Abs(number % 1) < double.Epsilon ? (long)number : number;
    }

    /// <summary>A JSON box's text parsed, or null when it is not JSON yet.</summary>
    public static JsonElement? Parsed(string text)
    {
        try
        {
            using var parsed = JsonDocument.Parse(text);
            return parsed.RootElement.Clone();
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>The {name}s of an endpoint's path ("GET /orders/{region}" has region), each once.</summary>
    public static IReadOnlyList<string> PathNames(string endpoint)
    {
        var path = endpoint.Contains(' ', StringComparison.Ordinal) ? endpoint[(endpoint.IndexOf(' ', StringComparison.Ordinal) + 1)..] : endpoint;
        return System.Text.RegularExpressions.Regex.Matches(path, @"\{([A-Za-z_]\w*)\}")
            .Select(m => m.Groups[1].Value)
            .Distinct()
            .ToList();
    }

    /// <summary>A path_values property's map of {name} to its value.</summary>
    public static IReadOnlyDictionary<string, string> Map(JsonElement? value) =>
        value is { ValueKind: JsonValueKind.Object } given
            ? given.EnumerateObject().ToDictionary(p => p.Name, p => Text(p.Value))
            : new Dictionary<string, string>();
}
