namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A native chart of a sheet: where it is anchored, its size in centimetres, its series.</summary>
public sealed record PreviewChart
{
    public string Kind { get; init; } = string.Empty;

    public string Cell { get; init; } = string.Empty;

    public double Width { get; init; }

    public double Height { get; init; }

    public string? Title { get; init; }

    public IReadOnlyList<string> Categories { get; init; } = [];

    public IReadOnlyList<ChartSeries> Series { get; init; } = [];
}
