using System.Text.Json;

namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /grids/{id}/profile?column=: a column's numbers. Every column: rows, blanks, distinct, whether every
/// row differs, the most common values. A number column: its range, mean, median, quartiles, spread, sum, zeros,
/// negatives and histogram; a text column: its shortest and longest, empty and padded text, the values that differ
/// only by case; a date column: its earliest and latest and its rows by month.</summary>
public sealed record ColumnProfile
{
    public string Column { get; init; } = string.Empty;

    public string Type { get; init; } = string.Empty;

    public string Family { get; init; } = string.Empty;

    public long Rows { get; init; }

    public long Blanks { get; init; }

    public double BlankPercent { get; init; }

    public long Distinct { get; init; }

    public bool AllUnique { get; init; }

    public IReadOnlyList<ValueCount> TopValues { get; init; } = [];

    public JsonElement? Min { get; init; }

    public JsonElement? Max { get; init; }

    public double? Mean { get; init; }

    public double? Median { get; init; }

    public double? Q1 { get; init; }

    public double? Q3 { get; init; }

    public double? Stddev { get; init; }

    public double? Sum { get; init; }

    public long? Zeros { get; init; }

    public long? Negatives { get; init; }

    public long? Shortest { get; init; }

    public long? Longest { get; init; }

    public long? EmptyStrings { get; init; }

    public long? Padded { get; init; }

    public JsonElement? Earliest { get; init; }

    public JsonElement? Latest { get; init; }

    public IReadOnlyList<HistogramBin>? Histogram { get; init; }

    public IReadOnlyList<MonthCount>? ByMonth { get; init; }

    public IReadOnlyList<CaseGroup>? CaseGroups { get; init; }
}
