namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A table block's column: its label, number format, width and total.</summary>
public sealed record ColumnSpec
{
    public string Name { get; init; } = string.Empty;

    public string? Label { get; init; }

    public string? Format { get; init; }

    public double? Width { get; init; }

    public string? Total { get; init; }
}
