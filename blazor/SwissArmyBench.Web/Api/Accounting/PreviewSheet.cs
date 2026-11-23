namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>One sheet as built: its first rows of cells, merged ranges, widths and charts.</summary>
public sealed record PreviewSheet
{
    public string Name { get; init; } = string.Empty;

    public IReadOnlyList<IReadOnlyList<PreviewCell?>> Rows { get; init; } = [];

    public int RowCount { get; init; }

    public int ColumnCount { get; init; }

    public bool Cut { get; init; }

    public IReadOnlyList<string> Merged { get; init; } = [];

    public IReadOnlyDictionary<string, double> Widths { get; init; } = new Dictionary<string, double>();

    public string? Freeze { get; init; }

    public IReadOnlyList<PreviewChart> Charts { get; init; } = [];
}
