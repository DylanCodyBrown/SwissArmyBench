using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Grids.Values;

/// <summary>
/// The value viewer's rules (the classic valueViewer.ts): text that holds JSON is opened as JSON; an object is a
/// key / value table, an array of objects a table, any other array a list, Markdown formatted, long text wrapped,
/// a short value as it is. Pure, so the rules are tested apart from the page.
/// </summary>
public static partial class ValueRules
{
    // Over this many characters (or with a line break), text is long text, cut in a table to this many.
    public const int LongText = 160;

    private const int ShortText = 80;

    /// <summary>Text that is JSON becomes the parsed value; anything else stays as it is.</summary>
    public static JsonElement Parsed(JsonElement value)
    {
        if (value.ValueKind != JsonValueKind.String)
        {
            return value;
        }
        var text = value.GetString()!.Trim();
        var looks = (text.StartsWith('{') && text.EndsWith('}')) || (text.StartsWith('[') && text.EndsWith(']'));
        if (!looks)
        {
            return value;
        }
        try
        {
            using var document = JsonDocument.Parse(text);
            return document.RootElement.Clone();
        }
        catch (JsonException)
        {
            return value;
        }
    }

    public static ValueShape Detect(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.Null or JsonValueKind.Undefined => ValueShape.Blank,
        JsonValueKind.Array => value.GetArrayLength() > 0 && value.EnumerateArray().All(v => v.ValueKind == JsonValueKind.Object) ? ValueShape.Table : ValueShape.Array,
        JsonValueKind.Object => ValueShape.Object,
        JsonValueKind.Number => ValueShape.Number,
        JsonValueKind.True or JsonValueKind.False => ValueShape.Boolean,
        _ => TextShape(value.GetString() ?? string.Empty),
    };

    private static ValueShape TextShape(string text) =>
        LooksLikeMarkdown(text) ? ValueShape.Markdown : text.Length > ShortText || text.Contains('\n') ? ValueShape.Text : ValueShape.Short;

    public static bool LooksLikeMarkdown(string text)
    {
        Regex[] strong = [Heading(), Fence(), TableRule()];
        if (strong.Any(r => r.IsMatch(text)))
        {
            return true;
        }
        Regex[] weak = [Bullet(), Numbered(), Bold(), Link(), Code(), Quote()];
        return weak.Count(r => r.IsMatch(text)) >= 2;
    }

    /// <summary>The badge's words: "JSON object · 3 keys", "Array of 12 objects", "Text · 412 characters".</summary>
    public static string Describe(JsonElement value, ValueShape shape) => shape switch
    {
        ValueShape.Object => $"JSON object · {Plural(value.EnumerateObject().Count(), "key")}",
        ValueShape.Table => $"Array of {Count(value.GetArrayLength())} objects",
        ValueShape.Array => $"Array · {Plural(value.GetArrayLength(), "item")}",
        ValueShape.Markdown => $"Markdown · {Count(Text(value).Length)} characters",
        ValueShape.Number => "Number",
        ValueShape.Boolean => "True/false",
        ValueShape.Blank => "Blank",
        _ => $"Text · {Count(Text(value).Length)} characters",
    };

    /// <summary>A nested value's summary on its Open button: "[ 3 items ]", "{ 2 keys }".</summary>
    public static string Summary(JsonElement inner) => inner.ValueKind == JsonValueKind.Array
        ? $"[ {Plural(inner.GetArrayLength(), "item")} ]"
        : $"{{ {Plural(inner.EnumerateObject().Count(), "key")} }}";

    /// <summary>A value as text: a string as it is, anything else as its JSON.</summary>
    public static string Text(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString() ?? string.Empty,
        JsonValueKind.Null or JsonValueKind.Undefined => string.Empty,
        _ => value.GetRawText(),
    };

    /// <summary>The layer's text for Copy: a string as it is, anything else as indented JSON.</summary>
    public static string Copied(JsonElement value) =>
        value.ValueKind == JsonValueKind.String ? value.GetString() ?? string.Empty : JsonSerializer.Serialize(value, _indented);

    public static string Pretty(JsonElement value) => JsonSerializer.Serialize(value, _indented);

    private static readonly JsonSerializerOptions _indented = new() { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

    public static string Plural(int count, string word) => $"{Count(count)} {word}{(count == 1 ? string.Empty : "s")}";

    private static string Count(int count) => count.ToString("N0", CultureInfo.CurrentCulture);

    [GeneratedRegex(@"^#{1,6}\s+\S", RegexOptions.Multiline)]
    private static partial Regex Heading();

    [GeneratedRegex(@"^```", RegexOptions.Multiline)]
    private static partial Regex Fence();

    [GeneratedRegex(@"^\|.+\|\s*$\n^\|?\s*:?-{3,}", RegexOptions.Multiline)]
    private static partial Regex TableRule();

    [GeneratedRegex(@"^\s*[-*+]\s+\S", RegexOptions.Multiline)]
    private static partial Regex Bullet();

    [GeneratedRegex(@"^\s*\d+\.\s+\S", RegexOptions.Multiline)]
    private static partial Regex Numbered();

    [GeneratedRegex(@"\*\*[^*\n]+\*\*")]
    private static partial Regex Bold();

    [GeneratedRegex(@"\[[^\]\n]+\]\([^)\s]+\)")]
    private static partial Regex Link();

    [GeneratedRegex(@"`[^`\n]+`")]
    private static partial Regex Code();

    [GeneratedRegex(@"^>\s", RegexOptions.Multiline)]
    private static partial Regex Quote();
}
