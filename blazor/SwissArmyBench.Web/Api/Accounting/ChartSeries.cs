namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A chart's series: its name, column or line, its values.</summary>
public sealed record ChartSeries
{
    public string Name { get; init; } = string.Empty;

    public string Kind { get; init; } = string.Empty;

    public IReadOnlyList<double?> Values { get; init; } = [];
}
