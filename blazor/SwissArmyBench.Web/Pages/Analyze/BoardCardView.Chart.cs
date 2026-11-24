using System.Text.Json;

using Microsoft.JSInterop;

using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Analyze;

// A chart card (the classic aiPanel.ts): drawn by Vega-Lite, Open large (scatter, line and area zoom with the wheel),
// More card actions' Download image (PNG), Download as HTML and Copy as Python (Altair), and the cross-filter: a
// click on a bar, point or heatmap cell filters the card's own table to that value.
public partial class BoardCardView
{
    private static readonly string[] _zoomableMarks = ["point", "line", "area"];

    private VegaChart? _chart;
    private bool _large;

    private bool IsChart => Card.Kind == "chart" && Card.VegaLite is { ValueKind: JsonValueKind.Object };

    private string ChartSpec => Card.VegaLite?.GetRawText() ?? string.Empty;

    private string Mark => Card.Spec is { ValueKind: JsonValueKind.Object } spec && spec.TryGetProperty("mark", out var mark) ? mark.GetString() ?? string.Empty : string.Empty;

    private bool Zoomable => _zoomableMarks.Contains(Mark);

    private string NoChart => Card.Note is { ValueKind: JsonValueKind.String } note ? note.GetString() ?? string.Empty : "This chart cannot be drawn.";

    private string ChartTitle => Card.Title.Length > 0 ? Card.Title : Name;

    private IEnumerable<MenuEntry> ChartEntries() => IsChart
        ?
        [
            new("Download image (PNG)", "image", () => _chart?.DownloadPngAsync(ChartTitle) ?? Task.CompletedTask),
            new("Download as HTML", "export", () => _chart?.DownloadHtmlAsync(ChartTitle, Card.Dataset) ?? Task.CompletedTask),
            new("Copy as Python (Altair)", "code", CopyAltairAsync),
        ]
        : [];

    private Task CopyAltairAsync() => DoAsync(async () =>
    {
        var made = await AnalyzeApi.ChartCodeAsync(Card.Id);
        await Js.InvokeAsync<bool>("sab.copy", made.Code);
        _ = Notes.SayAsync("Copied the Altair code.");
    });

    private Task LargeSelectAsync((string Value, string? Y) picked)
    {
        _large = false;
        return CrossFilterAsync(picked);
    }

    /// <summary>The cross-filter: the card's table gets the filter step (a heatmap cell's row value too).</summary>
    private Task CrossFilterAsync((string Value, string? Y) picked) => DoAsync(async () =>
    {
        var value = JsonDocument.Parse(picked.Value).RootElement.Clone();
        var cell = Mark == "heatmap" && picked.Y is not null;
        var y = cell ? JsonDocument.Parse(picked.Y!).RootElement.Clone() : (JsonElement?)null;
        await AnalyzeApi.SelectAsync(Card.Id, value, y);
        var words = $"Filtered the table to {Field("x")} = {Shown(value)}{(y is { } row ? $" and {Field("y")} = {Shown(row)}" : string.Empty)}.";
        _ = Notes.SayAsync(words);
    });

    private string Field(string axis) =>
        Card.Spec is { ValueKind: JsonValueKind.Object } spec && spec.TryGetProperty(axis, out var a) && a.TryGetProperty("field", out var f) ? f.ToString() : string.Empty;

    private static string Shown(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.Null => "(blank)",
        JsonValueKind.String => value.GetString() ?? string.Empty,
        _ => value.GetRawText(),
    };
}
