namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>Export workbook.py: where it was written, how to run it, the tables it reads.</summary>
public sealed record ExportedWorkbook
{
    public string Path { get; init; } = string.Empty;

    public string Run { get; init; } = string.Empty;

    public IReadOnlyList<string> Tables { get; init; } = [];
}
