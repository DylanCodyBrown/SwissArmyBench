using System.Text.Json;
using System.Text.Json.Serialization;

namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A block on a sheet's cells: a title, text, a table, a pivot or a chart, at its cell and its size in
/// cells. A table's columns are specs or names, a pivot's names (so they stay as the server sent them).</summary>
public sealed record WorkbookBlock
{
    public string Id { get; init; } = string.Empty;

    public string Kind { get; init; } = "title";

    public string Cell { get; init; } = "A1";

    public int W { get; init; } = 1;

    public int H { get; init; } = 1;

    public string? Text { get; init; }

    public BlockSource? Source { get; init; }

    public IReadOnlyList<JsonElement>? Columns { get; init; }

    public bool? TotalRow { get; init; }

    public IReadOnlyList<ColourRule>? Conditional { get; init; }

    public IReadOnlyList<string>? Rows { get; init; }

    public IReadOnlyList<PivotValue>? Values { get; init; }

    public bool? Totals { get; init; }

    public string? Chart { get; init; }

    public string? From { get; init; }

    public string? Category { get; init; }

    public IReadOnlyList<string>? Series { get; init; }

    public IReadOnlyList<string>? LineSeries { get; init; }

    public string? Title { get; init; }

    public Dictionary<string, JsonElement>? Style { get; init; }

    [JsonExtensionData]
    public Dictionary<string, JsonElement>? Extra { get; init; }
}
