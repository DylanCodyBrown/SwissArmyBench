using System.Text.Json;
using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>
/// An output record (nbformat's: stream, execute_result, display_data, error) read for drawing, and a run's
/// records kept as a notebook saves them: consecutive text of one stream joined, a clear honoured.
/// </summary>
public static partial class OutputReader
{
    public static string Type(JsonElement output) => Text(output, "output_type");

    public static string Text(JsonElement output, string name) =>
        output.ValueKind == JsonValueKind.Object && output.TryGetProperty(name, out var value)
            ? value.ValueKind switch
            {
                JsonValueKind.String => value.GetString() ?? string.Empty,
                JsonValueKind.Array => string.Concat(value.EnumerateArray().Select(v => v.GetString())),
                _ => value.GetRawText(),
            }
            : string.Empty;

    /// <summary>A rich output's data for one MIME type (a list of lines joined), or null.</summary>
    public static string? Data(JsonElement output, string mime) =>
        output.TryGetProperty("data", out var data) && data.ValueKind == JsonValueKind.Object && data.TryGetProperty(mime, out var value)
            ? value.ValueKind switch
            {
                JsonValueKind.String => value.GetString(),
                JsonValueKind.Array => string.Concat(value.EnumerateArray().Select(v => v.GetString())),
                _ => value.GetRawText(),
            }
            : null;

    /// <summary>The terminal's colour codes taken out (a traceback's, a progress bar's).</summary>
    public static string Plain(string text) => Ansi().Replace(text, string.Empty);

    /// <summary>A traceback's lines as one text.</summary>
    public static string Traceback(JsonElement output) =>
        output.TryGetProperty("traceback", out var lines) && lines.ValueKind == JsonValueKind.Array
            ? Plain(string.Join('\n', lines.EnumerateArray().Select(l => l.GetString())))
            : $"{Text(output, "ename")}: {Text(output, "evalue")}";

    /// <summary>A traceback's lines as one text, its colours kept (AnsiPre draws them).</summary>
    public static string ColouredTraceback(JsonElement output) =>
        output.TryGetProperty("traceback", out var lines) && lines.ValueKind == JsonValueKind.Array
            ? string.Join('\n', lines.EnumerateArray().Select(l => l.GetString()))
            : $"{Text(output, "ename")}: {Text(output, "evalue")}";

    /// <summary>A record added to a cell's outputs: a stream's text joins the stream before it, as a notebook keeps it.</summary>
    public static void Add(List<JsonElement> outputs, JsonElement record)
    {
        if (Type(record) == "stream" && outputs.Count > 0 && Type(outputs[^1]) == "stream" && Text(outputs[^1], "name") == Text(record, "name"))
        {
            var joined = new { output_type = "stream", name = Text(record, "name"), text = Text(outputs[^1], "text") + Text(record, "text") };
            outputs[^1] = JsonSerializer.SerializeToElement(joined);
            return;
        }
        outputs.Add(record.Clone());
    }

    [GeneratedRegex(@"\x1b\[[0-9;]*[A-Za-z]")]
    private static partial Regex Ansi();
}
